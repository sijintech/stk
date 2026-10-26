/* SPDX-License-Identifier: GPL-2.0-or-later */
/** CPU layout/input contract only; no native browser or OS presentation is claimed. */
#include <cmath>
#include <limits>
#include <type_traits>

#include "support.hh"

using namespace stk::ui;
using stk::ui::test::Harness;

static_assert(!std::is_copy_constructible_v<Context::NativeViewObserver>);
static_assert(std::is_nothrow_move_constructible_v<Context::NativeViewObserver>);
static_assert(std::is_nothrow_move_assignable_v<Context::NativeViewObserver>);

TEST(NativeViewport, StableResolvedGeometryClipAndScaleWithoutImageDrawing)
{
  Harness h;
  WidgetId id = 0;
  bool enabled = true, shown = true;
  h.ui = [&](Context &ctx) {
    auto &layout = ctx.block("report", {20, 30, 300, 60}).layout();
    if (shown) { id = layout.native_viewport("document", 8).disable(!enabled).id; }
  };
  h.frame();
  const WidgetId first = id;
  auto view = h.ctx->native_viewport_state(id);
  ASSERT_TRUE(view);
  EXPECT_EQ(view->rect, h.w("document").rect);
  EXPECT_FLOAT_EQ(view->height, h.ctx->style().u(8));
  EXPECT_TRUE(view->visible);
  EXPECT_TRUE(view->enabled);
  EXPECT_LT(view->rect.intersect(view->clip).h, view->height);
  EXPECT_EQ(view->clip.intersect({20, 30, 300, 60}), view->clip);
  for (const auto &cmd : h.ctx->draw_list().cmds) { EXPECT_NE(cmd.type, CmdType::Image); }
  h.ctx->set_scale(2);
  h.frame();
  EXPECT_EQ(id, first);
  EXPECT_FLOAT_EQ(h.ctx->native_viewport_state(id)->height, h.ctx->style().u(8));
  enabled = false;
  h.frame();
  EXPECT_FALSE(h.ctx->native_viewport_state(id)->enabled);
  h.ctx->begin_frame(h.window, h.t);
  EXPECT_FALSE(h.ctx->native_viewport_state(id));
  h.ctx->end_frame();
  shown = false;
  h.frame();
  EXPECT_FALSE(h.ctx->native_viewport_state(id));
}

TEST(NativeViewport, EmptyAndOffscreenGeometryCannotClaimVisibility)
{
  Harness h;
  h.ui = [](Context &ctx) {
    auto &l = ctx.block("outside", {500, 900, 200, 200}).layout();
    l.native_viewport("offscreen", 4);
    auto &zero = ctx.block("inside", {0, 0, 200, 200}).layout();
    zero.native_viewport("zero", 0);
    zero.native_viewport("invalid", std::numeric_limits<float>::infinity());
  };
  h.frame();
  for (const char *key : {"offscreen", "zero", "invalid"}) {
    auto view = h.ctx->native_viewport_state(h.w(key).id);
    ASSERT_TRUE(view);
    EXPECT_FALSE(view->visible) << key;
    EXPECT_TRUE(std::isfinite(view->height));
  }
}

TEST(NativeViewport, PointerAndTabDoNotTurnViewportIntoAnOrdinaryControl)
{
  Harness h;
  int actions = 0;
  h.ui = [&](Context &ctx) {
    auto &l = ctx.block("main", {0, 0, 400, 600}).layout();
    l.button("before", "Before", [&] { ++actions; });
    l.native_viewport("document", 4);
    l.button("after", "After", [&] { ++actions; });
  };
  h.frame();
  ASSERT_TRUE(h.ctx->focus_widget(h.w("before").id));
  h.click("document");
  EXPECT_EQ(h.ctx->active(), 0u);
  EXPECT_EQ(h.ctx->focused(), h.w("before").id);
  EXPECT_FALSE(h.ctx->focus_widget(h.w("document").id));
  h.key(Key::Tab);
  EXPECT_EQ(h.ctx->focused(), h.w("after").id);
  EXPECT_EQ(actions, 0);
}

TEST(NativeViewport, FocusReturnRejectsHiddenDisabledStaleAndDraftControls)
{
  Harness h;
  bool enabled = true, shown = true;
  std::string value = "saved";
  int actions = 0;
  h.ui = [&](Context &ctx) {
    auto &l = ctx.block("main", {0, 0, 400, 600}).layout();
    l.text_field("draft", bind(value));
    if (shown) { l.button("return", "Return", [&] { ++actions; }).disable(!enabled); }
    ctx.block("outside", {500, 900, 100, 100}).layout().button("hidden", "Hidden", [] {});
  };
  h.frame();
  const auto id = h.w("return").id;
  EXPECT_TRUE(h.ctx->focus_widget(id));
  EXPECT_FALSE(h.ctx->focus_widget(h.w("hidden").id));
  enabled = false;
  h.frame();
  EXPECT_FALSE(h.ctx->focus_widget(id));
  enabled = true;
  h.frame();
  h.click("draft");
  h.type("pending");
  ASSERT_NE(h.ctx->editing(), 0u);
  const std::string edit = h.ctx->edit_state()->text();
  EXPECT_FALSE(h.ctx->focus_widget(id));
  EXPECT_EQ(h.ctx->edit_state()->text(), edit);
  EXPECT_EQ(value, "saved");
  h.key(Key::Escape);
  shown = false;
  h.frame();
  EXPECT_FALSE(h.ctx->focus_widget(id));
  EXPECT_EQ(actions, 0);
}

