/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/shell.hh"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>

#include "stk/app/editor_area.hh"
#include "stk/app/project_attention.hh"
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/app/workspace_transfer.hh"
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

void AppShell::focus_viewer(wm::Screen &screen)
{
  const auto result = activate_editor(&screen, kEditorViewer, false);
  if (!result && store_.toast) { store_.toast(result.error().message, ui::ToastKind::Warning); }
}

bridge::Result<io::Json> AppShell::activate_editor(wm::Screen *screen, const std::string &editor_id,
                                                const bool maximize)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (!screen || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) {
    return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.closed")));
  }
  if (!registry_.find(editor_id)) {
    return Error::make(ErrorCode::InvalidParams,
        store_.catalog().format("app.focus.unknown_editor", {{"editor", editor_id}}));
  }
  if (screen->ui() && screen->ui()->text_input_active()) {
    return Error::make(ErrorCode::Busy, std::string(store_.tr("app.focus.busy")));
  }

  struct MaximizeRollback {
    wm::Screen &screen;
    wm::Area *original;
    bool committed = false;
    ~MaximizeRollback() { if (!committed) { screen.set_maximized(original); } }
  } rollback{*screen, screen->maximized()};
  if (!maximize) { screen->set_maximized(nullptr); }
  EditorArea *destination = dynamic_cast<EditorArea *>(rollback.original);
  int tab_index = -1;
  if (destination && destination->editor().type().id == editor_id) {
    tab_index = destination->active_tab();
  }
  else {
    destination = nullptr;
    // Active matching tabs take precedence over hidden tabs. Distinct AI editors
    // keep distinct unsent drafts, so repeated focus must preserve the visible one.
    for (auto *area : screen->areas()) {
      auto *editor = dynamic_cast<EditorArea *>(area);
      if (editor && editor->editor().type().id == editor_id) {
        destination = editor;
        tab_index = editor->active_tab();
        break;
      }
    }
  }
  if (!destination) {
    for (auto *area : screen->areas()) {
      auto *editor = dynamic_cast<EditorArea *>(area);
      if (!editor) { continue; }
      for (int i = 0; i < editor->tab_count(); ++i) {
        if (editor->tab(i).type().id == editor_id) {
          destination = editor;
          tab_index = i;
          break;
        }
      }
      if (destination) { break; }
    }
  }
  // Old layouts may place a Python/analysis tab beside the only Viewer tab in one area.
  // Reveal that existing instance elsewhere, retaining its drafts and the live Viewer.
  if (!maximize && editor_id != kEditorViewer && destination && destination->editor().type().id == kEditorViewer) {
    auto *origin = destination;
    EditorArea *editing = nullptr;
    for (auto *base : screen->areas()) {
      auto *area = dynamic_cast<EditorArea *>(base);
      if (!area || area == origin || area->editor().type().id == kEditorViewer || area->tab_count() >= 16) { continue; }
      const auto &current = area->editor().type().id;
      if (!editing || current == kEditorAnalysisGraph || current == kEditorPython || current == kEditorWorkspace) {
        editing = area;
      }
    }
    bool temporary = false;
    if (!editing) {
      try {
        editing = dynamic_cast<EditorArea *>(screen->split(*origin, wm::SplitDir::Horizontal, 0.5f, false, kEditorViewer));
      }
      catch (const std::exception &) { /* The original tabs have not been moved. */ }
      temporary = editing != nullptr;
    }
    if (!editing || (temporary && editing->has_unsaved_changes()) || !origin->move_tab_to(tab_index, *editing)) {
      if (temporary) { screen->join(*origin, *editing); }
      return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.open_failed")));
    }
    // Explicit split created a clean placeholder, never a copy of the hidden draft.
    if (temporary) { editing->close_tab(0); }
    destination = editing;
    tab_index = editing->active_tab();
  }
  if (!destination) {
    for (auto *area : screen->areas()) {
      auto *editor = dynamic_cast<EditorArea *>(area);
      if (!editor || editor->tab_count() >= 16) { continue; }
      const auto &current = editor->editor().type().id;
      if (editor_id != kEditorViewer && current == kEditorViewer) { continue; }
      if (!destination || current == kEditorAnalysisGraph || current == kEditorPython || current == kEditorWorkspace) {
        destination = editor;
      }
    }
  }
  // A one-area restored layout can still open another editor without losing its live Viewer.
  if (!destination && editor_id != kEditorViewer && screen->areas().size() == 1) {
    for (auto *base : screen->areas()) {
      auto *area = dynamic_cast<EditorArea *>(base);
      if (area && area->editor().type().id == kEditorViewer && !screen->maximized()) {
        try {
          destination = dynamic_cast<EditorArea *>(screen->split(*area, wm::SplitDir::Horizontal, 0.5f, false, editor_id));
        }
        catch (const std::exception &) {
          return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.open_failed")));
        }
        if (destination) {
          const bool opened = destination->editor().type().id == editor_id;
          if (!opened) {
            screen->join(*area, *destination);
            return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.open_failed")));
          }
          tab_index = 0;
          break;
        }
      }
    }
  }
  if (!destination) {
    return Error::make(ErrorCode::Busy, std::string(store_.tr("app.focus.no_capacity")));
  }
  if (tab_index < 0) {
    // No existing tab changes until the new editor has been constructed successfully.
    try {
      if (!destination->add_tab(editor_id, false)) {
        return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.open_failed")));
      }
    }
    catch (const std::exception &) {
      return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.open_failed")));
    }
    tab_index = destination->tab_count() - 1;
  }
  destination->set_active_tab(tab_index);
  screen->set_maximized(maximize ? destination : nullptr);
  rollback.committed = true;
  store_.changed();
  return io::Json{{"area_id", destination->id()}, {"editor_id", editor_id},
                  {"tab_index", tab_index}, {"maximized", maximize}};
}

