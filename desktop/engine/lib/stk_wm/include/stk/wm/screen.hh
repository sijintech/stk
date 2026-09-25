/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Screen layout (Blender's bScreen / ScrArea / ARegion model).
 *
 * A #Screen holds a tree of areas: every split node divides its rectangle horizontally (children
 * side by side) or vertically (children stacked top to bottom) with draggable splitters between
 * them; leaves are #Area objects. Each area docks its #Region objects (header on top, toolbar left,
 * sidebar right, main fill). Global areas (top bar, status bar) sit outside the tree with a fixed
 * height. Areas can be split, joined (double-click a splitter), resized with minimum sizes and
 * maximized (Ctrl+Space). The tree, area types, region sizes and area state serialize to JSON
 * (see #Screen::to_json and stk/wm/layout_store.hh).
 *
 * UI: one ui::Context per screen (= per window). Every frame each visible region builds its blocks
 * in window coordinates (Region::build_ui); popups, tooltips, modals and toasts are overlay blocks
 * above all areas. Painting goes region by region: the region's GPU content (Region::draw), then
 * its UI blocks, then the overlays on top. Events go to the UI first (widgets, popups, text
 * editing, IME), then to the region / area under the pointer. Redraw is on demand: per-region
 * redraw tags plus wake-up timers for tooltips and toasts.
 *
 * A Screen does not need a GHOST window: headless rendering and the unit tests lay out and build
 * the same screen (the tests with ui::FakeTextMeasurer and no GPU).
 *
 * All #Rect values are framebuffer pixels, origin bottom-left, half-open ([min, max)). UI toolkit
 * rectangles (ui::Rect) are window pixels with the origin top-left.
 */
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include "stk/wm/event.hh"

namespace stk::gfx {
struct FontStack;
}
namespace stk::ui {
class Clipboard;
class Context;
class TextMeasurer;
struct ContextConfig;
struct Rect;
}  // namespace stk::ui

namespace stk::wm {

class Area;
class Screen;
class Window;
struct ScreenNode;

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
  /** The window being drawn; nullptr for headless rendering and tests. */
  Window *window = nullptr;
  /** UI scale: native DPI factor x user scale (1.0 = 96 DPI). */
  float ui_scale = 1.0f;
  const gfx::FontStack *fonts = nullptr;
  /** Region rectangle in window pixels (the whole screen for Screen calls). */
  Rect rect;
  /** Frame time in seconds; < 0 uses the window manager's clock (or the last time, headless). */
  double now = -1.0;
  /** The screen's UI context (set for region calls once it exists). */
  ui::Context *ui = nullptr;
};

/** Height of a one-row UI bar (area header, top bar, status bar): 1 UI unit + panel margin. */
int ui_bar_height_px(float ui_scale);

enum class RegionAlign : uint8_t { Top, Bottom, Left, Right, Fill };

/**
 * A rectangular part of an area with its own drawing and event handling. UI regions override
 * #build_ui; regions with GPU content (a 3D viewport) override #draw and usually make their UI
 * block transparent (ui::Block::set_background with alpha 0) and set #ui_pass_through.
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
  /** Sets the size at scale 1 (clamped to [min_size_1x, max_size_1x] for resizable regions). */
  void set_size_1x(float size);
  /** Size in pixels at `ui_scale` (width for Left/Right, height for Top/Bottom). */
  virtual int size_px(float ui_scale) const;
  /** Current rectangle in window pixels (valid after Screen::layout; empty while hidden). */
  const Rect &rect() const
  {
    return rect_;
  }
  bool visible() const
  {
    return visible_;
  }
  /** Shows or collapses the region (side regions: toolbar, sidebar). */
  void set_visible(bool visible);
  Area *area() const
  {
    return area_;
  }
  Screen *screen() const;

  /** Side regions whose inner edge the user can drag (size clamped to the limits below). */
  bool resizable = false;
  float min_size_1x = 0.0f;
  float max_size_1x = 1.0e6f;
  /**
   * Pointer events over the region that do not hit a UI widget go to #handle_event instead of
   * the UI (for GPU content under a transparent UI block).
   */
  bool ui_pass_through = false;
  /** Persist size and visibility with the layout (default true for non-Fill regions). */
  bool persistent = true;

  /** Requests a redraw of this region (and the window showing it). */
  void tag_redraw();
  /** Tagged since the last frame (regions with cached GPU content re-render only then). */
  bool redraw_tagged() const
  {
    return redraw_;
  }

  /** Unique UI block name of this region: "<area id>/<region name>". */
  std::string block_name() const;
  /** #rect in UI toolkit coordinates (window pixels, origin top-left). */
  ui::Rect ui_rect() const;

  /**
   * Builds the region's UI blocks for this frame (between ui::Context::begin_frame and
   * end_frame; usually `ctx.ui->block(block_name(), ui_rect())`). Default: nothing.
   */
  virtual void build_ui(ui::Context &ui, const DrawContext &ctx);
  /**
   * Draws GPU content under the region's UI blocks. A pixel-space projection with the origin at
   * the region's bottom-left is active, and the viewport and scissor are limited to #rect.
   */
  virtual void draw(const DrawContext &ctx);
  /**
   * Handles an event not consumed by the UI (coordinates in window pixels; subtract
   * `rect().xmin/ymin` for local). Return true when consumed. Pointer events go to the region
   * under the cursor (or the one that received the button press until release); keyboard and
   * IME events go to the region under the pointer, else the last clicked one.
   */
  virtual bool handle_event(const Event &event, const DrawContext &ctx);
  /** Called after the rectangle changed. */
  virtual void on_layout(const DrawContext &ctx);

 private:
  friend class Area;
  friend class Screen;
  std::string name_;
  RegionAlign align_;
  float size_1x_;
  bool visible_ = true;
  bool redraw_ = true;
  Rect rect_;
  Area *area_ = nullptr;
};

