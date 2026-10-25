/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_reports.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/io/graph.hh"

#include <algorithm>
#include <filesystem>
#include <set>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
constexpr int64_t max_asset_bytes = 4 * 1024 * 1024;
void require(bool condition, const char *message)
{
  if (!condition) { throw std::runtime_error(message); }
}
bool valid_summary(const Json &item)
{
  if (!item.is_object() || !canonical_uuid(io::get_string(item, "id")) ||
      !item.contains("name") || !(item.at("name").is_string() || item.at("name").is_null()) ||
      !item.contains("format") || !(item.at("format").is_string() || item.at("format").is_null()) ||
      !item.contains("error") || !item.at("error").is_string()) { return false; }
  const auto state = io::get_string(item, "state");
  return state == "invalid" || (state == "readable" && item.at("name").is_string() &&
      io::get_string(item, "format") == "stk.report/1" &&
      core::is_sha256_hex(io::get_string(item, "source_sha256")));
}
bool valid_path(const std::string &path)
{
  if (path.empty() || path.size() > 1024 || path.front() == '/' || path.find('\\') != std::string::npos ||
      !core::utf8::is_valid(path)) { return false; }
  size_t start = 0;
  while (start <= path.size()) {
    const auto end = path.find('/', start);
    const auto part = path.substr(start, end == std::string::npos ? end : end - start);
    if (part.empty() || part == "." || part == "..") { return false; }
    for (const unsigned char c : part) { if (c < 32 || c == 127 || c == ':') { return false; } }
    if (end == std::string::npos) { break; }
    start = end + 1;
  }
  return true;
}
void validate_manifest(const Json &manifest, const std::string &project, const std::string &digest, int64_t revision)
{
  check_analysis_json_bounds(manifest);
  require(manifest.is_object() && manifest.size() == 8 && io::get_string(manifest, "format") == "stk.report/1" &&
      io::get_string(manifest, "project_id") == project &&
      canonical_uuid(io::get_string(manifest, "snapshot_id")) &&
      core::is_sha256_hex(io::get_string(manifest, "snapshot_sha256")) &&
      io::get_int(manifest, "source_revision", -1) >= 0 &&
      io::get_int(manifest, "source_revision", -1) <= revision &&
      manifest.contains("assets") && manifest.at("assets").is_array() &&
      !manifest.at("assets").empty() && manifest.at("assets").size() <= 64 &&
      manifest.contains("sources") && manifest.at("sources").is_array() &&
      manifest.at("sources").size() <= 16, "Invalid report manifest");
  std::set<std::string> paths, records;
  int64_t total = 0;
  for (const auto &asset : manifest.at("assets")) {
    const auto path = io::get_string(asset, "path"), record = io::get_string(asset, "record_id");
    const auto size = io::get_int(asset, "size", -1);
    require(asset.is_object() && asset.size() == 5 && valid_path(path) && canonical_uuid(record) &&
        paths.insert(path).second && records.insert(record).second &&
        core::is_sha256_hex(io::get_string(asset, "sha256")) && size >= 0 && size <= max_asset_bytes &&
        !io::get_string(asset, "mime").empty(), "Invalid report asset manifest");
    total += size;
  }
  require(total <= 32 * 1024 * 1024 && paths.contains(io::get_string(manifest, "entry_path")),
          "Invalid report entry or total asset size");
  std::set<std::pair<std::string, std::string>> sources;
  for (const auto &source : manifest.at("sources")) {
    const auto kind = io::get_string(source, "kind"), id = io::get_string(source, "id");
    const auto source_revision = io::get_int(source, "source_revision", -1);
    require(source.is_object() && source.size() == 6 && canonical_uuid(id) &&
        io::get_string(source, "project_id") == project && source_revision >= 0 &&
        source_revision <= io::get_int(manifest, "source_revision", -1) && sources.emplace(kind, id).second &&
        (kind == "context" || kind == "simulation_run" || kind == "analysis_run" || kind == "workflow_run"),
        "Invalid frozen report source identity");
    if (kind == "context") {
      require(source.contains("context") && source.at("context").is_object() &&
          io::get_string(source.at("context"), "id") == id &&
          io::get_string(source.at("context"), "project_id") == project &&
          io::get_int(source.at("context"), "source_revision", -1) == source_revision &&
          core::Sha256::hex(io::python_json_dumps(source.at("context"), true, true)) == io::get_string(source, "context_sha256"),
          "Frozen report context does not match its identity or checksum");
    }
    else {
      require(core::is_sha256_hex(io::get_string(source, "plan_sha256")) &&
          source.contains("captured_status") && source.at("captured_status").is_object(), "Invalid frozen report run source");
    }
  }
  require(core::Sha256::hex(io::python_json_dumps(manifest, true, true)) == digest,
          "Report manifest checksum does not match its source version");
}
// The shared decoder accepts unpadded input. Report receipts use canonical RFC 4648 base64,
// including zero unused bits; reject alternative encodings before allocating the bytes.
bool canonical_base64(const std::string &text, size_t size)
{
  if (text.size() != ((size + 2) / 3) * 4) { return false; }
  if (text.empty()) { return size == 0; }
  const size_t padding = size % 3 ? 3 - size % 3 : 0;
  const std::string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  for (size_t i = 0; i < text.size() - padding; ++i) {
    if (alphabet.find(text[i]) == std::string::npos) { return false; }
  }
  for (size_t i = text.size() - padding; i < text.size(); ++i) { if (text[i] != '=') { return false; } }
  if (padding) {
    const auto last = alphabet.find(text[text.size() - padding - 1]);
    if ((last & (padding == 2 ? 15 : 3)) != 0) { return false; }
  }
  return true;
}
bool same_output_path(const std::string &receipt, const std::string &requested)
{
  auto source = core::path_from_utf8(requested).lexically_normal();
  const auto target = core::path_from_utf8(receipt).lexically_normal();
  if (source == target) { return true; }
#ifdef __APPLE__
  // The backend canonicalizes only Darwin's verified standard aliases. Do not resolve
  // arbitrary user symlinks before sending the request (that would bypass its path gate).
  for (const char *name : {"var", "tmp", "etc"}) {
    const auto alias = std::filesystem::path("/") / name;
    const auto relative = source.lexically_relative(alias);
    if (relative.empty() || relative.is_absolute() || *relative.begin() == "..") { continue; }
    std::error_code error;
    const auto link = std::filesystem::read_symlink(alias, error);
    const auto physical = std::filesystem::path("/private") / name;
    if (!error && (link.is_absolute() ? link : alias.parent_path() / link).lexically_normal() == physical &&
        (physical / relative).lexically_normal() == target) { return true; }
  }
#endif
  return false;
}
}  // namespace

