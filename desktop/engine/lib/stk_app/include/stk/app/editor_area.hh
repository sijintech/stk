/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * EditorArea: a screen area showing editors in tabs. Regions:
 *   header  (top)   editor-type dropdown, tabs (when more than one), editor header widgets and the
 *                   area menu (split, join, maximize, toolbar / sidebar, tabs; right-click too)
 *   toolbar (left)  when the active editor has one; T toggles, resizable
 *   sidebar (right) when the active editor has one; N toggles, resizable (Blender's N-panel)
 *   main    (fill)  the active editor's content (and its GPU drawing)
 * Keys over the area: T / N toggle the side regions, Ctrl+PageUp / Ctrl+PageDown switch tabs,
 * the rest goes to the editor. Its state (tabs with their editor state, side-region preference)
 * is saved with the layout.
 */
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "stk/app/editor.hh"
#include "stk/wm/screen.hh"

namespace stk::app {

class AppShell;

class EditorArea : public wm::Area {
 public:
  /** An area with one tab of editor `type`. */
  EditorArea(AppShell &shell, const std::string &type);
  ~EditorArea() override;

  AppShell &shell() const
  {
    return shell_;
  }
  int tab_count() const
  {
    return int(tabs_.size());
  }
  int active_tab() const
  {
    return active_;
  }
  Editor &editor() const
  {
    return *tabs_[size_t(active_)];
  }
  Editor &tab(int i) const
  {
    return *tabs_[size_t(i)];
  }
  void set_active_tab(int index);
  /** Replaces the editor of tab `index` with a new one of `type` (false: unknown type). */
  bool set_tab_type(int index, const std::string &type);
  /** Appends a tab (false: unknown type). */
  bool add_tab(const std::string &type, bool activate = true);
  void close_tab(int index);
  /** Replaces all tabs (types must be registered; false leaves the area unchanged). */
  bool set_tabs(const std::vector<std::string> &types, int active);

  bool toolbar_open() const
  {
    return toolbar_open_;
  }
  bool sidebar_open() const
  {
    return sidebar_open_;
  }
  void set_toolbar_open(bool open);
  void set_sidebar_open(bool open);

  /** Entries of the area menu (also shown on right-click in the header). */
  std::vector<ui::MenuEntry> area_menu(const wm::DrawContext *draw);
  /** Key of the area-menu button (for ui::Context::open_popup). */
  std::string area_menu_key() const;

  EditorContext context(ui::Context *ui, const wm::DrawContext *draw);

  /* wm::Area hooks. */
  bool on_drop(const wm::Event &event) override;
  bool handle_event(const wm::Event &event, const wm::DrawContext &ctx) override;
  nlohmann::json save_state() const override;
  bool load_state(const nlohmann::json &state) override;

  /** Region names. */
  static constexpr const char *kHeader = "header";
  static constexpr const char *kToolbar = "toolbar";
  static constexpr const char *kSidebar = "sidebar";
  static constexpr const char *kMain = "main";

 private:
  friend class EditorRegion;
  void sync_regions();
  void build_header(ui::Layout &row, EditorContext &ctx);

  AppShell &shell_;
  std::vector<std::unique_ptr<Editor>> tabs_;
  int active_ = 0;
  bool toolbar_open_ = true;
  bool sidebar_open_ = true;
};

}  // namespace stk::app
