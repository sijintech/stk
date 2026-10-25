/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/project_skills.hh"
#include "stk/app/project_state.hh"
#include "stk/app/skill_catalog.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;

// SQLite/library writes and schema checks remain real. Inject receipt/read drift or one definite
// pre-write conflict to exercise observation recovery and the explicit new-version choice.
constexpr const char *kSkillBridge = R"PY(
import copy
from pathlib import Path
import sys
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main
from suan.desktop_bridge.protocol import BridgeError
from suan.skills import catalog
control = Path(sys.argv.pop(1))
original_catalog = catalog.load_catalog
def load_catalog(*args, **kwargs):
    if control.exists() and control.read_text(encoding='utf-8') == 'catalog_absent':
        raise catalog.SkillCatalogError('not_found', 'Test catalog is unavailable')
    kwargs['directories'] = [('builtin', catalog._builtin_root()), ('test', control.parent / 'definitions')]
    return original_catalog(*args, **kwargs)
catalog.load_catalog = load_catalog
original_init = Bridge.__init__
def controlled_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    publish = self.methods['project.skills.publish_global']
    def controlled_publish(params, context):
        mode = control.read_text(encoding='utf-8') if control.exists() else ''
        if mode == 'global_conflict' and params['mode'] == 'exact':
            raise BridgeError('conflict', 'Test occupied library version')
        return publish(params, context)
    self.methods['project.skills.publish_global'] = controlled_publish
    publication = self.methods['skills.publication.get']
    def controlled_publication(params, context):
        mode = control.read_text(encoding='utf-8') if control.exists() else ''
        if mode == 'global_query_conflict':
            raise BridgeError('conflict', 'Test unreadable publication receipt', data={'catalog_code': 'invalid_definition'})
        return publication(params, context)
    self.methods['skills.publication.get'] = controlled_publication
Bridge.__init__ = controlled_init
original = Bridge.send
def send(self, message, method=None):
    mode = control.read_text(encoding='utf-8') if control.exists() else ''
    if 'result' in message:
        if method in ('project.skills.pin', 'project.skills.create_workflow') and mode == 'receipt':
            message = copy.deepcopy(message)
            message['result']['record_id'] = '00000000-0000-4000-8000-000000000000'
        if method == 'project.skills.publish_global' and mode == 'global_receipt':
            message = copy.deepcopy(message)
            message['result']['publication_id'] = '00000000-0000-4000-8000-000000000000'
        if method == 'skills.get' and mode in ('catalog_digest', 'catalog_source'):
            message = copy.deepcopy(message)
            message['result']['skill']['content_sha256' if mode == 'catalog_digest' else 'source'] = '0' * 64 if mode == 'catalog_digest' else 'user'
        if method == 'project.skills.get' and mode == 'summary':
            message = copy.deepcopy(message)
            message['result']['skill']['versions'][0]['ref'] = 'stk.other@1'
    return original(self, message, method)
Bridge.send = send
main()
)PY";

class ProjectSkillsPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"project-skills"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;
  std::unique_ptr<ProjectSkills> skills;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  void mode(const std::string &value)
  {
    std::ofstream file(dir.path() / "mode", std::ios::binary); file << value;
    ASSERT_TRUE(file.good());
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    {
      std::ofstream script(dir.path() / "bridge.py", std::ios::binary); script << kSkillBridge;
      ASSERT_TRUE(script.good());
    }
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    options.command = {python, "-u", dir.str() + "/bridge.py", dir.str() + "/mode",
                       "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)); loop.run_ready();
    store().set_bridge(client.get()); project().sync();
    ASSERT_TRUE(loop.pump_until([&] { return project().ready(); }, 30));
    ASSERT_TRUE(project().create(dir.str() + "/project", "Saved skills"));
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy() && project().loaded() && !project().recent_loading(); }, 30));
    skills = std::make_unique<ProjectSkills>(store()); ASSERT_TRUE(skills->supported());
  }
  void TearDown() override
  {
    EXPECT_EQ(store().viewer().evaluations_started(), 0); EXPECT_FALSE(store().viewer().payload());
    skills.reset(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
  void settle()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !skills->busy() && !project().busy() && !project().recent_loading(); }, 30))
        << skills->error() << project().error();
  }
  Json call(const std::string &method, Json params)
  {
    std::optional<bridge::Result<Json>> response;
    client->call(method, std::move(params)).then([&](auto result) { response = std::move(result); });
    if (!loop.pump_until([&] { return response.has_value(); }, 30) || !response->ok()) {
      ADD_FAILURE() << method << " failed: " << (response ? response->error().describe() : "timed out"); return nullptr;
    }
    return response->value();
  }
  Json pin_params(const Json &item, const std::string &id)
  {
    return {{"skill_id", item.at("id")}, {"version", item.at("version")},
            {"content_sha256", item.at("content_sha256")}, {"project_skill_id", id},
            {"expected_revision", skills->revision()}};
  }
  Json first_skill()
  {
    return call("skills.get", {{"id", "stk.muferro.energy_trace"}, {"version", 1}}).at("skill");
  }
  void click(const std::string &key)
  {
    f.drv->frame();
    const auto *button = f.screen.ui()->find(key);
    ASSERT_NE(button, nullptr) << key; ASSERT_TRUE(button->enabled) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_GE(x, 0); ASSERT_LT(x, f.drv->ctx.rect.width());
    ASSERT_GE(y, 0); ASSERT_LT(y, f.drv->ctx.rect.height());
    f.drv->click(x, y); f.drv->frame();
  }
  void wait_for(const std::string &key, int64_t revision)
  {
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame(); const auto *button = f.screen.ui()->find(key);
      return button && button->enabled && !project().busy() && project().project()->revision == revision;
    }, 30)) << key << " revision " << revision;
  }
  Json saved_skill(const std::string &id)
  {
    return call("project.skills.get", {{"handle", project().project()->handle}, {"project_skill_id", id}}).at("skill");
  }
  void create_source(const std::string &id)
  {
    const auto document = Json::parse(R"({"format":"stk.analysis-document/1","graph":{"schema":"stk.graph/1","id":"user-method","name":"User method","parameters":[{"name":"large","type":"integer","default":1}],"nodes":[{"id":"source","type":"missing.source.node@1","params":{"binding":"data"}}],"outputs":{"view":"source.payload"}},"parameters":{"large":9007199254740993},"outputs":[]})");
    const auto result = call("project.analyses.create", {{"handle", project().project()->handle}, {"analysis_id", id},
        {"name", "My saved analysis"}, {"document", document}, {"expected_revision", project().project()->revision}});
    ASSERT_TRUE(result.is_object());
    project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
  }
  void publish_clicks(const std::string &language, float scale, int width)
  {
    const auto source = ProjectSkills::new_id(); ASSERT_NO_FATAL_FAILURE(create_source(source));
    store().set_language(language);
    f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, int(width * scale), int(1200 * scale), scale);
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
    f.screen.set_maximized(&area); f.drv->frame();
    const auto viewer = store().viewer().save_workspace_state();
    int clicks = 0;
    ASSERT_NO_FATAL_FAILURE(click("skills_project_tab")); ++clicks;
    ASSERT_NO_FATAL_FAILURE(click("project_skill_publish")); ++clicks;
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_sources", 1));
    ASSERT_NO_FATAL_FAILURE(click("project_skill_sources")); ++clicks;
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_publish_new", 1));
    const auto retained = f.screen.ui()->find("project_skill_publish_new")->on_click;
    ASSERT_NO_FATAL_FAILURE(click("project_skill_publish_new")); ++clicks;
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_analysis", 2));
    EXPECT_EQ(clicks, 4);
    const auto id = area.editor().save_workspace_state().at("selected_id").get<std::string>();
    const auto first = saved_skill(id);
    ASSERT_EQ(first.at("active").at("version"), 1);
    EXPECT_EQ(first.at("document").at("versions").at(0).at("template").at("source").at("analysis_id"), source);
    retained(); f.drv->frame(); loop.run_ready(); EXPECT_EQ(project().project()->revision, 2);
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_publish_version", 2));
    ASSERT_NO_FATAL_FAILURE(click("project_skill_publish_version"));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_analysis", 3));
    const auto second = saved_skill(id);
    EXPECT_EQ(second.at("active").at("version"), 2);
    EXPECT_EQ(second.at("document").at("versions").at(0), first.at("document").at("versions").at(0));
    EXPECT_EQ(store().viewer().save_workspace_state(), viewer);
  }
  std::string user_analysis_skill()
  {
    const auto source = ProjectSkills::new_id(), id = ProjectSkills::new_id();
    create_source(source);
    if (!skills->write("publish_analysis", {{"analysis_id", source}, {"project_skill_id", id}, {"create", true},
        {"name", "User method"}, {"description", "Explicit local method"},
        {"expected_revision", project().project()->revision}}, skills->epoch())) { ADD_FAILURE(); return {}; }
    settle();
    if (!skills->select(id)) { ADD_FAILURE(); return {}; }
    settle(); return id;
  }
  void show_project_skill(const std::string &id, const std::string &language = "en", float scale = 1, int width = 1280)
  {
    store().set_language(language);
    f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, int(width * scale), int(1800 * scale), scale);
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
    ASSERT_TRUE(area.editor().load_workspace_state({{"version", 1}, {"project_view", true},
        {"project_id", project().project()->id}, {"selected_id", id}}));
    f.screen.set_maximized(&area);
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_publish_global", project().project()->revision));
  }
  void settle_publication()
  {
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return !store().skills().publication_busy(); }, 30));
  }
  void select_library(const std::string &ref)
  {
    auto &library = store().skills();
    ASSERT_NO_FATAL_FAILURE(click("skills_library_tab"));
    ASSERT_TRUE(library.search(ref));
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return !library.loading(); }, 30));
    ASSERT_TRUE(library.select(ref));
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return !library.detail_loading(); }, 30));
    ASSERT_TRUE(library.detail().is_object()) << library.detail_error();
  }
  void create_workflow_source(const std::string &id, const std::string &child)
  {
    const Json interface = {{"inputs", Json::object()}, {"outputs", Json::object()}, {"parameters", Json::array()}};
    const Json child_document = {{"format", "stk.workflow/2"}, {"steps", Json::array()},
                                 {"ui", Json::object()}, {"interface", interface}};
    ASSERT_TRUE(call("project.workflows.create", {{"handle", project().project()->handle}, {"workflow_id", child},
        {"name", "Z child workflow"}, {"document", child_document},
        {"expected_revision", project().project()->revision}}).is_object());
    project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
    const Json document = {{"format", "stk.workflow/2"},
        {"steps", {{{"id", "nested"}, {"kind", "workflow"}, {"ref", {{"workflow", child}}}}}},
        {"ui", Json::object()}, {"interface", interface}};
    ASSERT_TRUE(call("project.workflows.create", {{"handle", project().project()->handle}, {"workflow_id", id},
        {"name", "A reusable workflow"}, {"document", document},
        {"expected_revision", project().project()->revision}}).is_object());
    project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
  }
  void workflow_clicks(const std::string &language, float scale, int width)
  {
    const auto source = ProjectSkills::new_id(), child = ProjectSkills::new_id();
    ASSERT_NO_FATAL_FAILURE(create_workflow_source(source, child));
    store().set_language(language);
    f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, int(width * scale), int(1800 * scale), scale);
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
    f.screen.set_maximized(&area); f.drv->frame();
    const auto viewer = store().viewer().save_workspace_state();
    int clicks = 0;
    ASSERT_NO_FATAL_FAILURE(click("skills_project_tab")); ++clicks;
    ASSERT_NO_FATAL_FAILURE(click("project_skill_workflow_publish")); ++clicks;
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_workflow_sources", 2));
    // Insertion order is child, then parent. Click the parent row's actual screen coordinates.
    const auto *sources = f.screen.ui()->find("project_skill_workflow_sources"); ASSERT_NE(sources, nullptr);
    const auto &style = f.screen.ui()->style();
    const int source_x = int(sources->rect.x + sources->rect.w * 0.5f);
    const int source_y = f.screen.rect().ymax - 1 - int(sources->rect.y + style.pixel + style.unit * 1.5f);
    f.drv->click(source_x, source_y); f.drv->frame(); ++clicks;
    ASSERT_EQ(f.screen.ui()->find("project_skill_workflow_sources")->list->selected.get(), 1);
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_workflow_publish_new", 2));
    ASSERT_NO_FATAL_FAILURE(click("project_skill_workflow_publish_new")); ++clicks;
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_workflow", 3));
    EXPECT_EQ(clicks, 4);
    const auto id = area.editor().save_workspace_state().at("selected_id").get<std::string>();
    const auto first = saved_skill(id);
    const auto &templ = first.at("document").at("versions").at(0).at("template");
    EXPECT_EQ(templ.at("source").at("workflow_id"), source);
    EXPECT_EQ(templ.at("workflows").size(), 2u);
    EXPECT_TRUE(templ.at("workflows").contains(child));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_workflow_publish_version", 3));
    ASSERT_NO_FATAL_FAILURE(click("project_skill_workflow_publish_version"));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_workflow", 4));
    EXPECT_EQ(saved_skill(id).at("active").at("version"), 2);
    EXPECT_EQ(saved_skill(id).at("document").at("versions").at(0), first.at("document").at("versions").at(0));
    const auto retained = f.screen.ui()->find("project_skill_create_workflow")->on_click;
    ASSERT_NO_FATAL_FAILURE(click("project_skill_create_workflow"));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_open_workflow", 5));
    retained(); f.drv->frame(); loop.run_ready(); EXPECT_EQ(project().project()->revision, 5);
    const auto workflows = call("project.workflows.list", {{"handle", project().project()->handle}}).at("workflows");
    ASSERT_EQ(workflows.size(), 4u);
    std::string copied;
    for (const auto &workflow : workflows) {
      const auto candidate = io::get_string(workflow, "id");
      if (candidate != source && candidate != child && io::get_string(workflow, "name") == "A reusable workflow") { copied = candidate; }
    }
    ASSERT_FALSE(copied.empty());
    const auto copied_document = call("project.workflows.get", {{"handle", project().project()->handle}, {"workflow_id", copied}})
        .at("workflow").at("document");
    EXPECT_NE(copied_document.at("steps").at(0).at("ref").at("workflow"), child);
    ASSERT_NO_FATAL_FAILURE(click("project_skill_open_workflow"));
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return area.editor().type().id == kEditorWorkflow &&
        area.editor().shows_navigation_target({{"workflow_id", copied}, {"handle", project().project()->handle}}); }, 30));
    EXPECT_EQ(store().viewer().save_workspace_state(), viewer);
  }
  void upgrade_restore(const std::string &language, float scale, int width)
  {
    store().set_language(language);
    f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, int(width * scale), int(1000 * scale), scale);
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
    f.screen.set_maximized(&area); f.drv->frame();
    ASSERT_TRUE(loop.pump_until([&] { return store().skills().loaded() && !store().skills().loading(); }, 30));
    ASSERT_TRUE(store().skills().select("stk.muferro.energy_trace@1"));
    ASSERT_TRUE(loop.pump_until([&] { return !store().skills().detail_loading(); }, 30));
    const auto viewer_before = store().viewer().save_workspace_state();
    ASSERT_NO_FATAL_FAILURE(click("project_skill_pin"));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_analysis", 1));
    const auto workspace = area.editor().save_workspace_state();
    const auto id = workspace.at("selected_id").get<std::string>();
    const auto original_skill = saved_skill(id);
    const auto old_hash = original_skill.at("active").at("content_sha256").get<std::string>();

    auto definition = original_skill.at("document").at("versions").at(0).at("definition");
    definition["version"] = 2;
    definition["title"] = {{"en", "Energy method revision two"}, {"zh_CN", "能量方法第二版"}};
    std::filesystem::create_directories(dir.path() / "definitions");
    {
      std::ofstream file(dir.path() / "definitions" / "stk.muferro.energy_trace.json", std::ios::binary);
      file << definition.dump(); ASSERT_TRUE(file.good());
    }
    ASSERT_TRUE(store().skills().refresh());
    ASSERT_TRUE(loop.pump_until([&] { return !store().skills().loading(); }, 30));
    ASSERT_TRUE(store().skills().select("stk.muferro.energy_trace@2"));
    ASSERT_TRUE(loop.pump_until([&] { return !store().skills().detail_loading(); }, 30));
    ASSERT_NO_FATAL_FAILURE(click("project_skill_upgrade"));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_analysis", 2));
    const auto upgraded = saved_skill(id);
    ASSERT_EQ(upgraded.at("active").at("version"), 2); ASSERT_EQ(upgraded.at("versions").size(), 2u);
    EXPECT_EQ(upgraded.at("document").at("versions").at(0), original_skill.at("document").at("versions").at(0));

    ASSERT_NO_FATAL_FAILURE(mode("catalog_absent"));
    ASSERT_TRUE(store().skills().refresh());
    ASSERT_TRUE(loop.pump_until([&] { return !store().skills().loading(); }, 30));
    ASSERT_FALSE(store().skills().error().empty());
    ASSERT_NO_FATAL_FAILURE(click("project_skill_restore_" + old_hash));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_analysis", 3));
    EXPECT_EQ(saved_skill(id).at("active"), original_skill.at("active"));
    ASSERT_NO_FATAL_FAILURE(click("project_skill_create_analysis"));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_open_analysis", 4));
    const auto analyses = call("project.analyses.list", {{"handle", project().project()->handle}});
    ASSERT_EQ(analyses.at("analyses").size(), 1u);
    const auto analysis_id = analyses.at("analyses").at(0).at("id");
    const auto analysis = call("project.analyses.get", {{"handle", project().project()->handle}, {"analysis_id", analysis_id}});
    EXPECT_EQ(analysis.at("analysis").at("document").at("graph").at("ui").at("project_skill").at("content_sha256"), old_hash);

    // A fresh editor restores only the selection; no installed catalog or executable is needed.
    ASSERT_TRUE(area.set_tab_type(0, kEditorPython)); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
    ASSERT_TRUE(area.editor().load_workspace_state(workspace));
    ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_analysis", 4));
    EXPECT_EQ(area.editor().save_workspace_state(), workspace);
    EXPECT_EQ(store().viewer().save_workspace_state(), viewer_before);
    EXPECT_EQ(store().viewer().evaluations_started(), 0);
    ASSERT_TRUE(project().create(dir.str() + "/other-project", "Other project"));
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy() && !project().recent_loading(); }, 30));
    f.drv->frame();
    EXPECT_TRUE(area.editor().save_workspace_state().at("selected_id").get<std::string>().empty());
    EXPECT_EQ(project().project()->revision, 0);
  }
};