/**
 * A leaf of the screen tree: a set of docked regions showing one editor. Applications subclass it
 * (stk_app's EditorArea) and install a factory on the screen (#Screen::set_area_factory) so that
 * split and layout restore can create areas by type.
 */
class Area {
 public:
  /** `type` identifies the content (editor type, e.g. "jobs"); persisted with the layout. */
  explicit Area(std::string type, float weight = 1.0f);
  virtual ~Area();
  Area(const Area &) = delete;
  Area &operator=(const Area &) = delete;

  /** Unique within the screen ("a1", "a2", ...), assigned when the area is added. */
  const std::string &id() const
  {
    return id_;
  }
  const std::string &type() const
  {
    return type_;
  }
  void set_type(std::string type);
  /** Same as #type (WP1 name). */
  const std::string &name() const
  {
    return type_;
  }
  /** Share of the parent split (normalized over the siblings). */
  float weight() const;
  void set_weight(float weight);
  const Rect &rect() const
  {
    return rect_;
  }
  Screen *screen() const
  {
    return screen_;
  }
  /** The tree node of this area (nullptr for global areas and detached areas). */
  ScreenNode *node() const
  {
    return node_;
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

  /** Minimum size at scale 1 (the docked regions add to it). */
  float min_width_1x = 100.0f;
  float min_height_1x = 24.0f;
  int min_width(float ui_scale) const;
  int min_height(float ui_scale) const;

  void tag_redraw();

  /* Hooks. */

  /** Files (`event.paths`) or text (`event.text`) dropped on the area. True when handled. */
  virtual bool on_drop(const Event &event);
  /** Events no region consumed (area shortcuts, pointer events on empty space). */
  virtual bool handle_event(const Event &event, const DrawContext &ctx);
  /** Per-area state persisted with the layout (JSON object). */
  virtual nlohmann::json save_state() const;
  /** Restores #save_state output; false rejects the layout (the caller falls back). */
  virtual bool load_state(const nlohmann::json &state);
  /** Called after the area was put into a screen. */
  virtual void on_added();

 private:
  friend class Screen;
  void layout(const Rect &rect, const DrawContext &ctx);

  std::string id_;
  std::string type_;
  float initial_weight_;
  Rect rect_;
  Screen *screen_ = nullptr;
  ScreenNode *node_ = nullptr;
  std::vector<std::unique_ptr<Region>> regions_;
};

enum class SplitDir : uint8_t {
  /** Children side by side, left to right (vertical splitter bars). */
  Horizontal,
  /** Children stacked top to bottom (horizontal splitter bars). */
  Vertical,
};
const char *split_dir_name(SplitDir dir);

/** Node of the screen tree: a leaf holds an area; a split holds two or more children. */
struct ScreenNode {
  SplitDir dir = SplitDir::Horizontal;
  /** Share of the parent's available length (normalized over the siblings). */
  float factor = 1.0f;
  std::vector<std::unique_ptr<ScreenNode>> children;
  std::unique_ptr<Area> area;
  ScreenNode *parent = nullptr;
  Rect rect;

  bool leaf() const
  {
    return area != nullptr;
  }
};

/** The bar between children `index` and `index + 1` of a split node (valid after layout). */
struct Splitter {
  ScreenNode *node = nullptr;
  int index = 0;
  SplitDir dir = SplitDir::Horizontal;
  /** The gap between the two children. */
  Rect rect;
};

class Screen {
 public:
  Screen();
  ~Screen();
  Screen(const Screen &) = delete;
  Screen &operator=(const Screen &) = delete;

  /* ------------------------------------------------------------------ */
  /** \name Tree
   * \{ */

