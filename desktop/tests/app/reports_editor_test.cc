/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_reports.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/io/payload.hh"
#include "stk/io/png.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;
const std::string report_id = "a1111111-1111-4111-8111-111111111111";
#ifdef __APPLE__
constexpr auto primary_modifier = wm::ModOS;
#else
constexpr auto primary_modifier = wm::ModCtrl;
#endif

// Real project/snapshot/report implementations and strict protocol validation. Only bytes or
// delivery timing are fault-injected; held replies are released after the source operation has
// left the ProjectSessions lock, permitting a genuine project/bridge switch before delivery.
constexpr const char *kReportBridge = R"PY(
import base64
from pathlib import Path
import sys
import threading
import time
from suan.project.reports import Reports
from suan.project import reports as report_storage
from suan.project.store import RevisionConflict
from suan.project.reports import ReportNotFound
from suan.project.snapshots import Snapshots
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main
control = Path(sys.argv.pop(1))
def mode():
    return control.read_text(encoding='utf-8') if control.exists() else ''
def count(name):
    with control.with_suffix('.calls').open('a', encoding='utf-8') as stream:
        stream.write(name + '\n')
asset = Reports.asset
def controlled_asset(self, *args, **kwargs):
    result = asset(self, *args, **kwargs)
    count('asset')
    if mode() == 'bad_bytes':
        result['data'] = base64.b64encode(b'x' * result['size']).decode('ascii')
    return result
Reports.asset = controlled_asset
export = Reports.export_file
def controlled_export(self, *args, **kwargs):
    result = export(self, *args, **kwargs)
    count('export')
    if mode() == 'bad_export_receipt':
        result['report_id'] = '00000000-0000-4000-8000-000000000000'
    return result
Reports.export_file = controlled_export
create_report = Reports.create
def controlled_create(self, *args, **kwargs):
    if mode() == "source_conflict":
        raise RevisionConflict("Report sources changed; explicitly review the selected sources again")
    result = create_report(self, *args, **kwargs)
    count('create')
    if mode() == 'bad_create_receipt':
        result['record_id'] = '00000000-0000-4000-8000-000000000000'
    return result
Reports.create = controlled_create
get_report = Reports.get
def controlled_get(self, report_id):
    if mode() == 'hide_created' and report_id != 'a1111111-1111-4111-8111-111111111111':
        raise ReportNotFound('Report not found')
    result = get_report(self, report_id)
    if mode() == 'changed_found_source' and report_id != 'a1111111-1111-4111-8111-111111111111':
        source = result['report']['manifest']['sources'][0]
        source['context']['title'] = 'Another frozen context title'
        source['context_sha256'] = report_storage._hash(source['context'])
        result['report']['source_sha256'] = report_storage._hash(result['report']['manifest'])
    return result
Reports.get = controlled_get
review_sources = Reports.review_sources
def controlled_review(self, *args, **kwargs):
    result = review_sources(self, *args, **kwargs)
    count('source_review')
    if mode() == 'bad_source_digest':
        result['sources_sha256'] = '0' * 64
    return result
Reports.review_sources = controlled_review
summaries = Snapshots.list_summaries
def controlled_summaries(self, *args, **kwargs):
    result = summaries(self, *args, **kwargs)
    count('summaries')
    return result
Snapshots.list_summaries = controlled_summaries
send = Bridge.send
def controlled_send(self, message, method=None):
    if method == 'project.contexts.list' and 'result' in message: count('source_list')
    hold = {'project.reports.asset': 'hold', 'project.snapshots.list_summaries': 'hold_summaries',
            'project.reports.create': 'hold_create', 'project.reports.review_sources': 'hold_source_review'}
    if method in hold and 'result' in message and mode() == hold[method]:
        control.with_suffix('.held').write_text('ready', encoding='utf-8')
        def deliver():
            deadline = time.monotonic() + 30
            while not control.with_suffix('.release').exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            send(self, message, method)
            control.with_suffix('.sent').write_text('sent', encoding='utf-8')
        threading.Thread(target=deliver, daemon=True).start()
        return
    return send(self, message, method)
Bridge.send = controlled_send
main()
)PY";