TEST(NativeViewInvalidation, PopupHidesSynchronouslyBeforeItsStateOrNextFrame)
{
  Harness h;
  h.ui = [](Context &ctx) {
    auto &l = ctx.block("main", {0, 0, 400, 600}).layout();
    l.native_viewport("document", 4);
    l.menu_button("menu", "Menu", {{"Action", [] {}}});
  };
  h.frame();
  bool hidden = false;
  auto subscription = h.ctx->observe_native_view_invalidated([&] {
    hidden = true;
    EXPECT_FALSE(h.ctx->popup_open());
    EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  });
  ASSERT_TRUE(h.ctx->open_popup("menu"));
  EXPECT_TRUE(hidden); // No frame/paint/event pump between the call and this assertion.
  EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  subscription.reset();
  h.frame();
  EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  h.ctx->close_popup();
  h.frame();
  EXPECT_FALSE(h.ctx->native_view_interaction_blocked());
}

TEST(NativeViewInvalidation, ModalTooltipAndToastNotifyBeforeOverlayConstruction)
{
  Harness h;
  h.ui = [](Context &ctx) { ctx.block("main", {0, 0, 400, 600}).layout().button("tip", "Tip", [] {}).tip("Help"); };
  h.frame();
  int invalidated = 0;
  auto subscription = h.ctx->observe_native_view_invalidated([&] {
    ++invalidated;
    EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  });
  ASSERT_TRUE(h.ctx->force_tooltip("tip"));
  EXPECT_EQ(invalidated, 1);
  h.frame();
  EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  ASSERT_FALSE(h.ctx->force_tooltip("absent"));
  h.frame();
  EXPECT_FALSE(h.ctx->native_view_interaction_blocked());
  const int before_toast = invalidated;
  h.ctx->toast("Notice", ToastKind::Info, 1);
  EXPECT_EQ(invalidated, before_toast + 1);
  EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  h.t += 2;
  h.frame();
  EXPECT_FALSE(h.ctx->native_view_interaction_blocked());
  const int before_modal = invalidated;
  h.ctx->begin_frame(h.window, h.t);
  h.ctx->modal("modal", "Modal", [] {}).button("ok", "OK", [] {});
  EXPECT_EQ(invalidated, before_modal + 1);
  h.ctx->end_frame();
  EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  EXPECT_FALSE(h.ctx->focus_widget(h.w("ok").id));
}

TEST(NativeViewInvalidation, PointerCaptureStaysBlockedThroughFramesAndReleasesOnce)
{
  Harness h;
  double number = 10;
  h.ui = [&](Context &ctx) {
    auto &l = ctx.block("main", {0, 0, 400, 600}).layout();
    l.native_viewport("document", 4);
    l.number("value", "Value", bind(number));
  };
  h.frame();
  int invalidated = 0;
  auto subscription = h.ctx->observe_native_view_invalidated([&] { ++invalidated; });
  const Vec2 start = h.center("value");
  h.ctx->handle_event(Event::mouse_down(start));
  EXPECT_EQ(invalidated, 1);
  EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  h.frame();
  h.move({start.x + 30, start.y});
  EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  h.send(Event::mouse_up({start.x + 30, start.y}));
  EXPECT_FALSE(h.ctx->native_view_interaction_blocked());
  EXPECT_NE(number, 10);
  EXPECT_EQ(invalidated, 1);
}

TEST(NativeViewInvalidation, ContainerDragHidesBeforeDropCallback)
{
  Harness h;
  int notices = 0, drops = 0;
  h.ui = [&](Context &ctx) {
    auto &grid = ctx.block("board", {0, 0, 400, 600}).layout().grid(2);
    auto &card = grid.box();
    card.drag_source("card", {"board", 1, [&](std::string) { EXPECT_GT(notices, 0); ++drops; }});
    card.label("Card");
    auto &lane = grid.column();
    lane.drop_target("lane", {"board", 1, "B"});
    lane.label("Lane");
  };
  h.frame();
  auto subscription = h.ctx->observe_native_view_invalidated([&] { ++notices; });
  h.ctx->handle_event(Event::mouse_down(h.center("card")));
  EXPECT_EQ(notices, 1);
  EXPECT_TRUE(h.ctx->native_view_interaction_blocked());
  h.move(h.center("lane"));
  EXPECT_EQ(drops, 0);
  h.send(Event::mouse_up(h.center("lane")));
  EXPECT_EQ(drops, 1);
}

TEST(NativeViewInvalidation, CancellationAdditionMoveAndContextLifetimeAreSafe)
{
  Harness h;
  h.frame();
  int first = 0, second = 0, late = 0;
  Context::NativeViewObserver a, b, added;
  a = h.ctx->observe_native_view_invalidated([&] {
    ++first;
    a.reset();
    b.reset();
    added = h.ctx->observe_native_view_invalidated([&] { ++late; });
  });
  b = h.ctx->observe_native_view_invalidated([&] { ++second; });
  h.ctx->toast("First");
  EXPECT_EQ(first, 1);
  EXPECT_EQ(second, 0);
  EXPECT_EQ(late, 0);
  Context::NativeViewObserver moved = std::move(added);
  EXPECT_FALSE(added);
  EXPECT_TRUE(moved);
  h.ctx->toast("Second");
  EXPECT_EQ(late, 1);
  h.ctx.reset();
  EXPECT_EQ(late, 2); // Closing the Context withdraws any view still attached to it.
  EXPECT_FALSE(moved);
  moved.reset();
}
