/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/materials_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;
#ifdef __APPLE__
constexpr auto primary_modifier = wm::ModOS;
#else
constexpr auto primary_modifier = wm::ModCtrl;
#endif

// Real strict bridge, validation, immutable input capture, durable jobs and model admission.
// Only the optional trainer is controlled: these tests prove UI/event/state behavior, not
// PyTorch training accuracy. It must load the actual frozen capsule after the live data is gone.
constexpr const char *kMaterialsBridge = R"PY(
from pathlib import Path
import hashlib
import json
import sys
import threading
import time
from suan.materials import curves, datasets, inputs, training
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main
control = Path(sys.argv.pop(1))
counter_lock = threading.Lock()
def count(name):
    with counter_lock, control.with_suffix('.calls').open('a', encoding='utf-8') as stream:
        stream.write(name + '\n')
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
operation = Bridge.materials_call
def recording(self, action, params):
    count(action)
    return operation(self, action, params)
Bridge.materials_call = recording
send = Bridge.send
def controlled_send(self, message, method=None):
    held = None
    if ('result' in message and method == 'materials.jobs.get'
            and message['result']['job']['state'] == 'prepared'
            and control.with_suffix('.hold_job').exists()):
        held = 'job'
    if ('result' in message and method == 'materials.models.list'
            and message['result'].get('kinds', {}).get('capacity_fade', {}).get('active') == 'v2'
            and control.with_suffix('.hold_models').exists()):
        held = 'models'
    if held:
        control.with_suffix('.' + held + '_held').write_text('constructed', encoding='utf-8')
        def deliver_snapshot(prefix=held):
            deadline = time.monotonic() + 30
            while not control.with_suffix('.' + prefix + '_release').exists():
                if time.monotonic() >= deadline:
                    return
                time.sleep(.01)
            send(self, message, method)
            control.with_suffix('.' + prefix + '_sent').write_text('sent', encoding='utf-8')
        threading.Thread(target=deliver_snapshot, daemon=True).start()
        return
    if (method == 'materials.datasets.validate' and 'result' in message
            and control.with_suffix('.hold_validate').exists()):
        control.with_suffix('.validate_held').write_text('constructed', encoding='utf-8')
        def deliver_validate():
            deadline = time.monotonic() + 30
            while not control.with_suffix('.validate_release').exists():
                if time.monotonic() >= deadline:
                    return
                time.sleep(.01)
            send(self, message, method)
            control.with_suffix('.validate_sent').write_text('sent', encoding='utf-8')
        threading.Thread(target=deliver_validate, daemon=True).start()
        return
    if method == 'materials.prepare' and 'result' in message:
        control.with_suffix('.prepared').write_text('frozen', encoding='utf-8')
        def deliver():
            deadline = time.monotonic() + 30
            while not control.with_suffix('.prepare_release').exists():
                if time.monotonic() >= deadline:
                    return
                time.sleep(.01)
            send(self, message, method)
        threading.Thread(target=deliver, daemon=True).start()
        return
    return send(self, message, method)
