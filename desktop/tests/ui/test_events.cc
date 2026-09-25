/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Event tests on the retained block: text field (IME, clipboard, undo), number drag and
 * click-to-type, dropdown, tabs, lists (100k rows), tables, logs, modal focus trapping, tooltips,
 * toasts, splitter. */
#include <chrono>
#include <cmath>
#include <cstdio>
#include <limits>
#include <tuple>

#include <gtest/gtest.h>

#include "support.hh"

using namespace stk::ui;
using stk::ui::test::Harness;

static const std::string ZHONG = "\xe4\xb8\xad";
static const std::string WEN = "\xe6\x96\x87";

static bool has_block(Context &ctx, Block::Kind k)
{
  for (const auto &b : ctx.blocks()) {
    if (b->kind() == k) {
      return true;
    }
  }
  return false;
}

TEST(TextField, ImePreeditCommitClipboardUndo)
{
  Harness h;
  std::string name = "ab";
  h.ui = [&](Context &ctx) { ctx.block("r", {0, 0, 400, 600}).layout().text_field("name", bind(name)); };
  h.frame();
  const WidgetId id = h.w("name").id;
  h.click("name");
  ASSERT_EQ(h.ctx->editing(), id);
  EXPECT_TRUE(h.ctx->text_input_active());
  EXPECT_EQ(h.ctx->edit_state()->cursor(), 2u) << "click right of the text puts the caret at the end";

  h.type("c");
  EXPECT_EQ(h.ctx->edit_state()->text(), "abc");
  EXPECT_EQ(name, "ab") << "the binding changes on commit only";

  /* Composition: preedit shown inline with an underline, not part of the text. */
  h.send(Event::ime_preedit("zhong", 5));
  EXPECT_EQ(h.ctx->edit_state()->text(), "abc");
  EXPECT_EQ(h.ctx->edit_state()->display_text(), "abczhong");
  const Style &st = h.ctx->style();
  const float x0 = h.w("name").rect.x + st.text_margin;
  bool underline = false, shown = false;
  for (const DrawCmd &c : h.ctx->draw_list().cmds) {
    if (c.type == CmdType::Text && c.text == "abczhong") {
      shown = true;
    }
    if (c.type == CmdType::Rect && c.color == h.ctx->theme().text.text_sel &&
        std::fabs(c.rect.x - (x0 + 16.5f)) <= 1.0f && std::fabs(c.rect.w - 27.5f) <= 1.0f)
    {
      underline = true;
    }
  }
  EXPECT_TRUE(shown);
  EXPECT_TRUE(underline) << "preedit underline under 'zhong'";

  /* Converted candidate, caret inside the preedit after 中. */
  h.send(Event::ime_preedit(ZHONG + WEN, 3));
  EXPECT_EQ(h.ctx->edit_state()->display_caret(), 6u);
  const Rect caret = h.ctx->text_input_rect();
  EXPECT_NEAR(caret.cx(), x0 + 16.5f + 11.0f, 1.5f) << "IME candidate window follows the caret";

  h.send(Event::ime_commit(ZHONG + WEN));
  EXPECT_FALSE(h.ctx->edit_state()->composing());
  EXPECT_EQ(h.ctx->edit_state()->text(), "abc" + ZHONG + WEN);
  h.key(Key::Enter);
  EXPECT_EQ(name, "abc" + ZHONG + WEN);
  EXPECT_EQ(h.ctx->editing(), 0u);

  /* Clipboard and undo. */
  h.click("name");
  h.key(Key::A, MOD_CTRL);
  h.key(Key::C, MOD_CTRL);
  EXPECT_EQ(h.clipboard.text, "abc" + ZHONG + WEN);
  h.key(Key::End);
  h.key(Key::V, MOD_CTRL);
  EXPECT_EQ(h.ctx->edit_state()->text(), "abc" + ZHONG + WEN + "abc" + ZHONG + WEN);
  h.key(Key::Z, MOD_CTRL);
  EXPECT_EQ(h.ctx->edit_state()->text(), "abc" + ZHONG + WEN);
  h.key(Key::Z, MOD_CTRL | MOD_SHIFT);
  EXPECT_EQ(h.ctx->edit_state()->text(), "abc" + ZHONG + WEN + "abc" + ZHONG + WEN);
  h.key(Key::Backspace, MOD_CTRL); /* deletes the word "中文" before the caret */
  EXPECT_EQ(h.ctx->edit_state()->text(), "abc" + ZHONG + WEN + "abc");
  h.key(Key::X, MOD_CTRL); /* no selection: no-op */
  h.key(Key::Escape);
  EXPECT_EQ(name, "abc" + ZHONG + WEN) << "Escape cancels the edit";
  EXPECT_EQ(h.ctx->editing(), 0u);

  /* Typing into the focused field starts editing it. */
  h.type("z");
  EXPECT_EQ(h.ctx->editing(), id);
  h.key(Key::Enter);
  EXPECT_EQ(name, "abc" + ZHONG + WEN + "z");
}