  /**
   * Adds an area to the right of the existing ones (WP1 convenience; the root becomes a
   * horizontal split). `weight` is its share.
   */
  Area &add_area(std::unique_ptr<Area> area);
  Area &add_area(std::string type, float weight = 1.0f)
  {
    return add_area(std::make_unique<Area>(std::move(type), weight));
  }
  /** Replaces the whole tree with a single area. */
  Area &set_root(std::unique_ptr<Area> area);
  /** Removes all areas of the tree (global areas stay). */
  void clear();
  const ScreenNode *root() const
  {
    return root_.get();
  }
  /** Areas of the tree in depth-first order (left to right, top to bottom). */
  std::vector<Area *> areas() const;
  Area *find_area(std::string_view id) const;
  /** Area (tree or global) under a window position. */
  Area *area_at(int x, int y) const;

  /**
   * Splits `area` along `dir`: the new area (same type, state copied via save_state/load_state)
   * gets `factor` of the length, after `area` (or before with `new_first`). Returns nullptr when
   * the result would violate minimum sizes (after a layout) or no factory can create the type.
   */
  Area *split(Area &area, SplitDir dir, float factor = 0.5f, bool new_first = false);
  /** `keep` and `remove` are adjacent siblings in one split (they share a full edge). */
  bool can_join(const Area &keep, const Area &remove) const;
  /** `keep` takes over the space of `remove`, which is destroyed. */
  bool join(Area &keep, Area &remove);
  /** Adjacent sibling area after (`forward`) or before `area`, if it is a leaf. */
  Area *sibling(const Area &area, bool forward) const;

  /** Creates areas by type for split and layout restore (default: plain Area). */
  using AreaFactory = std::function<std::unique_ptr<Area>(const std::string &type)>;
  void set_area_factory(AreaFactory factory)
  {
    factory_ = std::move(factory);
  }
  std::unique_ptr<Area> create_area(const std::string &type) const;

  /** Fixed-height areas outside the tree (top bar at the top, status bar at the bottom). */
  Area &set_global_area(RegionAlign edge, std::unique_ptr<Area> area);
  Area *global_area(RegionAlign edge) const;

  /** Shows `area` over the whole tree rectangle (nullptr restores). */
  void set_maximized(Area *area);
  Area *maximized() const
  {
    return maximized_;
  }
  /** Maximizes `area`, or restores when it (or anything) is maximized. */
  void toggle_maximized(Area *area);

  /** \} */

  /* ------------------------------------------------------------------ */
  /** \name Splitters
   * \{ */

  const std::vector<Splitter> &splitters() const
  {
    return splitters_;
  }
  /** Splitter under a window position (hit zone widened to at least `splitter_hit_1x`). */
  const Splitter *splitter_at(int x, int y) const;
  /**
   * Resizes child `index` of a split node to `size_px` along the split, taking the difference
   * from child `index + 1` (both kept at their minimum sizes); the other children keep their
   * size. Returns the size applied.
   */
  int resize_split(ScreenNode &node, int index, int size_px);

  /** Gap between areas at UI scale 1.0 (Blender's area border). */
  float area_gap_1x = 2.0f;
  /** Pointer tolerance around splitters and resizable region edges at UI scale 1.0. */
  float splitter_hit_1x = 3.0f;
  /** Clear color behind areas (gaps), RGBA 0..1 as written to the framebuffer. */
  float background[4] = {0.086f, 0.086f, 0.086f, 1.0f};

  /** \} */

  /* ------------------------------------------------------------------ */
  /** \name Layout, UI and drawing
   * \{ */

  /** Computes area and region rectangles for `rect` (normally the whole framebuffer). */
  void layout(const Rect &rect, const DrawContext &ctx);
  const Rect &rect() const
  {
    return rect_;
  }
  /** The tree's rectangle (the screen minus the global areas). */
  const Rect &tree_rect() const
  {
    return tree_rect_;
  }
  float ui_scale() const
  {
    return scale_;
  }

  /**
   * UI context configuration (catalog, clipboard, theme, text measurer). The context is created
   * on the first #update; missing measurer / clipboard are filled in from the draw context
   * (BLF measurer on the font stack, the window manager's clipboard).
   */
  void set_ui_config(const ui::ContextConfig &config);
  /** The UI context (nullptr before the first #update). */
  ui::Context *ui() const
  {
    return ui_.get();
  }
  /** Converts a window rectangle to UI toolkit coordinates (top-left origin). */
  ui::Rect to_ui(const Rect &r) const;

