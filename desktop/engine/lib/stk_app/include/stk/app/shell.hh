/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * AppShell: the application frame around the editors. Owns the AppStore and the editor
 * registry, installs on a screen the top bar (app menu File / View / Language / UI scale, window
 * title and, on GNOME Wayland, the client-side window buttons), the status bar (bridge state,
 * connection, hints), the area factory and the application shortcuts, builds the default layout
 * (Jobs | Viewer | Properties over a bottom strip with the Logs / Probe / Transfers / Bridge log
 * tabs) and converts screens to and from layout files.
 *
 *   AppShell shell({.i18n_dir = locate_i18n_dir("")});
 *   shell.install(window->screen(), window);
 *   if (!shell.restore(window->screen(), layout_path)) shell.build_default_layout(window->screen());
 */
#pragma once

#include <filesystem>
#include <functional>
#include <memory>
#include <string>
#include <string_view>

#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/wm/layout_store.hh"
#include "stk/wm/screen.hh"

namespace stk::ui {
class TextMeasurer;
}
namespace stk::wm {
class Window;
class WindowManager;
}  // namespace stk::wm

namespace stk::app {

/**
 * Directory of the message catalogs: `override_dir`, $STK_I18N_DIR, next to the executable
 * (`i18n/`, `../share/stk-desktop/i18n/`, `../Resources/i18n/`), else the source tree (development
 * builds). Empty when none has zh_CN.json.
 */
std::string locate_i18n_dir(std::string_view override_dir);

struct ShellOptions {
  /** Catalog directory (see #locate_i18n_dir). */
  std::string i18n_dir;
  /** Initial language (default zh_CN). */
  std::string language = ui::Catalog::DEFAULT_LANGUAGE;
  /** Text measurer for the screens' UI (tests: ui::FakeTextMeasurer); null = BLF. */
  const ui::TextMeasurer *measurer = nullptr;
  /** Log timestamps and toasts (off for deterministic headless renders and goldens). */
  bool interactive = true;
};

/** Default window size in logical points. */
inline constexpr int kDefaultWindowWidth = 1280;
inline constexpr int kDefaultWindowHeight = 800;

class AppShell {
 public:
  explicit AppShell(ShellOptions options = {});
  ~AppShell();
  AppShell(const AppShell &) = delete;
  AppShell &operator=(const AppShell &) = delete;

  AppStore &store()
  {
    return store_;
  }
  EditorRegistry &registry()
  {
    return registry_;
  }
  const ShellOptions &options() const
  {
    return options_;
  }
  /** Catalog loading result (false: the UI shows message keys). */
  bool catalogs_loaded() const
  {
    return catalogs_loaded_;
  }
  const std::string &catalog_error() const
  {
    return catalog_error_;
  }

  /**
   * Installs the top bar, status bar, area factory, UI configuration (catalog, measurer) and
   * application shortcuts on `screen`. `window` (nullable, headless) enables the window-level
   * parts: UI scale changes, client-side decorations and quitting.
   */
  void install(wm::Screen &screen, wm::Window *window);
  /** Replaces the screen's tree with the default layout. */
  void build_default_layout(wm::Screen &screen);

  /** Screen, language, UI scale and window geometry as a layout file. */
  wm::LayoutFile capture_layout(const wm::Screen &screen, const wm::Window *window) const;
  /** Applies language and UI scale, then the screen tree; false (screen unchanged) on errors. */
  bool apply_layout(wm::Screen &screen, const wm::LayoutFile &file, std::string *r_error = nullptr);
  /**
   * Loads `path` into `screen`. A missing file returns false quietly; a corrupt one is logged,
   * moved aside (`<path>.corrupt`) and returns false. The caller then builds the default layout.
   */
  bool restore(wm::Screen &screen, const std::filesystem::path &path, bool quarantine_corrupt = true);
  bool save(const wm::Screen &screen, const wm::Window *window, const std::filesystem::path &path);

  void set_language(const std::string &language);
  /** User UI scale (applied to the window manager in GUI mode). */
  void set_ui_scale(float scale);

  /** Where File > Save layout writes (default: wm::default_layout_path()). Empty = disabled. */
  std::filesystem::path layout_path;
  /** Called by File > Quit and Ctrl+Q (GUI). */
  std::function<void()> on_quit;

  /** The window manager of the installed window (null headless). */
  wm::WindowManager *window_manager() const
  {
    return wm_;
  }

 private:
  class TopBar;
  class StatusBar;
  friend class TopBar;
  friend class StatusBar;
  bool handle_shortcut(wm::Screen &screen, const wm::Event &event);
  std::vector<ui::MenuEntry> file_menu(wm::Screen &screen);
  std::vector<ui::MenuEntry> view_menu(wm::Screen &screen);
  std::vector<ui::MenuEntry> language_menu();
  std::vector<ui::MenuEntry> scale_menu();
  void reset_layout(wm::Screen &screen);

  ShellOptions options_;
  AppStore store_;
  EditorRegistry registry_;
  bool catalogs_loaded_ = false;
  std::string catalog_error_;
  wm::WindowManager *wm_ = nullptr;
  wm::Window *window_ = nullptr;
  std::vector<wm::Screen *> screens_;
};

}  // namespace stk::app