TEST(TextField, ClickOutsideCommitsAndTabMovesToNextField)
{
  Harness h;
  std::string a = "one", b = "two";
  int pressed = 0;
  h.ui = [&](Context &ctx) {
    Layout &l = ctx.block("r", {0, 0, 400, 600}).layout();
    l.text_field("a", bind(a));
    l.text_field("b", bind(b));
    l.button("btn", "Go", [&]() { pressed++; });
  };
  h.frame();
  h.click("a");
  h.type("!");
  h.key(Key::Tab);
  EXPECT_EQ(a, "one!");
  EXPECT_EQ(h.ctx->editing(), h.w("b").id) << "Tab commits and edits the next field";
  EXPECT_TRUE(h.ctx->edit_state()->has_selection());
  h.type("2");
  h.click("btn");
  EXPECT_EQ(b, "2");
  EXPECT_EQ(pressed, 1);
}

TEST(NumberField, DragClickToTypeAndArrows)
{
  Harness h;
  double v = 1.0;
  NumberProps p;
  p.step = 0.1;
  p.min = 0;
  p.max = 10;
  p.soft_max = 5;
  h.ui = [&](Context &ctx) { ctx.block("r", {0, 0, 400, 600}).layout().number("v", "Value", bind(v), p); };
  h.frame();
  const Vec2 c = h.center("v");
  /* Drag: one step per half widget unit (10 px at scale 1). */
  h.drag(c, {c.x + 40, c.y});
  EXPECT_NEAR(v, 1.4, 1e-9);
  h.drag(c, {c.x - 20, c.y}, MOD_SHIFT);
  EXPECT_NEAR(v, 1.38, 1e-9) << "Shift drags ten times finer";
  h.drag(c, {c.x + 2000, c.y});
  EXPECT_DOUBLE_EQ(v, 5.0) << "dragging stops at the soft maximum";

  /* Click without moving: type a value, scientific notation accepted. */
  h.click(c);
  ASSERT_EQ(h.ctx->editing(), h.w("v").id);
  EXPECT_EQ(h.ctx->edit_state()->text(), "5");
  EXPECT_TRUE(h.ctx->edit_state()->has_selection());
  h.type("1e-3");
  h.key(Key::Enter);
  EXPECT_DOUBLE_EQ(v, 1e-3);
  /* Typed values obey the hard limits only. */
  h.click(c);
  h.type("7.5");
  h.key(Key::Enter);
  EXPECT_DOUBLE_EQ(v, 7.5);
  h.click(c);
  h.type("1e9");
  h.key(Key::Enter);
  EXPECT_DOUBLE_EQ(v, 10.0);
  /* Invalid text keeps the value and shows a toast. */
  h.click(c);
  h.type("abc");
  h.key(Key::Enter);
  EXPECT_DOUBLE_EQ(v, 10.0);
  EXPECT_TRUE(has_block(*h.ctx, Block::Kind::Toast));

  /* Arrow zones step by `step`. */
  const Rect vr = h.w("v").rect; /* copy: widgets are rebuilt every frame */
  h.click({vr.x + 3, c.y});
  EXPECT_NEAR(v, 9.9, 1e-9);
  h.click({vr.x1() - 3, c.y});
  h.click({vr.x1() - 3, c.y});
  EXPECT_NEAR(v, 10.0, 1e-9);
  /* Keyboard: focused field, Left/Right step. */
  h.key(Key::Left);
  EXPECT_NEAR(v, 9.9, 1e-9);
}

