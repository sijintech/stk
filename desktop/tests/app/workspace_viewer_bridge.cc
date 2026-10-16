/* SPDX-License-Identifier: GPL-2.0-or-later */
/** A synchronous, portable payload bridge for inert workspace restoration tests.
 * No Python, jobs, subprocesses, network, cache simulation or POSIX process-group machinery. */
#include <filesystem>
#include <iostream>
#include <string>

#include "stk/core/paths.hh"
#include "stk/io/json.hh"

namespace fs = std::filesystem;
using stk::io::Json;

int main(int argc, char **argv)
{
  fs::path payload_dir, blob_dir;
  for (int i = 1; i + 1 < argc; ++i) {
    const std::string option = argv[i];
    if (option == "--payload-dir") { payload_dir = stk::core::path_from_utf8(argv[++i]); }
    else if (option == "--blob-dir") { blob_dir = stk::core::path_from_utf8(argv[++i]); }
  }
  if (payload_dir.empty() || blob_dir.empty()) { return 2; }
  auto manifest = stk::io::read_json_file(payload_dir / "manifest.json");
  for (auto &buffer : manifest.at("buffers")) {
    const auto sha = buffer.at("sha256").get<std::string>();
    const auto target = blob_dir / sha.substr(0, 2) / sha;
    fs::create_directories(target.parent_path());
    fs::copy_file(payload_dir / (sha + ".bin"), target, fs::copy_options::overwrite_existing);
    buffer["uri"] = "sha256:" + sha;
  }
  const auto blobs = stk::core::path_to_utf8(blob_dir);
  Json evaluations = Json::array(), probes = Json::array();
  for (std::string line; std::getline(std::cin, line);) {
    const auto request = stk::io::parse_json(line);
    const auto id = request.at("id");
    const auto method = request.at("method").get<std::string>();
    const auto params = request.value("params", Json::object());
    Json result;
    if (method == "hello") {
      result = {{"protocol", 1},
                {"server", {{"name", "stk-workspace-viewer-bridge"}, {"version", "1"},
                            {"python", "none"}, {"platform", "test"}, {"pid", 1}}},
                {"methods", {"hello", "graph.evaluate", "graph.cancel", "probe", "stats"}},
                {"events", Json::array()},
                {"limits", {{"max_line_bytes", 16777216}, {"max_inflight", 64},
                            {"watch_interval_s", 2.0}, {"log_chunk_bytes", 262144},
                            {"transfer_chunk_bytes", 1048576}}},
                {"paths", {{"state_dir", blobs}, {"cache_dir", blobs},
                           {"blob_dir", blobs}, {"download_dir", blobs}}},
                {"resumed_transfers", Json::array()}};
    }
    else if (method == "graph.evaluate") {
      evaluations.push_back(params);
      const auto graph = params.at("request");
      const auto step_parameter = graph.value("parameters", Json::object()).value("step", Json("latest"));
      const int step = step_parameter.is_number() ? step_parameter.get<int>() : step_parameter == "first" ? 0 : 2;
      auto frame = manifest;
      frame["view"]["time"] = {{"step", step}};
      const auto outputs = graph.value("outputs", Json::array({"view"}));
      const auto output = outputs.empty() ? "view" : outputs.at(0).get<std::string>();
      result = {{"result", {{"schema", "stk.graph-result/1"},
                            {"graph_sha256", std::string(64, '0')},
                            {"graph_hash", "sha256:" + std::string(64, '0')},
                            {"profile", graph.value("profile", "desktop")},
                            {"outputs", {{output, {{"type", "payload"}, {"manifest", frame}}}}},
                            {"parameters", {{"step", {{"value", step}, {"choices", {0, 1, 2}}}}}},
                            {"keys", Json::object()}, {"evaluated", Json::array({"scene"})},
                            {"timings", Json::object()}, {"cache", {{"hits", 0}, {"misses", 1}}},
                            {"warnings", Json::array()}}},
                {"blob_dir", blobs}};
    }
    else if (method == "graph.cancel") { result = {{"cancelled", false}}; }
    else if (method == "probe") {
      probes.push_back(params);
      result = {{"target", {{"binding", "run"}, {"path", "Polar.00000002.dat"}}},
                {"sample", {{"values", {0.25, -0.5, 0.75}}, {"units", "unspecified"}}}};
    }
    else if (method == "stats") { result = {{"evaluate_requests", evaluations}, {"probe_requests", probes}}; }
    else {
      std::cout << Json{{"id", id}, {"error", {{"code", "unsupported"},
          {"message", "Unexpected method: " + method}, {"retryable", false}}}}.dump() << std::endl;
      continue;
    }
    std::cout << Json{{"id", id}, {"result", result}}.dump() << std::endl;
  }
}
