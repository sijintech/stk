/* SPDX-License-Identifier: GPL-2.0-or-later */
/* H1 collected MuFerro HDF5 view (docs/design/mupro-hdf5-result-selection.md): the two strict local
 * request builders, the field-metadata decoder and the exact frame payload decoder. Synthetic replies
 * only; no bridge process, solver, partner asset or model request. */
#include "stk/app/muferro_hdf5_view.hh"

#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/io/blob_cache.hh"
#include "stk/io/graph.hh"

#include "../bridge/support.hh" /* TempDir under the build's test scratch area */

#include <gtest/gtest.h>

#include <algorithm>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <map>
#include <limits>
#include <string>
#include <utility>
#include <vector>

namespace {

namespace fs = std::filesystem;
using stk::bridge::EvaluateParams;
using stk::bridge::EvaluateResult;
using stk::io::Json;

/* Low-entropy placeholders, never real digests or run IDs. */
const std::string kRun = "00000000-0000-4000-8000-000000000002";
const std::string kSha = std::string(64, 'a');
const std::string kOther = std::string(64, 'b');
constexpr int64_t kSize = 6328;
const std::string kPath = "results/muferro/" + kRun + "/case/run.h5";

std::string selector(const std::string &field, int64_t step)
{
  char buffer[32];
  std::snprintf(buffer, sizeof(buffer), "/t%08lld/", static_cast<long long>(step));
  return buffer + field;
}

/** One entry as suan.connectors.mupro.discovery reports it (extra shape/dtype keys included). */
Json entry(const std::string &field, int64_t step, int components = 3, const char *dtype = "float32")
{
  return {{"selector", selector(field, step)}, {"step", step}, {"name", field},
          {"shape", {4, 3, 2, components}}, {"dtype", dtype}};
}

/** The stk.source.mupro_hdf5_fields@1 value, in the node's (step, name) order. */
Json metadata()
{
  return {{"path", kPath}, {"sha256", kSha}, {"size", kSize}, {"reader", "mupro.hdf5@1"},
          {"fields", Json::array({entry("Polar", 2), entry("Strain", 2, 6, "int16"), entry("Polar", 4),
                                  entry("Strain", 4, 6, "int16"), entry("Polar", 10)})}};
}

Json graph_result(const EvaluateParams &request, const char *output, Json value)
{
  const auto hash = stk::io::graph_hash(request.request.at("graph"));
  return {{"schema", "stk.graph-result/1"}, {"graph_hash", hash}, {"graph_sha256", hash.substr(7)},
          {"profile", "desktop"}, {"outputs", {{output, std::move(value)}}}, {"parameters", Json::object()},
          {"errors", Json::array()}};
}

EvaluateResult reply(Json result, std::string blob_dir = {})
{
  EvaluateResult out;
  out.result = std::move(result);
  out.blob_dir = std::move(blob_dir);
  return out;
}

class Project {
 public:
  Project() { fs::create_directories(root()); }
  fs::path root() const { return dir_.path() / "project"; }
  std::string str() const { return stk::core::path_to_utf8(root()); }
  /* The bridge binding is the resolved project root (macOS resolves /var to /private/var, for example). */
  std::string canonical() const { return stk::core::path_to_utf8(fs::canonical(root())); }
  const fs::path &scratch() const { return dir_.path(); }