bridge::Result<io::Json> AppShell::restore_split_layout(wm::Screen *screen)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (!screen || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) {
    return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.closed")));
  }
  if (screen->ui() && screen->ui()->text_input_active()) {
    return Error::make(ErrorCode::Busy, std::string(store_.tr("app.focus.busy")));
  }
  const bool restored = screen->maximized() != nullptr;
  if (restored) { screen->set_maximized(nullptr); store_.changed(); }
  return io::Json{{"restored", restored}};
}

void AppShell::activate_editor_later(wm::Screen *screen, std::string editor_id, const bool maximize,
                                     std::function<bool()> valid)
{
  if (!screen || (valid && !valid()) || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) { return; }
  const std::weak_ptr<bool> weak = alive_;
  screen->defer([this, weak, screen, editor_id = std::move(editor_id), maximize, valid = std::move(valid)] {
    if (!weak.lock() || (valid && !valid()) || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) { return; }
    const auto result = activate_editor(screen, editor_id, maximize);
    if (!result && store_.toast) { store_.toast(result.error().message, ui::ToastKind::Warning); }
  });
}

void AppShell::open_project_page_later(wm::Screen *screen, std::string page, std::string handle,
                                      std::function<bool()> valid, std::string table_id, std::string record_id)
{
  if (!screen || (valid && !valid()) || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) { return; }
  const std::weak_ptr<bool> weak = alive_;
  screen->defer([this, weak, screen, page = std::move(page), handle = std::move(handle), valid = std::move(valid),
                 table_id = std::move(table_id), record_id = std::move(record_id)] {
    if (!weak.lock() || (valid && !valid()) || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) { return; }
    auto &project = store_.project();
    project.sync();
    if ((project.project() ? project.project()->handle : std::string()) != handle) { return; }
    const bool management = page == "project" || page == "workspace";
    if (!management && (!project.loaded() || !project.ready() || project.busy())) { return; }
    if (text_input_active()) {
      if (store_.toast) { store_.toast(std::string(store_.tr("app.focus.busy")), ui::ToastKind::Warning); }
      return;
    }
    const char *editor = nullptr;
    std::string view;
    if (page == "workspace") { editor = kEditorWorkspace; }
    else if (page == "conversation") { editor = kEditorAI; }
    else if (page == "data") { editor = kEditorTable; view = "data"; }
    else if (page == "files") { editor = kEditorFiles; }
    else if (page == "project" || page == "simulation_runs" || page == "review") {
      editor = kEditorProject;
      view = page == "files" ? "files" : page == "simulation_runs" ? "runs" : page == "project" ? "location" :
          page == "review" ? "review" : "data";
    }
    else if (page == "analyses" || page == "analysis_runs") {
      editor = kEditorAnalysisGraph;
      view = page == "analyses" ? "saved" : "runs";
    }
    else if (page == "workflows") { editor = kEditorWorkflow; }
    else { return; }
    // Files select the file index table; the data page may name a table to select (a workflow step).
    const auto file_table = page == "data" ? table_id : std::string();
    // A search result may also name its row (in the data table or the file index).
    const auto record = file_table.empty() ? std::string() : record_id;
    if ((!file_table.empty() && file_table != project.table_id()) || (!record.empty() && record != project.record_id())) {
      for (const auto *target : screens_) {
        for (const auto *base : target->areas()) {
          const auto *area = dynamic_cast<const EditorArea *>(base);
          if (!area) { continue; }
          for (int i = 0; i < area->tab_count(); ++i) {
            if (!area->tab(i).can_change_project_selection(project.project()->id)) {
              if (store_.toast) { store_.toast(std::string(store_.tr("workspace.selection_busy")), ui::ToastKind::Warning); }
              return;
            }
          }
        }
      }
    }
    const auto result = activate_editor(screen, editor, false);
    if (!result) {
      if (store_.toast) { store_.toast(result.error().message, ui::ToastKind::Warning); }
      return;
    }
    auto *area = dynamic_cast<EditorArea *>(screen->find_area(io::get_string(result.value(), "area_id")));
    if (!area) { return; }
    if (!view.empty()) { area->editor().show_view(view); }
    if (page == "files" && !record_id.empty()) {
      std::string reason;
      area->editor().navigate({{"record_id", record_id}, {"project_handle", project.project()->handle},
                               {"expected_revision", project.project()->revision}}, {}, reason);
    }
    if (!file_table.empty()) { project.select_table(file_table); }
    if (!record.empty()) { project.select_record(record); }
    if (page == "analyses" || page == "analysis_runs" || page == "workflows") { area->set_sidebar_open(true); }
    store_.changed();
  });
}