std::string read_bytes(const fs::path &path)
{
  std::ifstream input(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

class ReportsEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"reports-editor"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 1000};
  std::unique_ptr<bridge::Client> client;
  std::unique_ptr<ProjectReports> reports;
  std::shared_ptr<const io::Payload> shown;
  std::string python, markdown, source_sha, project_id;
  std::vector<uint8_t> png;
  Json manifest, viewer_state;
  uint64_t camera_serial = 0, payload_serial = 0;
  int clicks = 0;
  double clock = 1000;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  EditorArea &area() { return f.area("a4"); }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  void frame() { f.screen.run_deferred(); f.drv->frame(); }
  void mode(const std::string &value)
  {
    std::ofstream output(dir.path() / "mode", std::ios::binary); output << value;
    ASSERT_TRUE(output.good());
  }
  void release()
  {
    std::ofstream output(dir.path() / "mode.release", std::ios::binary); output << "release";
  }
  int count(const std::string &operation) const
  {
    std::ifstream input(dir.path() / "mode.calls");
    std::string line; int result = 0;
    while (std::getline(input, line)) { result += line == operation; }
    return result;
  }
  bool start_client(const std::string &suffix)
  {
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge-" + suffix;
    options.cache_dir = dir.str() + "/cache-" + suffix;
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime-" + suffix;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    options.command = {python, "-u", dir.str() + "/bridge.py", dir.str() + "/mode",
        "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    client = bridge::Client::create(options);
    if (!client->start() || !client->wait_ready(60)) { return false; }
    loop.run_ready(); store().set_bridge(client.get()); project().sync();
    return loop.pump_until([&] { return project().ready(); }, 30);
  }
  Json call_on(bridge::Client &sender, const std::string &method, Json params)
  {
    std::optional<bridge::Result<Json>> response;
    sender.call(method, std::move(params)).then([&](auto result) { response = std::move(result); });
    if (!loop.pump_until([&] { return response.has_value(); }, 30) || !response->ok()) {
      ADD_FAILURE() << method << ": " << (response ? response->error().describe() : "timed out");
      return nullptr;
    }
    return response->value();
  }
  Json call(const std::string &method, Json params) { return call_on(*client, method, std::move(params)); }
  void settle_project()
  {
    ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy() && !project().recent_loading(); }, 30))
        << project().error();
  }
  void settle()
  {
    ASSERT_TRUE(loop.pump_until([&] { reports->sync(); return !reports->busy() && !project().busy(); }, 30))
        << reports->error();
  }
  void load_report()
  {
    ASSERT_TRUE(reports->load(report_id, source_sha)); ASSERT_NO_FATAL_FAILURE(settle());
    ASSERT_TRUE(reports->selected().is_object()) << reports->error();
    EXPECT_FALSE(reports->asset_loaded());
  }
  void held_read()
  {
    ASSERT_NO_FATAL_FAILURE(load_report());
    ASSERT_NO_FATAL_FAILURE(mode("hold"));
    ASSERT_TRUE(reports->read_asset());
    ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(dir.path() / "mode.held"); }, 15));
  }
  void drain_held(bridge::Client &sender)
  {
    release();
    ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(dir.path() / "mode.sent"); }, 15));
    // The marker is written after send(): a later response is an ordered barrier for the old
    // reply in this pipe and its queued executor callback, with no timing-dependent sleep.
    ASSERT_TRUE(call_on(sender, "project.list", Json::object()).is_object());
    loop.run_ready(); reports->sync();
  }
  void expect_viewer()
  {
    EXPECT_EQ(store().viewer().base_payload(), shown);
    EXPECT_EQ(store().viewer().payload_serial(), payload_serial);
    EXPECT_EQ(store().viewer().camera_serial(), camera_serial);
    EXPECT_EQ(store().viewer().save_workspace_state(), viewer_state);
    EXPECT_EQ(store().viewer().evaluations_started(), 0u);
    EXPECT_TRUE(store().scripts().history().empty());
  }
  void SetUp() override
  {
    python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    { std::ofstream script(dir.path() / "bridge.py", std::ios::binary); script << kReportBridge; ASSERT_TRUE(script.good()); }
    ASSERT_TRUE(start_client("first"));
    ASSERT_TRUE(project().create(dir.str() + "/project", "Frozen reports"));
    ASSERT_NO_FATAL_FAILURE(settle_project());
    project_id = project().project()->id;
    const auto handle = project().project()->handle;
    markdown = "# Frozen report\n\n" + std::string(70000, 'q') + "\nend of complete source\n";
    ASSERT_TRUE(wmtest::write_text(dir.str() + "/project/report.md", markdown));
    io::Image image(2, 1); image.pixels = {255, 0, 0, 255, 0, 255, 0, 255}; png = io::encode_png(image);
    {
      std::ofstream output(dir.path() / "project/plot.png", std::ios::binary);
      output.write(reinterpret_cast<const char *>(png.data()), std::streamsize(png.size())); ASSERT_TRUE(output.good());
    }
    ASSERT_TRUE(wmtest::write_text(dir.str() + "/project/paper.pdf", "%PDF-1.4\n%%EOF\n"));
    const auto indexed = call("project.files.index", {{"handle", handle}, {"expected_revision", 0},
        {"paths", Json::array({dir.str() + "/project/report.md", dir.str() + "/project/plot.png", dir.str() + "/project/paper.pdf"})}});
    ASSERT_TRUE(indexed.is_object());
    const auto ids = indexed.at("record_ids");
    const auto captured = call("project.snapshots.capture", {{"handle", handle}, {"record_ids", ids}, {"expected_revision", 1}});
    ASSERT_TRUE(captured.is_object());
    const auto saved = call("project.reports.create", {{"handle", handle}, {"name", "Frozen report"},
        {"snapshot_id", captured.at("snapshot").at("id")}, {"entry_record_id", ids.at(0)},
        {"assets", Json::array({{{"record_id", ids.at(0)}, {"path", "report.md"}},
                               {{"record_id", ids.at(1)}, {"path", "plot.png"}},
                               {{"record_id", ids.at(2)}, {"path", "paper.pdf"}}})},
        {"report_id", report_id}, {"expected_revision", 2}});
    ASSERT_TRUE(saved.is_object());
    project().refresh(); ASSERT_NO_FATAL_FAILURE(settle_project());
    ASSERT_EQ(project().project()->revision, 3);
    const auto record = call("project.reports.get", {{"handle", handle}, {"report_id", report_id}});
    ASSERT_TRUE(record.is_object()); manifest = record.at("report").at("manifest");
    source_sha = record.at("report").at("source_sha256").get<std::string>();
    reports = std::make_unique<ProjectReports>(store()); ASSERT_TRUE(reports->supported());
    store().viewer().set_auto_evaluate(false); store().viewer().prefetch_neighbours = false;
    shown = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    store().viewer().open_payload(shown, "Existing synthetic result");
    store().viewer().refresh_metadata();
    ASSERT_TRUE(loop.pump_until([&] {
      return store().viewer().presets_loaded() && !store().viewer().catalog().is_null() && store().viewer().colormaps();
    }, 30)) << store().viewer().metadata_error();
    viewer_state = store().viewer().save_workspace_state();
    camera_serial = store().viewer().camera_serial(); payload_serial = store().viewer().payload_serial();
  }
  void TearDown() override
  {
    release();
    if (shown) { expect_viewer(); }
    reports.reset(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
  void click(const std::string &key)
  {
    frame(); const auto *item = widget(key); ASSERT_NE(item, nullptr) << key;
    ASSERT_TRUE(item->enabled) << key;
    ASSERT_FALSE(item->rect.intersect(item->clip).empty()) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_GE(x, 0); ASSERT_LT(x, 1440); ASSERT_GE(y, 0); ASSERT_LT(y, 1000);
    ASSERT_TRUE(f.drv->click(x, y)) << key; ++clicks; frame();
  }
  void click_row(const std::string &key, int index)
  {
    frame(); const auto *item = widget(key); ASSERT_NE(item, nullptr) << key;
    ASSERT_TRUE(item->enabled); ASSERT_NE(item->list, nullptr);
    const auto &style = f.screen.ui()->style();
    const int x = int(item->rect.x + item->rect.w * 0.5f);
    const int y = f.screen.rect().ymax - 1 - int(item->rect.y + style.pixel + style.unit * (float(index) + 0.5f));
    ASSERT_GE(x, 0); ASSERT_LT(x, 1440); ASSERT_GE(y, 0); ASSERT_LT(y, 1000);
    ASSERT_TRUE(f.drv->click(x, y)); ++clicks; frame();
  }
  void text(const std::string &key, const std::string &value)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
    f.drv->key(wm::Key::A, primary_modifier);
    auto input = ui::Event::text_input(value); input.time = ++clock;
    f.screen.ui()->handle_event(input); frame();
    f.drv->key(wm::Key::Enter); frame();
  }
  void wait_widget(const std::string &key)
  {
    ASSERT_TRUE(loop.pump_until([&] { frame(); const auto *item = widget(key); return item && item->enabled; }, 30)) << key;
  }
  void show_reports()
  {
    // The default a4 has five tabs. Establish the promised two-tab layout explicitly,
    // and create a real dirty Python buffer rather than mistaking tab(1) (Logs) for it.
    ASSERT_TRUE(area().set_tabs({kEditorReports, kEditorPython}, 1));
    f.screen.set_maximized(&area()); frame();
    ASSERT_NO_FATAL_FAILURE(wait_widget("python_source"));
    const auto initial = area().editor().save_workspace_state();
    const auto baseline = initial.at("baseline");
    ASSERT_EQ(initial.at("source"), baseline);
    ASSERT_NO_FATAL_FAILURE(click("python_source"));
    f.drv->key(wm::Key::A, primary_modifier);
    const std::string draft = "print('keep this unsaved draft')";
    auto input = ui::Event::text_input(draft); input.time = ++clock;
    f.screen.ui()->handle_event(input); frame();
    // Clicking a presentation preference commits the text field without save/run/submit.
    ASSERT_NO_FATAL_FAILURE(click("python_output_open"));
    ASSERT_EQ(area().editor().type().id, kEditorPython);
    ASSERT_TRUE(area().editor().has_unsaved_changes());
    ASSERT_EQ(area().editor().save_workspace_state().at("source"), draft);
    ASSERT_EQ(area().editor().save_workspace_state().at("baseline"), baseline);
    ASSERT_TRUE(store().scripts().history().empty());
    area().set_active_tab(0); area().set_sidebar_open(false); area().set_toolbar_open(false);
    frame();
    ASSERT_NO_FATAL_FAILURE(wait_widget("reports_list"));
    clicks = 0; // The recorded flow starts on Reports with the established hidden draft.
  }
  void prepare_create(const std::string &title = "Native new report")
  {
    ASSERT_NO_FATAL_FAILURE(show_reports());
    ASSERT_NO_FATAL_FAILURE(click("reports_create_panel"));
    EXPECT_EQ(count("summaries"), 0);
    ASSERT_NO_FATAL_FAILURE(click("reports_create_snapshots"));
    ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_snapshot_list"));
    ASSERT_NO_FATAL_FAILURE(click_row("reports_create_snapshot_list", 0));
    ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_title"));
    ASSERT_NO_FATAL_FAILURE(text("reports_create_title", title));
    ASSERT_NO_FATAL_FAILURE(click_row("reports_create_files", 0));
    ASSERT_NO_FATAL_FAILURE(click("reports_create_include"));
    ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_entry"));
    ASSERT_NO_FATAL_FAILURE(click("reports_create_entry"));
    ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
    ASSERT_TRUE(area().editor().has_unsaved_changes());
  }

  Json context_source(int number = 0)
  {
    const std::string id = "c3333333-3333-4333-8333-" + std::string(12 - std::to_string(number).size(), '0') + std::to_string(number);
    return call("project.contexts.capture", {{"handle", project().project()->handle}, {"context_id", id},
        {"table_id", "d4444444-4444-4444-8444-444444444444"},
        {"record_ids", Json::array({"e5555555-5555-4555-8555-555555555555"})},
        {"field_ids", Json::array({"f6666666-6666-4666-8666-666666666666"})},
        {"expected_revision", project().project()->revision}, {"title", "Explicit missing-selection context"}});
  }
  void source_scroll_to(const std::string &key)
  {
    frame(); const auto main = area().find_region(EditorArea::kMain)->ui_rect();
    const auto visible = [&](const ui::Widget *item) {
      if (!item) { return false; }
      const auto clipped = item->rect.intersect(item->clip).intersect(ui::Rect{0, 0, 1440, 1000});
      return !clipped.empty() && clipped.h >= item->rect.h - 1 && clipped.w >= item->rect.w - 1;
    };
    for (int step = 0; step < 80 && !visible(widget(key)); ++step) {
      const auto *item = widget(key); ASSERT_NE(item, nullptr) << key;
      f.screen.ui()->handle_event(ui::Event::wheel({main.x1() - 2, main.cy()},
          item->rect.cy() > main.cy() ? -1.0f : 1.0f, ++clock)); frame();
    }
    ASSERT_TRUE(visible(widget(key))) << key;
  }
  void source_click(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(wait_widget(key));
    ASSERT_NO_FATAL_FAILURE(source_scroll_to(key));
    ASSERT_NO_FATAL_FAILURE(click(key));
  }
  void add_first_source()
  {
    ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_panel"));
    ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_load"));
    ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_source_candidates"));
    ASSERT_NO_FATAL_FAILURE(source_scroll_to("reports_create_source_candidates"));
    ASSERT_NO_FATAL_FAILURE(click_row("reports_create_source_candidates", 0));
    ASSERT_NO_FATAL_FAILURE(source_click("reports_create_source_add"));
    ASSERT_NE(widget("reports_create_submit"), nullptr); ASSERT_FALSE(widget("reports_create_submit")->enabled);
  }
};

