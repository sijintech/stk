/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/app/workspace_transfer.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <optional>

namespace stk::app {
namespace {
using io::Json;
const std::string table_id = "f1111111-1111-4111-8111-111111111111";
const std::string field_id = "f2222222-2222-4222-8222-222222222222";
const std::string record_id = "f3333333-3333-4333-8333-333333333333";
const std::string draft = "# synthetic portable draft\nprint('explicit Run is required')\n";

class WorkspaceTransferPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir directory{"workspace-transfer"};
  wmtest::AppFixture original{"en", 1, 1440, 1200};
  wmtest::AppFixture *app = &original;
  std::unique_ptr<bridge::Client> client;
  std::string python;
  int clicks = 0;
  double clock = 10000;
  ProjectState &project() { return app->shell->store().project(); }
  WorkspaceTransfer &transfer() { return app->shell->workspace_transfer(); }
  const ui::Widget *widget(const char *key) { return app->screen.ui()->find(key); }
  void frame() { app->screen.run_deferred(); app->drv->frame(); }
  bool pump(const std::function<bool()> &predicate)
  {
    return loop.pump_until([&] { frame(); return predicate(); }, 45);
  }
  void click(const char *key)
  {
    const auto *w = widget(key); ASSERT_NE(w, nullptr) << key;
    ASSERT_TRUE(w->enabled) << key;
    ASSERT_FALSE(w->rect.intersect(w->clip).empty()) << key;
    const auto [x, y] = app->widget_center(key);
    ASSERT_TRUE(app->drv->click(x, y)) << key;
    ++clicks; frame();
  }
  void text(const char *key, const std::string &value)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
    app->drv->key(wm::Key::A, wm::ModCtrl | wm::ModOS);
    auto event = ui::Event::text_input(value); event.time = ++clock;
    app->screen.ui()->handle_event(event); frame();
    app->drv->key(wm::Key::Enter); frame();
  }
  void menu(const char *label)
  {
    const auto *file = widget("file"); ASSERT_NE(file, nullptr);
    const auto translated = std::string(app->shell->store().tr(label));
    const auto found = std::find_if(file->menu.begin(), file->menu.end(), [&](const auto &entry) { return entry.text == translated; });
    ASSERT_NE(found, file->menu.end()) << label;
    const auto index = int(found - file->menu.begin());
    ASSERT_NO_FATAL_FAILURE(click("file"));
    const auto key = "popup/" + std::to_string(index);
    ASSERT_NO_FATAL_FAILURE(click(key.c_str()));
    ASSERT_TRUE(transfer().visible());
  }
  std::unique_ptr<bridge::Client> bridge(const std::string &tag)
  {
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = directory.str() + "/" + tag + "/bridge";
    options.cache_dir = directory.str() + "/" + tag + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = directory.str() + "/" + tag + "/runtime";
    options.env["STK_PROFILES_FILE"] = directory.str() + "/" + tag + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    return bridge::Client::create(options);
  }
  void export_file(const std::filesystem::path &path)
  {
    ASSERT_NO_FATAL_FAILURE(menu("workspace.transfer.export"));
    ASSERT_NO_FATAL_FAILURE(text("workspace_export_path", core::path_to_utf8(path)));
    ASSERT_NO_FATAL_FAILURE(click("workspace_export"));
    ASSERT_TRUE(pump([&] { return !transfer().busy() && std::filesystem::is_regular_file(path); }));
    ASSERT_TRUE(transfer().error().empty()) << transfer().error();
    ASSERT_NO_FATAL_FAILURE(click("workspace_transfer_close"));
  }
  void preview_file(const std::filesystem::path &path)
  {
    ASSERT_NO_FATAL_FAILURE(menu("workspace.transfer.import"));
    ASSERT_NO_FATAL_FAILURE(text("workspace_import_source", core::path_to_utf8(path)));
    ASSERT_NO_FATAL_FAILURE(click("workspace_preview"));
    ASSERT_TRUE(pump([&] { return !transfer().busy() && transfer().preview().is_object(); }));
    ASSERT_TRUE(transfer().error().empty()) << transfer().error();
    ASSERT_TRUE(transfer().preview().value("complete", false)) << transfer().preview().at("diagnostics");
  }
  Editor *python_editor(wmtest::AppFixture &fixture)
  {
    for (auto *base : fixture.screen.areas()) {
      auto *area = dynamic_cast<EditorArea *>(base); if (!area) { continue; }
      for (int i = 0; i < area->tab_count(); ++i) { if (area->tab(i).type().id == kEditorPython) { return &area->tab(i); } }
    }
    return nullptr;
  }
  void add_hidden_draft()
  {
    auto &area = original.area("a3");
    ASSERT_TRUE(area.add_tab(kEditorPython, false));
    auto *editor = python_editor(original); ASSERT_NE(editor, nullptr);
    ASSERT_TRUE(editor->load_state({{"source", draft}, {"baseline", ""}}));
    ASSERT_TRUE(editor->has_unsaved_changes()); frame();
  }
  void SetUp() override
  {
    python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    client = bridge("original"); ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)); loop.run_ready();
    original.shell->store().set_bridge(client.get()); project().sync();
    ASSERT_TRUE(project().create(directory.str() + "/project", "Synthetic portable workspace"));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", table_id}, {"name", "Synthetic observations"}},
      {{"op", "add_field"}, {"id", field_id}, {"table_id", table_id}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_record"}, {"id", record_id}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", field_id}, {"value", 300}},
    })));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    project().select_table(table_id); project().select_record(record_id); frame();
    std::filesystem::create_directory(directory.path() / "project" / "inputs");
    std::ofstream file(directory.path() / "project" / "inputs" / "synthetic.txt"); file << "synthetic portable resource\n"; file.close(); ASSERT_TRUE(file.good());
    original.shell->store().viewer().set_overlays(false); frame();
  }
  void TearDown() override
  {
    app = &original;
    original.shell->store().project().attach(nullptr); original.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(WorkspaceTransferPython, ExportFromFileMenuPreservesAHiddenProgramDraftAndNeverRunsIt)
{
  ASSERT_NO_FATAL_FAILURE(add_hidden_draft());
  const auto revision = project().project()->revision;
  const auto before = original.screen.to_json();
  const auto archive = directory.path() / "synthetic.stkworkspace";
  clicks = 0;
  ASSERT_NO_FATAL_FAILURE(export_file(archive));
  EXPECT_EQ(clicks, 5);  // File, Export entry, path focus, Export, Close.
  ASSERT_NE(python_editor(original), nullptr);
  EXPECT_EQ(python_editor(original)->save_state().at("source"), draft);
  EXPECT_TRUE(python_editor(original)->has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(original.screen.to_json(), before);
  EXPECT_TRUE(original.shell->store().scripts().history().empty());
  EXPECT_EQ(original.shell->store().viewer().evaluations_started(), 0u);
}

TEST_F(WorkspaceTransferPython, FreshBridgeAndShellRestoreProjectResourcesWindowParametersAndUnrunDraft)
{
  ASSERT_NO_FATAL_FAILURE(add_hidden_draft());
  const std::string disk_source = "# synthetic public disk version\n";
  const auto program = directory.path() / "portable-program.py";
  {
    std::ofstream file(program, std::ios::binary); file << disk_source; file.close();
    ASSERT_TRUE(file.good());
  }
  auto program_state = python_editor(original)->save_state();
  program_state["path"] = core::path_to_utf8(program);
  program_state["source_path"] = core::path_to_utf8(program);
  program_state["baseline"] = disk_source;
  program_state["version"] = core::Sha256::hex(disk_source);
  ASSERT_TRUE(python_editor(original)->load_state(program_state));
  ASSERT_EQ(python_editor(original)->workspace_resource_paths(), std::vector<std::string>{core::path_to_utf8(program)});
  const auto project_id = project().project()->id;
  const auto archive = directory.path() / "synthetic-portable.stkworkspace";
  ASSERT_NO_FATAL_FAILURE(export_file(archive));
  ASSERT_TRUE(std::filesystem::remove(program));
  wmtest::AppFixture fresh{"en", 1, 1440, 1200};
  auto fresh_client = bridge("fresh"); ASSERT_TRUE(fresh_client->start()); ASSERT_TRUE(fresh_client->wait_ready(60)); loop.run_ready();
  fresh.shell->store().set_bridge(fresh_client.get()); fresh.shell->store().project().sync();
  app = &fresh; frame();
  const auto destination = directory.path() / "fresh-import";
  clicks = 0;
  ASSERT_NO_FATAL_FAILURE(preview_file(archive));
  ASSERT_NO_FATAL_FAILURE(text("workspace_import_destination", core::path_to_utf8(destination)));
  ASSERT_NO_FATAL_FAILURE(click("workspace_import"));
  ASSERT_TRUE(pump([&] { return !transfer().busy(); }))
      << "transfer_error=" << transfer().error() << " project_error=" << project().error()
      << " project_loaded=" << project().loaded() << " project_busy=" << project().busy();
  ASSERT_TRUE(transfer().error().empty())
      << "transfer_error=" << transfer().error() << " project_error=" << project().error()
      << " project_loaded=" << project().loaded() << " project_busy=" << project().busy();
  ASSERT_TRUE(project().loaded()) << "Project adoption did not finish; error=" << project().error();
  ASSERT_TRUE(project().project().has_value());
  ASSERT_EQ(project().project()->id, project_id);
  EXPECT_EQ(clicks, 6);  // File, Import entry, source focus, Preview, destination focus, Import.
  EXPECT_EQ(project().table_id(), table_id); EXPECT_EQ(project().record_id(), record_id);
  ASSERT_NE(project().table(), nullptr); EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_TRUE(std::filesystem::is_regular_file(destination / "workspace.json"));
  EXPECT_TRUE(std::filesystem::is_regular_file(destination / "project" / "inputs" / "synthetic.txt"));
  ASSERT_NE(python_editor(fresh), nullptr);
  EXPECT_EQ(python_editor(fresh)->save_state().at("source"), draft);
  EXPECT_TRUE(python_editor(fresh)->has_unsaved_changes());
  const auto restored_program_state = python_editor(fresh)->save_state();
  const auto restored_program = core::path_from_utf8(io::get_string(restored_program_state, "source_path"));
  const auto relative = restored_program.lexically_relative(destination);
  ASSERT_FALSE(relative.empty());
  ASSERT_FALSE(relative.is_absolute());
  EXPECT_NE(*relative.begin(), "..");
  EXPECT_EQ(restored_program.filename(), program.filename());
  std::ifstream restored_file(restored_program, std::ios::binary);
  ASSERT_TRUE(restored_file.good());
  const std::string restored_source{std::istreambuf_iterator<char>(restored_file), std::istreambuf_iterator<char>()};
  EXPECT_EQ(restored_source, disk_source);
  EXPECT_EQ(io::get_string(restored_program_state, "baseline"), disk_source);
  EXPECT_EQ(io::get_string(restored_program_state, "version"), core::Sha256::hex(disk_source));
  EXPECT_EQ(python_editor(fresh)->workspace_resource_paths(), std::vector<std::string>{core::path_to_utf8(restored_program)});
  EXPECT_FALSE(fresh.shell->store().viewer().overlays());
  EXPECT_TRUE(fresh.shell->store().scripts().history().empty());
  EXPECT_EQ(fresh.shell->store().viewer().evaluations_started(), 0u);
  EXPECT_EQ(fresh_client->stats().schema_violations, 0u);
  fresh.shell->store().project().attach(nullptr); fresh.shell->store().set_bridge(nullptr);
  fresh_client->close(); loop.run_ready(); app = &original;
}

TEST_F(WorkspaceTransferPython, PackedPayloadAndIndependentCameraRestoreOnAFreshBridge)
{
  const auto fixture = std::filesystem::path(STK_REPO_ROOT) / "desktop/tests/viewer/fixtures/muferro_domains.stkp";
  const auto source = directory.path() / "synthetic-external-source.stkp";
  std::filesystem::copy_file(fixture, source);
  const auto source_bytes = core::read_file(source);
  const auto payload = std::make_shared<io::Payload>(io::read_stkp(source));
  ASSERT_FALSE(payload->buffers.empty()); ASSERT_FALSE(payload->layers().empty());
  const auto layer_id = payload->layers()[0].at("id").get<std::string>();
  auto &viewer = original.shell->store().viewer();
  viewer.open_payload(payload, core::path_to_utf8(source));
  viewer.set_parameter("synthetic_temperature", ui::FormValue::number(298.25));
  viewer.set_parameter("synthetic_annotation", ui::FormValue::string("Portable frozen display"));
  viewer.set_layer_opacity(layer_id, 0.375); viewer.set_layer_visible(layer_id, false);
  viewer.set_auto_evaluate(true); viewer.fps = 11.5; viewer.loop = false; viewer.prefetch_neighbours = true;
  viewer.export_settings.width = 1536; viewer.export_settings.height = 864;
  viewer.export_settings.magnification = 2; viewer.export_settings.transparent = true;
  viewer.export_settings.path = "portable-scientific-view.png";
  frame();
  const auto editor = [](wmtest::AppFixture &fixture) -> Editor * {
    for (auto *base : fixture.screen.areas()) {
      auto *area = dynamic_cast<EditorArea *>(base); if (!area) { continue; }
      for (int i = 0; i < area->tab_count(); ++i) {
        if (area->tab(i).type().id == kEditorViewer) { return &area->tab(i); }
      }
    }
    return nullptr;
  };
  auto *source_editor = editor(original); ASSERT_NE(source_editor, nullptr);
  auto camera = source_editor->save_workspace_state();
  camera["camera"]["position"] = {12.0, 9.0, 5.0};
  camera["camera"]["parallel"] = true; camera["camera"]["parallel_scale"] = 7.25;
  camera["camera"]["view_angle_deg"] = 45.0; camera["saved_camera"] = camera["camera"];
  camera["navigation"] = "paraview"; camera["lighting"] = "headlight"; camera["tool"] = "pick";
  ASSERT_TRUE(source_editor->load_workspace_state(camera)); frame();
  const auto expected_viewer = viewer.save_workspace_state(), expected_parameters = viewer.parameters();
  const auto project_id = project().project()->id;
  const auto archive = directory.path() / "packed-payload.stkworkspace";
  ASSERT_NO_FATAL_FAILURE(export_file(archive));
  ASSERT_TRUE(std::filesystem::remove(source));

  auto fresh_client = bridge("fresh-payload");
  ASSERT_TRUE(fresh_client->start()); ASSERT_TRUE(fresh_client->wait_ready(60)); loop.run_ready();
  wmtest::AppFixture fresh{"en", 1, 1440, 1200};
  fresh.shell->store().set_bridge(fresh_client.get()); fresh.shell->store().project().sync();
  app = &fresh; frame();
  const auto destination = directory.path() / "fresh-payload-import";
  ASSERT_NO_FATAL_FAILURE(preview_file(archive));
  ASSERT_NO_FATAL_FAILURE(text("workspace_import_destination", core::path_to_utf8(destination)));
  ASSERT_NO_FATAL_FAILURE(click("workspace_import"));
  ASSERT_TRUE(pump([&] { return !transfer().busy(); })) << transfer().error();
  ASSERT_TRUE(transfer().error().empty()) << transfer().error();
  ASSERT_TRUE(project().loaded()); ASSERT_TRUE(project().project().has_value());
  EXPECT_EQ(project().project()->id, project_id);
  EXPECT_EQ(std::filesystem::path(project().project()->directory), destination / "project");
  auto &restored = fresh.shell->store().viewer();
  const auto actual = restored.base_payload(); ASSERT_NE(actual, nullptr); EXPECT_NE(actual, payload);
  EXPECT_EQ(actual->manifest, payload->manifest);
  ASSERT_EQ(actual->buffers.size(), payload->buffers.size());
  for (size_t i = 0; i < payload->buffers.size(); ++i) {
    const auto &expected = payload->buffers[i], &buffer = actual->buffers[i];
    EXPECT_EQ(buffer.id, expected.id); EXPECT_EQ(buffer.sha256, expected.sha256);
    EXPECT_EQ(buffer.byte_length, expected.byte_length);
    EXPECT_EQ(buffer.bytes.size(), expected.bytes.size());
    EXPECT_TRUE(std::equal(buffer.bytes.span().begin(), buffer.bytes.span().end(),
                           expected.bytes.span().begin(), expected.bytes.span().end()));
  }
  const auto relocated_source = destination / "resources" / "viewer-source" / source.filename();
  ASSERT_TRUE(std::filesystem::is_regular_file(relocated_source));
  EXPECT_EQ(core::read_file(relocated_source), source_bytes);
  EXPECT_EQ(std::filesystem::path(restored.source().path), relocated_source);
  EXPECT_FALSE(std::filesystem::exists(source));
  EXPECT_TRUE(std::filesystem::is_regular_file(destination / "resources" / "viewer-payload" / "viewer.stkp"));
  EXPECT_EQ(restored.parameters(), expected_parameters);
  const auto actual_viewer = restored.save_workspace_state();
  for (const auto *key : {"form_values", "visibility", "opacity", "overlays", "auto_evaluate", "fps", "loop",
                          "prefetch_neighbours", "export_settings", "data_debounce_s", "client_debounce_s"}) {
    EXPECT_EQ(actual_viewer.at(key), expected_viewer.at(key)) << key;
  }
  auto *restored_editor = editor(fresh); ASSERT_NE(restored_editor, nullptr);
  EXPECT_EQ(restored_editor->save_workspace_state(), camera);
  EXPECT_TRUE(restored.workspace_suspended()); EXPECT_FALSE(restored.playing()); EXPECT_FALSE(restored.evaluating());
  EXPECT_TRUE(fresh.shell->store().scripts().history().empty());
  EXPECT_EQ(restored.evaluations_started(), 0u); EXPECT_EQ(viewer.evaluations_started(), 0u);
  EXPECT_EQ(fresh_client->stats().schema_violations, 0u);
  fresh.shell->store().project().attach(nullptr); fresh.shell->store().set_bridge(nullptr);
  fresh_client->close(); loop.run_ready(); app = &original;
}

TEST_F(WorkspaceTransferPython, EditingTheSourceOrClosingPreviewInvalidatesAnOldImportButton)
{
  const auto archive = directory.path() / "synthetic.stkworkspace";
  ASSERT_NO_FATAL_FAILURE(export_file(archive));
  ASSERT_NO_FATAL_FAILURE(preview_file(archive));
  const auto destination = directory.path() / "must-not-be-created";
  ASSERT_NO_FATAL_FAILURE(text("workspace_import_destination", core::path_to_utf8(destination)));
  ASSERT_NE(widget("workspace_import"), nullptr);
  const auto stale = widget("workspace_import")->on_click;
  const auto revision = project().project()->revision;
  ASSERT_NO_FATAL_FAILURE(text("workspace_import_source", directory.str() + "/other.stkworkspace"));
  stale(); frame();
  EXPECT_FALSE(transfer().busy()); EXPECT_FALSE(std::filesystem::exists(destination));
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NO_FATAL_FAILURE(click("workspace_transfer_close"));
  stale(); frame();
  EXPECT_FALSE(transfer().visible()); EXPECT_FALSE(std::filesystem::exists(destination));
  EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(WorkspaceTransferPython, AnInFlightRestoreCannotReplaceANewerPayloadWithTheSameSourceLabel)
{
  auto &viewer = original.shell->store().viewer();
  const auto first = std::make_shared<io::Payload>(io::read_stkp(
      std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  auto newer = std::make_shared<io::Payload>(*first);
  ASSERT_FALSE(newer->manifest.at("layers").empty());
  newer->manifest["layers"][0]["name"] = "Synthetic newer payload";
  ASSERT_NE(first->manifest, newer->manifest);
  const std::string label = "Synthetic same-label source";
  viewer.open_payload(first, label); frame();
  const auto archive = directory.path() / "same-label-source.stkworkspace";
  ASSERT_NO_FATAL_FAILURE(export_file(archive));
  ASSERT_NO_FATAL_FAILURE(preview_file(archive));
  const auto sha256 = transfer().preview().at("sha256").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(click("workspace_transfer_close"));
  const auto before = original.shell->capture_workspace();
  const auto project_id = project().project()->id, handle = project().project()->handle;
  const auto revision = project().project()->revision;
  std::optional<bridge::Result<Json>> response;
  ASSERT_TRUE(original.shell->import_workspace(core::path_to_utf8(archive),
      directory.str() + "/same-label-import", sha256,
      [&](bridge::Result<Json> result) { response = std::move(result); }));
  // A new in-memory source can have the same serialized label and parameters.
  // Change it before dispatching the response, without drawing a camera-fit frame.
  viewer.open_payload(newer, label);
  const auto payload_serial = viewer.payload_serial(), camera_serial = viewer.camera_serial();
  ASSERT_EQ(original.shell->capture_workspace(), before);
  ASSERT_TRUE(loop.pump_until([&] {
    original.screen.run_deferred();
    return response.has_value();
  }, 45));
  ASSERT_FALSE(response->ok());
  EXPECT_EQ(response->error().code, bridge::ErrorCode::Conflict);
  EXPECT_EQ(viewer.base_payload(), newer);
  EXPECT_EQ(viewer.payload_serial(), payload_serial); EXPECT_EQ(viewer.camera_serial(), camera_serial);
  EXPECT_EQ(project().project()->id, project_id); EXPECT_EQ(project().project()->handle, handle);
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_TRUE(original.shell->store().scripts().history().empty());
  EXPECT_EQ(viewer.evaluations_started(), 0u);
}

TEST_F(WorkspaceTransferPython, PublicApplyAndExportPreserveAnAlreadyQueuedViewerOpenRequest)
{
  auto &store = original.shell->store();
  const auto before = original.shell->capture_workspace(); auto candidate = before;
  candidate["app"]["viewer"]["overlays"] = true;
  const auto handle = project().project()->handle; const auto revision = project().project()->revision;
  const auto calls = client->stats().calls_sent;
  OpenResultRequest pending; pending.connection = "local"; pending.preset = "volume";
  pending.local_paths = {directory.str() + "/project/inputs/synthetic.txt"};
  store.request_open_result(pending);
  ASSERT_TRUE(store.has_open_result());
  std::string error; EXPECT_FALSE(original.shell->apply_workspace(candidate, &error)); EXPECT_FALSE(error.empty());
  bool called = false;
  EXPECT_FALSE(original.shell->export_workspace(directory.str() + "/not-exported.stkworkspace",
      [&](bridge::Result<Json>) { called = true; }));
  EXPECT_FALSE(called); EXPECT_EQ(client->stats().calls_sent, calls);
  EXPECT_FALSE(std::filesystem::exists(directory.path() / "not-exported.stkworkspace"));
  EXPECT_EQ(original.shell->capture_workspace(), before);
  EXPECT_EQ(project().project()->handle, handle); EXPECT_EQ(project().project()->revision, revision);
  ASSERT_TRUE(store.has_open_result()); const auto preserved = store.take_open_result(); ASSERT_TRUE(preserved);
  EXPECT_EQ(preserved->connection, pending.connection); EXPECT_EQ(preserved->preset, pending.preset);
  EXPECT_EQ(preserved->local_paths, pending.local_paths);
  EXPECT_EQ(store.viewer().evaluations_started(), 0u); EXPECT_TRUE(store.scripts().history().empty());
}

TEST_F(WorkspaceTransferPython, AnInFlightRestoreCannotConsumeOrReplaceANewQueuedViewerOpenRequest)
{
  const auto archive = directory.path() / "pending-result.stkworkspace";
  ASSERT_NO_FATAL_FAILURE(export_file(archive));
  ASSERT_NO_FATAL_FAILURE(preview_file(archive));
  const auto sha256 = transfer().preview().at("sha256").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(click("workspace_transfer_close"));
  auto &store = original.shell->store(); const auto before = original.shell->capture_workspace();
  const auto handle = project().project()->handle; const auto revision = project().project()->revision;
  const auto payload = store.viewer().base_payload(); const auto serial = store.viewer().payload_serial();
  std::optional<bridge::Result<Json>> response;
  ASSERT_TRUE(original.shell->import_workspace(core::path_to_utf8(archive), directory.str() + "/pending-result-import", sha256,
      [&](bridge::Result<Json> result) { response = std::move(result); }));
  OpenResultRequest pending; pending.connection = "local"; pending.preset = "volume";
  pending.local_paths = {directory.str() + "/project/inputs/synthetic.txt"};
  store.request_open_result(pending);
  ASSERT_EQ(original.shell->capture_workspace(), before);  // queued intent is intentionally outside serialized workspace state
  ASSERT_TRUE(loop.pump_until([&] { original.screen.run_deferred(); return response.has_value(); }, 45));
  ASSERT_FALSE(response->ok()); EXPECT_EQ(response->error().code, bridge::ErrorCode::Conflict);
  EXPECT_EQ(project().project()->handle, handle); EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(store.viewer().base_payload(), payload); EXPECT_EQ(store.viewer().payload_serial(), serial);
  ASSERT_TRUE(store.has_open_result()); const auto preserved = store.take_open_result(); ASSERT_TRUE(preserved);
  EXPECT_EQ(preserved->connection, pending.connection); EXPECT_EQ(preserved->preset, pending.preset);
  EXPECT_EQ(preserved->local_paths, pending.local_paths);
  EXPECT_EQ(store.viewer().evaluations_started(), 0u); EXPECT_TRUE(store.scripts().history().empty());
}

TEST_F(WorkspaceTransferPython, ChangedArchiveAfterPreviewFailsBeforeDestinationOrCurrentStateIsModified)
{
  const auto archive = directory.path() / "synthetic.stkworkspace";
  ASSERT_NO_FATAL_FAILURE(export_file(archive));
  ASSERT_NO_FATAL_FAILURE(preview_file(archive));
  const auto destination = directory.path() / "changed-archive-import";
  ASSERT_NO_FATAL_FAILURE(text("workspace_import_destination", core::path_to_utf8(destination)));
  const auto project_id = project().project()->id, handle = project().project()->handle;
  const auto revision = project().project()->revision;
  const auto before = original.screen.to_json();
  std::ofstream changed(archive, std::ios::binary | std::ios::app); changed << "synthetic changed bytes"; changed.close(); ASSERT_TRUE(changed.good());
  ASSERT_NO_FATAL_FAILURE(click("workspace_import"));
  ASSERT_TRUE(pump([&] { return !transfer().busy() && !transfer().error().empty(); }));
  EXPECT_FALSE(std::filesystem::exists(destination));
  EXPECT_EQ(project().project()->id, project_id); EXPECT_EQ(project().project()->handle, handle);
  EXPECT_EQ(project().project()->revision, revision); EXPECT_EQ(original.screen.to_json(), before);
  EXPECT_TRUE(original.shell->store().scripts().history().empty());
}

TEST_F(WorkspaceTransferPython, AnIncompletePackageRequiresExplicitConsentAndRetainsItsResourceDiagnostics)
{
  auto &table = original.area("a4").editor();
  auto parameters = table.save_state();
  parameters["io"]["destination"] = directory.str() + "/future-output.xlsx";
  ASSERT_TRUE(table.load_state(parameters)); frame();
  const auto archive = directory.path() / "incomplete.stkworkspace";
  ASSERT_NO_FATAL_FAILURE(export_file(archive));
  ASSERT_NO_FATAL_FAILURE(menu("workspace.transfer.import"));
  ASSERT_NO_FATAL_FAILURE(text("workspace_import_source", core::path_to_utf8(archive)));
  ASSERT_NO_FATAL_FAILURE(click("workspace_preview"));
  ASSERT_TRUE(pump([&] { return !transfer().busy() && transfer().preview().is_object(); }));
  ASSERT_FALSE(transfer().preview().value("complete", true));
  const auto diagnostics = transfer().preview().at("diagnostics"); ASSERT_FALSE(diagnostics.empty());
  const auto destination = directory.path() / "explicit-incomplete-import";
  ASSERT_NO_FATAL_FAILURE(text("workspace_import_destination", core::path_to_utf8(destination)));
  ASSERT_NE(widget("workspace_import"), nullptr); EXPECT_FALSE(widget("workspace_import")->enabled);
  const auto stale = widget("workspace_import")->on_click; stale(); frame();
  EXPECT_FALSE(transfer().busy()); EXPECT_FALSE(std::filesystem::exists(destination));
  ASSERT_NO_FATAL_FAILURE(click("workspace_allow_incomplete"));
  ASSERT_TRUE(widget("workspace_import")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("workspace_import"));
  ASSERT_TRUE(pump([&] { return !transfer().busy() && std::filesystem::is_regular_file(destination / "workspace.json"); }));
  ASSERT_TRUE(transfer().error().empty()) << transfer().error();
  std::ifstream stream(destination / "workspace.json"); Json manifest; stream >> manifest;
  EXPECT_FALSE(manifest.at("complete").get<bool>());
  EXPECT_EQ(manifest.at("diagnostics"), diagnostics);
  EXPECT_TRUE(original.shell->store().scripts().history().empty());
  ASSERT_NO_FATAL_FAILURE(click("workspace_transfer_close"));
  ASSERT_NO_FATAL_FAILURE(menu("workspace.transfer.open"));
  ASSERT_NO_FATAL_FAILURE(text("workspace_open_directory", core::path_to_utf8(destination)));
  ASSERT_NE(widget("workspace_allow_incomplete"), nullptr);
  EXPECT_FALSE(widget("workspace_allow_incomplete")->boolean.value());
  const auto handle = project().project()->handle;
  ASSERT_NO_FATAL_FAILURE(click("workspace_open"));
  ASSERT_TRUE(pump([&] { return !transfer().busy() && !transfer().error().empty(); }));
  EXPECT_EQ(project().project()->handle, handle) << "Reopen does not inherit a previous incomplete-resource approval";
  ASSERT_NO_FATAL_FAILURE(click("workspace_allow_incomplete"));
  ASSERT_NO_FATAL_FAILURE(click("workspace_open"));
  ASSERT_TRUE(pump([&] { return !transfer().busy() && transfer().error().empty(); }));
  std::ifstream reopened(destination / "workspace.json"); Json persisted; reopened >> persisted;
  EXPECT_FALSE(persisted.at("complete").get<bool>());
  EXPECT_EQ(persisted.at("diagnostics"), diagnostics);
  EXPECT_TRUE(original.shell->store().scripts().history().empty());
}

TEST_F(WorkspaceTransferPython, CaptureAndApplyPreserveAValidEmptyProjectSelection)
{
  ASSERT_TRUE(project().apply(Json::array({{{"op", "delete_table"}, {"id", table_id}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && project().tables().empty(); }));
  EXPECT_TRUE(project().table_id().empty()); EXPECT_TRUE(project().record_id().empty());
  const auto saved = original.shell->capture_workspace();
  const auto identity = project().project()->id, handle = project().project()->handle;
  const auto revision = project().project()->revision;
  std::string error;
  ASSERT_TRUE(original.shell->apply_workspace(saved, &error)) << error;
  frame();
  EXPECT_EQ(project().project()->id, identity); EXPECT_EQ(project().project()->handle, handle);
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_TRUE(project().tables().empty()); EXPECT_TRUE(project().table_id().empty()); EXPECT_TRUE(project().record_id().empty());
  EXPECT_TRUE(original.shell->store().scripts().history().empty());
}

TEST_F(WorkspaceTransferPython, CaptureAndApplyPreserveAValidEmptyTableSelection)
{
  ASSERT_TRUE(project().apply(Json::array({{{"op", "delete_record"}, {"id", record_id}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && project().table() && project().table()->records.empty(); }));
  EXPECT_EQ(project().table_id(), table_id); EXPECT_TRUE(project().record_id().empty());
  const auto saved = original.shell->capture_workspace();
  const auto revision = project().project()->revision;
  std::string error;
  ASSERT_TRUE(original.shell->apply_workspace(saved, &error)) << error;
  frame();
  EXPECT_EQ(project().project()->revision, revision); EXPECT_EQ(project().table_id(), table_id);
  ASSERT_NE(project().table(), nullptr); EXPECT_TRUE(project().table()->records.empty()); EXPECT_TRUE(project().record_id().empty());
  EXPECT_TRUE(original.shell->store().scripts().history().empty());
}

TEST_F(WorkspaceTransferPython, UnsavedDraftPreflightExplainsItsRefusalWithoutCallingTheOpenService)
{
  ASSERT_NO_FATAL_FAILURE(add_hidden_draft());
  ASSERT_NO_FATAL_FAILURE(menu("workspace.transfer.open"));
  ASSERT_NO_FATAL_FAILURE(text("workspace_open_directory", directory.str() + "/nonexistent-workspace"));
  const auto identity = project().project()->id;
  ASSERT_NO_FATAL_FAILURE(click("workspace_open"));
  EXPECT_FALSE(transfer().busy()); EXPECT_EQ(transfer().error(), "app.unsaved");
  EXPECT_EQ(project().project()->id, identity);
  ASSERT_NE(python_editor(original), nullptr);
  EXPECT_EQ(python_editor(original)->save_state().at("source"), draft);
  EXPECT_TRUE(python_editor(original)->has_unsaved_changes());
  EXPECT_TRUE(original.shell->store().scripts().history().empty());
}

}  // namespace
}  // namespace stk::app