TEST(NumberField, IntegerAndSlider)
{
  Harness h;
  double n = 3, s = 0.5;
  NumberProps ip;
  ip.integer = true;
  ip.min = 0;
  ip.max = 500;
  ip.step = 1;
  NumberProps sp;
  sp.min = 0;
  sp.max = 1;
  sp.step = 0.01;
  h.ui = [&](Context &ctx) {
    Layout &l = ctx.block("r", {0, 0, 408, 600}).layout();
    l.number("n", "N", bind(n), ip);
    l.slider("s", "S", bind(s), sp);
  };
  h.frame();
  const Vec2 c = h.center("n");
  h.drag(c, {c.x + 30, c.y});
  EXPECT_DOUBLE_EQ(n, 6.0) << "integers drag in whole steps";
  h.click(c);
  h.type("2.6");
  h.key(Key::Enter);
  EXPECT_DOUBLE_EQ(n, 3.0);
  /* Slider: the full width spans the soft range. */
  const Rect sw = h.w("s").rect;
  const Vec2 sc = h.center("s");
  h.drag(sc, {sc.x + sw.w * 0.25f, sc.y});
  EXPECT_NEAR(s, 0.75, 1e-6);
  h.drag(sc, {sc.x + sw.w, sc.y});
  EXPECT_DOUBLE_EQ(s, 1.0);
  /* Slider fill is drawn in the item colour, proportional to the value. */
  bool fill = false;
  for (const DrawCmd &cmd : h.ctx->draw_list().cmds) {
    if (cmd.type == CmdType::RoundBox && cmd.color == h.ctx->theme().numslider.item &&
        std::fabs(cmd.rect.w - sw.w) < 1.0f)
    {
      fill = true;
    }
  }
  EXPECT_TRUE(fill);
}

TEST(Dropdown, OpenSelectEscapeAndClickOutside)
{
  Harness h;
  int sel = 0, under = 0;
  h.ui = [&](Context &ctx) {
    Layout &row = ctx.block("r", {0, 0, 400, 600}).layout().row();
    row.dropdown("dd", {"iso", "+x", "-x", "+y", "-y"}, bind(sel));
    row.button("under", "Under", [&]() { under++; });
  };
  h.frame();
  h.click("dd");
  ASSERT_TRUE(h.ctx->popup_open());
  ASSERT_NE(h.ctx->find("popup/4"), nullptr);
  EXPECT_TRUE(has_block(*h.ctx, Block::Kind::Popup));
  h.key(Key::Down);
  h.key(Key::Enter);
  EXPECT_EQ(sel, 1);
  EXPECT_FALSE(h.ctx->popup_open());

  h.click("dd");
  h.key(Key::Down);
  h.key(Key::Escape);
  EXPECT_FALSE(h.ctx->popup_open());
  EXPECT_EQ(sel, 1) << "Escape closes without changing the value";

  h.click("dd");
  h.click("popup/3");
  EXPECT_EQ(sel, 3);
  EXPECT_FALSE(h.ctx->popup_open());

  /* A click outside closes the popup and is consumed (the button next to it does not fire). */
  h.click("dd");
  const Vec2 button = h.center("under");
  h.click(button);
  EXPECT_FALSE(h.ctx->popup_open());
  EXPECT_EQ(sel, 3);
  EXPECT_EQ(under, 0);
  h.click(button);
  EXPECT_EQ(under, 1);
}

