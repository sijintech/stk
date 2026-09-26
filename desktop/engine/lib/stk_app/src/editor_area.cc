/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/editor_area.hh"

#include <algorithm>

#include "stk/app/app_store.hh"
#include "stk/app/shell.hh"
#include "stk/ui/ui.hh"

#include "app_theme.hh"

namespace stk::app {

/* -------------------------------------------------------------------- */
/** \name Regions
 * \{ */

class EditorRegion final : public wm::Region {
 public:
  enum class Kind { Header, Toolbar, Sidebar, Main };

  EditorRegion(EditorArea &owner, const Kind kind)
      : Region(name_of(kind), align_of(kind), size_of(kind)), owner_(owner), kind_(kind)
  {
    switch (kind) {
      case Kind::Header:
        /* Right-click on empty header space opens the area menu. Its height follows the UI
         * scale, so there is nothing to persist. */
        ui_pass_through = true;
        persistent = false;
        break;
      case Kind::Toolbar:
        resizable = true;
        min_size_1x = 36.0f;
        max_size_1x = 240.0f;
        break;
      case Kind::Sidebar:
        resizable = true;
        min_size_1x = 120.0f;
        max_size_1x = 600.0f;
        break;
      case Kind::Main:
        break;
    }
  }

  int size_px(const float ui_scale) const override
  {
    return kind_ == Kind::Header ? wm::ui_bar_height_px(ui_scale) : Region::size_px(ui_scale);
  }

  void build_ui(ui::Context &ui, const wm::DrawContext &ctx) override
  {
    EditorContext ec = owner_.context(&ui, &ctx);
    Editor &ed = owner_.editor();
    ui::Block &b = ui.block(block_name(), ui_rect());
    switch (kind_) {
      case Kind::Header:
        b.set_background(theme::kHeaderBack);
        owner_.build_header(b.layout().row(false), ec);
        break;
      case Kind::Toolbar:
        b.set_background(theme::kToolBack);
        ed.draw_toolbar(b.layout(), ec);
        break;
      case Kind::Sidebar:
        b.set_background(theme::kToolBack);
        ed.draw_sidebar(b.layout(), ec);
        break;
      case Kind::Main:
        ui_pass_through = ed.draws_gpu();
        b.set_background(ed.main_background(ui.theme()));
        ed.draw_main(b.layout(), ec);
        break;
    }
  }

  void draw(const wm::DrawContext &ctx) override
  {
    if (kind_ == Kind::Main && owner_.editor().draws_gpu()) {
      EditorContext ec = owner_.context(ctx.ui, &ctx);
      owner_.editor().draw_gpu(ec);
    }
  }

  bool handle_event(const wm::Event &e, const wm::DrawContext &ctx) override
  {
    if (kind_ == Kind::Header && e.type == wm::EventType::MouseDown && e.button == wm::MouseButton::Right &&
        ctx.ui)
    {
      ctx.ui->open_popup(owner_.area_menu_key());
      tag_redraw();
      return true;
    }
    if (kind_ == Kind::Main && owner_.editor().draws_gpu()) {
      EditorContext ec = owner_.context(ctx.ui, &ctx);
      return owner_.editor().handle_gpu_event(e, ec);
    }
    return false;
  }

 private:
  static const char *name_of(const Kind k)
  {
    switch (k) {
      case Kind::Header: return EditorArea::kHeader;
      case Kind::Toolbar: return EditorArea::kToolbar;
      case Kind::Sidebar: return EditorArea::kSidebar;
      case Kind::Main: return EditorArea::kMain;
    }
    return EditorArea::kMain;
  }
  static wm::RegionAlign align_of(const Kind k)
  {
    switch (k) {
      case Kind::Header: return wm::RegionAlign::Top;
      case Kind::Toolbar: return wm::RegionAlign::Left;
      case Kind::Sidebar: return wm::RegionAlign::Right;
      case Kind::Main: return wm::RegionAlign::Fill;
    }
    return wm::RegionAlign::Fill;
  }
  static float size_of(const Kind k)
  {
    switch (k) {
      case Kind::Toolbar: return 48.0f;
      case Kind::Sidebar: return 220.0f;
      default: return 0.0f;
    }
  }

