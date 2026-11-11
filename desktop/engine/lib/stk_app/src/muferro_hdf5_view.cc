/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/muferro_hdf5_view.hh"

#include "stk/app/analysis_document.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/io/blob_cache.hh"
#include "stk/io/graph.hh"

#include <algorithm>
#include <bit>
#include <charconv>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace stk::app {
namespace {
using io::Json;
constexpr size_t kFrameByteLimit = 256 * 1024 * 1024;
constexpr size_t kFieldsByteLimit = 256 * 1024;
constexpr size_t kFieldChoices = 256;
constexpr int64_t kMaxSafeInteger = (int64_t(1) << 53) - 1;
constexpr size_t kVoxelResultByteLimit = 16 * 1024;
constexpr size_t kVoxelBlobByteLimit = 4096;

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

const Json &graph_outputs(const bridge::EvaluateParams &request, const bridge::EvaluateResult &reply,
                          size_t count, size_t line_limit)
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
  if (!outputs.is_object() || outputs.size() != count) {
    throw std::runtime_error("The MuFerro HDF5 graph did not return its requested output");
  }
  return outputs;
}

const Json &typed_output(const Json &outputs, const char *output, const char *type)
{
  if (!outputs.contains(output) || io::get_string(outputs.at(output), "type") != type) {
    throw std::runtime_error("The MuFerro HDF5 graph did not return its requested output");
  }
  return outputs.at(output);
}

const Json &graph_output(const bridge::EvaluateParams &request, const bridge::EvaluateResult &reply,
                         const char *output, const char *type, size_t line_limit)
{
  return typed_output(graph_outputs(request, reply, 1, line_limit), output, type);
}

std::string_view npy_type(std::string_view dtype)
{
  constexpr std::pair<std::string_view, std::string_view> types[] = {
      {"float32", "f4"}, {"float64", "f8"}, {"int8", "i1"}, {"uint8", "u1"}, {"int16", "i2"},
      {"uint16", "u2"}, {"int32", "i4"}, {"uint32", "u4"}, {"int64", "i8"}, {"uint64", "u8"}};
  for (const auto &[name, code] : types) {
    if (name == dtype) { return code; }
  }
  return {};
}

template<typename Float> std::string float_text(Float value)
{
  if (std::isnan(value)) { return "NaN"; }
  if (std::isinf(value)) { return std::signbit(value) ? "-Inf" : "+Inf"; }
  std::ostringstream out;
  out.imbue(std::locale::classic());
  out << std::setprecision(std::numeric_limits<Float>::max_digits10) << value;
  return out.str();
}

