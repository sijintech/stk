/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/project_state.hh"
#include "stk/app/skill_catalog.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;

TEST(SkillCatalog, ParsesRowsDefensivelyAndLocalizesText)
{
  const Json result = {{"skills", Json::array({
      {{"id", "stk.a"}, {"version", 2}, {"ref", "stk.a@2"}, {"content_sha256", std::string(64, 'a')},
       {"entry", {{"kind", "graph.preset"}, {"preset", "p"}}}, {"title", {{"en", "A"}, {"zh_CN", "甲"}}},
       {"summary", {{"en", "S"}}},
       {"availability", {{"status", "limited"}, {"unavailable_outputs", {"energy", 3}},
                         {"issues", Json::array({Json::object(), Json::object()})}}}},
      {{"id", "missing.ref"}, {"version", 1}},
      {{"id", "stk.b"}, {"version", 0}, {"ref", "stk.b@0"}},
      "not an object"})}};
  const auto rows = parse_skill_summaries(result);
  ASSERT_EQ(rows.size(), 1u);
  EXPECT_EQ(rows[0].ref, "stk.a@2"); EXPECT_EQ(rows[0].version, 2); EXPECT_EQ(rows[0].preset, "p");
  EXPECT_EQ(rows[0].status, "limited"); EXPECT_EQ(rows[0].issue_count, 2u);
  EXPECT_EQ(rows[0].unavailable_outputs, std::vector<std::string>{"energy"});
  EXPECT_EQ(skill_text(rows[0].title, "zh_CN"), "甲");
  EXPECT_EQ(skill_text(rows[0].title, "en"), "A");
  EXPECT_EQ(skill_text(rows[0].summary, "zh_CN"), "S");  // falls back to English
  EXPECT_EQ(skill_text(Json("plain"), "zh_CN"), "plain");
  EXPECT_TRUE(parse_skill_summaries(Json::array()).empty());
  EXPECT_TRUE(parse_skill_summaries({{"skills", "x"}}).empty());
}

TEST(SkillCatalog, WithoutBridgeNothingIsRequested)
{
  wmtest::AppFixture f;
  auto &skills = f.shell->store().skills();
  skills.sync();
  EXPECT_FALSE(skills.bridge_ready()); EXPECT_FALSE(skills.supported());
  EXPECT_FALSE(skills.ensure_loaded()); EXPECT_FALSE(skills.refresh()); EXPECT_FALSE(skills.search("x"));
  EXPECT_FALSE(skills.select("stk.a@1")); EXPECT_FALSE(skills.loading());
  ASSERT_TRUE(f.area("a2").set_tab_type(0, kEditorSkills));
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("skills_list"), nullptr);
}

class SkillsCatalogPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"skills-catalog"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;
  std::string python;

  SkillCatalogState &skills() { return f.shell->store().skills(); }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  EditorArea &area() { return f.area("a2"); }
  void SetUp() override
  {
    python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
  }
  void start(std::vector<std::string> wrapper = {})
  {
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.strict = options.validate = true;
    if (!wrapper.empty()) {
      std::string error;
      const auto resolved = bridge::find_python(options.python, error);
      ASSERT_TRUE(resolved) << error;
      options.command = {*resolved, std::string(STK_REPO_ROOT) + "/desktop/tests/bridge/skills_bridge.py"};
      options.command.insert(options.command.end(), wrapper.begin(), wrapper.end());
      for (const auto &arg : {std::string("--stdio"), std::string("--state-dir"), options.state_dir,
                              std::string("--cache-dir"), options.cache_dir, std::string("--strict")}) {
        options.command.push_back(arg);
      }
    }
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)); loop.run_ready();
    f.shell->store().set_bridge(client.get());
  }
  void open()
  {
    ASSERT_TRUE(area().set_tab_type(0, kEditorSkills));
    f.screen.set_maximized(&area()); f.drv->frame();
  }
  void settle()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !skills().loading() && !skills().detail_loading(); }, 30));
    f.drv->frame();
  }
  void write(const std::string &name, const std::string &text)
  {
    std::filesystem::create_directories(core::path_from_utf8(dir.str() + "/definitions"));
    std::ofstream file(core::path_from_utf8(dir.str() + "/definitions/" + name), std::ios::binary);
    file << text;
    ASSERT_TRUE(bool(file));
  }
  void TearDown() override
  {
    EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0);
    EXPECT_FALSE(f.shell->store().viewer().payload());
    EXPECT_FALSE(f.shell->store().project().project());
    f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(SkillsCatalogPython, ListsSelectsAndShowsTheContractWithoutRunningAnything)
{
  ASSERT_NO_FATAL_FAILURE(start());
  ASSERT_NO_FATAL_FAILURE(open());
  ASSERT_TRUE(skills().loading());  // the first draw requests the first page once
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills().error().empty()) << skills().error();
  ASSERT_EQ(skills().skills().size(), 3u);
  EXPECT_EQ(skills().total(), 3); EXPECT_FALSE(skills().has_next()); EXPECT_EQ(skills().problem_count(), 0);
  EXPECT_EQ(skills().skills()[0].ref, "stk.muferro.domains@1");
  const auto *list = widget("skills_list");
  ASSERT_NE(list, nullptr); ASSERT_TRUE(list->list); EXPECT_EQ(list->list->count, 3);
  EXPECT_EQ(list->list->selected.value(), -1);
  EXPECT_FALSE(widget("skills_previous")->enabled); EXPECT_FALSE(widget("skills_next")->enabled);
  EXPECT_EQ(widget("skills_inputs"), nullptr);
  const auto sent = client->stats().calls_sent;
  f.drv->frame(); f.drv->frame();
  EXPECT_EQ(client->stats().calls_sent, sent);  // drawing never re-requests a loaded page

  list = widget("skills_list");  // frames rebuild widgets: never reuse a pointer across them
  ASSERT_NE(list, nullptr); ASSERT_TRUE(list->list);
  list->list->selected.assign(2);  // the list binding selects by ref
  EXPECT_EQ(skills().selected(), "stk.visualize.scalar_volume@1");
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills().detail().is_object()) << skills().detail_error();
  const auto &skill = skills().detail();
  EXPECT_EQ(io::get_string(skill, "ref"), "stk.visualize.scalar_volume@1");
  EXPECT_EQ(io::get_string(skill.at("entry"), "operation"), "graph.evaluate");
  EXPECT_EQ(skill.at("inputs").at(0).at("name"), "data");
  EXPECT_EQ(skill.at("parameters").at(2).at("default"), 0);  // the component default stays an integer
  EXPECT_TRUE(skill.at("parameters").at(2).at("default").is_number_integer());
  f.drv->frame();
  EXPECT_EQ(widget("skills_list")->list->selected.value(), 2);
  for (const auto *key : {"skills_inputs", "skills_parameters", "skills_outputs", "skills_dependencies", "skills_examples"}) {
    EXPECT_NE(widget(key), nullptr) << key;
  }
  // Selecting the shown skill again does not resend; a new selection replaces the detail.
  EXPECT_FALSE(skills().select("stk.visualize.scalar_volume@1"));
  EXPECT_FALSE(skills().select("stk.no.such@1"));
  ASSERT_TRUE(skills().select("stk.muferro.domains@1"));
  EXPECT_TRUE(skills().detail().is_null());
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_EQ(io::get_string(skills().detail(), "ref"), "stk.muferro.domains@1");
}

