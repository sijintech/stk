/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * AppShell: the application frame around the editors. Owns the AppStore and the editor
 * registry, installs on a screen the top bar (app menu File / View / Language / UI scale, window
 * title and, on GNOME Wayland, the client-side window buttons), the status bar (bridge state,
 * connection, hints), the area factory and the application shortcuts, builds the default layout
 * (Files beside Viewer and Nodes/Python, with Table below and optional management/log tabs) and converts screens to and from layout files.
 *
 *   AppShell shell({.i18n_dir = locate_i18n_dir("")});
 *   shell.install(window->screen(), window);
 *   if (!shell.restore(window->screen(), layout_path)) shell.build_default_layout(window->screen());
 */
#pragma once

#include <filesystem>
#include <functional>
#include <memory>
#include <map>
#include <string>
#include <string_view>

#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/script_state.hh"
#include "stk/wm/layout_store.hh"
#include "stk/wm/screen.hh"

namespace stk::ui {
class TextMeasurer;
}
namespace stk::io {
class Payload;
}
namespace stk::wm {
class Window;
class WindowManager;
}  // namespace stk::wm

namespace stk::app {
class EditorArea;
class WorkspaceTransfer;

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
  enum class WorkMode { Preparation, Analysis };
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
  /** Stops tagging `screen` for redraw and showing toasts on it (called automatically when an
   * installed window closes; headless callers use it before destroying a screen). */
  void forget(wm::Screen &screen, wm::Window *window = nullptr);
  /** Screens the shell currently drives. */
  size_t screen_count() const
  {
    return screens_.size();
  }
  /** Whether an installed window has an active text edit. Pure inspection, without committing it. */
  bool text_input_active() const;
  /** Every live editor, including hidden tabs in other windows, agrees to change selection. */
  bool project_selection_available(std::string_view project_id) const;
  bool has_unsaved_changes() const;
  bool can_close_screen(wm::Screen *screen) const;
  bool has_screen(const wm::Screen *screen) const;
  /** Swap live Viewer/editing areas without reconstructing editors or their state. */
  bool swap_visual_editors(wm::Screen &screen);
  /** Per-window presentation preferences. Switching retains live editors and shared project,
   * Viewer and execution state; it never runs, saves or sends product work. */
  WorkMode work_mode(const wm::Screen &screen) const;
  bridge::Result<io::Json> switch_work_mode(wm::Screen *screen, WorkMode mode);
  /** Lifetime fence for callbacks retained by editors or integrations. */
  std::weak_ptr<void> lifetime() const { return alive_; }
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

  /** Activate a live editor on an installed screen without rebuilding its layout. Reuses an
   * existing tab or creates one only if capacity permits. `maximize=false` shows the split layout.
   * Both navigation operations run on the UI thread and refuse an active edit in the target
   * screen. Other windows and their input are unaffected. */
  bridge::Result<io::Json> activate_editor(wm::Screen *screen, const std::string &editor_id, bool maximize);
  bridge::Result<io::Json> restore_split_layout(wm::Screen *screen);
  /** Defer navigation from a widget. Checks screen membership before dereferencing it and again
   * after the event, and fences shell/caller lifetime. Live failures are shown as a toast. */
  void activate_editor_later(wm::Screen *screen, std::string editor_id, bool maximize,
                             std::function<bool()> valid = {});
  /** Project-scoped navigation; never executes work or replaces existing editors. Empty handle
   * is allowed only for workspace/project management. Checks all windows for active input. */
  void open_project_page_later(wm::Screen *screen, std::string page, std::string handle,
                               std::function<bool()> valid = {}, std::string table_id = {}, std::string record_id = {});
  /** Deferred: show `target` (Editor::navigate) in an `editor_id` tab of the same area while
   * `origin` is still that area's active editor, reusing such a tab or adding one. A refusing
   * editor leaves the area as it was and its reason is shown as a toast. */
  void open_in_area_later(EditorArea *area, std::weak_ptr<void> origin, std::string editor_id,
                          io::Json target, std::function<bool()> valid = {});
  /** Deferred: from the active editor `from`, activate the tab of `area` whose editor is `origin`;
   * when that tab is gone, show `fallback` in an `editor_id` tab instead. */
  void return_in_area_later(EditorArea *area, std::weak_ptr<void> from, std::weak_ptr<void> origin,
                            std::string editor_id, io::Json fallback);
  /** Deferred: activate an `editor_id` tab (as activate_editor) and show `target` in it (Editor::navigate),
   * for links from Home such as an attention item. A refusal is shown as a toast. */
  void open_target_later(wm::Screen *screen, std::string editor_id, io::Json target, std::function<bool()> valid = {});
  /** Whether `area` belongs to an installed screen (pointers held by deferred work may be stale). */
  bool has_area(const EditorArea *area) const;

