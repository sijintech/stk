/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_graph_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <filesystem>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;

class AnalysisDocumentsEditor : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"analysis-document-editor"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 1200};
  std::unique_ptr<bridge::Client> client;
  AppStore &store() { return f.shell->store(); }
  ViewerState &viewer() { return store().viewer(); }
  ProjectState &project() { return store().project(); }
  EditorArea &area() { return f.area("a2"); }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }

  void SetUp() override
  {
    viewer().set_auto_evaluate(false); viewer().prefetch_neighbours = false;
    viewer().set_metadata({{"presets", Json::array({io::read_json_file(fs::path(STK_REPO_ROOT) /
        "suan/graph/presets/muferro-domains.json")})}},
        io::read_json_file(fs::path(STK_REPO_ROOT) / "docs/specs/catalog/stk-catalog-m1.json"));
    fs::create_directories(dir.path() / "run");
    ASSERT_TRUE(viewer().open_path(core::path_to_utf8(dir.path() / "run"), "muferro-domains"));
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for analysis documents"; }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.executor = loop.executor(); options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready(); store().set_bridge(client.get()); project().sync();
    ASSERT_TRUE(project().create(dir.str() + "/project", "Analysis definitions"));
    ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy(); }, 30));
    ASSERT_TRUE(area().set_tab_type(0, kEditorAnalysisGraph));
    f.screen.set_maximized(&area()); area().find_region(EditorArea::kSidebar)->set_size_1x(410);
    f.drv->frame();
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame(); return store().scripts().ready() && store().scripts().desktop_ready() &&
          io::get_int(store().scripts().status(), "cursor", -1) >= 0;
    }, 30));
    loop.run_ready();
  }

  void TearDown() override
  {
    EXPECT_EQ(viewer().evaluations_started(), 0); EXPECT_FALSE(viewer().evaluating());
    viewer().close(); store().set_bridge(nullptr); project().attach(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }

  Json definition()
  {
    const auto capture = viewer().graph_inspection();
    const auto &config = *capture->desired;
    return {{"format", "stk.analysis-document/1"}, {"graph", config.graph},
        {"parameters", config.parameters}, {"outputs", config.requested_outputs}};
  }
  bool has_text(const std::string &text)
  {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  }
  const ui::Widget *name_widget()
  {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.key.find("/analysis_name/") != std::string::npos) { return &item; } }
    }
    return nullptr;
  }
  void expand(const char *key)
  {
    const auto *panel = widget(key); ASSERT_NE(panel, nullptr);
    const ui::Vec2 point{panel->rect.x + panel->rect.w / 2, panel->rect.y + panel->rect.h / 2};
    f.screen.ui()->handle_event(ui::Event::mouse_down(point));
    f.screen.ui()->handle_event(ui::Event::mouse_up(point)); f.drv->frame();
  }
  void save()
  {
    if (!widget("analysis_save")) { ASSERT_NO_FATAL_FAILURE(expand("graph_documents")); }
    ASSERT_NE(name_widget(), nullptr); name_widget()->string.assign("Saved volume definition"); f.drv->frame();
    ASSERT_NE(widget("analysis_save"), nullptr); ASSERT_TRUE(widget("analysis_save")->enabled);
    widget("analysis_save")->on_click();
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame(); return project().project()->revision == 1 && !project().busy() &&
          widget("graph_mode")->index.value() == 2;
    }, 30)) << client->bridge_log().text();
  }
};

TEST_F(AnalysisDocumentsEditor, SaveShowsIndependentDefinitionAndUndoKeepsItsOldReadExplicit)
{
  const auto before = definition();
  ASSERT_NO_FATAL_FAILURE(save());
  EXPECT_EQ(definition(), before);
  EXPECT_TRUE(has_text(std::string(store().tr("analysis_documents.definition_only"))));
  EXPECT_FALSE(has_text(std::string(store().tr("analysis_graph.no_comparison"))));
  EXPECT_EQ(project().tables().size(), 1u); ASSERT_EQ(project().tables()[0].records.size(), 1u);
  ASSERT_NE(widget("analysis_rename"), nullptr); EXPECT_TRUE(widget("analysis_rename")->enabled);
  ASSERT_TRUE(project().undo());
  ASSERT_TRUE(loop.pump_until([&] { return !project().busy() && project().project()->revision == 2; }, 30));
  f.drv->frame();
  EXPECT_TRUE(project().tables().empty());
  EXPECT_TRUE(has_text(std::string(store().tr("analysis_documents.stale"))));
  EXPECT_FALSE(widget("analysis_rename")->enabled);
  ASSERT_NE(widget("graph_node_select"), nullptr); // Explicitly retained read snapshot.
}