TEST_F(ProjectSkillsPython, PinsEveryBuiltinAndCopiesAnAnalysisWithoutEvaluation)
{
  ASSERT_TRUE(skills->load_page()); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_EQ(skills->page().at("total"), 0); EXPECT_EQ(project().project()->revision, 0);
  const auto catalog = call("skills.list", {{"offset", 0}, {"limit", 50}});
  ASSERT_EQ(catalog.at("skills").size(), 6u);
  for (const auto &item : catalog.at("skills")) {
    const auto id = ProjectSkills::new_id();
    ASSERT_TRUE(skills->write("pin", pin_params(item, id), skills->epoch()));
    ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_FALSE(skills->uncertain()) << skills->error();
    ASSERT_TRUE(skills->select(id)); ASSERT_NO_FATAL_FAILURE(settle());
    ASSERT_TRUE(skills->current()) << skills->error();
    EXPECT_EQ(skills->selected().at("active").at("content_sha256"), item.at("content_sha256"));
  }
  const auto analysis = ProjectSkills::new_id();
  ASSERT_TRUE(skills->write("create_analysis", {{"project_skill_id", skills->selected_id()},
      {"content_sha256", skills->selected().at("active").at("content_sha256")},
      {"analysis_id", analysis}, {"name", "Frozen method"}, {"expected_revision", skills->revision()}}, skills->epoch()));
  ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_EQ(skills->analysis_id(), analysis);
  const auto result = call("project.analyses.get", {{"handle", project().project()->handle}, {"analysis_id", analysis}});
  EXPECT_EQ(result.at("analysis").at("document").at("graph").at("ui").at("project_skill").at("id"), skills->selected_id());
  EXPECT_EQ(project().project()->revision, 7);
}