namespace {
int area_tab(const EditorArea &area, const std::weak_ptr<void> &editor)
{
  const auto live = editor.lock();
  for (int i = 0; live && i < area.tab_count(); ++i) {
    if (area.tab(i).lifetime().lock() == live) { return i; }
  }
  return -1;
}
}  // namespace

bool AppShell::has_area(const EditorArea *area) const
{
  for (const auto *screen : screens_) {
    for (const auto *base : screen->areas()) {
      if (base == area) { return true; }
    }
  }
  return false;
}

void AppShell::open_target_later(wm::Screen *screen, std::string editor_id, io::Json target, std::function<bool()> valid)
{
  if (!screen || (valid && !valid()) || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) { return; }
  const std::weak_ptr<bool> weak = alive_;
  screen->defer([this, weak, screen, editor_id = std::move(editor_id), target = std::move(target), valid = std::move(valid)] {
    if (!weak.lock() || (valid && !valid()) || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) { return; }
    if (text_input_active()) {
      if (store_.toast) { store_.toast(std::string(store_.tr("app.focus.busy")), ui::ToastKind::Warning); }
      return;
    }
    const auto result = activate_editor(screen, editor_id, false);
    if (!result) {
      if (store_.toast) { store_.toast(result.error().message, ui::ToastKind::Warning); }
      return;
    }
    auto *area = dynamic_cast<EditorArea *>(screen->find_area(io::get_string(result.value(), "area_id")));
    if (!area) { return; }
    std::string reason;
    if (!area->editor().navigate(target, {}, reason) && store_.toast) {
      store_.toast(std::string(store_.tr(reason.empty() ? "app.navigate.refused" : reason)), ui::ToastKind::Warning);
    }
    area->set_sidebar_open(true);
    store_.changed();
  });
}

