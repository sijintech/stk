/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Context: frame lifecycle, overlay blocks (popup, tooltip, toasts, modal), hit testing
 * and event handling. Drawing is in draw.cc. */
#include <algorithm>
#include <cmath>
#include <cstdio>

#include "layout_engine.hh"
#include "stk/ui/ui.hh"
#include "stk/ui/utf8.hh"

namespace stk::ui {

static constexpr double INF = std::numeric_limits<double>::infinity();

float Block::scroll() const
{
  return ctx_->scroll_of(id_);
}

Context::Context(ContextConfig config) : config_(std::move(config))
{
  style_ = Style::from_scale(1.0f);
}

Context::~Context() = default;

void Context::set_scale(float dpi_scale, float user_scale)
{
  const float s = std::max(0.25f, dpi_scale * user_scale);
  if (s != style_.scale) {
    style_ = Style::from_scale(s);
    redraw_ = true;
  }
}

std::string_view Context::tr(std::string_view key) const
{
  return config_.catalog ? config_.catalog->tr(key) : key;
}

bool Context::panel_open(WidgetId id, bool default_open) const
{
  const auto it = panels_.find(id);
  return it == panels_.end() ? default_open : it->second;
}

float Context::scroll_of(WidgetId id) const
{
  const auto it = scroll_.find(id);
  return it == scroll_.end() ? 0.0f : it->second;
}

void Context::set_scroll(WidgetId id, float v, float max)
{
  scroll_[id] = std::clamp(v, 0.0f, std::max(0.0f, max));
}

/* -------------------------------------------------------------------- */
/* Frame */

void Context::begin_frame(Vec2 window_size, double now)
{
  window_ = window_size;
  now_ = std::max(now_, now);
  blocks_.clear();
  draw_.clear();
  building_ = true;
  toasts_.erase(std::remove_if(toasts_.begin(), toasts_.end(), [&](const Toast &t) { return t.expires <= now_; }),
                toasts_.end());
}

Layout &LayoutEngine::init_block(Context &ctx, Block &b)
{
  b.layouts_.emplace_back();
  Layout &root = b.layouts_.back();
  root.kind_ = Layout::Kind::Column;
  root.block_ = &b;
  root.scope_ = b.id_;
  root.path_ = b.name_;
  b.root_ = &root;
  (void)ctx;
  return root;
}

Block &Context::new_block(Block::Kind kind, std::string_view name, Rect region)
{
  auto b = std::make_unique<Block>();
  b->ctx_ = this;
  b->kind_ = kind;
  b->name_ = std::string(name);
  b->id_ = utf8::fnv1a(name);
  b->rect_ = region;
  b->frame_ = region;
  LayoutEngine::init_block(*this, *b);
  blocks_.push_back(std::move(b));
  return *blocks_.back();
}

Block &Context::block(std::string_view name, Rect region)
{
  return new_block(Block::Kind::Region, name, region);
}

Layout &Context::modal(std::string_view key, std::string_view title, std::function<void()> on_close, ModalOptions opts)
{
  Block &b = new_block(Block::Kind::Modal, key, {0, 0, window_.x, window_.y});
  b.title_ = std::string(title);
  b.on_close = std::move(on_close);
  b.width_units_ = opts.width_units;
  b.has_pos_ = opts.has_pos;
  b.pos_ = opts.pos;
  return b.layout();
}

static void set_clip(Block &b, const Rect &clip)
{
  for (Widget &w : const_cast<std::deque<Widget> &>(b.widgets())) {
    w.clip = clip;
  }
}

void Context::layout_block(Block &b)
{
  const Style &st = style_;
  Layout &root = b.layout();
  switch (b.kind_) {
    case Block::Kind::Region: {
      const float m = st.panel_margin;
      const Rect r = b.rect_;
      float w = r.w - 2 * m;
      float h = LayoutEngine::resolve(*this, root, r.x + m, r.y + std::round(0.5f * m), w);
      b.content_h_ = h + m;
      if (b.content_h_ > r.h) {
        w -= st.scrollbar;
      }
      float &scroll = scroll_[b.id_];
      scroll = std::clamp(scroll, 0.0f, std::max(0.0f, b.content_h_ - r.h));
      if (scroll != 0.0f || b.content_h_ > r.h) {
        h = LayoutEngine::resolve(*this, root, r.x + m, r.y + std::round(0.5f * m) - std::round(scroll), w);
        b.content_h_ = h + m;
      }
      set_clip(b, r);
      break;
    }
    case Block::Kind::Modal: {
      const float pad = st.panel_margin;
      const float title_h = st.panel_header;
      const float W = st.u(b.width_units_);
      const float h = LayoutEngine::resolve(*this, root, 0, 0, W - 2 * pad);
      Rect f{0, 0, W, title_h + h + 2 * pad};
      if (b.has_pos_) {
        f.x = b.pos_.x;
        f.y = b.pos_.y;
      }
      else {
        f.x = std::round((window_.x - f.w) * 0.5f);
        f.y = std::round((window_.y - f.h) * 0.4f);
      }
      f.x = std::clamp(f.x, 0.0f, std::max(0.0f, window_.x - f.w));
      f.y = std::clamp(f.y, 0.0f, std::max(0.0f, window_.y - f.h));
      b.frame_ = f;
      LayoutEngine::resolve(*this, root, f.x + pad, f.y + title_h + pad, W - 2 * pad);
      b.content_h_ = f.h;
      set_clip(b, f);
      break;
    }
    default:
      break;
  }
}

void Context::end_frame()
{
  for (auto &b : blocks_) {
    layout_block(*b);
  }
  build_overlays();
  /* Interaction state of widgets that no longer exist is dropped (after the overlays are built,
   * since popup items are rebuilt there). */
  if (edit_.id && !find_id(edit_.id)) {
    commit_edit();
  }
  if (drag_.id && !find_id(drag_.id)) {
    drag_ = {};
  }
  if (focus_ && !find_id(focus_)) {
    focus_ = 0;
  }
  if (hover_ && !find_id(hover_)) {
    hover_ = 0;
  }
  /* Draw regions, then modals, popup, tooltip and toasts on top. */
  static constexpr Block::Kind order[] = {Block::Kind::Region, Block::Kind::Modal, Block::Kind::Popup,
                                          Block::Kind::Tooltip, Block::Kind::Toast};
  bool dimmed = false;
  overlay_begin_ = 0;
  for (const Block::Kind k : order) {
    if (k == Block::Kind::Modal) {
      overlay_begin_ = draw_.size();
    }
    for (const auto &b : blocks_) {
      if (b->kind_ != k) {
        continue;
      }
      if (k == Block::Kind::Modal && !dimmed) {
        draw_.rect({0, 0, window_.x, window_.y}, config_.theme.modal_dim);
        dimmed = true;
      }
      b->draw_begin_ = draw_.size();
      draw_block(*b);
      b->draw_end_ = draw_.size();
    }
  }
  building_ = false;
}

void Context::build_overlays()
{
  const Style &st = style_;
  const Theme &th = config_.theme;
  const float m = st.text_margin;

  /* Dropdown / menu popup. */
  if (popup_.owner) {
    const Widget *owner = find_id(popup_.owner);
    if (!owner || owner->block->kind() == Block::Kind::Popup) {
      popup_ = {};
    }
    else {
      popup_.anchor = owner->rect;
      popup_.count = int(owner->items.size());
      Block &b = new_block(Block::Kind::Popup, "popup", {0, 0, window_.x, window_.y});
      Layout &root = b.layout();
      root.align_ = true;
      float mw = 0.0f;
      for (const std::string &s : owner->items) {
        mw = std::max(mw, LayoutEngine::text_w(*this, s));
      }
      const float strip = popup_.colormap ? std::round(4.0f * st.unit) : 0.0f;
      const float W = std::round(std::max(owner->rect.w, mw + 2 * m + strip + (strip > 0 ? m : 0.0f) + st.unit));
      for (int i = 0; i < popup_.count; i++) {
        Widget &it = root.add_widget(WidgetType::MenuItem, std::to_string(i));
        it.id = utf8::hash_combine(popup_.owner, uint64_t(i) + 1);
        it.text = owner->items[size_t(i)];
        it.menu_index = i;
        if (popup_.menu && size_t(i) < owner->menu.size()) {
          it.enabled = owner->menu[size_t(i)].enabled;
        }
        if (popup_.colormap) {
          it.colormaps = owner->colormaps;
        }
      }
      const float pad = st.box_space;
      const float content = float(popup_.count) * st.unit;
      const float max_h = std::max(st.unit * 3, window_.y - 2 * pad);
      Rect f{owner->rect.x, owner->rect.y1(), W, std::min(content + 2 * pad, max_h)};
      if (f.y1() > window_.y && owner->rect.y - f.h >= 0.0f) {
        f.y = owner->rect.y - f.h;
      }
      f.y = std::clamp(f.y, 0.0f, std::max(0.0f, window_.y - f.h));
      f.x = std::clamp(f.x, 0.0f, std::max(0.0f, window_.x - f.w));
      b.frame_ = f;
      const WidgetId sid = utf8::hash_combine(popup_.owner, 0xC0FFEEull);
      const float view = f.h - 2 * pad;
      float &scroll = scroll_[sid];
      if (popup_.highlight >= 0) {
        const float hy = float(popup_.highlight) * st.unit;
        if (hy < scroll) {
          scroll = hy;
        }
        else if (hy + st.unit > scroll + view) {
          scroll = hy + st.unit - view;
        }
      }
      scroll = std::clamp(scroll, 0.0f, std::max(0.0f, content - view));
      b.id_ = sid;
      LayoutEngine::resolve(*this, root, f.x, f.y + pad - std::round(scroll), f.w);
      b.content_h_ = content;
      set_clip(b, f.inset(0, pad));
    }
  }

  /* Tooltip. */
  tooltip_shown_ = 0;
  WidgetId tip_id = tooltip_forced_;
  if (!tip_id && hover_ && drag_.kind == DragState::Kind::None && !popup_.owner &&
      now_ - hover_since_ >= config_.tooltip_delay)
  {
    tip_id = hover_;
  }
  if (tip_id) {
    const Widget *w = find_id(tip_id);
    if (w && !w->tooltip.empty()) {
      Block &b = new_block(Block::Kind::Tooltip, "tooltip", {0, 0, window_.x, window_.y});
      Widget &p = b.layout().paragraph(w->tooltip);
      const float W = std::round(std::min(LayoutEngine::text_w(*this, w->tooltip) + 2 * m + 2, std::round(22.0f * st.unit)));
      const float h = LayoutEngine::resolve(*this, b.layout(), 0, 0, W);
      Rect f{w->rect.x, w->rect.y1() + std::round(0.25f * st.unit), W, h};
      if (f.y1() > window_.y) {
        f.y = w->rect.y - f.h - std::round(0.25f * st.unit);
      }
      f.x = std::clamp(f.x, 0.0f, std::max(0.0f, window_.x - f.w));
      f.y = std::clamp(f.y, 0.0f, std::max(0.0f, window_.y - f.h));
      b.frame_ = f;
      LayoutEngine::resolve(*this, b.layout(), f.x, f.y, W);
      set_clip(b, f);
      (void)p;
      tooltip_shown_ = tip_id;
    }
  }

  /* Toasts: newest at the bottom right. */
  float y = window_.y - st.unit;
  for (auto it = toasts_.rbegin(); it != toasts_.rend(); ++it) {
    Block &b = new_block(Block::Kind::Toast, "toast/" + std::to_string(it->serial), {0, 0, window_.x, window_.y});
    b.toast_kind_ = it->kind;
    const float stripe = std::round(0.25f * st.unit);
    const float W = std::round(std::min(LayoutEngine::text_w(*this, it->text) + 2 * m + stripe + 2, std::round(22.0f * st.unit)));
    b.layout().paragraph(it->text);
    const float h = LayoutEngine::resolve(*this, b.layout(), 0, 0, W - stripe);
    const Rect f{window_.x - W - st.unit, y - h, W, h};
    b.frame_ = f;
    LayoutEngine::resolve(*this, b.layout(), f.x + stripe, f.y, W - stripe);
    set_clip(b, f);
    y -= h + st.space_x;
  }
  (void)th;
}

/* -------------------------------------------------------------------- */
/* Queries */

const Widget *Context::find_id(WidgetId id) const
{
  if (!id) {
    return nullptr;
  }
  for (const auto &b : blocks_) {
    for (const Widget &w : b->widgets()) {
      if (w.id == id) {
        return &w;
      }
    }
  }
  return nullptr;
}

const Widget *Context::find(std::string_view key) const
{
  for (const auto &b : blocks_) {
    for (const Widget &w : b->widgets()) {
      if (w.key == key) {
        return &w;
      }
    }
  }
  const std::string suffix = "/" + std::string(key);
  for (const auto &b : blocks_) {
    for (const Widget &w : b->widgets()) {
      if (w.key.size() >= suffix.size() && w.key.compare(w.key.size() - suffix.size(), suffix.size(), suffix) == 0) {
        return &w;
      }
    }
  }
  return nullptr;
}

static int kind_rank(Block::Kind k)
{
  switch (k) {
    case Block::Kind::Region: return 0;
    case Block::Kind::Modal: return 1;
    case Block::Kind::Popup: return 2;
    case Block::Kind::Toast: return 3;
    case Block::Kind::Tooltip: return -1;
  }
  return -1;
}

const Widget *Context::hit(Vec2 p, Block **r_block) const
{
  if (r_block) {
    *r_block = nullptr;
  }
  bool modal = false;
  for (const auto &b : blocks_) {
    modal |= b->kind() == Block::Kind::Modal;
  }
  for (int rank = 3; rank >= 0; rank--) {
    if (rank == 0 && modal) {
      return nullptr; /* Focus trap: nothing below a modal dialog reacts. */
    }
    for (auto it = blocks_.rbegin(); it != blocks_.rend(); ++it) {
      const Block &b = **it;
      if (kind_rank(b.kind()) != rank) {
        continue;
      }
      const Rect &area = b.kind() == Block::Kind::Region ? b.rect() : b.frame();
      if (!area.contains(p)) {
        continue;
      }
      if (r_block) {
        *r_block = const_cast<Block *>(&b);
      }
      const auto &ws = b.widgets();
      for (auto wi = ws.rbegin(); wi != ws.rend(); ++wi) {
        if (wi->rect.contains(p) && wi->clip.contains(p)) {
          return &*wi;
        }
      }
      return nullptr;
    }
  }
  return nullptr;
}

bool Context::in_modal_scope(const Widget &w) const
{
  const Block *top = nullptr;
  for (const auto &b : blocks_) {
    if (b->kind() == Block::Kind::Modal) {
      top = b.get();
    }
  }
  return !top || w.block == top;
}

/* -------------------------------------------------------------------- */
/* Services */

void Context::toast(std::string text, ToastKind kind, double seconds)
{
  toasts_.push_back({std::move(text), kind, now_ + seconds, ++toast_serial_});
  redraw_ = true;
}

bool Context::open_popup(std::string_view widget_key)
{
  const Widget *w = find(widget_key);
  if (!w || (w->type != WidgetType::Dropdown && w->type != WidgetType::ColormapDropdown &&
             w->type != WidgetType::MenuButton))
  {
    return false;
  }
  if (popup_.owner != w->id) {
    open_popup_for(*w);
  }
  return true;
}

void Context::close_popup()
{
  if (popup_.owner) {
    popup_ = {};
    redraw_ = true;
  }
}

bool Context::force_tooltip(std::string_view widget_key)
{
  const Widget *w = find(widget_key);
  tooltip_forced_ = w ? w->id : 0;
  redraw_ = true;
  return w != nullptr;
}

void Context::open_popup_for(const Widget &w)
{
  if (popup_.owner == w.id) {
    close_popup();
    return;
  }
  popup_ = {};
  popup_.owner = w.id;
  popup_.owner_key = w.key;
  popup_.count = int(w.items.size());
  popup_.anchor = w.rect;
  popup_.colormap = w.type == WidgetType::ColormapDropdown;
  popup_.menu = w.type == WidgetType::MenuButton;
  popup_.highlight = (w.index && !popup_.menu) ? w.index.value() : -1;
  focus_ = w.id;
  redraw_ = true;
}

void Context::popup_select(int index)
{
  const Widget *owner = find_id(popup_.owner);
  popup_ = {};
  redraw_ = true;
  if (!owner || index < 0 || size_t(index) >= owner->items.size()) {
    return;
  }
  if (owner->type == WidgetType::MenuButton) {
    const MenuEntry &e = owner->menu[size_t(index)];
    if (e.enabled && e.action) {
      e.action();
    }
  }
  else {
    owner->index.assign(index);
  }
}

double Context::next_wakeup() const
{
  double t = INF;
  if (hover_ && !tooltip_shown_ && drag_.kind == DragState::Kind::None && !popup_.owner) {
    const Widget *w = find_id(hover_);
    if (w && !w->tooltip.empty()) {
      t = hover_since_ + config_.tooltip_delay;
    }
  }
  for (const Toast &toast : toasts_) {
    t = std::min(t, toast.expires);
  }
  return t;
}

/* -------------------------------------------------------------------- */
/* Text editing */

void Context::begin_edit(const Widget &w, bool select_all, std::string initial, bool use_initial)
{
  if (edit_.id == w.id) {
    return;
  }
  if (edit_.id) {
    commit_edit();
  }
  edit_ = {};
  edit_.id = w.id;
  edit_.numeric = w.type == WidgetType::Number || w.type == WidgetType::Slider;
  edit_.password = !edit_.numeric && w.text_opts.password;
  std::string text;
  if (use_initial) {
    text = std::move(initial);
  }
  else if (edit_.numeric) {
    text = format_number_edit(w.number.value(), w.props);
  }
  else {
    text = w.string.value();
  }
  edit_.edit.set_text(std::move(text), select_all);
  edit_.edit.set_max_length(edit_.numeric ? 0 : w.text_opts.max_length);
  if (edit_.numeric) {
    edit_.commit = [num = w.number, props = w.props](const std::string &s) {
      const std::optional<double> v = parse_number(s, props);
      if (!v) {
        return false;
      }
      num.assign(clamp_number(*v, props));
      return true;
    };
  }
  else {
    edit_.commit = [str = w.string](const std::string &s) {
      str.assign(s);
      return true;
    };
  }
  focus_ = w.id;
  redraw_ = true;
}

void Context::commit_edit()
{
  if (!edit_.id) {
    return;
  }
  EditState old = std::move(edit_);
  edit_ = {};
  redraw_ = true;
  if (old.commit && !old.commit(old.edit.text())) {
    toast(config_.catalog ? config_.catalog->format("ui.error.invalid_number", {{"text", old.edit.text()}}) :
                            "Invalid number: " + old.edit.text(),
          ToastKind::Warning);
  }
}

void Context::cancel_edit()
{
  if (edit_.id) {
    edit_ = {};
    redraw_ = true;
  }
}

void Context::edit_click(const Widget &w, Vec2 p, bool extend, bool dbl)
{
  const FontStyle &font = w.mono ? style_.mono : style_.font;
  const float local = p.x - (w.rect.x + style_.text_margin) + edit_.scroll_x;
  const size_t idx = edit_.password ?
                         unmask_offset(edit_.edit.text(),
                                       measurer().index_at_x(mask_text(edit_.edit.text()), local, font)) :
                         measurer().index_at_x(edit_.edit.text(), local, font);
  if (dbl) {
    edit_.edit.select_word_at(idx);
  }
  else {
    edit_.edit.set_cursor(idx, extend);
  }
  redraw_ = true;
}

bool Context::edit_key(const Event &e)
{
  TextEdit &ed = edit_.edit;
  const bool prim = (e.mods & primary_mod()) != 0;
  const bool shift = (e.mods & MOD_SHIFT) != 0;
  /* Word navigation: Ctrl (Linux/Windows) or Alt/Option (macOS). */
  const bool word = config_.mac_shortcuts ? (e.mods & MOD_ALT) != 0 : prim;
  if (ed.composing()) {
    return true; /* The input method owns navigation keys while composing. */
  }
  switch (e.key) {
    case Key::Left:
      ed.move_left(word, shift);
      break;
    case Key::Right:
      ed.move_right(word, shift);
      break;
    case Key::Home:
      ed.home(shift);
      break;
    case Key::End:
      ed.end(shift);
      break;
    case Key::Backspace:
      ed.backspace(word);
      break;
    case Key::Delete:
      ed.delete_forward(word);
      break;
    case Key::Enter:
      commit_edit();
      return true;
    case Key::Escape:
      cancel_edit();
      return true;
    case Key::Tab: {
      commit_edit();
      focus_next(shift);
      const Widget *n = find_id(focus_);
      if (n && (n->type == WidgetType::TextField || n->type == WidgetType::Number || n->type == WidgetType::Slider)) {
        begin_edit(*n, true);
      }
      return true;
    }
    case Key::A:
      if (prim) {
        ed.select_all();
      }
      break;
    case Key::C:
      if (prim && config_.clipboard && ed.has_selection() && !edit_.password) {
        config_.clipboard->set(ed.selected_text());
      }
      break;
    case Key::X:
      if (prim && config_.clipboard && ed.has_selection() && !edit_.password) {
        config_.clipboard->set(ed.cut());
      }
      break;
    case Key::V:
      if (prim && config_.clipboard) {
        ed.paste(config_.clipboard->get());
      }
      break;
    case Key::Z:
      if (prim) {
        shift ? ed.redo() : ed.undo();
      }
      break;
    case Key::Y:
      if (prim) {
        ed.redo();
      }
      break;
    default:
      break;
  }
  redraw_ = true;
  return true;
}

/* -------------------------------------------------------------------- */
/* Focus */

void Context::focus_next(bool backwards)
{
  std::vector<const Widget *> order;
  bool modal = false;
  for (const auto &b : blocks_) {
    modal |= b->kind() == Block::Kind::Modal;
  }
  for (const auto &b : blocks_) {
    const bool eligible = modal ? b->kind() == Block::Kind::Modal : b->kind() == Block::Kind::Region;
    if (!eligible) {
      continue;
    }
    for (const Widget &w : b->widgets()) {
      if (w.focusable() && (!modal || in_modal_scope(w))) {
        order.push_back(&w);
      }
    }
  }
  if (order.empty()) {
    focus_ = 0;
    return;
  }
  int cur = -1;
  for (size_t i = 0; i < order.size(); i++) {
    if (order[i]->id == focus_) {
      cur = int(i);
    }
  }
  const int n = int(order.size());
  int next;
  if (cur < 0) {
    next = backwards ? n - 1 : 0;
  }
  else {
    next = ((cur + (backwards ? -1 : 1)) % n + n) % n;
  }
  focus_ = order[size_t(next)]->id;
  redraw_ = true;
}

bool Context::activate_focused(const Event &e)
{
  const Widget *w = find_id(focus_);
  if (!w || !w->enabled) {
    return false;
  }
  const bool confirm = e.key == Key::Enter || e.key == Key::Space;
  switch (w->type) {
    case WidgetType::Button:
    case WidgetType::MenuItem:
      if (confirm && w->on_click) {
        w->on_click();
        redraw_ = true;
        return true;
      }
      return false;
    case WidgetType::Checkbox:
      if (confirm) {
        w->boolean.assign(!w->boolean.value());
        redraw_ = true;
        return true;
      }
      return false;
    case WidgetType::PanelHeader:
      if (confirm) {
        panels_[w->id] = !panel_open(w->id, true);
        redraw_ = true;
        return true;
      }
      return false;
    case WidgetType::Dropdown:
    case WidgetType::ColormapDropdown:
    case WidgetType::MenuButton:
      if (confirm || e.key == Key::Down) {
        open_popup_for(*w);
        return true;
      }
      return false;
    case WidgetType::TextField:
      if (e.key == Key::Enter) {
        begin_edit(*w, true);
        return true;
      }
      return false;
    case WidgetType::Number:
    case WidgetType::Slider:
      if (e.key == Key::Enter) {
        begin_edit(*w, true);
        return true;
      }
      if (e.key == Key::Left || e.key == Key::Right) {
        const double step = w->props.integer ? std::max(1.0, w->props.step) : w->props.step;
        w->number.assign(clamp_number(w->number.value() + (e.key == Key::Left ? -step : step), w->props));
        redraw_ = true;
        return true;
      }
      return false;
    case WidgetType::Tabs:
      if ((e.key == Key::Left || e.key == Key::Right) && !w->items.empty()) {
        const int n = int(w->items.size());
        const int cur = w->index.value();
        w->index.assign(std::clamp(cur + (e.key == Key::Left ? -1 : 1), 0, n - 1));
        redraw_ = true;
        return true;
      }
      return false;
    case WidgetType::VirtualList:
    case WidgetType::Table: {
      const int count = w->list ? w->list->count : (w->table ? w->table->rows : 0);
      Binding<int> sel = w->list ? w->list->selected : w->table->selected;
      if (count <= 0) {
        return false;
      }
      const float row_h = list_row_height(*w);
      const float view_h = w->rect.h - (w->table ? row_h : 0.0f) - 2 * style_.pixel;
      const int page = std::max(1, int(view_h / row_h) - 1);
      /* Tables move through the view order (sorted), lists through the model order. */
      const std::vector<int> *perm = w->table ? &table_perm(*w) : nullptr;
      int view_row = -1;
      if (sel) {
        const int s = sel.value();
        if (perm) {
          for (size_t i = 0; i < perm->size(); i++) {
            if ((*perm)[i] == s) {
              view_row = int(i);
            }
          }
        }
        else {
          view_row = s;
        }
      }
      int next = view_row;
      switch (e.key) {
        case Key::Up: next = view_row - 1; break;
        case Key::Down: next = view_row + 1; break;
        case Key::PageUp: next = view_row - page; break;
        case Key::PageDown: next = view_row + page; break;
        case Key::Home: next = 0; break;
        case Key::End: next = count - 1; break;
        case Key::Enter:
          if (w->list && w->list->on_activate && view_row >= 0) {
            w->list->on_activate(view_row);
            return true;
          }
          return false;
        default: return false;
      }
      next = std::clamp(next, 0, count - 1);
      sel.assign(perm ? (*perm)[size_t(next)] : next);
      /* Scroll the new row into view. */
      const float y = float(next) * row_h;
      float s = scroll_of(w->id);
      if (y < s) {
        s = y;
      }
      else if (y + row_h > s + view_h) {
        s = y + row_h - view_h;
      }
      set_scroll(w->id, s, max_scroll(*w));
      redraw_ = true;
      return true;
    }
    case WidgetType::LogView: {
      const float line_h = list_row_height(*w);
      float s = scroll_of(w->id);
      const float page = w->rect.h * 0.9f;
      switch (e.key) {
        case Key::Up: s -= line_h; break;
        case Key::Down: s += line_h; break;
        case Key::PageUp: s -= page; break;
        case Key::PageDown: s += page; break;
        case Key::Home: s = 0; break;
        case Key::End: s = max_scroll(*w); break;
        default: return false;
      }
      set_scroll(w->id, s, max_scroll(*w));
      follow_[w->id] = scroll_of(w->id) >= max_scroll(*w) - 0.5f;
      redraw_ = true;
      return true;
    }
    default:
      return false;
  }
}

/* -------------------------------------------------------------------- */
/* Events */

void Context::set_hover(const Widget *w, Vec2 p)
{
  const WidgetId id = w ? w->id : 0;
  int zone = 0;
  if (w && (w->type == WidgetType::Number)) {
    const float handle = std::min(w->rect.w / 3.0f, w->rect.h * 0.7f);
    zone = p.x < w->rect.x + handle ? -1 : (p.x >= w->rect.x1() - handle ? 1 : 0);
  }
  else if (w && (w->type == WidgetType::VirtualList || w->type == WidgetType::Table)) {
    const float row_h = list_row_height(*w);
    const float body_y = w->rect.y + style_.pixel + (w->table ? row_h : 0.0f);
    zone = p.y < body_y ? -1 : int((p.y - body_y + scroll_of(w->id)) / row_h);
  }
  else if (w && w->type == WidgetType::Tabs && !w->items.empty()) {
    zone = int((p.x - w->rect.x) / (w->rect.w / float(w->items.size())));
  }
  if (id != hover_) {
    hover_ = id;
    hover_since_ = now_;
    tooltip_forced_ = 0;
    redraw_ = true;
  }
  if (zone != hover_zone_) {
    hover_zone_ = zone;
    redraw_ = true;
  }
  if (w && w->type == WidgetType::MenuItem && w->menu_index != popup_.highlight) {
    popup_.highlight = w->menu_index;
    redraw_ = true;
  }
}

float Context::list_row_height(const Widget &w) const
{
  if (w.type == WidgetType::LogView) {
    return std::round(style_.mono.size_px * 1.4f);
  }
  return style_.unit;
}

float Context::max_scroll(const Widget &w) const
{
  const float px = style_.pixel;
  const float row_h = list_row_height(w);
  float content = 0.0f, view = w.rect.h - 2 * px;
  if (w.list) {
    content = float(w.list->count) * row_h;
  }
  else if (w.table) {
    content = float(w.table->rows) * row_h;
    view -= row_h;
  }
  else if (w.log) {
    content = float(w.log->line_count()) * row_h + 2 * std::round(0.2f * style_.unit);
  }
  return std::max(0.0f, content - view);
}

Rect Context::scrollbar_rect(const Widget &w, float content, float view, float scroll, Rect area) const
{
  (void)w;
  if (content <= view || view <= 0.0f) {
    return {};
  }
  const float sb = style_.scrollbar;
  const Rect track{area.x1() - sb - style_.pixel, area.y + style_.pixel, sb, area.h - 2 * style_.pixel};
  const float thumb_h = std::max(style_.unit, track.h * view / content);
  const float t = scroll / (content - view);
  return {track.x, std::round(track.y + t * (track.h - thumb_h)), track.w, std::round(thumb_h)};
}

Context::TableState &Context::table_state(const Widget &w)
{
  TableState &s = tables_[w.id];
  if (s.widths_u.size() != w.table->columns.size()) {
    s.widths_u.clear();
    for (const TableColumn &c : w.table->columns) {
      s.widths_u.push_back(c.width);
    }
  }
  return s;
}

const std::vector<int> &Context::table_perm(const Widget &w)
{
  TableState &s = table_state(w);
  const TableSpec &t = *w.table;
  if (s.perm_version != t.data_version || s.perm_rows != t.rows || s.perm_col != s.sort_col ||
      s.perm_asc != s.ascending)
  {
    s.perm.resize(size_t(std::max(0, t.rows)));
    for (int i = 0; i < t.rows; i++) {
      s.perm[size_t(i)] = i;
    }
    if (s.sort_col >= 0 && size_t(s.sort_col) < t.columns.size() && t.cell) {
      const int c = s.sort_col;
      if (t.columns[size_t(c)].numeric) {
        std::vector<double> keys(size_t(t.rows));
        for (int i = 0; i < t.rows; i++) {
          NumberProps p;
          const std::optional<double> v = parse_number(t.cell(i, c), p);
          keys[size_t(i)] = v ? *v : std::numeric_limits<double>::infinity();
        }
        std::stable_sort(s.perm.begin(), s.perm.end(), [&](int a, int b) {
          return s.ascending ? keys[size_t(a)] < keys[size_t(b)] : keys[size_t(a)] > keys[size_t(b)];
        });
      }
      else {
        std::vector<std::string> keys(size_t(t.rows));
        for (int i = 0; i < t.rows; i++) {
          keys[size_t(i)] = t.cell(i, c);
        }
        std::stable_sort(s.perm.begin(), s.perm.end(), [&](int a, int b) {
          return s.ascending ? keys[size_t(a)] < keys[size_t(b)] : keys[size_t(a)] > keys[size_t(b)];
        });
      }
    }
    s.perm_version = t.data_version;
    s.perm_rows = t.rows;
    s.perm_col = s.sort_col;
    s.perm_asc = s.ascending;
  }
  return s.perm;
}

float Context::table_col_px(const Widget &w, int c)
{
  TableState &s = table_state(w);
  const int n = int(s.widths_u.size());
  if (c == n - 1) {
    float used = 0.0f;
    for (int i = 0; i < n - 1; i++) {
      used += std::round(s.widths_u[size_t(i)] * style_.unit);
    }
    const float avail = w.rect.w - 2 * style_.pixel - style_.scrollbar - used;
    return std::max(std::round(s.widths_u[size_t(c)] * style_.unit), avail);
  }
  return std::round(s.widths_u[size_t(c)] * style_.unit);
}

int Context::table_header_col(const Widget &w, Vec2 p)
{
  const float row_h = list_row_height(w);
  if (p.y >= w.rect.y + style_.pixel + row_h) {
    return -1;
  }
  float x = w.rect.x + style_.pixel;
  for (int c = 0; c < int(w.table->columns.size()); c++) {
    const float cw = table_col_px(w, c);
    if (p.x >= x && p.x < x + cw) {
      return c;
    }
    x += cw;
  }
  return -1;
}

int Context::table_resize_hit(const Widget &w, Vec2 p)
{
  const float row_h = list_row_height(w);
  if (p.y >= w.rect.y + style_.pixel + row_h) {
    return -1;
  }
  const float tol = std::max(3.0f, std::round(0.2f * style_.unit));
  float x = w.rect.x + style_.pixel;
  for (int c = 0; c + 1 < int(w.table->columns.size()); c++) {
    x += table_col_px(w, c);
    if (std::fabs(p.x - x) <= tol) {
      return c;
    }
  }
  return -1;
}

Rect Context::image_display_rect(const Widget &w)
{
  const Rect area = w.rect.inset(style_.pixel, style_.pixel);
  const ImageState &s = images_[w.id];
  const float iw = float(std::max(1, w.image.width)), ih = float(std::max(1, w.image.height));
  const float scale = s.zoom > 0.0f ? s.zoom : std::min(area.w / iw, area.h / ih);
  const float dw = iw * scale, dh = ih * scale;
  return {std::round(area.cx() - dw * 0.5f + s.pan.x), std::round(area.cy() - dh * 0.5f + s.pan.y), std::round(dw),
          std::round(dh)};
}

EventResult Context::handle_event(const Event &e)
{
  if (e.time > 0.0) {
    now_ = std::max(now_, e.time);
  }
  EventResult r;
  switch (e.type) {
    case EventType::MouseMove:
      r = mouse_move(e);
      break;
    case EventType::MouseDown:
      r = mouse_down(e);
      break;
    case EventType::MouseUp:
      r = mouse_up(e);
      break;
    case EventType::Wheel:
      r = wheel(e);
      break;
    case EventType::KeyDown:
      r = key_down(e);
      break;
    case EventType::KeyUp:
      break;
    case EventType::TextInput:
    case EventType::ImeCommit:
    case EventType::ImePreedit: {
      if (!edit_.id && e.type != EventType::ImeCommit && !e.text.empty()) {
        /* Typing into a focused field starts editing it. */
        const Widget *w = find_id(focus_);
        if (w && w->enabled && w->type == WidgetType::TextField) {
          begin_edit(*w, false); /* continue at the end of the current text */
        }
        else if (w && w->enabled && (w->type == WidgetType::Number || w->type == WidgetType::Slider)) {
          begin_edit(*w, false, std::string(), true); /* typing replaces the number */
        }
      }
      if (edit_.id) {
        if (e.type == EventType::ImePreedit) {
          edit_.edit.set_preedit(e.text, e.ime_cursor < 0 ? e.text.size() : size_t(e.ime_cursor));
        }
        else if (e.type == EventType::ImeCommit) {
          edit_.edit.commit(e.text);
        }
        else {
          std::string clean;
          for (const char c : e.text) {
            if ((unsigned char)c >= 0x20 && c != 0x7f) {
              clean += c;
            }
          }
          edit_.edit.insert(clean);
        }
        r = {true, true};
      }
      break;
    }
    case EventType::FocusLost:
      drag_ = {};
      hover_ = 0;
      r.redraw = true;
      break;
    case EventType::Tick: {
      if (next_wakeup() <= now_) {
        r.redraw = true;
      }
      break;
    }
  }
  if (r.redraw) {
    redraw_ = true;
  }
  return r;
}

EventResult Context::mouse_move(const Event &e)
{
  mouse_ = e.pos;
  if (drag_.kind != DragState::Kind::None) {
    const Widget *w = find_id(drag_.id);
    if (!w) {
      drag_ = {};
      return {true, true};
    }
    const Vec2 d{e.pos.x - drag_.start.x, e.pos.y - drag_.start.y};
    const float threshold = std::max(3.0f, 3.0f * style_.scale);
    if (!drag_.moved && std::fabs(d.x) < threshold && std::fabs(d.y) < threshold) {
      return {true, false};
    }
    drag_.moved = true;
    switch (drag_.kind) {
      case DragState::Kind::Number:
      case DragState::Kind::Slider:
        drag_number(*w, e);
        break;
      case DragState::Kind::TextSelect:
        edit_click(*w, e.pos, true, false);
        break;
      case DragState::Kind::Scroll: {
        const float view = w->rect.h - 2 * style_.pixel - (w->table ? list_row_height(*w) : 0.0f);
        const float ms = max_scroll(*w);
        const float content = ms + view;
        const float thumb_h = std::max(style_.unit, (view) * view / std::max(content, 1.0f));
        const float track = view - thumb_h;
        if (track > 0) {
          set_scroll(w->id, drag_.start_scroll + d.y * ms / track, ms);
          if (w->log) {
            follow_[w->id] = scroll_of(w->id) >= ms - 0.5f;
          }
        }
        break;
      }
      case DragState::Kind::ColumnResize: {
        TableState &s = table_state(*w);
        s.widths_u[size_t(drag_.column)] = std::max(1.5f, float(drag_.start_value) + d.x / style_.unit);
        break;
      }
      case DragState::Kind::Splitter: {
        /* The factor is relative to the parent splitter's width minus the bar. */
        const Layout *parent = nullptr;
        for (const Layout &l : LayoutEngine::layouts(*w->block)) {
          if (l.kind() == Layout::Kind::Splitter) {
            for (const auto &it : LayoutEngine::items(l)) {
              if (it.widget == w) {
                parent = &l;
              }
            }
          }
        }
        if (parent && w->factor) {
          const float avail = parent->rect.w - w->rect.w;
          const float f = float(drag_.start_value) + d.x / std::max(1.0f, avail);
          w->factor.assign(std::clamp(f, 0.05f, 0.95f));
        }
        break;
      }
      case DragState::Kind::ImagePan: {
        ImageState &s = images_[w->id];
        s.pan.x += e.pos.x - drag_.last.x;
        s.pan.y += e.pos.y - drag_.last.y;
        break;
      }
      default:
        break;
    }
    drag_.last = e.pos;
    return {true, true};
  }
  const Widget *w = hit(e.pos);
  const bool before = redraw_;
  redraw_ = false;
  set_hover(w, e.pos);
  const bool changed = redraw_;
  redraw_ = before || changed;
  return {w != nullptr, changed};
}

void Context::drag_number(const Widget &w, const Event &e)
{
  const NumberProps &p = w.props;
  const float dx = e.pos.x - drag_.start.x;
  const double fine = (e.mods & MOD_SHIFT) ? 0.1 : 1.0;
  double v;
  if (drag_.kind == DragState::Kind::Slider) {
    double lo = p.soft_lo(), hi = p.soft_hi();
    if (!std::isfinite(lo) || !std::isfinite(hi)) {
      lo = drag_.start_value - 100 * p.step;
      hi = drag_.start_value + 100 * p.step;
    }
    v = drag_.start_value + double(dx) / std::max(1.0f, w.rect.w) * (hi - lo) * fine;
  }
  else {
    /* One step per half widget unit, like Blender's number drag at default sensitivity. */
    const double step = p.integer ? std::max(1.0, p.step) : p.step;
    v = drag_.start_value + double(dx) / (0.5 * style_.unit) * step * fine;
  }
  if (e.mods & primary_mod()) {
    const double step = p.integer ? std::max(1.0, p.step) : p.step;
    v = std::round(v / step) * step;
  }
  /* Dragging stays inside the soft range; typed values only obey the hard limits. */
  if (std::isfinite(p.soft_lo()) && !std::isnan(p.soft_min)) {
    v = std::max(v, p.soft_min);
  }
  if (std::isfinite(p.soft_hi()) && !std::isnan(p.soft_max)) {
    v = std::min(v, p.soft_max);
  }
  w.number.assign(clamp_number(v, p));
}

EventResult Context::mouse_down(const Event &e)
{
  mouse_ = e.pos;
  Block *blk = nullptr;
  const Widget *w = hit(e.pos, &blk);

  if (popup_.owner && !(w && w->type == WidgetType::MenuItem)) {
    const bool on_owner = w && w->id == popup_.owner;
    close_popup();
    (void)on_owner;
    return {true, true};
  }
  if (blk && blk->kind() == Block::Kind::Toast) {
    const std::string serial = blk->name().substr(6);
    toasts_.erase(std::remove_if(toasts_.begin(), toasts_.end(),
                                 [&](const Toast &t) { return std::to_string(t.serial) == serial; }),
                  toasts_.end());
    return {true, true};
  }
  if (edit_.id && (!w || w->id != edit_.id)) {
    commit_edit();
  }
  tooltip_forced_ = 0;
  if (!w) {
    if (!blk) {
      focus_ = 0;
    }
    return {blk != nullptr, true};
  }
  if (!w->enabled) {
    return {true, false};
  }
  if (e.button != MouseButton::Left) {
    return {true, false};
  }
  const bool dbl = last_click_id_ == w->id && now_ - last_click_time_ <= config_.double_click_time &&
                   std::fabs(e.pos.x - last_click_pos_.x) < 4 * style_.scale &&
                   std::fabs(e.pos.y - last_click_pos_.y) < 4 * style_.scale;
  last_click_id_ = dbl ? 0 : w->id;
  last_click_time_ = now_;
  last_click_pos_ = e.pos;
  if (w->focusable() && w->type != WidgetType::MenuItem) {
    focus_ = w->id;
  }
  drag_ = {};
  drag_.id = w->id;
  drag_.kind = DragState::Kind::Press;
  drag_.start = drag_.last = e.pos;
  const bool shift = (e.mods & MOD_SHIFT) != 0;
  const float px = style_.pixel;

  switch (w->type) {
    case WidgetType::TextField:
      begin_edit(*w, false);
      edit_click(*w, e.pos, shift, dbl);
      drag_.kind = DragState::Kind::TextSelect;
      break;
    case WidgetType::Number:
    case WidgetType::Slider:
      if (edit_.id == w->id) {
        edit_click(*w, e.pos, shift, dbl);
        drag_.kind = DragState::Kind::TextSelect;
      }
      else {
        drag_.kind = w->type == WidgetType::Slider ? DragState::Kind::Slider : DragState::Kind::Number;
        drag_.start_value = w->number.value();
        const float handle = std::min(w->rect.w / 3.0f, w->rect.h * 0.7f);
        drag_.zone = w->type == WidgetType::Slider ? 0 :
                     (e.pos.x < w->rect.x + handle ? -1 : (e.pos.x >= w->rect.x1() - handle ? 1 : 0));
      }
      break;
    case WidgetType::Dropdown:
    case WidgetType::ColormapDropdown:
    case WidgetType::MenuButton:
      open_popup_for(*w);
      drag_ = {};
      break;
    case WidgetType::Tabs:
      if (!w->items.empty()) {
        const int i = std::clamp(int((e.pos.x - w->rect.x) / (w->rect.w / float(w->items.size()))), 0,
                                 int(w->items.size()) - 1);
        w->index.assign(i);
      }
      drag_ = {};
      break;
    case WidgetType::VirtualList:
    case WidgetType::Table:
    case WidgetType::LogView: {
      const float row_h = list_row_height(*w);
      const float header = w->table ? row_h : 0.0f;
      const Rect body{w->rect.x + px, w->rect.y + px + header, w->rect.w - 2 * px, w->rect.h - 2 * px - header};
      const float ms = max_scroll(*w);
      const float scroll = scroll_of(w->id);
      const Rect thumb = scrollbar_rect(*w, ms + body.h, body.h, scroll, body);
      if (!thumb.empty() && e.pos.x >= thumb.x - px && e.pos.y >= body.y) {
        drag_.kind = DragState::Kind::Scroll;
        drag_.start_scroll = scroll;
        if (!thumb.contains(e.pos)) {
          /* Click on the track: page towards the pointer. */
          const float page = body.h * 0.9f;
          set_scroll(w->id, scroll + (e.pos.y < thumb.y ? -page : page), ms);
          drag_.start_scroll = scroll_of(w->id);
        }
        break;
      }
      if (w->table) {
        const int rc = table_resize_hit(*w, e.pos);
        if (rc >= 0) {
          drag_.kind = DragState::Kind::ColumnResize;
          drag_.column = rc;
          drag_.start_value = table_state(*w).widths_u[size_t(rc)];
          break;
        }
        const int hc = table_header_col(*w, e.pos);
        if (hc >= 0) {
          drag_.kind = DragState::Kind::Header;
          drag_.column = hc;
          break;
        }
      }
      if (w->log) {
        /* The "follow" pill at the bottom right. */
        const float ph = std::round(0.9f * style_.unit);
        const float pw = std::round(LayoutEngine::text_w(*this, tr("ui.log.follow")) + style_.unit);
        const Rect pill{w->rect.x1() - pw - style_.scrollbar - 3 * px, w->rect.y1() - ph - 3 * px, pw, ph};
        if (!follow_.count(w->id) || follow_[w->id] || !pill.contains(e.pos)) {
          break;
        }
        follow_[w->id] = true;
        set_scroll(w->id, ms, ms);
        break;
      }
      const int view_row = int((e.pos.y - body.y + scroll) / row_h);
      const int count = w->list ? w->list->count : w->table->rows;
      if (view_row >= 0 && view_row < count) {
        const int model_row = w->table ? table_perm(*w)[size_t(view_row)] : view_row;
        Binding<int> sel = w->list ? w->list->selected : w->table->selected;
        sel.assign(model_row);
        if (dbl && w->list && w->list->on_activate) {
          w->list->on_activate(model_row);
        }
      }
      break;
    }
    case WidgetType::Image:
      if (dbl) {
        images_[w->id] = {};
        drag_ = {};
      }
      else {
        drag_.kind = DragState::Kind::ImagePan;
      }
      break;
    case WidgetType::SplitterBar:
      drag_.kind = DragState::Kind::Splitter;
      drag_.start_value = w->factor ? w->factor.value() : 0.5f;
      break;
    default:
      break;
  }
  redraw_ = true;
  return {true, true};
}

EventResult Context::mouse_up(const Event &e)
{
  if (!drag_.id) {
    return {false, false};
  }
  const DragState d = drag_;
  drag_ = {};
  const Widget *w = find_id(d.id);
  if (!w) {
    return {true, true};
  }
  const bool inside = w->rect.contains(e.pos) && w->clip.contains(e.pos);
  switch (d.kind) {
    case DragState::Kind::Press:
      if (!inside) {
        break;
      }
      switch (w->type) {
        case WidgetType::Button:
          if (w->on_click) {
            w->on_click();
          }
          break;
        case WidgetType::Checkbox:
          w->boolean.assign(!w->boolean.value());
          break;
        case WidgetType::MenuItem:
          if (w->enabled) {
            popup_select(w->menu_index);
          }
          break;
        case WidgetType::PanelHeader:
          panels_[w->id] = !panel_open(w->id, true);
          break;
        default:
          break;
      }
      break;
    case DragState::Kind::Number:
    case DragState::Kind::Slider:
      if (!d.moved) {
        if (d.zone != 0) {
          const double step = w->props.integer ? std::max(1.0, w->props.step) : w->props.step;
          w->number.assign(clamp_number(w->number.value() + d.zone * step, w->props));
        }
        else {
          begin_edit(*w, true);
        }
      }
      break;
    case DragState::Kind::Header:
      if (!d.moved && inside && w->table && d.column >= 0 && w->table->columns[size_t(d.column)].sortable) {
        TableState &s = table_state(*w);
        if (s.sort_col == d.column) {
          s.ascending = !s.ascending;
        }
        else {
          s.sort_col = d.column;
          s.ascending = true;
        }
      }
      break;
    default:
      break;
  }
  redraw_ = true;
  return {true, true};
}

EventResult Context::wheel(const Event &e)
{
  if (popup_.owner) {
    for (const auto &b : blocks_) {
      if (b->kind() == Block::Kind::Popup && b->frame().contains(e.pos)) {
        const float content = b->content_height();
        const float view = b->frame().h - 2 * style_.box_space;
        set_scroll(b->id_, scroll_of(b->id_) - e.wheel_y * 3 * style_.unit, content - view);
        return {true, true};
      }
    }
    return {true, false};
  }
  Block *blk = nullptr;
  const Widget *w = hit(e.pos, &blk);
  if (w && (w->type == WidgetType::VirtualList || w->type == WidgetType::Table || w->type == WidgetType::LogView)) {
    const float ms = max_scroll(*w);
    if (ms > 0.0f) {
      set_scroll(w->id, scroll_of(w->id) - e.wheel_y * 3 * list_row_height(*w), ms);
      if (w->log) {
        follow_[w->id] = scroll_of(w->id) >= ms - 0.5f;
      }
      return {true, true};
    }
  }
  if (w && w->type == WidgetType::Image) {
    ImageState &s = images_[w->id];
    const Rect area = w->rect.inset(style_.pixel, style_.pixel);
    const Rect cur = image_display_rect(*w);
    const float iw = float(std::max(1, w->image.width));
    const float old_scale = cur.w / iw;
    const float new_scale = std::clamp(old_scale * std::pow(1.25f, e.wheel_y), 0.01f, 256.0f);
    /* Keep the image point under the pointer fixed. */
    const float ux = (e.pos.x - cur.x) / old_scale, uy = (e.pos.y - cur.y) / old_scale;
    const float nx = e.pos.x - ux * new_scale, ny = e.pos.y - uy * new_scale;
    const float ih = float(std::max(1, w->image.height));
    s.zoom = new_scale;
    s.pan.x = nx - area.cx() + iw * new_scale * 0.5f;
    s.pan.y = ny - area.cy() + ih * new_scale * 0.5f;
    return {true, true};
  }
  if (w && (w->type == WidgetType::Number || w->type == WidgetType::Slider) && (e.mods & primary_mod())) {
    const double step = w->props.integer ? std::max(1.0, w->props.step) : w->props.step;
    w->number.assign(clamp_number(w->number.value() + (e.wheel_y > 0 ? step : -step), w->props));
    return {true, true};
  }
  if (blk && blk->kind() == Block::Kind::Region) {
    const float ms = std::max(0.0f, blk->content_height() - blk->rect().h);
    if (ms > 0.0f) {
      set_scroll(blk->id_, scroll_of(blk->id_) - e.wheel_y * 2 * style_.unit, ms);
      return {true, true};
    }
  }
  return {blk != nullptr, false};
}

bool Context::handle_popup_event(const Event &e, EventResult &res)
{
  const int n = popup_.count;
  const Widget *owner = find_id(popup_.owner);
  auto enabled = [&](int i) {
    return !owner || !popup_.menu || size_t(i) >= owner->menu.size() || owner->menu[size_t(i)].enabled;
  };
  auto step = [&](int dir) {
    int h = popup_.highlight;
    for (int k = 0; k < n; k++) {
      h = h < 0 ? (dir > 0 ? 0 : n - 1) : std::clamp(h + dir, 0, n - 1);
      if (enabled(h)) {
        break;
      }
    }
    popup_.highlight = h;
  };
  switch (e.key) {
    case Key::Up:
      step(-1);
      break;
    case Key::Down:
      step(1);
      break;
    case Key::Home:
      popup_.highlight = -1;
      step(1);
      break;
    case Key::End:
      popup_.highlight = -1;
      step(-1);
      break;
    case Key::Enter:
    case Key::Space:
      if (popup_.highlight >= 0 && enabled(popup_.highlight)) {
        popup_select(popup_.highlight);
      }
      else {
        close_popup();
      }
      break;
    case Key::Escape:
      close_popup();
      break;
    default:
      res = {true, false};
      return true;
  }
  res = {true, true};
  return true;
}

EventResult Context::key_down(const Event &e)
{
  EventResult res;
  if (popup_.owner && handle_popup_event(e, res)) {
    return res;
  }
  if (edit_.id) {
    edit_key(e);
    return {true, true};
  }
  if (e.key == Key::Escape) {
    for (auto it = blocks_.rbegin(); it != blocks_.rend(); ++it) {
      if ((*it)->kind() == Block::Kind::Modal) {
        if ((*it)->on_close) {
          (*it)->on_close();
        }
        return {true, true};
      }
    }
    if (focus_) {
      focus_ = 0;
      return {true, true};
    }
    return {false, false};
  }
  if (e.key == Key::Tab && !(e.mods & (MOD_CTRL | MOD_ALT | MOD_SUPER))) {
    focus_next((e.mods & MOD_SHIFT) != 0);
    return {true, true};
  }
  if (focus_ && activate_focused(e)) {
    return {true, true};
  }
  return {false, false};
}

}  // namespace stk::ui
