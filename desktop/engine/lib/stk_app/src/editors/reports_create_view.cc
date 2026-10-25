/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_create_view.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/bridge/client.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/io/graph.hh"
#include <algorithm>
#include <cctype>
#include <map>
#include <limits>
#include <set>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
constexpr int64_t asset_limit = 4 * 1024 * 1024, total_limit = 32 * 1024 * 1024;
// uuid5(NAMESPACE_URL, "urn:stk:project:reports:1"), the published ordinary Reports table.
constexpr const char *reports_table = "d848e08d-26a3-5b7b-b44a-710dc62fa4ae";
void require(bool value, const char *message)
{
  if (!value) { throw std::runtime_error(message); }
}
std::string shortened(const std::string &value, size_t limit = 180)
{
  return value.size() <= limit ? value : std::string(core::utf8::truncate_bytes(value, limit)) + "…";
}
bool text(const Json &value, const char *key, size_t limit)
{
  return value.contains(key) && value.at(key).is_string() &&
      value.at(key).get_ref<const std::string &>().size() <= limit &&
      core::utf8::is_valid(value.at(key).get_ref<const std::string &>()) &&
      value.at(key).get_ref<const std::string &>().find('\0') == std::string::npos;
}
bool valid_title(const std::string &value)
{
  if (value.size() > 1024 || !core::utf8::is_valid(value) || value.find('\0') != std::string::npos || !visible_text(value)) { return false; }
  size_t characters = 0;
  for (unsigned char c : value) { if ((c & 0xc0) != 0x80) { ++characters; } }
  return characters <= 256;
}
std::string mime(const std::string &name)
{
  const auto dot = name.rfind('.');
  if (dot == std::string::npos) { return {}; }
  auto extension = name.substr(dot);
  for (auto &c : extension) { c = char(std::tolower(static_cast<unsigned char>(c))); }
  static const std::map<std::string, std::string> types{
      {".md", "text/markdown; charset=utf-8"}, {".markdown", "text/markdown; charset=utf-8"},
      {".html", "text/html; charset=utf-8"}, {".htm", "text/html; charset=utf-8"},
      {".css", "text/css; charset=utf-8"}, {".txt", "text/plain; charset=utf-8"},
      {".png", "image/png"}, {".jpg", "image/jpeg"}, {".jpeg", "image/jpeg"},
      {".gif", "image/gif"}, {".webp", "image/webp"}, {".pdf", "application/pdf"}};
  const auto found = types.find(extension);
  return found == types.end() ? std::string() : found->second;
}
// Early feedback only. The backend remains authoritative for NFC/casefold and portable
// directory collisions; rejected paths remain editable in the draft.
bool path(const std::string &value)
{
  if (value.empty() || value.size() > 1024 || !core::utf8::is_valid(value) || value.front() == '/') { return false; }
  for (unsigned char c : value) { if (c < 32 || c == 127 || std::string_view("\\:<>\"|?*").find(char(c)) != std::string_view::npos) { return false; } }
  size_t start = 0;
  while (start <= value.size()) {
    const auto end = value.find('/', start);
    const auto part = value.substr(start, end == std::string::npos ? end : end - start);
    if (part.empty() || part == "." || part == ".." || part.back() == ' ' || part.back() == '.') { return false; }
    auto lower = part;
    for (auto &c : lower) { c = char(std::tolower(static_cast<unsigned char>(c))); }
    if (start == 0 && lower == "stk-report.json") { return false; }
    if (end == std::string::npos) { break; }
    start = end + 1;
  }
  return true;
}
Json blank()
{
  return {{"version", 1}, {"project_id", ""}, {"snapshot_id", ""}, {"snapshot_sha256", ""},
      {"name", ""}, {"entry_record_id", ""}, {"assets", Json::array()}, {"pending", nullptr}};
}
std::string hash(const Json &value) { return core::Sha256::hex(io::python_json_dumps(value, true, true)); }
// Workspace APIs use sorted nlohmann::json, while RPC state uses ordered_json. Bound
// the original tree before converting it, so malformed input cannot force a large copy.
bool workspace_budget(const nlohmann::json &state)
{
  struct Item { const nlohmann::json *value; size_t depth; };
  std::vector<Item> pending{{&state, 0}};
  size_t remaining = 256 * 1024, scheduled = 1;
  const auto consume = [&remaining](size_t count) {
    if (count > remaining) { return false; }
    remaining -= count; return true;
  };
  while (!pending.empty()) {
    const auto item = pending.back(); pending.pop_back();
    const auto &value = *item.value;
    if (item.depth > 64 || !consume(1)) { return false; }
    if (value.is_string()) {
      if (!consume(value.get_ref<const std::string &>().size())) { return false; }
    }
    else if (value.is_object() || value.is_array()) {
      if (value.size() > 65536 - scheduled) { return false; }
      scheduled += value.size();
      for (auto it = value.begin(); it != value.end(); ++it) {
        if (value.is_object() && !consume(it.key().size())) { return false; }
        pending.push_back({&it.value(), item.depth + 1});
      }
    }
  }
  return true;
}
bool valid_draft(const Json &state)
{
  try {
    check_analysis_json_bounds(state, 256 * 1024);
    if (state.is_object() && state.empty()) { return true; }
    require(state.is_object() && state.size() == 8 && io::get_int(state, "version", -1) == 1,
            "Invalid report creation workspace state");
    for (const char *key : {"project_id", "snapshot_id", "snapshot_sha256", "name", "entry_record_id"}) {
      require(text(state, key, std::string_view(key) == "name" ? 1024 : 64), "Invalid report draft text");
    }
    const auto project = io::get_string(state, "project_id"), snapshot = io::get_string(state, "snapshot_id");
    const auto digest = io::get_string(state, "snapshot_sha256"), entry = io::get_string(state, "entry_record_id");
    require((project.empty() || canonical_uuid(project)) && (snapshot.empty() || canonical_uuid(snapshot)) &&
        (digest.empty() || core::is_sha256_hex(digest)) && (snapshot.empty() == digest.empty()) &&
        (snapshot.empty() || !project.empty()) && (entry.empty() || canonical_uuid(entry)), "Invalid report draft identity");
    const auto &assets = state.at("assets");
    require(assets.is_array() && assets.size() <= 64 && (assets.empty() || !snapshot.empty()), "Invalid report draft asset count");
    std::set<std::string> records;
    for (const auto &asset : assets) {
      require(asset.is_object() && asset.size() == 2 && text(asset, "record_id", 36) && text(asset, "path", 1024) &&
          canonical_uuid(io::get_string(asset, "record_id")) && records.insert(io::get_string(asset, "record_id")).second,
          "Invalid report draft asset");
    }
    require(entry.empty() || records.contains(entry), "Report entry is not selected");
    const auto &pending = state.at("pending");
    if (pending.is_null()) { return true; }
    require(valid_title(io::get_string(state, "name")) && pending.is_object() && pending.size() == 4 && canonical_uuid(io::get_string(pending, "report_id")) &&
        io::get_int(pending, "expected_revision", -1) >= 0 && core::is_sha256_hex(io::get_string(pending, "source_sha256")),
        "Invalid pending report identity");
    const auto &manifest = pending.at("manifest");
    require(manifest.is_object() && manifest.size() == 8 && io::get_string(manifest, "format") == "stk.report/1" &&
        io::get_string(manifest, "project_id") == project && io::get_string(manifest, "snapshot_id") == snapshot &&
        io::get_string(manifest, "snapshot_sha256") == digest &&
        io::get_int(manifest, "source_revision", -1) == io::get_int(pending, "expected_revision", -2) &&
        manifest.at("sources") == Json::array() && manifest.at("assets").is_array() &&
        manifest.at("assets").size() == assets.size() && !assets.empty(), "Pending report does not match its draft");
    int64_t total = 0; std::set<std::string> paths; bool found_entry = false;
    for (size_t i = 0; i < assets.size(); ++i) {
      const auto &item = manifest.at("assets")[i];
      const auto size = io::get_int(item, "size", -1);
      require(item.is_object() && item.size() == 5 && item.at("record_id") == assets[i].at("record_id") &&
          item.at("path") == assets[i].at("path") && path(io::get_string(item, "path")) &&
          paths.insert(io::get_string(item, "path")).second && text(item, "mime", 80) &&
          !io::get_string(item, "mime").empty() && core::is_sha256_hex(io::get_string(item, "sha256")) &&
          size >= 0 && size <= asset_limit, "Pending report assets differ from their draft");
      total += size;
      if (io::get_string(item, "record_id") == entry) {
        found_entry = item.at("path") == manifest.at("entry_path");
      }
    }
    require(found_entry && total <= total_limit && hash(manifest) == io::get_string(pending, "source_sha256"),
            "Pending report manifest does not match its checksum or entry");
    return true;
  }
  catch (...) { return false; }
}
}  // namespace