TEST_F(ReportsEditorPython, FrozenBytesSurviveLiveRemovalAndZipRequiresAnExplicitAction)
{
  const auto history = call("project.history", {{"handle", project().project()->handle}});
  ASSERT_TRUE(reports->load_page()); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_EQ(reports->page().at("reports").size(), 1u); EXPECT_EQ(count("asset"), 0);
  ASSERT_NO_FATAL_FAILURE(load_report());
  fs::remove(dir.path() / "project/report.md"); fs::remove(dir.path() / "project/plot.png"); fs::remove(dir.path() / "project/paper.pdf");
  ASSERT_TRUE(reports->read_asset()); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->asset_loaded()) << reports->error();
  EXPECT_EQ(std::string(reports->asset_bytes().begin(), reports->asset_bytes().end()), markdown);
  EXPECT_EQ(reports->asset_mime(), "text/markdown; charset=utf-8");
  ASSERT_TRUE(reports->select_asset("plot.png")); EXPECT_FALSE(reports->asset_loaded());
  ASSERT_TRUE(reports->read_asset()); ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_EQ(reports->asset_bytes(), png);
  const auto destination = dir.path() / "report.zip"; EXPECT_FALSE(fs::exists(destination));
  ASSERT_TRUE(reports->export_file(core::path_to_utf8(destination))); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->export_receipt().is_object()) << reports->error();
  const auto bytes = read_bytes(destination);
  ASSERT_GE(bytes.size(), 4u); EXPECT_EQ(bytes.substr(0, 4), std::string("PK\3\4", 4));
  EXPECT_EQ(reports->export_receipt().at("sha256"), core::Sha256::hex(bytes));
  EXPECT_EQ(reports->export_receipt().at("size"), bytes.size());
  EXPECT_EQ(count("export"), 1);
  EXPECT_EQ(call("project.history", {{"handle", project().project()->handle}}), history);
}