TEST(MenuButton, RunsActionsSkipsDisabled)
{
  Harness h;
  int opened = 0, quit = 0;
  h.ui = [&](Context &ctx) {
    ctx.block("r", {0, 0, 400, 600})
        .layout()
        .menu_button("file", "File", {{"Open", [&]() { opened++; }}, {"Quit", [&]() { quit++; }, false}});
  };
  h.frame();
  h.click("file");
  h.click("popup/1");
  EXPECT_EQ(quit, 0);
  EXPECT_TRUE(h.ctx->popup_open()) << "disabled entries do nothing";
  h.click("popup/0");
  EXPECT_EQ(opened, 1);
  EXPECT_FALSE(h.ctx->popup_open());
}

TEST(Tabs, ClickAndKeyboard)
{
  Harness h;
  int tab = 0;
  h.ui = [&](Context &ctx) { ctx.block("r", {0, 0, 400, 600}).layout().tabs("t", {"Logs", "Probe", "Transfers"}, bind(tab)); };
  h.frame();
  const Rect r = h.w("t").rect;
  h.click({r.x + r.w * 0.5f, r.cy()});
  EXPECT_EQ(tab, 1);
  h.click({r.x + r.w * 0.9f, r.cy()});
  EXPECT_EQ(tab, 2);
  h.key(Key::Left);
  EXPECT_EQ(tab, 1);
}

TEST(CheckboxAndPanel, ToggleAndCollapse)
{
  Harness h;
  bool on = false;
  double inner = 1;
  h.ui = [&](Context &ctx) {
    Layout &l = ctx.block("r", {0, 0, 400, 600}).layout();
    l.checkbox("cb", "Grid", bind(on));
    if (Layout *p = l.panel("pan", "Panel")) {
      p->number("inner", "Inner", bind(inner));
    }
  };
  h.frame();
  h.click("cb");
  EXPECT_TRUE(on);
  h.key(Key::Space);
  EXPECT_FALSE(on);
  ASSERT_NE(h.ctx->find("inner"), nullptr);
  h.click("pan");
  EXPECT_EQ(h.ctx->find("inner"), nullptr);
  h.click("pan");
  EXPECT_NE(h.ctx->find("inner"), nullptr);
}

TEST(VirtualList, HundredThousandRowsBuildUnderOneMs)
{
  Harness h;
  int sel = -1;
  int activated = -1;
  h.ui = [&](Context &ctx) {
    Layout &l = ctx.block("r", {0, 0, 400, 600}).layout();
    l.label("Jobs");
    ListSpec s;
    s.count = 100000;
    s.rows = 8;
    s.text = [](int i) { return "Job #" + std::to_string(i); };
    s.selected = bind(sel);
    s.on_activate = [&](int i) { activated = i; };
    l.virtual_list("list", std::move(s));
    l.button("b", "OK", {});
  };
  h.frame();
  const WidgetId id = h.w("list").id;
  const Vec2 c = h.center("list");
  h.send(Event::wheel(c, -1.0f));
  EXPECT_FLOAT_EQ(h.ctx->scroll_of(id), 60.0f);
  /* Jump to the middle of the list, then time full rebuilds. */
  for (int i = 0; i < 1000; i++) {
    h.ctx->handle_event(Event::wheel(c, -50.0f, h.t));
  }
  h.frame();
  EXPECT_GT(h.ctx->scroll_of(id), 1.0e6f);
  const int iters = 200;
  const auto t0 = std::chrono::steady_clock::now();
  for (int i = 0; i < iters; i++) {
    h.frame();
  }
  const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count() / iters;
  RecordProperty("build_ms", std::to_string(ms));
  std::printf("virtual list (100k rows) build: %.4f ms/frame\n", ms);
  EXPECT_LT(ms, 1.0);
  size_t texts = 0;
  for (const DrawCmd &cmd : h.ctx->draw_list().cmds) {
    texts += cmd.type == CmdType::Text;
  }
  EXPECT_LT(texts, 20u) << "only visible rows are drawn";

  /* Click selects the row under the pointer; keyboard moves the selection. */
  const Rect lr = h.w("list").rect;
  const float scroll = h.ctx->scroll_of(id);
  const float row_h = h.ctx->style().unit;
  const Vec2 p{lr.x + 20, lr.y + 1 + row_h * 2.5f};
  h.click(p);
  const int expect = int((row_h * 2.5f + scroll) / row_h);
  EXPECT_EQ(sel, expect);
  h.key(Key::Down);
  EXPECT_EQ(sel, expect + 1);
  h.key(Key::End);
  EXPECT_EQ(sel, 99999);
  h.key(Key::Home);
  EXPECT_EQ(sel, 0);
  EXPECT_FLOAT_EQ(h.ctx->scroll_of(id), 0.0f);
  h.key(Key::PageDown);
  EXPECT_EQ(sel, 7);
  /* Double click activates. */
  const Vec2 q{lr.x + 20, lr.y + 1 + row_h * 0.5f};
  h.send(Event::mouse_down(q));
  h.send(Event::mouse_up(q));
  h.send(Event::mouse_down(q));
  h.send(Event::mouse_up(q));
  EXPECT_EQ(activated, 0);
}