TEST_F(SkillsCatalogPython, SearchPagesAndKeepsOnlyTheLatestReply)
{
  ASSERT_NO_FATAL_FAILURE(start());
  ASSERT_NO_FATAL_FAILURE(open());
  ASSERT_NO_FATAL_FAILURE(settle());
  const auto type_and_search = [&](const char *text) {
    // Widgets are rebuilt every frame: look them up again each time.
    const auto *query = widget("skills_query"); ASSERT_NE(query, nullptr);
    query->string.assign(text);
    widget("skills_search")->on_click(); ASSERT_NO_FATAL_FAILURE(settle());
  };
  ASSERT_NO_FATAL_FAILURE(type_and_search("MUFERRO"));
  EXPECT_EQ(skills().query(), "MUFERRO"); EXPECT_EQ(skills().total(), 2);
  ASSERT_NO_FATAL_FAILURE(type_and_search("no such skill"));
  EXPECT_TRUE(skills().skills().empty()); EXPECT_EQ(skills().total(), 0);
  // Two requests in flight: only the later one may be applied.
  ASSERT_TRUE(skills().search("energy_out"));
  ASSERT_TRUE(skills().search("铁电"));
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_EQ(skills().skills().size(), 1u);
  EXPECT_EQ(skills().query(), "铁电"); EXPECT_EQ(skills().skills()[0].id, "stk.muferro.domains");
  ASSERT_TRUE(skills().search(""));
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_EQ(skills().total(), 3); EXPECT_FALSE(skills().next_page()); EXPECT_FALSE(skills().previous_page());
  EXPECT_TRUE(skills().search(std::string(SkillCatalogState::kMaxQuery + 50, 'x')));  // clamped, still valid
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_TRUE(skills().error().empty()) << skills().error();
  EXPECT_EQ(skills().query().size(), SkillCatalogState::kMaxQuery);
  std::string chinese;
  for (int i = 0; i < 100; ++i) { chinese += "铁"; }  // 300 bytes; a byte cut at 200 would split a character
  ASSERT_TRUE(skills().search(chinese));
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_TRUE(skills().error().empty()) << skills().error();
  EXPECT_EQ(skills().query().size(), 198u);
  EXPECT_EQ(skills().total(), 0);
}

TEST_F(SkillsCatalogPython, BridgeRestartClearsTheSelectionAndReloads)
{
  ASSERT_NO_FATAL_FAILURE(start());
  ASSERT_NO_FATAL_FAILURE(open());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills().search("energy"));
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_EQ(skills().total(), 2);
  ASSERT_TRUE(skills().select("stk.muferro.energy_trace@1"));
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills().detail().is_object());
  const auto pid = client->bridge_pid();
  client->shutdown_bridge();
  ASSERT_TRUE(loop.pump_until([&] { return client->state() == bridge::BridgeState::Ready && client->bridge_pid() != 0 &&
      client->bridge_pid() != pid; }, 60));
  f.drv->frame();
  EXPECT_TRUE(skills().selected().empty()); EXPECT_TRUE(skills().detail().is_null());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills().loaded());
  EXPECT_EQ(skills().query(), "energy"); EXPECT_EQ(skills().total(), 2);  // the applied query is kept
}