class ReportsCreateView::Impl {
 public:
  ~Impl() { *alive = false; if (future) { future->cancel(); } }
  enum class Operation { None, Read, Create, Check };
  struct Snapshot { std::string id, sha, label; };
  Json draft = blank();
  AppStore *store = nullptr;
  bridge::Client *client = nullptr;
  std::string session, project_id, handle, error, selected_file, validation;
  uint64_t validation_action = std::numeric_limits<uint64_t>::max();
  int64_t revision = -1, reviewed_revision = -1;
  uint64_t epoch = 0, request = 0, action = 0, group = 0, title_generation = 0, path_generation = 0;
  std::shared_ptr<bool> alive = std::make_shared<bool>(true);
  std::optional<bridge::Future<Json>> future;
  Operation operation = Operation::None;
  std::vector<Snapshot> snapshots;
  int64_t offset = 0, total = 0;
  bool list_loaded = false, abandon_pending = false;
  Json files = Json::array();
  std::optional<Created> created;
  std::function<bool()> reader_available;

  bool pending() const { return !draft.at("pending").is_null(); }
  bool dirty() const { return draft != blank() || operation == Operation::Create; }
  bool busy() const { return operation != Operation::None; }
  void changed() { ++action; if (store) { store->changed(); } }
  void form_changed() { ++group; ++title_generation; ++path_generation; changed(); }
  void cancel()
  {
    ++request; operation = Operation::None;
    auto old = std::move(future); future.reset();
    if (old) { old->cancel(); }
  }
  void sync(AppStore &owner)
  {
    store = &owner; auto &project = store->project(); project.sync();
    auto *next_client = store->bridge();
    const auto next_session = next_client && next_client->state() == bridge::BridgeState::Ready ?
        std::to_string(next_client->bridge_pid()) + ":" + std::to_string(next_client->stats().spawned) : std::string();
    const auto *current = project.project() ? &*project.project() : nullptr;
    const auto next_id = current ? current->id : std::string(), next_handle = current ? current->handle : std::string();
    const auto next_revision = current ? current->revision : int64_t(-1);
    if (client != next_client || session != next_session || project_id != next_id || handle != next_handle) {
      ++epoch; client = next_client; session = next_session; project_id = next_id; handle = next_handle;
      cancel(); snapshots.clear(); offset = total = 0; list_loaded = abandon_pending = false; files = Json::array(); reviewed_revision = -1;
      selected_file.clear(); error.clear(); created.reset(); form_changed();
    }
    if (revision != next_revision) {
      revision = next_revision;
      // Successful writes may publish project.changed before delivering their own receipt.
      // Invalidate read metadata and controls, but keep the original write identity alive.
      if (operation == Operation::Read) { cancel(); }
      snapshots.clear(); offset = total = 0; list_loaded = abandon_pending = false; files = Json::array(); reviewed_revision = -1;
      selected_file.clear(); form_changed();
    }
  }
  bool supports(const char *method) const
  {
    if (!store || store->bridge() != client || !client || session.empty() || !store->project().ready() ||
        !store->project().loaded() || !store->project().project() || handle.empty()) { return false; }
    const auto hello = client->hello_info(); return hello && hello->has_method(method);
  }
  std::function<bool()> guard(bool actions = true)
  {
    const std::weak_ptr<bool> weak = alive;
    const auto e = epoch, g = group, a = action; const auto r = revision;
    return [this, weak, e, g, a, r, actions] {
      const auto life = weak.lock(); if (!life || !*life || !store) { return false; }
      sync(*store);
      return epoch == e && revision == r && group == g && (!actions || action == a);
    };
  }
  bool call(const char *method, Json params, Operation op, std::function<void(const Json &)> done)
  {
    sync(*store);
    if (busy() || !supports(method) || store->project().busy() || !reader_available || !reader_available()) { return false; }
    params["handle"] = handle;
    const auto e = epoch, req = ++request; const auto source_revision = revision;
    const std::weak_ptr<bool> weak = alive;
    operation = op; error.clear();
    bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
    future = client->call(method, params, options);
    future->then([this, weak, e, req, source_revision, op, done = std::move(done)](bridge::Result<Json> result) {
      const auto life = weak.lock(); if (!life || !*life) { return; }
      sync(*store);
      if (e != epoch || req != request || (op == Operation::Read && source_revision != revision)) { return; }
      operation = Operation::None; future.reset();
      if (!result) {
        const auto &failure = result.error(); error = failure.describe();
        // A known remote rejection is not an uncertain commit. Queries never clear pending,
        // including NotFound: an older create may still be in flight or may have been undone.
        if (op == Operation::Create && !failure.local &&
            (failure.code == bridge::ErrorCode::InvalidParams || failure.code == bridge::ErrorCode::Conflict ||
             failure.code == bridge::ErrorCode::NotFound || failure.code == bridge::ErrorCode::Unsupported ||
             failure.code == bridge::ErrorCode::Unauthorized || failure.code == bridge::ErrorCode::UnknownMethod)) {
          draft["pending"] = nullptr; form_changed();
        }
        if (failure.code == bridge::ErrorCode::Conflict) { store->project().refresh(); }
      }
      else {
        try { done(result.value()); }
        catch (const std::exception &failure) { error = failure.what(); }
      }
      changed();
    });
    changed(); return true;
  }
  void load_snapshots(int64_t requested_offset = 0)
  {
    if (dirty() || requested_offset < 0) { return; }
    call("project.snapshots.list_summaries", {{"expected_revision", revision}, {"offset", requested_offset}, {"limit", 64}},
        Operation::Read, [this, requested_offset](const Json &result) {
      check_analysis_json_bounds(result, 64 * 1024);
      const auto &items = result.at("snapshots");
      require(io::get_int(result, "revision", -1) == revision && items.is_array() && items.size() <= 64 &&
          io::get_int(result, "offset", -1) == requested_offset && io::get_int(result, "total", -1) >= 0 &&
          requested_offset <= io::get_int(result, "total", -1) &&
          int64_t(items.size()) == std::min(int64_t(64), io::get_int(result, "total", -1) - requested_offset),
          "Snapshot summary page revision or range changed; reload the page");
      std::vector<Snapshot> summaries; std::set<std::string> ids;
      for (const auto &item : items) {
        const auto id = io::get_string(item, "id"), sha = io::get_string(item, "sha256");
        require(canonical_uuid(id) && ids.insert(id).second && core::is_sha256_hex(sha) &&
            io::get_string(item, "kind") == "files" && text(item, "created_at", 64) &&
            io::get_int(item, "revision", -1) >= 0 && io::get_int(item, "revision", -1) <= revision &&
            io::get_int(item, "file_count", -1) >= 1 && io::get_int(item, "file_count", -1) <= 100,
            "Invalid input snapshot summary");
        summaries.push_back({id, sha, id.substr(0, 8) + " · " + io::get_string(item, "created_at") +
            " · " + std::to_string(io::get_int(item, "file_count", 0))});
      }
      snapshots = std::move(summaries); offset = requested_offset;
      total = io::get_int(result, "total", 0); list_loaded = true; form_changed();
    });
  }
  void review(const std::string &id, const std::string &expected)
  {
    if (pending() || (!io::get_string(draft, "snapshot_id").empty() &&
        (io::get_string(draft, "snapshot_id") != id || io::get_string(draft, "project_id") != project_id))) { return; }
    call("project.snapshots.get", {{"snapshot_id", id}}, Operation::Read, [this, id, expected](const Json &result) {
      check_analysis_json_bounds(result, 2 * 1024 * 1024 + 64 * 1024);
      const auto &snapshot = result.at("snapshot"), &manifest = snapshot.at("manifest");
      require(io::get_string(snapshot, "id") == id && io::get_string(snapshot, "sha256") == expected &&
          io::get_string(snapshot, "kind") == "files" && io::get_int(snapshot, "revision", -1) >= 0 &&
          io::get_int(snapshot, "revision", -1) <= revision && io::get_int(manifest, "format", -1) == 1 &&
          io::get_string(manifest, "kind") == "files" && io::get_string(manifest, "project_id") == project_id &&
          io::get_int(manifest, "source_revision", -1) >= 0 &&
          io::get_int(manifest, "source_revision", -1) < io::get_int(snapshot, "revision", -1) &&
          hash(manifest) == expected, "Input snapshot identity, revision or checksum does not match");
      const auto &entries = manifest.at("files");
      require(entries.is_array() && !entries.empty() && entries.size() <= 100, "Invalid input snapshot files");
      Json selected = Json::array(); std::set<std::string> ids;
      for (const auto &file : entries) {
        const auto record = io::get_string(file, "record_id"), name = io::get_string(file, "name");
        require(canonical_uuid(record) && ids.insert(record).second && text(file, "name", 1024) &&
            core::is_sha256_hex(io::get_string(file, "sha256")) && io::get_int(file, "size", -1) >= 0 &&
            io::get_int(file, "size", -1) <= int64_t(1024) * 1024 * 1024 * 1024, "Invalid snapshot file identity");
        selected.push_back({{"record_id", record}, {"name", name}, {"sha256", file.at("sha256")},
            {"size", file.at("size")}, {"mime", mime(name)}});
      }
      for (const auto &asset : draft.at("assets")) {
        require(ids.contains(io::get_string(asset, "record_id")), "A selected report asset is missing from its frozen snapshot");
      }
      draft["project_id"] = project_id; draft["snapshot_id"] = id; draft["snapshot_sha256"] = expected;
      files = std::move(selected); reviewed_revision = revision; selected_file.clear(); form_changed();
    });
  }
  const Json *file(const std::string &id) const
  {
    for (const auto &entry : files) { if (io::get_string(entry, "record_id") == id) { return &entry; } }
    return nullptr;
  }
  Json *asset(const std::string &id)
  {
    for (auto &entry : draft["assets"]) { if (io::get_string(entry, "record_id") == id) { return &entry; } }
    return nullptr;
  }
  bool eligible(const Json &entry) const
  {
    return !io::get_string(entry, "mime").empty() && io::get_int(entry, "size", -1) <= asset_limit;
  }
  Json proposed_manifest() const
  {
    require(io::get_string(draft, "project_id") == project_id && reviewed_revision == revision && revision >= 0 && revision < std::numeric_limits<int64_t>::max() &&
        !io::get_string(draft, "snapshot_id").empty(), "Review the frozen snapshot at the current project revision");
    require(valid_title(io::get_string(draft, "name")), "Enter a report title of 1 to 256 characters");
    const auto &assets = draft.at("assets");
    require(!assets.empty() && assets.size() <= 64, "Select 1 to 64 report assets");
    Json result = {{"format", "stk.report/1"}, {"project_id", project_id},
        {"snapshot_id", draft.at("snapshot_id")}, {"snapshot_sha256", draft.at("snapshot_sha256")},
        {"source_revision", revision}, {"entry_path", ""}, {"assets", Json::array()}, {"sources", Json::array()}};
    int64_t total = 0; std::set<std::string> paths;
    for (const auto &entry : assets) {
      const auto *original = file(io::get_string(entry, "record_id")); const auto target = io::get_string(entry, "path");
      require(original && eligible(*original) && path(target) && paths.insert(target).second,
              "Check the selected asset format, size and unique portable paths");
      auto item = entry; item["size"] = original->at("size"); item["sha256"] = original->at("sha256"); item["mime"] = original->at("mime");
      result["assets"].push_back(std::move(item)); total += io::get_int(*original, "size", 0);
      if (entry.at("record_id") == draft.at("entry_record_id")) { result["entry_path"] = target; }
    }
    require(total <= total_limit && !io::get_string(result, "entry_path").empty(), "Choose one entry asset; total assets must not exceed 32 MiB");
    return result;
  }
  void finish()
  {
    created = Created{io::get_string(draft, "project_id"), io::get_string(draft.at("pending"), "report_id"),
        io::get_string(draft.at("pending"), "source_sha256")};
    draft = blank(); files = Json::array(); snapshots.clear(); reviewed_revision = -1; selected_file.clear();
    form_changed(); store->project().refresh();
  }
  void create()
  {
    if (pending() || busy()) { return; }
    Json manifest;
    try { manifest = proposed_manifest(); }
    catch (const std::exception &failure) { error = failure.what(); changed(); return; }
    auto id = new_idempotency_key(); id.insert(8, "-"); id.insert(13, "-"); id.insert(18, "-"); id.insert(23, "-");
    const auto expected = revision;
    draft["pending"] = {{"report_id", id}, {"expected_revision", expected}, {"manifest", manifest}, {"source_sha256", hash(manifest)}};
    form_changed();
    const Json params = {{"report_id", id}, {"name", draft.at("name")}, {"snapshot_id", draft.at("snapshot_id")},
        {"entry_record_id", draft.at("entry_record_id")}, {"assets", draft.at("assets")},
        {"sources", Json::array()}, {"expected_revision", expected}};
    if (!call("project.reports.create", params, Operation::Create, [this, id, expected](const Json &result) {
      check_analysis_json_bounds(result);
      require(io::get_string(result, "record_id") == id && io::get_string(result, "table_id") == reports_table &&
          io::get_int(result, "revision", -1) == expected + 1, "Report creation receipt does not match the original request; check its UUID");
      finish();
    })) { draft["pending"] = nullptr; form_changed(); }
  }
  void check_pending()
  {
    if (!pending() || io::get_string(draft, "project_id") != project_id) { return; }
    const auto id = io::get_string(draft.at("pending"), "report_id");
    call("project.reports.get", {{"report_id", id}}, Operation::Check, [this, id](const Json &result) {
      check_analysis_json_bounds(result, 400 * 1024);
      const auto &report = result.at("report"), &pending = draft.at("pending");
      require(io::get_string(result, "table_id") == reports_table &&
          io::get_int(result, "revision", -1) > io::get_int(pending, "expected_revision", -1) &&
          io::get_string(report, "id") == id && io::get_string(report, "state") == "readable" &&
          io::get_string(report, "format") == "stk.report/1" && report.at("name") == draft.at("name") &&
          // Ordered JSON key order changes after canonical database persistence. Compare
          // the complete canonical manifest, preserving asset order and all scalar values.
          io::python_json_dumps(report.at("manifest"), true, true) ==
              io::python_json_dumps(pending.at("manifest"), true, true) &&
          io::get_string(report, "source_sha256") == io::get_string(pending, "source_sha256") &&
          hash(report.at("manifest")) == io::get_string(pending, "source_sha256"),
          "The report found under this UUID does not match the original creation request");
      finish();
    });
  }
  void draw(ui::Layout &layout, EditorContext &ctx, std::function<bool()> reader_available);
};