TEST(Table, SortAndResize)
{
  Harness h;
  const std::vector<std::string> names = {"b", "a", "c"}, values = {"10", "9", "100"};
  int sel = -1;
  h.ui = [&](Context &ctx) {
    TableSpec t;
    t.columns = {{"Name", 6, true, false}, {"Value", 6, true, true}, {"Note", 4, false, false}};
    t.rows = 3;
    t.cell = [&](int r, int c) { return c == 0 ? names[size_t(r)] : (c == 1 ? values[size_t(r)] : "-"); };
    t.selected = bind(sel);
    ctx.block("r", {0, 0, 400, 600}).layout().table("t", std::move(t));
  };
  h.frame();
  const Rect w = h.w("t").rect;
  const float u = h.ctx->style().unit;
  const Vec2 value_header{w.x + 1 + 6 * u + 2 * u, w.y + 1 + u * 0.5f};
  const Vec2 name_header{w.x + 1 + 2 * u, w.y + 1 + u * 0.5f};
  auto first_row = [&]() {
    h.click({w.x + 10, w.y + 1 + u * 1.5f});
    return sel;
  };
  EXPECT_EQ(first_row(), 0) << "unsorted";
  h.click(value_header);
  EXPECT_EQ(first_row(), 1) << "numeric ascending: 9 first";
  h.click(value_header);
  EXPECT_EQ(first_row(), 2) << "numeric descending: 100 first";
  h.click(name_header);
  EXPECT_EQ(first_row(), 1) << "string ascending: a first";
  h.key(Key::Down);
  EXPECT_EQ(sel, 0) << "keyboard follows the sorted order (b)";

  /* Resize the first column by dragging its header edge. */
  auto title_x = [&](const char *title) {
    for (const DrawCmd &c : h.ctx->draw_list().cmds) {
      if (c.type == CmdType::Text && c.text == title) {
        return c.pos.x;
      }
    }
    return -1.0f;
  };
  const float before = title_x("Note");
  const Vec2 edge{w.x + 1 + 6 * u, value_header.y};
  h.drag(edge, {edge.x + 40, edge.y});
  EXPECT_NEAR(title_x("Note") - before, 40.0f, 1.0f) << "left-aligned title of the next column moves";
  /* Unsortable column: header clicks do nothing. */
  h.click({w.x + 1 + 14 * u + 2 * u + 10, value_header.y});
  EXPECT_EQ(first_row(), 1);
}