void AppShell::open_in_area_later(EditorArea *area, std::weak_ptr<void> origin, std::string editor_id, io::Json target,
                                 std::function<bool()> valid)
{
  if (!area || !has_area(area) || !area->screen() || (valid && !valid())) { return; }
  const std::weak_ptr<bool> weak = alive_;
  area->screen()->defer([this, weak, area, origin = std::move(origin), editor_id = std::move(editor_id),
                         target = std::move(target), valid = std::move(valid)] {
    if (!weak.lock() || !has_area(area) || origin.expired() || (valid && !valid()) ||
        area_tab(*area, origin) != area->active_tab()) { return; }
    if (text_input_active()) {
      if (store_.toast) { store_.toast(std::string(store_.tr("app.focus.busy")), ui::ToastKind::Warning); }
      return;
    }
    int index = -1;
    for (int i = 0; i < area->tab_count() && index < 0; ++i) {
      if (area->tab(i).type().id == editor_id) { index = i; }
    }
    const bool added = index < 0;
    if (added) {
      if (!area->add_tab(editor_id, false)) {
        if (store_.toast) { store_.toast(std::string(store_.tr("app.tabs.full")), ui::ToastKind::Warning); }
        return;
      }
      index = area->tab_count() - 1;
    }
    std::string reason;
    if (!area->tab(index).navigate(target, origin, reason)) {
      if (added) { area->close_tab(index); }
      if (store_.toast) {
        store_.toast(std::string(store_.tr(reason.empty() ? "app.navigate.refused" : reason)), ui::ToastKind::Warning);
      }
      return;
    }
    area->set_active_tab(index);
    area->set_sidebar_open(true);
    store_.changed();
  });
}

void AppShell::return_in_area_later(EditorArea *area, std::weak_ptr<void> from, std::weak_ptr<void> origin,
                                    std::string editor_id, io::Json fallback)
{
  if (!area || !has_area(area) || !area->screen()) { return; }
  const std::weak_ptr<bool> weak = alive_;
  area->screen()->defer([this, weak, area, from = std::move(from), origin = std::move(origin),
                         editor_id = std::move(editor_id), fallback = std::move(fallback)] {
    if (!weak.lock() || !has_area(area) || from.expired() || area_tab(*area, from) != area->active_tab()) { return; }
    if (const int index = area_tab(*area, origin); index >= 0) {
      area->set_active_tab(index);
      store_.changed();
      return;
    }
    open_in_area_later(area, from, editor_id, fallback);
  });
}

void AppShell::open_saved_review(wm::Screen *screen, std::string handle, const int64_t expected_revision,
                                 io::Json draft, const uint64_t expected_review_generation,
                                 std::function<bool()> valid, ScriptState::Completion complete)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (!valid || !valid() || !complete) { return; }
  if (!screen || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) {
    complete(Error::make(ErrorCode::Unavailable, "The target desktop screen was closed"));
    return;
  }
  std::weak_ptr<bool> weak = alive_;
  screen->defer([this, weak, screen, handle = std::move(handle), expected_revision,
                 draft = std::move(draft), expected_review_generation,
                 valid = std::move(valid), complete = std::move(complete)]() mutable {
    if (!weak.lock() || !valid()) { return; }
    if (std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) {
      complete(Error::make(ErrorCode::Unavailable, "The target desktop screen was closed"));
      return;
    }
    auto &project = store_.project();
    project.sync();
    if (project.review_generation() != expected_review_generation) {
      complete(Error::make(ErrorCode::Conflict, "The review changed before the saved draft could be opened"));
      return;
    }
    for (auto *target : screens_) {
      if (target->ui() && target->ui()->text_input_active()) {
        complete(Error::make(ErrorCode::Busy, "Finish the current desktop text edit before opening a review"));
        return;
      }
    }
    // Preselect the exact destination. A full area must not hide another area's
    // available slot, and a completely full layout must not consume the draft.
    EditorArea *destination = nullptr;
    int project_tab = -1;
    for (auto *area : screen->areas()) {
      auto *editor = dynamic_cast<EditorArea *>(area);
      if (!editor) { continue; }
      for (int i = 0; i < editor->tab_count(); ++i) {
        if (editor->tab(i).type().id == kEditorProject) {
          destination = editor;
          project_tab = i;
          break;
        }
      }
      if (project_tab >= 0) { break; }
      // EditorArea::add_tab enforces this same 16-tab limit.
      if (editor->tab_count() < 16 &&
          (!destination || destination->editor().type().id == kEditorPython)) {
        destination = editor;
      }
    }
    if (!destination || !registry_.find(kEditorProject)) {
      complete(Error::make(ErrorCode::Unavailable, "The target desktop has no available project editor tab"));
      return;
    }
    auto result = project.request_saved_review(handle, expected_revision, draft);
    if (result.ok()) {
      const auto opened = activate_editor(screen, kEditorProject, false);
      if (!opened) {
        // A failed editor factory must not leave an adopted but invisible review.
        // Adoption required an empty review, so restore that state without touching
        // the durable draft. Normal capacity failures were rejected before adoption.
        project.discard_review();
        complete(opened.error());
        return;
      }
      if (auto *area = dynamic_cast<EditorArea *>(screen->find_area(io::get_string(opened.value(), "area_id")))) {
        area->editor().show_view("review");
      }
    }
    complete(std::move(result));
  });
}