 private:
  stk::bridge::test::TempDir dir_{"muferro-hdf5-view"};
};

EvaluateParams fields_request(const Project &project)
{
  return stk::app::muferro_hdf5_fields_request("hdf5-fields-1", project.str(), kRun, kSha);
}

EvaluateParams frame_request(const Project &project, const std::string &field = "Polar", int64_t step = 2)
{
  return stk::app::muferro_hdf5_frame_request("hdf5-frame-1", project.str(), kRun, selector(field, step), field, kSha);
}

stk::app::MuFerroHdf5Source voxel_source(const Project &project, const std::string &dtype = "uint64")
{
  return {"project", "handle", project.str(), kRun, kSha, 1, 2, 3, 4,
          {"Polar", 2, selector("Polar", 2), {4, 3, 2, 3}, dtype, kSize}, 0};
}

std::vector<uint8_t> npy_scalar(std::string_view dtype, uint64_t bits, std::string_view shape = "(1, 1, 1)")
{
  std::string header = "{'descr': '" + std::string(dtype) + "', 'fortran_order': False, 'shape': " +
                       std::string(shape) + ", }";
  header.append((64 - (10 + header.size() + 1) % 64) % 64, ' ');
  header += '\n';
  const size_t width = size_t(dtype[2] - '0');
  std::vector<uint8_t> bytes{0x93, 'N', 'U', 'M', 'P', 'Y', 1, 0, uint8_t(header.size()), 0};
  bytes.reserve(bytes.size() + header.size() + width);
  bytes.insert(bytes.end(), header.begin(), header.end());
  for (size_t i = 0; i < width; ++i) {
    bytes.push_back(uint8_t(bits >> (8 * (dtype[0] == '>' ? width - i - 1 : i))));
  }
  return bytes;
}

Json voxel_result(const EvaluateParams &request, const stk::app::MuFerroHdf5Source &source,
                  const std::array<int64_t, 3> &position, const stk::io::BlobCache &blobs,
                  std::span<const uint8_t> bytes)
{
  const auto &field = source.frame;
  auto result = graph_result(request, "voxel", {{"type", "file"}, {"name", "voxel.npy"},
      {"media_type", "application/x-npy"}, {"size", bytes.size()}, {"blob", blobs.put(bytes)}});
  result["outputs"]["source"] = {{"type", "dataset"}, {"descriptor", {
      {"schema", "stk.dataset/1"}, {"kind", "image"}, {"id", field.field},
      {"time", {{"step", field.step}}},
      {"geometry", {{"dimensions", {1, 1, 1}}, {"origin", position}, {"spacing", {1, 1, 1}},
                    {"length_unit", "grid_index"}}},
      {"fields", Json::array({{{"name", field.field}, {"dtype", field.dtype}, {"association", "point"},
                               {"components", field.shape[3]}}})},
      {"frames", Json::array({{{"step", field.step}, {"sources", {{field.field, {
          {"path", "case/run.h5"}, {"reader", "mupro.hdf5@1"}, {"selector", field.selector},
          {"sha256", source.sha256}, {"size", field.container_size}}}}}}})}}}};
  return result;
}

std::vector<std::string> labels(const std::vector<stk::app::MuFerroHdf5Frame> &frames)
{
  std::vector<std::string> out;
  for (const auto &frame : frames) {
    out.push_back(frame.field + "@" + std::to_string(frame.step) + "=" + frame.selector);
  }
  return out;
}

/** A minimal stk.payload/2 scene: one 2x2x2 float volume with a 256-entry LUT, blobs in a cache. */
struct VolumeScene {
  Json manifest;
  std::vector<std::pair<std::string, std::vector<uint8_t>>> blobs;
  std::vector<float> voxels{0, 1, 2, 3, 4, 5, 6, 69};

  VolumeScene()
  {
    manifest = {{"schema", "stk.payload/2"}, {"render_origin", {0.0, 0.0, 0.0}}, {"length_unit", "unspecified"},
                {"buffers", Json::array()}, {"accessors", Json::array()}, {"layers", Json::array()}};
    std::vector<uint8_t> lut;
    for (int i = 0; i < 256; ++i) { lut.insert(lut.end(), {uint8_t(i), uint8_t(80), uint8_t(255 - i), uint8_t(255)}); }
    add("lut", std::move(lut), "u8", 4, 256);
    std::vector<uint8_t> bytes(voxels.size() * sizeof(float));
    std::memcpy(bytes.data(), voxels.data(), bytes.size());
    add("vol", std::move(bytes), "f32", 1, voxels.size());
    manifest["colormaps"] = Json::array({{{"id", "cm"}, {"name", "coolwarm"}, {"categorical", false},
                                          {"lut", "lut"}, {"size", 256}}});
    manifest["layers"].push_back(
        {{"id", "volume"}, {"type", "volume"}, {"name", "Polar_x"},
         {"grid", {{"dimensions", {2, 2, 2}}, {"origin", {0.0, 0.0, 0.0}}, {"spacing", {1.0, 1.0, 1.0}}}},
         {"data", "vol"}, {"value_range", {0.0, 69.0}},
         {"transfer_function", {{"colormap", "cm"}, {"range", {0.0, 69.0}}, {"opacity", {{0.0, 0.5}, {69.0, 0.5}}}}}});
  }

  void add(const std::string &id, std::vector<uint8_t> bytes, const char *type, int components, size_t count)
  {
    const auto sha = stk::core::Sha256::hex(bytes.data(), bytes.size());
    manifest["buffers"].push_back({{"id", "b_" + id}, {"uri", "sha256:" + sha}, {"sha256", sha},
                                   {"byteLength", bytes.size()}, {"encoding", "raw"}});
    manifest["accessors"].push_back({{"id", id}, {"buffer", "b_" + id}, {"byteOffset", 0}, {"count", count},
                                     {"type", type}, {"components", components}});
    blobs.emplace_back(sha, std::move(bytes));
  }

  /** Store the blobs in `<dir>/<aa>/<sha>` (the bridge's announced blob directory). */
  fs::path store(const fs::path &dir) const
  {
    const stk::io::BlobCache cache(dir);
    for (const auto &[sha, bytes] : blobs) { EXPECT_EQ(cache.put(bytes), sha); }
    return dir;
  }

  std::string sha(const std::string &id) const
  {
    for (const auto &buffer : manifest.at("buffers")) {
      if (buffer.at("id") == "b_" + id) { return buffer.at("sha256").get<std::string>(); }
    }
    return {};
  }

