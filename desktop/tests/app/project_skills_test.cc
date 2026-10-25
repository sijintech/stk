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

// All SQLite edits and schema checks remain real. Alter only an already committed write receipt
// or a read's version summary, to check that the native browser refuses inconsistent observations.
constexpr const char *kSkillBridge = R"PY(
import copy
from pathlib import Path
import sys
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main
from suan.skills import catalog
control = Path(sys.argv.pop(1))
original_catalog = catalog.load_catalog
def load_catalog(*args, **kwargs):
    if control.exists() and control.read_text(encoding='utf-8') == 'catalog_absent':
        raise catalog.SkillCatalogError('not_found', 'Test catalog is unavailable')
    kwargs['directories'] = [('builtin', catalog._builtin_root()), ('test', control.parent / 'definitions')]
    return original_catalog(*args, **kwargs)
catalog.load_catalog = load_catalog
original = Bridge.send
def send(self, message, method=None):
    mode = control.read_text(encoding='utf-8') if control.exists() else ''
    if 'result' in message:
        if method == 'project.skills.pin' and mode == 'receipt':
            message = copy.deepcopy(message)
            message['result']['record_id'] = '00000000-0000-4000-8000-000000000000'
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
      ADD_FAILURE() << method << " failed"; return nullptr;
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
