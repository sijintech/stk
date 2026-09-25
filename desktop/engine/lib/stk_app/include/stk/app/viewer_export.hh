/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Rendering of a ViewerState export job with stk_viewer_gpu (GPU context required): one PNG, or
 * one PNG per time step plus the stk.series/1 manifest (<stem>.series.json). Shared by the Viewer
 * editor (export dialog) and `stk-desktop --headless --export ... [--sequence]`.
 */
#pragma once

#include <string>

#include "stk/app/viewer_state.hh"

namespace stk::viewer_gpu {
class Viewer;
}

namespace stk::app {

/**
 * Renders `job` with `viewer` (its camera, visibility and overlays as they are). A sequence shows
 * each step's payload in turn (the camera is kept: steps share the view's camera signature) and
 * restores `current` afterwards. `message` is the localized result for the log / a toast.
 */
bool render_export_job(viewer_gpu::Viewer &viewer, const ExportJob &job, const AppStore &store,
                       std::shared_ptr<const io::Payload> current, std::string &message);

}  // namespace stk::app
