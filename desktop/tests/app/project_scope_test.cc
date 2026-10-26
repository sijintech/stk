/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/app_store.hh"
#include "stk/bridge/client.hh"

#include <stdexcept>
#include <vector>

namespace stk::app {
namespace {
TEST(ProjectScopeNotifications, InvalidatesBeforeReplacingTheBorrowedBridge)
{
  AppStore store;
  auto client = bridge::Client::create({}); // No process is started.
  std::vector<bridge::Client *> seen;
  auto token = store.observe_project_scope([&] { seen.push_back(store.bridge()); });
  store.set_bridge(client.get());
  ASSERT_EQ(seen.size(), 1u); EXPECT_EQ(seen[0], nullptr);
  const auto epoch = store.project_scope_epoch();
  store.set_bridge(client.get());
  EXPECT_EQ(store.project_scope_epoch(), epoch); EXPECT_EQ(seen.size(), 1u);
  store.set_bridge(nullptr);
  ASSERT_EQ(seen.size(), 2u); EXPECT_EQ(seen[1], client.get());
}

TEST(ProjectScopeNotifications, LostBridgeClosesResourcesBeforeChangingItsVisibleStatus)
{
  AppStore store; store.set_bridge_state(BridgeState::Ready);
  std::vector<BridgeState> seen;
  auto token = store.observe_project_scope([&] { seen.push_back(store.bridge_state()); });
  store.set_bridge_state(BridgeState::Restarting);
  ASSERT_EQ(seen.size(), 1u); EXPECT_EQ(seen[0], BridgeState::Ready);
  const auto epoch = store.project_scope_epoch();
  store.set_bridge_state(BridgeState::Restarting);
  EXPECT_EQ(store.project_scope_epoch(), epoch);
}

TEST(ProjectScopeNotifications, CancellationDuringNotificationPreventsLaterBorrowedCallbacks)
{
  AppStore store; std::vector<int> seen;
  ProjectScopeSubscription first, second;
  first = store.observe_project_scope([&] { seen.push_back(1); first.reset(); second.reset(); });
  second = store.observe_project_scope([&] { seen.push_back(2); });
  auto third = store.observe_project_scope([&] { seen.push_back(3); });
  store.invalidate_project_scope();
  EXPECT_EQ(seen, (std::vector<int>{1, 3}));
  store.invalidate_project_scope();
  EXPECT_EQ(seen, (std::vector<int>{1, 3, 3}));
}

TEST(ProjectScopeNotifications, NewListenerWaitsUntilTheNextInvalidation)
{
  AppStore store; std::vector<int> seen; ProjectScopeSubscription added;
  auto first = store.observe_project_scope([&] {
    seen.push_back(1);
    if (seen.size() == 1) { added = store.observe_project_scope([&] { seen.push_back(2); }); }
  });
  store.invalidate_project_scope(); EXPECT_EQ(seen, (std::vector<int>{1}));
  store.invalidate_project_scope(); EXPECT_EQ(seen, (std::vector<int>{1, 1, 2}));
}

TEST(ProjectScopeNotifications, ReentrantInvalidationDoesNotRepeatTheOuterRemainder)
{
  AppStore store; std::vector<int> seen; bool nested = false;
  auto first = store.observe_project_scope([&] {
    seen.push_back(1);
    if (!nested) { nested = true; store.invalidate_project_scope(); }
  });
  auto second = store.observe_project_scope([&] { seen.push_back(2); });
  store.invalidate_project_scope();
  EXPECT_EQ(seen, (std::vector<int>{1, 1, 2})); EXPECT_EQ(store.project_scope_epoch(), 2u);
}

TEST(ProjectScopeNotifications, OtherOwnersStillInvalidateIfOneListenerThrows)
{
  AppStore store; bool other_closed = false;
  auto bad = store.observe_project_scope([] { throw std::runtime_error("controlled listener failure"); });
  auto good = store.observe_project_scope([&] { other_closed = true; });
  EXPECT_THROW(store.invalidate_project_scope(), std::runtime_error);
  EXPECT_TRUE(other_closed);
}

TEST(ProjectScopeNotifications, MovingATokenReplacesItsPreviousRegistration)
{
  AppStore store; std::vector<int> seen;
  auto first = store.observe_project_scope([&] { seen.push_back(1); });
  auto second = store.observe_project_scope([&] { seen.push_back(2); });
  second = std::move(first);
  store.invalidate_project_scope(); EXPECT_EQ(seen, (std::vector<int>{1}));
  second.reset(); store.invalidate_project_scope(); EXPECT_EQ(seen.size(), 1u);
}

TEST(ProjectScopeNotifications, ATokenCanOutliveItsStoreWithoutCallingABorrowedOwner)
{
  ProjectScopeSubscription token; int called = 0;
  {
    AppStore store;
    token = store.observe_project_scope([&] { ++called; });
  }
  token.reset(); EXPECT_EQ(called, 0);
}
} // namespace
} // namespace stk::app