TEST_F(ReportsEditorPython, SameLengthCorruptedBytesAreRejectedBeforeDisplay)
{
  ASSERT_NO_FATAL_FAILURE(load_report());
  ASSERT_NO_FATAL_FAILURE(mode("bad_bytes"));
  ASSERT_TRUE(reports->read_asset()); ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_FALSE(reports->asset_loaded()); EXPECT_TRUE(reports->asset_bytes().empty());
  EXPECT_NE(reports->error().find("checksum"), std::string::npos);
  EXPECT_EQ(count("asset"), 1);
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_TRUE(reports->read_asset()); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->asset_loaded()); EXPECT_EQ(reports->asset_bytes().size(), markdown.size());
}

TEST_F(ReportsEditorPython, ClearInvalidatesARealHeldReply)
{
  ASSERT_NO_FATAL_FAILURE(held_read());
  const auto epoch = reports->epoch(); reports->clear();
  ASSERT_GT(reports->epoch(), epoch); EXPECT_FALSE(reports->busy());
  ASSERT_NO_FATAL_FAILURE(drain_held(*client));
  EXPECT_TRUE(reports->selected().is_null()); EXPECT_TRUE(reports->page().is_null());
  EXPECT_FALSE(reports->asset_loaded()); EXPECT_TRUE(reports->asset_bytes().empty());
  EXPECT_TRUE(reports->error().empty()); EXPECT_EQ(count("asset"), 1);
}