  Json output() const { return {{"type", "payload"}, {"manifest", manifest}}; }
};

void flip_first_byte(const fs::path &file)
{
  std::fstream stream(file, std::ios::in | std::ios::out | std::ios::binary);
  ASSERT_TRUE(stream.good()) << file;
  const int first = stream.get();
  stream.seekp(0);
  stream.put(static_cast<char>(first ^ 1));
  stream.close();
  ASSERT_TRUE(stream.good()) << file;
}

}  // namespace

TEST(MuferroHdf5ViewTest, PathIsTheFixedProjectRelativeContainer)
{
  EXPECT_EQ(stk::app::muferro_hdf5_path(kRun), kPath);
  EXPECT_EQ(kPath.find('\\'), std::string::npos);
  for (const char *bad : {"", "00000000-0000-4000-8000-00000000000G", "00000000-0000-4000-8000-00000000000A",
                          "00000000000040008000000000000002", "../00000000-0000-4000-8000-000000000002",
                          "00000000-0000-4000-8000-0000000000020"}) {
    EXPECT_THROW(stk::app::muferro_hdf5_path(bad), std::invalid_argument) << bad;
  }
}

TEST(MuferroHdf5ViewTest, FieldsRequestReadsOnlyTheRegisteredContainerFromTheProjectRoot)
{
  const Project project;
  const auto params = fields_request(project);
  const Json expected = {
      {"graph", {{"schema", "stk.graph/1"}, {"catalog", {{"stk", 1}}},
                 {"nodes", Json::array({{{"id", "fields"}, {"type", "stk.source.mupro_hdf5_fields@1"},
                                         {"params", {{"binding", "run"}, {"path", kPath}, {"expected_sha256", kSha}}}}})},
                 {"outputs", {{"fields", "fields.out"}}}}},
      {"profile", "desktop"}, {"outputs", Json::array({"fields"})}, {"budget", {{"max_output_bytes", 256 * 1024}}}};
  EXPECT_EQ(params.request.dump(), expected.dump());
  const Json wire = params.to_json();
  EXPECT_EQ(wire.at("eval_id"), "hdf5-fields-1");
  EXPECT_EQ(wire.at("local_bindings"), Json({{"run", project.canonical()}}));
  EXPECT_FALSE(wire.contains("mode")); /* local evaluation */
  EXPECT_FALSE(wire.contains("connection"));
  EXPECT_FALSE(wire.contains("wait"));

  /* A non-normal spelling of the same root binds the resolved root, not the caller's text or the case. */
  fs::create_directories(project.root() / "results");
  const auto dotted = stk::core::path_to_utf8(project.root() / "results" / "..");
  const auto again = stk::app::muferro_hdf5_fields_request("hdf5-fields-2", dotted, kRun, kSha);
  EXPECT_EQ(again.local_bindings.at("run"), project.canonical());
  EXPECT_EQ(again.request.at("graph"), params.request.at("graph"));
}

TEST(MuferroHdf5ViewTest, BuildersRefuseAnInvalidIdentityOrProjectDirectory)
{
  const Project project;
  {
    std::ofstream file(project.scratch() / "plain.txt");
    file << "not a directory";
  }
  const auto file = stk::core::path_to_utf8(project.scratch() / "plain.txt");
  const auto missing = stk::core::path_to_utf8(project.scratch() / "missing");
  const std::string sel = selector("Polar", 2);
  using Builder = std::function<void(std::string, const std::string &, const std::string &, const std::string &)>;
  const std::vector<std::pair<std::string, Builder>> builders = {
      {"fields", [](std::string id, const std::string &dir, const std::string &run, const std::string &sha) {
         stk::app::muferro_hdf5_fields_request(std::move(id), dir, run, sha);
       }},
      {"frame", [&](std::string id, const std::string &dir, const std::string &run, const std::string &sha) {
         stk::app::muferro_hdf5_frame_request(std::move(id), dir, run, sel, "Polar", sha);
       }},
  };
  for (const auto &[name, build] : builders) {
    EXPECT_NO_THROW(build("x", project.str(), kRun, kSha)) << name;
    EXPECT_THROW(build("", project.str(), kRun, kSha), std::invalid_argument) << name << " empty eval id";
    for (const auto &sha : {std::string(64, 'A'), kSha.substr(1), kSha + "a", std::string()}) {
      EXPECT_THROW(build("x", project.str(), kRun, sha), std::invalid_argument) << name << " sha " << sha;
    }
    EXPECT_THROW(build("x", project.str(), "not-a-run", kSha), std::invalid_argument) << name << " run";
    /* "." always exists: a relative spelling is refused, not resolved against the working directory. */
    for (const auto &dir : {std::string("."), std::string("project"), std::string(), file, missing,
                            project.str() + std::string(1, '\0')}) {
      EXPECT_THROW(build("x", dir, kRun, kSha), std::invalid_argument) << name << " directory " << dir.c_str();
    }
  }
}