ProjectReports::ProjectReports(AppStore &store) : store_(store), project_(store.project()) { sync(); }
ProjectReports::~ProjectReports()
{
  *alive_ = false;
  if (exporting_) { store_.log("Report export reply unavailable; inspect the chosen destination before exporting again"); }
  if (future_) { future_->cancel(); }
}
void ProjectReports::changed() { ++version_; store_.changed(); }
void ProjectReports::clear_asset()
{
  ++asset_version_; asset_loaded_ = false; asset_mime_.clear(); asset_bytes_.clear();
}
void ProjectReports::reset()
{
  ++epoch_; ++request_;
  if (exporting_) { store_.log("Report export reply unavailable; inspect the chosen destination before exporting again"); }
  busy_ = exporting_ = false;
  page_ = selected_ = export_receipt_ = nullptr;
  asset_path_.clear(); clear_asset(); error_.clear(); notice_.clear();
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
  changed();
}
void ProjectReports::clear() { reset(); }
void ProjectReports::sync()
{
  project_.sync();
  auto *client = store_.bridge();
  const auto *project = project_.project() ? &*project_.project() : nullptr;
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  const std::string handle = project ? project->handle : std::string(), id = project ? project->id : std::string();
  const int64_t revision = project ? project->revision : -1;
  if (client != client_ || session != session_ || handle != handle_ || id != project_id_ || revision != revision_) {
    client_ = client; session_ = session; handle_ = handle; project_id_ = id; revision_ = revision;
    reset();
  }
}
bool ProjectReports::supports(const std::string &method) const
{
  if (store_.bridge() != client_ || !client_ || !project_.ready() || !project_.loaded() ||
      !project_.project() || project_.project()->handle != handle_ ||
      project_.project()->id != project_id_ || project_.project()->revision != revision_ || session_.empty()) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method(method);
}
bool ProjectReports::supported() const
{
  return supports("project.reports.list") && supports("project.reports.get");
}
bool ProjectReports::call(const std::string &method, Json params,
                          std::function<void(const Json &)> done, bool exporting)
{
  sync();
  if (!supports(method) || busy_ || project_.busy()) { return false; }
  params["handle"] = handle_;
  const auto epoch = epoch_, request = ++request_;
  const std::weak_ptr<bool> weak = alive_;
  busy_ = true; exporting_ = exporting; error_.clear(); notice_.clear();
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  future_ = client_->call(method, params, options);
  future_->then([this, weak, epoch, request, exporting, done = std::move(done)](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive) { return; }
    sync();
    if (epoch != epoch_ || request != request_) { return; }
    busy_ = exporting_ = false; future_.reset();
    if (!result) {
      error_ = result.error().describe();
      if (exporting && (result.error().local || result.error().code == bridge::ErrorCode::InternalError ||
                        result.error().code == bridge::ErrorCode::Unknown)) {
        notice_ = "reports.export_check_destination";
      }
      if (result.error().code == bridge::ErrorCode::Conflict) { project_.refresh(); }
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &error) {
        error_ = error.what();
        if (exporting) { notice_ = "reports.export_check_destination"; }
      }
    }
    changed();
  });
  changed(); return true;
}
bool ProjectReports::load_page(int64_t offset)
{
  if (offset < 0) { return false; }
  return call("project.reports.list", {{"offset", offset}, {"limit", 64}}, [this, offset](const Json &result) {
    check_analysis_json_bounds(result, 1024 * 1024);
    if (io::get_int(result, "revision", -1) >= 0 && io::get_int(result, "revision", -1) != revision_) { project_.refresh(); }
    require(result.is_object() && io::get_int(result, "revision", -1) == revision_ &&
        canonical_uuid(io::get_string(result, "table_id")) && io::get_int(result, "offset", -1) == offset &&
        io::get_int(result, "total", -1) >= 0 && result.contains("reports") &&
        result.at("reports").is_array() && result.at("reports").size() <= 64,
        "Invalid or stale report list response");
    std::set<std::string> ids;
    for (const auto &item : result.at("reports")) {
      require(valid_summary(item) && ids.insert(io::get_string(item, "id")).second, "Invalid report summary");
    }
    page_ = result;
  });
}
bool ProjectReports::load(const std::string &id, const std::string &expected)
{
  sync();
  if (!canonical_uuid(id) || (!expected.empty() && !core::is_sha256_hex(expected)) || busy_) { return false; }
  selected_ = export_receipt_ = nullptr; asset_path_.clear(); clear_asset();
  return call("project.reports.get", {{"report_id", id}}, [this, id, expected](const Json &result) {
    check_analysis_json_bounds(result, 400 * 1024);
    if (io::get_int(result, "revision", -1) >= 0 && io::get_int(result, "revision", -1) != revision_) { project_.refresh(); }
    require(result.is_object() && io::get_int(result, "revision", -1) == revision_ &&
        canonical_uuid(io::get_string(result, "table_id")) && result.contains("report") &&
        valid_summary(result.at("report")) && io::get_string(result.at("report"), "id") == id,
        "Invalid or stale report response");
    const auto &item = result.at("report");
    const auto digest = io::get_string(item, "source_sha256");
    require(expected.empty() || digest == expected, "Saved report version changed; explicitly reopen the current report");
    if (io::get_string(item, "state") == "readable") {
      require(item.contains("manifest"), "Missing report manifest");
      validate_manifest(item.at("manifest"), project_id_, digest, revision_);
    }
    selected_ = item;
    if (io::get_string(item, "state") == "readable") { asset_path_ = io::get_string(item.at("manifest"), "entry_path"); }
  });
}
const Json *ProjectReports::selected_asset() const
{
  if (!selected_.is_object() || io::get_string(selected_, "state") != "readable") { return nullptr; }
  for (const auto &asset : selected_.at("manifest").at("assets")) {
    if (io::get_string(asset, "path") == asset_path_) { return &asset; }
  }
  return nullptr;
}
bool ProjectReports::select_asset(const std::string &path)
{
  sync();
  if (busy_ || !selected_.is_object() || io::get_string(selected_, "state") != "readable") { return false; }
  for (const auto &asset : selected_.at("manifest").at("assets")) {
    if (io::get_string(asset, "path") == path) {
      if (asset_path_ != path) { asset_path_ = path; clear_asset(); changed(); }
      return true;
    }
  }
  return false;
}
bool ProjectReports::read_asset()
{
  sync();
  const auto *asset = selected_asset();
  if (!asset || busy_) { return false; }
  const auto entry = *asset;
  const auto id = io::get_string(selected_, "id"), digest = io::get_string(selected_, "source_sha256");
  const auto path = asset_path_;
  clear_asset();
  return call("project.reports.asset", {{"report_id", id}, {"path", path}, {"expected_revision", revision_},
      {"expected_source_sha256", digest}}, [this, id, digest, path, entry](const Json &result) {
    require(result.is_object() && io::get_string(result, "project_id") == project_id_ &&
        io::get_string(result, "report_id") == id && io::get_string(result, "source_sha256") == digest &&
        io::get_string(result, "path") == path && io::get_string(result, "mime") == io::get_string(entry, "mime") &&
        io::get_string(result, "content_sha256") == io::get_string(entry, "sha256") &&
        io::get_int(result, "size", -1) == io::get_int(entry, "size", -2) &&
        result.contains("data") && result.at("data").is_string(), "Report asset receipt differs from its manifest");
    const auto size = size_t(io::get_int(entry, "size", -1));
    const auto &encoded = result.at("data").get_ref<const std::string &>();
    require(canonical_base64(encoded, size), "Invalid report asset base64 encoding");
    auto bytes = bridge::decode_base64(encoded);
    require(bytes && bytes->size() == size && core::Sha256::hex(*bytes) == io::get_string(entry, "sha256"),
            "Report asset bytes do not match the frozen checksum or size");
    const auto mime = io::get_string(entry, "mime");
    if (mime.starts_with("text/")) {
      const std::string_view text(bytes->empty() ? "" : reinterpret_cast<const char *>(bytes->data()), bytes->size());
      require(core::utf8::is_valid(text), "Report text is not valid UTF-8");
      for (size_t i = 0; i < text.size();) {
        const auto cp = core::utf8::decode(text, i); i += cp.length;
        require(!((cp.code_point < 32 && cp.code_point != '\t' && cp.code_point != '\r' && cp.code_point != '\n') ||
                  (cp.code_point >= 127 && cp.code_point <= 159)), "Report text contains control characters");
      }
    }
    asset_bytes_ = std::move(*bytes); asset_mime_ = mime; asset_loaded_ = true; ++asset_version_;
  });
}
bool ProjectReports::export_file(const std::string &destination)
{
  sync();
  if (busy_ || !selected_.is_object() || io::get_string(selected_, "state") != "readable") { return false; }
  if (destination.empty() || destination.size() > 4096 || destination.find('\0') != std::string::npos ||
      !core::utf8::is_valid(destination) || !core::path_from_utf8(destination).is_absolute()) {
    error_ = "Report export requires a valid absolute destination path"; changed(); return false;
  }
  const auto path = core::path_to_utf8(core::path_from_utf8(destination).lexically_normal().make_preferred());
  const auto id = io::get_string(selected_, "id"), digest = io::get_string(selected_, "source_sha256");
  export_receipt_ = nullptr;
  return call("project.reports.export_file", {{"report_id", id}, {"destination", path}, {"expected_revision", revision_},
      {"expected_source_sha256", digest}}, [this, id, digest, path](const Json &result) {
    check_analysis_json_bounds(result, 16 * 1024);
    require(result.is_object() && io::get_string(result, "project_id") == project_id_ &&
        io::get_string(result, "report_id") == id && io::get_string(result, "source_sha256") == digest &&
        same_output_path(io::get_string(result, "path"), path) && core::is_sha256_hex(io::get_string(result, "sha256")) &&
        io::get_int(result, "size", -1) > 0, "Invalid report export receipt; inspect the chosen destination");
    export_receipt_ = result; notice_ = "reports.exported";
  }, true);
}
}  // namespace stk::app