TEST_F(ProjectSkillsPython, UncertainReceiptIsInspectedWithoutReplayingTheWrite)
{
  const auto item = first_skill(); const auto id = ProjectSkills::new_id();
  ASSERT_NO_FATAL_FAILURE(mode("receipt"));
  const auto params = pin_params(item, id);
  ASSERT_TRUE(skills->write("pin", params, skills->epoch())); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills->uncertain()); EXPECT_FALSE(skills->write("pin", params, skills->epoch()));
  ASSERT_TRUE(skills->check_pending()); ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_FALSE(skills->uncertain()); EXPECT_TRUE(skills->current()) << skills->error();
  EXPECT_EQ(skills->selected_id(), id); EXPECT_EQ(project().project()->revision, 1);
  ASSERT_TRUE(skills->load_page()); ASSERT_NO_FATAL_FAILURE(settle()); EXPECT_EQ(skills->page().at("total"), 1);
}

TEST_F(ProjectSkillsPython, PublishesUserAnalysisAndCopiesExactSubmissionWithoutCatalog)
{
  const auto source = ProjectSkills::new_id(), id = ProjectSkills::new_id();
  ASSERT_NO_FATAL_FAILURE(create_source(source));
  ASSERT_NO_FATAL_FAILURE(mode("catalog_absent"));
  ASSERT_TRUE(skills->can_publish());
  ASSERT_TRUE(skills->write("publish_analysis", {{"analysis_id", source}, {"project_skill_id", id}, {"create", true},
      {"name", "User method"}, {"description", "Explicit local method"}, {"expected_revision", 1}}, skills->epoch()));
  ASSERT_NO_FATAL_FAILURE(settle()); EXPECT_FALSE(skills->uncertain()) << skills->error();
  ASSERT_TRUE(skills->select(id)); ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_TRUE(skills->current()) << skills->error();
  const auto copy = ProjectSkills::new_id();
  ASSERT_TRUE(skills->write("create_analysis", {{"project_skill_id", id},
      {"content_sha256", skills->selected().at("active").at("content_sha256")}, {"analysis_id", copy},
      {"name", "Copied user method"}, {"expected_revision", 2}}, skills->epoch()));
  ASSERT_NO_FATAL_FAILURE(settle());
  const auto result = call("project.analyses.get", {{"handle", project().project()->handle}, {"analysis_id", copy}});
  const auto &document = result.at("analysis").at("document");
  EXPECT_EQ(document.at("parameters").at("large"), INT64_C(9007199254740993));
  EXPECT_TRUE(document.at("outputs").empty());
  EXPECT_EQ(document.at("graph").at("ui").at("project_skill").at("id"), id);
}

TEST_F(ProjectSkillsPython, PublishesUserSkillInFourClicksEnglishAndAppendsVersion)
{
  ASSERT_NO_FATAL_FAILURE(publish_clicks("en", 1, 1280));
}

TEST_F(ProjectSkillsPython, PublishesUserSkillInFourClicksChineseAndAppendsVersion)
{
  ASSERT_NO_FATAL_FAILURE(publish_clicks("zh_CN", 2, 560));
}

TEST_F(ProjectSkillsPython, RetainedPublishButtonCannotFollowAnotherSourceSelection)
{
  ASSERT_NO_FATAL_FAILURE(create_source(ProjectSkills::new_id()));
  ASSERT_NO_FATAL_FAILURE(create_source(ProjectSkills::new_id()));
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
  f.screen.set_maximized(&area); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("skills_project_tab"));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_publish"));
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_sources", 2));
  const auto select = f.screen.ui()->find("project_skill_sources")->list->selected.set;
  select(0); ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_publish_new", 2));
  const auto retained = f.screen.ui()->find("project_skill_publish_new")->on_click;
  select(1); ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_publish_new", 2));
  retained(); f.drv->frame(); loop.run_ready();
  EXPECT_EQ(project().project()->revision, 2);
  const auto page = call("project.skills.list", {{"handle", project().project()->handle}});
  EXPECT_EQ(page.at("total"), 0);
}

TEST_F(ProjectSkillsPython, PublishesWorkflowInFourClicksEnglishAndCreatesFrozenClosure)
{
  ASSERT_NO_FATAL_FAILURE(workflow_clicks("en", 1, 1280));
}

TEST_F(ProjectSkillsPython, PublishesWorkflowInFourClicksChineseAndCreatesFrozenClosure)
{
  ASSERT_NO_FATAL_FAILURE(workflow_clicks("zh_CN", 2, 560));
}

TEST_F(ProjectSkillsPython, WorkflowLostReceiptChecksOriginalRootWithoutCreatingAgain)
{
  const auto source = ProjectSkills::new_id(), child = ProjectSkills::new_id(), id = ProjectSkills::new_id();
  ASSERT_NO_FATAL_FAILURE(create_workflow_source(source, child));
  ASSERT_TRUE(skills->can_publish_workflow()); ASSERT_TRUE(skills->can_create_workflow());
  ASSERT_TRUE(skills->write("publish_workflow", {{"workflow_id", source}, {"project_skill_id", id}, {"create", true},
      {"name", "Frozen workflow"}, {"description", "Complete method"}, {"expected_revision", 2}}, skills->epoch()));
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills->select(id)); ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_TRUE(skills->current()) << skills->error();
  ASSERT_NO_FATAL_FAILURE(mode("receipt"));
  const auto copy = ProjectSkills::new_id();
  const Json params = {{"project_skill_id", id}, {"workflow_id", copy}, {"name", "New workflow"},
      {"content_sha256", skills->selected().at("active").at("content_sha256")}, {"expected_revision", 3},
      {"bindings", {{"tables", Json::object()}, {"fields", Json::object()}, {"snapshots", Json::object()}}}};
  ASSERT_TRUE(skills->write("create_workflow", params, skills->epoch())); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills->uncertain()); EXPECT_FALSE(skills->write("create_workflow", params, skills->epoch()));
  ASSERT_TRUE(skills->check_pending()); ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_FALSE(skills->uncertain()); EXPECT_EQ(skills->workflow_id(), copy);
  EXPECT_EQ(project().project()->revision, 4);
  EXPECT_EQ(call("project.workflows.list", {{"handle", project().project()->handle}}).at("total"), 4);
}

