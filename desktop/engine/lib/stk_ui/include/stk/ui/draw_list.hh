/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Backend-neutral draw list produced by ui_core and consumed by a Painter (ui_gpu draws it with
 * the GPU module and BLF; tests serialize it to JSON goldens). Coordinates are window pixels,
 * origin top-left.
 *
 * RoundBox maps 1:1 onto Blender's widget-base shader parameters (rect, radius, corner mask,
 * inner/outline/emboss colours and the "tria" decorations: number arrows, menu chevron, check
 * mark, dash), so painted widgets look like Blender's.
 */
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "stk/ui/geom.hh"
#include "stk/ui/text.hh"

namespace stk::ui {

enum Corner : uint8_t {
  CORNER_TOP_LEFT = 1 << 0,
  CORNER_TOP_RIGHT = 1 << 1,
  CORNER_BOTTOM_RIGHT = 1 << 2,
  CORNER_BOTTOM_LEFT = 1 << 3,
  CORNER_NONE = 0,
  CORNER_ALL = 0xF,
  CORNER_TOP = CORNER_TOP_LEFT | CORNER_TOP_RIGHT,
  CORNER_BOTTOM = CORNER_BOTTOM_LEFT | CORNER_BOTTOM_RIGHT,
  CORNER_LEFT = CORNER_TOP_LEFT | CORNER_BOTTOM_LEFT,
  CORNER_RIGHT = CORNER_TOP_RIGHT | CORNER_BOTTOM_RIGHT,
};

/** Decorations drawn by the widget shader (Blender's ROUNDBOX_TRIA_*). */
enum class Tria : uint8_t {
  None = 0,
  ArrowLeft,  /**< Number field decrement arrow. */
  ArrowRight, /**< Number field increment arrow. */
  Menu,       /**< Down chevron of dropdowns. */
  Check,      /**< Checkbox check mark. */
  Dash,       /**< Indeterminate checkbox. */
};

enum class CmdType : uint8_t {
  RoundBox,   /**< Rounded rectangle: fill, outline, emboss, optional tria. */
  Rect,       /**< Flat filled rectangle (no AA). */
  Triangle,   /**< Filled triangle p0 p1 p2 (disclosure/sort arrows). */
  Text,       /**< One line of text; `pos` is the left end of the baseline. */
  ColorStrip, /**< Horizontal gradient through `colors` (colormap swatch). */
  Image,      /**< Textured quad (texture handle from the host), uv rect in [0, 1]. */
  ClipPush,   /**< Intersect the clip rectangle with `rect`. */
  ClipPop,
};

struct DrawCmd {
  CmdType type = CmdType::Rect;
  Rect rect;
  Color color;      /**< Fill / text / triangle colour. */
  /* RoundBox. */
  Color color2;     /**< Bottom fill colour (== color unless shaded). */
  Color outline;    /**< Alpha 0 = no outline. */
  Color emboss;     /**< Alpha 0 = no emboss. */
  float radius = 0.0f;
  uint8_t corners = CORNER_ALL;
  float line_width = 1.0f;
  Tria tria = Tria::None;
  Vec2 tria_center;
  float tria_size = 0.0f;
  Color tria_color;
  /* Triangle. */
  Vec2 p[3];
  /* Text. */
  std::string text;
  Vec2 pos;
  FontStyle font;
  /* ColorStrip. */
  std::vector<Color> colors;
  /* Image. */
  uint64_t texture = 0;
  Rect uv{0, 0, 1, 1};
};

class DrawList {
 public:
  std::vector<DrawCmd> cmds;

  void clear() { cmds.clear(); }
  size_t size() const { return cmds.size(); }

  void rect(const Rect &r, Color c);
  DrawCmd &round_box(const Rect &r, float radius, uint8_t corners, Color inner, Color outline, Color emboss = {0, 0, 0, 0});
  void triangle(Vec2 a, Vec2 b, Vec2 c, Color col);
  void text(std::string s, Vec2 baseline_left, const FontStyle &font, Color c);
  void color_strip(const Rect &r, std::vector<Color> colors);
  void image(const Rect &r, uint64_t texture, const Rect &uv, Color tint = {255, 255, 255, 255});
  void clip_push(const Rect &r);
  void clip_pop();
};

/** Renders draw lists; ui_gpu provides the GPU/BLF implementation. */
class Painter {
 public:
  virtual ~Painter() = default;
  /** Paints into the currently bound framebuffer of size `viewport` (pixels). */
  virtual void paint(const DrawList &list, Vec2 viewport) = 0;
};

}  // namespace stk::ui