bool AppShell::text_input_active() const
{
  return std::any_of(screens_.begin(), screens_.end(), [](const auto *screen) {
    return screen->ui() && screen->ui()->text_input_active();
  });
}

bool AppShell::project_selection_available(const std::string_view project_id) const
{
  for (const auto *screen : screens_) {
    for (const auto *base : screen->areas()) {
      const auto *area = dynamic_cast<const EditorArea *>(base);
      if (!area) { continue; }
      for (int i = 0; i < area->tab_count(); ++i) {
        if (!area->tab(i).can_change_project_selection(project_id)) { return false; }
      }
    }
  }
  return true;
}

bool AppShell::has_unsaved_changes() const
{
  for (const auto *screen : screens_) {
    for (const auto *base : screen->areas()) {
      const auto *area = dynamic_cast<const EditorArea *>(base);
      if (area && area->has_unsaved_changes()) { return true; }
    }
  }
  return false;
}

bool AppShell::can_close_screen(wm::Screen *screen) const
{
  if (!screen || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) { return true; }
  if (workspace_busy_) { return false; }
  if (screen->ui() && screen->ui()->text_input_active()) { return false; }
  for (const auto *base : screen->areas()) {
    const auto *area = dynamic_cast<const EditorArea *>(base);
    if (area && area->has_unsaved_changes()) { return false; }
  }
  return true;
}

bool AppShell::has_screen(const wm::Screen *screen) const
{
  return std::find(screens_.begin(), screens_.end(), screen) != screens_.end();
}

bool AppShell::swap_visual_editors(wm::Screen &screen)
{
  if (std::find(screens_.begin(), screens_.end(), &screen) == screens_.end() || text_input_active()) { return false; }
  EditorArea *viewer = nullptr, *editing = nullptr;
  for (auto *base : screen.areas()) {
    auto *area = dynamic_cast<EditorArea *>(base);
    if (!area) { continue; }
    const auto &id = area->editor().type().id;
    if (id == kEditorViewer && !viewer) { viewer = area; }
    if ((id == kEditorAnalysisGraph || id == kEditorPython || id == kEditorWorkflow) && !editing) { editing = area; }
  }
  if (!viewer || !editing || !screen.swap_areas(*viewer, *editing)) { return false; }
  store_.changed();
  return true;
}

bridge::Result<uint64_t> AppShell::analysis_payload_target(wm::Screen *screen)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (!screen || std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) {
    return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.closed")));
  }
  for (auto *target : screens_) {
    if (target->ui() && target->ui()->text_input_active()) {
      return Error::make(ErrorCode::Busy, std::string(store_.tr("analysis_runs.finish_input")));
    }
  }
  auto &viewer = store_.viewer();
  if (viewer.source().kind != SourceKind::None || viewer.base_payload() || viewer.evaluating() ||
      store_.has_open_result()) {
    return Error::make(ErrorCode::Busy, std::string(store_.tr("analysis_runs.viewer_occupied")));
  }
  bool available = false;
  for (auto *area : screen->areas()) {
    auto *editor = dynamic_cast<EditorArea *>(area);
    if (!editor) { continue; }
    if (editor->tab_count() < 16) { available = true; }
    for (int i = 0; i < editor->tab_count(); ++i) {
      if (editor->tab(i).type().id == kEditorViewer) { available = true; }
    }
  }
  if (!available || !registry_.find(kEditorViewer)) {
    return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.no_capacity")));
  }
  return viewer.version();
}