  /** Layout plus one UI frame (every visible region's build_ui). No GPU calls. */
  void update(const DrawContext &ctx);
  /**
   * #update, then paints all visible regions into the currently bound framebuffer (window back
   * buffer or offscreen). The caller has set the viewport to the full framebuffer. With a window,
   * also places the IME candidate window and schedules the UI wake-up timer.
   */
  void draw(const DrawContext &ctx);
  /** Routes an event (see the file comment); true when consumed. */
  bool dispatch(const Event &event, const DrawContext &ctx);

  /** Events nobody consumed (application shortcuts such as Ctrl+Q). */
  std::function<bool(const Event &)> on_unhandled_event;

  /**
   * Runs `fn` after the current event dispatch (or before the next frame). UI callbacks use it
   * for structural changes (split, join, switching editors) that destroy regions or areas.
   */
  void defer(std::function<void()> fn);
  /** Runs the deferred calls now (dispatch and update do this). */
  void run_deferred();
  /** The tree area that last had the pointer (Blender's active area); nullptr when none. */
  Area *active_area() const
  {
    return active_area_;
  }

  /** IME caret while a text field is edited (window pixels, bottom-left origin). */
  std::optional<Rect> ime_caret() const;
  /** An IME composition is in progress in the edited field. */
  bool ime_composing() const;
  /** Absolute time (seconds) of the next timed UI change (tooltip, toast); +inf when idle. */
  double next_wakeup() const;

  Region *focused_region() const
  {
    return focus_;
  }
  void set_focus(Region *region);
  /** Region under the pointer at the last pointer event. */
  Region *hovered_region() const
  {
    return hover_;
  }
  Region *find_region(const std::string &name) const;
  Region *region_at(int x, int y) const;
  /** Visible regions in paint order (tree areas, then global areas). */
  std::vector<Region *> visible_regions() const;

  enum class Capture : uint8_t { None, Ui, Region, Splitter, RegionEdge };
  Capture capture() const
  {
    return capture_;
  }

  bool needs_redraw() const
  {
    return needs_redraw_;
  }
  /** Tags every region for redraw. */
  void tag_redraw();
  void clear_redraw()
  {
    needs_redraw_ = false;
  }
  /** Called when a redraw is requested (set by the owning Window). */
  std::function<void()> on_redraw_request;
  /** Frames built so far (tests). */
  uint64_t frames_built() const
  {
    return frames_built_;
  }

  /** \} */

  /* ------------------------------------------------------------------ */
  /** \name Persistence
   * \{ */

  /**
   * {"maximized": id|null, "root": node}; node = {"factor", "area": {"id", "type",
   * "regions": [{"name", "size", "visible"}], "state": {...}}} or {"factor",
   * "split": "horizontal"|"vertical", "children": [node, ...]}.
   */
  nlohmann::json to_json() const;
  /**
   * Rebuilds the tree from #to_json output through the area factory. Validates everything first:
   * on any error returns false with `r_error` and leaves the screen unchanged.
   */
  bool from_json(const nlohmann::json &json, std::string *r_error = nullptr);

  /** \} */

 private:
  friend class Region;
  friend class Area;
  struct Impl;

  void attach(Area &area, ScreenNode *node);
  void detach(Area &area);
  void layout_node(ScreenNode &node, const Rect &rect, const DrawContext &ctx);
  int min_extent(const ScreenNode &node, SplitDir along, float scale) const;
  void forget(const Area &area);
  void ensure_ui(const DrawContext &ctx);
  bool dispatch_event(const Event &event, const DrawContext &ctx);
  bool dispatch_pointer(const Event &event, const DrawContext &ctx);
  bool dispatch_keyboard(const Event &event, const DrawContext &ctx);
  bool send_ui(const Event &event, bool *r_consumed_any = nullptr);
  bool send_region(Region *region, const Event &event, const DrawContext &ctx);
  bool ui_widget_at(int x, int y) const;
  bool ui_busy() const;
  Region *edge_region_at(int x, int y) const;
  void after_draw(const DrawContext &ctx);
  double frame_time(const DrawContext &ctx);
  DrawContext region_ctx(const DrawContext &ctx, const Region &region) const;

  std::unique_ptr<ScreenNode> root_;
  std::unique_ptr<Area> top_, bottom_;
  Area *maximized_ = nullptr;
  AreaFactory factory_;
  int next_id_ = 1;

  Rect rect_;
  Rect tree_rect_;
  float scale_ = 1.0f;
  std::vector<Splitter> splitters_;

  std::unique_ptr<Impl> impl_;
  std::unique_ptr<ui::Context> ui_;

  Region *focus_ = nullptr;
  Region *hover_ = nullptr;
  Area *active_area_ = nullptr;
  std::vector<std::function<void()>> deferred_;
  Capture capture_ = Capture::None;
  Region *capture_region_ = nullptr;
  bool needs_redraw_ = true;
  uint64_t frames_built_ = 0;
};

}  // namespace stk::wm