Bridge.send = controlled_send
def controlled_train(directory, output, *, frozen=False, progress=None, cancel=None, **kwargs):
    if not frozen:
        raise AssertionError('The UI started an unfrozen training request')
    manifest, description, samples = inputs.load(directory)
    count('train_worker')
    control.with_suffix('.input.json').write_text(json.dumps(manifest), encoding='utf-8')
    for epoch in (1, 2):
        progress(epoch, .6 / epoch, .8 / epoch)
    control.with_suffix('.input_ready').write_text('ready', encoding='utf-8')
    deadline = time.monotonic() + 30
    while not control.with_suffix('.train_release').exists():
        if cancel.is_set():
            raise training.Cancelled('Controlled UI training cancelled')
        if time.monotonic() >= deadline:
            raise AssertionError('UI test did not release its controlled trainer')
        time.sleep(.01)
    progress(3, .1, .2)
    split = manifest['split']
    metrics = {'samples': len(split['test']), 'rmse': .001, 'normalized_rmse': .01}
    selected = {sample['id']: sample for sample in samples}
    preview = {'grid': curves.grid(manifest['kind']), 'samples': [
        {'id': identity, 'inputs': selected[identity]['inputs'],
         'observed': selected[identity]['curve'], 'candidate': selected[identity]['curve'],
         **{role: selected[identity]['curve'] if manifest[role + '_model'] else None
            for role in ('base', 'baseline')}} for identity in split['test'][:3]]}
    weights = b'controlled UI fixture; not a torch model'
    meta = {'format': training.MODEL_FORMAT, 'kind': manifest['kind'],
        'inputs': description['inputs'], 'grid': curves.grid(manifest['kind']),
        'created_at': '2026-10-29T00:00:00+00:00', 'dataset': {
            'name': description['name'], 'sha256': datasets.digest(description, samples),
            'samples': len(samples), 'synthetic': description['synthetic'],
            'license': description['license'], 'sensitivity': description['sensitivity']},
        'metrics': {'test': metrics, 'train': {**metrics, 'samples': len(split['train'])},
                    'epochs': 3, 'best_epoch': 3, 'seconds': 0},
        'comparison': {'format': 'stk.materials-training-comparison/1',
            'test_sha256': digest(split['test']), 'test_samples': len(split['test']),
            'candidate': metrics,
            **{role: metrics if manifest[role + '_model'] else None for role in ('base', 'baseline')}},
        'evaluation_preview': preview, 'weights_sha256': hashlib.sha256(weights).hexdigest(),
        'training_input': {'capsule_sha256': manifest['sha256'], 'split_sha256': digest(split),
            'split_counts': {key: len(ids) for key, ids in split.items()},
            'base_model': manifest['base_model'], 'baseline_model': manifest['baseline_model']}}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'model.pt').write_bytes(weights)
    (output / 'model.json').write_text(json.dumps(meta, allow_nan=False), encoding='utf-8')
    return meta
training.torch_module = lambda: object()
training.train = controlled_train
main()
)PY";

class MaterialsEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"materials-editor"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 1100};
  std::unique_ptr<bridge::Client> client;
  std::shared_ptr<const io::Payload> shown;
  Json viewer_state, python_draft;
  uint64_t camera_serial = 0, payload_serial = 0;
  double clock = 1000;
  int clicks = 0;
  AppStore &store() { return f.shell->store(); }
  EditorArea &area() { return f.area("a4"); }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  std::string dataset() const { return core::path_to_utf8(dir.path() / "live-data"); }
  void frame() { f.screen.run_deferred(); f.drv->frame(); }
  void release(const std::string &suffix)
  {
    std::ofstream stream(dir.path() / ("control." + suffix), std::ios::binary); stream << "release";
  }
  int count(const std::string &name) const
  {
    std::ifstream stream(dir.path() / "control.calls");
    int result = 0; std::string line;
    while (std::getline(stream, line)) { result += line == name; }
    return result;
  }
  Json call(const std::string &method, Json params)
  {
    std::optional<bridge::Result<Json>> result;
    client->call(method, std::move(params)).then([&](auto value) { result = std::move(value); });
    if (!loop.pump_until([&] { return result.has_value(); }, 30) || !result->ok()) {
      ADD_FAILURE() << method << ": " << (result ? result->error().describe() : "timed out");
      return nullptr;
    }
    return result->value();
  }
  void wait_widget(const std::string &key)
  {
    ASSERT_TRUE(loop.pump_until([&] { frame(); const auto *item = widget(key); return item && item->enabled; }, 30)) << key;
  }
  void visible(const std::string &key)
  {
    frame(); const auto *item = widget(key); ASSERT_NE(item, nullptr) << key;
    const auto clipped = item->rect.intersect(item->clip);
    EXPECT_NEAR(clipped.w, item->rect.w, 1.0f) << key;
    EXPECT_NEAR(clipped.h, item->rect.h, 1.0f) << key;
    EXPECT_GT(clipped.w, 12 * f.screen.ui()->style().pixel) << key;
    EXPECT_GT(clipped.h, 8 * f.screen.ui()->style().pixel) << key;
  }
  void click(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(visible(key));
    ASSERT_TRUE(widget(key)->enabled) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_GE(x, f.screen.rect().xmin); ASSERT_LT(x, f.screen.rect().xmax);
    ASSERT_GE(y, f.screen.rect().ymin); ASSERT_LT(y, f.screen.rect().ymax);
    ASSERT_TRUE(f.drv->click(x, y)) << key; ++clicks; frame();
  }
  void click_tab(const std::string &key, int index)
  {
    ASSERT_NO_FATAL_FAILURE(visible(key)); const auto *item = widget(key);
    ASSERT_EQ(item->type, ui::WidgetType::Tabs); ASSERT_TRUE(item->enabled);
    ASSERT_GE(index, 0); ASSERT_LT(size_t(index), item->items.size());
    const int x = int(item->rect.x + item->rect.w * (float(index) + .5f) / float(item->items.size()));
    const int y = f.screen.rect().ymax - 1 - int(item->rect.y + item->rect.h * .5f);
    ASSERT_TRUE(f.drv->click(x, y)); ++clicks; frame();
  }
  void text(const std::string &key, const std::string &value)
  {
    ASSERT_NO_FATAL_FAILURE(click(key)); f.drv->key(wm::Key::A, primary_modifier);
    auto event = ui::Event::text_input(value); event.time = ++clock;
    f.screen.ui()->handle_event(event); frame(); f.drv->key(wm::Key::Enter); frame();
  }
  void select_dropdown(const std::string &key, const std::string &prefix)
  {
    frame(); const auto *item = widget(key); ASSERT_NE(item, nullptr);
    int index = -1;
    for (size_t i = 0; i < item->items.size(); ++i) {
      if (item->items[i].starts_with(prefix)) { index = int(i); break; }
    }
    ASSERT_GE(index, 0) << key << ": " << prefix;
    ASSERT_NO_FATAL_FAILURE(click(key));
    const ui::Widget *option = nullptr;
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &candidate : block->widgets()) {
        if (candidate.type == ui::WidgetType::MenuItem && candidate.menu_index == index) { option = &candidate; }
      }
    }
    ASSERT_NE(option, nullptr); ASSERT_TRUE(option->enabled);
    const auto clipped = option->rect.intersect(option->clip); ASSERT_FALSE(clipped.empty());
    const int x = int(clipped.x + clipped.w * .5f);
    const int y = f.screen.rect().ymax - 1 - int(clipped.y + clipped.h * .5f);
    ASSERT_TRUE(f.drv->click(x, y)); ++clicks; frame();
  }
  void expect_preserved()
  {
    EXPECT_EQ(store().viewer().base_payload(), shown);
    EXPECT_EQ(store().viewer().payload_serial(), payload_serial);
    EXPECT_EQ(store().viewer().camera_serial(), camera_serial);
    EXPECT_EQ(store().viewer().save_workspace_state(), viewer_state);
    EXPECT_EQ(store().viewer().evaluations_started(), 0u);
    EXPECT_TRUE(store().scripts().history().empty());
    if (!python_draft.is_null()) {
      ASSERT_GE(area().tab_count(), 2);
      EXPECT_EQ(area().tab(1).save_workspace_state(), python_draft);
      EXPECT_TRUE(area().tab(1).has_unsaved_changes());
    }
  }
  void show_materials()
  {
    ASSERT_TRUE(area().set_tabs({kEditorMaterials, kEditorPython}, 1));
    f.screen.set_maximized(&area()); frame();
    ASSERT_NO_FATAL_FAILURE(wait_widget("python_source"));
    ASSERT_NO_FATAL_FAILURE(click("python_source")); f.drv->key(wm::Key::A, primary_modifier);
    auto input = ui::Event::text_input("print('keep hidden materials draft')"); input.time = ++clock;
    f.screen.ui()->handle_event(input); frame();
    ASSERT_NO_FATAL_FAILURE(click("python_output_open"));
    python_draft = area().editor().save_workspace_state();
    ASSERT_TRUE(area().editor().has_unsaved_changes());
    area().set_active_tab(0); area().set_sidebar_open(true); area().set_toolbar_open(false); frame();
    area().find_region(EditorArea::kSidebar)->set_size_1x(560); frame();
    ASSERT_NO_FATAL_FAILURE(wait_widget("materials_directory"));
  }
  void admit_two_versions()
  {
    release("prepare_release"); release("train_release");
    for (const auto *id : {"version-one", "version-two"}) {
      ASSERT_EQ(call("materials.prepare", {{"directory", dataset()}, {"job_id", id}}).at("job").at("state"), "prepared");
      ASSERT_TRUE(call("materials.start", {{"job_id", id}}).is_object());
      Json result;
      ASSERT_TRUE(loop.pump_until([&] { result = call("materials.jobs.get", {{"job_id", id}}).at("job");
        return result.at("state") != "running"; }, 30));
      ASSERT_EQ(result.at("state"), "done") << result.dump();
    }
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    { std::ofstream script(dir.path() / "bridge.py", std::ios::binary); script << kMaterialsBridge; ASSERT_TRUE(script.good()); }
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/state";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    options.command = {python, "-u", dir.str() + "/bridge.py", dir.str() + "/control",
        "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)); loop.run_ready(); store().set_bridge(client.get());
    ASSERT_TRUE(call("materials.datasets.synthetic", {{"directory", dataset()}, {"kind", "capacity_fade"},
        {"samples", 24}, {"seed", 7}, {"name", "Controlled UI public synthetic data"}}).at("card").at("ok").get<bool>());
    store().viewer().set_auto_evaluate(false); store().viewer().prefetch_neighbours = false;
    shown = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    store().viewer().open_payload(shown, "Existing synthetic result"); store().viewer().refresh_metadata();
    ASSERT_TRUE(loop.pump_until([&] { return store().viewer().presets_loaded() &&
        !store().viewer().catalog().is_null() && store().viewer().colormaps(); }, 30));
    viewer_state = store().viewer().save_workspace_state(); camera_serial = store().viewer().camera_serial();
    payload_serial = store().viewer().payload_serial();
  }
  void TearDown() override
  {
    release("prepare_release"); release("train_release"); release("validate_release");
    release("job_release"); release("models_release");
    if (shown) { expect_preserved(); }
    store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(MaterialsEditorPython, LateValidationCannotCrossSameClientDetachAndReattachWithoutAFrame)
{
  auto &state = store().materials(); const auto view = state.new_view(); state.sync(view);
  ASSERT_TRUE(loop.pump_until([&] { state.sync(view); return !view->reading(); }, 30));
  release("hold_validate");
  ASSERT_TRUE(state.validate(view, dataset()));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.validate_held"); }, 30));
  ASSERT_TRUE(view->card.is_null());
  const auto original_epoch = store().bridge_epoch();
  store().set_bridge(nullptr); store().set_bridge(client.get()); // Intentionally no UI frame/sync.
  EXPECT_GT(store().bridge_epoch(), original_epoch);
  release("validate_release");
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.validate_sent"); }, 30));
  // Pipe/executor ordering drains the real old reply before checking the original View. No
  // MaterialsState::sync or frame may mask missing reply-time bridge epoch validation here.
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object());
  EXPECT_TRUE(view->card.is_null());
  ASSERT_TRUE(fs::remove(dir.path() / "control.hold_validate"));
  state.sync(view);
  ASSERT_TRUE(loop.pump_until([&] { state.sync(view); return !view->reading(); }, 30));
  ASSERT_TRUE(state.validate(view, dataset()));
  ASSERT_TRUE(loop.pump_until([&] { return view->card.is_object() && !view->reading(); }, 30));
  EXPECT_TRUE(view->card.at("ok").get<bool>());
  EXPECT_EQ(count("validate"), 2); EXPECT_EQ(count("prepare"), 0); EXPECT_EQ(count("start"), 0);
  EXPECT_EQ(count("recover"), 0); EXPECT_EQ(count("activate"), 0);
  state.detach(view); ASSERT_NO_FATAL_FAILURE(expect_preserved());
}