TEST_F(AnalysisDocumentsEditor, LateSaveDoesNotOverrideNewerViewerTabChoice)
{
  ASSERT_NO_FATAL_FAILURE(expand("graph_documents"));
  ASSERT_NE(name_widget(), nullptr); name_widget()->string.assign("Late save"); f.drv->frame();
  widget("analysis_save")->on_click();
  widget("graph_mode")->index.assign(1); f.drv->frame();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame(); return project().project()->revision == 1 && !project().busy();
  }, 30));
  EXPECT_EQ(widget("graph_mode")->index.value(), 1);
  widget("graph_mode")->index.assign(2); f.drv->frame();
  ASSERT_NE(widget("graph_node_select"), nullptr);
  EXPECT_TRUE(has_text(std::string(store().tr("analysis_documents.definition_only"))));
}

TEST_F(AnalysisDocumentsEditor, FirstSaveClickCommitsActiveUnicodeNameAndSavesOnce)
{
  ASSERT_NO_FATAL_FAILURE(expand("graph_documents"));
  ASSERT_NE(name_widget(), nullptr);
  const auto [x, y] = f.widget_center(name_widget()->key);
  f.drv->click(x, y);
  f.drv->key(wm::Key::Unknown, wm::ModNone, "首次保存 α"); f.drv->frame();
  ASSERT_TRUE(f.screen.ui()->text_input_active());
  ASSERT_EQ(f.screen.ui()->edit_state()->text(), "首次保存 α");
  const auto [save_x, save_y] = f.widget_center(widget("analysis_save")->key);
  f.drv->click(save_x, save_y);
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame(); return project().project()->revision == 1 && !project().busy();
  }, 30));
  ASSERT_EQ(project().tables().size(), 1u); ASSERT_EQ(project().tables()[0].records.size(), 1u);
  bool found = false;
  const auto &table = project().tables()[0];
  for (size_t column = 0; column < table.fields.size(); ++column) {
    if (table.fields[column].name == "Name") {
      ASSERT_NE(table.cell(0, int(column)), nullptr); EXPECT_EQ(*table.cell(0, int(column)), "首次保存 α"); found = true;
    }
  }
  EXPECT_TRUE(found); EXPECT_EQ(widget("graph_mode")->index.value(), 2);
}

TEST_F(AnalysisDocumentsEditor, RetainedSaveRejectsChangedConfigurationAndClosedEditor)
{
  ASSERT_NO_FATAL_FAILURE(expand("graph_documents"));
  name_widget()->string.assign("Old button"); f.drv->frame();
  const auto old_save = widget("analysis_save")->on_click;
  const auto old_name = name_widget()->string;
  viewer().set_parameter("min_magnitude", ui::FormValue::number(0.75));
  old_save(); loop.run_ready();
  EXPECT_EQ(project().project()->revision, 0);
  ASSERT_TRUE(area().set_tab_type(0, kEditorProject));
  old_name.assign("Must not write to a closed editor"); old_save(); loop.run_ready();
  EXPECT_EQ(project().project()->revision, 0);
}

TEST_F(AnalysisDocumentsEditor, RenameUsesSameIdentityAndReopenRequiresExplicitDocumentRead)
{
  ASSERT_NO_FATAL_FAILURE(save());
  const auto id = project().tables()[0].records[0].id;
  name_widget()->string.assign("Renamed analysis"); f.drv->frame();
  ASSERT_TRUE(widget("analysis_rename")->enabled); widget("analysis_rename")->on_click();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame(); return project().project()->revision == 2 && !project().busy();
  }, 30));
  ASSERT_EQ(project().tables()[0].records.size(), 1u); EXPECT_EQ(project().tables()[0].records[0].id, id);
  ASSERT_TRUE(project().close()); ASSERT_TRUE(loop.pump_until([&] { return !project().project(); }, 30));
  f.drv->frame(); EXPECT_EQ(widget("graph_node_select"), nullptr);
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy(); }, 30)); f.drv->frame();
  EXPECT_EQ(widget("graph_node_select"), nullptr);
  ASSERT_NE(widget("analysis_list"), nullptr); widget("analysis_list")->on_click();
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget("analysis_documents") != nullptr; }, 30));
  const auto table = *widget("analysis_documents")->table;
  ASSERT_EQ(table.rows, 1); EXPECT_EQ(table.cell(0, 0), "Renamed analysis"); table.selected.assign(0);
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget("graph_node_select") != nullptr; }, 30));
  EXPECT_TRUE(has_text(id));
}

