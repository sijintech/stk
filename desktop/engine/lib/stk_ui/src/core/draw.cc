/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Draw-list generation for blocks and widgets, following Blender's interface_widgets.cc
 * (widget_state colours, hover highlight, number arrows, slider fill, option check box, menu
 * chevron, text field caret/selection/IME underline). */
#include <algorithm>
#include <cmath>

#include "layout_engine.hh"
#include "stk/ui/ui.hh"
#include "stk/ui/utf8.hh"

namespace stk::ui {

namespace {

/** Blender's widget_active_color(): hover highlight. */
WidgetColors active_colors(WidgetColors c)
{
  auto gray = [](const Color &x) { return 0.2126f * x.r + 0.7152f * x.g + 0.0722f * x.b; };
  const bool dark = gray(c.text) > gray(c.inner);
  c.inner = c.inner.mul_hsl(1.0f, 1.15f, dark ? 1.2f : 1.1f);
  c.outline = c.outline.blend(c.outline_sel, 0.5f);
  c.outline_sel = c.outline_sel.mul_hsl(1.0f, 1.15f, 1.15f);
  c.text = c.text.mul_hsl(1.0f, 1.15f, dark ? 1.25f : 0.8f);
  return c;
}

/** Blender's widget_state(): selected / hover / disabled. */
WidgetColors state_colors(const WidgetColors &base, bool selected, bool hover, bool disabled)
{
  WidgetColors c = base;
  if (selected) {
    c.inner = c.inner_sel;
    c.outline = c.outline_sel;
    c.text = c.text_sel;
  }
  else if (hover) {
    c = active_colors(c);
  }
  if (disabled) {
    c.outline = c.outline.scaled_alpha(0.5f);
    c.inner = c.inner.scaled_alpha(0.5f);
    c.item = c.item.scaled_alpha(0.5f);
    c.text = c.text.scaled_alpha(0.5f);
    c.text_sel = c.text_sel.scaled_alpha(0.5f);
  }
  return c;
}

float clamp_radius(float r, const Rect &rect)
{
  return std::max(0.0f, std::min(r, 0.5f * std::min(rect.w, rect.h)));
}

}  // namespace

void Context::draw_shadow(const Rect &r, float radius)
{
  const float sw = std::round(config_.theme.menu_shadow_width * style_.scale);
  const float fac = config_.theme.menu_shadow_fac;
  for (int i = 3; i >= 1; i--) {
    const float grow = sw * float(i) / 3.0f;
    const Rect s{r.x - grow * 0.5f, r.y - grow * 0.25f, r.w + grow, r.h + grow};
    const uint8_t a = uint8_t(std::round(255.0f * fac * (1.0f - float(i - 1) / 3.0f) * 0.6f));
    draw_.round_box(snap(s), radius + grow, CORNER_ALL, Color{0, 0, 0, a}, Color{0, 0, 0, 0});
  }
}

void Context::draw_scrollbar(const Rect &area, float content, float view, float scroll, bool hot)
{
  const Rect thumb = scrollbar_rect(Widget{}, content, view, scroll, area);
  if (thumb.empty()) {
    return;
  }
  const WidgetColors &sc = config_.theme.scroll;
  Color c = sc.item;
  if (hot) {
    c = c.mul_hsl(1.0f, 1.0f, 1.35f);
  }
  draw_.round_box(thumb, clamp_radius(sc.roundness * thumb.w * 2.0f, thumb), CORNER_ALL, c, Color{0, 0, 0, 0});
}

void Context::draw_block(const Block &b)
{
  const Theme &th = config_.theme;
  const Style &st = style_;
  switch (b.kind()) {
    case Block::Kind::Region: {
      const Color bg = b.has_background_ ? b.background_ : th.region_back;
      if (bg.a > 0) {
        draw_.rect(b.rect(), bg);
      }
      draw_.clip_push(b.rect());
      draw_layout(*b.root_, b);
      if (b.content_height() > b.rect().h) {
        const bool hot = mouse_.x >= b.rect().x1() - st.scrollbar - 2 * st.pixel && b.rect().contains(mouse_);
        draw_scrollbar(b.rect(), b.content_height(), b.rect().h, scroll_of(b.id_), hot);
      }
      draw_.clip_pop();
      break;
    }
    case Block::Kind::Modal: {
      const WidgetColors &mb = th.menu_back;
      const float r = clamp_radius(mb.roundness * st.unit, b.frame());
      draw_shadow(b.frame(), r);
      draw_.round_box(b.frame(), r, CORNER_ALL, mb.inner, mb.outline);
      const Rect title{b.frame().x + st.panel_margin, b.frame().y, b.frame().w - 2 * st.panel_margin, st.panel_header};
      const FontMetrics fm = measurer().metrics(st.font);
      draw_.text(clip_text(b.title(), title.w, measurer(), st.font),
                 {title.x, std::round(title.cy() + (fm.ascent - fm.descent) * 0.5f)}, st.font, th.panel_title);
      draw_.rect({b.frame().x + st.pixel, b.frame().y + st.panel_header - st.pixel, b.frame().w - 2 * st.pixel, st.pixel},
                 mb.outline);
      draw_.clip_push(b.frame());
      draw_layout(*b.root_, b);
      draw_.clip_pop();
      break;
    }
    case Block::Kind::Popup: {
      const WidgetColors &mb = th.menu_back;
      const float r = clamp_radius(mb.roundness * st.unit, b.frame());
      draw_shadow(b.frame(), r);
      draw_.round_box(b.frame(), r, CORNER_ALL, mb.inner, mb.outline);
      draw_.clip_push(b.frame().inset(0, st.box_space));
      draw_layout(*b.root_, b);
      draw_.clip_pop();
      const float view = b.frame().h - 2 * st.box_space;
      if (b.content_height() > view) {
        draw_scrollbar(b.frame().inset(0, st.box_space), b.content_height(), view, scroll_of(b.id_), false);
      }
      break;
    }
    case Block::Kind::Tooltip: {
      const WidgetColors &tc = th.tooltip;
      const float r = clamp_radius(tc.roundness * st.unit, b.frame());
      draw_shadow(b.frame(), r);
      draw_.round_box(b.frame(), r, CORNER_ALL, tc.inner, tc.outline);
      draw_layout(*b.root_, b);
      break;
    }
    case Block::Kind::Toast: {
      const WidgetColors &tc = th.tooltip;
      const float r = clamp_radius(tc.roundness * st.unit, b.frame());
      draw_shadow(b.frame(), r);
      draw_.round_box(b.frame(), r, CORNER_ALL, tc.inner, tc.outline);
      Color sc = th.state.info;
      switch (b.toast_kind_) {
        case ToastKind::Info: sc = th.state.info; break;
        case ToastKind::Success: sc = th.state.success; break;
        case ToastKind::Warning: sc = th.state.warning; break;
        case ToastKind::Error: sc = th.state.error; break;
      }
      const float stripe = std::round(0.25f * st.unit);
      draw_.round_box({b.frame().x, b.frame().y, stripe, b.frame().h}, clamp_radius(r, {0, 0, stripe * 2, b.frame().h}),
                      CORNER_LEFT, sc, Color{0, 0, 0, 0});
      draw_layout(*b.root_, b);
      break;
    }
  }
}

void Context::draw_layout(const Layout &l, const Block &b)
{
  const Theme &th = config_.theme;
  const Style &st = style_;
  if (l.kind() == Layout::Kind::Box) {
    const WidgetColors &bc = th.box;
    draw_.round_box(l.rect, clamp_radius(bc.roundness * st.unit, l.rect), CORNER_ALL, bc.inner, bc.outline);
  }
  else if (l.kind() == Layout::Kind::Panel) {
    const float r = clamp_radius(th.panel_roundness * st.unit, l.rect);
    draw_.round_box(l.rect, r, CORNER_ALL, th.panel_back, th.panel_outline);
  }
  const Rect clip = b.kind() == Block::Kind::Region ? b.rect() : b.frame();
  for (const auto &it : LayoutEngine::items(l)) {
    if (it.layout) {
      if (it.layout->rect.y > clip.y1() || it.layout->rect.y1() < clip.y) {
        continue;
      }
      draw_layout(*it.layout, b);
    }
    else if (it.widget) {
      const Rect &r = it.widget->rect;
      if (r.y > clip.y1() || r.y1() < clip.y) {
        continue;
      }
      draw_widget(*it.widget);
    }
  }
}

void Context::draw_widget(const Widget &w)
{
  const Theme &th = config_.theme;
  const Style &st = style_;
  const TextMeasurer &tm = measurer();
  const bool hover = hover_ == w.id;
  const bool focused = focus_ == w.id;
  const bool pressed = drag_.id == w.id && drag_.kind == DragState::Kind::Press;
  const bool editing = edit_.id == w.id;
  const bool disabled = !w.enabled;
  const Rect &r = w.rect;
  const float px = st.pixel;
  const Color none{0, 0, 0, 0};
  const FontStyle &font = w.mono ? st.mono : st.font;
  const FontMetrics fm = tm.metrics(font);
  auto baseline = [&](const Rect &rr) { return std::round(rr.cy() + (fm.ascent - fm.descent) * 0.5f); };
  auto text_in = [&](const Rect &rr, std::string_view s, Align a, Color c) {
    if (s.empty() || rr.w <= 0) {
      return;
    }
    std::string t = clip_text(s, rr.w, tm, font);
    const float tw = tm.width(t, font);
    float x = rr.x;
    if (a == Align::Center) {
      x = rr.x + std::max(0.0f, (rr.w - tw) * 0.5f);
    }
    else if (a == Align::Right) {
      x = rr.x1() - tw;
    }
    draw_.text(std::move(t), {std::round(x), baseline(rr)}, font, c);
  };
  auto box = [&](const Rect &rr, const WidgetColors &c, uint8_t corners, bool emboss = true) -> DrawCmd & {
    return draw_.round_box(rr, clamp_radius(c.roundness * st.unit, rr), corners, c.inner, c.outline,
                           emboss && c.outline.a ? th.widget_emboss : none);
  };
  /* Text field / number editing: selection, text, IME preedit underline, caret. */
  auto draw_editing = [&](const Rect &area) {
    const TextEdit &ed = edit_.edit;
    const bool pw = edit_.password;
    const std::string raw = ed.display_text();
    const std::string disp = pw ? mask_text(raw) : raw;
    /* Byte offsets of the display text (masked for passwords). */
    const auto dpos = [&](const size_t i) { return pw ? mask_offset(raw, i) : i; };
    const size_t caret = dpos(ed.display_caret());
    const float caret_x = tm.caret_x(disp, caret, font);
    /* Keep the caret visible. */
    float &sx = edit_.scroll_x;
    if (caret_x - sx > area.w - px) {
      sx = caret_x - area.w + px;
    }
    if (caret_x - sx < 0) {
      sx = caret_x;
    }
    const float full = tm.width(disp, font);
    if (full - sx < area.w) {
      sx = std::max(0.0f, full - area.w);
    }
    const float x0 = std::round(area.x - sx);
    const float by = baseline(area);
    draw_.clip_push(area);
    if (ed.has_selection() && !ed.composing()) {
      const auto [s0, s1] = ed.selection();
      const float a = tm.caret_x(disp, dpos(s0), font), b = tm.caret_x(disp, dpos(s1), font);
      draw_.rect(snap({x0 + a, area.y + 2 * px, b - a, area.h - 4 * px}), th.text.item);
    }
    draw_.text(disp, {x0, by}, font, th.text.text_sel);
    if (ed.composing()) {
      /* IME preedit: underline under the composition, thicker under the caret segment. */
      const auto [p0r, p1r] = ed.display_preedit();
      const size_t p0 = dpos(p0r), p1 = dpos(p1r);
      const float a = tm.caret_x(disp, p0, font), b = tm.caret_x(disp, p1, font);
      const float uy = std::round(by + std::max(px, fm.descent * 0.5f));
      draw_.rect(snap({x0 + a, uy, b - a, px}), th.text.text_sel);
      if (caret > p0 && caret <= p1) {
        draw_.rect(snap({x0 + a, uy, caret_x - a, 2 * px}), th.text.text_sel);
      }
    }
    const float cw = std::max(1.0f, std::round(1.5f * st.scale));
    const Rect cr = snap({x0 + caret_x - cw * 0.5f, area.y + 2 * px, cw, area.h - 4 * px});
    draw_.rect(cr, th.text_cursor);
    draw_.clip_pop();
    edit_caret_ = cr;
  };

  switch (w.type) {
    case WidgetType::Label: {
      const Color c = th.space_text.scaled_alpha(disabled ? 0.5f : 1.0f);
      text_in(r.inset(st.text_margin, 0), w.text, w.align, c);
      break;
    }
    case WidgetType::Paragraph: {
      const bool overlay = w.block && (w.block->kind() == Block::Kind::Tooltip || w.block->kind() == Block::Kind::Toast);
      const Color c = (overlay ? th.tooltip.text : th.space_text).scaled_alpha(disabled ? 0.5f : 1.0f);
      const float pad = std::round(0.2f * st.unit);
      const FontMetrics m = tm.metrics(st.font);
      const float lead = std::round((st.line_height - (m.ascent + m.descent)) * 0.5f + m.ascent);
      for (size_t i = 0; i < w.lines.size(); i++) {
        const TextLine &ln = w.lines[i];
        draw_.text(w.text.substr(ln.begin, ln.end - ln.begin),
                   {r.x + st.text_margin, r.y + pad + float(i) * st.line_height + lead}, st.font, c);
      }
      break;
    }
    case WidgetType::Button: {
      const WidgetColors c = state_colors(th.regular, pressed, hover || focused, disabled);
      box(r, c, w.corners);
      text_in(r.inset(st.text_margin, 0), w.text, Align::Center, c.text);
      break;
    }
    case WidgetType::MenuButton: {
      const bool open = popup_.owner == w.id;
      WidgetColors c = th.pulldown;
      if (open || hover || focused) {
        c.inner = c.inner_sel;
      }
      c = state_colors(c, false, false, disabled);
      box(r, c, w.corners, false);
      text_in(r.inset(st.text_margin, 0), w.text, Align::Center, c.text);
      break;
    }
    case WidgetType::Checkbox: {
      const bool on = w.boolean.value();
      const WidgetColors c = state_colors(th.option, on, hover || focused, disabled);
      Rect sq{r.x, r.y, r.h, r.h};
      const float delta = std::floor((r.h - 2 * px) / 6.0f);
      sq = {sq.x, sq.y + delta, sq.w - 2 * delta, sq.h - 2 * delta};
      DrawCmd &cmd = draw_.round_box(sq, clamp_radius(c.roundness * sq.h, sq), CORNER_ALL, c.inner, c.outline,
                                     c.outline.a ? th.widget_emboss : none);
      if (on) {
        cmd.tria = Tria::Check;
        cmd.tria_center = {sq.x + 0.5f * sq.h, sq.y + 0.5f * sq.h};
        cmd.tria_size = 0.5f * sq.h;
        cmd.tria_color = c.item;
      }
      const WidgetColors tc = state_colors(th.option, false, hover || focused, disabled);
      text_in({sq.x1() + std::round(delta * 0.9f) + px, r.y, r.x1() - sq.x1() - delta, r.h}, w.text, Align::Left,
              tc.text);
      break;
    }
    case WidgetType::TextField: {
      WidgetColors c = state_colors(th.text, editing, (hover || focused) && !editing, disabled);
      box(r, c, w.corners);
      const Rect area = r.inset(st.text_margin, 0);
      if (editing) {
        draw_editing(area);
      }
      else {
        const std::string v = w.string.value();
        if (v.empty() && !w.text_opts.placeholder.empty()) {
          text_in(area, w.text_opts.placeholder, Align::Left, c.text.scaled_alpha(0.45f));
        }
        else {
          text_in(area, w.text_opts.password ? mask_text(v) : v, Align::Left, c.text);
        }
      }
      break;
    }
    case WidgetType::Number:
    case WidgetType::Slider: {
      const bool slider = w.type == WidgetType::Slider;
      const WidgetColors &base = slider ? th.numslider : th.num;
      const bool dragging = drag_.id == w.id && drag_.moved;
      WidgetColors c = state_colors(base, editing || dragging, false, disabled);
      const float rad = clamp_radius(c.roundness * st.unit, r);
      if (editing) {
        box(r, c, w.corners);
        draw_editing(r.inset(st.text_margin, 0));
        break;
      }
      const double v = w.number.value();
      if (slider) {
        /* Inner, then the fill in the item colour, then the outline on top. */
        const WidgetColors hc = (hover || focused) && !dragging ? active_colors(c) : c;
        draw_.round_box(r, rad, w.corners, hc.inner, none, th.widget_emboss);
        double lo = w.props.soft_lo(), hi = w.props.soft_hi();
        float f = 0.0f;
        if (std::isfinite(lo) && std::isfinite(hi) && hi > lo) {
          f = float(std::clamp((v - lo) / (hi - lo), 0.0, 1.0));
        }
        const float fw = std::round(r.w * f);
        if (fw > 0.0f) {
          uint8_t corners = w.corners & CORNER_LEFT;
          if (fw >= r.w - rad) {
            corners = w.corners;
          }
          const Rect fr{r.x, r.y, fw, r.h};
          draw_.round_box(fr, clamp_radius(rad, {0, 0, fw * 2, r.h}), corners, c.item, none);
        }
        draw_.round_box(r, rad, w.corners, none, hc.outline);
        c = hc;
      }
      else {
        const bool hot = (hover || focused) && !dragging;
        const WidgetColors hc = hot ? active_colors(c) : c;
        if (hot) {
          /* Arrow zones (widget_numbut_draw). */
          const float handle = std::min(r.w / 3.0f, r.h * 0.7f);
          draw_.round_box(r, rad, w.corners, none, none, th.widget_emboss);
          for (int side = -1; side <= 1; side++) {
            const bool zone_hot = hover && hover_zone_ == side;
            const WidgetColors zc = zone_hot ? active_colors(c) : c;
            Rect zr;
            uint8_t corners;
            if (side == -1) {
              zr = {r.x, r.y, handle + px, r.h};
              corners = w.corners & CORNER_LEFT;
            }
            else if (side == 1) {
              zr = {r.x1() - handle - px, r.y, handle + px, r.h};
              corners = w.corners & CORNER_RIGHT;
            }
            else {
              zr = {r.x + handle - px, r.y, r.w - 2 * handle + 2 * px, r.h};
              corners = CORNER_NONE;
            }
            DrawCmd &zcmd = draw_.round_box(snap(zr), side == 0 ? 0.0f : rad, corners,
                                            side == 0 && hover && hover_zone_ == 0 ? active_colors(c).inner : zc.inner,
                                            none);
            if (side != 0) {
              zcmd.tria = side < 0 ? Tria::ArrowLeft : Tria::ArrowRight;
              zcmd.tria_center = {side < 0 ? zr.x + 0.4f * r.h : zr.x1() - 0.4f * r.h, r.y + 0.5f * r.h};
              zcmd.tria_size = 0.3f * r.h;
              zcmd.tria_color = zc.text;
            }
          }
          draw_.round_box(r, rad, w.corners, none, hc.outline);
        }
        else {
          box(r, c, w.corners);
        }
        c = hc;
      }
      /* Text: "Label" left and value right, or the value centred. */
      const float pad = slider ? st.text_margin : std::round(0.5f * r.h);
      const Rect area = r.inset(pad, 0);
      std::string value = format_number(v, w.props);
      if (!w.props.unit.empty()) {
        value += " " + w.props.unit;
      }
      if (w.text.empty()) {
        text_in(area, value, Align::Center, c.text);
      }
      else {
        const float vw = tm.width(value, font);
        text_in({area.x, area.y, std::max(0.0f, area.w - vw - st.text_margin * 0.5f), area.h}, w.text, Align::Left,
                c.text);
        text_in(area, value, Align::Right, c.text);
      }
      break;
    }
    case WidgetType::Dropdown:
    case WidgetType::ColormapDropdown: {
      const bool open = popup_.owner == w.id;
      const WidgetColors c = state_colors(th.menu, false, hover || focused || open, disabled);
      DrawCmd &cmd = box(r, c, w.corners);
      const float h = r.h;
      if (r.w / h >= 0.5f) {
        cmd.tria = Tria::Menu;
        cmd.tria_center = {r.w > h * 1.1f ? r.x1() - 0.32f * h : r.x + 0.52f * h, r.y + 0.48f * h};
        cmd.tria_size = 0.4f * h;
        cmd.tria_color = c.item;
      }
      const int sel = w.index ? w.index.value() : -1;
      Rect area{r.x + st.text_margin, r.y, r.w - st.text_margin - h * 0.8f, h};
      if (w.type == WidgetType::ColormapDropdown && w.colormaps && sel >= 0 && size_t(sel) < w.colormaps->size()) {
        const float sw = std::min(std::round(4.0f * st.unit), std::round(area.w * 0.5f));
        const Rect strip = snap({area.x, r.y + 0.25f * h, sw, 0.5f * h});
        draw_.color_strip(strip, (*w.colormaps)[size_t(sel)].lut);
        area.x += sw + st.text_margin * 0.5f;
        area.w -= sw + st.text_margin * 0.5f;
      }
      if (sel >= 0 && size_t(sel) < w.items.size()) {
        text_in(area, w.items[size_t(sel)], Align::Left, c.text);
      }
      break;
    }
    case WidgetType::MenuItem: {
      const bool hl = popup_.highlight == w.menu_index && w.enabled;
      const WidgetColors c = state_colors(th.menu_item, hl, false, !w.enabled);
      if (hl) {
        box(r.inset(px, 0), c, CORNER_ALL, false);
      }
      Rect area = r.inset(st.text_margin, 0);
      if (w.colormaps && w.menu_index >= 0 && size_t(w.menu_index) < w.colormaps->size()) {
        const float sw = std::round(4.0f * st.unit);
        draw_.color_strip(snap({area.x, r.y + 0.25f * r.h, sw, 0.5f * r.h}), (*w.colormaps)[size_t(w.menu_index)].lut);
        area.x += sw + st.text_margin;
        area.w -= sw + st.text_margin;
      }
      text_in(area, w.text, Align::Left, c.text);
      break;
    }
    case WidgetType::Tabs: {
      const int n = int(w.items.size());
      const int sel = w.index ? w.index.value() : -1;
      for (int i = 0; i < n; i++) {
        const float x0 = std::round(r.x + r.w * float(i) / float(n));
        const float x1 = std::round(r.x + r.w * float(i + 1) / float(n));
        const Rect tr{x0, r.y, x1 - x0 - (i + 1 < n ? px : 0.0f), r.h};
        const bool hot = hover && hover_zone_ == i && i != sel;
        const WidgetColors c = state_colors(th.tab, i == sel, hot, disabled);
        box(tr, c, CORNER_TOP, false);
        text_in(tr.inset(st.text_margin * 0.5f, 0), w.items[size_t(i)], Align::Center, c.text);
      }
      if (focused) {
        draw_.rect({r.x, r.y1() - px, r.w, px}, th.menu.inner_sel);
      }
      break;
    }
    case WidgetType::PanelHeader: {
      const bool open = panel_open(w.id, true);
      const Color tc = (hover || focused) ? th.panel_title.mul_hsl(1, 1, 1.1f) : th.panel_title;
      const float s = std::round(0.3f * st.unit);
      const float cx = r.x + std::round(0.6f * st.unit), cy = r.cy();
      if (open) {
        draw_.triangle({cx - s, cy - s * 0.5f}, {cx + s, cy - s * 0.5f}, {cx, cy + s * 0.6f}, tc.scaled_alpha(0.8f));
      }
      else {
        draw_.triangle({cx - s * 0.5f, cy - s}, {cx - s * 0.5f, cy + s}, {cx + s * 0.6f, cy}, tc.scaled_alpha(0.8f));
      }
      text_in({r.x + std::round(1.2f * st.unit), r.y, r.w - std::round(1.6f * st.unit), r.h}, w.text, Align::Left, tc);
      break;
    }
    case WidgetType::CurvePreview: {
      draw_.round_box(r, 0, CORNER_NONE, th.box.inner, th.box.outline);
      const Rect plot = r.inset(5 * px, 5 * px);
      if (plot.empty()) {
        break;
      }
      draw_.clip_push(plot);
      for (int i = 0; i <= 4; i++) {
        const float t = float(i) / 4;
        draw_.rect({plot.x + t * plot.w, plot.y, px, plot.h}, th.box.outline);
        draw_.rect({plot.x, plot.y + t * plot.h, plot.w, px}, th.box.outline);
      }
      std::vector<Vec2> points;
      for (Vec2 p : w.curve) {
        if (std::isfinite(p.x) && std::isfinite(p.y)) {
          points.push_back({std::clamp(p.x, 0.0f, 1.0f), std::clamp(p.y, 0.0f, 1.0f)});
        }
      }
      std::stable_sort(points.begin(), points.end(), [](Vec2 a, Vec2 b) { return a.x < b.x; });
      /* Duplicate positions follow the payload contract: last point wins. */
      std::vector<Vec2> unique;
      for (Vec2 p : points) {
        if (!unique.empty() && unique.back().x == p.x) {
          unique.back() = p;
        }
        else {
          unique.push_back(p);
        }
      }
      auto screen = [&](Vec2 p) { return Vec2{plot.x + p.x * plot.w, plot.y1() - p.y * plot.h}; };
      if (!unique.empty()) {
        points = unique;
        points.insert(points.begin(), {0, points.front().y});
        points.push_back({1, points.back().y});
        for (size_t i = 1; i < points.size(); i++) {
          const Vec2 a = screen(points[i - 1]), b = screen(points[i]);
          const float len = std::hypot(b.x - a.x, b.y - a.y);
          if (len <= 0) {
            continue;
          }
          const Vec2 d{-(b.y - a.y) * px / len, (b.x - a.x) * px / len};
          draw_.triangle({a.x + d.x, a.y + d.y}, {a.x - d.x, a.y - d.y},
                         {b.x + d.x, b.y + d.y}, th.progress.item);
          draw_.triangle({a.x - d.x, a.y - d.y}, {b.x - d.x, b.y - d.y},
                         {b.x + d.x, b.y + d.y}, th.progress.item);
        }
        for (Vec2 p : unique) {
          const Vec2 c = screen(p);
          draw_.rect({c.x - 2 * px, c.y - 2 * px, 4 * px, 4 * px}, th.box.text);
        }
      }
      draw_.clip_pop();
      break;
    }
    case WidgetType::Progress: {
      const WidgetColors &c = th.progress;
      const float rad = clamp_radius(c.roundness * st.unit, r);
      draw_.round_box(r, rad, w.corners, c.inner, c.outline, th.widget_emboss);
      const float f = std::clamp(w.fraction, 0.0f, 1.0f);
      const float fw = std::round((r.w - 2 * px) * f);
      if (fw > 0) {
        const Rect fr{r.x + px, r.y + px, fw, r.h - 2 * px};
        draw_.round_box(fr, clamp_radius(rad - px, {0, 0, fw * 2, fr.h}), fw >= r.w - rad ? CORNER_ALL : CORNER_LEFT,
                        c.item, none);
      }
      std::string t = w.text;
      if (t.empty()) {
        t = std::to_string(int(std::round(f * 100.0f))) + "%";
      }
      text_in(r.inset(st.text_margin, 0), t, Align::Center, c.text);
      break;
    }
    case WidgetType::VirtualList:
    case WidgetType::Table:
    case WidgetType::LogView: {
      const bool log = w.type == WidgetType::LogView;
      const bool table = w.type == WidgetType::Table;
      const WidgetColors &bc = log ? th.text : th.box;
      draw_.round_box(r, clamp_radius(bc.roundness * st.unit, r), CORNER_ALL, bc.inner, bc.outline);
      const float row_h = list_row_height(w);
      const float header = table ? row_h : 0.0f;
      const Rect body{r.x + px, r.y + px + header, r.w - 2 * px, r.h - 2 * px - header};
      const float ms = max_scroll(w);
      if (log && (!follow_.count(w.id) || follow_[w.id])) {
        follow_[w.id] = true;
        scroll_[w.id] = ms;
      }
      float scroll = std::clamp(scroll_of(w.id), 0.0f, ms);
      scroll_[w.id] = scroll;
      const float sbw = ms > 0.0f ? st.scrollbar + 2 * px : 0.0f;
      const int count = w.list ? w.list->count : (w.table ? w.table->rows : int(w.log->line_count()));
      const float lpad = log ? std::round(0.2f * st.unit) : 0.0f;
      const int first = std::max(0, int((scroll - lpad) / row_h));
      const int last = std::min(count, int((scroll + body.h) / row_h) + 1);
      const int hover_row = hover ? hover_zone_ : -1;
      if (table) {
        /* Header cells with sort indicator and column separators. */
        TableState &ts = table_state(w);
        float x = r.x + px;
        const Rect hdr{r.x + px, r.y + px, r.w - 2 * px, row_h};
        draw_.round_box(hdr, clamp_radius(bc.roundness * st.unit, hdr), CORNER_TOP, th.panel_header, none);
        draw_.clip_push(hdr);
        for (int c = 0; c < int(w.table->columns.size()); c++) {
          const TableColumn &col = w.table->columns[size_t(c)];
          const float cw = table_col_px(w, c);
          const Rect cell{x, hdr.y, cw, row_h};
          float tw = cell.w - st.text_margin * 2;
          if (ts.sort_col == c) {
            const float s = std::round(0.2f * st.unit);
            const float cx = cell.x1() - st.text_margin - s, cy = cell.cy();
            if (ts.ascending) {
              draw_.triangle({cx - s, cy + s * 0.5f}, {cx + s, cy + s * 0.5f}, {cx, cy - s * 0.6f}, th.space_text);
            }
            else {
              draw_.triangle({cx - s, cy - s * 0.5f}, {cx + s, cy - s * 0.5f}, {cx, cy + s * 0.6f}, th.space_text);
            }
            tw -= 3 * s;
          }
          text_in({cell.x + st.text_margin, cell.y, tw, cell.h}, col.title, col.numeric ? Align::Right : Align::Left,
                  th.space_text);
          x += cw;
          if (c + 1 < int(w.table->columns.size())) {
            draw_.rect({x - px, hdr.y + 2 * px, px, row_h - 4 * px}, th.box.outline);
          }
        }
        draw_.clip_pop();
      }
      draw_.clip_push(body);
      const std::vector<int> *perm = table ? &table_perm(w) : nullptr;
      const int selected = w.list && w.list->selected ? w.list->selected.value() :
                           (w.table && w.table->selected ? w.table->selected.value() : -1);
      for (int i = first; i < last; i++) {
        const float y = std::round(body.y + lpad + float(i) * row_h - scroll);
        const Rect row{body.x, y, body.w - sbw, row_h};
        if (log) {
          draw_.text(std::string(w.log->line(size_t(i))), {row.x + st.text_margin, baseline(row)}, st.mono,
                     th.tooltip.text);
          continue;
        }
        const int model = perm ? (*perm)[size_t(i)] : i;
        const bool sel = model == selected;
        const WidgetColors &lc = th.list_item;
        if (table && (i % 2) == 1) {
          draw_.rect(row, th.panel_sub_back);
        }
        if (sel) {
          draw_.round_box(row.inset(px, 0), clamp_radius(lc.roundness * st.unit, row), CORNER_ALL, lc.inner_sel, none);
        }
        else if (i == hover_row) {
          draw_.round_box(row.inset(px, 0), clamp_radius(lc.roundness * st.unit, row), CORNER_ALL,
                          lc.item.scaled_alpha(0.5f), none);
        }
        const Color tc = sel ? lc.text_sel : lc.text;
        if (w.list) {
          text_in(row.inset(st.text_margin, 0), w.list->text ? w.list->text(i) : std::string(), Align::Left, tc);
        }
        else {
          float x = r.x + px;
          for (int c = 0; c < int(w.table->columns.size()); c++) {
            const float cw = table_col_px(w, c);
            const Rect cell{x + st.text_margin, row.y, cw - 2 * st.text_margin, row.h};
            Color cc = tc;
            if (!sel && w.table->cell_color) {
              const Color custom = w.table->cell_color(model, c);
              if (custom.a != 0) {
                cc = custom;
              }
            }
            text_in(cell, w.table->cell ? w.table->cell(model, c) : std::string(),
                    w.table->columns[size_t(c)].numeric ? Align::Right : Align::Left, cc);
            x += cw;
          }
        }
      }
      draw_.clip_pop();
      if (ms > 0.0f) {
        const bool hot = hover && mouse_.x >= body.x1() - st.scrollbar - 2 * px;
        draw_scrollbar(body, ms + body.h, body.h, scroll, hot);
      }
      if (log && !follow_[w.id]) {
        const std::string_view label = tr("ui.log.follow");
        const float ph = std::round(0.9f * st.unit);
        const float pw = std::round(LayoutEngine::text_w(*this, label) + st.unit);
        const Rect pill{r.x1() - pw - st.scrollbar - 3 * px, r.y1() - ph - 3 * px, pw, ph};
        draw_.round_box(pill, pill.h * 0.5f, CORNER_ALL, th.menu.inner_sel, none);
        const FontMetrics m = tm.metrics(st.font);
        draw_.text(std::string(label), {pill.x + std::round(st.unit * 0.5f), std::round(pill.cy() + (m.ascent - m.descent) * 0.5f)},
                   st.font, th.tooltip.text_sel);
      }
      if (focused && !log) {
        draw_.round_box(r, clamp_radius(bc.roundness * st.unit, r), CORNER_ALL, none, th.menu.inner_sel);
      }
      break;
    }
    case WidgetType::Image: {
      draw_.round_box(r, clamp_radius(th.text.roundness * st.unit, r), CORNER_ALL, th.text.inner, th.text.outline);
      if (w.image.texture) {
        const Rect area = r.inset(px, px);
        draw_.clip_push(area);
        draw_.image(image_display_rect(w), w.image.texture, {0, 0, 1, 1});
        draw_.clip_pop();
      }
      break;
    }
    case WidgetType::SplitterBar: {
      const bool hot = hover || (drag_.id == w.id);
      const Color c = hot ? th.menu.inner_sel : th.editor_border;
      const float lw = std::max(1.0f, std::round(st.scale));
      draw_.rect(snap({r.cx() - lw * 0.5f, r.y, lw, r.h}), c);
      break;
    }
  }
}

}  // namespace stk::ui