TEST_F(ProjectSkillsPython, WorkflowMappingsPreserveInvalidDraftAndRejectRetainedCreate)
{
  const auto table = ProjectSkills::new_id(), source = ProjectSkills::new_id(), id = ProjectSkills::new_id();
  ASSERT_TRUE(call("project.apply", {{"handle", project().project()->handle}, {"expected_revision", 0},
      {"commands", {{{"op", "create_table"}, {"id", table}, {"name", "Measurements"}}}}}).is_object());
  const Json document = {{"format", "stk.workflow/1"}, {"steps", {{{"id", "data"}, {"kind", "table"}, {"ref", {{"table", table}}}}}},
      {"ui", Json::object()}};
  ASSERT_TRUE(call("project.workflows.create", {{"handle", project().project()->handle}, {"workflow_id", source},
      {"name", "Data method"}, {"document", document}, {"expected_revision", 1}}).is_object());
  project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills->write("publish_workflow", {{"workflow_id", source}, {"project_skill_id", id}, {"create", true},
      {"name", "Data method"}, {"description", "Reviewed references"}, {"expected_revision", 2}}, skills->epoch()));
  ASSERT_NO_FATAL_FAILURE(settle());
  f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, 1280, 1600, 1);
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
  ASSERT_TRUE(area.editor().load_workspace_state({{"version", 1}, {"project_view", true},
      {"project_id", project().project()->id}, {"selected_id", id}}));
  f.screen.set_maximized(&area); ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_workflow", 3));
  const auto *field = f.screen.ui()->find("project_skill_workflow_bindings"); ASSERT_NE(field, nullptr);
  EXPECT_EQ(Json::parse(field->string.get()).at("tables").at(table), table);
  const auto retained = f.screen.ui()->find("project_skill_create_workflow")->on_click;
  field->string.set("{ unfinished mapping"); f.drv->frame();
  ASSERT_FALSE(f.screen.ui()->find("project_skill_create_workflow")->enabled);
  retained(); loop.run_ready(); EXPECT_EQ(project().project()->revision, 3);
  const auto workspace = area.editor().save_workspace_state();
  ASSERT_EQ(workspace.at("binding_drafts").size(), 1u);
  EXPECT_EQ(workspace.at("binding_drafts").begin().value(), "{ unfinished mapping");
  ASSERT_NO_FATAL_FAILURE(click("project_skills_refresh"));
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); const auto *mapping = f.screen.ui()->find("project_skill_workflow_bindings");
      return mapping && mapping->string.get() == "{ unfinished mapping" && !project().busy(); }, 30));
  ASSERT_TRUE(area.editor().load_workspace_state(workspace)); f.drv->frame();
  EXPECT_EQ(area.editor().save_workspace_state().at("binding_drafts"), workspace.at("binding_drafts"));
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_workflow_bindings", 3));
  const auto old_get = f.screen.ui()->find("project_skill_workflow_bindings")->string.get;
  const auto old_set = f.screen.ui()->find("project_skill_workflow_bindings")->string.set;
  const auto second = ProjectSkills::new_id();
  ASSERT_TRUE(call("project.skills.publish_workflow", {{"handle", project().project()->handle}, {"workflow_id", source},
      {"project_skill_id", second}, {"create", true}, {"name", "Another method"},
      {"description", "Different selected skill"}, {"expected_revision", 3}}).is_object());
  project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); const auto *list = f.screen.ui()->find("project_skills_list");
      return list && list->list && list->list->count == 2; }, 30));
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skills_list", 4));
  f.screen.ui()->find("project_skills_list")->list->selected.set(1);
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_workflow", 4));
  const auto before = area.editor().save_workspace_state().at("binding_drafts");
  EXPECT_EQ(old_get(), ""); old_set("late edit from another skill");
  EXPECT_EQ(area.editor().save_workspace_state().at("binding_drafts"), before);
  const auto current_get = f.screen.ui()->find("project_skill_workflow_bindings")->string.get;
  const auto current_set = f.screen.ui()->find("project_skill_workflow_bindings")->string.set;
  ASSERT_TRUE(area.editor().load_workspace_state({{"version", 1}, {"project_view", true},
      {"project_id", project().project()->id}, {"selected_id", second}}));
  EXPECT_NO_THROW(EXPECT_EQ(current_get(), ""));
  current_set("late edit after workspace restore");
  EXPECT_TRUE(area.editor().save_workspace_state().at("binding_drafts").empty());
}