TEST(MuferroHdf5ViewTest, FrameRequestIsTheExplicitPinnedFrameGraph)
{
  const Project project;
  const auto params = frame_request(project);
  const Json nodes = Json::array({
      {{"id", "src"}, {"type", "stk.source.mupro_hdf5@1"},
       {"params", {{"binding", "run"}, {"path", kPath}, {"selector", "/t00000002/Polar"}, {"expected_sha256", kSha}}}},
      {{"id", "component"}, {"type", "stk.filter.calculator@1"}, {"inputs", {{"in", {{"from", "src.out"}}}}},
       {"params", {{"operation", "component"}, {"field", "Polar"}, {"component", 0}, {"keep_input", false}}}},
      {{"id", "volume"}, {"type", "stk.render.volume@1"}, {"inputs", {{"in", {{"from", "component.out"}}}}},
       {"params", {{"colormap", "coolwarm"}}}},
      {{"id", "scene"}, {"type", "stk.view.scene@1"}, {"inputs", {{"layers", Json::array({{{"from", "volume.layer"}}})}}}},
  });
  const Json expected = {
      {"graph", {{"schema", "stk.graph/1"}, {"catalog", {{"stk", 1}}}, {"nodes", nodes}, {"outputs", {{"view", "scene.scene"}}}}},
      {"profile", "desktop"}, {"outputs", Json::array({"view"})},
      {"budget", {{"max_output_bytes", 256 * 1024 * 1024}}}};
  EXPECT_EQ(params.request.dump(), expected.dump());
  EXPECT_EQ(params.eval_id, "hdf5-frame-1");
  EXPECT_EQ(params.mode, "local");
  EXPECT_EQ(params.local_bindings, (std::map<std::string, std::string>{{"run", project.canonical()}}));

  /* Another step is another graph: no reply can stand in for a different selected frame. */
  EXPECT_NE(stk::io::graph_hash(frame_request(project, "Polar", 4).request.at("graph")),
            stk::io::graph_hash(params.request.at("graph")));
}

TEST(MuferroHdf5ViewTest, FrameRequestRefusesASelectorThatIsNotTheExplicitFieldAndStep)
{
  const Project project;
  const std::string long_field = "F" + std::string(64, 'x');
  const std::vector<std::pair<std::string, std::string>> cases = {
      {"/t00000002/Polar", "Strain"},     {"/t00000002/Strain", "Polar"},  {"/t2/Polar", "Polar"},
      {"/t00000002/Polar\n", "Polar"},    {"latest", "Polar"},             {"", "Polar"},
      {"/t0000000x/Polar", "Polar"},      {"t00000002/Polar", "Polar"},    {"/T00000002/Polar", "Polar"},
      {"/t00000002Polar", "Polar"},       {"/t00000002/Polar/x", "Polar"}, {"/t-0000002/Polar", "Polar"},
      {"/t00000002/9x", "9x"},            {"/t00000002/_x", "_x"},         {"/t00000002/Po-lar", "Po-lar"},
      {"/t00000002/", ""},                {selector(long_field, 2), long_field},
  };
  for (const auto &[sel, field] : cases) {
    EXPECT_THROW(stk::app::muferro_hdf5_frame_request("x", project.str(), kRun, sel, field, kSha),
                 std::invalid_argument)
        << sel << " / " << field;
  }
  const std::string widest = "F" + std::string(63, 'x');
  EXPECT_NO_THROW(stk::app::muferro_hdf5_frame_request("x", project.str(), kRun, selector(widest, 99999999), widest, kSha));
  EXPECT_NO_THROW(stk::app::muferro_hdf5_frame_request("x", project.str(), kRun, "/t00000000/S_2", "S_2", kSha));
}

TEST(MuferroHdf5ViewTest, VoxelRequestPinsTheCollectedContainerAndOnlyTheDisplayedComponent)
{
  const Project project;
  const auto source = voxel_source(project);
  const auto request = stk::app::muferro_hdf5_voxel_request("voxel", source, {3, 1, 0});
  const auto &nodes = request.request.at("graph").at("nodes");
  EXPECT_EQ(nodes[0].at("params").at("extent"), Json::array({3, 3, 1, 1, 0, 0}));
  EXPECT_EQ(nodes[0].at("params").at("path"), "case/run.h5");
  EXPECT_EQ(nodes[0].at("params").at("selector"), source.frame.selector);
  EXPECT_EQ(nodes[0].at("params").at("expected_sha256"), kSha);
  EXPECT_EQ(nodes[1].at("params").at("component"), 0);
  EXPECT_EQ(nodes[2].at("params").at("format"), "npy");
  EXPECT_EQ(request.request.at("outputs"), Json::array({"source", "voxel"}));
  const auto &proof = request.local_proofs.at("run");
  EXPECT_EQ(proof.at("project_root"), project.str());
  EXPECT_EQ(proof.at("case_path"), "results/muferro/" + kRun);
  EXPECT_EQ(proof.at("files"), Json::array({{{"path", kPath}, {"sha256", kSha}}}));
  EXPECT_EQ(request.local_bindings.at("run"), stk::core::path_to_utf8(project.root() / "results/muferro" / kRun));
  EXPECT_THROW(stk::app::muferro_hdf5_voxel_request("voxel", source, {4, 0, 0}), std::invalid_argument);
  EXPECT_THROW(stk::app::muferro_hdf5_voxel_request("voxel", source, {-1, 0, 0}), std::invalid_argument);
}