  EditorArea &owner_;
  Kind kind_;
};

/** \} */

/* -------------------------------------------------------------------- */
/** \name EditorArea
 * \{ */

EditorArea::EditorArea(AppShell &shell, const std::string &type) : wm::Area(type), shell_(shell)
{
  min_width_1x = 100.0f;
  min_height_1x = 24.0f;
  emplace_region<EditorRegion>(*this, EditorRegion::Kind::Header);
  emplace_region<EditorRegion>(*this, EditorRegion::Kind::Toolbar);
  emplace_region<EditorRegion>(*this, EditorRegion::Kind::Sidebar);
  emplace_region<EditorRegion>(*this, EditorRegion::Kind::Main);
  std::unique_ptr<Editor> e = shell_.registry().create(type);
  if (!e && !shell_.registry().types().empty()) {
    e = shell_.registry().create(shell_.registry().types().front()->id);
  }
  tabs_.push_back(std::move(e));
  sync_regions();
}

EditorArea::~EditorArea() = default;

void EditorArea::sync_regions()
{
  if (tabs_.empty() || !tabs_[size_t(active_)]) {
    return;
  }
  Editor &ed = editor();
  find_region(kToolbar)->set_visible(ed.has_toolbar() && toolbar_open_);
  find_region(kSidebar)->set_visible(ed.has_sidebar() && sidebar_open_);
  if (type() != ed.type().id) {
    set_type(ed.type().id);
  }
  tag_redraw();
}

void EditorArea::set_active_tab(const int index)
{
  const int i = std::clamp(index, 0, int(tabs_.size()) - 1);
  if (i != active_) {
    active_ = i;
    sync_regions();
  }
}

bool EditorArea::set_tab_type(const int index, const std::string &type)
{
  if (index < 0 || index >= int(tabs_.size())) {
    return false;
  }
  if (tabs_[size_t(index)]->type().id == type) {
    return true;
  }
  std::unique_ptr<Editor> e = shell_.registry().create(type);
  if (!e) {
    return false;
  }
  tabs_[size_t(index)] = std::move(e);
  sync_regions();
  return true;
}

bool EditorArea::add_tab(const std::string &type, const bool activate)
{
  std::unique_ptr<Editor> e = shell_.registry().create(type);
  if (!e || tabs_.size() >= 16) {
    return false;
  }
  tabs_.push_back(std::move(e));
  if (activate) {
    active_ = int(tabs_.size()) - 1;
  }
  sync_regions();
  return true;
}

void EditorArea::close_tab(const int index)
{
  if (tabs_.size() <= 1 || index < 0 || index >= int(tabs_.size())) {
    return;
  }
  tabs_.erase(tabs_.begin() + index);
  if (active_ >= int(tabs_.size()) || active_ > index) {
    active_ = std::max(0, active_ - 1);
  }
  sync_regions();
}

bool EditorArea::set_tabs(const std::vector<std::string> &types, const int active)
{
  if (types.empty() || types.size() > 16) {
    return false;
  }
  std::vector<std::unique_ptr<Editor>> tabs;
  for (const std::string &t : types) {
    std::unique_ptr<Editor> e = shell_.registry().create(t);
    if (!e) {
      return false;
    }
    tabs.push_back(std::move(e));
  }
  tabs_ = std::move(tabs);
  active_ = std::clamp(active, 0, int(tabs_.size()) - 1);
  sync_regions();
  return true;
}

void EditorArea::set_toolbar_open(const bool open)
{
  if (open != toolbar_open_) {
    toolbar_open_ = open;
    sync_regions();
  }
}

void EditorArea::set_sidebar_open(const bool open)
{
  if (open != sidebar_open_) {
    sidebar_open_ = open;
    sync_regions();
  }
}

std::string EditorArea::area_menu_key() const
{
  return id() + "/" + kHeader + "/area_menu";
}

EditorContext EditorArea::context(ui::Context *ui, const wm::DrawContext *draw)
{
  return EditorContext{shell_.store(), *this, ui, draw};
}

static std::string mark(const bool on, std::string_view text)
{
  /* "• " marks the active choice (U+2022 is in Inter). */
  return std::string(on ? "\xe2\x80\xa2 " : "   ") + std::string(text);
}

std::vector<ui::MenuEntry> EditorArea::area_menu(const wm::DrawContext *draw)
{
  AppStore &store = shell_.store();
  wm::Screen *s = screen();
  std::vector<ui::MenuEntry> m;
  auto defer = [s](std::function<void()> fn) {
    if (s) {
      s->defer(std::move(fn));
    }
  };
  auto split = [this, s, &store](wm::SplitDir dir) {
    return [this, s, dir, &store]() {
      s->defer([this, s, dir, &store]() {
        if (!s->split(*this, dir, 0.5f)) {
          if (store.toast) {
            store.toast(std::string(store.tr("area.too_small")), ui::ToastKind::Warning);
          }
        }
      });
    };
  };
  Area *prev = s ? s->sibling(*this, false) : nullptr;
  Area *next = s ? s->sibling(*this, true) : nullptr;
  const bool in_tree = node() != nullptr;
  m.push_back({std::string(store.tr("area.menu.split_h")), split(wm::SplitDir::Horizontal), in_tree});
  m.push_back({std::string(store.tr("area.menu.split_v")), split(wm::SplitDir::Vertical), in_tree});
  m.push_back({std::string(store.tr("area.menu.join_prev")),
               [this, s, defer]() {
                 defer([this, s]() {
                   if (Area *p = s->sibling(*this, false)) {
                     s->join(*this, *p);
                   }
                 });
               },
               prev != nullptr});
  m.push_back({std::string(store.tr("area.menu.join_next")),
               [this, s, defer]() {
                 defer([this, s]() {
                   if (Area *n = s->sibling(*this, true)) {
                     s->join(*this, *n);
                   }
                 });
               },
               next != nullptr});
  const bool maxed = s && s->maximized() == this;
  m.push_back({std::string(store.tr(maxed ? "area.menu.restore" : "area.menu.maximize")),
               [this, s, defer]() { defer([this, s]() { s->toggle_maximized(this); }); },
               in_tree && (!s || !s->maximized() || maxed)});
  m.push_back({mark(toolbar_open_ && editor().has_toolbar(), store.tr("area.menu.toolbar")),
               [this]() { set_toolbar_open(!toolbar_open_); },
               editor().has_toolbar()});
  m.push_back({mark(sidebar_open_ && editor().has_sidebar(), store.tr("area.menu.sidebar")),
               [this]() { set_sidebar_open(!sidebar_open_); },
               editor().has_sidebar()});
  m.push_back({std::string(store.tr("area.menu.new_tab")),
               [this, defer]() {
                 const std::string t = editor().type().id;
                 defer([this, t]() { add_tab(t); });
               },
               tabs_.size() < 16});
  m.push_back({std::string(store.tr("area.menu.close_tab")),
               [this, defer]() {
                 const int i = active_;
                 defer([this, i]() { close_tab(i); });
               },
               tabs_.size() > 1});
  m.push_back({std::string(store.tr("area.menu.close_area")),
               [this, s, defer]() {
                 defer([this, s]() {
                   /* The neighbour takes the space; `this` is destroyed. */
                   if (Area *p = s->sibling(*this, false)) {
                     s->join(*p, *this);
                   }
                   else if (Area *n = s->sibling(*this, true)) {
                     s->join(*n, *this);
                   }
                 });
               },
               prev != nullptr || next != nullptr});
  EditorContext ec = context(s ? s->ui() : nullptr, draw);
  editor().menu_entries(m, ec);
  return m;
}

void EditorArea::build_header(ui::Layout &row, EditorContext &ctx)
{
  ui::Context &ui = *ctx.ui;
  const ui::Style &st = ui.style();
  const EditorRegistry &reg = shell_.registry();
  auto units = [&](float px) { return px / std::max(1.0f, st.unit); };
  auto text_w = [&](std::string_view s) { return ui.measurer().width(s, st.font); };

  std::vector<std::string> names;
  float names_w = 0.0f;
  for (const auto &t : reg.types()) {
    names.emplace_back(ctx.tr(t->title_key));
    names_w = std::max(names_w, text_w(names.back()));
  }
  const int current = reg.index_of(editor().type().id);
  row.dropdown("editor_type",
               names,
               ui::Binding<int>{[current]() { return current; },
                                [this, &reg](int i) {
                                  if (i < 0 || i >= int(reg.types().size())) {
                                    return;
                                  }
                                  const std::string id = reg.types()[size_t(i)]->id;
                                  const int tab = active_;
                                  if (wm::Screen *s = screen()) {
                                    s->defer([this, tab, id]() { set_tab_type(tab, id); });
                                  }
                                }})
      .width(units(names_w + 2 * st.text_margin + st.unit))
      .tip(ctx.tr("area.editor_type.tip"));
  if (tabs_.size() > 1) {
    /* The tabs widget gives every tab the same width: size it for the longest label. */
    std::vector<std::string> labels;
    float widest = 0.0f;
    for (const auto &e : tabs_) {
      labels.emplace_back(ctx.tr(e->type().title_key));
      widest = std::max(widest, text_w(labels.back()) + 2 * st.text_margin);
    }
    const float w = widest * float(labels.size());
    row.tabs("tabs", labels, ui::Binding<int>{[this]() { return active_; }, [this](int i) { set_active_tab(i); }})
        .width(units(w));
  }
  editor().draw_header(row, ctx);
  row.label(""); /* Flexible space. */
  const std::string_view menu = ctx.tr("area.menu");
  row.menu_button("area_menu", menu, area_menu(ctx.draw))
      .width(units(std::max(2.0f * st.unit, text_w(menu) + 2 * st.text_margin)))
      .tip(ctx.tr("area.menu.tip"));
}

bool EditorArea::on_drop(const wm::Event &event)
{
  if (event.paths.empty()) {
    return false;
  }
  AppStore &store = shell_.store();
  EditorContext ec = context(screen() ? screen()->ui() : nullptr, nullptr);
  if (editor().on_drop(event.paths, ec)) {
    return true;
  }
  const std::string msg = store.catalog().format(
      "app.drop.unhandled",
      {{"count", std::to_string(event.paths.size())}, {"editor", std::string(store.tr(editor().type().title_key))}});
  store.log(msg);
  if (store.toast) {
    store.toast(msg, ui::ToastKind::Info);
  }
  return true;
}

bool EditorArea::handle_event(const wm::Event &e, const wm::DrawContext &ctx)
{
  if (e.type == wm::EventType::KeyDown) {
    const uint32_t mods = e.modifiers & ~wm::ModShift;
    if (mods == wm::ModNone && e.key == wm::Key::T && editor().has_toolbar()) {
      set_toolbar_open(!toolbar_open_);
      return true;
    }
    if (mods == wm::ModNone && e.key == wm::Key::N && editor().has_sidebar()) {
      set_sidebar_open(!sidebar_open_);
      return true;
    }
    if (mods == wm::ModCtrl && (e.key == wm::Key::PageUp || e.key == wm::Key::PageDown) && tabs_.size() > 1) {
      const int n = int(tabs_.size());
      set_active_tab((active_ + (e.key == wm::Key::PageDown ? 1 : n - 1)) % n);
      return true;
    }
  }
  EditorContext ec = context(ctx.ui, &ctx);
  return editor().on_key(e, ec);
}

nlohmann::json EditorArea::save_state() const
{
  nlohmann::json tabs = nlohmann::json::array();
  for (const auto &e : tabs_) {
    nlohmann::json st = e->save_state();
    tabs.push_back({{"type", e->type().id}, {"state", st.is_object() ? st : nlohmann::json::object()}});
  }
  return {{"tabs", std::move(tabs)}, {"active", active_}, {"toolbar", toolbar_open_}, {"sidebar", sidebar_open_}};
}

bool EditorArea::load_state(const nlohmann::json &state)
{
  if (!state.is_object()) {
    return false;
  }
  bool toolbar = toolbar_open_, sidebar = sidebar_open_;
  if (const auto t = state.find("toolbar"); t != state.end()) {
    if (!t->is_boolean()) {
      return false;
    }
    toolbar = t->get<bool>();
  }
  if (const auto s = state.find("sidebar"); s != state.end()) {
    if (!s->is_boolean()) {
      return false;
    }
    sidebar = s->get<bool>();
  }
  const auto tabs = state.find("tabs");
  if (tabs != state.end()) {
    if (!tabs->is_array() || tabs->empty() || tabs->size() > 16) {
      return false;
    }
    std::vector<std::unique_ptr<Editor>> created;
    for (const auto &t : *tabs) {
      const auto type = t.is_object() ? t.find("type") : t.end();
      if (!t.is_object() || type == t.end() || !type->is_string()) {
        return false;
      }
      std::unique_ptr<Editor> e = shell_.registry().create(type->get<std::string>());
      if (!e) {
        return false;
      }
      if (const auto st = t.find("state"); st != t.end()) {
        if (!st->is_object() || !e->load_state(*st)) {
          return false;
        }
      }
      created.push_back(std::move(e));
    }
    int active = 0;
    if (const auto a = state.find("active"); a != state.end()) {
      if (!a->is_number_integer() || a->get<long long>() < 0 || a->get<long long>() >= (long long)created.size()) {
        return false;
      }
      active = a->get<int>();
    }
    tabs_ = std::move(created);
    active_ = active;
  }
  toolbar_open_ = toolbar;
  sidebar_open_ = sidebar;
  sync_regions();
  return true;
}

/** \} */

}  // namespace stk::app