void AppShell::open_analysis_payload(wm::Screen *screen, std::string handle,
                                     const uint64_t expected_viewer_version,
                                     std::shared_ptr<const io::Payload> payload, std::string label,
                                     std::function<bool()> valid, ScriptState::Completion complete)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (!valid || !valid() || !complete) { return; }
  const auto preflight = analysis_payload_target(screen);
  if (!preflight) { complete(preflight.error()); return; }
  if (!payload) {
    complete(Error::make(ErrorCode::InvalidParams, std::string(store_.tr("analysis_runs.no_payload"))));
    return;
  }
  const std::weak_ptr<bool> weak = alive_;
  screen->defer([this, weak, screen, handle = std::move(handle), expected_viewer_version,
                 payload = std::move(payload), label = std::move(label),
                 valid = std::move(valid), complete = std::move(complete)]() mutable {
    if (!weak.lock() || !valid()) { return; }
    const auto target = analysis_payload_target(screen);
    if (!target) { complete(target.error()); return; }
    auto &project = store_.project();
    project.sync();
    if (!project.project() || project.project()->handle != handle || target.value() != expected_viewer_version) {
      complete(Error::make(ErrorCode::Conflict, std::string(store_.tr("analysis_runs.target_changed"))));
      return;
    }
    // Capacity and input were checked before navigation. Factory failures leave the empty
    // Viewer unchanged; after successful activation, adoption cannot call the bridge.
    const auto activated = activate_editor(screen, kEditorViewer, false);
    if (!activated) { complete(activated.error()); return; }
    store_.viewer().open_payload(std::move(payload), std::move(label));
    complete(activated.value());
  });
}

class AppShell::TopBar final : public wm::Region {
 public:
  TopBar(AppShell &shell, wm::Screen &screen) : Region("topbar"), shell_(shell), screen_(screen)
  {
    persistent = false;
  }

