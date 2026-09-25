/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/viewer_export.hh"

#include <algorithm>

#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "stk/viewer_gpu/viewer.hh"

namespace stk::app {

bool render_export_job(viewer_gpu::Viewer &viewer, const ExportJob &job, const AppStore &store,
                       std::shared_ptr<const io::Payload> current, std::string &message)
{
  viewer_gpu::ExportOptions eo;
  eo.width = job.settings.width;
  eo.height = job.settings.height;
  eo.magnification = std::clamp(job.settings.magnification, 1, 8);
  eo.transparent = job.settings.transparent;
  eo.overlays = job.settings.overlays;
  std::string err;
  if (!job.settings.sequence) {
    if (!job.frames.empty() && job.frames.front().second && job.frames.front().second != viewer.payload()) {
      viewer.set_payload(job.frames.front().second);
    }
    const bool ok = viewer.export_png(core::path_from_utf8(job.settings.path), eo, err);
    if (current && current != viewer.payload()) {
      viewer.set_payload(current);
    }
    message = ok ? store.catalog().format("export.done", {{"path", job.settings.path}}) :
                   store.catalog().format("export.failed", {{"error", err}});
    return ok;
  }
  bool ok = true;
  size_t written = 0;
  for (const auto &[step, payload] : job.frames) {
    if (!payload) {
      err = "step " + step.dump() + " has no payload";
      ok = false;
      break;
    }
    viewer.set_payload(payload); /* same camera signature across steps: the camera is kept */
    if (!viewer.export_png(core::path_from_utf8(sequence_frame_path(job.settings.path, step)), eo, err)) {
      ok = false;
      break;
    }
    written++;
  }
  if (current) {
    viewer.set_payload(current);
  }
  if (ok) {
    ok = ViewerState::write_series(job, &err);
  }
  message = ok ? store.catalog().format("export.done_sequence", {{"count", std::to_string(written)},
                                                                 {"path", sequence_manifest_path(job.settings.path)}}) :
                 store.catalog().format("export.failed", {{"error", err}});
  return ok;
}

}  // namespace stk::app
