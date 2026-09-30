/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_discussion.hh"
#include "stk/app/project_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
using Result = bridge::Result<Json>;

class SavedReviewPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"saved-review-app"};
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;
  Json draft;

  ProjectState &state() { return f.shell->store().project(); }

  void settled()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !state().busy() && !state().discussion().busy(); }, 30))
        << client->bridge_log().text();
  }

  void call(const std::string &method, Json params, Json &out)
  {
    std::optional<Result> result;
    client->call(method, std::move(params)).then([&](auto value) { result = std::move(value); });
    ASSERT_TRUE(loop.pump_until([&] { return result.has_value(); })) << client->bridge_log().text();
    ASSERT_TRUE(result->ok()) << result->error().describe();
    out = result->value();
  }

  void queue_open(wm::Screen *screen, std::optional<Result> &result,
                  std::function<bool()> valid = [] { return true; })
  {
    f.shell->open_saved_review(screen, state().project()->handle, 0, draft, state().review_generation(),
        std::move(valid), [&result](auto value) { result = std::move(value); });
  }

  void empty_review()
  {
    EXPECT_TRUE(state().saved_review().empty());
    EXPECT_FALSE(state().review());
    EXPECT_EQ(state().review_source(), "[]");
    EXPECT_EQ(state().project()->revision, 0);
    EXPECT_TRUE(state().tables().empty());
  }

  void fill_tabs(EditorArea &area)
  {
    while (area.tab_count() < 16) { ASSERT_TRUE(area.add_tab(kEditorLogs, false)); }
  }

  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON to run saved-review integration"; }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge";
    options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = "fixture-model";
    options.executor = loop.executor();
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    f.shell->store().set_bridge(client.get());
    state().sync();
    ASSERT_TRUE(loop.pump_until([&] { return state().ready(); }, 60)) << client->bridge_log().text();
    ASSERT_TRUE(state().create(dir.str() + "/project", "Saved Review"));
    ASSERT_NO_FATAL_FAILURE(settled());
    ASSERT_TRUE(state().loaded());
    state().set_review_source(Json::array({{{"op", "create_table"}, {"name", "Proposed cases"}}}).dump());
    ASSERT_TRUE(state().preview());
    ASSERT_NO_FATAL_FAILURE(settled());
    ASSERT_TRUE(state().review()) << state().review_error();
    ASSERT_TRUE(state().save_review("Saved candidate"));
    ASSERT_NO_FATAL_FAILURE(settled());
    draft = state().saved_review();
    ASSERT_FALSE(draft.empty()) << state().drafts_error();
    state().discard_review();
    ASSERT_NO_FATAL_FAILURE(empty_review());
  }

  void TearDown() override
  {
    state().attach(nullptr);
    f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); }
    loop.run_ready();
    EXPECT_EQ(client ? client->stats().schema_violations : 0, 0u);
  }
};

TEST_F(SavedReviewPython, AdoptionWaitsForPreviewAndAppliesTheOriginalDurableReceipt)
{
  Json before;
  ASSERT_NO_FATAL_FAILURE(call("project.history", {{"handle", state().project()->handle}}, before));
  auto accepted = state().request_saved_review(state().project()->handle, 0, draft);
  ASSERT_TRUE(accepted.ok()) << accepted.error().describe();
  EXPECT_EQ(accepted.value().at("draft_id"), draft.at("id"));
  EXPECT_EQ(state().saved_review(), draft);
  EXPECT_EQ(io::canonical_json(io::parse_json(state().review_source())), io::canonical_json(draft.at("commands")));
  EXPECT_FALSE(state().review());
  EXPECT_FALSE(state().busy());
  EXPECT_FALSE(state().apply_review());
  EXPECT_EQ(state().project()->revision, 0);
  EXPECT_TRUE(state().tables().empty());
  Json after;
  ASSERT_NO_FATAL_FAILURE(call("project.history", {{"handle", state().project()->handle}}, after));
  EXPECT_EQ(after, before);
  ASSERT_TRUE(state().preview());
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(state().can_apply_review());
  EXPECT_EQ(state().saved_review().at("id"), draft.at("id"));
  ASSERT_TRUE(state().apply_review());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().saved_review().at("id"), draft.at("id"));
  EXPECT_EQ(state().saved_review().at("status"), "applied");
  ASSERT_EQ(state().tables().size(), 1u);
  EXPECT_EQ(state().tables()[0].id, draft.at("commands")[0].at("id").get<std::string>());
  ASSERT_TRUE(state().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_TRUE(state().tables().empty());
  Json receipt;
  ASSERT_NO_FATAL_FAILURE(call("project.drafts.apply", {{"handle", state().project()->handle},
      {"draft_id", draft.at("id")}, {"expected_revision", 0}}, receipt));
  EXPECT_EQ(receipt.at("replayed"), true);
  EXPECT_EQ(receipt.at("revision"), 1);
  state().refresh();
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_TRUE(state().tables().empty());
}