TEST_F(AnalysisDocumentsEditor, SavedStateHasNoViewerReceiptAndIgnoresViewerOnlyChanges)
{
  AnalysisGraphState state(viewer());
  const auto document = definition();
  ASSERT_TRUE(state.open_document(project().project()->handle, "definition", 0, document));
  ASSERT_TRUE(state.saved()); ASSERT_TRUE(state.definition()); ASSERT_TRUE(state.view());
  EXPECT_FALSE(state.configuration()); EXPECT_FALSE(state.inspection());
  const auto view = state.view(); const auto generation = state.generation();
  viewer().set_parameter("min_magnitude", ui::FormValue::number(0.9)); state.sync();
  EXPECT_EQ(state.view(), view); EXPECT_EQ(state.generation(), generation);
  EXPECT_EQ(state.definition()->parameters, document.at("parameters")); EXPECT_FALSE(state.inspection());
  state.show_displayed(false);
  ASSERT_TRUE(state.configuration()); ASSERT_TRUE(state.inspection()); EXPECT_FALSE(state.saved());
  EXPECT_NE(state.definition()->parameters, document.at("parameters"));
  state.show_saved(); EXPECT_EQ(state.definition()->parameters, document.at("parameters")); EXPECT_FALSE(state.inspection());
}

TEST_F(AnalysisDocumentsEditor, SavedValidationSurvivesViewerChangeButNotNewDocumentOrClose)
{
  AnalysisGraphState state(viewer());
  auto document = definition();
  ASSERT_TRUE(state.open_document(project().project()->handle, "first", 0, document));
  ASSERT_TRUE(state.validate());
  viewer().set_parameter("min_magnitude", ui::FormValue::number(0.9)); state.sync();
  ASSERT_TRUE(loop.pump_until([&] { return !state.validating(); }, 30));
  ASSERT_TRUE(state.validation().is_object()); EXPECT_EQ(state.validation().at("ok"), true);
  ASSERT_TRUE(state.validate()); ASSERT_TRUE(bridge::test::wait_until([&] { return loop.queued() > 0; }, 30));
  document["parameters"]["min_magnitude"] = 0.8;
  ASSERT_TRUE(state.open_document(project().project()->handle, "second", 0, document));
  loop.run_ready(); EXPECT_TRUE(state.validation().is_null());
  ASSERT_TRUE(project().close()); ASSERT_TRUE(loop.pump_until([&] { return !project().project(); }, 30));
  state.sync(); EXPECT_FALSE(state.definition()); EXPECT_FALSE(state.view()); EXPECT_FALSE(state.inspection());
  EXPECT_FALSE(state.validate());
}

TEST_F(AnalysisDocumentsEditor, RememberingDocumentDoesNotChangeCurrentViewOrValidation)
{
  AnalysisGraphState state(viewer());
  ASSERT_TRUE(state.validate()); ASSERT_TRUE(loop.pump_until([&] { return !state.validating(); }, 30));
  const auto view = state.view(); const auto generation = state.generation(); const auto result = state.validation();
  ASSERT_TRUE(state.open_document(project().project()->handle, "remembered", 0, definition(), false));
  EXPECT_FALSE(state.saved()); EXPECT_EQ(state.view(), view); EXPECT_EQ(state.generation(), generation);
  EXPECT_EQ(state.validation(), result);
  EXPECT_FALSE(state.open_document("wrong-opening", "foreign", 0, definition()));
  EXPECT_EQ(state.generation(), generation); state.show_saved(); EXPECT_EQ(state.document_id(), "remembered");
}

TEST_F(AnalysisDocumentsEditor, SavedLayoutContainsModeOnlyAndDoesNotReopenProjectOrDefinition)
{
  ASSERT_NO_FATAL_FAILURE(save());
  const auto layout = area().editor().save_state();
  EXPECT_EQ(layout, (nlohmann::json{{"displayed", false}, {"saved", true}}));
  wmtest::AppFixture reopened;
  ASSERT_TRUE(reopened.area("a2").set_tab_type(0, kEditorAnalysisGraph));
  ASSERT_TRUE(reopened.area("a2").editor().load_state(layout));
  reopened.screen.set_maximized(&reopened.area("a2")); reopened.drv->frame();
  EXPECT_EQ(reopened.screen.ui()->find("graph_mode")->index.value(), 2);
  EXPECT_EQ(reopened.screen.ui()->find("graph_node_select"), nullptr);
  EXPECT_FALSE(reopened.shell->store().project().project());
  EXPECT_FALSE(reopened.shell->store().bridge());
  EXPECT_FALSE(reopened.area("a2").editor().load_state({{"saved", "yes"}}));
}

}  // namespace
}  // namespace stk::app