TEST_F(MaterialsEditorPython, StaleStartCallbacksCannotFollowAnotherJobOrDetachedBridge)
{
  release("prepare_release");
  for (const auto *id : {"first-job", "second-job"}) {
    ASSERT_EQ(call("materials.prepare", {{"directory", dataset()}, {"job_id", id}}).at("job").at("state"), "prepared");
  }
  ASSERT_NO_FATAL_FAILURE(show_materials());
  ASSERT_NO_FATAL_FAILURE(click_tab("materials_sections", 1));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_jobs"));
  ASSERT_NO_FATAL_FAILURE(select_dropdown("materials_jobs", "first-job"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_start"));
  const auto first_start = widget("materials_start")->on_click;
  ASSERT_TRUE(bool(first_start));
  ASSERT_NO_FATAL_FAILURE(select_dropdown("materials_jobs", "second-job"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_start"));
  const auto second_start = widget("materials_start")->on_click;
  ASSERT_TRUE(bool(second_start));
  first_start();
  ASSERT_TRUE(call("materials.jobs.get", {{"job_id", "first-job"}}).is_object()); frame();
  EXPECT_EQ(count("start"), 0); EXPECT_EQ(count("train_worker"), 0);
  store().set_bridge(nullptr);
  second_start();
  store().set_bridge(client.get());
  second_start(); // The same Client pointer must not revive a ticket across an unframed detach.
  frame();
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object()); frame();
  EXPECT_EQ(count("start"), 0); EXPECT_EQ(count("train_worker"), 0);
  EXPECT_EQ(count("recover"), 0); EXPECT_EQ(count("activate"), 0);
  ASSERT_NO_FATAL_FAILURE(expect_preserved());
}

TEST_F(MaterialsEditorPython, EnabledActivationRejectsOldSelectionBridgeHiddenAndDetachedOwner)
{
  // Produce real durable/admitted versions with the controlled UI trainer. The second capsule
  // freezes the first active model as its baseline; its descriptor and held-out set stay bound.
  ASSERT_NO_FATAL_FAILURE(admit_two_versions());
  const auto models = call("materials.models.list", Json::object()).at("kinds").at("capacity_fade");
  ASSERT_EQ(models.at("active"), "v2"); ASSERT_EQ(models.at("versions").size(), 2u);
  ASSERT_NO_FATAL_FAILURE(show_materials());
  ASSERT_NO_FATAL_FAILURE(click_tab("materials_sections", 2));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_kind"));
  ASSERT_EQ(widget("materials_kind")->items.size(), 2u);
  const auto capacity = widget("materials_kind")->items.at(1);
  ASSERT_NO_FATAL_FAILURE(select_dropdown("materials_kind", capacity));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_versions"));
  ASSERT_NO_FATAL_FAILURE(select_dropdown("materials_versions", "v1"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_activate"));
  const auto old_selection = widget("materials_activate")->on_click; ASSERT_TRUE(bool(old_selection));
  ASSERT_NO_FATAL_FAILURE(select_dropdown("materials_versions", "v2"));
  old_selection();
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object()); frame();
  EXPECT_EQ(count("activate"), 0);

  ASSERT_NO_FATAL_FAILURE(select_dropdown("materials_versions", "v1"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_activate"));
  const auto old_bridge = widget("materials_activate")->on_click; ASSERT_TRUE(bool(old_bridge));
  store().set_bridge(nullptr); frame(); old_bridge();
  store().set_bridge(client.get()); frame();
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_versions"));
  ASSERT_NO_FATAL_FAILURE(select_dropdown("materials_versions", "v1"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_activate"));
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object()); frame();
  EXPECT_EQ(count("activate"), 0);

  const auto old_unframed = widget("materials_activate")->on_click; ASSERT_TRUE(bool(old_unframed));
  store().set_bridge(nullptr); store().set_bridge(client.get());
  old_unframed(); // No frame/sync may be needed to revoke the original bridge ticket.
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object()); frame();
  EXPECT_EQ(count("activate"), 0);
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_versions"));
  ASSERT_NO_FATAL_FAILURE(select_dropdown("materials_versions", "v1"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_activate"));

  const auto old_owner = widget("materials_activate")->on_click; ASSERT_TRUE(bool(old_owner));
  const auto workspace = area().editor().save_workspace_state();
  ASSERT_TRUE(area().add_tab(kEditorMaterials, true));
  ASSERT_TRUE(area().editor().load_workspace_state(workspace)); frame(); old_owner();
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object()); frame();
  EXPECT_EQ(count("activate"), 0);
  area().set_active_tab(0); frame(); ASSERT_NO_FATAL_FAILURE(wait_widget("materials_activate"));
  const auto old_detached = widget("materials_activate")->on_click; ASSERT_TRUE(bool(old_detached));
  // The lifecycle hook used by region removal/move must revoke already-created controls too.
  area().editor().on_area_removed(); old_detached();
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object()); frame();
  EXPECT_EQ(count("activate"), 0); ASSERT_NO_FATAL_FAILURE(wait_widget("materials_activate"));
  const int before = clicks;
  ASSERT_NO_FATAL_FAILURE(click("materials_activate"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return count("activate") == 1; }, 30));
  EXPECT_EQ(call("materials.models.list", Json::object()).at("kinds").at("capacity_fade").at("active"), "v1");
  EXPECT_EQ(clicks - before, 1); EXPECT_EQ(count("activate"), 1);
  EXPECT_EQ(count("prepare"), 2); EXPECT_EQ(count("start"), 2); EXPECT_EQ(count("train_worker"), 2);
  EXPECT_EQ(count("recover"), 0); ASSERT_NO_FATAL_FAILURE(expect_preserved());
}

TEST_F(MaterialsEditorPython, OldPreparedJobReplyCannotUndoStartAcknowledgementOrFreshCurves)
{
  release("prepare_release");
  ASSERT_EQ(call("materials.prepare", {{"directory", dataset()}, {"job_id", "ordered-job"}}).at("job").at("state"), "prepared");
  auto &state = store().materials(); const auto view = state.new_view(); state.sync(view);
  ASSERT_TRUE(loop.pump_until([&] { state.sync(view); return !view->reading(); }, 30));
  ASSERT_TRUE(state.select_job(view, "ordered-job"));
  ASSERT_TRUE(loop.pump_until([&] { return !view->reading() && view->job.is_object(); }, 30));
  ASSERT_EQ(view->job.at("state"), "prepared");
  release("hold_job"); ASSERT_TRUE(state.refresh(view));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.job_held"); }, 30));
  ASSERT_TRUE(state.start(view));
  ASSERT_TRUE(loop.pump_until([&] { return !view->busy() && view->job.at("state") == "running"; }, 30));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.input_ready"); }, 30));
  release("job_release");
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.job_sent"); }, 30));
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object());
  ASSERT_EQ(view->job.at("state"), "running"); // Old prepared bytes arrived after the start ACK.
  ASSERT_TRUE(fs::remove(dir.path() / "control.hold_job"));
  ASSERT_TRUE(state.refresh(view));
  ASSERT_TRUE(loop.pump_until([&] { state.sync(view); return view->epochs.size() == 2 && !view->reading(); }, 30));
  EXPECT_EQ(view->job.at("state"), "running");
  EXPECT_EQ(view->epochs.back().at("epoch"), 2);
  EXPECT_EQ(count("prepare"), 1); EXPECT_EQ(count("start"), 1); EXPECT_EQ(count("train_worker"), 1);
  release("train_release");
  ASSERT_TRUE(loop.pump_until([&] { state.sync(view); return view->job.at("state") == "done"; }, 30));
  EXPECT_EQ(view->selected_job, "ordered-job"); EXPECT_EQ(count("recover"), 0);
  state.detach(view); ASSERT_NO_FATAL_FAILURE(expect_preserved());
}

TEST_F(MaterialsEditorPython, OldModelListingCannotUndoActivationAcknowledgement)
{
  ASSERT_NO_FATAL_FAILURE(admit_two_versions());
  auto &state = store().materials(); const auto view = state.new_view(); state.sync(view);
  ASSERT_TRUE(loop.pump_until([&] { state.sync(view); return !view->reading(); }, 30));
  ASSERT_EQ(view->models.at("kinds").at("capacity_fade").at("active"), "v2");
  release("hold_models"); ASSERT_TRUE(state.refresh(view));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.models_held"); }, 30));
  ASSERT_TRUE(state.activate(view, "capacity_fade", "v1"));
  ASSERT_TRUE(loop.pump_until([&] { return !view->busy() &&
      view->models.at("kinds").at("capacity_fade").at("active") == "v1"; }, 30));
  release("models_release");
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.models_sent"); }, 30));
  ASSERT_EQ(call("materials.models.list", Json::object()).at("kinds").at("capacity_fade").at("active"), "v1");
  ASSERT_EQ(view->models.at("kinds").at("capacity_fade").at("active"), "v1");
  ASSERT_TRUE(fs::remove(dir.path() / "control.hold_models"));
  ASSERT_TRUE(state.refresh(view));
  ASSERT_TRUE(loop.pump_until([&] { state.sync(view); return !view->reading(); }, 30));
  EXPECT_EQ(view->models.at("kinds").at("capacity_fade").at("active"), "v1");
  EXPECT_EQ(view->models.at("kinds").at("capacity_fade").at("versions").size(), 2u);
  EXPECT_EQ(count("activate"), 1); EXPECT_EQ(count("start"), 2); EXPECT_EQ(count("train_worker"), 2);
  EXPECT_EQ(count("recover"), 0); state.detach(view); ASSERT_NO_FATAL_FAILURE(expect_preserved());
}

struct MaterialsLayout { const char *language; int width, height; float scale; const char *name; };
void PrintTo(const MaterialsLayout &layout, std::ostream *out) { *out << layout.name; }
class MaterialsMouse : public MaterialsEditorPython, public ::testing::WithParamInterface<MaterialsLayout> {};

TEST_P(MaterialsMouse, ThreeClicksValidateFreezeAndStartKeepViewerDraftAndReopenReadOnly)
{
  const auto layout = GetParam(); store().set_language(layout.language);
  f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, layout.width, layout.height, layout.scale);
  ASSERT_NO_FATAL_FAILURE(show_materials());
  ASSERT_NO_FATAL_FAILURE(text("materials_directory", dataset()));
  ASSERT_NO_FATAL_FAILURE(text("materials_job_id", "ui-frozen-job"));
  ASSERT_NO_FATAL_FAILURE(visible("materials_validate"));
  ASSERT_NO_FATAL_FAILURE(visible("materials_prepare"));
  EXPECT_EQ(widget("materials_hidden"), nullptr); // Advanced settings stay collapsed.
  EXPECT_EQ(count("validate"), 0); EXPECT_EQ(count("prepare"), 0); EXPECT_EQ(count("start"), 0);
  RecordProperty("starting_layout", std::string(layout.language) + " " + std::to_string(layout.width) + "x" +
      std::to_string(layout.height) + " scale=" + std::to_string(layout.scale) +
      "; a4 maximized Materials Inputs; sidebar 560 logical; prefilled directory/job ID; advanced closed; hidden Python draft; existing Viewer");
  clicks = 0;
  ASSERT_NO_FATAL_FAILURE(click("materials_validate"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return count("validate") == 1; }, 30));
  // Ordered read barrier after validation; frame consumes the delivered card without mutation.
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object()); frame();
  ASSERT_NO_FATAL_FAILURE(visible("materials_prepare"));
  ASSERT_NO_FATAL_FAILURE(click("materials_prepare"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return fs::exists(dir.path() / "control.prepared"); }, 30));
  EXPECT_EQ(count("prepare"), 1); EXPECT_EQ(count("start"), 0); EXPECT_EQ(count("train_worker"), 0);
  EXPECT_TRUE(widget("materials_start") == nullptr || !widget("materials_start")->enabled);
  ASSERT_NE(widget("materials_prepare"), nullptr); EXPECT_FALSE(widget("materials_prepare")->enabled);
  const auto prepared = call("materials.jobs.get", {{"job_id", "ui-frozen-job"}}).at("job");
  ASSERT_EQ(prepared.at("state"), "prepared"); EXPECT_EQ(prepared.at("epoch"), 0);
  ASSERT_EQ(prepared.at("input_sha256").get<std::string>().size(), 64u);
  ASSERT_GT(fs::remove_all(dir.path() / "live-data"), 0u);
  release("prepare_release"); ASSERT_NO_FATAL_FAILURE(wait_widget("materials_start"));
  EXPECT_EQ(area().editor().save_workspace_state().at("section"), 1);
  const auto workspace = area().editor().save_workspace_state();
  const auto stale_start = widget("materials_start")->on_click;
  ASSERT_TRUE(bool(stale_start));
  ASSERT_EQ(clicks, 2); EXPECT_EQ(count("start"), 0);

  // A fresh actual editor instance restores only drafts/preferences, never its old selected job.
  const auto reads = count("jobs"); ASSERT_TRUE(area().add_tab(kEditorMaterials, true));
  ASSERT_TRUE(area().editor().load_workspace_state(workspace)); frame();
  stale_start(); // An old hidden tab's explicit action must not acquire authority in this tab.
  ASSERT_TRUE(loop.pump_until([&] { frame(); return count("jobs") > reads; }, 30));
  ASSERT_TRUE(call("materials.models.list", Json::object()).is_object()); frame();
  EXPECT_EQ(area().editor().save_workspace_state(), workspace);
  EXPECT_EQ(widget("materials_start"), nullptr);
  EXPECT_EQ(count("validate"), 1); EXPECT_EQ(count("prepare"), 1); ASSERT_EQ(count("start"), 0);
  EXPECT_EQ(count("train_worker"), 0); EXPECT_EQ(count("recover"), 0);
  ASSERT_NO_FATAL_FAILURE(expect_preserved());
  area().set_active_tab(0); frame(); ASSERT_NO_FATAL_FAILURE(wait_widget("materials_start"));

  ASSERT_NO_FATAL_FAILURE(click("materials_start"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return fs::exists(dir.path() / "control.input_ready"); }, 30));
  EXPECT_EQ(count("start"), 1); EXPECT_EQ(count("train_worker"), 1);
  EXPECT_FALSE(fs::exists(dir.path() / "live-data"));
  std::ifstream manifest_file(dir.path() / "control.input.json"); Json frozen; manifest_file >> frozen;
  EXPECT_EQ(frozen.at("sha256"), prepared.at("input_sha256"));
  EXPECT_EQ(frozen.at("kind"), "capacity_fade");
  const auto running = call("materials.jobs.get", {{"job_id", "ui-frozen-job"}}).at("job");
  frame(); ASSERT_NE(widget("materials_start"), nullptr); EXPECT_FALSE(widget("materials_start")->enabled);
  EXPECT_EQ(running.at("state"), "running");
  RecordProperty("actual_clicks", clicks); EXPECT_EQ(clicks, 3);
  release("train_release");
  Json done;
  ASSERT_TRUE(loop.pump_until([&] { frame(); done = call("materials.jobs.get", {{"job_id", "ui-frozen-job"}}).at("job");
    return done.at("state") != "running"; }, 30));
  ASSERT_EQ(done.at("state"), "done") << done.dump();
  EXPECT_EQ(done.at("input_sha256"), prepared.at("input_sha256"));
  EXPECT_EQ(done.at("comparison").at("test_samples"), frozen.at("split").at("test").size());
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_plot_kind"));
  const int flow_clicks = clicks;
  ASSERT_NO_FATAL_FAILURE(click_tab("materials_plot_kind", 1));
  ASSERT_NO_FATAL_FAILURE(wait_widget("materials_sample"));
  ASSERT_NO_FATAL_FAILURE(visible("materials_sample"));
  EXPECT_EQ(area().editor().save_workspace_state().at("plot"), 1);
  RecordProperty("evaluation_clicks_after_training", clicks - flow_clicks);
  EXPECT_EQ(clicks - flow_clicks, 1);
  EXPECT_EQ(count("prepare"), 1); EXPECT_EQ(count("start"), 1); EXPECT_EQ(count("train_worker"), 1);
  EXPECT_EQ(count("recover"), 0); EXPECT_EQ(count("train"), 0); EXPECT_EQ(count("activate"), 0);
  ASSERT_NO_FATAL_FAILURE(expect_preserved());
}

INSTANTIATE_TEST_SUITE_P(LanguagesWidthsAndScales, MaterialsMouse, ::testing::Values(
    MaterialsLayout{"en", 1440, 1100, 1, "EnglishWide1x"},
    MaterialsLayout{"zh_CN", 1000, 1100, 1, "ChineseNarrow1x"},
    MaterialsLayout{"en", 2160, 1650, 1.5f, "EnglishWide1p5x"},
    MaterialsLayout{"zh_CN", 2000, 2200, 2, "ChineseNarrow2x"}),
    [](const ::testing::TestParamInfo<MaterialsLayout> &info) { return info.param.name; });
}  // namespace
}  // namespace stk::app
