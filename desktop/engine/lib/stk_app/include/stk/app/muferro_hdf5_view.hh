/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/types.hh"
#include "stk/io/payload.hh"

#include <array>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace stk::app {

struct MuFerroHdf5Frame {
  std::string field;
  int64_t step;
  std::string selector;
  std::array<int64_t, 4> shape;
  std::string dtype;
  int64_t container_size;
};

/** Live origin of an accepted collected frame. It is not restored from workspace data. */
struct MuFerroHdf5Source {
  std::string project_id, project_handle, project_directory, run_id, sha256;
  int64_t project_revision;
  uint64_t project_scope, bridge_epoch;
  int64_t bridge_pid;
  MuFerroHdf5Frame frame;
  int64_t component;

  bool contains(const std::array<int64_t, 3> &position) const;
};

struct MuFerroHdf5Voxel {
  std::string dtype, value;
};

std::string muferro_hdf5_path(std::string_view run_id);

/** Read only the selected collected container's metadata. */
bridge::EvaluateParams muferro_hdf5_fields_request(std::string eval_id, std::string_view project_directory,
                                                  std::string_view run_id, std::string_view sha256);
std::vector<MuFerroHdf5Frame> decode_muferro_hdf5_fields(const bridge::EvaluateParams &request,
                                                       const bridge::EvaluateResult &reply);

/** Build a local graph for one collected MuFerro HDF5 frame, component and recorded container SHA-256.
 * The caller pins the project, result row and selected frame and validates the index against its shape. */
bridge::EvaluateParams muferro_hdf5_frame_request(std::string eval_id, std::string_view project_directory,
                                                 std::string_view run_id, std::string_view selector,
                                                 std::string_view field, std::string_view sha256,
                                                 int64_t component = 0);

/** Decode the request's exact view from the bridge's announced cache. Throws on an invalid reply.
 * The caller rechecks the project and Viewer scope before adopting the owned payload. */
std::shared_ptr<const io::Payload> decode_muferro_hdf5_frame(const bridge::EvaluateParams &request,
                                                           const bridge::EvaluateResult &reply,
                                                           std::string_view expected_blob_dir);

bridge::EvaluateParams muferro_hdf5_voxel_request(std::string eval_id, const MuFerroHdf5Source &source,
                                                 const std::array<int64_t, 3> &position);
/** Verify the exact source descriptor and read one digest-bound scalar from the bridge cache. */
MuFerroHdf5Voxel decode_muferro_hdf5_voxel(const bridge::EvaluateParams &request,
                                         const bridge::EvaluateResult &reply, std::string_view expected_blob_dir,
                                         const MuFerroHdf5Source &source, const std::array<int64_t, 3> &position);

}  // namespace stk::app
