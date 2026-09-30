/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/json.hh"

#include <cstdint>
#include <string>

namespace stk::app {

/** Bounded immutable input references from an already-read run, detached from its definition,
 * result and lifecycle. Public fields are revalidated before a snapshot can be accepted. */
struct AnalysisInputReusePlan {
  std::string project_id, run_id, analysis_id, plan_sha256;
  std::string snapshot_id, snapshot_sha256;
  int64_t source_revision = -1;
  io::Json bindings; // {binding:{relative_path:{record_id,sha256,size}}}
};

/** Local preparation only. No original source paths, graph, parameters, outputs or results.
 * Snapshot get verifies manifest metadata; file bytes are checked separately when a run starts. */
struct AnalysisReusedInputs {
  std::string project_id, run_id, analysis_id, plan_sha256;
  std::string snapshot_id, snapshot_sha256;
  int64_t snapshot_revision = -1;
  io::Json bindings; // {binding:{relative_path:record_id}}
  io::Json files;    // [{record_id,name,sha256,size}], all snapshot files in manifest order
};

/** Pure bounded extraction and consistency checks. Both functions throw invalid_argument before
 * publishing a result on malformed/mismatched metadata. They never resolve paths or read bytes.
 * Unconsumed run/manifest fields are not traversed or copied. Full stored checksum/identity
 * validation remains the responsibility of the existing project.snapshots.get backend. */
AnalysisInputReusePlan analysis_input_reuse_plan(const io::Json &validated_run,
                                                const std::string &project_id);
AnalysisReusedInputs analysis_reused_inputs(const AnalysisInputReusePlan &plan,
                                           const io::Json &snapshot);

}  // namespace stk::app