TEST_F(ProjectSkillsPython, LargeWorkflowDependenciesStayBrowsableAndMappingsRemainEditable)
{
  // A valid structural method may collect independent tables without being ready for a run.
  // This package exceeds the old 64 KiB text limit while staying inside all storage budgets.
  Json commands = Json::array(), child_steps = Json::array();
  std::vector<std::string> tables;
  for (int i = 0; i < 800; ++i) {
    tables.push_back(ProjectSkills::new_id());
    commands.push_back({{"op", "create_table"}, {"id", tables.back()}, {"name", "Dataset " + std::to_string(i)}});
  }
  ASSERT_TRUE(call("project.apply", {{"handle", project().project()->handle}, {"expected_revision", 0},
      {"commands", commands}}).is_object());
  int64_t revision = 1;
  const Json interface = {{"inputs", Json::object()}, {"outputs", Json::object()}, {"parameters", Json::array()}};
  for (int group = 0; group < 8; ++group) {
    const auto child = ProjectSkills::new_id();
    Json steps = Json::array();
    for (int i = 0; i < 100; ++i) {
      steps.push_back({{"id", "data_" + std::to_string(i)}, {"kind", "table"}, {"ref", {{"table", tables[size_t(group * 100 + i)]}}}});
    }
    const Json document = {{"format", "stk.workflow/2"}, {"steps", steps}, {"ui", Json::object()}, {"interface", interface}};
    ASSERT_TRUE(call("project.workflows.create", {{"handle", project().project()->handle}, {"workflow_id", child},
        {"name", "Data group " + std::to_string(group)}, {"document", document}, {"expected_revision", revision++}}).is_object());
    child_steps.push_back({{"id", "group_" + std::to_string(group)}, {"kind", "workflow"}, {"ref", {{"workflow", child}}}});
  }
  const auto source = ProjectSkills::new_id(), id = ProjectSkills::new_id();
  const Json document = {{"format", "stk.workflow/2"}, {"steps", child_steps}, {"ui", Json::object()}, {"interface", interface}};
  ASSERT_TRUE(call("project.workflows.create", {{"handle", project().project()->handle}, {"workflow_id", source},
      {"name", "Many datasets"}, {"document", document}, {"expected_revision", revision++}}).is_object());
  project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills->write("publish_workflow", {{"workflow_id", source}, {"project_skill_id", id}, {"create", true},
      {"name", "Many datasets"}, {"description", "Explicit table references"}, {"expected_revision", revision++}}, skills->epoch()));
  ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_FALSE(skills->uncertain()) << skills->error();
  f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, 1280, 1600, 1);
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
  ASSERT_TRUE(area.editor().load_workspace_state({{"version", 1}, {"project_view", true},
      {"project_id", project().project()->id}, {"selected_id", id}}));
  f.screen.set_maximized(&area); ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_workflow", revision));
  const auto *field = f.screen.ui()->find("project_skill_workflow_bindings"); ASSERT_NE(field, nullptr);
  const auto text = field->string.get();
  ASSERT_GT(text.size(), 65536u); EXPECT_GE(field->text_opts.max_length, text.size());
  EXPECT_EQ(Json::parse(text).at("tables").size(), 800u);
  ASSERT_NO_FATAL_FAILURE(click("project_skill_workflow_dependencies"));
  const auto *list = f.screen.ui()->find("project_skill_dependencies_tables"); ASSERT_NE(list, nullptr);
  ASSERT_TRUE(list->list); EXPECT_EQ(list->list->count, 800); EXPECT_LE(list->list->rows, 5);
  EXPECT_NE(list->list->text(799).find("Dataset "), std::string::npos);
  size_t visible_widgets = 0;
  for (const auto &block : f.screen.ui()->blocks()) { visible_widgets += block->widgets().size(); }
  EXPECT_LT(visible_widgets, 100u);
  field = f.screen.ui()->find("project_skill_workflow_bindings"); ASSERT_NE(field, nullptr);
  field->string.set(text + " unfinished"); f.drv->frame();
  ASSERT_FALSE(f.screen.ui()->find("project_skill_create_workflow")->enabled);
  f.screen.ui()->find("project_skill_workflow_bindings")->string.set(text); f.drv->frame();
  EXPECT_TRUE(f.screen.ui()->find("project_skill_create_workflow")->enabled);
  const auto workspace = area.editor().save_workspace_state();
  EXPECT_EQ(workspace.at("binding_drafts").begin().value(), text);
  EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(ProjectSkillsPython, RetainedWorkflowPublishCannotFollowAnotherSourceSelection)
{
  ASSERT_NO_FATAL_FAILURE(create_workflow_source(ProjectSkills::new_id(), ProjectSkills::new_id()));
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
  f.screen.set_maximized(&area); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("skills_project_tab"));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_workflow_publish"));
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_workflow_sources", 2));
  const auto select = f.screen.ui()->find("project_skill_workflow_sources")->list->selected.set;
  select(0); ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_workflow_publish_new", 2));
  const auto retained = f.screen.ui()->find("project_skill_workflow_publish_new")->on_click;
  select(1); ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_workflow_publish_new", 2));
  retained(); f.drv->frame(); loop.run_ready();
  EXPECT_EQ(project().project()->revision, 2);
  EXPECT_EQ(call("project.skills.list", {{"handle", project().project()->handle}}).at("total"), 0);
}

TEST_F(ProjectSkillsPython, PublishesGlobalAnalysisInOneClickAndCopiesIntoAnotherProject)
{
  const auto id = user_analysis_skill(); ASSERT_FALSE(id.empty());
  const auto original = saved_skill(id);
  ASSERT_NO_FATAL_FAILURE(show_project_skill(id));
  const auto viewer = store().viewer().save_workspace_state();
  const auto retained = f.screen.ui()->find("project_skill_publish_global")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("project_skill_publish_global"));
  ASSERT_NO_FATAL_FAILURE(settle_publication());
  auto &library = store().skills();
  ASSERT_TRUE(library.publication().is_object()) << library.publication_error();
  EXPECT_EQ(project().project()->revision, 2); EXPECT_EQ(saved_skill(id), original);
  const auto receipt = library.publication();
  retained(); f.drv->frame(); loop.run_ready();
  EXPECT_EQ(library.publication(), receipt); EXPECT_FALSE(library.publication_busy());
  const auto ref = io::get_string(receipt.at("skill"), "ref");
  ASSERT_NO_FATAL_FAILURE(select_library(ref));
  EXPECT_EQ(library.detail().at("source"), "user");
  EXPECT_EQ(library.detail().at("entry").at("kind"), "graph.document");
  EXPECT_EQ(library.detail().at("availability").at("status"), "unchecked");
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(project().create(dir.str() + "/target", "Target")); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_pin", 0));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_pin"));
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_create_analysis", 1));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_create_analysis"));
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_open_analysis", 2));
  const auto analyses = call("project.analyses.list", {{"handle", project().project()->handle}}).at("analyses");
  ASSERT_EQ(analyses.size(), 1u);
  const auto copied = call("project.analyses.get", {{"handle", project().project()->handle}, {"analysis_id", analyses[0].at("id")}})
      .at("analysis").at("document");
  EXPECT_EQ(copied.at("parameters").at("large"), INT64_C(9007199254740993));
  EXPECT_TRUE(copied.at("outputs").empty());
  EXPECT_EQ(store().viewer().save_workspace_state(), viewer);
}