TEST(LogView, FollowsTailUntilScrolledUp)
{
  Harness h;
  LogBuffer log;
  for (int i = 0; i < 50; i++) {
    log.append("line " + std::to_string(i) + "\n");
  }
  h.ui = [&](Context &ctx) { ctx.block("r", {0, 0, 400, 600}).layout().log_view("log", log, 5.0f); };
  h.frame();
  const WidgetId id = h.w("log").id;
  auto max_scroll = [&]() {
    const float line_h = std::round(h.ctx->style().mono.size_px * 1.4f);
    return float(log.line_count()) * line_h + 2 * std::round(0.2f * h.ctx->style().unit) - (h.w("log").rect.h - 2);
  };
  EXPECT_NEAR(h.ctx->scroll_of(id), max_scroll(), 0.5f);
  log.append("\x1b[31mnew line\x1b[0m\n");
  h.frame();
  EXPECT_NEAR(h.ctx->scroll_of(id), max_scroll(), 0.5f) << "follows the tail";
  bool stripped = false;
  for (const DrawCmd &c : h.ctx->draw_list().cmds) {
    stripped |= c.type == CmdType::Text && c.text == "new line";
  }
  EXPECT_TRUE(stripped);

  h.send(Event::wheel(h.center("log"), 1.0f));
  const float s = h.ctx->scroll_of(id);
  EXPECT_LT(s, max_scroll());
  log.append("more\n");
  h.frame();
  EXPECT_FLOAT_EQ(h.ctx->scroll_of(id), s) << "stays put while the user reads";
  /* The "follow" pill brings it back. */
  const std::string_view label = h.ctx->tr("ui.log.follow");
  Vec2 pill{-1, -1};
  for (const DrawCmd &c : h.ctx->draw_list().cmds) {
    if (c.type == CmdType::Text && c.text == label) {
      pill = {c.pos.x + 2, c.pos.y - 3};
    }
  }
  ASSERT_GE(pill.x, 0.0f) << "follow pill shown";
  h.click(pill);
  EXPECT_NEAR(h.ctx->scroll_of(id), max_scroll(), 0.5f);
}

TEST(Modal, TrapsFocusAndInput)
{
  Harness h;
  bool open = true;
  int under = 0, ok = 0;
  double x = 1;
  h.ui = [&](Context &ctx) {
    Layout &l = ctx.block("r", {0, 0, 400, 600}).layout();
    l.button("under", "Under", [&]() { under++; });
    l.text_field("under_text", Binding<std::string>{[]() { return std::string("t"); }, {}});
    if (open) {
      Layout &m = ctx.modal("dlg", "Dialog", [&]() { open = false; });
      m.number("x", "X", bind(x));
      Layout &r = m.row();
      r.button("ok", "OK", [&]() { ok++; });
      r.button("cancel", "Cancel", [&]() { open = false; });
    }
  };
  h.frame();
  ASSERT_TRUE(has_block(*h.ctx, Block::Kind::Modal));
  h.click("under");
  EXPECT_EQ(under, 0) << "widgets below a modal do not react";
  EXPECT_EQ(h.ctx->hovered(), 0u);

  const WidgetId ids[] = {h.w("x").id, h.w("ok").id, h.w("cancel").id};
  auto in_modal = [&](WidgetId f) { return f == ids[0] || f == ids[1] || f == ids[2]; };
  for (int i = 0; i < 7; i++) {
    h.key(Key::Tab);
    EXPECT_TRUE(in_modal(h.ctx->focused())) << "Tab #" << i;
  }
  h.key(Key::Tab, MOD_SHIFT);
  EXPECT_TRUE(in_modal(h.ctx->focused()));
  /* Focus "ok" and activate it with Enter. */
  while (h.ctx->focused() != ids[1]) {
    h.key(Key::Tab);
  }
  h.key(Key::Enter);
  EXPECT_EQ(ok, 1);
  h.key(Key::Escape);
  EXPECT_FALSE(open);
  EXPECT_FALSE(has_block(*h.ctx, Block::Kind::Modal));
  h.click("under");
  EXPECT_EQ(under, 1);
}