std::string decode_npy_scalar(std::span<const uint8_t> bytes, std::string_view dtype)
{
  const auto require = [](bool valid) {
    if (!valid) { throw std::runtime_error("Invalid MuFerro HDF5 voxel NPY"); }
  };
  require(bytes.size() >= 10 && bytes[0] == 0x93 && std::memcmp(bytes.data() + 1, "NUMPY", 5) == 0);
  const int version = bytes[6];
  const size_t header_offset = version == 1 ? 10 : 12;
  require(version >= 1 && version <= 3 && bytes[7] == 0 && bytes.size() >= header_offset);
  size_t header_size = 0;
  for (size_t i = 8; i < header_offset; ++i) { header_size |= size_t(bytes[i]) << (8 * (i - 8)); }
  const auto type = npy_type(dtype);
  require(!type.empty());
  const size_t width = size_t(type[1] - '0');
  require(header_size > 0 && header_size <= bytes.size() - header_offset &&
          bytes.size() - header_offset - header_size == width);
  std::string_view header(reinterpret_cast<const char *>(bytes.data() + header_offset), header_size);
  require(header.back() == '\n');
  header.remove_suffix(1);
  while (!header.empty() && header.back() == ' ') { header.remove_suffix(1); }
  constexpr std::string_view prefix = "{'descr': '";
  require(header.starts_with(prefix) && header.size() > prefix.size() + 3);
  header.remove_prefix(prefix.size());
  const char order = header[0];
  require(header.substr(1, 2) == type &&
          header.substr(3) == "', 'fortran_order': False, 'shape': (1, 1, 1), }" &&
          (width == 1 ? order == '|' : order == '<' || order == '>'));
  uint64_t bits = 0;
  const auto data = bytes.last(width);
  for (size_t i = 0; i < width; ++i) {
    bits |= uint64_t(data[order == '>' ? width - i - 1 : i]) << (8 * i);
  }
  if (type == "f4") { return float_text(std::bit_cast<float>(uint32_t(bits))); }
  if (type == "f8") { return float_text(std::bit_cast<double>(bits)); }
  if (type == "i1") { return std::to_string(std::bit_cast<int8_t>(uint8_t(bits))); }
  if (type == "i2") { return std::to_string(std::bit_cast<int16_t>(uint16_t(bits))); }
  if (type == "i4") { return std::to_string(std::bit_cast<int32_t>(uint32_t(bits))); }
  if (type == "i8") { return std::to_string(std::bit_cast<int64_t>(bits)); }
  return std::to_string(bits);
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
    const auto &shape = field.at("shape");
    const auto dtype = io::get_string(field, "dtype");
    if (!shape.is_array() || shape.size() != 4 || npy_type(dtype).empty()) {
      throw std::runtime_error("Invalid MuFerro HDF5 field shape or dtype");
    }
    std::array<int64_t, 4> dims;
    for (size_t i = 0; i < dims.size(); ++i) {
      if (!shape[i].is_number_integer()) { throw std::runtime_error("Invalid MuFerro HDF5 field dimension"); }
      dims[i] = shape[i].get<int64_t>();
      if (dims[i] < 1 || dims[i] > kMaxSafeInteger) {
        throw std::runtime_error("Invalid MuFerro HDF5 field dimension");
      }
    }
    frames.push_back({std::move(name), step, std::move(selector), dims, dtype, size});
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
                                                 std::string_view field, std::string_view sha256,
                                                 int64_t component)
{
  if (eval_id.empty() || !matches_selector(selector, field) || !core::is_sha256_hex(sha256) ||
      component < 0 || component > kMaxSafeInteger) {
    throw std::invalid_argument("Invalid MuFerro HDF5 frame identity");
  }
  const auto path = muferro_hdf5_path(run_id);
  const auto nodes = Json::array({
      {{"id", "src"}, {"type", "stk.source.mupro_hdf5@1"},
       {"params", {{"binding", "run"}, {"path", path}, {"selector", selector}, {"expected_sha256", sha256}}}},
      {{"id", "component"}, {"type", "stk.filter.calculator@1"},
       {"inputs", {{"in", {{"from", "src.out"}}}}},
       {"params", {{"operation", "component"}, {"field", field},
                   {"component", component}, {"keep_input", false}}}},
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

bool MuFerroHdf5Source::contains(const std::array<int64_t, 3> &position) const
{
  for (size_t i = 0; i < position.size(); ++i) {
    if (position[i] < 0 || position[i] >= frame.shape[i]) { return false; }
  }
  return true;
}

bridge::EvaluateParams muferro_hdf5_voxel_request(std::string eval_id, const MuFerroHdf5Source &source,
                                                 const std::array<int64_t, 3> &position)
{
  const auto root = core::path_from_utf8(source.project_directory);
  if (eval_id.empty() || !root.is_absolute() || source.project_directory.find('\0') != std::string::npos ||
      !matches_selector(source.frame.selector, source.frame.field) || !core::is_sha256_hex(source.sha256) ||
      npy_type(source.frame.dtype).empty() || !source.contains(position) || source.component < 0 ||
      source.component >= source.frame.shape[3] || source.frame.container_size <= 0 ||
      source.frame.container_size > (int64_t(1) << 30)) {
    throw std::invalid_argument("Invalid collected MuFerro HDF5 voxel identity");
  }
  const auto path = muferro_hdf5_path(source.run_id);
  const std::string run_path = "results/muferro/" + source.run_id;
  const auto [x, y, z] = position;
  const Json nodes = Json::array({
      {{"id", "src"}, {"type", "stk.source.mupro_hdf5@1"},
       {"params", {{"binding", "run"}, {"path", "case/run.h5"}, {"selector", source.frame.selector},
                   {"expected_sha256", source.sha256}, {"extent", {x, x, y, y, z, z}}}}},
      {{"id", "component"}, {"type", "stk.filter.calculator@1"},
       {"inputs", {{"in", {{"from", "src.out"}}}}},
       {"params", {{"operation", "component"}, {"field", source.frame.field}, {"component", source.component},
                   {"result", "value"}, {"keep_input", false}}}},
      {{"id", "voxel"}, {"type", "stk.output.dataset@1"}, {"inputs", {{"in", {{"from", "component.out"}}}}},
       {"params", {{"format", "npy"}, {"precision", "float64"}}}},
  });
  bridge::EvaluateParams params;
  params.eval_id = std::move(eval_id);
  params.local_bindings["run"] = core::path_to_utf8(root / core::path_from_utf8(run_path));
  params.local_proofs = {{"run", {{"project_root", source.project_directory}, {"case_path", run_path},
      {"files", Json::array({{{"path", path}, {"sha256", source.sha256}}})}}}};
  params.request = {{"graph", {{"schema", "stk.graph/1"}, {"catalog", {{"stk", 1}}}, {"nodes", nodes},
                    {"outputs", {{"source", "src.out"}, {"voxel", "voxel.file"}}}}},
                    {"profile", "desktop"}, {"outputs", {"source", "voxel"}},
                    {"budget", {{"max_output_bytes", kVoxelResultByteLimit}}}};
  return params;
}

MuFerroHdf5Voxel decode_muferro_hdf5_voxel(const bridge::EvaluateParams &request,
                                         const bridge::EvaluateResult &reply, std::string_view expected_blob_dir,
                                         const MuFerroHdf5Source &source, const std::array<int64_t, 3> &position)
{
  const auto &outputs = graph_outputs(request, reply, 2, kVoxelResultByteLimit);
  const auto &descriptor = typed_output(outputs, "source", "dataset").at("descriptor");
  const auto &geometry = descriptor.at("geometry");
  const auto &fields = descriptor.at("fields");
  const auto &frames = descriptor.at("frames");
  if (descriptor.at("schema") != "stk.dataset/1" || descriptor.at("kind") != "image" ||
      descriptor.at("id") != source.frame.field || descriptor.at("time").at("step") != source.frame.step ||
      geometry.at("dimensions") != Json::array({1, 1, 1}) || geometry.at("origin") != Json(position) ||
      geometry.at("spacing") != Json::array({1, 1, 1}) || geometry.at("length_unit") != "grid_index" ||
      !fields.is_array() || fields.size() != 1 || !frames.is_array() || frames.size() != 1) {
    throw std::runtime_error("Invalid MuFerro HDF5 voxel source descriptor");
  }
  const auto &field = fields.front();
  const auto &frame = frames.front();
  const auto &identity = frame.at("sources").at(source.frame.field);
  if (field.at("name") != source.frame.field || field.at("dtype") != source.frame.dtype ||
      field.at("association") != "point" || field.at("components") != source.frame.shape[3] ||
      frame.at("step") != source.frame.step || identity.at("path") != "case/run.h5" ||
      identity.at("reader") != "mupro.hdf5@1" || identity.at("selector") != source.frame.selector ||
      identity.at("sha256") != source.sha256 || identity.at("size") != source.frame.container_size) {
    throw std::runtime_error("MuFerro HDF5 voxel source does not match the displayed field");
  }
  const auto &file = typed_output(outputs, "voxel", "file");
  const auto sha = io::get_string(file, "blob");
  const auto size = io::get_int(file, "size", 0);
  const auto returned = core::path_from_utf8(reply.blob_dir);
  if (io::get_string(file, "name") != "voxel.npy" || io::get_string(file, "media_type") != "application/x-npy" ||
      !core::is_sha256_hex(sha) || size <= 0 || uint64_t(size) > kVoxelBlobByteLimit ||
      !returned.is_absolute() || returned != core::path_from_utf8(expected_blob_dir)) {
    throw std::runtime_error("Invalid MuFerro HDF5 voxel file receipt");
  }
  const io::BlobCache blobs(absolute_directory(expected_blob_dir));
  const auto bytes = core::SharedBytes::read_exact_file(blobs.path_for(sha), size_t(size));
  if (core::Sha256::hex(bytes.span()) != sha) {
    throw std::runtime_error("MuFerro HDF5 voxel file checksum mismatch");
  }
  return {source.frame.dtype, decode_npy_scalar(bytes.span(), source.frame.dtype)};
}

}  // namespace stk::app
