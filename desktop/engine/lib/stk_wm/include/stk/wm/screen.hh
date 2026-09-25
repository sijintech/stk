/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Screen layout: a screen holds areas, an area holds regions (Blender's bScreen / ScrArea /
 * ARegion model, reduced to what WP1 needs). Areas are laid out side by side by weight and
 * regions are docked inside their area (top / bottom / left / right, then fill). Splitters,
 * popups and layout persistence come with WP3 on top of this.
 *
 * A Screen does not need a GHOST window: headless rendering lays out and draws the same screen
 * into an offscreen framebuffer, so GUI and `--headless` exports share one code path.
 *
 * All rectangles are framebuffer pixels, origin bottom-left, half-open ([min, max)).
 */
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include "stk/wm/event.hh"

namespace stk::gfx {
struct FontStack;
}

namespace stk::wm {

class Area;
class Screen;
class Window;

struct Rect {
  int xmin = 0, ymin = 0, xmax = 0, ymax = 0;

  int width() const
  {
    return xmax - xmin;
  }
  int height() const
  {
    return ymax - ymin;
  }
  bool empty() const
  {
    return xmax <= xmin || ymax <= ymin;
  }
  bool contains(const int x, const int y) const
  {
    return x >= xmin && x < xmax && y >= ymin && y < ymax;
  }
  bool operator==(const Rect &o) const = default;
};

/** Everything a region needs to draw or handle events. */
struct DrawContext {
  /** The window being drawn; nullptr for headless rendering. */
  Window *window = nullptr;
  /** UI scale: native DPI factor x user scale (1.0 = 96 DPI). */
  float ui_scale = 1.0f;
  const gfx::FontStack *fonts = nullptr;
  /** Region rectangle in window pixels. Drawing happens in region-local pixel space. */
  Rect rect;
};

enum class RegionAlign : uint8_t { Top, Bottom, Left, Right, Fill };

/**
 * A rectangular part of an area with its own drawing and event handling. Subclass and override
 * #draw / #handle_event. Redraw happens on demand only: call #tag_redraw when state changes.
 */
class Region {
 public:
  /**
   * \param size_1x: width (Left/Right) or height (Top/Bottom) in pixels at UI scale 1.0;
   * ignored for Fill.
   */
  explicit Region(std::string name, RegionAlign align = RegionAlign::Fill, float size_1x = 0.0f);
  virtual ~Region() = default;
  Region(const Region &) = delete;
  Region &operator=(const Region &) = delete;

  const std::string &name() const
  {
    return name_;
  }
  RegionAlign align() const
  {
    return align_;
  }
  float size_1x() const
  {
    return size_1x_;
  }
  void set_size_1x(float size);
  /** Current rectangle in window pixels (valid after Screen::layout). */
  const Rect &rect() const
  {
    return rect_;
  }
  bool visible() const
  {
    return visible_;
  }
  void set_visible(bool visible);
  Area *area() const
  {
    return area_;
  }
  Screen *screen() const;

  /** Requests a redraw of the window showing this region. */
  void tag_redraw();

  /**
   * Draws the region. A pixel-space projection with the origin at the region's bottom-left is
   * active, and the viewport and scissor are limited to #rect.
   */
  virtual void draw(const DrawContext &ctx);
  /**
   * Handles an event (coordinates in window pixels; subtract `rect().xmin/ymin` for local).
   * Return true when consumed. Pointer events go to the region under the cursor (or the one that
   * received the button press until release); keyboard and IME events go to the focused region.
   */
  virtual bool handle_event(const Event &event, const DrawContext &ctx);
  /** Called after the rectangle changed. */
  virtual void on_layout(const DrawContext &ctx);

 private:
  friend class Area;
  std::string name_;
  RegionAlign align_;
  float size_1x_;
  bool visible_ = true;
  Rect rect_;
  Area *area_ = nullptr;
};

class Area {
 public:
  explicit Area(std::string name, float weight = 1.0f);
  Area(const Area &) = delete;
  Area &operator=(const Area &) = delete;

  const std::string &name() const
  {
    return name_;
  }
  float weight() const
  {
    return weight_;
  }
  void set_weight(float weight);
  const Rect &rect() const
  {
    return rect_;
  }
  Screen *screen() const
  {
    return screen_;
  }

  /** Adds a region; docked regions are carved from the area in insertion order. */
  Region &add_region(std::unique_ptr<Region> region);
  template<typename T, typename... Args> T &emplace_region(Args &&...args)
  {
    return static_cast<T &>(add_region(std::make_unique<T>(std::forward<Args>(args)...)));
  }
  const std::vector<std::unique_ptr<Region>> &regions() const
  {
    return regions_;
  }
  Region *find_region(const std::string &name) const;
  Region *region_at(int x, int y) const;

 private:
  friend class Screen;
  void layout(const Rect &rect, const DrawContext &ctx);

  std::string name_;
  float weight_;
  Rect rect_;
  Screen *screen_ = nullptr;
  std::vector<std::unique_ptr<Region>> regions_;
};

class Screen {
 public:
  Screen() = default;
  Screen(const Screen &) = delete;
  Screen &operator=(const Screen &) = delete;

  /** Adds an area; areas share the screen width by weight, left to right. */
  Area &add_area(std::unique_ptr<Area> area);
  Area &add_area(std::string name, float weight = 1.0f)
  {
    return add_area(std::make_unique<Area>(std::move(name), weight));
  }
  const std::vector<std::unique_ptr<Area>> &areas() const
  {
    return areas_;
  }
  Region *find_region(const std::string &name) const;
  Region *region_at(int x, int y) const;

  /** Gap between areas at UI scale 1.0 (Blender's area border). */
  float area_gap_1x = 2.0f;
  /** Clear color behind areas (gaps), RGBA 0..1 as written to the framebuffer. */
  float background[4] = {0.086f, 0.086f, 0.086f, 1.0f};

  /** Computes area and region rectangles for `rect` (normally the whole framebuffer). */
  void layout(const Rect &rect, const DrawContext &ctx);
  const Rect &rect() const
  {
    return rect_;
  }
  /**
   * Draws all visible regions into the currently bound framebuffer (window back buffer or
   * offscreen). The caller has set the viewport to the full framebuffer.
   */
  void draw(const DrawContext &ctx);
  /** Routes an event to a region (see Region::handle_event); true when consumed. */
  bool dispatch(const Event &event, const DrawContext &ctx);

  Region *focused_region() const
  {
    return focus_;
  }
  void set_focus(Region *region);

  bool needs_redraw() const
  {
    return needs_redraw_;
  }
  void tag_redraw();
  void clear_redraw()
  {
    needs_redraw_ = false;
  }
  /** Called when a redraw is requested (set by the owning Window). */
  std::function<void()> on_redraw_request;

 private:
  std::vector<std::unique_ptr<Area>> areas_;
  Rect rect_;
  Region *focus_ = nullptr;
  Region *capture_ = nullptr;
  Region *hover_ = nullptr;
  bool needs_redraw_ = true;
};

}  // namespace stk::wm