TEST(MuferroHdf5ViewTest, VoxelDecoderKeepsExactIntegersFloatWidthAndNonfiniteValues)
{
  const Project project;
  const auto blob_dir = stk::core::path_to_utf8(project.scratch() / "blobs");
  const stk::io::BlobCache blobs(stk::core::path_from_utf8(blob_dir));
  const std::array<int64_t, 3> position{2, 1, 0};
  const auto check = [&](const char *dtype, const char *descr, uint64_t bits, const char *expected) {
    const auto source = voxel_source(project, dtype);
    const auto request = stk::app::muferro_hdf5_voxel_request("voxel", source, position);
    const auto result = voxel_result(request, source, position, blobs, npy_scalar(descr, bits));
    const auto value = stk::app::decode_muferro_hdf5_voxel(request, reply(result, blob_dir), blob_dir, source, position);
    EXPECT_EQ(value.dtype, dtype);
    EXPECT_EQ(value.value, expected);
  };
  check("uint64", "<u8", UINT64_C(9223372036854775931), "9223372036854775931");
  check("int64", ">i8", std::bit_cast<uint64_t>(INT64_C(-9007199254740993)), "-9007199254740993");
  check("float64", "<f8", std::bit_cast<uint64_t>(1.0000000000000002), "1.0000000000000002");
  check("float64", "<f8", std::bit_cast<uint64_t>(std::numeric_limits<double>::infinity()), "+Inf");
  check("float32", "<f4", std::bit_cast<uint32_t>(std::numeric_limits<float>::quiet_NaN()), "NaN");
}

TEST(MuferroHdf5ViewTest, VoxelDecoderRejectsWrongOriginDtypeFileAndDigest)
{
  const Project project;
  const auto blob_dir = stk::core::path_to_utf8(project.scratch() / "blobs");
  const stk::io::BlobCache blobs(stk::core::path_from_utf8(blob_dir));
  const auto source = voxel_source(project);
  const std::array<int64_t, 3> position{2, 1, 0};
  const auto request = stk::app::muferro_hdf5_voxel_request("voxel", source, position);
  const auto decode = [&](const Json &result) {
    return stk::app::decode_muferro_hdf5_voxel(request, reply(result, blob_dir), blob_dir, source, position);
  };
  const auto good = voxel_result(request, source, position, blobs, npy_scalar("<u8", 42));
  auto wrong = good;
  wrong["outputs"]["source"]["descriptor"]["geometry"]["origin"] = {1, 1, 0};
  EXPECT_THROW(decode(wrong), std::exception);
  wrong = good;
  wrong["outputs"]["source"]["descriptor"]["fields"][0]["dtype"] = "int64";
  EXPECT_THROW(decode(wrong), std::exception);
  wrong = good;
  wrong["outputs"]["voxel"]["size"] = 4097;
  EXPECT_THROW(decode(wrong), std::exception);
  EXPECT_THROW(decode(voxel_result(request, source, position, blobs, npy_scalar("<i8", 42))), std::exception);
  EXPECT_THROW(decode(voxel_result(request, source, position, blobs, npy_scalar("<u8", 42, "(1, 1, 2)"))),
               std::exception);
  ASSERT_NO_FATAL_FAILURE(flip_first_byte(blobs.path_for(good.at("outputs").at("voxel").at("blob").get<std::string>())));
  EXPECT_THROW(decode(good), std::exception);
}

TEST(MuferroHdf5ViewTest, FieldsDecodeTheNodeMetadataInFieldThenNumericStepOrder)
{
  const Project project;
  const auto request = fields_request(project);
  const auto frames = stk::app::decode_muferro_hdf5_fields(request, reply(graph_result(request, "fields",
                                                                                       {{"type", "value"}, {"value", metadata()}})));
  /* The node lists by (step, name); a selector-string sort would also be step-major. */
  EXPECT_EQ(labels(frames), (std::vector<std::string>{"Polar@2=/t00000002/Polar", "Polar@4=/t00000004/Polar",
                                                      "Polar@10=/t00000010/Polar", "Strain@2=/t00000002/Strain",
                                                      "Strain@4=/t00000004/Strain"}));
  /* The same set in another order decodes identically. */
  Json reversed = metadata();
  std::reverse(reversed["fields"].begin(), reversed["fields"].end());
  EXPECT_EQ(labels(stk::app::decode_muferro_hdf5_fields(
                request, reply(graph_result(request, "fields", {{"type", "value"}, {"value", reversed}})))),
            labels(frames));

  Json empty = metadata();
  empty["fields"] = Json::array();
  EXPECT_TRUE(stk::app::decode_muferro_hdf5_fields(
                  request, reply(graph_result(request, "fields", {{"type", "value"}, {"value", empty}})))
                  .empty());
}

