/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/wm/screen.hh"

#include <algorithm>
#include <cmath>

#include "GPU_framebuffer.hh"
#include "GPU_state.hh"

#include "stk/gfx/offscreen.hh"

namespace stk::wm {

using namespace blender;

static int scaled(const float size_1x, const float ui_scale)
{
  return std::max(0, int(std::lround(size_1x * ui_scale)));
}

/* -------------------------------------------------------------------- */
/** \name Region
 * \{ */

Region::Region(std::string name, const RegionAlign align, const float size_1x)
    : name_(std::move(name)), align_(align), size_1x_(size_1x)
{
}

Screen *Region::screen() const
{
  return area_ ? area_->screen() : nullptr;
}

void Region::set_size_1x(const float size)
{
  if (size != size_1x_) {
    size_1x_ = size;
    tag_redraw();
  }
}

void Region::set_visible(const bool visible)
{
  if (visible != visible_) {
    visible_ = visible;
    tag_redraw();
  }
}

void Region::tag_redraw()
{
  if (Screen *s = screen()) {
    s->tag_redraw();
  }
}

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

Area::Area(std::string name, const float weight) : name_(std::move(name)), weight_(weight) {}

void Area::set_weight(const float weight)
{
  weight_ = std::max(weight, 0.0f);
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

void Area::layout(const Rect &rect, const DrawContext &ctx)
{
  rect_ = rect;
  Rect free = rect;
  for (const auto &r : regions_) {
    Rect rr{};
    if (r->visible()) {
      const int size = scaled(r->size_1x(), ctx.ui_scale);
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
    if (changed && !rr.empty()) {
      DrawContext rctx = ctx;
      rctx.rect = rr;
      r->on_layout(rctx);
    }
  }
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Screen
 * \{ */

Area &Screen::add_area(std::unique_ptr<Area> area)
{
  area->screen_ = this;
  areas_.push_back(std::move(area));
  tag_redraw();
  return *areas_.back();
}

Region *Screen::find_region(const std::string &name) const
{
  for (const auto &a : areas_) {
    if (Region *r = a->find_region(name)) {
      return r;
    }
  }
  return nullptr;
}

Region *Screen::region_at(const int x, const int y) const
{
  for (const auto &a : areas_) {
    if (a->rect().contains(x, y)) {
      return a->region_at(x, y);
    }
  }
  return nullptr;
}

void Screen::layout(const Rect &rect, const DrawContext &ctx)
{
  rect_ = rect;
  float total = 0.0f;
  for (const auto &a : areas_) {
    total += a->weight();
  }
  const int gap = areas_.size() > 1 ? scaled(area_gap_1x, ctx.ui_scale) : 0;
  const int avail = std::max(0, rect.width() - gap * int(areas_.size() > 0 ? areas_.size() - 1 : 0));
  int x = rect.xmin;
  float acc = 0.0f;
  for (size_t i = 0; i < areas_.size(); i++) {
    Area &a = *areas_[i];
    acc += a.weight();
    /* Accumulate to avoid rounding drift; the last area ends exactly at the right edge. */
    const int x_end = (i + 1 == areas_.size()) ? rect.xmax :
                                                 rect.xmin + int(std::lround(avail * (total > 0 ? acc / total : 0))) +
                                                     gap * int(i);
    a.layout({x, rect.ymin, std::max(x, x_end), rect.ymax}, ctx);
    x = x_end + gap;
  }
}

void Screen::draw(const DrawContext &ctx)
{
  GPU_clear_color(background[0], background[1], background[2], background[3]);
  for (const auto &a : areas_) {
    for (const auto &r : a->regions()) {
      const Rect &rr = r->rect();
      if (!r->visible() || rr.empty()) {
        continue;
      }
      GPU_viewport(rr.xmin, rr.ymin, rr.width(), rr.height());
      GPU_scissor(rr.xmin, rr.ymin, rr.width(), rr.height());
      GPU_scissor_test(true);
      gfx::push_pixel_space(rr.width(), rr.height());
      DrawContext rctx = ctx;
      rctx.rect = rr;
      r->draw(rctx);
      gfx::pop_pixel_space();
      GPU_scissor_test(false);
    }
  }
  if (!rect_.empty()) {
    GPU_viewport(rect_.xmin, rect_.ymin, rect_.width(), rect_.height());
    GPU_scissor(rect_.xmin, rect_.ymin, rect_.width(), rect_.height());
  }
}

bool Screen::dispatch(const Event &event, const DrawContext &ctx)
{
  auto send = [&](Region *r) {
    if (!r) {
      return false;
    }
    DrawContext rctx = ctx;
    rctx.rect = r->rect();
    return r->handle_event(event, rctx);
  };

  if (event.is_pointer()) {
    Region *target = capture_ ? capture_ : region_at(event.x, event.y);
    if (event.type == EventType::MouseDown) {
      capture_ = target;
      if (target) {
        focus_ = target;
      }
    }
    else if (event.type == EventType::MouseUp) {
      capture_ = nullptr;
    }
    hover_ = region_at(event.x, event.y);
    return send(target);
  }
  if (event.is_keyboard()) {
    return send(focus_ ? focus_ : hover_);
  }
  if (event.type == EventType::FocusOut) {
    capture_ = nullptr;
  }
  if (event.type == EventType::DragLeave) {
    return send(hover_);
  }
  return false;
}

void Screen::set_focus(Region *region)
{
  focus_ = region;
}

void Screen::tag_redraw()
{
  needs_redraw_ = true;
  if (on_redraw_request) {
    on_redraw_request();
  }
}

/** \} */

}  // namespace stk::wm
