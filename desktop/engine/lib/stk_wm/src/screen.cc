/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/wm/screen.hh"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>
#include <unordered_map>
#include <unordered_set>

#include "GPU_framebuffer.hh"
#include "GPU_state.hh"

#include "stk/gfx/offscreen.hh"
#include "stk/ui/gpu_painter.hh"
#include "stk/ui/ui.hh"
#include "stk/wm/layout_math.hh"
#include "stk/wm/ui_bridge.hh"
#include "stk/wm/window.hh"

namespace stk::wm {

using namespace blender;

static int scaled(const float size_1x, const float ui_scale)
{
  return std::max(0, int(std::lround(size_1x * ui_scale)));
}

int ui_bar_height_px(const float ui_scale)
{
  const ui::Style st = ui::Style::from_scale(std::max(0.25f, ui_scale));
  return int(st.unit + st.panel_margin);
}

const char *split_dir_name(const SplitDir dir)
{
  return dir == SplitDir::Horizontal ? "horizontal" : "vertical";
}

/** Length of a rectangle along a split direction. */
static int extent(const Rect &r, const SplitDir dir)
{
  return dir == SplitDir::Horizontal ? r.width() : r.height();
}

/* -------------------------------------------------------------------- */
/** \name Screen internals
 * \{ */

struct Screen::Impl {
  /* UI hosting. */
  bool has_config = false;
  ui::ContextConfig config;
  std::unique_ptr<ui::gpu::BlfTextMeasurer> measurer;
  std::unique_ptr<ui::gpu::GpuPainter> painter;
  std::unique_ptr<WmClipboard> clipboard;
  ui::DrawList scratch;
  struct Segment {
    size_t begin = 0, end = 0;
  };
  std::unordered_map<const Region *, Segment> segments;
  double last_now = 0.0;

  /* Splitter / region edge drags. */
  ScreenNode *drag_node = nullptr;
  int drag_index = 0;
  int drag_start_size = 0;
  int drag_start_x = 0, drag_start_y = 0;
  Region *edge_region = nullptr;
  ScreenNode *click_node = nullptr;
  int click_index = -1;
  uint64_t click_time = 0;

