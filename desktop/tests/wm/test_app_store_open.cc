/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/app_store.hh"

namespace stk::app {

TEST(AppStore, OpenResultRequestIsQueuedOnceAndTaken)
{
  AppStore store;
  int changes = 0;
  store.on_change = [&] { changes++; };
  EXPECT_FALSE(store.has_open_result());
  EXPECT_EQ(store.bridge(), nullptr);
  store.request_open_result({.connection = "local", .task_id = "t1"});
  store.request_open_result({.connection = "runtime:lab", .task_id = "t2", .preset = "muferro-domains"});
  EXPECT_EQ(changes, 2);
  ASSERT_TRUE(store.has_open_result());
  const std::optional<OpenResultRequest> taken = store.take_open_result();
  ASSERT_TRUE(taken.has_value());
  EXPECT_EQ(taken->task_id, "t2"); /* the newer request replaces an unconsumed one */
  EXPECT_EQ(taken->preset, "muferro-domains");
  EXPECT_FALSE(store.has_open_result());
  EXPECT_FALSE(store.take_open_result().has_value());
}

}  // namespace stk::app