TEST_F(SavedReviewPython, InvalidForeignTerminalAndOccupiedReviewsNeverReplaceState)
{
  const auto handle = state().project()->handle;
  const auto layout = f.screen.to_json();
  auto rejected = [&](const Json &value, const bridge::ErrorCode code) {
    const auto result = state().request_saved_review(handle, 0, value);
    ASSERT_FALSE(result.ok());
    EXPECT_EQ(result.error().code, code);
    empty_review();
  };
  Json malformed = draft;
  malformed.erase("commands");
  rejected(malformed, bridge::ErrorCode::InvalidParams);
  Json foreign = draft;
  foreign["project_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  rejected(foreign, bridge::ErrorCode::Conflict);
  Json terminal = draft;
  terminal["status"] = "discarded";
  terminal["closed_at"] = "2026-09-30T00:00:00Z";
  rejected(terminal, bridge::ErrorCode::Conflict);
  Json nonfinite = draft;
  nonfinite["commands"][0]["unexpected"] = std::numeric_limits<double>::infinity();
  rejected(nonfinite, bridge::ErrorCode::InvalidParams);
  state().set_review_source("unfinished native input");
  auto occupied = state().request_saved_review(handle, 0, draft);
  ASSERT_FALSE(occupied.ok());
  EXPECT_EQ(occupied.error().code, bridge::ErrorCode::Conflict);
  EXPECT_EQ(state().review_source(), "unfinished native input");
  state().discard_review();
  ASSERT_TRUE(state().request_saved_review(handle, 0, draft).ok());
  occupied = state().request_saved_review(handle, 0, draft);
  ASSERT_FALSE(occupied.ok());
  EXPECT_EQ(occupied.error().code, bridge::ErrorCode::Conflict);
  EXPECT_EQ(state().saved_review(), draft);
  EXPECT_EQ(f.screen.to_json(), layout);
}

TEST_F(SavedReviewPython, DeferredOpenDoesNotOverwriteAReviewEditedAndClearedAfterQueueing)
{
  const auto layout = f.screen.to_json();
  std::optional<Result> result;
  queue_open(&f.screen, result);
  ASSERT_FALSE(result.has_value());
  state().set_review_source("new input that was later cleared");
  state().discard_review();
  f.screen.run_deferred();
  ASSERT_TRUE(result.has_value());
  ASSERT_FALSE(result->ok());
  EXPECT_EQ(result->error().code, bridge::ErrorCode::Conflict);
  empty_review();
  EXPECT_EQ(f.screen.to_json(), layout);
}

TEST_F(SavedReviewPython, DeferredOpenPreservesUncommittedTextInAnotherInstalledWindow)
{
  struct ExtraScreen {
    AppShell &shell;
    wm::Screen screen;
    wmtest::ScreenDriver driver;
    explicit ExtraScreen(AppShell &owner) : shell(owner), driver(screen, 1280, 1000, 1)
    {
      shell.install(screen, nullptr);
      shell.build_default_layout(screen);
    }
    ~ExtraScreen() { shell.forget(screen); }
  } extra(*f.shell);
  auto *area = dynamic_cast<EditorArea *>(extra.screen.find_area("a2"));
  ASSERT_NE(area, nullptr);
  ASSERT_TRUE(area->set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area->editor().show_view("review"));
  extra.screen.set_maximized(area);
  extra.driver.frame();
  ASSERT_NO_FATAL_FAILURE(settled());
  extra.driver.frame();
  const auto *input = extra.screen.ui()->find("a2/main/review_source");
  ASSERT_NE(input, nullptr);
  const auto rect = input->rect;
  const auto layout = f.screen.to_json();
  std::optional<Result> result;
  queue_open(&f.screen, result);
  // Start editing only after navigation was queued, before its final UI turn.
  extra.driver.click(int(rect.cx()), extra.screen.rect().ymax - 1 - int(rect.cy()));
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  extra.driver.key(wm::Key::A, primary);
  extra.driver.key(wm::Key::Unknown, wm::ModNone, "uncommitted second-window input");
  ASSERT_TRUE(extra.screen.ui()->text_input_active());
  ASSERT_NE(extra.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(extra.screen.ui()->edit_state()->text(), "uncommitted second-window input");
  EXPECT_EQ(state().review_source(), "[]");
  f.screen.run_deferred();
  ASSERT_TRUE(result.has_value());
  ASSERT_FALSE(result->ok());
  EXPECT_EQ(result->error().code, bridge::ErrorCode::Busy);
  EXPECT_EQ(extra.screen.ui()->edit_state()->text(), "uncommitted second-window input");
  EXPECT_EQ(f.screen.to_json(), layout);
  empty_review();
}

TEST_F(SavedReviewPython, FullFirstAreaUsesAnotherAreaWithCapacity)
{
  auto *available = &f.area("a2");
  const auto before = available->tab_count();
  for (auto *area : f.screen.areas()) {
    auto *editor = dynamic_cast<EditorArea *>(area);
    ASSERT_NE(editor, nullptr);
    if (editor != available) { ASSERT_NO_FATAL_FAILURE(fill_tabs(*editor)); }
  }
  f.screen.set_maximized(&f.area("a1"));
  std::optional<Result> result;
  queue_open(&f.screen, result);
  f.screen.run_deferred();
  ASSERT_TRUE(result.has_value());
  ASSERT_TRUE(result->ok()) << result->error().describe();
  EXPECT_EQ(available->tab_count(), before + 1);
  EXPECT_EQ(available->editor().type().id, kEditorProject);
  EXPECT_EQ(f.screen.maximized(), available);
  EXPECT_EQ(state().saved_review().at("id"), draft.at("id"));
  EXPECT_FALSE(state().review());
  EXPECT_EQ(state().project()->revision, 0);
  f.drv->frame();
  const auto *tabs = f.screen.ui()->find("a2/main/project_view");
  ASSERT_NE(tabs, nullptr);
  EXPECT_EQ(tabs->index.value(), 1);
}

TEST_F(SavedReviewPython, AllFullAreasRejectWithoutAdoptionButAnExistingProjectTabCanOpen)
{
  for (auto *area : f.screen.areas()) {
    auto *editor = dynamic_cast<EditorArea *>(area);
    ASSERT_NE(editor, nullptr);
    ASSERT_NO_FATAL_FAILURE(fill_tabs(*editor));
  }
  const auto layout = f.screen.to_json();
  const auto generation = state().review_generation();
  std::optional<Result> result;
  queue_open(&f.screen, result);
  f.screen.run_deferred();
  ASSERT_TRUE(result.has_value());
  ASSERT_FALSE(result->ok());
  EXPECT_EQ(result->error().code, bridge::ErrorCode::Unavailable);
  empty_review();
  EXPECT_EQ(state().review_generation(), generation);
  EXPECT_EQ(f.screen.to_json(), layout);
  auto &existing = f.area("a2");
  ASSERT_TRUE(existing.set_tab_type(0, kEditorProject));
  existing.set_active_tab(1);
  result.reset();
  queue_open(&f.screen, result);
  f.screen.run_deferred();
  ASSERT_TRUE(result.has_value());
  ASSERT_TRUE(result->ok()) << result->error().describe();
  EXPECT_EQ(existing.tab_count(), 16);
  EXPECT_EQ(existing.editor().type().id, kEditorProject);
  EXPECT_EQ(state().saved_review().at("id"), draft.at("id"));
}

TEST_F(SavedReviewPython, NullAndForgottenScreensNeverAdoptOrNavigate)
{
  const auto layout = f.screen.to_json();
  std::optional<Result> result;
  queue_open(nullptr, result);
  ASSERT_TRUE(result.has_value());
  ASSERT_FALSE(result->ok());
  EXPECT_EQ(result->error().code, bridge::ErrorCode::Unavailable);
  empty_review();
  result.reset();
  queue_open(&f.screen, result);
  ASSERT_FALSE(result.has_value());
  f.shell->forget(f.screen);
  f.screen.run_deferred();
  ASSERT_TRUE(result.has_value());
  ASSERT_FALSE(result->ok());
  EXPECT_EQ(result->error().code, bridge::ErrorCode::Unavailable);
  empty_review();
  EXPECT_EQ(f.screen.to_json(), layout);
}

TEST_F(SavedReviewPython, ExpiredCallerDropsDeferredNavigationAndCompletion)
{
  const auto layout = f.screen.to_json();
  auto lifetime = std::make_shared<bool>(true);
  std::weak_ptr<bool> weak = lifetime;
  std::optional<Result> result;
  queue_open(&f.screen, result, [weak] { return !weak.expired(); });
  lifetime.reset();
  f.screen.run_deferred();
  EXPECT_FALSE(result.has_value());
  empty_review();
  EXPECT_EQ(f.screen.to_json(), layout);
}

}  // namespace
}  // namespace stk::app