TEST_F(ProjectSkillsPython, GlobalWorkflowChineseRequiresExplicitForeignDataMapping)
{
  const auto table = ProjectSkills::new_id(), source = ProjectSkills::new_id(), id = ProjectSkills::new_id();
  ASSERT_TRUE(call("project.apply", {{"handle", project().project()->handle}, {"expected_revision", 0},
      {"commands", {{{"op", "create_table"}, {"id", table}, {"name", "Source data"}}}}}).is_object());
  const Json document = {{"format", "stk.workflow/1"}, {"ui", Json::object()},
      {"steps", {{{"id", "data"}, {"kind", "table"}, {"ref", {{"table", table}}}}}}};
  ASSERT_TRUE(call("project.workflows.create", {{"handle", project().project()->handle}, {"workflow_id", source},
      {"name", "Data method"}, {"document", document}, {"expected_revision", 1}}).is_object());
  project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills->write("publish_workflow", {{"workflow_id", source}, {"project_skill_id", id}, {"create", true},
      {"name", "Data method"}, {"description", "Explicit data references"}, {"expected_revision", 2}}, skills->epoch()));
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_NO_FATAL_FAILURE(show_project_skill(id, "zh_CN", 2, 560));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_publish_global"));
  ASSERT_NO_FATAL_FAILURE(settle_publication());
  auto &library = store().skills(); ASSERT_TRUE(library.publication().is_object()) << library.publication_error();
  EXPECT_EQ(project().project()->revision, 3);
  const auto ref = io::get_string(library.publication().at("skill"), "ref");
  ASSERT_NO_FATAL_FAILURE(select_library(ref));
  EXPECT_EQ(library.detail().at("entry").at("kind"), "workflow.document");
  EXPECT_EQ(library.detail().at("method").at("data_dependencies").at("tables"), 1);
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(project().create(dir.str() + "/target", "Target")); ASSERT_NO_FATAL_FAILURE(settle());
  const auto target = ProjectSkills::new_id();
  ASSERT_TRUE(call("project.apply", {{"handle", project().project()->handle}, {"expected_revision", 0},
      {"commands", {{{"op", "create_table"}, {"id", target}, {"name", "Target data"}}}}}).is_object());
  project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_pin", 1));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_pin"));
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_workflow_bindings", 2));
  const auto *mapping = f.screen.ui()->find("project_skill_workflow_bindings"); ASSERT_NE(mapping, nullptr);
  auto bindings = Json::parse(mapping->string.get()); EXPECT_EQ(bindings.at("tables").at(table), "");
  ASSERT_FALSE(f.screen.ui()->find("project_skill_create_workflow")->enabled);
  bindings["tables"][table] = target; mapping->string.set(bindings.dump(2)); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("project_skill_create_workflow"));
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_open_workflow", 3));
  const auto list = call("project.workflows.list", {{"handle", project().project()->handle}}).at("workflows");
  ASSERT_EQ(list.size(), 1u);
  const auto copied = call("project.workflows.get", {{"handle", project().project()->handle}, {"workflow_id", list[0].at("id")}})
      .at("workflow").at("document");
  EXPECT_EQ(copied.at("steps").at(0).at("ref").at("table"), target);
}

TEST_F(ProjectSkillsPython, GlobalLostReceiptCanBeCheckedAfterSourceProjectCloses)
{
  const auto id = user_analysis_skill(); ASSERT_FALSE(id.empty());
  auto &library = store().skills(); library.sync();
  const auto digest = io::get_string(skills->selected().at("active"), "content_sha256");
  ASSERT_NO_FATAL_FAILURE(mode("global_receipt"));
  ASSERT_TRUE(library.publish(*skills, "exact", skills->epoch(), digest));
  const auto publication_id = library.publication_pending().at("publication_id");
  ASSERT_NO_FATAL_FAILURE(settle_publication());
  ASSERT_TRUE(library.publication_uncertain());
  EXPECT_FALSE(library.publish(*skills, "exact", skills->epoch(), digest));
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_NO_FATAL_FAILURE(mode("global_query_conflict"));
  ASSERT_TRUE(library.check_publication()); ASSERT_NO_FATAL_FAILURE(settle_publication());
  EXPECT_TRUE(library.publication_uncertain());
  EXPECT_EQ(library.publication_pending().at("publication_id"), publication_id);
  EXPECT_FALSE(library.publication_error().empty());
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_TRUE(library.check_publication()); ASSERT_NO_FATAL_FAILURE(settle_publication());
  EXPECT_FALSE(library.publication_uncertain()); ASSERT_TRUE(library.publication().is_object()) << library.publication_error();
  EXPECT_EQ(library.publication().at("publication_id"), publication_id);
  EXPECT_EQ(library.publication().at("skill").at("version"), 1);
  EXPECT_FALSE(project().project());
}

TEST_F(ProjectSkillsPython, GlobalConflictOffersAnExplicitNewVersionWithoutChangingProjectHistory)
{
  const auto id = user_analysis_skill(); ASSERT_FALSE(id.empty());
  const auto original = saved_skill(id);
  ASSERT_NO_FATAL_FAILURE(show_project_skill(id));
  ASSERT_NO_FATAL_FAILURE(mode("global_conflict"));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_publish_global"));
  ASSERT_NO_FATAL_FAILURE(settle_publication());
  auto &library = store().skills(); EXPECT_FALSE(library.publication_uncertain());
  ASSERT_NO_FATAL_FAILURE(wait_for("project_skill_publish_global_new_version", 2));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_publish_global_new_version"));
  ASSERT_NO_FATAL_FAILURE(settle_publication());
  ASSERT_TRUE(library.publication().is_object()) << library.publication_error();
  EXPECT_EQ(library.publication().at("mode"), "new_version");
  EXPECT_GT(library.publication().at("skill").at("version").get<int64_t>(), 1);
  EXPECT_EQ(saved_skill(id), original); EXPECT_EQ(project().project()->revision, 2);
}

TEST_F(ProjectSkillsPython, CatalogDetailRejectsSameRefWithChangedDigestOrSource)
{
  auto &library = store().skills(); library.sync(); ASSERT_TRUE(library.ensure_loaded());
  ASSERT_TRUE(loop.pump_until([&] { return !library.loading(); }, 30));
  ASSERT_NO_FATAL_FAILURE(mode("catalog_digest"));
  ASSERT_TRUE(library.select("stk.muferro.energy_trace@1"));
  ASSERT_TRUE(loop.pump_until([&] { return !library.detail_loading(); }, 30));
  EXPECT_TRUE(library.detail().is_null()); EXPECT_FALSE(library.detail_error().empty());
  ASSERT_NO_FATAL_FAILURE(mode("catalog_source")); ASSERT_TRUE(library.refresh());
  ASSERT_TRUE(loop.pump_until([&] { return !library.loading() && !library.detail_loading(); }, 30));
  EXPECT_TRUE(library.detail().is_null()); EXPECT_FALSE(library.detail_error().empty());
  ASSERT_NO_FATAL_FAILURE(mode("")); ASSERT_TRUE(library.refresh());
  ASSERT_TRUE(loop.pump_until([&] { return !library.loading() && !library.detail_loading(); }, 30));
  ASSERT_TRUE(library.detail().is_object()) << library.detail_error();
  EXPECT_EQ(library.detail().at("source"), "builtin"); EXPECT_EQ(project().project()->revision, 0);
}

