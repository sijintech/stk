/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The editor registry of the D1 editors, in menu order: Jobs, Transfers, Logs and Bridge log
 * (WP9, editors/jobs_*.cc) and Viewer, Properties and Probe (WP10, editors/viewer_*.cc). The ids
 * are the ones WP3 layouts were saved with.
 */

#include "stk/app/editor.hh"

#include "editors/jobs_common.hh"
#include "editors/viewer_common.hh"

namespace stk::app {

void register_builtin_editors(EditorRegistry &registry)
{
  registry.add({kEditorJobs, "editor.jobs.title", make_jobs_editor});
  registry.add(viewer_editor_type());     /* WP10 (editors/viewer_editor.cc) */
  registry.add(properties_editor_type()); /* WP10 (editors/viewer_panels.cc) */
  registry.add({kEditorLogs, "editor.logs.title", make_logs_editor});
  registry.add(probe_editor_type()); /* WP10 (editors/viewer_panels.cc) */
  registry.add({kEditorTransfers, "editor.transfers.title", make_transfers_editor});
  registry.add({kEditorBridgeLog, "editor.bridge_log.title", make_bridge_log_editor});
}

}  // namespace stk::app
