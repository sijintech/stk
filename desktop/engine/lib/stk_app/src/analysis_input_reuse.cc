/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_input_reuse.hh"

#include "stk/core/utf8.hh"
#include "stk/io/graph.hh"

#include <limits>
#include <map>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace stk::app {
namespace {
using io::Json;
constexpr uint64_t max_input_bytes = 256 * 1024 * 1024;
constexpr uint64_t max_snapshot_file_bytes = uint64_t(1) << 40;
constexpr uint64_t max_revision = uint64_t(std::numeric_limits<int64_t>::max());

void require(const bool condition, const char *message)
{
  if (!condition) { throw std::invalid_argument(message); }
}

bool hex(const char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); }

bool uuid(const std::string_view value)
{
  if (value.size() != 36) { return false; }
  for (size_t i = 0; i < value.size(); ++i) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (value[i] != '-') { return false; }
    }
    else if (!hex(value[i])) { return false; }
  }
  return true;
}

bool sha(const std::string_view value)
{
  if (value.size() != 64) { return false; }
  for (const char c : value) { if (!hex(c)) { return false; } }
  return true;
}

const Json &member(const Json &value, const char *key)
{
  require(value.is_object(), "Input reuse metadata requires an object");
  const auto it = value.find(key);
  require(it != value.end(), "Input reuse metadata is missing a required field");
  return *it;
}

const std::string &string(const Json &object, const char *key, const size_t max_bytes)
{
  const auto &value = member(object, key);
  require(value.is_string(), "Input reuse metadata requires a string");
  const auto &text = value.get_ref<const std::string &>();
  require(!text.empty() && text.size() <= max_bytes && core::utf8::is_valid(text) &&
      text.find('\0') == std::string::npos, "Input reuse text must be bounded valid UTF-8");
  return text;
}

const std::string &identity(const Json &object, const char *key)
{
  const auto &value = string(object, key, 36);
  require(uuid(value), "Input reuse identities must be canonical UUIDs");
  return value;
}

const std::string &digest(const Json &object, const char *key)
{
  const auto &value = string(object, key, 64);
  require(sha(value), "Input reuse digests must be lowercase SHA-256");
  return value;
}

uint64_t integer(const Json &value, const uint64_t maximum)
{
  require(value.is_number_integer(), "Input reuse counts and revisions must be integers");
  if (value.is_number_unsigned()) {
    const auto result = value.get<uint64_t>();
    require(result <= maximum, "Input reuse count or revision exceeds its limit");
    return result;
  }
  const auto result = value.get<int64_t>();
  require(result >= 0 && uint64_t(result) <= maximum, "Input reuse count or revision exceeds its limit");
  return uint64_t(result);
}

void relative_path(const std::string &path)
{
  require(!path.empty() && path.size() <= 1024 && core::utf8::is_valid(path),
          "Input reuse requires bounded UTF-8 relative paths");
  // The stored run already passed the backend's complete portable/casefold collision policy.
  // Keep basic path syntax bounded here; no filesystem interpretation or normalization occurs.
  size_t start = 0;
  while (start <= path.size()) {
    const auto slash = path.find('/', start);
    const auto part = std::string_view(path).substr(start,
        slash == std::string::npos ? std::string::npos : slash - start);
    require(!part.empty() && part != "." && part != ".." && part.size() <= 255 &&
        part.back() != ' ' && part.back() != '.', "Input reuse paths must have portable relative components");
    for (const unsigned char c : part) {
      require(c >= 32 && c != 127 && std::string_view("\\:<>\"|?*").find(char(c)) == std::string_view::npos,
              "Input reuse paths must have portable relative components");
    }
    if (slash == std::string::npos) { break; }
    start = slash + 1;
  }
}

void check_bindings(const Json &bindings)
{
  require(bindings.is_object() && !bindings.empty() && bindings.size() <= 32,
          "Input reuse requires 1 to 32 binding groups");
  size_t count = 0;
  uint64_t total = 0;
  for (const auto &[name, files] : bindings.items()) {
    require(io::is_graph_id(name), "Input reuse binding names must be graph identifiers");
    require(files.is_object() && !files.empty() && files.size() <= 100 - count,
            "Input reuse requires 1 to 100 explicit file mappings");
    count += files.size();
    for (const auto &[path, file] : files.items()) {
      relative_path(path);
      require(file.is_object() && file.size() == 3, "Invalid frozen input file metadata");
      (void)identity(file, "record_id"); (void)digest(file, "sha256");
      total += integer(member(file, "size"), max_input_bytes - total);
    }
  }
}