TEST_F(ReportsEditorPython, ProjectSwitchRejectsAReplyFromThePreviousOpenedHandle)
{
  ASSERT_NO_FATAL_FAILURE(held_read());
  const auto old_handle = reports->handle();
  ASSERT_TRUE(project().create(dir.str() + "/other-project", "Other project"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  ASSERT_NE(reports->project_id(), project_id); ASSERT_NE(reports->handle(), old_handle);
  ASSERT_NO_FATAL_FAILURE(drain_held(*client));
  EXPECT_TRUE(reports->selected().is_null()); EXPECT_FALSE(reports->asset_loaded());
  EXPECT_TRUE(reports->asset_bytes().empty()); EXPECT_TRUE(reports->error().empty());
}

TEST_F(ReportsEditorPython, NewBridgeSessionCannotAdoptThePreviousSessionsHeldBytes)
{
  ASSERT_NO_FATAL_FAILURE(held_read());
  const auto old_handle = reports->handle();
  auto old = std::move(client);
  project().attach(nullptr); store().set_bridge(nullptr); reports->sync();
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_TRUE(start_client("second"));
  // ProjectState reconnects its retained persistent UUID on attaching a new ready bridge.
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  ASSERT_NE(reports->handle(), old_handle); EXPECT_EQ(reports->project_id(), project_id);
  ASSERT_NO_FATAL_FAILURE(drain_held(*old));
  EXPECT_FALSE(reports->asset_loaded()); EXPECT_TRUE(reports->selected().is_null());
  ASSERT_NO_FATAL_FAILURE(load_report()); EXPECT_FALSE(reports->asset_loaded());
  old->close(); EXPECT_EQ(old->stats().schema_violations, 0u);
}

TEST_F(ReportsEditorPython, UncertainExportReceiptIsNotAutomaticallyReplayed)
{
  ASSERT_NO_FATAL_FAILURE(load_report());
  ASSERT_NO_FATAL_FAILURE(mode("bad_export_receipt"));
  const auto destination = dir.path() / "uncertain.zip";
  ASSERT_TRUE(reports->export_file(core::path_to_utf8(destination))); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(fs::exists(destination)); EXPECT_TRUE(reports->export_receipt().is_null());
  EXPECT_FALSE(reports->error().empty()); EXPECT_EQ(reports->notice(), "reports.export_check_destination");
  ASSERT_NO_FATAL_FAILURE(mode("")); reports->clear();
  ASSERT_NO_FATAL_FAILURE(load_report());
  EXPECT_EQ(count("export"), 1); EXPECT_FALSE(reports->exporting());
}

TEST_F(ReportsEditorPython, FourMouseClicksReadAndExportWithoutChangingViewerOrHiddenDraft)
{
  ASSERT_NO_FATAL_FAILURE(show_reports());
  auto *draft = &area().tab(1); const auto draft_state = draft->save_workspace_state();
  RecordProperty("starting_layout", "1440x1000 scale=1; a4 maximized Reports; hidden Python draft; existing Viewer payload");
  EXPECT_EQ(count("asset"), 0); EXPECT_EQ(count("export"), 0);
  ASSERT_NO_FATAL_FAILURE(click_row("reports_list", 0));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_read_asset"));
  EXPECT_EQ(count("asset"), 0); EXPECT_EQ(area().editor().save_workspace_state().at("report_id"), report_id);
  ASSERT_NO_FATAL_FAILURE(click("reports_read_asset"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_text_page"));
  const auto destination = dir.path() / "mouse-report.zip";
  ASSERT_NO_FATAL_FAILURE(text("reports_destination", core::path_to_utf8(destination)));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_export"));
  ASSERT_NO_FATAL_FAILURE(click("reports_export"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return fs::is_regular_file(destination) && !area().editor().has_unsaved_changes(); }, 30));
  EXPECT_EQ(clicks, 4); RecordProperty("actual_mouse_clicks", clicks);
  EXPECT_EQ(count("asset"), 1); EXPECT_EQ(count("export"), 1);
  EXPECT_EQ(draft->save_workspace_state(), draft_state); EXPECT_TRUE(draft->has_unsaved_changes());
  expect_viewer();
}

TEST_F(ReportsEditorPython, WorkspaceRestoresOnlyMetadataAndReadingPreferences)
{
  ASSERT_NO_FATAL_FAILURE(show_reports());
  ASSERT_NO_FATAL_FAILURE(click_row("reports_list", 0));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_read_asset"));
  ASSERT_NO_FATAL_FAILURE(click("reports_read_asset"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_text_page"));
  ASSERT_NO_FATAL_FAILURE(click("reports_text_next"));
  const auto state = area().editor().save_workspace_state();
  ASSERT_EQ(state.size(), 6u); EXPECT_EQ(state.at("text_page"), 1);
  EXPECT_EQ(state.at("project_id"), project_id); EXPECT_EQ(state.at("source_sha256"), source_sha);
  for (const auto *key : {"handle", "session_id", "bytes", "data", "destination", "url", "manifest"}) {
    EXPECT_FALSE(state.contains(key)) << key;
  }
  const auto draft = area().tab(1).save_workspace_state();
  ASSERT_TRUE(area().set_tab_type(0, kEditorPython)); ASSERT_TRUE(area().set_tab_type(0, kEditorReports));
  ASSERT_TRUE(area().editor().load_workspace_state(state));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_read_asset"));
  EXPECT_EQ(count("asset"), 1); EXPECT_EQ(widget("reports_text_page"), nullptr);
  EXPECT_EQ(area().editor().save_workspace_state(), state); EXPECT_EQ(area().tab(1).save_workspace_state(), draft);
  ASSERT_NO_FATAL_FAILURE(click("reports_read_asset"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_text_page"));
  EXPECT_EQ(count("asset"), 2); EXPECT_EQ(area().editor().save_workspace_state().at("text_page"), 1);
}

TEST_F(ReportsEditorPython, RestoredWrongSourceVersionDoesNotReadAssets)
{
  ASSERT_NO_FATAL_FAILURE(show_reports());
  ASSERT_TRUE(area().editor().load_workspace_state({{"version", 1}, {"project_id", project_id},
      {"report_id", report_id}, {"source_sha256", std::string(64, '0')}, {"asset_path", "report.md"}, {"text_page", 0}}));
  ASSERT_TRUE(loop.pump_until([&] {
    frame();
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find("Saved report version changed") != std::string::npos) { return true; } }
    }
    return false;
  }, 30));
  EXPECT_EQ(count("asset"), 0); EXPECT_EQ(widget("reports_read_asset"), nullptr);
}

TEST_F(ReportsEditorPython, SelectedPngUsesItsFrozenBytesAndTheReportsImageWidget)
{
  ASSERT_NO_FATAL_FAILURE(show_reports());
  ASSERT_NO_FATAL_FAILURE(click_row("reports_list", 0));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_read_asset"));
  const auto previous_read = widget("reports_read_asset")->on_click;
  ASSERT_NO_FATAL_FAILURE(click_row("reports_assets", 1));
  EXPECT_EQ(area().editor().save_workspace_state().at("asset_path"), "plot.png");
  previous_read(); frame(); ASSERT_NO_FATAL_FAILURE(wait_widget("reports_read_asset"));
  EXPECT_EQ(count("asset"), 0);
  fs::remove(dir.path() / "project/plot.png");
  ASSERT_NO_FATAL_FAILURE(click("reports_read_asset"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_image"));
  EXPECT_EQ(count("asset"), 1); EXPECT_EQ(widget("reports_text_page"), nullptr);
  expect_viewer();
}

TEST_F(ReportsEditorPython, EightMouseClicksCreateFrozenReportWithoutReadingAssetsOrChangingHiddenDraft)
{
  const auto history = call("project.history", {{"handle", project().project()->handle}});
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  auto *draft = &area().tab(1); const auto draft_state = draft->save_workspace_state();
  const auto create_count = count("create");
  RecordProperty("starting_layout", "1440x1000 scale=1; maximized Reports; hidden Python draft; existing Viewer payload");
  ASSERT_NO_FATAL_FAILURE(click("reports_create_submit"));
  ASSERT_TRUE(loop.pump_until([&] {
    frame();
    return project().project()->revision == 4 && !project().busy() &&
        !area().editor().has_unsaved_changes() && widget("reports_read_asset");
  }, 30));
  EXPECT_EQ(clicks, 8); RecordProperty("actual_mouse_clicks", clicks);
  EXPECT_EQ(count("create"), create_count + 1); EXPECT_EQ(count("summaries"), 1);
  EXPECT_EQ(count("asset"), 0); EXPECT_EQ(count("export"), 0);
  const auto state = area().editor().save_workspace_state();
  ASSERT_EQ(state.at("version"), 1); EXPECT_FALSE(state.contains("create_draft"));
  const auto id = state.at("report_id").get<std::string>();
  ASSERT_FALSE(id.empty()); EXPECT_NE(id, report_id);
  const auto result = call("project.reports.get", {{"handle", project().project()->handle}, {"report_id", id}});
  ASSERT_TRUE(result.is_object()); const auto &report = result.at("report");
  EXPECT_EQ(report.at("name"), "Native new report");
  EXPECT_EQ(report.at("manifest").at("snapshot_id"), manifest.at("snapshot_id"));
  EXPECT_EQ(report.at("manifest").at("entry_path"), "report.md");
  EXPECT_EQ(report.at("manifest").at("assets").size(), 1u);
  EXPECT_EQ(report.at("manifest").at("source_revision"), 3);
  EXPECT_EQ(report.at("manifest").at("sources"), Json::array());
  EXPECT_EQ(report.at("source_sha256"), state.at("source_sha256"));
  EXPECT_EQ(call("project.history", {{"handle", project().project()->handle}}).at("history").size(),
            history.at("history").size() + 1);
  EXPECT_EQ(draft->save_workspace_state(), draft_state); EXPECT_TRUE(draft->has_unsaved_changes());
  expect_viewer();
}

TEST_F(ReportsEditorPython, CreationDraftRestoresWithoutRequestsAndNeedsExplicitSnapshotReview)
{
  ASSERT_NO_FATAL_FAILURE(prepare_create("Keep creation draft"));
  const auto state = area().editor().save_workspace_state();
  ASSERT_EQ(state.at("version"), 2); ASSERT_EQ(state.size(), 7u);
  const auto &draft = state.at("create_draft");
  ASSERT_EQ(draft.size(), 9u); EXPECT_EQ(draft.at("version"), 2); EXPECT_TRUE(draft.at("sources").empty()); EXPECT_EQ(draft.at("name"), "Keep creation draft");
  EXPECT_EQ(draft.at("pending"), nullptr); EXPECT_EQ(draft.at("assets").size(), 1u);
  for (const char *key : {"handle", "session_id", "url", "data", "bytes"}) { EXPECT_FALSE(draft.contains(key)); }
  const auto before = count("create"), pages = count("summaries");
  const auto old_title = widget("reports_create_title")->string;
  const auto old_submit = widget("reports_create_submit")->on_click;
  ASSERT_TRUE(area().editor().load_workspace_state(state)); frame();
  old_title.assign("Obsolete title"); old_submit(); frame();
  EXPECT_EQ(area().editor().save_workspace_state(), state);
  EXPECT_EQ(count("create"), before); EXPECT_EQ(count("summaries"), pages);
  ASSERT_NE(widget("reports_create_submit"), nullptr); EXPECT_FALSE(widget("reports_create_submit")->enabled);
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_review"));
  ASSERT_NO_FATAL_FAILURE(click("reports_create_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
  EXPECT_EQ(widget("reports_create_title")->string.value(), "Keep creation draft");
  EXPECT_EQ(count("create"), before); EXPECT_EQ(count("asset"), 0);
  auto invalid = state; invalid["create_draft"]["unknown"] = true;
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  EXPECT_EQ(area().editor().save_workspace_state(), state);
}

TEST_F(ReportsEditorPython, UncertainCreationKeepsOriginalUuidAcrossNotFoundAndNeverReplays)
{
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  const auto original_submit = widget("reports_create_submit")->on_click;
  const auto before = count("create");
  ASSERT_NO_FATAL_FAILURE(mode("bad_create_receipt"));
  ASSERT_NO_FATAL_FAILURE(click("reports_create_submit"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_check"));
  const auto state = area().editor().save_workspace_state();
  ASSERT_EQ(state.at("version"), 2); const auto pending = state.at("create_draft").at("pending");
  ASSERT_TRUE(pending.is_object()); const auto id = pending.at("report_id");
  EXPECT_EQ(pending.at("expected_revision"), 3);
  EXPECT_EQ(count("create"), before + 1);
  ASSERT_NO_FATAL_FAILURE(mode("hide_created"));
  ASSERT_NO_FATAL_FAILURE(click("reports_create_check"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_check"));
  EXPECT_EQ(area().editor().save_workspace_state().at("create_draft").at("pending"), pending);
  original_submit(); frame(); EXPECT_EQ(count("create"), before + 1);
  ASSERT_TRUE(area().editor().load_workspace_state(state)); frame();
  EXPECT_EQ(area().editor().save_workspace_state().at("create_draft").at("pending").at("report_id"), id);
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_check"));
  ASSERT_NO_FATAL_FAILURE(click("reports_create_check"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return !area().editor().has_unsaved_changes(); }, 30));
  EXPECT_EQ(area().editor().save_workspace_state().at("report_id"), id);
  EXPECT_EQ(count("create"), before + 1); EXPECT_EQ(count("asset"), 0);
}

TEST_F(ReportsEditorPython, NewProjectCannotAdoptAnOldSnapshotSummaryReply)
{
  ASSERT_NO_FATAL_FAILURE(show_reports());
  ASSERT_NO_FATAL_FAILURE(click("reports_create_panel"));
  ASSERT_NO_FATAL_FAILURE(mode("hold_summaries"));
  ASSERT_NO_FATAL_FAILURE(click("reports_create_snapshots"));
  ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(dir.path() / "mode.held"); }, 15));
  ASSERT_TRUE(project().create(dir.str() + "/other-create-project", "Other report project"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); frame();
  ASSERT_NO_FATAL_FAILURE(drain_held(*client)); frame();
  EXPECT_EQ(widget("reports_create_snapshot_list"), nullptr);
  EXPECT_EQ(count("summaries"), 1); EXPECT_EQ(count("asset"), 0);
  const auto state = area().editor().save_workspace_state();
  EXPECT_EQ(state.at("version"), 1); EXPECT_FALSE(state.contains("create_draft"));
  EXPECT_NE(project().project()->id, project_id);
}

TEST_F(ReportsEditorPython, WorkspaceRejectsOversizedDeepAndMismatchedCreationStateAtomically)
{
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  const auto state = area().editor().save_workspace_state();
  const auto before = count("create"), pages = count("summaries");
  auto invalid = state; invalid["create_draft"]["name"] = std::string(600 * 1024, 'a');
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  EXPECT_EQ(area().editor().save_workspace_state(), state);
  nlohmann::json deep = nullptr;
  for (int i = 0; i < 512; ++i) { deep = nlohmann::json::array({std::move(deep)}); }
  invalid = state; invalid["create_draft"]["pending"] = std::move(deep);
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  EXPECT_EQ(area().editor().save_workspace_state(), state);
  invalid = state; invalid["asset_path"] = std::string(2 * 1024 * 1024, 'b');
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  invalid = state; invalid["version"] = uint64_t(-1);
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  EXPECT_EQ(area().editor().save_workspace_state(), state);
  ASSERT_NO_FATAL_FAILURE(mode("bad_create_receipt"));
  ASSERT_NO_FATAL_FAILURE(click("reports_create_submit"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_check"));
  const auto pending = area().editor().save_workspace_state();
  invalid = pending; invalid["create_draft"]["pending"]["manifest"]["source_revision"] = 0;
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  EXPECT_EQ(area().editor().save_workspace_state(), pending);
  invalid = pending; invalid["create_draft"]["pending"]["source_sha256"] = std::string(64, '0');
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  EXPECT_EQ(area().editor().save_workspace_state(), pending);
  EXPECT_EQ(count("create"), before + 1); EXPECT_EQ(count("summaries"), pages); EXPECT_EQ(count("asset"), 0);
}

TEST_F(ReportsEditorPython, CreationFieldBindingsKeepSiblingEditsAndRejectUsedOrRevisedCallbacks)
{
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  const auto title = widget("reports_create_title")->string;
  const auto path = widget("reports_create_path")->string;
  const auto submit = widget("reports_create_submit")->on_click;
  title.assign("Sibling title"); path.assign("nested/report.md");
  EXPECT_EQ(title.value(), ""); EXPECT_EQ(path.value(), "");
  title.assign("obsolete"); path.assign("obsolete.md"); submit(); frame();
  auto state = area().editor().save_workspace_state();
  EXPECT_EQ(state.at("create_draft").at("name"), "Sibling title");
  EXPECT_EQ(state.at("create_draft").at("assets").at(0).at("path"), "nested/report.md");
  EXPECT_EQ(count("create"), 1); // Only fixture setup, never the retained submit.
  const auto current_title = widget("reports_create_title")->string;
  const auto current_path = widget("reports_create_path")->string;
  const auto current_submit = widget("reports_create_submit")->on_click;
  call("project.apply", {{"handle", project().project()->handle}, {"expected_revision", 3},
      {"commands", Json::array({{{"op", "create_table"}, {"id", "f6666666-6666-4666-8666-666666666666"}, {"name", "Later"}}})}});
  project().refresh(); ASSERT_NO_FATAL_FAILURE(settle_project()); frame();
  current_title.assign("stale revision"); current_path.assign("stale.md"); current_submit(); frame();
  EXPECT_EQ(current_title.value(), ""); EXPECT_EQ(current_path.value(), "");
  EXPECT_EQ(area().editor().save_workspace_state(), state); EXPECT_EQ(count("create"), 1);
  ASSERT_NE(widget("reports_create_submit"), nullptr); EXPECT_FALSE(widget("reports_create_submit")->enabled);
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_review"));
}

TEST_F(ReportsEditorPython, BridgeReplacementPreservesUnconfirmedCreationAndIgnoresOldReceipt)
{
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  const auto before = count("create");
  ASSERT_NO_FATAL_FAILURE(mode("hold_create"));
  ASSERT_NO_FATAL_FAILURE(click("reports_create_submit"));
  ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(dir.path() / "mode.held"); }, 15));
  frame(); const auto pending = area().editor().save_workspace_state().at("create_draft").at("pending");
  const auto old_handle = project().project()->handle;
  auto old = std::move(client);
  project().attach(nullptr); store().set_bridge(nullptr); frame();
  ASSERT_NO_FATAL_FAILURE(mode("")); ASSERT_TRUE(start_client("creation-second"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); frame();
  ASSERT_NE(project().project()->handle, old_handle);
  ASSERT_NO_FATAL_FAILURE(drain_held(*old)); frame();
  EXPECT_EQ(area().editor().save_workspace_state().at("create_draft").at("pending"), pending);
  EXPECT_EQ(count("create"), before + 1); EXPECT_EQ(count("asset"), 0);
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_check"));
  ASSERT_NO_FATAL_FAILURE(click("reports_create_check"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return !area().editor().has_unsaved_changes(); }, 30));
  EXPECT_EQ(area().editor().save_workspace_state().at("report_id"), pending.at("report_id"));
  EXPECT_EQ(count("create"), before + 1); EXPECT_EQ(count("asset"), 0);
  old->close(); EXPECT_EQ(old->stats().schema_violations, 0u);
}


TEST_F(ReportsEditorPython, SourceSelectionUsesExplicitReadsAndCreatesExactReviewedContextWithThirteenClicks)
{
  const auto context = context_source(); ASSERT_TRUE(context.is_object());
  ASSERT_NO_FATAL_FAILURE(prepare_create("With frozen source"));
  auto *hidden = &area().tab(1); ASSERT_NE(hidden, nullptr); const auto hidden_state = hidden->save_workspace_state();
  const auto before = call("project.history", {{"handle", project().project()->handle}});
  ASSERT_NO_FATAL_FAILURE(add_first_source());
  EXPECT_EQ(count("source_list"), 1); EXPECT_EQ(count("source_review"), 0); EXPECT_EQ(count("asset"), 0);
  const auto draft = area().editor().save_workspace_state().at("create_draft");
  ASSERT_EQ(draft.at("sources").size(), 1u);
  EXPECT_FALSE(draft.contains("reviewed_sources")); EXPECT_TRUE(draft.at("pending").is_null());
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
  const auto created_before = count("create");
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_submit"));
  ASSERT_TRUE(loop.pump_until([&] {
    frame(); const auto state = area().editor().save_workspace_state();
    return !state.contains("create_draft") && !state.at("report_id").get<std::string>().empty();
  }, 30));
  const auto state = area().editor().save_workspace_state();
  const auto saved = call("project.reports.get", {{"handle", project().project()->handle}, {"report_id", state.at("report_id")}});
  ASSERT_EQ(saved.at("report").at("manifest").at("sources").size(), 1u);
  EXPECT_EQ(nlohmann::json(saved.at("report").at("manifest").at("sources")[0].at("context")), nlohmann::json(context.at("context")));
  EXPECT_EQ(count("source_review"), 1); EXPECT_EQ(count("create"), created_before + 1); EXPECT_EQ(count("asset"), 0);
  EXPECT_EQ(call("project.history", {{"handle", project().project()->handle}}).at("history").size(), before.at("history").size() + 1);
  EXPECT_EQ(hidden->save_workspace_state(), hidden_state); EXPECT_TRUE(hidden->has_unsaved_changes()); expect_viewer();
  RecordProperty("source_create_clicks", clicks); EXPECT_EQ(clicks, 13);
}

TEST_F(ReportsEditorPython, RestoredSourceDraftNeverReadsAndRejectsRetainedReviewControls)
{
  ASSERT_TRUE(context_source().is_object());
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  ASSERT_NO_FATAL_FAILURE(add_first_source());
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
  const auto state = area().editor().save_workspace_state();
  const auto old_review = widget("reports_create_sources_review")->on_click;
  const auto old_submit = widget("reports_create_submit")->on_click;
  const auto reads = count("source_review"), lists = count("source_list"), writes = count("create");
  ASSERT_TRUE(area().editor().load_workspace_state(state)); frame(); old_review(); old_submit(); frame();
  EXPECT_EQ(area().editor().save_workspace_state(), state);
  EXPECT_EQ(count("source_review"), reads); EXPECT_EQ(count("source_list"), lists); EXPECT_EQ(count("create"), writes);
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_sources_review"));
  EXPECT_FALSE(widget("reports_create_submit")->enabled);
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
  EXPECT_EQ(count("source_review"), reads + 1); EXPECT_EQ(count("create"), writes);
}

TEST_F(ReportsEditorPython, SourceCasConflictRequiresExplicitReviewAndNeverKeepsAnUncertainWrite)
{
  ASSERT_TRUE(context_source().is_object());
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  ASSERT_NO_FATAL_FAILURE(add_first_source());
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
  const auto before = call("project.history", {{"handle", project().project()->handle}});
  const auto writes = count("create"), reads = count("source_review");
  ASSERT_NO_FATAL_FAILURE(mode("source_conflict"));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_submit"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); const auto saved = area().editor().save_workspace_state();
    return saved.contains("create_draft") && saved.at("create_draft").at("pending").is_null() && widget("reports_create_sources_review")->enabled;
  }, 30));
  EXPECT_FALSE(widget("reports_create_submit")->enabled);
  EXPECT_EQ(count("create"), writes); EXPECT_EQ(count("source_review"), reads);
  EXPECT_EQ(call("project.history", {{"handle", project().project()->handle}}), before);
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
  EXPECT_EQ(count("source_review"), reads + 1);
}

TEST_F(ReportsEditorPython, ValidShapeWrongReviewDigestCannotEnableSubmission)
{
  ASSERT_TRUE(context_source().is_object());
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  ASSERT_NO_FATAL_FAILURE(add_first_source());
  ASSERT_NO_FATAL_FAILURE(mode("bad_source_digest"));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_sources_review"));
  EXPECT_FALSE(widget("reports_create_submit")->enabled); EXPECT_EQ(count("source_review"), 1);
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
}

TEST_F(ReportsEditorPython, RevisedProjectDiscardsHeldSourceReviewWithoutAutomaticallyReadingAgain)
{
  ASSERT_TRUE(context_source().is_object());
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  ASSERT_NO_FATAL_FAILURE(add_first_source());
  ASSERT_NO_FATAL_FAILURE(mode("hold_source_review"));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(dir.path() / "mode.held"); }, 15));
  ASSERT_TRUE(call("project.apply", {{"handle", project().project()->handle}, {"expected_revision", 3},
      {"commands", Json::array({{{"op", "create_table"}, {"id", "b2222222-2222-4222-8222-222222222222"}, {"name", "Later"}}})}}).is_object());
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(settle_project()); frame();
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain_held(*client)); frame();
  EXPECT_EQ(count("source_review"), 1); EXPECT_FALSE(widget("reports_create_submit")->enabled);
  const auto state = area().editor().save_workspace_state();
  EXPECT_EQ(state.at("create_draft").at("sources").size(), 1u); EXPECT_TRUE(state.at("create_draft").at("pending").is_null());
}

TEST_F(ReportsEditorPython, SourceCreationUncertainReceiptStillRequiresTheExactFullManifest)
{
  ASSERT_TRUE(context_source().is_object());
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  ASSERT_NO_FATAL_FAILURE(add_first_source());
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_submit"));
  const auto writes = count("create");
  ASSERT_NO_FATAL_FAILURE(mode("bad_create_receipt"));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_submit"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_check"));
  const auto pending = area().editor().save_workspace_state().at("create_draft").at("pending");
  ASSERT_EQ(pending.at("manifest").at("sources").size(), 1u);
  ASSERT_NO_FATAL_FAILURE(mode("changed_found_source"));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_check"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_check"));
  EXPECT_EQ(area().editor().save_workspace_state().at("create_draft").at("pending"), pending);
  EXPECT_EQ(count("create"), writes + 1);
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_check"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return !area().editor().save_workspace_state().contains("create_draft"); }, 30));
  EXPECT_EQ(count("create"), writes + 1);
}