TEST(MuferroHdf5ViewTest, FieldsListIsBoundedToTheDropdownAndTheContainerLimit)
{
  const Project project;
  const auto request = fields_request(project);
  const auto decode = [&](const Json &value) {
    return stk::app::decode_muferro_hdf5_fields(request,
                                                reply(graph_result(request, "fields", {{"type", "value"}, {"value", value}})));
  };
  Json full = metadata();
  full["fields"] = Json::array();
  for (int step = 0; step < 128; ++step) {
    full["fields"].push_back(entry("Polar", step));
    full["fields"].push_back(entry("Strain", step, 6, "int16"));
  }
  const auto frames = decode(full);
  ASSERT_EQ(frames.size(), 256u);
  EXPECT_EQ(frames.front().selector, "/t00000000/Polar");
  EXPECT_EQ(frames.back().selector, "/t00000127/Strain");
  Json over = full;
  over["fields"].push_back(entry("Polar", 128));
  EXPECT_THROW(decode(over), std::runtime_error) << "257 choices";

  Json largest = metadata();
  largest["size"] = int64_t(1) << 30;
  EXPECT_EQ(decode(largest).size(), 5u);

  /* The reply is bounded before it is read, at the request's 256 KiB output budget. */
  Json padded = metadata();
  padded["note"] = std::string(256 * 1024, 'x');
  try {
    decode(padded);
    ADD_FAILURE() << "an oversized metadata reply must be refused";
  }
  catch (const std::exception &error) {
    EXPECT_NE(std::string(error.what()).find("byte limit"), std::string::npos) << error.what();
  }
}

TEST(MuferroHdf5ViewTest, FieldsRefuseAnotherContainerOrMalformedChoice)
{
  const Project project;
  const auto request = fields_request(project);
  using Mutation = std::function<void(Json &)>;
  const std::vector<std::pair<std::string, Mutation>> cases = {
      {"other run path", [](Json &v) { v["path"] = "results/muferro/00000000-0000-4000-8000-000000000003/case/run.h5"; }},
      {"case-relative path", [](Json &v) { v["path"] = "case/run.h5"; }},
      {"changed sha", [](Json &v) { v["sha256"] = kOther; }},
      {"uppercase sha", [](Json &v) { v["sha256"] = std::string(64, 'A'); }},
      {"missing sha", [](Json &v) { v.erase("sha256"); }},
      {"DAT reader", [](Json &v) { v["reader"] = "mupro.dat@1"; }},
      {"missing reader", [](Json &v) { v.erase("reader"); }},
      {"zero size", [](Json &v) { v["size"] = 0; }},
      {"negative size", [](Json &v) { v["size"] = -1; }},
      {"size over 1 GiB", [](Json &v) { v["size"] = (int64_t(1) << 30) + 1; }},
      {"size string", [](Json &v) { v["size"] = "6328"; }},
      {"size float", [](Json &v) { v["size"] = 6328.0; }},
      {"missing size", [](Json &v) { v.erase("size"); }},
      {"fields object", [](Json &v) { v["fields"] = Json::object(); }},
      {"missing fields", [](Json &v) { v.erase("fields"); }},
      {"value not an object", [](Json &v) { v = Json::array(); }},
      {"selector step differs", [](Json &v) { v["fields"][0]["step"] = 4; }},
      {"selector field differs", [](Json &v) { v["fields"][0]["name"] = "Strain"; }},
      {"float step", [](Json &v) { v["fields"][0]["step"] = 2.0; }},
      {"string step", [](Json &v) { v["fields"][0]["step"] = "2"; }},
      {"missing step", [](Json &v) { v["fields"][0].erase("step"); }},
      {"negative step", [](Json &v) { v["fields"][0]["step"] = -2; }},
      {"huge unsigned step", [](Json &v) { v["fields"][0]["step"] = uint64_t(-1); }},
      {"short selector", [](Json &v) { v["fields"][0]["selector"] = "/t2/Polar"; }},
      {"selector newline", [](Json &v) { v["fields"][0]["selector"] = "/t00000002/Polar\n"; }},
      {"selector latest", [](Json &v) { v["fields"][0]["selector"] = "latest"; }},
      {"missing selector", [](Json &v) { v["fields"][0].erase("selector"); }},
      {"missing name", [](Json &v) { v["fields"][0].erase("name"); }},
      {"name starts with digit", [](Json &v) { v["fields"][0] = entry("9x", 2); }},
      {"name over 64", [](Json &v) { v["fields"][0] = entry("F" + std::string(64, 'x'), 2); }},
      {"entry not an object", [](Json &v) { v["fields"][0] = 2; }},
      {"duplicate field and step", [](Json &v) { v["fields"].push_back(entry("Polar", 4)); }},
  };
  for (const auto &[label, mutate] : cases) {
    Json value = metadata();
    mutate(value);
    EXPECT_THROW(stk::app::decode_muferro_hdf5_fields(
                     request, reply(graph_result(request, "fields", {{"type", "value"}, {"value", value}}))),
                 std::exception)
        << label;
  }
}

