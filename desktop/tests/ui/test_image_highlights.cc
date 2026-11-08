/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include <array>
#include <cmath>
#include <limits>
#include <vector>

#include "stk/ui/golden.hh"

using namespace stk::ui;
using stk::ui::test::Harness;

namespace {

using Quad = std::array<Vec2, 4>;
using Highlights = std::vector<Quad>;

struct ImageFrame {
  bool has_image = false;
  DrawCmd image;
  Rect image_clip;
  std::vector<DrawCmd> triangles;
  std::vector<Rect> triangle_clips;
};

ImageFrame capture(const Harness &h)
{
  ImageFrame result;
  Rect clip{0, 0, h.window.x, h.window.y};
  std::vector<Rect> stack;
  for (const DrawCmd &cmd : h.ctx->draw_list().cmds) {
    if (cmd.type == CmdType::ClipPush) {
      stack.push_back(clip);
      clip = clip.intersect(cmd.rect);
    }
    else if (cmd.type == CmdType::ClipPop) {
      if (stack.empty()) {
        ADD_FAILURE() << "Unbalanced clip stack";
        return result;
      }
      clip = stack.back();
      stack.pop_back();
    }
    else if (cmd.type == CmdType::Image) {
      EXPECT_FALSE(result.has_image);
      result.has_image = true;
      result.image = cmd;
      result.image_clip = clip;
    }
    else if (cmd.type == CmdType::Triangle) {
      EXPECT_TRUE(result.has_image) << "Highlights must be drawn after the image";
      result.triangles.push_back(cmd);
      result.triangle_clips.push_back(clip);
    }
  }
  EXPECT_TRUE(stack.empty());
  return result;
}

void expect_quad(const ImageFrame &frame, const Quad &quad, int width, int height, Color color)
{
  ASSERT_TRUE(frame.has_image);
  ASSERT_EQ(frame.triangles.size(), 2u);
  ASSERT_EQ(frame.triangle_clips.size(), 2u);
  const Rect &r = frame.image.rect;
  constexpr int corners[2][3] = {{0, 1, 2}, {0, 2, 3}};
  for (size_t t = 0; t < 2; ++t) {
    EXPECT_EQ(frame.triangles[t].color, color);
    EXPECT_EQ(frame.triangle_clips[t], frame.image_clip.intersect(r));
    for (size_t p = 0; p < 3; ++p) {
      const Vec2 source = quad[corners[t][p]];
      EXPECT_NEAR(frame.triangles[t].p[p].x, r.x + double(source.x) / width * r.w, 0.0001);
      EXPECT_NEAR(frame.triangles[t].p[p].y, r.y + double(source.y) / height * r.h, 0.0001);
    }
  }
}

void expect_finite_commands(const Context &ctx)
{
  for (const DrawCmd &cmd : ctx.draw_list().cmds) {
    EXPECT_TRUE(std::isfinite(cmd.rect.x));
    EXPECT_TRUE(std::isfinite(cmd.rect.y));
    EXPECT_TRUE(std::isfinite(cmd.rect.w));
    EXPECT_TRUE(std::isfinite(cmd.rect.h));
    for (const Vec2 point : cmd.p) {
      EXPECT_TRUE(std::isfinite(point.x));
      EXPECT_TRUE(std::isfinite(point.y));
    }
  }
}

}  // namespace

TEST(ImageHighlights, FollowTheDisplayedImageThroughLetterboxingZoomAndPan)
{
  Harness h(1, false);
  const Quad quad{{{100, 80}, {500, 80}, {500, 180}, {100, 180}}};
  ImageSpec spec{601, 1000, 500, 8};
  spec.highlights = std::make_shared<const Highlights>(Highlights{quad});
  spec.highlight_color = {230, 180, 40, 91};
  float width = 300;
  h.ui = [&](Context &ctx) { ctx.block("main", {20, 30, width, 250}).layout().image("page", spec); };
  h.frame();

  const ImageFrame initial = capture(h);
  ASSERT_TRUE(initial.has_image);
  EXPECT_GT(initial.image.rect.y, h.w("main/page").rect.y + h.ctx->style().pixel);
  EXPECT_EQ(initial.image.texture, 601u);
  EXPECT_EQ(initial.image.uv, (Rect{0, 0, 1, 1}));
  expect_quad(initial, quad, spec.width, spec.height, spec.highlight_color);

  h.send(Event::wheel(h.center("main/page"), 1));
  const ImageFrame zoomed = capture(h);
  ASSERT_TRUE(zoomed.has_image);
  EXPECT_GT(zoomed.image.rect.w, initial.image.rect.w);
  expect_quad(zoomed, quad, spec.width, spec.height, spec.highlight_color);

  const Vec2 from = h.center("main/page");
  h.drag(from, {from.x + 23, from.y + 17});
  const ImageFrame panned = capture(h);
  ASSERT_TRUE(panned.has_image);
  EXPECT_FLOAT_EQ(panned.image.rect.x, zoomed.image.rect.x + 23);
  EXPECT_FLOAT_EQ(panned.image.rect.y, zoomed.image.rect.y + 17);
  EXPECT_FLOAT_EQ(panned.image.rect.w, zoomed.image.rect.w);
  EXPECT_FLOAT_EQ(panned.image.rect.h, zoomed.image.rect.h);
  expect_quad(panned, quad, spec.width, spec.height, spec.highlight_color);
  EXPECT_EQ(panned.image.texture, initial.image.texture);
  width = 240;
  h.frame();
  const ImageFrame resized = capture(h);
  ASSERT_TRUE(resized.has_image);
  EXPECT_NE(resized.image.rect.x, panned.image.rect.x);
  expect_quad(resized, quad, spec.width, spec.height, spec.highlight_color);
  expect_finite_commands(*h.ctx);
}