void ReportsCreateView::Impl::draw(ui::Layout &layout, EditorContext &ctx, std::function<bool()> available)
{
  reader_available = std::move(available);
  sync(ctx.store);
  auto *panel = layout.panel("reports_create_panel", ctx.tr("reports.create.panel"), false);
  if (!panel) { return; }
  auto *shell = &ctx.area.shell();
  const auto current = guard();
  const auto same_form = guard(false);
  const bool blocked = busy() || !reader_available() || store->project().busy();
  const bool other_project = dirty() && io::get_string(draft, "project_id") != project_id;
  panel->paragraph(ctx.tr("reports.create.intro"));
  if (!error.empty()) { panel->paragraph(error); }
  if (busy()) { panel->label(ctx.tr("project.busy")); }
  if (dirty()) {
    if (other_project) { panel->paragraph(ctx.tr("reports.create.other_project")); }
    if (pending()) {
      panel->paragraph(ctx.tr("reports.create.pending"));
      panel->label(io::get_string(draft.at("pending"), "report_id"));
      panel->button("reports_create_check", ctx.tr("reports.create.check"), [this, current, shell] {
        if (current() && !shell->text_input_active()) { check_pending(); }
      }).disable(blocked || other_project || !supports("project.reports.get") || shell->text_input_active());
      panel->checkbox("reports_create_abandon", ctx.tr("reports.create.abandon"),
          {[this, same_form] { return same_form() && abandon_pending; },
           [this, current](bool value) { if (current() && !busy()) { abandon_pending = value; changed(); } }}).disable(blocked);
    }
    panel->button("reports_create_discard", ctx.tr("reports.create.discard"), [this, current, shell] {
      if (!current() || busy() || shell->text_input_active() || (pending() && !abandon_pending)) { return; }
      draft = blank(); files = Json::array(); selected_file.clear(); reviewed_revision = -1;
      error.clear(); abandon_pending = false; form_changed();
    }).disable(blocked || (pending() && !abandon_pending) || shell->text_input_active());
  }
  if (pending() || other_project) { return; }
  if (!supports("project.reports.create") || !supports("project.snapshots.list_summaries") ||
      !supports("project.snapshots.get")) {
    panel->paragraph(ctx.tr("reports.create.unsupported")); return;
  }
  const auto snapshot_id = io::get_string(draft, "snapshot_id");
  if (snapshot_id.empty()) {
    panel->button("reports_create_snapshots", ctx.tr("reports.create.load_snapshots"), [this, current, shell] {
      if (current() && !shell->text_input_active()) { load_snapshots(); }
    }).disable(blocked || shell->text_input_active());
    if (!list_loaded) { return; }
    panel->label(std::string(ctx.tr("reports.create.snapshot_columns")));
    panel->label(std::to_string(snapshots.empty() ? 0 : offset + 1) + "–" +
        std::to_string(offset + int64_t(snapshots.size())) + " / " + std::to_string(total));
    if (snapshots.empty()) { panel->paragraph(ctx.tr("reports.create.no_snapshots")); }
    ui::ListSpec list; list.count = int(snapshots.size()); list.rows = std::min(4.0f, float(snapshots.size()));
    const auto summaries = snapshots; // At most 64 small summaries; no full manifests or file paths.
    list.text = [summaries](int i) { return summaries.at(size_t(i)).label; };
    list.selected = {[] { return -1; }, [this, current, summaries, shell](int i) {
      if (!current() || shell->text_input_active() || i < 0 || size_t(i) >= summaries.size()) { return; }
      review(summaries[size_t(i)].id, summaries[size_t(i)].sha);
    }};
    if (!snapshots.empty()) { panel->virtual_list("reports_create_snapshot_list", std::move(list)).disable(blocked); }
    if (offset || total > int64_t(snapshots.size())) {
      auto &pages = panel->row();
      pages.button("reports_create_snapshots_previous", ctx.tr("reports.previous"), [this, current] {
        if (current()) { load_snapshots(std::max(int64_t(0), offset - 64)); }
      }).disable(blocked || !offset);
      pages.button("reports_create_snapshots_next", ctx.tr("reports.next"), [this, current] {
        if (current()) { load_snapshots(offset + 64); }
      }).disable(blocked || int64_t(snapshots.size()) >= total - offset);
    }
    return;
  }
  panel->label(std::string(ctx.tr("reports.snapshot")) + snapshot_id);
  if (reviewed_revision != revision) {
    panel->paragraph(ctx.tr("reports.create.review_needed"));
    panel->button("reports_create_review", ctx.tr("reports.create.review"), [this, current, shell, snapshot_id] {
      if (current() && !shell->text_input_active()) { review(snapshot_id, io::get_string(draft, "snapshot_sha256")); }
    }).disable(blocked || shell->text_input_active());
  }
  // A text commit invalidates action callbacks, but not an untouched sibling field.
  // This permits Tab to commit a title then focus the path before the next redraw.
  const auto title_token = title_generation;
  panel->prop(ctx.tr("reports.create.title")).text_field("reports_create_title",
      {[this, same_form, title_token] { return same_form() && title_token == title_generation ? io::get_string(draft, "name") : std::string(); },
       [this, same_form, title_token](const std::string &value) {
         if (!same_form() || title_token != title_generation || pending() || busy() || value.size() > 1024 ||
             !core::utf8::is_valid(value) || value.find('\0') != std::string::npos) { return; }
         draft["name"] = value; ++title_generation; changed();
       }}, {.max_length = 256}).disable(blocked);
  if (reviewed_revision == revision) {
    panel->paragraph(ctx.tr("reports.create.choose_assets"));
    ui::ListSpec list; list.count = int(files.size()); list.rows = std::min(5.0f, float(files.size()));
    std::vector<std::string> names, ids; int selected = -1;
    for (const auto &item : files) {
      const auto id = io::get_string(item, "record_id"); ids.push_back(id);
      names.push_back((asset(id) ? "☑ " : "☐ ") + shortened(io::get_string(item, "name")) +
          " · " + std::to_string(io::get_int(item, "size", 0)) + " B" + (eligible(item) ? "" : " ⚠"));
      if (id == selected_file) { selected = int(ids.size()) - 1; }
    }
    list.text = [names](int i) { return names.at(size_t(i)); };
    list.selected = {[selected] { return selected; }, [this, current, ids, shell](int i) {
      if (!current() || busy() || shell->text_input_active() || i < 0 || size_t(i) >= ids.size()) { return; }
      selected_file = ids[size_t(i)]; form_changed();
    }};
    panel->virtual_list("reports_create_files", std::move(list)).disable(blocked);
    const auto *selected_item = file(selected_file);
    if (selected_item) {
      const auto id = selected_file; const bool included = asset(id) != nullptr;
      panel->label(shortened(io::get_string(*selected_item, "name"), 512));
      panel->label(io::get_string(*selected_item, "mime"));
      panel->checkbox("reports_create_include", ctx.tr("reports.create.include"),
          {[included] { return included; }, [this, current, id, shell](bool value) {
            if (!current() || busy() || shell->text_input_active()) { return; }
            const auto *original = file(id); if (!original || !eligible(*original)) { return; }
            if (value && !asset(id) && draft.at("assets").size() < 64) {
              draft["assets"].push_back({{"record_id", id}, {"path", io::get_string(*original, "name")}});
            }
            else if (!value && asset(id)) {
              auto &entries = draft["assets"];
              for (size_t i = 0; i < entries.size(); ++i) { if (io::get_string(entries[i], "record_id") == id) { entries.erase(i); break; } }
              if (io::get_string(draft, "entry_record_id") == id) { draft["entry_record_id"] = ""; }
            }
            form_changed();
          }}).disable(blocked || !eligible(*selected_item) || (!included && draft.at("assets").size() >= 64));
      if (included) {
        const auto path_token = path_generation;
        panel->prop(ctx.tr("reports.create.path")).text_field("reports_create_path",
            {[this, same_form, id, path_token] {
              if (!same_form() || selected_file != id || path_token != path_generation) { return std::string(); }
              const auto *entry = asset(id); return entry ? io::get_string(*entry, "path") : std::string();
            }, [this, same_form, id, path_token](const std::string &value) {
              if (!same_form() || selected_file != id || path_token != path_generation || pending() || busy() ||
                  value.size() > 1024 || !core::utf8::is_valid(value) || value.find('\0') != std::string::npos) { return; }
              auto *entry = asset(id); if (!entry) { return; }
              (*entry)["path"] = value; ++path_generation; changed();
            }}, {.max_length = 1024}).disable(blocked);
        panel->button("reports_create_entry", ctx.tr("reports.create.use_entry"), [this, current, id, shell] {
          if (current() && !busy() && !shell->text_input_active() && asset(id)) { draft["entry_record_id"] = id; form_changed(); }
        }).disable(blocked || io::get_string(draft, "entry_record_id") == id || shell->text_input_active());
      }
    }
  }
  // Review every selected virtual path, including files outside the current list viewport.
  if (!draft.at("assets").empty()) {
    panel->label(std::string(ctx.tr("reports.create.selected")) + std::to_string(draft.at("assets").size()) + " / 64");
    std::vector<std::string> rows;
    for (const auto &item : draft.at("assets")) {
      const auto *original = file(io::get_string(item, "record_id"));
      rows.push_back((item.at("record_id") == draft.at("entry_record_id") ? "▶ " : "") +
          shortened(io::get_string(item, "path"), 512) + " ← " +
          shortened(original ? io::get_string(*original, "name") : io::get_string(item, "record_id")));
    }
    ui::ListSpec review; review.count = int(rows.size()); review.rows = std::min(3.0f, float(rows.size()));
    review.text = [rows](int i) { return rows.at(size_t(i)); };
    panel->virtual_list("reports_create_asset_review", std::move(review));
  }
  panel->paragraph(ctx.tr("reports.create.limits"));
  panel->paragraph(ctx.tr("reports.create.finish_text"));
  if (validation_action != action) {
    validation_action = action; validation.clear();
    try { (void)proposed_manifest(); } catch (const std::exception &failure) { validation = failure.what(); }
  }
  if (!validation.empty()) { panel->paragraph(validation); }
  panel->button("reports_create_submit", ctx.tr("reports.create.submit"), [this, current, shell] {
    if (current() && !busy() && !shell->text_input_active()) { create(); }
  }).disable(blocked || !validation.empty() || shell->text_input_active());
}