TEST_F(ReportsEditorPython, SourceSelectionIsPagedAndRejectsMoreThanSixteenOrDuplicateWorkspaceKeys)
{
  Json selected = Json::array();
  for (int i = 0; i < 17; ++i) {
    const auto source = context_source(i); ASSERT_TRUE(source.is_object());
    if (i < 16) { selected.push_back({{"kind", "context"}, {"id", source.at("context").at("id")}}); }
  }
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  auto saved = area().editor().save_workspace_state(); saved["create_draft"]["sources"] = nlohmann::json(selected);
  ASSERT_TRUE(area().editor().load_workspace_state(saved)); frame();
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_panel"));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_load"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_source_candidates"));
  ASSERT_EQ(widget("reports_create_source_candidates")->list->count, 8);
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_next"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_source_candidates"));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_next"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_create_source_candidates"));
  ASSERT_EQ(widget("reports_create_source_candidates")->list->count, 1);
  ASSERT_NO_FATAL_FAILURE(source_scroll_to("reports_create_source_candidates"));
  ASSERT_NO_FATAL_FAILURE(click_row("reports_create_source_candidates", 0));
  ASSERT_NE(widget("reports_create_source_add"), nullptr); EXPECT_FALSE(widget("reports_create_source_add")->enabled);
  EXPECT_EQ(count("source_review"), 0); EXPECT_EQ(count("source_list"), 3);
  auto invalid = saved; invalid["create_draft"]["sources"].push_back(nlohmann::json(selected[0]));
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  invalid = saved; invalid["create_draft"]["sources"][1] = invalid["create_draft"]["sources"][0];
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  EXPECT_EQ(area().editor().save_workspace_state(), saved);
}

