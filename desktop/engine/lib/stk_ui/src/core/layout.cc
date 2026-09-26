/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Layout building (uiLayout-style containers and widget constructors) and resolution:
 * preferred widths bottom-up, widths top-down (row distribution like Blender's ui_item_fit),
 * heights bottom-up (wrapped paragraphs depend on their width), positions top-down.
 */
#include <algorithm>
#include <cmath>

#include "layout_engine.hh"
#include "stk/ui/ui.hh"
#include "stk/ui/utf8.hh"

namespace stk::ui {

Binding<double> bind_float(float &ref)
{
  return {[&ref]() { return double(ref); }, [&ref](double v) { ref = float(v); }};
}

Binding<double> bind_int(int &ref)
{
  return {[&ref]() { return double(ref); }, [&ref](double v) { ref = int(std::lround(v)); }};
}

const char *widget_type_name(WidgetType t)
{
  switch (t) {
    case WidgetType::Label: return "label";
    case WidgetType::Paragraph: return "paragraph";
    case WidgetType::Button: return "button";
    case WidgetType::Checkbox: return "checkbox";
    case WidgetType::TextField: return "text";
    case WidgetType::Number: return "number";
    case WidgetType::Slider: return "slider";
    case WidgetType::Dropdown: return "dropdown";
    case WidgetType::ColormapDropdown: return "colormap";
    case WidgetType::MenuButton: return "menu_button";
    case WidgetType::Tabs: return "tabs";
    case WidgetType::PanelHeader: return "panel";
    case WidgetType::Progress: return "progress";
    case WidgetType::VirtualList: return "list";
    case WidgetType::LogView: return "log";
    case WidgetType::Table: return "table";
    case WidgetType::Image: return "image";
    case WidgetType::SplitterBar: return "splitter";
    case WidgetType::MenuItem: return "menu_item";
    case WidgetType::CurvePreview: return "curve_preview";
  }
  return "?";
}

bool Widget::focusable() const
{
  if (!enabled) {
    return false;
  }
  switch (type) {
    case WidgetType::Label:
    case WidgetType::Paragraph:
    case WidgetType::Progress:
    case WidgetType::SplitterBar:
    case WidgetType::Image:
    case WidgetType::CurvePreview:
      return false;
    default:
      return true;
  }
}

Widget &Widget::tip(std::string_view t)
{
  tooltip = std::string(t);
  return *this;
}

Widget &Widget::disable(bool disabled)
{
  enabled = !disabled;
  return *this;
}

Widget &Widget::width(float units)
{
  fixed_width = block ? block->ctx().style().u(units) : units * 20.0f;
  return *this;
}

/* -------------------------------------------------------------------- */
/* Building */

Context &Layout::ctx() const
{
  return block_->ctx();
}

Layout &Layout::add_child(Kind kind, bool align)
{
  block_->layouts_.emplace_back();
  Layout &c = block_->layouts_.back();
  c.kind_ = kind;
  c.block_ = block_;
  c.align_ = align;
  c.enabled_ = enabled_;
  c.scale_y_ = scale_y_;
  c.scope_ = scope_;
  c.path_ = path_;
  items_.push_back({&c, nullptr, 0.0f});
  return c;
}

Widget &Layout::add_widget(WidgetType type, std::string_view key)
{
  block_->widgets_.emplace_back();
  Widget &w = block_->widgets_.back();
  w.type = type;
  w.block = block_;
  w.enabled = enabled_;
  std::string k = key.empty() ? "#" + std::to_string(block_->widgets_.size() - 1) : std::string(key);
  w.id = utf8::hash_combine(scope_, utf8::fnv1a(k));
  w.key = path_ + "/" + k;
  w.height = std::round(block_->ctx().style().unit * scale_y_);
  items_.push_back({nullptr, &w, 0.0f});
  return w;
}

Layout &Layout::row(bool align)
{
  return add_child(Kind::Row, align);
}

Layout &Layout::column(bool align)
{
  return add_child(Kind::Column, align);
}

Layout &Layout::split(float factor, bool align)
{
  Layout &l = add_child(Kind::Split, align);
  l.split_factor_ = std::clamp(factor, 0.0f, 1.0f);
  return l;
}

Layout &Layout::grid(int columns, bool align)
{
  Layout &l = add_child(Kind::Grid, align);
  l.columns_ = std::max(1, columns);
  return l;
}

Layout &Layout::box()
{
  return add_child(Kind::Box, false);
}

Layout &Layout::scope(std::string_view key)
{
  Layout &l = add_child(Kind::Column, false);
  l.scope_ = utf8::hash_combine(scope_, utf8::fnv1a(key));
  l.path_ = path_ + "/" + std::string(key);
  return l;
}

Layout *Layout::panel(std::string_view key, std::string_view title, bool default_open)
{
  Layout &p = add_child(Kind::Panel, false);
  const WidgetId pid = utf8::hash_combine(scope_, utf8::fnv1a(key));
  p.scope_ = pid;
  p.path_ = path_ + "/" + std::string(key);
  Widget &h = p.add_widget(WidgetType::PanelHeader, "");
  h.id = pid;
  h.key = p.path_;
  h.text = std::string(title);
  h.height = block_->ctx().style().panel_header;
  p.header_ = &h;
  /* Remember the default so the first toggle flips it (panel state persists by id). */
  block_->ctx().panels_.try_emplace(pid, default_open);
  p.open_ = block_->ctx().panel_open(pid, default_open);
  if (!p.open_) {
    return nullptr;
  }
  return &p.add_child(Kind::Column, false);
}

Layout &Layout::prop(std::string_view label, std::string_view tooltip)
{
  Layout &s = split(0.4f, false);
  Widget &l = s.label(label, Align::Right);
  l.tooltip = std::string(tooltip);
  return s.column(true);
}

std::pair<Layout *, Layout *> Layout::splitter(std::string_view key, Binding<float> factor)
{
  Layout &s = add_child(Kind::Splitter, false);
  Layout &a = s.add_child(Kind::Column, false);
  Widget &bar = s.add_widget(WidgetType::SplitterBar, key);
  bar.factor = std::move(factor);
  bar.fixed_width = std::max(2.0f, std::round(0.3f * ctx().style().unit));
  Layout &b = s.add_child(Kind::Column, false);
  return {&a, &b};
}

void Layout::separator(float units)
{
  items_.push_back({nullptr, nullptr, ctx().style().u(units)});
}

Layout &Layout::scale_y(float s)
{
  scale_y_ = s;
  return *this;
}

Layout &Layout::alignment(LayoutAlign a)
{
  alignment_ = a;
  return *this;
}

Layout &Layout::enabled(bool e)
{
  enabled_ = e;
  return *this;
}

Widget &Layout::label(std::string_view text, Align align)
{
  Widget &w = add_widget(WidgetType::Label, "");
  w.text = std::string(text);
  w.align = align;
  return w;
}

Widget &Layout::paragraph(std::string_view text)
{
  Widget &w = add_widget(WidgetType::Paragraph, "");
  w.text = std::string(text);
  return w;
}

Widget &Layout::button(std::string_view key, std::string_view text, std::function<void()> on_click)
{
  Widget &w = add_widget(WidgetType::Button, key);
  w.text = std::string(text);
  w.align = Align::Center;
  w.on_click = std::move(on_click);
  return w;
}

Widget &Layout::checkbox(std::string_view key, std::string_view text, Binding<bool> value)
{
  Widget &w = add_widget(WidgetType::Checkbox, key);
  w.text = std::string(text);
  w.boolean = std::move(value);
  return w;
}

Widget &Layout::text_field(std::string_view key, Binding<std::string> value, TextFieldOptions opts)
{
  Widget &w = add_widget(WidgetType::TextField, key);
  w.string = std::move(value);
  w.mono = opts.mono;
  w.text_opts = std::move(opts);
  return w;
}

Widget &Layout::number(std::string_view key, std::string_view label, Binding<double> value, NumberProps props)
{
  Widget &w = add_widget(WidgetType::Number, key);
  w.text = std::string(label);
  w.number = std::move(value);
  w.props = std::move(props);
  w.align = Align::Center;
  return w;
}

Widget &Layout::slider(std::string_view key, std::string_view label, Binding<double> value, NumberProps props)
{
  Widget &w = number(key, label, std::move(value), std::move(props));
  w.type = WidgetType::Slider;
  return w;
}

Widget &Layout::dropdown(std::string_view key, std::vector<std::string> items, Binding<int> selected)
{
  Widget &w = add_widget(WidgetType::Dropdown, key);
  w.items = std::move(items);
  w.index = std::move(selected);
  return w;
}

Widget &Layout::colormap_dropdown(std::string_view key,
                                  std::shared_ptr<const std::vector<ColormapItem>> colormaps,
                                  Binding<int> selected)
{
  Widget &w = add_widget(WidgetType::ColormapDropdown, key);
  w.colormaps = std::move(colormaps);
  w.index = std::move(selected);
  if (w.colormaps) {
    for (const ColormapItem &c : *w.colormaps) {
      w.items.push_back(c.name);
    }
  }
  return w;
}

Widget &Layout::menu_button(std::string_view key, std::string_view text, std::vector<MenuEntry> entries)
{
  Widget &w = add_widget(WidgetType::MenuButton, key);
  w.text = std::string(text);
  w.menu = std::move(entries);
  for (const MenuEntry &e : w.menu) {
    w.items.push_back(e.text);
  }
  return w;
}

Widget &Layout::tabs(std::string_view key, std::vector<std::string> labels, Binding<int> selected)
{
  Widget &w = add_widget(WidgetType::Tabs, key);
  w.items = std::move(labels);
  w.index = std::move(selected);
  return w;
}

Widget &Layout::progress(float fraction, std::string_view text)
{
  Widget &w = add_widget(WidgetType::Progress, "");
  w.fraction = fraction;
  w.text = std::string(text);
  w.align = Align::Center;
  return w;
}

Widget &Layout::virtual_list(std::string_view key, ListSpec spec)
{
  Widget &w = add_widget(WidgetType::VirtualList, key);
  const Style &st = ctx().style();
  w.height = std::round(spec.rows * st.unit * scale_y_) + 2.0f * st.pixel;
  w.list = std::make_shared<ListSpec>(std::move(spec));
  return w;
}

Widget &Layout::log_view(std::string_view key, const LogBuffer &log, float height_units)
{
  Widget &w = add_widget(WidgetType::LogView, key);
  w.log = &log;
  w.mono = true;
  w.height = ctx().style().u(height_units);
  return w;
}

Widget &Layout::table(std::string_view key, TableSpec spec)
{
  Widget &w = add_widget(WidgetType::Table, key);
  const Style &st = ctx().style();
  w.height = std::round((spec.visible_rows + 1.0f) * st.unit * scale_y_) + 2.0f * st.pixel;
  w.table = std::make_shared<TableSpec>(std::move(spec));
  return w;
}

Widget &Layout::image(std::string_view key, ImageSpec spec)
{
  Widget &w = add_widget(WidgetType::Image, key);
  w.height = ctx().style().u(spec.height_units);
  w.image = spec;
  return w;
}

Widget &Layout::curve_preview(std::string_view key, std::vector<Vec2> points)
{
  Widget &w = add_widget(WidgetType::CurvePreview, key);
  w.height = ctx().style().u(4.0f);
  w.curve = std::move(points);
  return w;
}

/* -------------------------------------------------------------------- */
/* Resolution */

float LayoutEngine::text_w(const Context &ctx, std::string_view s, bool mono)
{
  return ctx.measurer().width(s, mono ? ctx.style().mono : ctx.style().font);
}

float LayoutEngine::pref_width(const Context &ctx, const Widget &w)
{
  if (w.fixed_width > 0.0f) {
    return w.fixed_width;
  }
  const Style &st = ctx.style();
  const float m = st.text_margin;
  switch (w.type) {
    case WidgetType::Label:
      return text_w(ctx, w.text) + 2 * m;
    case WidgetType::Paragraph:
      return std::min(text_w(ctx, w.text) + 2 * m, 20.0f * st.unit);
    case WidgetType::Button:
    case WidgetType::MenuButton:
      return std::max(2.0f * st.unit, text_w(ctx, w.text) + 2 * m);
    case WidgetType::Checkbox:
      return w.height + text_w(ctx, w.text) + m;
    case WidgetType::TextField:
      return 8.0f * st.unit;
    case WidgetType::Number:
    case WidgetType::Slider:
      return std::max(5.0f * st.unit, text_w(ctx, w.text) + 4.0f * st.unit);
    case WidgetType::Dropdown: {
      float mx = 0.0f;
      for (const std::string &s : w.items) {
        mx = std::max(mx, text_w(ctx, s));
      }
      return mx + 2 * m + st.unit;
    }
    case WidgetType::ColormapDropdown:
      return 8.0f * st.unit;
    case WidgetType::Tabs: {
      float sum = 0.0f;
      for (const std::string &s : w.items) {
        sum += text_w(ctx, s) + 2 * m;
      }
      return sum;
    }
    case WidgetType::Progress:
      return 6.0f * st.unit;
    case WidgetType::VirtualList:
    case WidgetType::LogView:
    case WidgetType::Table:
    case WidgetType::Image:
    case WidgetType::CurvePreview:
      return 10.0f * st.unit;
    case WidgetType::SplitterBar:
      return st.unit * 0.3f;
    case WidgetType::PanelHeader:
      return text_w(ctx, w.text) + 2 * st.unit;
    case WidgetType::MenuItem:
      return text_w(ctx, w.text) + 2 * m;
  }
  return st.unit;
}

float LayoutEngine::space(const Layout &l, const Style &st)
{
  if (l.align_) {
    return 0.0f;
  }
  switch (l.kind_) {
    case Layout::Kind::Row:
    case Layout::Kind::Split:
      return st.space_x;
    case Layout::Kind::Grid:
      return st.column_space;
    default:
      return st.space_y;
  }
}

float LayoutEngine::measure(Context &ctx, Layout &l)
{
  const Style &st = ctx.style();
  float w = 0.0f;
  const float sp = space(l, st);
  int n = 0;
  float mx = 0.0f;
  for (Layout::Item &it : l.items_) {
    float cw;
    if (it.layout) {
      cw = measure(ctx, *it.layout);
    }
    else if (it.widget) {
      cw = pref_width(ctx, *it.widget);
    }
    else {
      cw = (l.kind_ == Layout::Kind::Row) ? it.space : 0.0f;
    }
    mx = std::max(mx, cw);
    if (l.kind_ == Layout::Kind::Row) {
      w += cw + (n > 0 ? sp : 0.0f);
    }
    n++;
  }
  switch (l.kind_) {
    case Layout::Kind::Row:
      break;
    case Layout::Kind::Split:
      w = mx * float(std::max(1, n)) + sp * float(std::max(0, n - 1));
      break;
    case Layout::Kind::Grid:
      w = mx * float(l.columns_) + sp * float(l.columns_ - 1);
      break;
    case Layout::Kind::Box:
      w = mx + 2 * st.box_space;
      break;
    case Layout::Kind::Panel:
      w = mx + 2 * st.panel_margin;
      break;
    default:
      w = mx;
      break;
  }
  l.pref_w_ = w;
  return w;
}

void LayoutEngine::set_x(Layout::Item &it, float x, float w)
{
  if (it.layout) {
    it.layout->rect.x = x;
    it.layout->rect.w = w;
  }
  else if (it.widget) {
    it.widget->rect.x = x;
    it.widget->rect.w = w;
  }
}

void LayoutEngine::place_x(Context &ctx, Layout &l, float x, float w)
{
  const Style &st = ctx.style();
  l.rect.x = x;
  l.rect.w = w;
  const float sp = space(l, st);
  const size_t n = l.items_.size();
  if (n == 0) {
    return;
  }
  auto recurse = [&](Layout::Item &it, float cx, float cw) {
    set_x(it, cx, cw);
    if (it.layout) {
      place_x(ctx, *it.layout, cx, cw);
    }
  };
  auto pref = [&](const Layout::Item &it) -> float {
    if (it.layout) {
      return it.layout->pref_w_;
    }
    if (it.widget) {
      return pref_width(ctx, *it.widget);
    }
    return it.space;
  };
  auto is_fixed = [&](const Layout::Item &it) {
    return (it.widget && it.widget->fixed_width > 0.0f) || (!it.layout && !it.widget);
  };

  switch (l.kind_) {
    case Layout::Kind::Column:
      for (Layout::Item &it : l.items_) {
        recurse(it, x, w);
      }
      break;
    case Layout::Kind::Box:
      for (Layout::Item &it : l.items_) {
        recurse(it, x + st.box_space, w - 2 * st.box_space);
      }
      break;
    case Layout::Kind::Panel:
      for (Layout::Item &it : l.items_) {
        if (it.widget == l.header_) {
          recurse(it, x, w);
        }
        else {
          recurse(it, x + st.panel_margin, w - 2 * st.panel_margin);
        }
      }
      break;
    case Layout::Kind::Row: {
      const float avail = w - sp * float(n - 1);
      float fixed = 0.0f, flex = 0.0f;
      for (const Layout::Item &it : l.items_) {
        (is_fixed(it) ? fixed : flex) += pref(it);
      }
      const bool expand = l.alignment_ == LayoutAlign::Expand;
      const float scale = (flex > 0.0f && expand) ? std::max(0.0f, avail - fixed) / flex :
                          (flex > 0.0f ? std::min(1.0f, std::max(0.0f, avail - fixed) / flex) : 1.0f);
      float used = 0.0f;
      std::vector<float> widths(n);
      for (size_t i = 0; i < n; i++) {
        widths[i] = is_fixed(l.items_[i]) ? pref(l.items_[i]) : pref(l.items_[i]) * scale;
        used += widths[i];
      }
      used += sp * float(n - 1);
      float cx = x;
      if (!expand) {
        if (l.alignment_ == LayoutAlign::Center) {
          cx += std::max(0.0f, (w - used) * 0.5f);
        }
        else if (l.alignment_ == LayoutAlign::Right) {
          cx += std::max(0.0f, w - used);
        }
      }
      for (size_t i = 0; i < n; i++) {
        /* Pixel-snap edges so adjacent aligned widgets share borders exactly. */
        const float x0 = std::round(cx);
        float x1 = std::round(cx + widths[i]);
        if (expand && i == n - 1) {
          x1 = std::round(x + w);
        }
        recurse(l.items_[i], x0, x1 - x0);
        cx += widths[i] + sp;
      }
      break;
    }
    case Layout::Kind::Split: {
      const float avail = w - sp * float(n - 1);
      const float first = n > 1 ? avail * l.split_factor_ : avail;
      const float rest = n > 1 ? (avail - first) / float(n - 1) : 0.0f;
      float cx = x;
      for (size_t i = 0; i < n; i++) {
        const float cw = i == 0 ? first : rest;
        const float x0 = std::round(cx);
        const float x1 = i == n - 1 ? std::round(x + w) : std::round(cx + cw);
        recurse(l.items_[i], x0, x1 - x0);
        cx += cw + sp;
      }
      break;
    }
    case Layout::Kind::Grid: {
      const int cols = l.columns_;
      const float cw = (w - sp * float(cols - 1)) / float(cols);
      for (size_t i = 0; i < n; i++) {
        const int c = int(i % size_t(cols));
        const float x0 = std::round(x + c * (cw + sp));
        const float x1 = std::round(x + c * (cw + sp) + cw);
        recurse(l.items_[i], x0, x1 - x0);
      }
      break;
    }
    case Layout::Kind::Splitter: {
      /* items: left pane, bar, right pane. */
      Widget *bar = n == 3 ? l.items_[1].widget : nullptr;
      const float bw = bar ? bar->fixed_width : 0.0f;
      float f = (bar && bar->factor) ? bar->factor.value() : 0.5f;
      f = std::clamp(f, 0.05f, 0.95f);
      const float left = std::round((w - bw) * f);
      recurse(l.items_[0], x, left);
      if (n == 3) {
        recurse(l.items_[1], x + left, bw);
        recurse(l.items_[2], x + left + bw, w - left - bw);
      }
      break;
    }
  }
}

float LayoutEngine::widget_height(Context &ctx, Widget &w)
{
  if (w.type == WidgetType::Paragraph) {
    const Style &st = ctx.style();
    w.lines = break_lines(w.text, w.rect.w - 2 * st.text_margin, ctx.measurer(), st.font);
    const float pad = std::round(0.2f * st.unit);
    w.height = std::max(st.unit, float(w.lines.size()) * st.line_height + 2 * pad);
  }
  return w.height;
}

float LayoutEngine::height(Context &ctx, Layout &l)
{
  const Style &st = ctx.style();
  const float sp = space(l, st);
  auto item_h = [&](Layout::Item &it) -> float {
    if (it.layout) {
      return height(ctx, *it.layout);
    }
    if (it.widget) {
      return widget_height(ctx, *it.widget);
    }
    return l.kind_ == Layout::Kind::Row ? 0.0f : it.space;
  };
  float h = 0.0f;
  switch (l.kind_) {
    case Layout::Kind::Column:
    case Layout::Kind::Box:
    case Layout::Kind::Panel: {
      size_t i = 0;
      const Layout::Item *prev = nullptr;
      for (Layout::Item &it : l.items_) {
        const float ih = item_h(it);
        if (l.kind_ == Layout::Kind::Panel && it.widget == l.header_) {
          h += ih;
          i++;
          continue;
        }
        if (prev && prev->layout && it.layout &&
            (prev->layout->kind_ == Layout::Kind::Panel || it.layout->kind_ == Layout::Kind::Panel))
        {
          h += st.panel_space;
        }
        else if (prev && (prev->layout || prev->widget) && (it.layout || it.widget)) {
          h += sp;
        }
        h += ih;
        prev = &it;
        i++;
      }
      if (l.kind_ == Layout::Kind::Box) {
        h += 2 * st.box_space;
      }
      if (l.kind_ == Layout::Kind::Panel && l.open_) {
        h += st.box_space + st.panel_margin * 0.5f;
      }
      break;
    }
    case Layout::Kind::Row:
    case Layout::Kind::Split:
    case Layout::Kind::Splitter:
      for (Layout::Item &it : l.items_) {
        h = std::max(h, item_h(it));
      }
      break;
    case Layout::Kind::Grid: {
      const size_t cols = size_t(l.columns_);
      float row_h = 0.0f;
      for (size_t i = 0; i < l.items_.size(); i++) {
        row_h = std::max(row_h, item_h(l.items_[i]));
        if ((i + 1) % cols == 0 || i + 1 == l.items_.size()) {
          h += row_h + (h > 0.0f ? st.space_y : 0.0f);
          row_h = 0.0f;
        }
      }
      break;
    }
  }
  l.rect.h = std::round(h);
  return l.rect.h;
}

void LayoutEngine::place_y(Context &ctx, Layout &l, float y)
{
  const Style &st = ctx.style();
  const float sp = space(l, st);
  l.rect.y = std::round(y);
  auto set = [&](Layout::Item &it, float cy, float ch_override = -1.0f) {
    if (it.layout) {
      place_y(ctx, *it.layout, cy);
    }
    else if (it.widget) {
      it.widget->rect.y = std::round(cy);
      it.widget->rect.h = ch_override > 0.0f ? ch_override : it.widget->height;
    }
  };
  auto item_h = [&](const Layout::Item &it) -> float {
    if (it.layout) {
      return it.layout->rect.h;
    }
    if (it.widget) {
      return it.widget->height;
    }
    return l.kind_ == Layout::Kind::Row ? 0.0f : it.space;
  };
  switch (l.kind_) {
    case Layout::Kind::Column:
    case Layout::Kind::Box:
    case Layout::Kind::Panel: {
      float cy = y + (l.kind_ == Layout::Kind::Box ? st.box_space : 0.0f);
      const Layout::Item *prev = nullptr;
      for (Layout::Item &it : l.items_) {
        if (l.kind_ == Layout::Kind::Panel && it.widget == l.header_) {
          set(it, cy);
          cy += item_h(it) + st.box_space;
          continue;
        }
        if (prev && prev->layout && it.layout &&
            (prev->layout->kind_ == Layout::Kind::Panel || it.layout->kind_ == Layout::Kind::Panel))
        {
          cy += st.panel_space;
        }
        else if (prev && (prev->layout || prev->widget) && (it.layout || it.widget)) {
          cy += sp;
        }
        set(it, cy);
        cy += item_h(it);
        prev = &it;
      }
      break;
    }
    case Layout::Kind::Row:
    case Layout::Kind::Split:
      for (Layout::Item &it : l.items_) {
        set(it, y);
      }
      break;
    case Layout::Kind::Splitter:
      for (Layout::Item &it : l.items_) {
        /* The bar spans the full height of the panes. */
        set(it, y, it.widget ? l.rect.h : -1.0f);
      }
      break;
    case Layout::Kind::Grid: {
      const size_t cols = size_t(l.columns_);
      float cy = y;
      for (size_t r = 0; r * cols < l.items_.size(); r++) {
        float row_h = 0.0f;
        for (size_t c = 0; c < cols && r * cols + c < l.items_.size(); c++) {
          Layout::Item &it = l.items_[r * cols + c];
          set(it, cy);
          row_h = std::max(row_h, item_h(it));
        }
        cy += row_h + st.space_y;
      }
      break;
    }
  }
}

void LayoutEngine::apply_align(Layout &l)
{
  if (l.align_ && (l.kind_ == Layout::Kind::Row || l.kind_ == Layout::Kind::Column || l.kind_ == Layout::Kind::Split)) {
    std::vector<Widget *> leaves;
    for (Layout::Item &it : l.items_) {
      if (it.widget) {
        leaves.push_back(it.widget);
      }
    }
    const bool row = l.kind_ != Layout::Kind::Column;
    for (size_t i = 0; i < leaves.size(); i++) {
      uint8_t c = CORNER_ALL;
      if (leaves.size() > 1) {
        if (i == 0) {
          c = row ? CORNER_LEFT : CORNER_TOP;
        }
        else if (i + 1 == leaves.size()) {
          c = row ? CORNER_RIGHT : CORNER_BOTTOM;
        }
        else {
          c = CORNER_NONE;
        }
      }
      leaves[i]->corners = c;
    }
  }
  for (Layout::Item &it : l.items_) {
    if (it.layout) {
      apply_align(*it.layout);
    }
  }
}

float LayoutEngine::resolve(Context &ctx, Layout &root, float x, float y, float w)
{
  apply_align(root);
  measure(ctx, root);
  place_x(ctx, root, x, w);
  const float h = height(ctx, root);
  place_y(ctx, root, y);
  return h;
}

}  // namespace stk::ui