TEST(Tooltip, AppearsAfterDelay)
{
  Harness h;
  h.ui = [&](Context &ctx) {
    Layout &l = ctx.block("r", {0, 0, 400, 600}).layout();
    l.button("b", "Run", {}).tip("Submit the job");
    l.label("plain");
  };
  h.frame();
  h.move(h.center("b"));
  EXPECT_FALSE(has_block(*h.ctx, Block::Kind::Tooltip));
  EXPECT_NEAR(h.ctx->next_wakeup(), h.t + 0.5, 1e-9);
  h.wait(0.3);
  EXPECT_FALSE(h.ctx->handle_event(Event::tick(h.t)).redraw);
  h.wait(0.3);
  EXPECT_TRUE(h.ctx->handle_event(Event::tick(h.t)).redraw);
  h.frame();
  ASSERT_TRUE(has_block(*h.ctx, Block::Kind::Tooltip));
  bool text = false;
  for (const DrawCmd &c : h.ctx->draw_list().cmds) {
    text |= c.type == CmdType::Text && c.text == "Submit the job";
  }
  EXPECT_TRUE(text);
  EXPECT_EQ(h.ctx->next_wakeup(), std::numeric_limits<double>::infinity()) << "idle: no redraw needed";
  h.move({390, 590});
  EXPECT_FALSE(has_block(*h.ctx, Block::Kind::Tooltip));
}

TEST(Toast, ExpiresAndClickDismisses)
{
  Harness h;
  h.ui = [&](Context &ctx) { ctx.block("r", {0, 0, 400, 600}).layout().label("x"); };
  h.frame(); /* the context clock starts with the first frame */
  h.ctx->toast("Saved", ToastKind::Success, 2.0);
  h.frame();
  ASSERT_TRUE(has_block(*h.ctx, Block::Kind::Toast));
  EXPECT_NEAR(h.ctx->next_wakeup(), h.t + 2.0, 1e-6);
  h.wait(2.5);
  h.frame();
  EXPECT_FALSE(has_block(*h.ctx, Block::Kind::Toast));
  h.ctx->toast("Again", ToastKind::Error, 100.0);
  h.frame();
  const Block *tb = nullptr;
  for (const auto &b : h.ctx->blocks()) {
    if (b->kind() == Block::Kind::Toast) {
      tb = b.get();
    }
  }
  ASSERT_NE(tb, nullptr);
  h.click({tb->frame().cx(), tb->frame().cy()});
  EXPECT_FALSE(has_block(*h.ctx, Block::Kind::Toast));
}

TEST(Splitter, DragChangesFactor)
{
  Harness h;
  float f = 0.5f;
  h.ui = [&](Context &ctx) {
    auto [a, b] = ctx.block("r", {0, 0, 400, 600}).layout().splitter("sp", bind(f));
    a->label("left");
    b->label("right");
  };
  h.frame();
  const Rect bar = h.w("sp").rect;
  const Vec2 c{bar.cx(), bar.cy()};
  const float avail = 384.0f - bar.w;
  h.drag(c, {c.x + 48, c.y});
  EXPECT_NEAR(f, 0.5f + 48.0f / avail, 1e-4);
}

TEST(Region, WheelScrollsOverflowingBlock)
{
  Harness h;
  h.ui = [&](Context &ctx) {
    Layout &l = ctx.block("r", {0, 0, 300, 200}).layout();
    for (int i = 0; i < 30; i++) {
      l.button("b" + std::to_string(i), "Button " + std::to_string(i), {});
    }
  };
  h.frame();
  const float y0 = h.w("b0").rect.y;
  h.send(Event::wheel({150, 100}, -1.0f));
  EXPECT_FLOAT_EQ(h.w("b0").rect.y, y0 - 2 * h.ctx->style().unit);
  EXPECT_LT(h.w("b0").rect.w, 300.0f - 2 * h.ctx->style().panel_margin) << "scrollbar space reserved";
}

TEST(Scale, UnitsFollowDpiTimesUserScale)
{
  for (const auto &[dpi, user, unit] : {std::tuple{1.0f, 1.0f, 20.0f}, std::tuple{1.0f, 1.5f, 29.0f}, std::tuple{2.0f, 1.0f, 40.0f}}) {
    Harness h;
    h.ctx->set_scale(dpi, user);
    EXPECT_FLOAT_EQ(h.ctx->style().unit, unit);
    double v = 0;
    h.ui = [&](Context &ctx) { ctx.block("r", {0, 0, 400, 600}).layout().number("v", "V", bind(v)); };
    h.frame();
    EXPECT_FLOAT_EQ(h.w("v").rect.h, unit);
  }
}