  void build_ui(ui::Context &ui, const wm::DrawContext &ctx) override
  {
    if (shell_.store_.has_open_result()) {
      AppShell *shell = &shell_;
      wm::Screen *screen = &screen_;
      std::weak_ptr<bool> weak = shell_.alive_;
      screen_.defer([shell, screen, weak]() {
        if (!weak.lock() || std::find(shell->screens_.begin(), shell->screens_.end(), screen) == shell->screens_.end()) { return; }
        if (auto request = shell->store_.take_open_result()) {
          shell->store_.viewer().open(*request);
          shell->focus_viewer(*screen);
        }
      });
    }
    shell_.workspace_transfer().draw(ui, &screen_);
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
    // Primary editors are visible actions, rather than destinations inside nested menus.
    for (const auto &item : std::vector<std::pair<const char *, const char *>>{
             {kEditorFiles, "app.tool.files"}, {kEditorAnalysisGraph, "app.tool.nodes"},
             {kEditorTable, "app.tool.table"}, {kEditorPython, "app.tool.python"}}) {
      const std::string key = std::string("tool_") + item.first;
      const std::string id = item.first;
      const auto label = shell_.store_.tr(item.second);
      row.button(key, label, [shell = &shell_, screen = &screen_, weak = shell_.lifetime(), id] {
        if (!weak.expired()) { shell->activate_editor_later(screen, id, false); }
      }).width(fit_units(ui, label, 2.0f));
    }
    const auto swap_label = shell_.store_.tr("app.tool.swap");
    row.button("tool_swap", swap_label, [shell = &shell_, screen = &screen_, weak = shell_.lifetime()] {
      if (weak.expired() || !shell->has_screen(screen)) { return; }
      screen->defer([shell, screen, weak] {
        if (!weak.expired() && shell->has_screen(screen)) { shell->swap_visual_editors(*screen); }
      });
    }).width(fit_units(ui, swap_label, 2.0f)).disable(screen_.maximized() != nullptr);
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
    // Unviewed items that need a person (Home lists them); a click opens Home.
    auto &attention = store.attention();
    attention.sync();
    if (attention.polling() && !attention.wake_scheduled) {
      if (auto *wm = shell_.window_manager()) {
        attention.wake_scheduled = true;
        auto *app = &store;
        wm->add_timer(ProjectAttention::kPollMs + 50, 0, [app] { app->attention().wake_scheduled = false; app->changed(); });
      }
    }
    if (const auto count = attention.needs_you(); count > 0) {
      const auto text = store.catalog().format("app.status.attention", {{"count", std::to_string(count)}});
      auto *shell = &shell_;
      auto *screen = &screen_;
      row.button("status_attention", text, [shell, screen] { shell->activate_editor_later(screen, kEditorWorkspace, false); })
          .width(fit_units(ui, text) + 1).tip(store.tr("app.status.attention.tip"));
    }
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
  std::weak_ptr<bool> weak = alive_;
  store_.scripts().set_ui_handler([this, weak](const auto &operation, const auto &params,
                                              const int64_t expires_at, auto valid, auto complete) {
    if (weak.lock()) {
      handle_ui_request(operation, params, expires_at, std::move(valid), std::move(complete));
    }
  });
  store_.project().set_selection_guard([this, weak] {
    if (!weak.lock()) { return false; }
    const auto &project = store_.project().project();
    return !project || project_selection_available(project->id);
  });
}

AppShell::~AppShell()
{
  alive_.reset();
  workspace_transfer_.reset();
  store_.on_change = nullptr;
  store_.toast = nullptr;
  for (const auto &screen : workspace_screens_) { std::erase(screens_, screen.get()); }
  workspace_screens_.clear();
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
    window->can_close = [this, alive, s = &screen] {
      if (!alive.lock() || can_close_screen(s)) { return true; }
      if (store_.toast) { store_.toast(std::string(store_.tr("app.unsaved")), ui::ToastKind::Warning); }
      return false;
    };
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
  if (!can_close_screen(&screen) || text_input_active()) {
    if (store_.toast) { store_.toast(std::string(store_.tr("app.unsaved")), ui::ToastKind::Warning); }
    return;
  }
  /* Ready-to-use editors, with optional project management and logs available as peer tabs.
   * Area IDs remain stable for old layouts; changing editor never reopens data or starts work. */
  const nlohmann::json top = {
      {"factor", 0.70},
      {"split", "horizontal"},
      {"children",
       {leaf_json("a2", {kEditorViewer}, 0.52),
        leaf_json("a3", {kEditorAnalysisGraph, kEditorPython, kEditorWorkflow, kEditorProperties}, 0.48)}}};
  const nlohmann::json work = {
      {"factor", 0.82}, {"split", "vertical"},
      {"children", {top, leaf_json("a4", {kEditorTable, kEditorLogs, kEditorProbe, kEditorTransfers, kEditorBridgeLog}, 0.30)}}};
  const nlohmann::json layout = {
      {"maximized", nullptr},
      {"root",
       {{"factor", 1.0},
        {"split", "horizontal"},
        {"children", {leaf_json("a1", {kEditorFiles, kEditorWorkspace, kEditorJobs, kEditorProject, kEditorSkills}, 0.18), work}}}}};
  std::string err;
  if (!screen.from_json(layout, &err)) {
    /* Only reachable when an editor type was unregistered: fall back to one area. */
    std::fprintf(stderr, "stk-desktop: default layout: %s\n", err.c_str());
    screen.set_root(std::make_unique<EditorArea>(*this, kEditorJobs));
  }
  // Both the Viewer and node canvas stay usable at the initial window width. Inspectors are
  // available with N, and also as their own editor type, without taking half of each pane.
  for (auto *base : screen.areas()) {
    if (auto *area = dynamic_cast<EditorArea *>(base)) { area->set_sidebar_open(false); }
  }
}

void AppShell::reset_layout(wm::Screen &screen)
{
  if (!can_close_screen(&screen) || text_input_active()) {
    if (store_.toast) { store_.toast(std::string(store_.tr("app.unsaved")), ui::ToastKind::Warning); }
    return;
  }
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
  if (!can_close_screen(&screen) || text_input_active()) {
    if (r_error) { *r_error = std::string(store_.tr("app.unsaved")); }
    return false;
  }
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
  if (!can_close_screen(&screen) || text_input_active()) {
    if (store_.toast) { store_.toast(std::string(store_.tr("app.unsaved")), ui::ToastKind::Warning); }
    return false;
  }
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
  const auto shell_lifetime = lifetime();
  auto show_editor = [this, s, shell_lifetime](const std::string &type) {
    if (!shell_lifetime.expired()) { activate_editor_later(s, type, false); }
  };
  const std::weak_ptr<bool> weak = alive_;
  m.push_back({std::string(store_.tr("editor.workspace.title")), [this, weak, s] {
    if (weak.lock()) { activate_editor_later(s, kEditorWorkspace, false); }
  }});
  m.push_back({std::string(store_.tr("editor.skills.title")), [this, weak, s] {
    if (weak.lock()) { activate_editor_later(s, kEditorSkills, false); }
  }});
  m.push_back({std::string(store_.tr("editor.ai.title")), [show_editor] { show_editor(kEditorAI); }});
  m.push_back({std::string(store_.tr("editor.project.title")), [show_editor] { show_editor(kEditorProject); }});
  m.push_back({std::string(store_.tr("editor.table.title")), [show_editor] { show_editor(kEditorTable); }});
  m.push_back({std::string(store_.tr("editor.files.title")), [show_editor] { show_editor(kEditorFiles); }});
  m.push_back({std::string(store_.tr("editor.workflow.title")), [show_editor] { show_editor(kEditorWorkflow); }});
  m.push_back({std::string(store_.tr("editor.python.title")), [show_editor] { show_editor(kEditorPython); }});
  /* WP10: open a payload (.stkp / directory), a result directory or a run directory in the Viewer. */
  m.push_back({std::string(store_.tr("viewer.menu.open")), [this]() {
                 store_.viewer().open_dialog = true;
                 store_.changed();
               }});
  m.push_back({std::string(store_.tr("workspace.transfer.export")), [this, weak, s] {
    if (weak.lock()) { workspace_transfer().show(s, false); }
  }});
  m.push_back({std::string(store_.tr("workspace.transfer.import")), [this, weak, s] {
    if (weak.lock()) { workspace_transfer().show(s, true); }
  }});
  m.push_back({std::string(store_.tr("workspace.transfer.open")), [this, weak, s] {
    if (weak.lock()) { workspace_transfer().show_open(s); }
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
  std::weak_ptr<bool> weak = alive_;
  const auto focus = [this, weak, s](const std::string &editor_id) {
    if (!weak.lock() || std::find(screens_.begin(), screens_.end(), s) == screens_.end()) { return; }
    s->defer([this, weak, s, editor_id] {
      if (!weak.lock() || std::find(screens_.begin(), screens_.end(), s) == screens_.end()) { return; }
      const auto result = editor_id.empty() ? restore_split_layout(s) : activate_editor(s, editor_id, true);
      if (!result.ok() && s->ui()) { s->ui()->toast(result.error().message, ui::ToastKind::Warning); }
    });
  };
  m.push_back({std::string(store_.tr("app.menu.view.focus_preparation")), [focus] { focus(kEditorAI); }});
  m.push_back({std::string(store_.tr("app.menu.view.focus_analysis")), [focus] { focus(kEditorViewer); }});
  m.push_back({std::string(store_.tr("app.menu.view.restore_split_layout")), [focus] { focus(""); },
               screen.maximized() != nullptr});
  m.push_back({std::string(store_.tr("editor.analysis_graph.title")), [this, weak, s] {
    if (weak.lock()) { activate_editor_later(s, kEditorAnalysisGraph, false); }
  }});
  wm::Area *active = screen.maximized() ? screen.maximized() : screen.active_area();
  auto *ea = dynamic_cast<EditorArea *>(active);
  const bool maxed = screen.maximized() != nullptr;
  if (!maxed) {
    m.push_back({std::string(store_.tr("app.menu.view.maximize")),
                 [s, active]() { s->defer([s, active]() { s->toggle_maximized(active); }); },
                 active != nullptr});
  }
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