TEST(MuferroHdf5ViewTest, ResultMustBeThisRequestsStrictDesktopGraph)
{
  const Project project;
  const auto request = fields_request(project);
  const Json output = {{"type", "value"}, {"value", metadata()}};
  const auto other = stk::app::muferro_hdf5_fields_request("hdf5-fields-1", project.str(), kRun, kOther);
  using Mutation = std::function<void(Json &)>;
  const std::vector<std::pair<std::string, Mutation>> cases = {
      {"schema", [](Json &r) { r["schema"] = "stk.graph-result/2"; }},
      {"web profile", [](Json &r) { r["profile"] = "web"; }},
      {"missing profile", [](Json &r) { r.erase("profile"); }},
      {"other graph", [&](Json &r) {
         const auto hash = stk::io::graph_hash(other.request.at("graph"));
         r["graph_hash"] = hash;
         r["graph_sha256"] = hash.substr(7);
       }},
      {"sha256 differs from hash", [](Json &r) { r["graph_sha256"] = kOther; }},
      {"missing graph_sha256", [](Json &r) { r.erase("graph_sha256"); }},
      {"node errors", [](Json &r) { r["errors"] = Json::array({{{"code", "invalid_data"}, {"message", "x"}}}); }},
      {"errors object", [](Json &r) { r["errors"] = Json::object(); }},
      {"extra output", [&](Json &r) { r["outputs"]["view"] = output; }},
      {"renamed output", [&](Json &r) { r["outputs"] = {{"result", output}}; }},
      {"no outputs", [](Json &r) { r.erase("outputs"); }},
      {"payload output", [](Json &r) { r["outputs"]["fields"]["type"] = "payload"; }},
      {"not an object", [](Json &r) { r = nullptr; }},
  };
  for (const auto &[label, mutate] : cases) {
    Json result = graph_result(request, "fields", output);
    mutate(result);
    EXPECT_THROW(stk::app::decode_muferro_hdf5_fields(request, reply(result)), std::exception) << label;
  }
  /* A hub review action is never a local metadata reply. */
  auto pending = reply(graph_result(request, "fields", output));
  pending.action = stk::bridge::HubActionSummary{};
  EXPECT_THROW(stk::app::decode_muferro_hdf5_fields(request, pending), std::runtime_error);
  /* An omitted errors member is accepted; the strict bridge may drop the empty list. */
  Json without_errors = graph_result(request, "fields", output);
  without_errors.erase("errors");
  EXPECT_EQ(stk::app::decode_muferro_hdf5_fields(request, reply(without_errors)).size(), 5u);
}

TEST(MuferroHdf5ViewTest, FrameDecodesAnOwnedVolumeFromTheAnnouncedCache)
{
  const Project project;
  const VolumeScene scene;
  const auto blobs = scene.store(project.scratch() / "blobs");
  const auto blob_dir = stk::core::path_to_utf8(blobs);
  const auto request = frame_request(project);
  const auto payload = stk::app::decode_muferro_hdf5_frame(
      request, reply(graph_result(request, "view", scene.output()), blob_dir), blob_dir);
  ASSERT_NE(payload, nullptr);
  const Json *volume = payload->layer("volume");
  ASSERT_NE(volume, nullptr);
  EXPECT_EQ(volume->at("type"), "volume");
  EXPECT_EQ(volume->at("value_range"), Json::array({0.0, 69.0}));
  EXPECT_FALSE(payload->skipped("volume"));
  EXPECT_EQ(payload->floats("vol"), scene.voxels);
  ASSERT_EQ(payload->buffers.size(), 2u);
  for (const auto &buffer : payload->buffers) {
    EXPECT_FALSE(buffer.bytes.mapped()) << buffer.sha256;
    EXPECT_EQ(stk::core::Sha256::hex(buffer.bytes.span()), buffer.sha256);
  }
  /* The Viewer holds the verified bytes: rewriting the cache file afterwards changes nothing it shows. */
  const auto vol_sha = scene.sha("vol");
  ASSERT_NO_FATAL_FAILURE(flip_first_byte(stk::io::BlobCache(blobs).path_for(vol_sha)));
  EXPECT_EQ(payload->floats("vol"), scene.voxels);
  for (const auto &buffer : payload->buffers) {
    EXPECT_EQ(stk::core::Sha256::hex(buffer.bytes.span()), buffer.sha256);
  }
  /* The same rewrite is refused on the next decode. */
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, reply(graph_result(request, "view", scene.output()), blob_dir),
                                                   blob_dir),
               std::exception);
}