TEST(ImageHighlights, OutsideQuadsAreClippedToTheImageAndViewport)
{
  Harness h(1.5f, false);
  /* This quad reaches into letterboxing and, after zoom/pan, beyond the viewport. */
  const Quad quad{{{-100, -100}, {1100, -100}, {1100, 600}, {-100, 600}}};
  ImageSpec spec{602, 1000, 500, 8};
  spec.highlights = std::make_shared<const Highlights>(Highlights{quad});
  h.ui = [&](Context &ctx) { ctx.block("main", {20, 30, 330, 300}).layout().image("page", spec); };
  h.frame();
  const ImageFrame initial = capture(h);
  ASSERT_TRUE(initial.has_image);
  ASSERT_EQ(initial.triangle_clips.size(), 2u);
  EXPECT_GT(initial.image.rect.y, initial.image_clip.y);
  expect_quad(initial, quad, spec.width, spec.height, spec.highlight_color);
  EXPECT_GT(initial.triangle_clips[0].y, initial.image_clip.y);

  h.send(Event::wheel(h.center("main/page"), 3));
  const Vec2 from = h.center("main/page");
  h.drag(from, {from.x + 90, from.y + 15});
  const ImageFrame moved = capture(h);
  ASSERT_TRUE(moved.has_image);
  ASSERT_EQ(moved.triangle_clips.size(), 2u);
  EXPECT_GT(moved.image.rect.w, moved.image_clip.w);
  expect_quad(moved, quad, spec.width, spec.height, spec.highlight_color);
  EXPECT_LT(moved.triangle_clips[0].w, moved.image.rect.w);
  expect_finite_commands(*h.ctx);
}

TEST(ImageHighlights, EmptyAndClearedOverlaysPreserveTheLegacyFrame)
{
  Harness h(1, false);
  ImageSpec spec{603, 640, 480, 8};
  EXPECT_FALSE(spec.highlights);
  EXPECT_GT(spec.highlight_color.a, 0);
  EXPECT_LT(spec.highlight_color.a, 255);
  h.ui = [&](Context &ctx) { ctx.block("main", {20, 30, 300, 250}).layout().image("page", spec); };
  h.frame();
  const std::string legacy = dump_frame(*h.ctx);
  spec.highlights = std::make_shared<const Highlights>();
  h.frame();
  EXPECT_EQ(dump_frame(*h.ctx), legacy);
  spec.highlights = std::make_shared<const Highlights>(Highlights{Quad{{{10, 10}, {50, 10}, {50, 40}, {10, 40}}}});
  h.frame();
  EXPECT_EQ(capture(h).triangles.size(), 2u);
  EXPECT_NE(dump_frame(*h.ctx), legacy);
  spec.highlights.reset();
  h.frame();
  EXPECT_EQ(dump_frame(*h.ctx), legacy);
}

TEST(ImageHighlights, NonfiniteAndOverflowingQuadsNeverReachDrawCommands)
{
  Harness h(1, false);
  const Quad valid{{{0.1f, 0.1f}, {0.9f, 0.1f}, {0.9f, 0.9f}, {0.1f, 0.9f}}};
  Highlights quads{valid};
  for (const float bad : {std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity(),
                          -std::numeric_limits<float>::infinity(), std::numeric_limits<float>::max(),
                          -std::numeric_limits<float>::max()}) {
    for (size_t axis = 0; axis < 2; ++axis) {
      Quad quad = valid;
      if (axis == 0) {
        quad[3].x = bad;
      }
      else {
        quad[3].y = bad;
      }
      quads.push_back(quad);
    }
  }
  ImageSpec spec{604, 1, 1, 8};
  spec.highlights = std::make_shared<const Highlights>(quads);
  h.ui = [&](Context &ctx) { ctx.block("main", {20, 30, 300, 250}).layout().image("page", spec); };
  h.frame();
  const ImageFrame frame = capture(h);
  ASSERT_TRUE(frame.has_image);
  ASSERT_GT(frame.image.rect.w, 1);
  expect_quad(frame, valid, spec.width, spec.height, spec.highlight_color);
  expect_finite_commands(*h.ctx);

  /* Unknown source dimensions keep legacy image behavior without dividing overlay pixels. */
  for (const std::array<int, 2> size : {std::array<int, 2>{0, 1}, {1, 0}, {-1, 1}, {1, -1}}) {
    spec.width = size[0];
    spec.height = size[1];
    h.frame();
    EXPECT_TRUE(capture(h).triangles.empty());
    expect_finite_commands(*h.ctx);
  }
}