TEST_F(ProjectSkillsPython, SkillsChangedRefreshesTheVisibleLibraryAfterExternalPublication)
{
  const auto id = user_analysis_skill(); ASSERT_FALSE(id.empty());
  auto &library = store().skills(); library.sync(); ASSERT_TRUE(library.ensure_loaded());
  ASSERT_TRUE(loop.pump_until([&] { return !library.loading(); }, 30));
  const auto before = library.total();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
  f.screen.set_maximized(&area); f.drv->frame();
  ASSERT_TRUE(call("project.skills.publish_global", {{"handle", project().project()->handle}, {"project_skill_id", id},
      {"content_sha256", skills->selected().at("active").at("content_sha256")}, {"expected_revision", 2},
      {"publication_id", ProjectSkills::new_id()}, {"mode", "exact"}}).is_object());
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return !library.loading() && library.total() == before + 1; }, 30));
  EXPECT_EQ(project().project()->revision, 2);
}

TEST_F(ProjectSkillsPython, GlobalLargeJsonDefaultHasBoundedVisiblePreview)
{
  const auto source = ProjectSkills::new_id(), id = ProjectSkills::new_id();
  const Json document = {{"format", "stk.analysis-document/1"},
      {"graph", {{"schema", "stk.graph/1"},
          {"nodes", {{{"id", "source"}, {"type", "missing.source.node@1"}, {"params", {{"binding", "data"}}}}}},
          {"outputs", {{"view", "source.payload"}}},
          {"parameters", {{{"name", "config"}, {"type", "json"}, {"default", {{"payload", std::string(32000, 'x')}}}}}}}},
      {"parameters", Json::object()}, {"outputs", Json::array()}};
  ASSERT_TRUE(call("project.analyses.create", {{"handle", project().project()->handle}, {"analysis_id", source},
      {"name", "Large default"}, {"document", document}, {"expected_revision", 0}}).is_object());
  project().refresh(); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills->write("publish_analysis", {{"analysis_id", source}, {"project_skill_id", id}, {"create", true},
      {"name", "Large default"}, {"description", "Bounded user interface"}, {"expected_revision", 1}}, skills->epoch()));
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_NO_FATAL_FAILURE(show_project_skill(id));
  ASSERT_NO_FATAL_FAILURE(click("project_skill_publish_global"));
  ASSERT_NO_FATAL_FAILURE(settle_publication());
  auto &library = store().skills(); ASSERT_TRUE(library.publication().is_object()) << library.publication_error();
  ASSERT_NO_FATAL_FAILURE(select_library(io::get_string(library.publication().at("skill"), "ref")));
  ASSERT_EQ(library.detail().at("parameters").at(0).at("default").at("payload").get<std::string>().size(), 32000u);
  for (int i = 0; i < 3; ++i) {
    f.drv->frame();
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &widget : block->widgets()) { EXPECT_LT(widget.text.size(), 2048u); }
    }
  }
  EXPECT_EQ(project().project()->revision, 2);
}

TEST_F(ProjectSkillsPython, RejectsSummaryDriftAndOldOpenEpoch)
{
  const auto item = first_skill(); const auto id = ProjectSkills::new_id();
  const auto epoch = skills->epoch();
  ASSERT_TRUE(skills->write("pin", pin_params(item, id), epoch)); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_NO_FATAL_FAILURE(mode("summary"));
  ASSERT_TRUE(skills->select(id)); ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_FALSE(skills->current()); EXPECT_FALSE(skills->error().empty());
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(settle()); skills->sync();
  ASSERT_TRUE(project().open(dir.str() + "/project")); ASSERT_NO_FATAL_FAILURE(settle()); skills->sync();
  EXPECT_NE(skills->epoch(), epoch);
  EXPECT_FALSE(skills->write("pin", pin_params(item, ProjectSkills::new_id()), epoch));
  EXPECT_EQ(project().project()->revision, 1);
}

TEST_F(ProjectSkillsPython, EditorPinsWithOneClickAndRejectsItsOldButton)
{
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorSkills));
  f.screen.set_maximized(&area); f.drv->frame();
  ASSERT_TRUE(loop.pump_until([&] { return !store().skills().loading(); }, 30));
  ASSERT_TRUE(store().skills().select("stk.muferro.energy_trace@1"));
  ASSERT_TRUE(loop.pump_until([&] { return !store().skills().detail_loading(); }, 30)); f.drv->frame();
  const auto *button = f.screen.ui()->find("project_skill_pin"); ASSERT_NE(button, nullptr); ASSERT_TRUE(button->enabled);
  const auto old_button = button->on_click;
  const auto [x, y] = f.widget_center("project_skill_pin"); f.drv->click(x, y); f.drv->frame();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto *create = f.screen.ui()->find("project_skill_create_analysis");
    return create && create->enabled;
  }, 30));
  EXPECT_EQ(project().project()->revision, 1);
  const auto state = area.editor().save_workspace_state();
  EXPECT_TRUE(state.at("project_view").get<bool>()); EXPECT_EQ(state.at("project_id"), project().project()->id);
  EXPECT_FALSE(state.at("selected_id").get<std::string>().empty());
  const auto sent = client->stats().calls_sent; old_button(); f.drv->frame(); loop.run_ready();
  EXPECT_EQ(client->stats().calls_sent, sent); EXPECT_EQ(project().project()->revision, 1);
}

TEST_F(ProjectSkillsPython, UpgradeRestoreAndWorkspaceEnglishAtOneScale)
{
  ASSERT_NO_FATAL_FAILURE(upgrade_restore("en", 1, 1280));
}
TEST_F(ProjectSkillsPython, UpgradeRestoreAndWorkspaceChineseAtOneScale)
{
  ASSERT_NO_FATAL_FAILURE(upgrade_restore("zh_CN", 1, 560));
}
TEST_F(ProjectSkillsPython, UpgradeRestoreAndWorkspaceEnglishAtTwoScale)
{
  ASSERT_NO_FATAL_FAILURE(upgrade_restore("en", 2, 560));
}
TEST_F(ProjectSkillsPython, UpgradeRestoreAndWorkspaceChineseAtTwoScale)
{
  ASSERT_NO_FATAL_FAILURE(upgrade_restore("zh_CN", 2, 1280));
}
}  // namespace
}  // namespace stk::app