ReportsCreateView::ReportsCreateView() : impl_(std::make_unique<Impl>()) {}
ReportsCreateView::~ReportsCreateView() = default;
bool ReportsCreateView::dirty() const { return impl_->dirty(); }
void ReportsCreateView::draw(ui::Layout &layout, EditorContext &ctx, std::function<bool()> available) { impl_->draw(layout, ctx, std::move(available)); }
std::optional<ReportsCreateView::Created> ReportsCreateView::take_created()
{
  auto result = std::move(impl_->created); impl_->created.reset(); return result;
}
nlohmann::json ReportsCreateView::save_workspace_state() const
{
  return impl_->dirty() ? nlohmann::json(impl_->draft) : nlohmann::json::object();
}
bool ReportsCreateView::valid_workspace_state(const nlohmann::json &state)
{
  return workspace_budget(state) && valid_draft(Json(state));
}
bool ReportsCreateView::load_workspace_state(const nlohmann::json &state)
{
  if (!valid_workspace_state(state)) { return false; }
  ++impl_->epoch; impl_->cancel(); impl_->draft = state.empty() ? blank() : Json(state);
  impl_->snapshots.clear(); impl_->files = Json::array(); impl_->reviewed_revision = -1;
  impl_->offset = impl_->total = 0; impl_->list_loaded = impl_->abandon_pending = false;
  impl_->selected_file.clear(); impl_->created.reset(); impl_->error.clear(); impl_->form_changed();
  return true;
}
}  // namespace stk::app
