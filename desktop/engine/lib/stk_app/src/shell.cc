/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/shell.hh"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>

#include "stk/app/editor_area.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/fonts.hh"
#include "stk/ui/ui.hh"
#include "stk/wm/csd.hh"
#include "stk/wm/window.hh"

#include "app_theme.hh"

#ifndef STK_APP_VERSION
#  define STK_APP_VERSION "0.0.0"
#endif

namespace stk::app {

namespace fs = std::filesystem;

/* -------------------------------------------------------------------- */
/** \name Catalog lookup
 * \{ */

std::string locate_i18n_dir(std::string_view override_dir)
{
  auto has_catalog = [](const fs::path &dir) {
    std::error_code ec;
    return !dir.empty() && fs::is_regular_file(dir / "zh_CN.json", ec);
  };
  std::vector<fs::path> candidates;
  if (!override_dir.empty()) {
    candidates.push_back(core::path_from_utf8(override_dir));
  }
  if (const auto env = core::getenv_utf8("STK_I18N_DIR"); env && !env->empty()) {
    candidates.push_back(core::path_from_utf8(*env));
  }
  const std::string exe = gfx::executable_dir();
  if (!exe.empty()) {
    const fs::path e = core::path_from_utf8(exe);
    candidates.push_back(e / "i18n");
    candidates.push_back(e / ".." / "share" / "stk-desktop" / "i18n");
    candidates.push_back(e / ".." / "Resources" / "i18n");
  }
#ifdef STK_APP_SOURCE_I18N_DIR
  candidates.push_back(core::path_from_utf8(STK_APP_SOURCE_I18N_DIR));
#endif
  for (const fs::path &c : candidates) {
    if (has_catalog(c)) {
      return core::path_to_utf8(fs::weakly_canonical(c));
    }
  }
  return {};
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Top bar and status bar
 * \{ */

namespace {

float text_px(ui::Context &ui, std::string_view s)
{
  return ui.measurer().width(s, ui.style().font);
}

float units_of(ui::Context &ui, const float px)
{
  return px / std::max(1.0f, ui.style().unit);
}

/** Fixed width fitting a label / button text. */
float fit_units(ui::Context &ui, std::string_view s, const float min_units = 0.0f)
{
  return std::max(min_units, units_of(ui, text_px(ui, s) + 2.0f * ui.style().text_margin));
}

std::string mark(const bool on, std::string_view text)
{
  return std::string(on ? "\xe2\x80\xa2 " : "   ") + std::string(text);
}

const char *csd_glyph(const wm::CsdButtonKind k, const bool maximized)
{
  switch (k) {
    case wm::CsdButtonKind::Close: return "\xc3\x97";                             /* × */
    case wm::CsdButtonKind::Maximize: return maximized ? "\xe2\x9d\x90" : "\xe2\x96\xa1"; /* ❐ □ */
    case wm::CsdButtonKind::Minimize: return "\xe2\x80\x93";                      /* – */
    case wm::CsdButtonKind::Menu: return "STK";
  }
  return "";
}

}  // namespace

class AppShell::TopBar final : public wm::Region {
 public:
  TopBar(AppShell &shell, wm::Screen &screen) : Region("topbar"), shell_(shell), screen_(screen)
  {
    persistent = false;
  }

  void build_ui(ui::Context &ui, const wm::DrawContext &ctx) override
  {
    const ui::Rect r = ui_rect();
    const ui::Style &st = ui.style();
    wm::CsdLayout csd;
    const bool has_csd = ctx.window && shell_.wm_ && shell_.wm_->csd_active();
    if (has_csd) {
      csd = wm::csd_layout(*ctx.window);
    }
    const float left = float(csd.left_reserve), right = float(csd.right_reserve);
    ui::Block &b = ui.block(block_name(), {r.x + left, r.y, std::max(0.0f, r.w - left - right), r.h});
    b.set_background(theme::kBarBack);
    ui::Layout &row = b.layout().row(false);
    auto menu = [&](const char *key, const char *label_key, std::vector<ui::MenuEntry> entries) {
      const std::string_view label = shell_.store_.tr(label_key);
      row.menu_button(key, label, std::move(entries)).width(fit_units(ui, label, 2.0f));
    };
    menu("file", "app.menu.file", shell_.file_menu(screen_));
    menu("view", "app.menu.view", shell_.view_menu(screen_));
    menu("language", "app.menu.language", shell_.language_menu());
    menu("scale", "app.menu.scale", shell_.scale_menu());
    row.label(shell_.store_.tr("app.title"), ui::Align::Center);

    if (has_csd && !csd.buttons.empty()) {
      /* The window buttons sit exactly where GHOST expects them: one aligned block per side,
       * widened by the block margin so the row spans the button rectangles. */
      const bool maximized = ctx.window->maximized();
      for (int side = 0; side < 2; side++) {
        std::vector<const wm::CsdButton *> btns;
        for (const wm::CsdButton &cb : csd.buttons) {
          const bool is_left = cb.rect.xmin < csd.left_reserve;
          if ((side == 0) == is_left) {
            btns.push_back(&cb);
          }
        }
        if (btns.empty()) {
          continue;
        }
        std::sort(btns.begin(), btns.end(), [](auto *a, auto *b) { return a->rect.xmin < b->rect.xmin; });
        const float x0 = float(btns.front()->rect.xmin), x1 = float(btns.back()->rect.xmax);
        const float m = st.panel_margin;
        ui::Block &cb = ui.block(block_name() + (side == 0 ? "/csd_l" : "/csd_r"), {x0 - m, r.y, x1 - x0 + 2 * m, r.h});
        cb.set_background(theme::kBarBack);
        ui::Layout &brow = cb.layout().row(true);
        for (const wm::CsdButton *btn : btns) {
          /* GHOST performs the action (it sees the same events); the button only shows it. */
          brow.button(std::string("csd") + std::to_string(int(btn->kind)), csd_glyph(btn->kind, maximized), []() {})
              .width(units_of(ui, float(btn->rect.width())));
        }
      }
    }
  }

 private:
  AppShell &shell_;
  wm::Screen &screen_;
};

class AppShell::StatusBar final : public wm::Region {
 public:
  StatusBar(AppShell &shell, wm::Screen &screen) : Region("statusbar"), shell_(shell), screen_(screen)
  {
    persistent = false;
  }

  void build_ui(ui::Context &ui, const wm::DrawContext & /*ctx*/) override
  {
    AppStore &store = shell_.store_;
    ui::Block &b = ui.block(block_name(), ui_rect());
    b.set_background(theme::kBarBack);
    ui::Layout &row = b.layout().row(false);
    const std::string bridge = store.catalog().format(
        "app.status.bridge", {{"state", std::string(store.tr(bridge_state_key(store.bridge_state())))}});
    std::string tip(store.tr("app.status.bridge.tip"));
    if (!store.bridge_error().empty()) {
      tip += "\n" + store.bridge_error();
    }
    row.label(bridge).width(fit_units(ui, bridge)).tip(tip);
    const std::string conn = store.connection().empty() ?
                                 std::string(store.tr("app.status.connection.none")) :
                                 store.catalog().format("app.status.connection", {{"name", store.connection()}});
    row.label(conn).width(fit_units(ui, conn));
    std::string hint(store.tr("app.status.hint"));
    if (screen_.maximized()) {
      hint = std::string(store.tr("app.status.maximized"));
    }
    row.label(hint);
    const std::string version = std::string("STK ") + STK_APP_VERSION;
    row.label(version, ui::Align::Right).width(fit_units(ui, version));
  }

 private:
  AppShell &shell_;
  wm::Screen &screen_;
};

/** \} */

/* -------------------------------------------------------------------- */
/** \name AppShell
 * \{ */

AppShell::AppShell(ShellOptions options) : options_(std::move(options))
{
  register_builtin_editors(registry_);
  if (options_.i18n_dir.empty()) {
    options_.i18n_dir = locate_i18n_dir("");
  }
  ui::Catalog &cat = store_.catalog();
  if (options_.i18n_dir.empty()) {
    catalog_error_ = "message catalogs not found";
  }
  else {
    std::string err;
    catalogs_loaded_ = cat.load_dir(options_.i18n_dir, &err) >= 2 && cat.has(ui::Catalog::DEFAULT_LANGUAGE, "app.title");
    if (!catalogs_loaded_) {
      catalog_error_ = err.empty() ? "incomplete catalogs in " + options_.i18n_dir : err;
    }
  }
  cat.set_language(options_.language.empty() ? std::string(ui::Catalog::DEFAULT_LANGUAGE) : options_.language);
  layout_path = wm::default_layout_path();
  if (options_.interactive) {
    store_.clock = []() {
      const std::time_t t = std::time(nullptr);
      std::tm tm{};
#ifdef _WIN32
      localtime_s(&tm, &t);
#else
      localtime_r(&t, &tm);
#endif
      char buf[16];
      std::strftime(buf, sizeof(buf), "%H:%M:%S", &tm);
      return std::string(buf);
    };
  }
  store_.on_change = [this]() {
    for (wm::Screen *s : screens_) {
      s->tag_redraw();
    }
  };
  store_.toast = [this](const std::string &text, ui::ToastKind kind) {
    if (!options_.interactive) {
      return;
    }
    for (wm::Screen *s : screens_) {
      if (s->ui()) {
        s->ui()->toast(text, kind);
        s->tag_redraw();
      }
    }
  };
}

AppShell::~AppShell()
{
  alive_.reset();
  store_.on_change = nullptr;
  store_.toast = nullptr;
}

void AppShell::forget(wm::Screen &screen, wm::Window *window)
{
  std::erase(screens_, &screen);
  if (window && window == window_) {
    window_ = nullptr;
  }
}

void AppShell::install(wm::Screen &screen, wm::Window *window)
{
  if (std::find(screens_.begin(), screens_.end(), &screen) == screens_.end()) {
    screens_.push_back(&screen);
  }
  if (window) {
    window_ = window;
    wm_ = &window->manager();
    /* Forget the screen (and window) when the window closes: store changes arriving later (bridge
     * callbacks, the viewer and jobs states) must not reach a destroyed screen. */
    std::weak_ptr<bool> alive = alive_;
    window->add_close_listener([this, alive, s = &screen](wm::Window &w) {
      if (alive.lock()) {
        forget(*s, &w);
      }
    });
  }
  ui::ContextConfig cfg;
  cfg.measurer = options_.measurer;
  cfg.catalog = &store_.catalog();
#ifdef __APPLE__
  cfg.mac_shortcuts = true;
#endif
  screen.set_ui_config(cfg);
  screen.background[0] = screen.background[1] = screen.background[2] = 0x16 / 255.0f;
  screen.background[3] = 1.0f;
  screen.set_area_factory([this](const std::string &type) -> std::unique_ptr<wm::Area> {
    if (!registry_.find(type)) {
      return nullptr;
    }
    return std::make_unique<EditorArea>(*this, type);
  });
  auto top = std::make_unique<wm::Area>("topbar");
  top->emplace_region<TopBar>(*this, screen);
  screen.set_global_area(wm::RegionAlign::Top, std::move(top));
  auto bottom = std::make_unique<wm::Area>("statusbar");
  bottom->emplace_region<StatusBar>(*this, screen);
  screen.set_global_area(wm::RegionAlign::Bottom, std::move(bottom));
  wm::Screen *sp = &screen;
  screen.on_unhandled_event = [this, sp](const wm::Event &e) { return handle_shortcut(*sp, e); };
}

static nlohmann::json leaf_json(const char *id, const std::vector<const char *> &tabs, const double factor)
{
  nlohmann::json t = nlohmann::json::array();
  for (const char *type : tabs) {
    t.push_back({{"type", type}});
  }
  return {{"factor", factor},
          {"area", {{"id", id}, {"type", tabs.front()}, {"state", {{"tabs", t}, {"active", 0}}}}}};
}

void AppShell::build_default_layout(wm::Screen &screen)
{
  /* Jobs | Viewer | Properties over a strip of Logs / Probe / Transfers / Bridge log tabs. */
  const nlohmann::json top = {
      {"factor", 0.72},
      {"split", "horizontal"},
      {"children",
       {leaf_json("a1", {kEditorJobs}, 0.22), leaf_json("a2", {kEditorViewer}, 0.53),
        leaf_json("a3", {kEditorProperties}, 0.25)}}};
  const nlohmann::json layout = {
      {"maximized", nullptr},
      {"root",
       {{"factor", 1.0},
        {"split", "vertical"},
        {"children", {top, leaf_json("a4", {kEditorLogs, kEditorProbe, kEditorTransfers, kEditorBridgeLog}, 0.28)}}}}};
  std::string err;
  if (!screen.from_json(layout, &err)) {
    /* Only reachable when an editor type was unregistered: fall back to one area. */
    std::fprintf(stderr, "stk-desktop: default layout: %s\n", err.c_str());
    screen.set_root(std::make_unique<EditorArea>(*this, kEditorJobs));
  }
}

void AppShell::reset_layout(wm::Screen &screen)
{
  build_default_layout(screen);
  store_.log(std::string(store_.tr("app.log.layout_reset")));
}

wm::LayoutFile AppShell::capture_layout(const wm::Screen &screen, const wm::Window *window) const
{
  wm::LayoutFile f;
  f.language = store_.language();
  f.ui_scale = store_.ui_scale();
  f.screen = screen.to_json();
  f.window.width = kDefaultWindowWidth;
  f.window.height = kDefaultWindowHeight;
  if (window) {
    int x = 0, y = 0, w = 0, h = 0;
    window->client_geometry(x, y, w, h);
    f.window.width = w;
    f.window.height = h;
    const char *backend = window->manager().system_backend();
    f.window.has_position = !(backend && std::strcmp(backend, "WAYLAND") == 0);
    f.window.x = x;
    f.window.y = y;
    f.window.maximized = window->maximized();
  }
  return f;
}

bool AppShell::apply_layout(wm::Screen &screen, const wm::LayoutFile &file, std::string *r_error)
{
  if (!screen.from_json(file.screen, r_error)) {
    return false;
  }
  const std::vector<std::string> langs = store_.catalog().languages();
  if (!file.language.empty() && std::find(langs.begin(), langs.end(), file.language) != langs.end()) {
    set_language(file.language);
  }
  set_ui_scale(file.ui_scale);
  return true;
}

bool AppShell::restore(wm::Screen &screen, const fs::path &path, const bool quarantine_corrupt)
{
  wm::LayoutFile file;
  std::string err;
  const wm::LayoutLoad res = wm::load_layout_file(path, file, &err);
  if (res == wm::LayoutLoad::Missing) {
    return false;
  }
  if (res == wm::LayoutLoad::Ok && apply_layout(screen, file, &err)) {
    store_.log(store_.catalog().format("app.log.layout_restored", {{"path", core::path_to_utf8(path)}}));
    return true;
  }
  std::string msg = store_.catalog().format("app.log.layout_corrupt", {{"path", core::path_to_utf8(path)}, {"error", err}});
  if (quarantine_corrupt) {
    const fs::path aside = wm::quarantine_layout_file(path);
    if (!aside.empty()) {
      msg += " -> " + core::path_to_utf8(aside);
    }
  }
  store_.log(msg);
  std::fprintf(stderr, "stk-desktop: %s\n", msg.c_str());
  return false;
}

bool AppShell::save(const wm::Screen &screen, const wm::Window *window, const fs::path &path)
{
  std::string err;
  if (!wm::save_layout_file(path, capture_layout(screen, window), &err)) {
    store_.log(store_.catalog().format("app.log.layout_save_failed", {{"error", err}}));
    return false;
  }
  store_.log(store_.catalog().format("app.log.layout_saved", {{"path", core::path_to_utf8(path)}}));
  return true;
}

void AppShell::set_language(const std::string &language)
{
  store_.set_language(language);
}

void AppShell::set_ui_scale(const float scale)
{
  store_.set_ui_scale(scale);
  if (wm_) {
    /* With client-side decorations GHOST picks up the new title-bar size at the compositor's
     * next configure (resize, state or activation change). */
    wm_->set_user_scale(store_.ui_scale());
  }
}

std::vector<ui::MenuEntry> AppShell::file_menu(wm::Screen &screen)
{
  std::vector<ui::MenuEntry> m;
  wm::Screen *s = &screen;
  /* WP10: open a payload (.stkp / directory), a result directory or a run directory in the Viewer. */
  m.push_back({std::string(store_.tr("viewer.menu.open")), [this]() {
                 store_.viewer().open_dialog = true;
                 store_.changed();
               }});
  m.push_back({std::string(store_.tr("app.menu.file.save_layout")),
               [this, s]() { save(*s, window_, layout_path); },
               !layout_path.empty()});
  m.push_back({std::string(store_.tr("app.menu.file.reset_layout")),
               [this, s]() { s->defer([this, s]() { reset_layout(*s); }); }});
  m.push_back({std::string(store_.tr("app.menu.file.quit")),
               [this]() {
                 if (on_quit) {
                   on_quit();
                 }
               },
               bool(on_quit)});
  return m;
}

std::vector<ui::MenuEntry> AppShell::view_menu(wm::Screen &screen)
{
  std::vector<ui::MenuEntry> m;
  wm::Screen *s = &screen;
  wm::Area *active = screen.maximized() ? screen.maximized() : screen.active_area();
  auto *ea = dynamic_cast<EditorArea *>(active);
  const bool maxed = screen.maximized() != nullptr;
  m.push_back({std::string(store_.tr(maxed ? "app.menu.view.restore" : "app.menu.view.maximize")),
               [s, active]() { s->defer([s, active]() { s->toggle_maximized(active); }); },
               maxed || active != nullptr});
  m.push_back({std::string(store_.tr("app.menu.view.split_h")),
               [s, active]() { s->defer([s, active]() { s->split(*active, wm::SplitDir::Horizontal); }); },
               active != nullptr && !maxed});
  m.push_back({std::string(store_.tr("app.menu.view.split_v")),
               [s, active]() { s->defer([s, active]() { s->split(*active, wm::SplitDir::Vertical); }); },
               active != nullptr && !maxed});
  m.push_back({mark(ea && ea->toolbar_open() && ea->editor().has_toolbar(), store_.tr("app.menu.view.toolbar")),
               [ea]() { ea->set_toolbar_open(!ea->toolbar_open()); },
               ea && ea->editor().has_toolbar()});
  m.push_back({mark(ea && ea->sidebar_open() && ea->editor().has_sidebar(), store_.tr("app.menu.view.sidebar")),
               [ea]() { ea->set_sidebar_open(!ea->sidebar_open()); },
               ea && ea->editor().has_sidebar()});
  m.push_back({std::string(store_.tr("app.menu.file.reset_layout")),
               [this, s]() { s->defer([this, s]() { reset_layout(*s); }); }});
  return m;
}

std::vector<ui::MenuEntry> AppShell::language_menu()
{
  const std::string &lang = store_.language();
  return {
      {mark(lang == "zh_CN", "\xe4\xb8\xad\xe6\x96\x87"), [this]() { set_language("zh_CN"); }}, /* 中文 */
      {mark(lang == "en", "English"), [this]() { set_language("en"); }},
  };
}

std::vector<ui::MenuEntry> AppShell::scale_menu()
{
  std::vector<ui::MenuEntry> m;
  for (const float s : {0.75f, 1.0f, 1.25f, 1.5f, 1.75f, 2.0f}) {
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%d%%", int(std::lround(s * 100)));
    m.push_back({mark(std::fabs(store_.ui_scale() - s) < 1e-3f, buf), [this, s]() { set_ui_scale(s); }, bool(wm_)});
  }
  return m;
}

bool AppShell::handle_shortcut(wm::Screen &screen, const wm::Event &e)
{
  if (e.type != wm::EventType::KeyDown) {
    return false;
  }
  const uint32_t mods = e.modifiers & ~wm::ModShift;
#ifdef __APPLE__
  const uint32_t primary = wm::ModOS;
#else
  const uint32_t primary = wm::ModCtrl;
#endif
  if (mods != primary) {
    return false;
  }
  switch (e.key) {
    case wm::Key::Q:
      if (on_quit) {
        on_quit();
        return true;
      }
      return false;
    case wm::Key::S:
      if (!layout_path.empty()) {
        save(screen, window_, layout_path);
        if (store_.toast) {
          store_.toast(std::string(store_.tr("app.toast.layout_saved")), ui::ToastKind::Success);
        }
        return true;
      }
      return false;
    case wm::Key::Equal:
    case wm::Key::Plus:
    case wm::Key::NumpadPlus:
      set_ui_scale(std::min(3.0f, store_.ui_scale() + 0.25f));
      return bool(wm_);
    case wm::Key::Minus:
    case wm::Key::NumpadMinus:
      set_ui_scale(std::max(0.5f, store_.ui_scale() - 0.25f));
      return bool(wm_);
    case wm::Key::Num0:
    case wm::Key::Numpad0:
      set_ui_scale(1.0f);
      return bool(wm_);
    default:
      return false;
  }
}

/** \} */

}  // namespace stk::app