TEST_F(ReportsEditorPython, SourceFreeVersionOneDraftMigratesWithoutReadingMetadata)
{
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  auto legacy = area().editor().save_workspace_state();
  legacy["create_draft"]["version"] = 1; legacy["create_draft"].erase("sources");
  const auto reads = count("source_review"), lists = count("source_list");
  ASSERT_TRUE(area().editor().load_workspace_state(legacy)); frame();
  const auto state = area().editor().save_workspace_state();
  EXPECT_EQ(state.at("create_draft").at("version"), 2); EXPECT_TRUE(state.at("create_draft").at("sources").empty());
  EXPECT_EQ(count("source_review"), reads); EXPECT_EQ(count("source_list"), lists);
  EXPECT_FALSE(widget("reports_create_submit")->enabled);
}

TEST_F(ReportsEditorPython, NewProjectCannotAdoptAnOldSourceReviewAndKeepsTheOriginalDraft)
{
  ASSERT_TRUE(context_source().is_object());
  ASSERT_NO_FATAL_FAILURE(prepare_create());
  ASSERT_NO_FATAL_FAILURE(add_first_source());
  const auto draft = area().editor().save_workspace_state().at("create_draft");
  ASSERT_NO_FATAL_FAILURE(mode("hold_source_review"));
  ASSERT_NO_FATAL_FAILURE(source_click("reports_create_sources_review"));
  ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(dir.path() / "mode.held"); }, 15));
  ASSERT_TRUE(project().create(dir.str() + "/source-other", "Other source project"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); frame();
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain_held(*client)); frame();
  EXPECT_EQ(area().editor().save_workspace_state().at("create_draft"), draft);
  EXPECT_EQ(count("source_review"), 1); EXPECT_EQ(widget("reports_create_submit"), nullptr);
  EXPECT_EQ(widget("reports_create_sources_review"), nullptr);
}

}  // namespace
}  // namespace stk::app
