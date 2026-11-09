/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/muferro_hdf5_view.hh"

#include "stk/app/analysis_document.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/io/blob_cache.hh"
#include "stk/io/graph.hh"

#include <algorithm>
#include <charconv>
#include <filesystem>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace stk::app {
namespace {
using io::Json;
constexpr size_t kFrameByteLimit = 256 * 1024 * 1024;
constexpr size_t kFieldsByteLimit = 256 * 1024;
constexpr size_t kFieldChoices = 256;

std::filesystem::path absolute_directory(std::string_view directory)
{
  const auto path = core::path_from_utf8(directory);
  std::error_code error;
  if (path.is_absolute() && directory.find('\0') == std::string_view::npos) {
    const auto resolved = std::filesystem::canonical(path, error);
    if (!error && std::filesystem::is_directory(resolved, error)) { return resolved; }
  }
  throw std::invalid_argument("The MuFerro HDF5 view needs an existing absolute directory");
}

bool matches_selector(std::string_view selector, std::string_view field)
{
  const auto alpha = [](char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); };
  const auto digit = [](char c) { return c >= '0' && c <= '9'; };
  if (field.empty() || field.size() > 64 || !alpha(field.front()) ||
      !std::all_of(field.begin(), field.end(), [&](char c) { return alpha(c) || digit(c) || c == '_'; })) {
    return false;
  }
  return selector.size() == 11 + field.size() && selector.starts_with("/t") && selector[10] == '/' &&
         std::all_of(selector.begin() + 2, selector.begin() + 10, digit) && selector.substr(11) == field;
}

bridge::EvaluateParams local_request(std::string eval_id, std::string_view project_directory,
                                     Json graph, const char *output, size_t max_bytes)
{
  bridge::EvaluateParams params;
  params.eval_id = std::move(eval_id);
  params.local_bindings["run"] = core::path_to_utf8(absolute_directory(project_directory));
  params.request = {{"graph", std::move(graph)}, {"profile", "desktop"}, {"outputs", Json::array({output})},
                    {"budget", {{"max_output_bytes", max_bytes}}}};
  return params;
}

const Json &graph_output(const bridge::EvaluateParams &request, const bridge::EvaluateResult &reply,
                         const char *output, const char *type, size_t line_limit)
{
  const auto &result = reply.result;
  if (reply.action || !result.is_object() || io::get_string(result, "schema") != io::kResultSchema ||
      io::get_string(result, "profile") != "desktop") {
    throw std::runtime_error("Invalid local MuFerro HDF5 graph result");
  }
  check_analysis_json_bounds(result, line_limit);
  const auto expected_hash = io::graph_hash(request.request.at("graph"));
  if (io::get_string(result, "graph_hash") != expected_hash ||
      io::get_string(result, "graph_sha256") != expected_hash.substr(7)) {
    throw std::runtime_error("The MuFerro HDF5 graph result belongs to another request");
  }
  const auto errors = result.find("errors");
  if (errors != result.end() && (!errors->is_array() || !errors->empty())) {
    throw std::runtime_error("The MuFerro HDF5 graph reported an error");
  }
  const auto &outputs = result.at("outputs");
  if (!outputs.is_object() || outputs.size() != 1 || !outputs.contains(output) ||
      io::get_string(outputs.at(output), "type") != type) {
    throw std::runtime_error("The MuFerro HDF5 graph did not return its requested output");
  }
  return outputs.at(output);
}
}  // namespace

std::string muferro_hdf5_path(std::string_view run_id)
{
  if (!canonical_uuid(run_id)) { throw std::invalid_argument("Invalid collected MuFerro run ID"); }
  return "results/muferro/" + std::string(run_id) + "/case/run.h5";
}

bridge::EvaluateParams muferro_hdf5_fields_request(std::string eval_id, std::string_view project_directory,
                                                  std::string_view run_id, std::string_view sha256)
{
  if (eval_id.empty() || !core::is_sha256_hex(sha256)) {
    throw std::invalid_argument("Invalid collected MuFerro HDF5 identity");
  }
  const Json node = {{"id", "fields"}, {"type", "stk.source.mupro_hdf5_fields@1"},
                     {"params", {{"binding", "run"}, {"path", muferro_hdf5_path(run_id)}, {"expected_sha256", sha256}}}};
  Json graph = {{"schema", "stk.graph/1"}, {"catalog", {{"stk", 1}}},
                {"nodes", Json::array({node})}, {"outputs", {{"fields", "fields.out"}}}};
  return local_request(std::move(eval_id), project_directory, std::move(graph), "fields", kFieldsByteLimit);
}

