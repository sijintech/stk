/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/wm/screen.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "support.hh"

#include <filesystem>

namespace stk::wmtest {
namespace {

TEST(WorkspaceTree, MovesAreaAndRegionIdentitiesRebindsScreenAndKeepsGlobalBars)
{
  wm::Screen target, prepared;
  auto &obsolete = target.add_area("old");
  (void)obsolete;
  auto &bar = target.set_global_area(wm::RegionAlign::Top, std::make_unique<wm::Area>("bar"));
  auto &moved = prepared.add_area("source");
  auto &region = moved.emplace_region<wm::Region>("main");
  const auto identity = moved.id();
  prepared.set_maximized(&moved);
  target.adopt_tree_from(prepared);
  EXPECT_EQ(target.find_area(identity), &moved);
  EXPECT_EQ(moved.screen(), &target); EXPECT_EQ(region.screen(), &target);
  EXPECT_EQ(target.maximized(), &moved); EXPECT_EQ(target.global_area(wm::RegionAlign::Top), &bar);
  EXPECT_EQ(prepared.root(), nullptr); EXPECT_EQ(prepared.maximized(), nullptr);
  EXPECT_EQ(moved.node(), target.root());
}

TEST(WorkspaceTree, DropsBothTreesDeferredCallbacksAndAcceptsEmptyAndSelfMoves)
{
  wm::Screen target, prepared;
  target.add_area("old"); prepared.add_area("new");
  int callbacks = 0;
  target.defer([&] { callbacks++; }); prepared.defer([&] { callbacks += 10; });
  target.adopt_tree_from(prepared);
  target.run_deferred(); prepared.run_deferred();
  EXPECT_EQ(callbacks, 0);
  const auto before = target.to_json();
  target.adopt_tree_from(target); EXPECT_EQ(target.to_json(), before);
  target.adopt_tree_from(prepared); EXPECT_EQ(target.root(), nullptr);
}

TEST(WorkspaceTree, MovingDuringADeferredBatchCancelsTheRemainingOldTreeCallbacks)
{
  wm::Screen target, prepared;
  target.add_area("old"); prepared.add_area("new");
  int stale_callback = 0;
  target.defer([&] { target.adopt_tree_from(prepared); });
  target.defer([&] { stale_callback++; });
  target.run_deferred();
  EXPECT_EQ(stale_callback, 0);
  ASSERT_TRUE(target.root()); EXPECT_EQ(target.root()->area->type(), "new");
}

TEST(WorkspaceDesktop, CapturesHiddenTabsAndRestoresAllHeadlessWindows)
{
  AppFixture f;
  const auto original = f.shell->capture_workspace();
  ASSERT_EQ(original["windows"].size(), 1u);
  auto state = original;
  state["windows"].push_back(state["windows"][0]);
  state["windows"].push_back(state["windows"][0]);
  state["app"]["viewer"]["export_settings"]["width"] = 2048;
  std::string error;
  ASSERT_TRUE(f.shell->apply_workspace(state, &error)) << error;
  EXPECT_EQ(f.shell->screen_count(), 3u);
  const auto copy = f.shell->capture_workspace();
  EXPECT_EQ(copy["windows"], state["windows"]);
  EXPECT_EQ(f.shell->store().viewer().export_settings.width, 2048);
  EXPECT_TRUE(f.shell->store().viewer().workspace_suspended());
  // Existing externally owned Screen objects retain their identity for callers/tests.
  EXPECT_TRUE(f.shell->has_screen(&f.screen));
  ASSERT_TRUE(f.shell->apply_workspace(original, &error)) << error;
  EXPECT_EQ(f.shell->screen_count(), 1u);
}

TEST(WorkspaceDesktop, InvalidLaterWindowLeavesEveryExistingWindowAndViewerUnchanged)
{
  AppFixture f;
  const auto original = f.shell->capture_workspace();
  auto invalid = original;
  invalid["windows"].push_back(invalid["windows"][0]);
  invalid["windows"][1]["screen"]["root"] = {{"factor", 1}, {"area", {{"id", "a1"}, {"type", "unknown-editor"}}}};
  invalid["app"]["viewer"]["export_settings"]["width"] = 4096;
  std::string error;
  EXPECT_FALSE(f.shell->apply_workspace(invalid, &error));
  EXPECT_FALSE(error.empty()); EXPECT_EQ(f.shell->capture_workspace(), original);
  EXPECT_EQ(f.shell->screen_count(), 1u); EXPECT_FALSE(f.shell->store().viewer().workspace_suspended());
}

TEST(WorkspaceDesktop, PreservesTheSpecificViewerValidationErrorAndCurrentDesktop)
{
  AppFixture f;
  const auto original = f.shell->capture_workspace();
  auto invalid = original;
  invalid["app"]["viewer"]["fps"] = 0;
  std::string error;
  EXPECT_FALSE(f.shell->apply_workspace(invalid, &error));
  EXPECT_NE(error.find("outside its bounds"), std::string::npos) << error;
  EXPECT_EQ(f.shell->capture_workspace(), original);
}

TEST(WorkspaceDesktop, RejectsMissingFalseOrInvalidWorkspaceMarkersWithoutPartialAdoption)
{
  AppFixture f;
  const auto original = f.shell->capture_workspace();
  for (int fault = 0; fault < 3; fault++) {
    SCOPED_TRACE(fault);
    auto invalid = original;
    invalid["windows"].push_back(invalid["windows"][0]);
    invalid["app"]["viewer"]["export_settings"]["width"] = 4096;
    auto *node = &invalid["windows"][1]["screen"]["root"];
    while (!node->contains("area")) { node = &node->at("children").at(0); }
    auto &state = node->at("area").at("state");
    if (fault == 0) { state.erase("workspace"); }
    if (fault == 1) { state["workspace"] = false; }
    if (fault == 2) { state["workspace"] = "true"; }
    std::string error;
    EXPECT_FALSE(f.shell->apply_workspace(invalid, &error));
    EXPECT_NE(error.find("complete editor state"), std::string::npos) << error;
    EXPECT_EQ(f.shell->capture_workspace(), original);
    EXPECT_EQ(f.shell->screen_count(), 1u);
    EXPECT_FALSE(f.shell->store().viewer().workspace_suspended());
  }
}

TEST(WorkspaceDesktop, AcceptsRegularPackedPayloadWithoutEvaluation)
{
  namespace fs = std::filesystem;
  struct Scratch {
    fs::path path = fs::path(temp_dir("workspace-payload"));
    ~Scratch() { std::error_code ec; fs::remove_all(path, ec); }
  } scratch;
  const auto real = scratch.path / "real";
  fs::create_directory(real);
  const auto payload = real / "viewer.stkp";
  fs::copy_file(fs::path(desktop_dir()).parent_path() / "docs/specs/examples/payload-v2/example.stkp", payload);
  AppFixture f;
  auto state = f.shell->capture_workspace();
  state["app"]["viewer_payload_path"] = core::path_to_utf8(payload);
  std::string error;
  // The system temp path on Darwin may contain its standard /var alias.
  ASSERT_TRUE(f.shell->apply_workspace(state, &error)) << error;
  ASSERT_NE(f.shell->store().viewer().base_payload(), nullptr);
  EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0u);
  EXPECT_TRUE(f.shell->store().viewer().workspace_suspended());
}

#ifndef _WIN32
TEST(WorkspaceDesktop, RejectsUserParentSymlinksWithoutChangingTheDesktop)
{
  namespace fs = std::filesystem;
  struct Scratch {
    fs::path path = fs::path(temp_dir("workspace-payload-symlink"));
    ~Scratch() { std::error_code ec; fs::remove_all(path, ec); }
  } scratch;
  const auto real = scratch.path / "real";
  fs::create_directory(real);
  const auto payload = real / "viewer.stkp";
  fs::copy_file(fs::path(desktop_dir()).parent_path() / "docs/specs/examples/payload-v2/example.stkp", payload);
  AppFixture f;
  const auto original = f.shell->capture_workspace();
  auto state = original;
  const auto alias = scratch.path / "user-alias";
  std::error_code ec;
  fs::create_directory_symlink(real, alias, ec);
  ASSERT_FALSE(ec) << ec.message();
  state["app"]["viewer_payload_path"] = core::path_to_utf8(alias / "viewer.stkp");
  std::string error;
  EXPECT_FALSE(f.shell->apply_workspace(state, &error));
  EXPECT_NE(error.find("symbolic links"), std::string::npos) << error;
  EXPECT_EQ(f.shell->capture_workspace(), original);
}
#endif

}  // namespace
}  // namespace stk::wmtest
