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
bool document_mime(const std::string &mime)
{
  return mime == "text/markdown; charset=utf-8" || mime == "text/html; charset=utf-8";
}
bool raster_mime(const std::string &mime)
{
  return mime == "image/png" || mime == "image/jpeg" || mime == "image/gif" || mime == "image/webp";
}
bool same_asset_descriptor(const Json &actual, const Json &expected)
{
  if (!actual.is_object() || actual.size() != 5) { return false; }
  for (const char *key : {"record_id", "path", "mime", "sha256"}) {
    if (io::get_string(actual, key) != io::get_string(expected, key)) { return false; }
  }
  return io::get_int(actual, "size", -1) == io::get_int(expected, "size", -2);
}
std::vector<uint8_t> verified_preview_bytes(const Json &receipt, int64_t size, const std::string &digest)
{
  require(size >= 0 && size <= max_asset_bytes && receipt.contains("data") && receipt.at("data").is_string(),
          "Invalid report preview byte payload");
  const auto &encoded = receipt.at("data").get_ref<const std::string &>();
  require(canonical_base64(encoded, size_t(size)), "Invalid report preview base64 encoding");
  auto bytes = bridge::decode_base64(encoded);
  require(bytes && bytes->size() == size_t(size) && core::Sha256::hex(*bytes) == digest,
          "Report preview bytes do not match their checksum or size");
  return std::move(*bytes);
}
void validate_preview_text(const std::vector<uint8_t> &bytes)
{
  const std::string_view text(bytes.empty() ? "" : reinterpret_cast<const char *>(bytes.data()), bytes.size());
  require(core::utf8::is_valid(text), "Report preview HTML is not valid UTF-8");
  for (size_t i = 0; i < text.size();) {
    const auto cp = core::utf8::decode(text, i); i += cp.length;
    require(!((cp.code_point < 32 && cp.code_point != '\t' && cp.code_point != '\r' && cp.code_point != '\n') ||
              (cp.code_point >= 127 && cp.code_point <= 159)), "Report preview HTML contains control characters");
  }
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

struct ProjectReports::PreviewPreparation {
  PreparedReportPreview result;
  Json manifest_assets, resources;
  size_t next_resource = 0;
  int64_t total_size = 0, received_size = 0;
};

ProjectReports::ProjectReports(AppStore &store) : store_(store), project_(store.project()) { sync(); }
ProjectReports::~ProjectReports()
{
  *alive_ = false;
  if (exporting_) { store_.log("Report export reply unavailable; inspect the chosen destination before exporting again"); }
  if (future_) { future_->cancel(); }
  if (preview_future_) { preview_future_->cancel(); }
}
void ProjectReports::changed() { ++version_; store_.changed(); }
void ProjectReports::clear_asset()
{
  ++asset_version_; asset_loaded_ = false; asset_mime_.clear(); asset_bytes_.clear();
}
void ProjectReports::reset()
{
  ++epoch_; ++request_;
  clear_preview();
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
  clear_preview();
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

void ProjectReports::clear_preview()
{
  ++preview_generation_; ++preview_request_; ++preview_version_;
  preview_busy_ = false; preview_error_.clear();
  preview_pending_.reset(); prepared_preview_.reset();
  auto old = std::move(preview_future_); preview_future_.reset();
  if (old) { old->cancel(); }
  changed();
}
void ProjectReports::fail_preview(const std::string &error)
{
  clear_preview(); preview_error_ = error; changed();
}
bool ProjectReports::preview_call(const std::string &method, Json params,
                                  std::function<void(const Json &)> done)
{
  sync();
  if (!preview_pending_ || !preview_busy_ || !supports(method) || project_.busy()) { return false; }
  params["handle"] = handle_;
  const auto epoch = epoch_, generation = preview_generation_, request = ++preview_request_;
  const auto project = project_id_, handle = handle_, session = session_;
  const auto revision = revision_;
  const auto report = preview_pending_->result.identity.report_id;
  const auto digest = preview_pending_->result.identity.source_sha256;
  const auto *client = client_;
  const std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  preview_future_ = client_->call(method, params, options);
  preview_future_->then([this, weak, epoch, generation, request, project, handle, session, revision,
                        report, digest, client, done = std::move(done)](bridge::Result<Json> result) {
    const auto alive = weak.lock(); if (!alive || !*alive) { return; }
    sync();
    if (epoch != epoch_ || generation != preview_generation_ || request != preview_request_) { return; }
    if (!preview_pending_ || client != client_ || project != project_id_ || handle != handle_ ||
        session != session_ || revision != revision_ || io::get_string(selected_, "id") != report ||
        io::get_string(selected_, "source_sha256") != digest) {
      clear_preview(); return;
    }
    preview_future_.reset();
    if (!result) {
      fail_preview(result.error().describe());
      if (result.error().code == bridge::ErrorCode::Conflict) { project_.refresh(); }
      return;
    }
    try { done(result.value()); }
    catch (const std::exception &error) { fail_preview(error.what()); }
    changed();
  });
  changed(); return true;
}
bool ProjectReports::prepare_preview()
{
  sync();
  if (busy_ || preview_busy_ || project_.busy()) { return false; }
  clear_preview();
  if (!supports("project.reports.preview_resources") || !supports("project.reports.asset")) {
    preview_error_ = "This bridge does not support frozen report resource previews"; changed(); return false;
  }
  if (!selected_.is_object() || io::get_string(selected_, "state") != "readable") {
    preview_error_ = "Select a readable report before preparing its preview"; changed(); return false;
  }
  const auto &manifest = selected_.at("manifest");
  const auto entry_path = io::get_string(manifest, "entry_path");
  const auto &assets = manifest.at("assets");
  const auto entry = std::find_if(assets.begin(), assets.end(), [&](const Json &asset) {
    return io::get_string(asset, "path") == entry_path;
  });
  if (entry == assets.end() || !document_mime(io::get_string(*entry, "mime")) ||
      io::get_int(*entry, "size", -1) > 1024 * 1024) {
    preview_error_ = "Resource preview requires a Markdown or HTML entry within 1 MiB"; changed(); return false;
  }
  preview_pending_ = std::make_unique<PreviewPreparation>();
  preview_pending_->manifest_assets = assets;
  preview_pending_->result.identity = {project_id_, io::get_string(selected_, "id"),
                                      io::get_string(selected_, "source_sha256"), {}};
  preview_pending_->result.entry_path = entry_path;
  preview_busy_ = true;
  const auto &identity = preview_pending_->result.identity;
  if (!preview_call("project.reports.preview_resources", {{"report_id", identity.report_id},
      {"expected_revision", revision_}, {"expected_source_sha256", identity.source_sha256}},
      [this](const Json &result) { accept_preview(result); })) {
    fail_preview("Report preview selection is no longer available"); return false;
  }
  return true;
}
void ProjectReports::accept_preview(const Json &result)
{
  check_analysis_json_bounds(result, 6 * 1024 * 1024);
  require(preview_pending_ && result.is_object() && result.size() == 3 &&
      result.contains("preview") && result.at("preview").is_object() && result.at("preview").size() == 14 &&
      result.contains("resources") && result.at("resources").is_array() && result.at("resources").size() <= 63,
      "Invalid report resource preparation response");
  auto &pending = *preview_pending_;
  const auto &preview = result.at("preview");
  const auto &identity = pending.result.identity;
  const auto entry = std::find_if(pending.manifest_assets.begin(), pending.manifest_assets.end(), [&](const Json &asset) {
    return io::get_string(asset, "path") == pending.result.entry_path;
  });
  require(entry != pending.manifest_assets.end(), "The report entry is missing from its manifest");
  const auto session = io::get_string(preview, "session_id");
  const auto display_sha = io::get_string(preview, "content_sha256");
  const auto display_size = io::get_int(preview, "size", -1);
  const auto source_size = io::get_int(preview, "source_size", -1);
  require(io::get_int(preview, "revision", -1) == revision_ &&
      io::get_string(preview, "project_id") == identity.project_id &&
      io::get_string(preview, "report_id") == identity.report_id &&
      io::get_string(preview, "source_sha256") == identity.source_sha256 && canonical_uuid(session) &&
      io::get_string(preview, "path") == pending.result.entry_path &&
      io::get_string(preview, "renderer") == "stk.report-renderer/1" &&
      io::get_string(preview, "mime") == "text/html; charset=utf-8" &&
      document_mime(io::get_string(preview, "source_mime")) &&
      io::get_string(preview, "source_mime") == io::get_string(*entry, "mime") &&
      io::get_string(preview, "source_content_sha256") == io::get_string(*entry, "sha256") &&
      source_size >= 0 && source_size <= 1024 * 1024 && source_size == io::get_int(*entry, "size", -1) &&
      core::is_sha256_hex(display_sha) && display_size >= 0 && display_size <= max_asset_bytes,
      "Report preview source or display identity differs from the frozen manifest");
  Json expected = Json::array();
  for (const auto &asset : pending.manifest_assets) {
    if (io::get_string(asset, "path") != pending.result.entry_path && raster_mime(io::get_string(asset, "mime"))) {
      expected.push_back(asset);
    }
  }
  const auto &resources = result.at("resources");
  require(resources.size() == expected.size(), "Report preview omitted or added raster resources");
  int64_t total = display_size;
  for (size_t i = 0; i < expected.size(); ++i) {
    require(same_asset_descriptor(resources.at(i), expected.at(i)),
            "Report preview resource order or source descriptor differs from the manifest");
    total += io::get_int(expected.at(i), "size", -1);
  }
  require(total <= 32 * 1024 * 1024 && io::get_int(result, "total_size", -1) == total,
          "Report preview display budget or total is invalid");
  auto bytes = verified_preview_bytes(preview, display_size, display_sha);
  validate_preview_text(bytes);
  pending.result.identity.session_id = session;
  pending.result.assets.push_back({pending.result.entry_path, "text/html; charset=utf-8", std::move(bytes)});
  pending.resources = std::move(expected);
  pending.total_size = total; pending.received_size = display_size;
  read_preview_resource();
}
void ProjectReports::read_preview_resource()
{
  require(bool(preview_pending_), "Report preview preparation ended");
  auto &pending = *preview_pending_;
  if (pending.next_resource == pending.resources.size()) {
    require(pending.received_size == pending.total_size && pending.result.assets.size() == pending.resources.size() + 1 &&
        pending.result.assets.size() <= 64, "Report preview collection is incomplete");
    prepared_preview_ = std::move(pending.result);
    preview_pending_.reset(); preview_busy_ = false; ++preview_version_;
    return;
  }
  const auto descriptor = pending.resources.at(pending.next_resource);
  const auto identity = pending.result.identity;
  if (!preview_call("project.reports.asset", {{"report_id", identity.report_id},
      {"path", io::get_string(descriptor, "path")}, {"expected_revision", revision_},
      {"expected_source_sha256", identity.source_sha256}}, [this, descriptor, identity](const Json &result) {
    check_analysis_json_bounds(result, 6 * 1024 * 1024);
    require(preview_pending_ && result.is_object() && result.size() == 8 &&
        io::get_string(result, "project_id") == identity.project_id &&
        io::get_string(result, "report_id") == identity.report_id &&
        io::get_string(result, "source_sha256") == identity.source_sha256 &&
        io::get_string(result, "path") == io::get_string(descriptor, "path") &&
        io::get_string(result, "mime") == io::get_string(descriptor, "mime") &&
        raster_mime(io::get_string(result, "mime")) &&
        io::get_string(result, "content_sha256") == io::get_string(descriptor, "sha256") &&
        io::get_int(result, "size", -1) == io::get_int(descriptor, "size", -2),
        "Report preview image receipt differs from its frozen descriptor");
    const auto size = io::get_int(descriptor, "size", -1);
    auto bytes = verified_preview_bytes(result, size, io::get_string(descriptor, "sha256"));
    auto &current = *preview_pending_;
    require(size >= 0 && size <= 32 * 1024 * 1024 - current.received_size,
            "Report preview images exceed the display budget");
    current.received_size += size;
    current.result.assets.push_back({io::get_string(descriptor, "path"), io::get_string(descriptor, "mime"), std::move(bytes)});
    ++current.next_resource;
    read_preview_resource();
  })) {
    fail_preview("Report preview selection changed before its images were verified");
  }
}
}  // namespace stk::app