std::vector<MuFerroHdf5Frame> decode_muferro_hdf5_fields(const bridge::EvaluateParams &request,
                                                       const bridge::EvaluateResult &reply)
{
  const auto &value = graph_output(request, reply, "fields", "value", kFieldsByteLimit).at("value");
  const auto &params = request.request.at("graph").at("nodes").at(0).at("params");
  const auto &fields = value.at("fields");
  const auto size = io::get_int(value, "size", 0);
  if (value.at("path") != params.at("path") || value.at("sha256") != params.at("expected_sha256") ||
      io::get_string(value, "reader") != "mupro.hdf5@1" || size <= 0 || size > (int64_t(1) << 30) ||
      !fields.is_array() || fields.size() > kFieldChoices) {
    throw std::runtime_error("Invalid collected MuFerro HDF5 field list");
  }
  std::vector<MuFerroHdf5Frame> frames;
  frames.reserve(fields.size());
  for (const auto &field : fields) {
    auto name = io::get_string(field, "name");
    auto selector = io::get_string(field, "selector");
    const auto step = io::get_int(field, "step", -1);
    if (!matches_selector(selector, name)) { throw std::runtime_error("Invalid MuFerro HDF5 field selector"); }
    int64_t selector_step = -1;
    const auto parsed = std::from_chars(selector.data() + 2, selector.data() + 10, selector_step);
    if (parsed.ec != std::errc() || selector_step != step) { throw std::runtime_error("Invalid MuFerro HDF5 field step"); }
    frames.push_back({std::move(name), step, std::move(selector)});
  }
  const auto key = [](const auto &frame) { return std::tie(frame.field, frame.step); };
  std::sort(frames.begin(), frames.end(), [&](const auto &left, const auto &right) { return key(left) < key(right); });
  if (std::adjacent_find(frames.begin(), frames.end(), [&](const auto &left, const auto &right) {
        return key(left) == key(right);
      }) != frames.end()) {
    throw std::runtime_error("Duplicate MuFerro HDF5 field and step");
  }
  return frames;
}

bridge::EvaluateParams muferro_hdf5_frame_request(std::string eval_id, std::string_view project_directory,
                                                 std::string_view run_id, std::string_view selector,
                                                 std::string_view field, std::string_view sha256)
{
  if (eval_id.empty() || !matches_selector(selector, field) ||
      !core::is_sha256_hex(sha256)) {
    throw std::invalid_argument("Invalid MuFerro HDF5 frame identity");
  }
  const auto path = muferro_hdf5_path(run_id);
  const auto nodes = Json::array({
      {{"id", "src"}, {"type", "stk.source.mupro_hdf5@1"},
       {"params", {{"binding", "run"}, {"path", path}, {"selector", selector}, {"expected_sha256", sha256}}}},
      {{"id", "component"}, {"type", "stk.filter.calculator@1"},
       {"inputs", {{"in", {{"from", "src.out"}}}}},
       {"params", {{"operation", "component"}, {"field", field}, {"component", 0}, {"keep_input", false}}}},
      {{"id", "volume"}, {"type", "stk.render.volume@1"},
       {"inputs", {{"in", {{"from", "component.out"}}}}}, {"params", {{"colormap", "coolwarm"}}}},
      {{"id", "scene"}, {"type", "stk.view.scene@1"},
       {"inputs", {{"layers", Json::array({{{"from", "volume.layer"}}})}}}},
  });
  Json graph = {{"schema", "stk.graph/1"}, {"catalog", {{"stk", 1}}},
                      {"nodes", nodes}, {"outputs", {{"view", "scene.scene"}}}};
  return local_request(std::move(eval_id), project_directory, std::move(graph), "view", kFrameByteLimit);
}

std::shared_ptr<const io::Payload> decode_muferro_hdf5_frame(const bridge::EvaluateParams &request,
                                                           const bridge::EvaluateResult &reply,
                                                           std::string_view expected_blob_dir)
{
  const auto &manifest = graph_output(request, reply, "view", "payload", bridge::kDefaultMaxLineBytes).at("manifest");
  if (!manifest.is_object() || io::get_string(manifest, "schema") != "stk.payload/2") {
    throw std::runtime_error("Invalid MuFerro HDF5 view manifest");
  }
  const auto returned = core::path_from_utf8(reply.blob_dir);
  if (!returned.is_absolute() || returned != core::path_from_utf8(expected_blob_dir)) {
    throw std::runtime_error("The MuFerro HDF5 view cache does not match the local bridge");
  }
  const auto result_bytes = io::python_json_dumps(reply.result).size();
  if (result_bytes > kFrameByteLimit) {
    throw std::runtime_error("The MuFerro HDF5 view exceeds its byte limit");
  }
  const io::BlobCache blobs(absolute_directory(expected_blob_dir));
  auto payload = blobs.decode_owned_manifest(manifest, kFrameByteLimit - result_bytes);
  const auto *volume = payload.layer("volume");
  if (!volume || io::get_string(*volume, "type") != "volume" || payload.skipped("volume")) {
    throw std::runtime_error("The MuFerro HDF5 view has no displayable volume");
  }
  return std::make_shared<const io::Payload>(std::move(payload));
}

}  // namespace stk::app
