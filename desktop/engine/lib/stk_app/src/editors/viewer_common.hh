/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Shared helpers of the WP10 editors (Viewer, Properties, Probe) and their dialogs (open,
 * export). Internal to stk_app.
 */
#pragma once

#include <string>
#include <string_view>

#include "stk/app/editor.hh"
#include "stk/app/viewer_state.hh"

namespace stk::wm {
class WindowManager;
}

namespace stk::app::viewer_ui {

/** Fixed width (UI units) fitting a button or label text. */
float fit_units(const EditorContext &ctx, std::string_view text, float min_units = 2.0f);
/** Height in UI units that fills what is left of the region below `used_units`. */
float fill_units(const EditorContext &ctx, float used_units, float min_units = 0.0f);
/** A number as the overlay labels format it (viewer::format_label, default ".6g"). */
std::string num(double value, std::string_view spec = ".6g");
/** "x, y, z" with num(). */
std::string vec3(const std::array<double, 3> &v, std::string_view spec = ".6g");
/** A step value for display ("12", "latest"). */
std::string step_text(const io::Json &step);
/** Localized preset name (props.preset.<id>, else the preset's own name). */
std::string preset_label(const EditorContext &ctx, const PresetInfo &preset);
/** The window manager of the editor's shell (null headless / in tests). */
wm::WindowManager *window_manager(const EditorContext &ctx);

/**
 * Consumes a pending "Open in viewer" request of the Jobs editor and runs ViewerState::pump;
 * schedules a redraw at the next wake-up (debounce, playback). Every WP10 editor calls it while
 * building, so whichever is visible keeps the state moving.
 */
void pump(EditorContext &ctx);

/** The open-payload and export dialogs (modals), when requested. */
void draw_dialogs(EditorContext &ctx);

/** Evaluation status line: progress bar while evaluating, else the last evaluation summary. */
void draw_eval_status(ui::Layout &l, EditorContext &ctx, bool compact);

}  // namespace stk::app::viewer_ui

namespace stk::app {

/** Editor types of WP10 (ids kEditorViewer, kEditorProperties, kEditorProbe). */
EditorType viewer_editor_type();
EditorType properties_editor_type();
EditorType probe_editor_type();

}  // namespace stk::app