void check_plan(const AnalysisInputReusePlan &plan)
{
  require(uuid(plan.project_id) && uuid(plan.run_id) && uuid(plan.analysis_id) && uuid(plan.snapshot_id),
          "Input reuse identities must be canonical UUIDs");
  require(sha(plan.plan_sha256) && sha(plan.snapshot_sha256), "Input reuse digests must be lowercase SHA-256");
  require(plan.source_revision >= 0, "Input reuse requires a nonnegative source revision");
  check_bindings(plan.bindings);
}
}  // namespace

AnalysisInputReusePlan analysis_input_reuse_plan(const Json &run, const std::string &project_id)
{
  require(uuid(project_id), "Input reuse requires the current project UUID");
  const auto &project = identity(run, "project_id");
  require(project == project_id, "The analysis run belongs to another project");
  const auto &id = identity(run, "id");
  const auto &analysis = identity(run, "analysis_id");
  const auto &snapshot = identity(run, "snapshot_id");
  const auto &plan_hash = digest(run, "plan_sha256");
  const auto &snapshot_hash = digest(run, "snapshot_sha256");
  const auto revision = integer(member(run, "source_revision"), max_revision);
  const auto &bindings = member(run, "bindings");
  check_bindings(bindings);
  // Copy only after every consumed subtree has passed bounded checks.
  return {project, id, analysis, plan_hash, snapshot, snapshot_hash, int64_t(revision), bindings};
}

AnalysisReusedInputs analysis_reused_inputs(const AnalysisInputReusePlan &plan, const Json &snapshot)
{
  check_plan(plan); // Public structs can be changed after initial extraction.
  require(identity(snapshot, "id") == plan.snapshot_id && digest(snapshot, "sha256") == plan.snapshot_sha256,
          "The input snapshot identity or hash differs from the frozen run");
  require(string(snapshot, "kind", 16) == "files", "Input reuse requires a file snapshot");
  const auto snapshot_revision = integer(member(snapshot, "revision"), max_revision);
  require(snapshot_revision <= uint64_t(plan.source_revision), "The input snapshot is newer than the frozen run");
  const auto &manifest = member(snapshot, "manifest");
  require(integer(member(manifest, "format"), 1) == 1 && string(manifest, "kind", 16) == "files" &&
      identity(manifest, "project_id") == plan.project_id, "Input snapshot manifest identity or format differs");
  require(integer(member(manifest, "source_revision"), max_revision) <= snapshot_revision,
          "The input snapshot source revision is inconsistent");
  const auto &files = member(manifest, "files");
  require(files.is_array() && !files.empty() && files.size() <= 100, "Input snapshots require 1 to 100 files");
  // Borrowed keys and rows remain valid for the duration of this call; no unbounded snapshot
  // strings, original paths/locations, timestamps or unknown fields are copied.
  std::map<std::string_view, const Json *> by_id;
  for (const auto &file : files) {
    const auto &id = identity(file, "record_id");
    require(by_id.emplace(id, &file).second, "The input snapshot contains duplicate record UUIDs");
    (void)string(file, "name", 1024); (void)digest(file, "sha256");
    (void)integer(member(file, "size"), max_snapshot_file_bytes);
  }
  for (const auto &binding : plan.bindings) {
    for (const auto &file : binding) {
      const auto found = by_id.find(file.at("record_id").get_ref<const std::string &>());
      require(found != by_id.end(), "A frozen input mapping is missing from its snapshot");
      const auto &saved = *found->second;
      require(saved.at("sha256") == file.at("sha256") &&
          integer(saved.at("size"), max_snapshot_file_bytes) == integer(file.at("size"), max_input_bytes),
          "A frozen input mapping differs from its snapshot hash or size");
    }
  }
  AnalysisReusedInputs result{plan.project_id, plan.run_id, plan.analysis_id, plan.plan_sha256,
      plan.snapshot_id, plan.snapshot_sha256, int64_t(snapshot_revision), Json::object(), Json::array()};
  for (const auto &[name, entries] : plan.bindings.items()) {
    Json mapping = Json::object();
    for (const auto &[path, file] : entries.items()) { mapping[path] = file.at("record_id"); }
    result.bindings[name] = std::move(mapping);
  }
  for (const auto &file : files) {
    result.files.push_back({{"record_id", file.at("record_id")}, {"name", file.at("name")},
        {"sha256", file.at("sha256")}, {"size", file.at("size")}});
  }
  return result;
}

}  // namespace stk::app
