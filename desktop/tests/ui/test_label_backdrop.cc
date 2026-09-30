/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include <algorithm>

using namespace stk::ui;
using namespace stk::ui::test;

namespace {

std::vector<DrawCmd> commands(const Context &ctx, CmdType type)
{
  std::vector<DrawCmd> result;
  for (const auto &cmd : ctx.draw_list().cmds) {
    if (cmd.type == type) { result.push_back(cmd); }
  }
  return result;
}

void expect_same_rect(const Rect &a, const Rect &b)
{
  EXPECT_EQ(a.x, b.x); EXPECT_EQ(a.y, b.y);
  EXPECT_EQ(a.w, b.w); EXPECT_EQ(a.h, b.h);
}

}  // namespace

TEST(LabelBackdrop, DefaultAndExplicitOffRemainTransparent)
{
  Harness h;
  bool backdrop = false;
  h.ui = [&](Context &ctx) {
    auto &block = ctx.block("caption", {20, 30, 240, 60});
    block.set_background({0, 0, 0, 0});
    block.layout().label("Source: signed.dat").backdrop(backdrop).tip("Source details");
  };
  h.frame();
  const Widget initial = h.w("caption/#0");
  const auto initial_text = commands(*h.ctx, CmdType::Text);
  ASSERT_EQ(initial_text.size(), 1u);
  EXPECT_EQ(initial_text[0].color, h.ctx->theme().space_text);
  EXPECT_TRUE(commands(*h.ctx, CmdType::RoundBox).empty());
  EXPECT_TRUE(commands(*h.ctx, CmdType::Rect).empty());
  backdrop = true;
  h.frame();
  const auto boxes = commands(*h.ctx, CmdType::RoundBox);
  ASSERT_EQ(boxes.size(), 1u);
  expect_same_rect(boxes[0].rect, initial.rect);
  expect_same_rect(h.w("caption/#0").rect, initial.rect);
  expect_same_rect(h.w("caption/#0").clip, initial.clip);
  EXPECT_EQ(h.w("caption/#0").id, initial.id);
  const auto backed_text = commands(*h.ctx, CmdType::Text);
  ASSERT_EQ(backed_text.size(), 1u);
  EXPECT_EQ(backed_text[0].text, initial_text[0].text);
  EXPECT_EQ(backed_text[0].pos.x, initial_text[0].pos.x);
  EXPECT_EQ(backed_text[0].pos.y, initial_text[0].pos.y);
  backdrop = false;
  h.frame();
  EXPECT_TRUE(commands(*h.ctx, CmdType::RoundBox).empty());
  EXPECT_EQ(commands(*h.ctx, CmdType::Text)[0].color, initial_text[0].color);
  Widget ordinary;
  EXPECT_FALSE(ordinary.label_backdrop);
}

TEST(LabelBackdrop, OpaqueBackgroundUsesTheThemesPairedColors)
{
  FakeTextMeasurer measurer;
  for (const bool light : {false, true}) {
    SCOPED_TRACE(light ? "custom light theme" : "default dark theme");
    ContextConfig cfg;
    cfg.measurer = &measurer;
    if (light) {
      cfg.theme.tooltip.inner = {231, 237, 242, 32};
      cfg.theme.tooltip.text = {23, 29, 34, 17};
      cfg.theme.space_text = {255, 0, 0, 255};
      cfg.theme.tooltip.roundness = 0.1f;
    }
    Context ctx(cfg);
    ctx.begin_frame({300, 100}, 1);
    auto &block = ctx.block("caption", {0, 0, 300, 100});
    block.set_background({0, 0, 0, 0});
    block.layout().label("Source and range").backdrop();
    ctx.end_frame();
    const auto boxes = commands(ctx, CmdType::RoundBox);
    const auto text = commands(ctx, CmdType::Text);
    ASSERT_EQ(boxes.size(), 1u); ASSERT_EQ(text.size(), 1u);
    EXPECT_EQ(boxes[0].color, cfg.theme.tooltip.inner.with_alpha(255));
    EXPECT_EQ(boxes[0].color2, boxes[0].color);
    EXPECT_EQ(boxes[0].outline.a, 0);
    EXPECT_EQ(boxes[0].emboss.a, 0);
    EXPECT_EQ(text[0].color, cfg.theme.tooltip.text.with_alpha(255));
    EXPECT_FLOAT_EQ(boxes[0].radius, cfg.theme.tooltip.roundness * ctx.style().unit);
  }
}