  /* IME and wake-up timer (windows only). */
  bool ime_ours = false;
  Rect ime_caret;
  WindowManager *timer_wm = nullptr;
  uint64_t timer = 0;
  double timer_at = 0.0;
};

/** \} */

/* -------------------------------------------------------------------- */
/** \name Region
 * \{ */

Region::Region(std::string name, const RegionAlign align, const float size_1x)
    : name_(std::move(name)), align_(align), size_1x_(size_1x)
{
  persistent = align != RegionAlign::Fill;
}

Screen *Region::screen() const
{
  return area_ ? area_->screen() : nullptr;
}

void Region::set_size_1x(float size)
{
  if (!std::isfinite(size)) {
    return;
  }
  if (resizable) {
    size = std::clamp(size, min_size_1x, std::max(min_size_1x, max_size_1x));
  }
  size = std::max(0.0f, size);
  if (size != size_1x_) {
    size_1x_ = size;
    tag_redraw();
  }
}

int Region::size_px(const float ui_scale) const
{
  return scaled(size_1x_, ui_scale);
}

void Region::set_visible(const bool visible)
{
  if (visible != visible_) {
    visible_ = visible;
    if (Screen *s = screen()) {
      s->tag_redraw();
    }
  }
}

void Region::tag_redraw()
{
  redraw_ = true;
  if (Screen *s = screen()) {
    s->needs_redraw_ = true;
    if (s->on_redraw_request) {
      s->on_redraw_request();
    }
  }
}

std::string Region::block_name() const
{
  return area_ ? area_->id() + "/" + name_ : name_;
}

ui::Rect Region::ui_rect() const
{
  const Screen *s = screen();
  return s ? s->to_ui(rect_) : ui::Rect{float(rect_.xmin), 0.0f, float(rect_.width()), float(rect_.height())};
}

void Region::build_ui(ui::Context & /*ui*/, const DrawContext & /*ctx*/) {}

void Region::draw(const DrawContext & /*ctx*/) {}

bool Region::handle_event(const Event & /*event*/, const DrawContext & /*ctx*/)
{
  return false;
}

void Region::on_layout(const DrawContext & /*ctx*/) {}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Area
 * \{ */

Area::Area(std::string type, const float weight) : type_(std::move(type)), initial_weight_(weight) {}

Area::~Area() = default;

void Area::set_type(std::string type)
{
  type_ = std::move(type);
  tag_redraw();
}

float Area::weight() const
{
  return node_ ? node_->factor : initial_weight_;
}

void Area::set_weight(const float weight)
{
  const float w = std::isfinite(weight) ? std::max(weight, 0.0f) : 0.0f;
  if (node_) {
    node_->factor = w;
  }
  initial_weight_ = w;
  tag_redraw();
}

void Area::tag_redraw()
{
  for (const auto &r : regions_) {
    r->redraw_ = true;
  }
  if (screen_) {
    screen_->tag_redraw();
  }
}

Region &Area::add_region(std::unique_ptr<Region> region)
{
  region->area_ = this;
  regions_.push_back(std::move(region));
  if (screen_) {
    screen_->tag_redraw();
  }
  return *regions_.back();
}

Region *Area::find_region(const std::string &name) const
{
  for (const auto &r : regions_) {
    if (r->name() == name) {
      return r.get();
    }
  }
  return nullptr;
}

Region *Area::region_at(const int x, const int y) const
{
  /* Later regions are on top (docked regions are carved first, so they never overlap). */
  for (auto it = regions_.rbegin(); it != regions_.rend(); ++it) {
    if ((*it)->visible() && (*it)->rect().contains(x, y)) {
      return it->get();
    }
  }
  return nullptr;
}

int Area::min_width(const float ui_scale) const
{
  int sides = 0;
  for (const auto &r : regions_) {
    if (r->visible() && (r->align() == RegionAlign::Left || r->align() == RegionAlign::Right)) {
      sides += r->size_px(ui_scale);
    }
  }
  return std::max(scaled(min_width_1x, ui_scale), sides + scaled(32.0f, ui_scale));
}

int Area::min_height(const float ui_scale) const
{
  int bars = 0;
  for (const auto &r : regions_) {
    if (r->visible() && (r->align() == RegionAlign::Top || r->align() == RegionAlign::Bottom)) {
      bars += r->size_px(ui_scale);
    }
  }
  return std::max(scaled(min_height_1x, ui_scale), bars + scaled(20.0f, ui_scale));
}

bool Area::on_drop(const Event & /*event*/)
{
  return false;
}

bool Area::handle_event(const Event & /*event*/, const DrawContext & /*ctx*/)
{
  return false;
}

nlohmann::json Area::save_state() const
{
  return nlohmann::json::object();
}

bool Area::load_state(const nlohmann::json & /*state*/)
{
  return true;
}

void Area::on_added() {}

void Area::layout(const Rect &rect, const DrawContext &ctx)
{
  rect_ = rect;
  Rect free = rect;
  /* Docked regions are carved in insertion order; Fill regions take what is left, whatever
   * their position in the list (Blender's main region). */
  std::vector<Region *> order;
  for (const auto &r : regions_) {
    if (r->align() != RegionAlign::Fill) {
      order.push_back(r.get());
    }
  }
  for (const auto &r : regions_) {
    if (r->align() == RegionAlign::Fill) {
      order.push_back(r.get());
    }
  }
  for (Region *r : order) {
    Rect rr{};
    if (r->visible() && !rect.empty()) {
      const int size = r->size_px(ctx.ui_scale);
      switch (r->align()) {
        case RegionAlign::Top:
          rr = {free.xmin, std::max(free.ymin, free.ymax - size), free.xmax, free.ymax};
          free.ymax = rr.ymin;
          break;
        case RegionAlign::Bottom:
          rr = {free.xmin, free.ymin, free.xmax, std::min(free.ymax, free.ymin + size)};
          free.ymin = rr.ymax;
          break;
        case RegionAlign::Left:
          rr = {free.xmin, free.ymin, std::min(free.xmax, free.xmin + size), free.ymax};
          free.xmin = rr.xmax;
          break;
        case RegionAlign::Right:
          rr = {std::max(free.xmin, free.xmax - size), free.ymin, free.xmax, free.ymax};
          free.xmax = rr.xmin;
          break;
        case RegionAlign::Fill:
          rr = free;
          break;
      }
    }
    const bool changed = !(rr == r->rect_);
    r->rect_ = rr;
    if (changed) {
      r->redraw_ = true;
      if (!rr.empty()) {
        DrawContext rctx = ctx;
        rctx.rect = rr;
        r->on_layout(rctx);
      }
    }
  }
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Screen: tree
 * \{ */

Screen::Screen() : impl_(std::make_unique<Impl>()) {}

Screen::~Screen()
{
  if (impl_->timer && impl_->timer_wm) {
    impl_->timer_wm->remove_timer(impl_->timer);
  }
  /* The UI context references the measurer and clipboard in impl_. */
  ui_.reset();
}

static void collect_leaves(const ScreenNode *node, std::vector<Area *> &out)
{
  if (!node) {
    return;
  }
  if (node->leaf()) {
    out.push_back(node->area.get());
    return;
  }
  for (const auto &c : node->children) {
    collect_leaves(c.get(), out);
  }
}

std::vector<Area *> Screen::areas() const
{
  std::vector<Area *> out;
  collect_leaves(root_.get(), out);
  return out;
}

Area *Screen::find_area(const std::string_view id) const
{
  for (Area *a : areas()) {
    if (a->id() == id) {
      return a;
    }
  }
  for (Area *g : {top_.get(), bottom_.get()}) {
    if (g && g->id() == id) {
      return g;
    }
  }
  return nullptr;
}

Area *Screen::area_at(const int x, const int y) const
{
  for (Area *g : {top_.get(), bottom_.get()}) {
    if (g && g->rect().contains(x, y)) {
      return g;
    }
  }
  if (maximized_) {
    return maximized_->rect().contains(x, y) ? maximized_ : nullptr;
  }
  for (Area *a : areas()) {
    if (a->rect().contains(x, y)) {
      return a;
    }
  }
  return nullptr;
}

std::unique_ptr<Area> Screen::create_area(const std::string &type) const
{
  if (factory_) {
    return factory_(type);
  }
  return std::make_unique<Area>(type);
}

static int id_number(const std::string &id)
{
  if (id.size() < 2 || id[0] != 'a') {
    return 0;
  }
  int n = 0;
  for (size_t i = 1; i < id.size(); i++) {
    if (id[i] < '0' || id[i] > '9' || n > 100000000) {
      return 0;
    }
    n = n * 10 + (id[i] - '0');
  }
  return n;
}

void Screen::attach(Area &area, ScreenNode *node)
{
  area.screen_ = this;
  area.node_ = node;
  if (area.id_.empty() || (find_area(area.id_) != &area && find_area(area.id_) != nullptr)) {
    area.id_ = "a" + std::to_string(next_id_++);
  }
  next_id_ = std::max(next_id_, id_number(area.id_) + 1);
  area.on_added();
  area.tag_redraw();
}

void Screen::forget(const Area &area)
{
  for (const auto &r : area.regions()) {
    if (focus_ == r.get()) {
      focus_ = nullptr;
    }
    if (hover_ == r.get()) {
      hover_ = nullptr;
    }
    if (capture_region_ == r.get() || impl_->edge_region == r.get()) {
      capture_region_ = nullptr;
      impl_->edge_region = nullptr;
      capture_ = Capture::None;
    }
    impl_->segments.erase(r.get());
  }
  if (maximized_ == &area) {
    maximized_ = nullptr;
  }
  if (active_area_ == &area) {
    active_area_ = nullptr;
  }
  if (capture_ == Capture::Splitter) {
    capture_ = Capture::None;
  }
  impl_->drag_node = nullptr;
  impl_->click_node = nullptr;
}

void Screen::clear()
{
  for (Area *a : areas()) {
    forget(*a);
  }
  root_.reset();
  maximized_ = nullptr;
  splitters_.clear();
  tag_redraw();
}

Area &Screen::set_root(std::unique_ptr<Area> area)
{
  clear();
  root_ = std::make_unique<ScreenNode>();
  root_->factor = 1.0f;
  Area &a = *area;
  root_->area = std::move(area);
  attach(a, root_.get());
  return a;
}

Area &Screen::add_area(std::unique_ptr<Area> area)
{
  if (!root_) {
    const float w = area->initial_weight_;
    Area &a = set_root(std::move(area));
    root_->factor = w;
    return a;
  }
  if (root_->leaf() || root_->dir != SplitDir::Horizontal) {
    auto split = std::make_unique<ScreenNode>();
    split->dir = SplitDir::Horizontal;
    split->factor = 1.0f;
    root_->parent = split.get();
    split->children.push_back(std::move(root_));
    root_ = std::move(split);
  }
  auto leaf = std::make_unique<ScreenNode>();
  leaf->factor = area->initial_weight_;
  leaf->parent = root_.get();
  Area &a = *area;
  leaf->area = std::move(area);
  ScreenNode *node = leaf.get();
  root_->children.push_back(std::move(leaf));
  attach(a, node);
  return a;
}

/** The owning slot of a node (its parent's child pointer, or the root). */
static std::unique_ptr<ScreenNode> *slot_of(std::unique_ptr<ScreenNode> &root, ScreenNode *node)
{
  if (!node->parent) {
    return root.get() == node ? &root : nullptr;
  }
  for (auto &c : node->parent->children) {
    if (c.get() == node) {
      return &c;
    }
  }
  return nullptr;
}

static int index_in_parent(const ScreenNode *node)
{
  if (!node || !node->parent) {
    return -1;
  }
  const auto &cs = node->parent->children;
  for (size_t i = 0; i < cs.size(); i++) {
    if (cs[i].get() == node) {
      return int(i);
    }
  }
  return -1;
}

Area *Screen::split(Area &area, const SplitDir dir, float factor, const bool new_first)
{
  ScreenNode *leaf = area.node_;
  if (!leaf || area.screen_ != this || !std::isfinite(factor)) {
    return nullptr;
  }
  factor = std::clamp(factor, 0.05f, 0.95f);
  std::unique_ptr<Area> created = create_area(area.type());
  if (!created) {
    return nullptr;
  }
  created->load_state(area.save_state());
  for (const auto &r : created->regions()) {
    if (const Region *src = area.find_region(r->name())) {
      r->resizable = src->resizable;
      r->set_size_1x(src->size_1x());
      r->set_visible(src->visible());
    }
  }
  /* Refuse splits that cannot give both areas their minimum size (known after a layout). */
  if (!area.rect().empty()) {
    const int gap = scaled(area_gap_1x, scale_);
    const int len = extent(area.rect(), dir) - gap;
    const int new_len = int(std::lround(len * factor));
    const int old_len = len - new_len;
    const int new_min = dir == SplitDir::Horizontal ? created->min_width(scale_) : created->min_height(scale_);
    const int old_min = dir == SplitDir::Horizontal ? area.min_width(scale_) : area.min_height(scale_);
    if (new_len < new_min || old_len < old_min) {
      return nullptr;
    }
  }

  auto node = std::make_unique<ScreenNode>();
  Area &a = *created;
  node->area = std::move(created);
  ScreenNode *new_node = node.get();
  ScreenNode *parent = leaf->parent;
  if (parent && parent->dir == dir) {
    const int idx = index_in_parent(leaf);
    node->factor = leaf->factor * factor;
    leaf->factor *= 1.0f - factor;
    node->parent = parent;
    parent->children.insert(parent->children.begin() + idx + (new_first ? 0 : 1), std::move(node));
  }
  else {
    std::unique_ptr<ScreenNode> *slot = slot_of(root_, leaf);
    if (!slot) {
      return nullptr;
    }
    auto split = std::make_unique<ScreenNode>();
    split->dir = dir;
    split->factor = leaf->factor;
    split->parent = parent;
    std::unique_ptr<ScreenNode> old = std::move(*slot);
    old->factor = 1.0f - factor;
    old->parent = split.get();
    node->factor = factor;
    node->parent = split.get();
    if (new_first) {
      split->children.push_back(std::move(node));
      split->children.push_back(std::move(old));
    }
    else {
      split->children.push_back(std::move(old));
      split->children.push_back(std::move(node));
    }
    *slot = std::move(split);
  }
  attach(a, new_node);
  splitters_.clear();
  tag_redraw();
  return &a;
}

bool Screen::can_join(const Area &keep, const Area &remove) const
{
  if (&keep == &remove || keep.screen_ != this || remove.screen_ != this || !keep.node_ || !remove.node_) {
    return false;
  }
  const ScreenNode *p = keep.node_->parent;
  if (!p || p != remove.node_->parent) {
    return false;
  }
  return std::abs(index_in_parent(keep.node_) - index_in_parent(remove.node_)) == 1;
}

Area *Screen::sibling(const Area &area, const bool forward) const
{
  const ScreenNode *n = area.node_;
  if (!n || !n->parent) {
    return nullptr;
  }
  const int i = index_in_parent(n) + (forward ? 1 : -1);
  const auto &cs = n->parent->children;
  if (i < 0 || i >= int(cs.size()) || !cs[size_t(i)]->leaf()) {
    return nullptr;
  }
  return cs[size_t(i)]->area.get();
}

bool Screen::join(Area &keep, Area &remove)
{
  if (!can_join(keep, remove)) {
    return false;
  }
  ScreenNode *parent = keep.node_->parent;
  keep.node_->factor += remove.node_->factor;
  forget(remove);
  const int ri = index_in_parent(remove.node_);
  parent->children.erase(parent->children.begin() + ri);

  if (parent->children.size() == 1) {
    /* Collapse the split: its only child takes its place. */
    std::unique_ptr<ScreenNode> *slot = slot_of(root_, parent);
    std::unique_ptr<ScreenNode> child = std::move(parent->children.front());
    child->factor = parent->factor;
    child->parent = parent->parent;
    ScreenNode *grand = parent->parent;
    *slot = std::move(child); /* Destroys `parent`. */
    ScreenNode *c = slot->get();
    /* Flatten a split into a parent of the same direction. */
    if (grand && !c->leaf() && c->dir == grand->dir) {
      const int ci = index_in_parent(c);
      float sum = 0.0f;
      for (const auto &gc : c->children) {
        sum += gc->factor;
      }
      std::vector<std::unique_ptr<ScreenNode>> moved = std::move(c->children);
      const float f = c->factor;
      grand->children.erase(grand->children.begin() + ci);
      for (size_t i = 0; i < moved.size(); i++) {
        moved[i]->factor = sum > 0 ? moved[i]->factor / sum * f : f / float(moved.size());
        moved[i]->parent = grand;
        grand->children.insert(grand->children.begin() + ci + int(i), std::move(moved[i]));
      }
    }
  }
  splitters_.clear();
  tag_redraw();
  return true;
}

Area &Screen::set_global_area(const RegionAlign edge, std::unique_ptr<Area> area)
{
  std::unique_ptr<Area> &slot = edge == RegionAlign::Bottom ? bottom_ : top_;
  if (slot) {
    forget(*slot);
  }
  slot = std::move(area);
  /* Global areas are named by their type ("topbar"), outside the tree's "a<n>" sequence. */
  if (slot->id_.empty()) {
    slot->id_ = slot->type();
  }
  attach(*slot, nullptr);
  tag_redraw();
  return *slot;
}

Area *Screen::global_area(const RegionAlign edge) const
{
  return edge == RegionAlign::Bottom ? bottom_.get() : (edge == RegionAlign::Top ? top_.get() : nullptr);
}

void Screen::set_maximized(Area *area)
{
  if (area && (area->screen_ != this || !area->node_)) {
    return;
  }
  if (maximized_ != area) {
    maximized_ = area;
    splitters_.clear();
    capture_ = Capture::None;
    tag_redraw();
  }
}

void Screen::toggle_maximized(Area *area)
{
  set_maximized(maximized_ ? nullptr : area);
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Screen: layout
 * \{ */

int Screen::min_extent(const ScreenNode &node, const SplitDir along, const float scale) const
{
  if (node.leaf()) {
    return along == SplitDir::Horizontal ? node.area->min_width(scale) : node.area->min_height(scale);
  }
  const int gap = scaled(area_gap_1x, scale);
  int v = 0;
  for (const auto &c : node.children) {
    const int m = min_extent(*c, along, scale);
    v = node.dir == along ? v + m : std::max(v, m);
  }
  if (node.dir == along && !node.children.empty()) {
    v += gap * int(node.children.size() - 1);
  }
  return v;
}

void Screen::layout_node(ScreenNode &node, const Rect &r, const DrawContext &ctx)
{
  node.rect = r;
  if (node.leaf()) {
    node.area->layout(maximized_ && maximized_ != node.area.get() ? Rect{} : r, ctx);
    return;
  }
  const size_t n = node.children.size();
  const int gap = n > 1 ? scaled(area_gap_1x, ctx.ui_scale) : 0;
  const int avail = std::max(0, extent(r, node.dir) - gap * int(n - 1));
  std::vector<float> factors(n);
  std::vector<int> mins(n);
  for (size_t i = 0; i < n; i++) {
    factors[i] = node.children[i]->factor;
    mins[i] = min_extent(*node.children[i], node.dir, ctx.ui_scale);
  }
  const std::vector<int> sizes = distribute_sizes(avail, factors, mins);
  int pos = node.dir == SplitDir::Horizontal ? r.xmin : r.ymax;
  for (size_t i = 0; i < n; i++) {
    Rect cr;
    Rect bar;
    if (node.dir == SplitDir::Horizontal) {
      cr = {pos, r.ymin, pos + sizes[i], r.ymax};
      pos += sizes[i];
      bar = {pos, r.ymin, pos + gap, r.ymax};
      pos += gap;
    }
    else {
      cr = {r.xmin, pos - sizes[i], r.xmax, pos};
      pos -= sizes[i];
      bar = {r.xmin, pos - gap, r.xmax, pos};
      pos -= gap;
    }
    layout_node(*node.children[i], cr, ctx);
    if (i + 1 < n && !maximized_) {
      splitters_.push_back({&node, int(i), node.dir, bar});
    }
  }
}

void Screen::layout(const Rect &rect, const DrawContext &ctx)
{
  rect_ = rect;
  scale_ = ctx.ui_scale > 0.0f ? ctx.ui_scale : 1.0f;
  const int gap = scaled(area_gap_1x, scale_);
  Rect tree = rect;
  if (top_) {
    const int h = std::min(rect.height(), ui_bar_height_px(scale_));
    top_->layout({rect.xmin, rect.ymax - h, rect.xmax, rect.ymax}, ctx);
    tree.ymax = std::max(tree.ymin, rect.ymax - h - gap);
  }
  if (bottom_) {
    const int h = std::min(tree.height(), ui_bar_height_px(scale_));
    bottom_->layout({rect.xmin, tree.ymin, rect.xmax, tree.ymin + h}, ctx);
    tree.ymin = std::min(tree.ymax, tree.ymin + h + gap);
  }
  tree_rect_ = tree;
  splitters_.clear();
  if (root_) {
    if (maximized_) {
      for (Area *a : areas()) {
        a->layout(a == maximized_ ? tree : Rect{}, ctx);
      }
      root_->rect = tree;
    }
    else {
      layout_node(*root_, tree, ctx);
    }
  }
}

const Splitter *Screen::splitter_at(const int x, const int y) const
{
  const int tol = std::max(1, scaled(splitter_hit_1x, scale_));
  for (const Splitter &s : splitters_) {
    Rect r = s.rect;
    if (s.dir == SplitDir::Horizontal) {
      r.xmin -= tol;
      r.xmax += tol;
    }
    else {
      r.ymin -= tol;
      r.ymax += tol;
    }
    if (r.contains(x, y)) {
      return &s;
    }
  }
  return nullptr;
}

int Screen::resize_split(ScreenNode &node, const int index, const int size_px)
{
  if (node.leaf() || index < 0 || index + 1 >= int(node.children.size())) {
    return 0;
  }
  const size_t n = node.children.size();
  std::vector<int> sizes(n);
  long total_all = 0;
  for (size_t i = 0; i < n; i++) {
    sizes[i] = extent(node.children[i]->rect, node.dir);
    total_all += sizes[i];
  }
  if (total_all <= 0) {
    return 0;
  }
  const size_t a = size_t(index), b = a + 1;
  const int total = sizes[a] + sizes[b];
  const int min_a = min_extent(*node.children[a], node.dir, scale_);
  const int min_b = min_extent(*node.children[b], node.dir, scale_);
  sizes[a] = clamp_pair(total, size_px, min_a, min_b);
  sizes[b] = total - sizes[a];
  for (size_t i = 0; i < n; i++) {
    node.children[i]->factor = float(double(sizes[i]) / double(total_all));
  }
  tag_redraw();
  return sizes[a];
}

Region *Screen::edge_region_at(const int x, const int y) const
{
  const int tol = std::max(1, scaled(splitter_hit_1x, scale_));
  for (Area *a : areas()) {
    if (a->rect().empty()) {
      continue;
    }
    for (const auto &rp : a->regions()) {
      const Region &r = *rp;
      if (!r.resizable || !r.visible() || r.rect().empty()) {
        continue;
      }
      const Rect &rr = r.rect();
      switch (r.align()) {
        case RegionAlign::Left:
          if (std::abs(x - rr.xmax) <= tol && y >= rr.ymin && y < rr.ymax) {
            return rp.get();
          }
          break;
        case RegionAlign::Right:
          if (std::abs(x - rr.xmin) <= tol && y >= rr.ymin && y < rr.ymax) {
            return rp.get();
          }
          break;
        case RegionAlign::Top:
          if (std::abs(y - rr.ymin) <= tol && x >= rr.xmin && x < rr.xmax) {
            return rp.get();
          }
          break;
        case RegionAlign::Bottom:
          if (std::abs(y - rr.ymax) <= tol && x >= rr.xmin && x < rr.xmax) {
            return rp.get();
          }
          break;
        case RegionAlign::Fill:
          break;
      }
    }
  }
  return nullptr;
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Screen: UI frame and drawing
 * \{ */

void Screen::set_ui_config(const ui::ContextConfig &config)
{
  impl_->config = config;
  impl_->has_config = true;
  ui_.reset();
  tag_redraw();
}

ui::Rect Screen::to_ui(const Rect &r) const
{
  return {float(r.xmin - rect_.xmin), float(rect_.ymax - r.ymax), float(r.width()), float(r.height())};
}

void Screen::ensure_ui(const DrawContext &ctx)
{
  if (ui_) {
    return;
  }
  ui::ContextConfig config = impl_->has_config ? impl_->config : ui::ContextConfig{};
  if (!config.measurer) {
    if (!ctx.fonts) {
      return;
    }
    impl_->measurer = std::make_unique<ui::gpu::BlfTextMeasurer>(*ctx.fonts);
    config.measurer = impl_->measurer.get();
  }
  if (!config.clipboard && ctx.window) {
    impl_->clipboard = std::make_unique<WmClipboard>(ctx.window->manager());
    config.clipboard = impl_->clipboard.get();
  }
#ifdef __APPLE__
  if (!impl_->has_config) {
    config.mac_shortcuts = true;
  }
#endif
  ui_ = std::make_unique<ui::Context>(config);
}

std::vector<Region *> Screen::visible_regions() const
{
  std::vector<Region *> out;
  auto add = [&](const Area *a) {
    if (!a || a->rect().empty()) {
      return;
    }
    for (const auto &r : a->regions()) {
      if (r->visible() && !r->rect().empty()) {
        out.push_back(r.get());
      }
    }
  };
  for (const Area *a : areas()) {
    add(a);
  }
  add(top_.get());
  add(bottom_.get());
  return out;
}

double Screen::frame_time(const DrawContext &ctx)
{
  double now = impl_->last_now;
  if (ctx.now >= 0.0) {
    now = ctx.now;
  }
  else if (ctx.window) {
    now = double(ctx.window->manager().time_ms()) / 1000.0;
  }
  impl_->last_now = std::max(impl_->last_now, now);
  return now;
}

DrawContext Screen::region_ctx(const DrawContext &ctx, const Region &region) const
{
  DrawContext r = ctx;
  r.rect = region.rect();
  r.ui = ui_.get();
  return r;
}

void Screen::update(const DrawContext &ctx)
{
  run_deferred();
  layout(ctx.rect, ctx);
  ensure_ui(ctx);
  impl_->segments.clear();
  if (!ui_) {
    return;
  }
  ui_->set_scale(ctx.ui_scale, 1.0f);
  ui_->begin_frame({float(rect_.width()), float(rect_.height())}, frame_time(ctx));
  struct Built {
    Region *region;
    size_t b0, b1;
  };
  std::vector<Built> built;
  for (Region *r : visible_regions()) {
    const size_t n0 = ui_->blocks().size();
    r->build_ui(*ui_, region_ctx(ctx, *r));
    built.push_back({r, n0, ui_->blocks().size()});
  }
  ui_->end_frame();
  ui_->clear_redraw();
  const auto &blocks = ui_->blocks();
  for (const Built &b : built) {
    Impl::Segment seg{std::numeric_limits<size_t>::max(), 0};
    for (size_t i = b.b0; i < b.b1 && i < blocks.size(); i++) {
      if (blocks[i]->kind() == ui::Block::Kind::Region) {
        seg.begin = std::min(seg.begin, blocks[i]->draw_begin());
        seg.end = std::max(seg.end, blocks[i]->draw_end());
      }
    }
    if (seg.end > seg.begin) {
      impl_->segments[b.region] = seg;
    }
  }
  frames_built_++;
}

void Screen::draw(const DrawContext &ctx)
{
  update(ctx);
  GPU_clear_color(background[0], background[1], background[2], background[3]);
  const Rect full = rect_;
  const ui::Vec2 window_size{float(full.width()), float(full.height())};
  auto paint_range = [&](size_t begin, size_t end) {
    if (!ui_ || !ctx.fonts || end <= begin) {
      return;
    }
    const ui::DrawList &list = ui_->draw_list();
    end = std::min(end, list.size());
    if (end <= begin) {
      return;
    }
    if (!impl_->painter) {
      impl_->painter = std::make_unique<ui::gpu::GpuPainter>(*ctx.fonts);
    }
    impl_->scratch.cmds.assign(list.cmds.begin() + long(begin), list.cmds.begin() + long(end));
    GPU_viewport(full.xmin, full.ymin, full.width(), full.height());
    GPU_scissor(full.xmin, full.ymin, full.width(), full.height());
    impl_->painter->set_pixel_size(ui_->style().pixel);
    impl_->painter->paint(impl_->scratch, window_size);
    GPU_scissor_test(false);
  };
  for (Region *r : visible_regions()) {
    const Rect &rr = r->rect();
    GPU_viewport(rr.xmin, rr.ymin, rr.width(), rr.height());
    GPU_scissor(rr.xmin, rr.ymin, rr.width(), rr.height());
    GPU_scissor_test(true);
    gfx::push_pixel_space(rr.width(), rr.height());
    r->draw(region_ctx(ctx, *r));
    gfx::pop_pixel_space();
    GPU_scissor_test(false);
    const auto it = impl_->segments.find(r);
    if (it != impl_->segments.end()) {
      paint_range(it->second.begin, it->second.end);
    }
    r->redraw_ = false;
  }
  if (ui_) {
    paint_range(ui_->overlay_draw_begin(), ui_->draw_list().size());
  }
  if (!full.empty()) {
    GPU_viewport(full.xmin, full.ymin, full.width(), full.height());
    GPU_scissor(full.xmin, full.ymin, full.width(), full.height());
  }
  after_draw(ctx);
}

std::optional<Rect> Screen::ime_caret() const
{
  if (!ui_ || !ui_->text_input_active()) {
    return std::nullopt;
  }
  const ui::Rect c = ui_->text_input_rect();
  const int top = rect_.ymax;
  return Rect{rect_.xmin + int(c.x), top - int(c.y1()), rect_.xmin + int(c.x1()) + 1, top - int(c.y)};
}

bool Screen::ime_composing() const
{
  const ui::TextEdit *ed = ui_ ? ui_->edit_state() : nullptr;
  return ed && ed->composing();
}

double Screen::next_wakeup() const
{
  return ui_ ? ui_->next_wakeup() : std::numeric_limits<double>::infinity();
}

void Screen::after_draw(const DrawContext &ctx)
{
  if (!ctx.window) {
    return;
  }
  Window &win = *ctx.window;
  /* Input method: enabled while a field is edited, candidate window at the caret. */
  if (const std::optional<Rect> caret = ime_caret()) {
    if (!win.ime_active() || !(*caret == impl_->ime_caret)) {
      win.ime_begin(*caret, !ime_composing());
      impl_->ime_caret = *caret;
      impl_->ime_ours = true;
    }
  }
  else if (impl_->ime_ours) {
    if (win.ime_active()) {
      win.ime_end();
    }
    impl_->ime_ours = false;
    impl_->ime_caret = {};
  }
  /* Tooltips and toasts: wake up when the next timed change is due. */
  const double wake = next_wakeup();
  if (!std::isfinite(wake) || (impl_->timer && wake == impl_->timer_at)) {
    return;
  }
  WindowManager &wm = win.manager();
  if (impl_->timer && impl_->timer_wm) {
    impl_->timer_wm->remove_timer(impl_->timer);
  }
  const double now = double(wm.time_ms()) / 1000.0;
  const uint64_t delay = uint64_t(std::max(0.0, wake - now) * 1000.0) + 5;
  impl_->timer_at = wake;
  impl_->timer_wm = &wm;
  impl_->timer = wm.add_timer(delay, 0, [this, &wm]() {
    impl_->timer = 0;
    if (ui_) {
      ui_->handle_event(ui::Event::tick(double(wm.time_ms()) / 1000.0));
    }
    tag_redraw();
  });
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Screen: events
 * \{ */

void Screen::set_focus(Region *region)
{
  focus_ = region;
}

Region *Screen::find_region(const std::string &name) const
{
  for (Area *a : areas()) {
    if (Region *r = a->find_region(name)) {
      return r;
    }
  }
  for (Area *g : {top_.get(), bottom_.get()}) {
    if (g) {
      if (Region *r = g->find_region(name)) {
        return r;
      }
    }
  }
  return nullptr;
}

Region *Screen::region_at(const int x, const int y) const
{
  Area *a = area_at(x, y);
  return a ? a->region_at(x, y) : nullptr;
}

void Screen::tag_redraw()
{
  needs_redraw_ = true;
  for (Area *a : areas()) {
    for (const auto &r : a->regions()) {
      r->redraw_ = true;
    }
  }
  for (Area *g : {top_.get(), bottom_.get()}) {
    if (g) {
      for (const auto &r : g->regions()) {
        r->redraw_ = true;
      }
    }
  }
  if (on_redraw_request) {
    on_redraw_request();
  }
}

bool Screen::send_ui(const Event &event, bool *r_consumed_any)
{
  if (!ui_) {
    return false;
  }
  bool consumed = false;
  for (const ui::Event &e : translate_event(event, rect_)) {
    const ui::EventResult res = ui_->handle_event(e);
    consumed |= res.consumed;
    if (res.redraw || ui_->redraw_requested()) {
      tag_redraw();
      ui_->clear_redraw();
    }
  }
  if (r_consumed_any) {
    *r_consumed_any = consumed;
  }
  return consumed;
}

bool Screen::send_region(Region *region, const Event &event, const DrawContext &ctx)
{
  if (!region) {
    return false;
  }
  return region->handle_event(event, region_ctx(ctx, *region));
}

bool Screen::ui_busy() const
{
  if (!ui_) {
    return false;
  }
  if (ui_->popup_open() || ui_->active() != 0) {
    return true;
  }
  for (const auto &b : ui_->blocks()) {
    if (b->kind() == ui::Block::Kind::Modal) {
      return true;
    }
  }
  return false;
}

bool Screen::ui_widget_at(const int x, const int y) const
{
  if (!ui_) {
    return false;
  }
  const ui::Vec2 p{float(x - rect_.xmin), float(rect_.ymax - 1 - y)};
  const auto &blocks = ui_->blocks();
  for (auto it = blocks.rbegin(); it != blocks.rend(); ++it) {
    const ui::Block &b = **it;
    switch (b.kind()) {
      case ui::Block::Kind::Tooltip:
        break;
      case ui::Block::Kind::Popup:
      case ui::Block::Kind::Modal:
      case ui::Block::Kind::Toast:
        if (b.frame().contains(p)) {
          return true;
        }
        break;
      case ui::Block::Kind::Region:
        if (b.rect().contains(p)) {
          for (const ui::Widget &w : b.widgets()) {
            /* Text does not take the pointer away from pass-through regions. */
            const bool passive = w.type == ui::WidgetType::Label || w.type == ui::WidgetType::Paragraph ||
                                 w.type == ui::WidgetType::Progress;
            if (!passive && w.rect.contains(p) && w.clip.contains(p)) {
              return true;
            }
          }
          return false;
        }
        break;
    }
  }
  return false;
}

void Screen::defer(std::function<void()> fn)
{
  if (fn) {
    deferred_.push_back(std::move(fn));
    tag_redraw();
  }
}

void Screen::run_deferred()
{
  /* Calls may defer more calls; run until drained (bounded against runaway loops). */
  for (int round = 0; round < 8 && !deferred_.empty(); round++) {
    std::vector<std::function<void()>> calls = std::move(deferred_);
    deferred_.clear();
    for (auto &fn : calls) {
      fn();
    }
  }
}

bool Screen::dispatch(const Event &event, const DrawContext &ctx)
{
  const bool consumed = dispatch_event(event, ctx);
  if (!deferred_.empty()) {
    run_deferred();
    DrawContext lctx = ctx;
    lctx.rect = rect_;
    lctx.ui_scale = scale_;
    if (!rect_.empty()) {
      layout(rect_, lctx);
    }
  }
  return consumed;
}

bool Screen::dispatch_event(const Event &event, const DrawContext &ctx)
{
  switch (event.type) {
    case EventType::Resize:
    case EventType::Expose:
    case EventType::DpiChange:
      tag_redraw();
      return false;
    case EventType::Close:
    case EventType::FocusIn:
    case EventType::None:
      return false;
    case EventType::FocusOut:
      capture_ = Capture::None;
      capture_region_ = nullptr;
      impl_->edge_region = nullptr;
      impl_->drag_node = nullptr;
      send_ui(event);
      tag_redraw();
      return false;
    case EventType::DragEnter:
    case EventType::DragOver:
      hover_ = region_at(event.x, event.y);
      return area_at(event.x, event.y) != nullptr;
    case EventType::DragLeave:
      return false;
    case EventType::Drop: {
      Area *a = area_at(event.x, event.y);
      if (a && a->on_drop(event)) {
        a->tag_redraw();
        return true;
      }
      return false;
    }
    default:
      break;
  }
  if (event.is_pointer()) {
    return dispatch_pointer(event, ctx);
  }
  if (event.is_keyboard()) {
    return dispatch_keyboard(event, ctx);
  }
  return false;
}

bool Screen::dispatch_pointer(const Event &e, const DrawContext &ctx)
{
  const bool move = e.type == EventType::MouseMove;
  const bool down = e.type == EventType::MouseDown;
  const bool up = e.type == EventType::MouseUp;
  DrawContext sctx = ctx;
  sctx.rect = rect_;
  auto relayout = [&]() {
    DrawContext lctx = sctx;
    lctx.ui_scale = scale_;
    layout(rect_, lctx);
  };
  auto set_cursor = [&](Cursor c) {
    if (ctx.window) {
      ctx.window->set_cursor(c);
    }
  };
  auto clear_ui_hover = [&]() {
    if (ui_) {
      ui_->handle_event(ui::Event::mouse_move({-1.0e6f, -1.0e6f}, double(e.time_ms) / 1000.0));
    }
  };

  switch (capture_) {
    case Capture::Splitter: {
      ScreenNode *node = impl_->drag_node;
      if (move && node) {
        const int delta = node->dir == SplitDir::Horizontal ? e.x - impl_->drag_start_x :
                                                              impl_->drag_start_y - e.y;
        resize_split(*node, impl_->drag_index, impl_->drag_start_size + delta);
        relayout();
      }
      if (up) {
        capture_ = Capture::None;
        impl_->drag_node = nullptr;
      }
      return true;
    }
    case Capture::RegionEdge: {
      Region *r = impl_->edge_region;
      if (move && r) {
        int delta = 0;
        switch (r->align()) {
          case RegionAlign::Left: delta = e.x - impl_->drag_start_x; break;
          case RegionAlign::Right: delta = impl_->drag_start_x - e.x; break;
          case RegionAlign::Top: delta = impl_->drag_start_y - e.y; break;
          case RegionAlign::Bottom: delta = e.y - impl_->drag_start_y; break;
          case RegionAlign::Fill: break;
        }
        r->set_size_1x(float(impl_->drag_start_size + delta) / scale_);
        relayout();
      }
      if (up) {
        capture_ = Capture::None;
        impl_->edge_region = nullptr;
      }
      return true;
    }
    case Capture::Region: {
      Region *r = capture_region_;
      if (move) {
        hover_ = region_at(e.x, e.y);
      }
      bool consumed = send_region(r, e, ctx);
      if (!consumed && r && r->area()) {
        consumed = r->area()->handle_event(e, ctx);
      }
      if (up) {
        capture_ = Capture::None;
        capture_region_ = nullptr;
      }
      return consumed || r != nullptr;
    }
    case Capture::Ui:
      if (move) {
        hover_ = region_at(e.x, e.y);
      }
      send_ui(e);
      if (up) {
        capture_ = Capture::None;
      }
      return true;
    case Capture::None:
      break;
  }

  hover_ = region_at(e.x, e.y);
  if (hover_ && hover_->area() && hover_->area()->node()) {
    active_area_ = hover_->area();
  }
  const bool busy = ui_busy();
  if (!busy && (move || down)) {
    if (const Splitter *s = splitter_at(e.x, e.y)) {
      set_cursor(s->dir == SplitDir::Horizontal ? Cursor::ResizeLeftRight : Cursor::ResizeUpDown);
      if (move) {
        clear_ui_hover();
      }
      if (down && e.button == MouseButton::Left) {
        const bool dbl = impl_->click_node == s->node && impl_->click_index == s->index &&
                         e.time_ms - impl_->click_time <= 400;
        if (dbl) {
          /* Double-click joins the two areas beside the bar (the larger one stays). */
          impl_->click_node = nullptr;
          ScreenNode &node = *s->node;
          ScreenNode &na = *node.children[size_t(s->index)];
          ScreenNode &nb = *node.children[size_t(s->index) + 1];
          if (na.leaf() && nb.leaf()) {
            const bool keep_a = extent(na.rect, node.dir) >= extent(nb.rect, node.dir);
            Area &a = *na.area, &b = *nb.area;
            if (keep_a ? join(a, b) : join(b, a)) {
              relayout();
            }
          }
          return true;
        }
        impl_->click_node = s->node;
        impl_->click_index = s->index;
        impl_->click_time = e.time_ms;
        capture_ = Capture::Splitter;
        impl_->drag_node = s->node;
        impl_->drag_index = s->index;
        impl_->drag_start_x = e.x;
        impl_->drag_start_y = e.y;
        impl_->drag_start_size = extent(s->node->children[size_t(s->index)]->rect, s->node->dir);
      }
      return true;
    }
    if (Region *r = edge_region_at(e.x, e.y)) {
      const bool horizontal = r->align() == RegionAlign::Left || r->align() == RegionAlign::Right;
      set_cursor(horizontal ? Cursor::ResizeLeftRight : Cursor::ResizeUpDown);
      if (move) {
        clear_ui_hover();
      }
      if (down && e.button == MouseButton::Left) {
        capture_ = Capture::RegionEdge;
        impl_->edge_region = r;
        impl_->drag_start_x = e.x;
        impl_->drag_start_y = e.y;
        impl_->drag_start_size = horizontal ? r->rect().width() : r->rect().height();
      }
      return true;
    }
  }
  if (move) {
    set_cursor(Cursor::Default);
  }

  if (ui_) {
    const bool to_ui = !hover_ || !hover_->ui_pass_through || busy || ui_widget_at(e.x, e.y);
    if (to_ui) {
      if (send_ui(e)) {
        if (down) {
          capture_ = Capture::Ui;
          if (hover_) {
            focus_ = hover_;
          }
        }
        return true;
      }
    }
    else if (move) {
      clear_ui_hover();
    }
  }

  Region *target = hover_;
  if (down) {
    focus_ = target;
    if (target) {
      capture_ = Capture::Region;
      capture_region_ = target;
    }
  }
  bool consumed = send_region(target, e, ctx);
  if (!consumed && target && target->area()) {
    consumed = target->area()->handle_event(e, ctx);
  }
  return consumed;
}

bool Screen::dispatch_keyboard(const Event &e, const DrawContext &ctx)
{
  if (send_ui(e)) {
    return true;
  }
  Region *target = hover_ ? hover_ : focus_;
  if (e.type == EventType::KeyDown && e.key == Key::Space && (e.modifiers & ~ModShift) == ModCtrl) {
    /* Ctrl+Space: maximize the area under the pointer, or restore (Blender). */
    Area *a = target ? target->area() : nullptr;
    if (maximized_ || (a && a->node())) {
      toggle_maximized(a && a->node() ? a : nullptr);
      return true;
    }
  }
  if (send_region(target, e, ctx)) {
    return true;
  }
  if (target && target->area() && target->area()->handle_event(e, ctx)) {
    return true;
  }
  return on_unhandled_event && on_unhandled_event(e);
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Screen: persistence
 * \{ */

static double round6(const double v)
{
  return std::round(v * 1.0e6) / 1.0e6;
}

static nlohmann::json node_to_json(const ScreenNode &node)
{
  nlohmann::json j = nlohmann::json::object();
  j["factor"] = round6(node.factor);
  if (node.leaf()) {
    const Area &a = *node.area;
    nlohmann::json regions = nlohmann::json::array();
    for (const auto &r : a.regions()) {
      if (r->persistent && r->align() != RegionAlign::Fill) {
        regions.push_back({{"name", r->name()}, {"size", round6(r->size_1x())}, {"visible", r->visible()}});
      }
    }
    nlohmann::json state = a.save_state();
    if (!state.is_object()) {
      state = nlohmann::json::object();
    }
    j["area"] = {{"id", a.id()}, {"type", a.type()}, {"regions", std::move(regions)}, {"state", std::move(state)}};
  }
  else {
    j["split"] = split_dir_name(node.dir);
    nlohmann::json children = nlohmann::json::array();
    for (const auto &c : node.children) {
      children.push_back(node_to_json(*c));
    }
    j["children"] = std::move(children);
  }
  return j;
}

nlohmann::json Screen::to_json() const
{
  nlohmann::json j = nlohmann::json::object();
  j["maximized"] = maximized_ ? nlohmann::json(maximized_->id()) : nlohmann::json(nullptr);
  j["root"] = root_ ? node_to_json(*root_) : nlohmann::json(nullptr);
  return j;
}

namespace {

constexpr int kMaxDepth = 16;
constexpr int kMaxAreas = 64;
constexpr int kMaxChildren = 32;

struct Builder {
  const Screen &screen;
  std::string error;
  std::unordered_set<std::string> ids;
  struct Leaf {
    Area *area;
    ScreenNode *node;
    std::string id;
  };
  std::vector<Leaf> leaves;
  int areas = 0;

  bool fail(std::string msg)
  {
    if (error.empty()) {
      error = std::move(msg);
    }
    return false;
  }

  static bool short_string(const nlohmann::json &v, size_t max_len)
  {
    return v.is_string() && !v.get_ref<const std::string &>().empty() && v.get_ref<const std::string &>().size() <= max_len;
  }

  std::unique_ptr<ScreenNode> build(const nlohmann::json &j, ScreenNode *parent, int depth)
  {
    if (depth > kMaxDepth) {
      fail("layout tree too deep");
      return nullptr;
    }
    if (!j.is_object()) {
      fail("node is not an object");
      return nullptr;
    }
    auto node = std::make_unique<ScreenNode>();
    node->parent = parent;
    const auto f = j.find("factor");
    if (f == j.end() || !f->is_number() || !std::isfinite(f->get<double>()) || f->get<double>() <= 0.0 ||
        f->get<double>() > 1.0e6)
    {
      fail("node factor must be a positive number");
      return nullptr;
    }
    node->factor = float(f->get<double>());
    const auto area = j.find("area");
    const auto split = j.find("split");
    if ((area != j.end()) == (split != j.end())) {
      fail("node must have exactly one of 'area' or 'split'");
      return nullptr;
    }
    if (area != j.end()) {
      return build_leaf(*area, std::move(node));
    }
    if (!split->is_string() || (*split != "horizontal" && *split != "vertical")) {
      fail("split must be 'horizontal' or 'vertical'");
      return nullptr;
    }
    node->dir = *split == "horizontal" ? SplitDir::Horizontal : SplitDir::Vertical;
    const auto children = j.find("children");
    if (children == j.end() || !children->is_array() || children->size() < 2 || children->size() > kMaxChildren) {
      fail("split needs 2 to 32 children");
      return nullptr;
    }
    for (const auto &c : *children) {
      std::unique_ptr<ScreenNode> child = build(c, node.get(), depth + 1);
      if (!child) {
        return nullptr;
      }
      node->children.push_back(std::move(child));
    }
    return node;
  }

  std::unique_ptr<ScreenNode> build_leaf(const nlohmann::json &a, std::unique_ptr<ScreenNode> node)
  {
    if (!a.is_object()) {
      fail("area is not an object");
      return nullptr;
    }
    if (++areas > kMaxAreas) {
      fail("too many areas");
      return nullptr;
    }
    const auto id = a.find("id");
    const auto type = a.find("type");
    if (id == a.end() || !short_string(*id, 64)) {
      fail("area id must be a non-empty string");
      return nullptr;
    }
    if (type == a.end() || !short_string(*type, 64)) {
      fail("area type must be a non-empty string");
      return nullptr;
    }
    const std::string sid = id->get<std::string>();
    if (!ids.insert(sid).second) {
      fail("duplicate area id '" + sid + "'");
      return nullptr;
    }
    std::unique_ptr<Area> created = screen.create_area(type->get<std::string>());
    if (!created) {
      fail("unknown area type '" + type->get<std::string>() + "'");
      return nullptr;
    }
    if (const auto regions = a.find("regions"); regions != a.end()) {
      if (!regions->is_array() || regions->size() > 32) {
        fail("area regions must be an array");
        return nullptr;
      }
      for (const auto &r : *regions) {
        const auto name = r.is_object() ? r.find("name") : r.end();
        if (!r.is_object() || name == r.end() || !short_string(*name, 64)) {
          fail("region entry needs a name");
          return nullptr;
        }
        const auto size = r.find("size");
        const auto visible = r.find("visible");
        if ((size != r.end() && (!size->is_number() || !std::isfinite(size->get<double>()) ||
                                 size->get<double>() < 0.0 || size->get<double>() > 10000.0)) ||
            (visible != r.end() && !visible->is_boolean()))
        {
          fail("invalid region size or visibility");
          return nullptr;
        }
        Region *region = created->find_region(name->get<std::string>());
        if (!region) {
          continue; /* Regions of older versions are ignored. */
        }
        if (size != r.end()) {
          region->set_size_1x(float(size->get<double>()));
        }
        if (visible != r.end()) {
          region->set_visible(visible->get<bool>());
        }
      }
    }
    if (const auto state = a.find("state"); state != a.end()) {
      if (!state->is_object()) {
        fail("area state must be an object");
        return nullptr;
      }
      if (!created->load_state(*state)) {
        fail("invalid state for area '" + sid + "'");
        return nullptr;
      }
    }
    leaves.push_back({created.get(), node.get(), sid});
    node->area = std::move(created);
    return node;
  }
};

}  // namespace

bool Screen::from_json(const nlohmann::json &json, std::string *r_error)
{
  auto fail = [&](const std::string &msg) {
    if (r_error) {
      *r_error = msg;
    }
    return false;
  };
  if (!json.is_object()) {
    return fail("screen is not an object");
  }
  const auto root = json.find("root");
  if (root == json.end() || !root->is_object()) {
    return fail("screen has no root node");
  }
  Builder builder{*this, {}, {}, {}, 0};
  std::unique_ptr<ScreenNode> tree = builder.build(*root, nullptr, 0);
  if (!tree) {
    return fail(builder.error);
  }
  std::string max_id;
  if (const auto m = json.find("maximized"); m != json.end() && !m->is_null()) {
    if (!m->is_string()) {
      return fail("maximized must be an area id or null");
    }
    max_id = m->get<std::string>();
  }
  /* Commit. */
  clear();
  root_ = std::move(tree);
  root_->parent = nullptr;
  for (const Builder::Leaf &leaf : builder.leaves) {
    leaf.area->id_ = leaf.id;
  }
  for (const Builder::Leaf &leaf : builder.leaves) {
    attach(*leaf.area, leaf.node);
  }
  maximized_ = max_id.empty() ? nullptr : find_area(max_id);
  if (maximized_ && !maximized_->node()) {
    maximized_ = nullptr;
  }
  tag_redraw();
  return true;
}

/** \} */

}  // namespace stk::wm