TEST_F(SkillsCatalogPython, RepliesForAnotherBridgeAreDiscardedAndReloaded)
{
  ASSERT_NO_FATAL_FAILURE(start());
  ASSERT_NO_FATAL_FAILURE(open());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills().select("stk.muferro.domains@1"));
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(skills().refresh());  // list and definition in flight
  ASSERT_TRUE(skills().loading()); ASSERT_TRUE(skills().detail_loading());
  f.shell->store().set_bridge(nullptr);
  ASSERT_TRUE(loop.pump_until([&] { return !skills().loading() && !skills().detail_loading(); }, 30));
  EXPECT_FALSE(skills().loaded()); EXPECT_TRUE(skills().skills().empty());
  EXPECT_TRUE(skills().selected().empty()); EXPECT_TRUE(skills().detail().is_null());
  f.drv->frame();
  EXPECT_FALSE(skills().bridge_ready()); EXPECT_EQ(widget("skills_list"), nullptr);
  f.shell->store().set_bridge(client.get());
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_EQ(skills().total(), 3);
}

TEST_F(SkillsCatalogPython, OlderBridgeShowsTheCatalogAsUnavailable)
{
  ASSERT_NO_FATAL_FAILURE(start({"legacy"}));
  ASSERT_NO_FATAL_FAILURE(open());
  EXPECT_TRUE(skills().bridge_ready()); EXPECT_FALSE(skills().supported());
  EXPECT_FALSE(skills().loading()); EXPECT_EQ(widget("skills_list"), nullptr);
  EXPECT_EQ(widget("skills_query"), nullptr);
  bool explained = false;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &w : block->widgets()) { explained |= w.text.find("does not provide the skill catalog") != std::string::npos; }
  }
  EXPECT_TRUE(explained);
}

TEST_F(SkillsCatalogPython, BrokenDefinitionsAndMissingModulesAreExplained)
{
  ASSERT_NO_FATAL_FAILURE(write("broken.json", "{\"schema\": "));
  ASSERT_NO_FATAL_FAILURE(write("test.fixture.limited.json", R"({
    "schema": "stk.skill/1", "id": "test.fixture.limited", "version": 1,
    "title": {"en": "Fixture with a missing module"}, "summary": {"en": "Energy plot needs a module that is absent."},
    "entry": {"kind": "graph.preset", "preset": "energy-plot"},
    "dependencies": {"python": [{"module": "stk_test_module_that_is_not_installed", "outputs": ["energy"],
                                 "purpose": {"en": "Fixture only."}}]}})"));
  ASSERT_NO_FATAL_FAILURE(start({"catalog", dir.str() + "/definitions"}));
  ASSERT_NO_FATAL_FAILURE(open());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_EQ(skills().skills().size(), 4u);
  EXPECT_EQ(skills().problem_count(), 1);
  EXPECT_EQ(io::get_string(skills().problems().at(0), "code"), "invalid_json");
  EXPECT_EQ(io::get_string(skills().problems().at(0), "file"), "broken.json");
  EXPECT_NE(widget("skills_problems"), nullptr);
  const auto &limited = skills().skills()[3];
  EXPECT_EQ(limited.ref, "test.fixture.limited@1"); EXPECT_EQ(limited.status, "limited");
  EXPECT_EQ(limited.unavailable_outputs, std::vector<std::string>{"energy"});
  ASSERT_TRUE(skills().select(limited.ref));
  ASSERT_NO_FATAL_FAILURE(settle());
  const auto &issues = skills().detail().at("availability").at("issues");
  ASSERT_EQ(issues.size(), 1u);
  EXPECT_EQ(issues.at(0).at("code"), "missing_module");
  EXPECT_EQ(skills().detail().at("dependencies").at("python").at(0).at("available"), false);
}

TEST_F(SkillsCatalogPython, WorkspaceOpensTheSharedLibraryWithoutAProject)
{
  ASSERT_NO_FATAL_FAILURE(start());
  auto &home = f.area("a1");
  ASSERT_TRUE(home.set_tab_type(0, kEditorWorkspace));
  f.screen.set_maximized(&home); f.drv->frame();
  const auto *button = widget("workspace_skills");
  ASSERT_NE(button, nullptr); ASSERT_TRUE(button->enabled);
  const auto [x, y] = f.widget_center("workspace_skills");
  f.drv->click(x, y); f.screen.run_deferred(); f.drv->frame();
  auto *target = dynamic_cast<EditorArea *>(f.screen.maximized());
  ASSERT_NE(target, nullptr);
  EXPECT_EQ(target->editor().type().id, kEditorSkills);
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_EQ(skills().skills().size(), 3u);
  ASSERT_NE(widget("project_workspace"), nullptr);  // the way back
}

}  // namespace
}  // namespace stk::app