TEST(LabelBackdrop, DisabledTextIsMutedButTheBackgroundRemainsOpaque)
{
  FakeTextMeasurer measurer;
  ContextConfig cfg;
  cfg.measurer = &measurer;
  cfg.theme.tooltip.inner = {240, 235, 220, 50};
  cfg.theme.tooltip.text = {20, 30, 40, 60};
  Context ctx(cfg);
  ctx.begin_frame({300, 100}, 1);
  auto &block = ctx.block("caption", {0, 0, 300, 100});
  block.set_background({0, 0, 0, 0});
  block.layout().label("Inactive caption").backdrop().disable();
  ctx.end_frame();
  const auto boxes = commands(ctx, CmdType::RoundBox);
  const auto text = commands(ctx, CmdType::Text);
  ASSERT_EQ(boxes.size(), 1u); ASSERT_EQ(text.size(), 1u);
  EXPECT_EQ(boxes[0].color, cfg.theme.tooltip.inner.with_alpha(255));
  EXPECT_EQ(text[0].color, (Color{20, 30, 40, 128}));
  ASSERT_NE(ctx.find("caption/#0"), nullptr);
  EXPECT_FALSE(ctx.find("caption/#0")->enabled);
  EXPECT_FALSE(ctx.find("caption/#0")->focusable());
}

TEST(LabelBackdrop, HoverTooltipAndNonFocusableBehaviorAreUnchanged)
{
  Harness h;
  bool backdrop = false;
  h.ui = [&](Context &ctx) {
    auto &block = ctx.block("caption", {20, 30, 240, 60});
    block.set_background({0, 0, 0, 0});
    block.layout().label("Source").backdrop(backdrop).width(8).tip("Original source path");
  };
  h.frame();
  const auto id = h.w("caption/#0").id;
  h.move(h.center("caption/#0"));
  EXPECT_EQ(h.ctx->hovered(), id);
  h.click("caption/#0");
  EXPECT_EQ(h.ctx->focused(), 0u);
  backdrop = true;
  h.frame();
  EXPECT_EQ(h.ctx->hovered(), id);
  h.click("caption/#0");
  EXPECT_EQ(h.ctx->focused(), 0u);
  EXPECT_FALSE(h.ctx->text_input_active());
  ASSERT_TRUE(h.ctx->force_tooltip("caption/#0"));
  h.frame();
  const auto text = commands(*h.ctx, CmdType::Text);
  EXPECT_TRUE(std::any_of(text.begin(), text.end(), [](const DrawCmd &cmd) {
    return cmd.text == "Original source path";
  }));
}

TEST(LabelBackdrop, Utf8ClippingAlignmentAndScalePreserveTextGeometry)
{
  for (const float scale : {1.0f, 1.5f, 2.0f}) {
    for (const auto align : {Align::Left, Align::Center, Align::Right}) {
      SCOPED_TRACE(scale);
      Harness h(scale);
      bool backdrop = false;
      h.ui = [&](Context &ctx) {
        auto &block = ctx.block("caption", {20, 30, 190, 80});
        block.set_background({0, 0, 0, 0});
        block.layout().label("场文件 signed.dat：负值范围 −66 到 22", align).backdrop(backdrop);
      };
      h.frame();
      const auto before = commands(*h.ctx, CmdType::Text);
      ASSERT_EQ(before.size(), 1u);
      backdrop = true;
      h.frame();
      const auto after = commands(*h.ctx, CmdType::Text);
      ASSERT_EQ(after.size(), 1u);
      EXPECT_EQ(after[0].text, before[0].text);
      EXPECT_EQ(after[0].pos.x, before[0].pos.x);
      EXPECT_EQ(after[0].pos.y, before[0].pos.y);
      const Widget &w = h.w("caption/#0");
      EXPECT_LE(h.measurer.width(after[0].text, after[0].font),
                w.rect.w - 2 * h.ctx->style().text_margin + 0.5f);
      const auto boxes = commands(*h.ctx, CmdType::RoundBox);
      ASSERT_EQ(boxes.size(), 1u);
      expect_same_rect(boxes[0].rect, w.rect);
    }
  }
}

TEST(LabelBackdrop, RegionClippingAndOtherWidgetsRetainTheirBehavior)
{
  Harness h;
  bool backdrop = false;
  h.ui = [&](Context &ctx) {
    auto &block = ctx.block("caption", {20, 30, 180, 12});
    block.set_background({0, 0, 0, 0});
    block.layout().label("Partially clipped").backdrop(backdrop);
    ctx.block("controls", {220, 30, 160, 60}).layout().button("button", "Unchanged", [] {}).backdrop(backdrop);
  };
  h.frame();
  const auto before = commands(*h.ctx, CmdType::RoundBox);
  ASSERT_GE(before.size(), 1u); // The clipped region can also have a scrollbar.
  const Widget caption = h.w("caption/#0");
  backdrop = true;
  h.frame();
  const auto after = commands(*h.ctx, CmdType::RoundBox);
  ASSERT_EQ(after.size(), before.size() + 1);
  expect_same_rect(after[0].rect, caption.rect);
  expect_same_rect(after.back().rect, before.back().rect);
  EXPECT_EQ(after.back().color, before.back().color);
  EXPECT_EQ(after.back().outline, before.back().outline);
  const auto clips = commands(*h.ctx, CmdType::ClipPush);
  ASSERT_FALSE(clips.empty());
  expect_same_rect(clips.front().rect, (Rect{20, 30, 180, 12}));
  h.move({caption.rect.cx(), 45});
  EXPECT_EQ(h.ctx->hovered(), 0u) << "the backdrop must not extend hit testing outside the region";
}