TEST(MuferroHdf5ViewTest, FrameRefusesAnotherCacheRootOrRequest)
{
  const Project project;
  const VolumeScene scene;
  const auto blob_dir = stk::core::path_to_utf8(scene.store(project.scratch() / "blobs"));
  /* A second cache with the same valid bytes is still not the bridge's announced cache. */
  const auto copy_dir = stk::core::path_to_utf8(scene.store(project.scratch() / "copy"));
  const auto request = frame_request(project);
  const Json result = graph_result(request, "view", scene.output());
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, reply(result, copy_dir), blob_dir), std::runtime_error);
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, reply(result, blob_dir), copy_dir), std::runtime_error);
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, reply(result, ""), blob_dir), std::runtime_error);
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, reply(result, "blobs"), "blobs"), std::runtime_error);
  const auto missing = stk::core::path_to_utf8(project.scratch() / "missing");
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, reply(result, missing), missing), std::exception);

  /* A valid payload hashed for another frame, or for the metadata request, belongs to another graph. */
  const auto step4 = frame_request(project, "Polar", 4);
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(
                   request, reply(graph_result(step4, "view", scene.output()), blob_dir), blob_dir),
               std::runtime_error);
  const auto fields = fields_request(project);
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(
                   request, reply(graph_result(fields, "view", scene.output()), blob_dir), blob_dir),
               std::runtime_error);
  EXPECT_THROW(stk::app::decode_muferro_hdf5_fields(
                   fields, reply(graph_result(request, "fields", {{"type", "value"}, {"value", metadata()}}))),
               std::runtime_error);
  auto pending = reply(result, blob_dir);
  pending.action = stk::bridge::HubActionSummary{};
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, pending, blob_dir), std::runtime_error);
}

TEST(MuferroHdf5ViewTest, FrameRefusesAnInvalidOrUndisplayablePayload)
{
  const Project project;
  const VolumeScene scene;
  const auto blobs = scene.store(project.scratch() / "blobs");
  const auto blob_dir = stk::core::path_to_utf8(blobs);
  const auto request = frame_request(project);
  using Mutation = std::function<void(Json &)>;
  const std::vector<std::pair<std::string, Mutation>> cases = {
      {"value output", [](Json &o) { o["type"] = "value"; }},
      {"manifest schema", [](Json &o) { o["manifest"]["schema"] = "stk.payload/1"; }},
      {"manifest not an object", [](Json &o) { o["manifest"] = Json::array(); }},
      {"missing manifest", [](Json &o) { o.erase("manifest"); }},
      {"no volume layer", [](Json &o) { o["manifest"]["layers"][0]["id"] = "density"; }},
      {"volume id of an unknown type is skipped", [](Json &o) { o["manifest"]["layers"][0]["type"] = "volume_v9"; }},
      {"declared buffer over 256 MiB", [](Json &o) {
         o["manifest"]["buffers"][1]["byteLength"] = (int64_t(256) << 20) + 1;
       }},
      {"buffer lengths disagree", [](Json &o) {
         auto copy = o["manifest"]["buffers"][1];
         copy["id"] = "b_vol_copy";
         copy["byteLength"] = 4;
         o["manifest"]["buffers"].push_back(copy);
       }},
      {"blob absent", [](Json &o) {
         const std::string absent(64, 'c');
         o["manifest"]["buffers"][1]["sha256"] = absent;
         o["manifest"]["buffers"][1]["uri"] = "sha256:" + absent;
       }},
  };
  for (const auto &[label, mutate] : cases) {
    Json output = scene.output();
    mutate(output);
    EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, reply(graph_result(request, "view", output), blob_dir),
                                                     blob_dir),
                 std::exception)
        << label;
  }
  /* The declared size is checked before any blob is read. */
  Json oversized = scene.output();
  oversized["manifest"]["buffers"][1]["byteLength"] = (int64_t(256) << 20) + 1;
  try {
    stk::app::decode_muferro_hdf5_frame(request, reply(graph_result(request, "view", oversized), blob_dir), blob_dir);
    ADD_FAILURE() << "an oversized buffer must be refused";
  }
  catch (const std::exception &error) {
    EXPECT_NE(std::string(error.what()).find("byte limit"), std::string::npos) << error.what();
  }
  /* A same-size rewrite of a cached blob fails the digest of the exact bytes read. */
  ASSERT_NO_FATAL_FAILURE(flip_first_byte(stk::io::BlobCache(blobs).path_for(scene.sha("lut"))));
  EXPECT_THROW(stk::app::decode_muferro_hdf5_frame(request, reply(graph_result(request, "view", scene.output()), blob_dir),
                                                   blob_dir),
               std::exception);
}
