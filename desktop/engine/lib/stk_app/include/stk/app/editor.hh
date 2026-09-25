/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Editors: the content types an area can show (Jobs, Viewer, Properties, Logs, Probe, Transfers,
 * Bridge log). An #Editor instance belongs to one tab of one area (EditorArea) and keeps that
 * area's per-editor state; shared data lives in the AppStore. Every frame the area's regions call
 * the draw_* hooks to build their stk_ui layouts (immediate-mode style: read state, bind widgets
 * with closures). Editors add header widgets, area-menu entries and shortcuts through hooks, and
 * receive file drops and GPU drawing for their main region.
 *
 * #register_builtin_editors registers the D1 editors (WP9: Jobs, Transfers, Logs, Bridge log;
 * WP10: Viewer, Properties, Probe) under the ids WP3 layouts were saved with. A new editor
 * subclasses #Editor and registers an #EditorType.
 */
#pragma once

#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include "stk/ui/ui.hh"
#include "stk/wm/event.hh"
#include "stk/wm/screen.hh"

namespace stk::app {

class AppStore;
class EditorArea;
class Editor;

/** What an editor hook can reach. `ui` and `draw` are null outside a frame (e.g. on_drop). */
struct EditorContext {
  AppStore &store;
  EditorArea &area;
  ui::Context *ui = nullptr;
  const wm::DrawContext *draw = nullptr;

  std::string_view tr(std::string_view key) const;
  /** Runs `fn` after the current event (structural changes; see wm::Screen::defer). */
  void defer(std::function<void()> fn) const;
};

struct EditorType {
  /** Stable id stored in layouts ("jobs", "viewer", ...). */
  std::string id;
  /** Catalog key of the display name ("editor.jobs.title"). */
  std::string title_key;
  std::function<std::unique_ptr<Editor>(const EditorType &type)> create;
};

class Editor {
 public:
  explicit Editor(const EditorType &type) : type_(&type) {}
  virtual ~Editor() = default;
  Editor(const Editor &) = delete;
  Editor &operator=(const Editor &) = delete;

  const EditorType &type() const
  {
    return *type_;
  }

  /* ---- Regions ---- */

  /** Main region content (root layout of the region's block). */
  virtual void draw_main(ui::Layout &layout, EditorContext &ctx) = 0;
  /** Optional left toolbar (collapsible with T). */
  virtual bool has_toolbar() const
  {
    return false;
  }
  virtual void draw_toolbar(ui::Layout &layout, EditorContext &ctx) {}
  /** Optional right sidebar / N-panel (collapsible with N, resizable). */
  virtual bool has_sidebar() const
  {
    return false;
  }
  virtual void draw_sidebar(ui::Layout &layout, EditorContext &ctx) {}
  /** Editor-specific header widgets, placed after the editor-type dropdown and the tabs. */
  virtual void draw_header(ui::Layout &row, EditorContext &ctx) {}
  /** Main region background (alpha 0 = transparent, e.g. over #draw_gpu content). */
  virtual ui::Color main_background(const ui::Theme &theme) const;

  /* ---- GPU content (viewer) ---- */

  /** Draws under the main region's UI; pixel space at the region, viewport = the region. */
  virtual bool draws_gpu() const
  {
    return false;
  }
  virtual void draw_gpu(EditorContext &ctx) {}
  /** Pointer events over the main region that no widget took (navigation, picking). */
  virtual bool handle_gpu_event(const wm::Event &event, EditorContext &ctx)
  {
    return false;
  }

  /* ---- Menus, shortcuts, drops ---- */

  /** Entries appended to the area menu (header "Area" button / right-click on the header). */
  virtual void menu_entries(std::vector<ui::MenuEntry> &entries, EditorContext &ctx) {}
  /** Key events over the area that the UI did not consume. */
  virtual bool on_key(const wm::Event &event, EditorContext &ctx)
  {
    return false;
  }
  /** Files dropped on the area (absolute paths). False lets the area report "not handled". */
  virtual bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx)
  {
    return false;
  }

  /* ---- Persistence ---- */

  /** Per-area editor state saved with the layout (JSON object). */
  virtual nlohmann::json save_state() const
  {
    return nlohmann::json::object();
  }
  /** False rejects the saved layout (the application falls back to the default layout). */
  virtual bool load_state(const nlohmann::json &state)
  {
    return true;
  }

 private:
  const EditorType *type_;
};

class EditorRegistry {
 public:
  /** Adds or replaces (same id) an editor type. Types keep their registration order. */
  void add(EditorType type);
  const EditorType *find(std::string_view id) const;
  const std::vector<std::unique_ptr<EditorType>> &types() const
  {
    return types_;
  }
  int index_of(std::string_view id) const;
  std::unique_ptr<Editor> create(std::string_view id) const;

 private:
  std::vector<std::unique_ptr<EditorType>> types_;
};

/** The D1 editor ids in menu order. */
inline constexpr const char *kEditorJobs = "jobs";
inline constexpr const char *kEditorViewer = "viewer";
inline constexpr const char *kEditorProperties = "properties";
inline constexpr const char *kEditorLogs = "logs";
inline constexpr const char *kEditorProbe = "probe";
inline constexpr const char *kEditorTransfers = "transfers";
inline constexpr const char *kEditorBridgeLog = "bridge_log";

/** Registers the D1 editors for all seven ids. */
void register_builtin_editors(EditorRegistry &registry);

}  // namespace stk::app
