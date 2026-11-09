/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/types.hh"
#include "stk/io/payload.hh"

#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace stk::app {

struct MuFerroHdf5Frame {
  std::string field;
  int64_t step;
  std::string selector;
};

std::string muferro_hdf5_path(std::string_view run_id);

/** Read only the selected collected container's metadata. */
bridge::EvaluateParams muferro_hdf5_fields_request(std::string eval_id, std::string_view project_directory,
                                                  std::string_view run_id, std::string_view sha256);
std::vector<MuFerroHdf5Frame> decode_muferro_hdf5_fields(const bridge::EvaluateParams &request,
                                                       const bridge::EvaluateResult &reply);

/** Build a local graph for one collected MuFerro HDF5 frame and its recorded container SHA-256.
 * The caller pins the project, result row and selected frame before submitting. */
bridge::EvaluateParams muferro_hdf5_frame_request(std::string eval_id, std::string_view project_directory,
                                                 std::string_view run_id, std::string_view selector,
                                                 std::string_view field, std::string_view sha256);

/** Decode the request's exact view from the bridge's announced cache. Throws on an invalid reply.
 * The caller rechecks the project and Viewer scope before adopting the owned payload. */
std::shared_ptr<const io::Payload> decode_muferro_hdf5_frame(const bridge::EvaluateParams &request,
                                                           const bridge::EvaluateResult &reply,
                                                           std::string_view expected_blob_dir);

}  // namespace stk::app