  /** Defer saved-draft adoption and Review navigation into the originating screen.
   * `valid` must fence the caller's lifetime and selected request. Expired callers
   * receive no callback; live conflicts preserve all review and text input state. */
  void open_saved_review(wm::Screen *screen, std::string handle, int64_t expected_revision,
                         io::Json draft, uint64_t expected_review_generation,
                         std::function<bool()> valid, ScriptState::Completion complete);

  /** Pure preflight for importing an explicitly selected analysis output. All Viewer areas
   * share one state: an occupied Viewer or any active desktop text edit prevents adoption.
   * The returned version must still match after the payload has been read and verified. */
  bridge::Result<uint64_t> analysis_payload_target(wm::Screen *screen);
  /** Adopt an already decoded, verified payload into an empty shared Viewer. The durable run
   * keeps its provenance separately; this import never invents a submitted Viewer graph.
   * Navigation and adoption are deferred with project, caller and Viewer-version fences. */
  void open_analysis_payload(wm::Screen *screen, std::string handle, uint64_t expected_viewer_version,
                             std::shared_ptr<const io::Payload> payload, std::string label,
                             std::function<bool()> valid, ScriptState::Completion complete);

  /** Explicit portable workspace actions. Import/open never execute restored programs. */
  WorkspaceTransfer &workspace_transfer();
  io::Json capture_workspace() const;
  bool apply_workspace(const io::Json &state, std::string *error = nullptr);
  bool export_workspace(const std::string &path, ScriptState::Completion complete);
  bool import_workspace(const std::string &source, const std::string &destination,
                        const std::string &expected_sha256, ScriptState::Completion complete,
                        bool allow_incomplete = false);
  bool open_workspace(const std::string &directory, ScriptState::Completion complete,
                      bool allow_incomplete = false);

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
  void focus_viewer(wm::Screen &screen);
  void handle_ui_request(const std::string &operation, const io::Json &params, int64_t expires_at,
                         std::function<bool()> valid, ScriptState::Completion complete);
  void perform_ui_request(wm::Screen &screen, const std::string &operation, const io::Json &params,
                          ScriptState::Completion complete, std::function<bool()> valid);

  void perform_viewer_request(wm::Screen &screen, const std::string &operation, const io::Json &params,
                              ScriptState::Completion complete);

  bool receive_workspace(const std::string &method, io::Json params,
                         ScriptState::Completion complete, bool allow_incomplete);
  struct WorkspacePrepared;
  std::shared_ptr<WorkspacePrepared> prepare_workspace(const io::Json &state, std::string *error);
  bool commit_workspace(const std::shared_ptr<WorkspacePrepared> &prepared, std::string *error);
  std::unique_ptr<WorkspaceTransfer> workspace_transfer_;
  std::vector<std::unique_ptr<wm::Screen>> workspace_screens_;
  bool workspace_busy_ = false;

  ShellOptions options_;
  AppStore store_;
  EditorRegistry registry_;
  bool catalogs_loaded_ = false;
  std::string catalog_error_;
  wm::WindowManager *wm_ = nullptr;
  wm::Window *window_ = nullptr;
  std::vector<wm::Screen *> screens_;
  struct WorkModePane {
    std::string area;
    std::weak_ptr<void> editor;
    bool toolbar = true;
    bool sidebar = false;
  };
  struct WorkModeLayout {
    nlohmann::json geometry;
    std::vector<WorkModePane> panes;
  };
  struct WorkModes {
    WorkMode active = WorkMode::Analysis;
    std::map<WorkMode, WorkModeLayout> layouts;
  };
  std::map<const wm::Screen *, WorkModes> work_modes_;
  WorkModeLayout capture_work_mode(const wm::Screen &screen) const;
  WorkModeLayout adapt_work_mode(const wm::Screen &screen, const WorkModeLayout &saved) const;
  nlohmann::json capture_work_modes(const wm::Screen &screen) const;
  bool read_work_modes(const wm::Screen &screen, const nlohmann::json &layout,
                       WorkModes &modes, std::string *error) const;
  /** Expires with the shell: close listeners of windows that outlive it do nothing. */
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
};

}  // namespace stk::app
