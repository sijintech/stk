/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_report_generation.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/model_settings.hh"
#include "stk/app/project_data_labels.hh"
#include "stk/app/project_state.hh"
#include "stk/bridge/schema.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/io/graph.hh"
#include <algorithm>
#include <set>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace stk::app {
namespace {
using io::Json;
constexpr size_t workspace_limit = 512 * 1024;
constexpr const char *reports_table = "d848e08d-26a3-5b7b-b44a-710dc62fa4ae";
void require(bool ok, const char *message) { if (!ok) { throw std::runtime_error(message); } }
std::string canonical(const Json &v) { return io::python_json_dumps(v, true, true); }
std::string hash(const Json &v) { return core::Sha256::hex(canonical(v)); }
bool same(const Json &a, const Json &b) { return canonical(a) == canonical(b); }
void bounded(const Json &v, size_t bytes)
{
  check_analysis_json_bounds(v, bytes);
  require(canonical(v).size() <= bytes, "Report JSON exceeds its encoded byte budget");
}
void shape(const Json &v, const char *definition, size_t bytes)
{
  bounded(v, bytes);
  const auto &schema = bridge::ProtocolSchema::embedded().resolved(std::string("#/$defs/") + definition);
  require(io::check_value(v, schema).empty(), "Invalid report response structure");
}
void keys(const Json &v, std::initializer_list<const char *> expected)
{
  require(v.is_object() && v.size() == expected.size(), "Unexpected report draft fields");
  for (const auto *name : expected) { require(v.contains(name), "Missing report draft field"); }
}
void text(const std::string &s, bool nonblank, bool controls = false)
{
  require(s.size() <= 64 * 1024 && core::utf8::is_valid(s) && (!nonblank || visible_text(s)), "Enter bounded UTF-8 text");
  if (controls) {
    for (size_t i = 0; i < s.size();) {
      const auto cp = core::utf8::decode(s, i); i += cp.length;
      require(!((cp.code_point < 32 && cp.code_point != '\t' && cp.code_point != '\r' && cp.code_point != '\n') ||
                (cp.code_point >= 127 && cp.code_point <= 159)), "Report body contains control characters");
    }
  }
}
bool title(const std::string &s)
{
  return s.size() <= 1024 && core::utf8::is_valid(s) && s.find('\0') == std::string::npos && visible_text(s) &&
      std::count_if(s.begin(), s.end(), [](unsigned char c) { return (c & 0xc0) != 0x80; }) <= 256;
}
std::string mime(const std::string &path)
{
  require(!path.empty() && path.size() <= 1024 && core::utf8::is_valid(path) && path.front() != '/', "Invalid report path");
  for (unsigned char c : path) { require(c >= 32 && c != 127 && std::string_view("\\:<>\"|?*").find(c) == std::string_view::npos, "Invalid report path"); }
  size_t start = 0;
  while (start <= path.size()) {
    const auto end = path.find('/', start); const auto part = path.substr(start, end == std::string::npos ? end : end - start);
    require(!part.empty() && part != "." && part != "..", "Invalid report path segment");
    if (end == std::string::npos) { break; } start = end + 1;
  }
  const auto slash = path.rfind('/'), dot = path.rfind('.');
  const auto begin = slash == std::string::npos ? 0 : slash + 1;
  std::string suffix = dot != std::string::npos && dot > begin ? path.substr(dot) : "";
  for (auto &c : suffix) { if (c >= 'A' && c <= 'Z') { c += 'a' - 'A'; } }
  if (suffix == ".md" || suffix == ".markdown") { return "text/markdown; charset=utf-8"; }
  if (suffix == ".html" || suffix == ".htm") { return "text/html; charset=utf-8"; }
  return {};
}
std::string uuid()
{
  auto id = new_idempotency_key(); id.insert(8, "-"); id.insert(13, "-"); id.insert(18, "-"); id.insert(23, "-"); return id;
}
Json blank()
{
  return {{"version", 1}, {"project_id", ""}, {"context_id", ""}, {"context_sha256", ""}, {"question", ""},
      {"configuration", Json::object()}, {"selection", nullptr}, {"snapshot_sha256", nullptr}, {"assets_sha256", ""},
      {"name", ""}, {"entry_path", "report.md"}, {"body", ""}, {"body_initialized", false},
      {"message_id", ""}, {"request_id", ""}, {"input_sha256", ""}, {"response_sha256", ""},
      {"send_attempted", false}, {"phase", "draft"}, {"pending_save", nullptr}};
}
void context(const Json &v, const std::string &project, int64_t revision)
{
  shape(v, "projectContext", 256 * 1024);
  require(io::get_string(v, "project_id") == project && io::get_int(v, "source_revision", -1) <= revision,
          "Context belongs to another project or newer revision");
  const auto &content = v.at("content");
  if (io::get_string(content, "state") == "included") {
    const auto encoded = canonical(content.at("value"));
    require(encoded.size() == size_t(io::get_int(content, "size_bytes", -1)) &&
        core::Sha256::hex(encoded) == io::get_string(content, "sha256"), "Context content checksum differs");
  }
}
Json combined_sources(const Json &primary, const Json &sources, const std::string &project, int64_t revision)
{
  Json result = Json::array();
  const Json first = {{"kind", "context"}, {"id", primary.at("id")}, {"project_id", project},
      {"source_revision", primary.at("source_revision")}, {"context_sha256", hash(primary)}, {"context", primary}};
  result.push_back(first); std::set<std::pair<std::string, std::string>> seen;
  require(sources.is_array() && sources.size() <= 16, "Too many report sources");
  for (const auto &source : sources) {
    shape(source, "projectReportSource", 192 * 1024);
    const auto kind = io::get_string(source, "kind"), id = io::get_string(source, "id");
    require(seen.emplace(kind, id).second && io::get_string(source, "project_id") == project &&
        io::get_int(source, "source_revision", -1) <= revision, "Report source identity or revision differs");
    if (kind == "context") {
      context(source.at("context"), project, revision);
      require(io::get_string(source.at("context"), "id") == id &&
          source.at("context").at("source_revision") == source.at("source_revision") &&
          hash(source.at("context")) == io::get_string(source, "context_sha256"), "Report context source checksum differs");
    }
    if (kind == "context" && source.at("id") == primary.at("id")) { require(same(first, source), "Primary context differs"); }
    else { result.push_back(source); }
  }
  require(result.size() <= 16, "The primary context occupies one of 16 source slots"); return result;
}
void frozen(const Json &v, const Json &primary, const std::string &project, int64_t current)
{
  shape(v, "projectReportInput", 256 * 1024);
  const auto rev = io::get_int(v, "source_revision", -1);
  require(io::get_string(v, "project_id") == project && rev <= current &&
      io::get_int(primary, "source_revision", -1) <= rev, "Frozen input source revision differs");
  const auto combined = combined_sources(primary, v.at("sources"), project, rev);
  bounded(Json{{"sources", combined}, {"assets", v.at("assets")}}, 192 * 1024);
  if (v.at("snapshot_id").is_null()) {
    require(v.at("snapshot_sha256").is_null() && v.at("assets").empty(), "Assets require a real snapshot");
  }
  else { require(core::is_sha256_hex(io::get_string(v, "snapshot_sha256")), "Missing snapshot checksum"); }
  std::set<std::string> records, paths; int64_t total = 0;
  for (const auto &asset : v.at("assets")) {
    const auto path = io::get_string(asset, "path"); (void)mime(path);
    require(records.insert(io::get_string(asset, "record_id")).second && paths.insert(path).second,
            "Duplicate report asset");
    total += io::get_int(asset, "size", -1);
  }
  require(total <= 32 * 1024 * 1024 - 64 * 1024, "Report assets must reserve 64 KiB for generated text");
}
// Bound the original sorted workspace tree before conversion into ordered RPC JSON.
bool workspace_budget(const nlohmann::json &state)
{
  struct Item { const nlohmann::json *value; size_t depth; };
  std::vector<Item> pending{{&state, 0}};
  size_t remaining = workspace_limit, scheduled = 1;
  const auto consume = [&remaining](size_t count) {
    if (count > remaining) { return false; } remaining -= count; return true;
  };
  while (!pending.empty()) {
    const auto item = pending.back(); pending.pop_back(); const auto &value = *item.value;
    if (item.depth > 64 || !consume(1)) { return false; }
    if (value.is_string()) {
      if (!consume(value.get_ref<const std::string &>().size())) { return false; }
    }
    else if (value.is_object() || value.is_array()) {
      if (value.size() > 65536 - scheduled) { return false; } scheduled += value.size();
      for (auto it = value.begin(); it != value.end(); ++it) {
        if (value.is_object() && !consume(it.key().size())) { return false; }
        pending.push_back({&it.value(), item.depth + 1});
      }
    }
  }
  return true;
}
void validate_workspace(const Json &v)
{
  bounded(v, workspace_limit); keys(v, {"version", "project_id", "context_id", "context_sha256", "question", "configuration",
      "selection", "snapshot_sha256", "assets_sha256", "name", "entry_path", "body", "body_initialized", "message_id",
      "request_id", "input_sha256", "response_sha256", "send_attempted", "phase", "pending_save"});
  require(v.at("version") == 1 && v.at("version").is_number_integer(), "Unsupported report draft version");
  for (const auto *key : {"project_id", "context_id", "message_id", "request_id"}) {
    require(v.at(key).is_string() && (v.at(key) == "" || canonical_uuid(v.at(key).get<std::string>())), "Invalid report draft UUID");
  }
  for (const auto *key : {"context_sha256", "assets_sha256", "input_sha256", "response_sha256"}) {
    require(v.at(key).is_string() && (v.at(key) == "" || core::is_sha256_hex(v.at(key).get<std::string>())), "Invalid report draft checksum");
  }
  require(v.at("body_initialized").is_boolean() && v.at("send_attempted").is_boolean(), "Invalid report draft flags");
  for (const auto *key : {"question", "body", "name", "entry_path", "phase"}) { require(v.at(key).is_string(), "Invalid report draft text"); }
  text(v.at("question").get_ref<const std::string &>(), false);
  text(v.at("body").get_ref<const std::string &>(), false, true);
  require(v.at("name") == "" || title(v.at("name").get<std::string>()), "Invalid report title");
  require(!mime(v.at("entry_path").get<std::string>()).empty(), "Generated entry must be Markdown or HTML");
  const std::set<std::string> phases{"draft", "import_pending", "message_pending", "message_saved", "request_pending", "prepared", "start_pending",
      "running", "cancel_pending", "recover_pending", "completed", "terminal", "save_pending", "saved"};
  const auto phase = io::get_string(v, "phase"); require(phases.contains(phase), "Invalid report draft phase");
  require(v.at("configuration").is_object(), "Invalid report configuration");
  if (!v.at("configuration").empty()) { shape(v.at("configuration"), "projectRequestConfiguration", 2048); }
  if (!v.at("selection").is_null()) { shape(v.at("selection"), "projectReportRequestSelection", 32 * 1024); }
  require(v.at("snapshot_sha256").is_null() || core::is_sha256_hex(io::get_string(v, "snapshot_sha256")), "Invalid snapshot checksum");
  require(v.at("body_initialized").get<bool>() || v.at("body") == "", "Uninitialized report body is not empty");
  if (phase == "import_pending") {
    auto expected = blank(); expected["phase"] = "import_pending";
    expected["project_id"] = v.at("project_id"); expected["request_id"] = v.at("request_id");
    require(canonical_uuid(io::get_string(v, "project_id")) && canonical_uuid(io::get_string(v, "request_id")) &&
        same(v, expected), "Invalid pending request import");
    return;
  }
  if (phase == "draft") {
    require(v.at("message_id") == "" && v.at("request_id") == "" && v.at("input_sha256") == "" &&
        v.at("response_sha256") == "" && !v.at("send_attempted").get<bool>(), "Draft has a sent request identity");
  }
  if (!v.at("selection").is_null()) {
    require(canonical_uuid(io::get_string(v, "project_id")) && canonical_uuid(io::get_string(v, "context_id")) &&
        core::is_sha256_hex(io::get_string(v, "context_sha256")) && core::is_sha256_hex(io::get_string(v, "assets_sha256")) &&
        !v.at("configuration").empty(), "Incomplete reviewed input identity");
    const auto &selection = v.at("selection");
    require(selection.at("snapshot_id").is_null() == v.at("snapshot_sha256").is_null() &&
        (!selection.at("snapshot_id").is_null() || selection.at("assets").empty()), "Invalid restored asset identity");
  }
  if (phase != "draft") {
    require(canonical_uuid(io::get_string(v, "project_id")) && canonical_uuid(io::get_string(v, "context_id")) &&
        canonical_uuid(io::get_string(v, "message_id")) && canonical_uuid(io::get_string(v, "request_id")) &&
        core::is_sha256_hex(io::get_string(v, "context_sha256")) && core::is_sha256_hex(io::get_string(v, "assets_sha256")) &&
        v.at("selection").is_object() && !v.at("configuration").empty(), "Incomplete pending report identity");
    text(v.at("question").get_ref<const std::string &>(), true);
  }
  if (phase != "draft" && phase != "message_pending" && phase != "message_saved" && phase != "request_pending") {
    require(core::is_sha256_hex(io::get_string(v, "input_sha256")), "Missing frozen request checksum");
  }
  if (phase == "completed" || phase == "save_pending" || phase == "saved") {
    require(core::is_sha256_hex(io::get_string(v, "response_sha256")), "Missing complete response checksum");
  }
  if (phase == "prepared") { require(!v.at("send_attempted").get<bool>(), "Prepared request already attempted send"); }
  if (phase == "start_pending") { require(v.at("send_attempted").get<bool>(), "Missing send attempt marker"); }
  if (!v.at("pending_save").is_null()) {
    const auto &save = v.at("pending_save"); keys(save, {"report_id", "expected_revision", "name", "entry_path", "body_sha256"});
    require(phase == "save_pending" && canonical_uuid(io::get_string(save, "report_id")) &&
        save.at("expected_revision").is_number_integer() && io::get_int(save, "expected_revision", -1) >= io::get_int(v.at("selection"), "expected_revision", 0) && title(io::get_string(save, "name")) && save.at("name") == v.at("name") &&
        save.at("entry_path") == v.at("entry_path") && core::Sha256::hex(io::get_string(v, "body")) == io::get_string(save, "body_sha256") &&
        core::is_sha256_hex(io::get_string(v, "input_sha256")) && core::is_sha256_hex(io::get_string(v, "response_sha256")),
        "Pending report save differs from its immutable draft");
  }
  else { require(phase != "save_pending", "Missing pending report save"); }
}
} // namespace

class ProjectReportGeneration::Impl {
 public:
  explicit Impl(AppStore &value) : store(value), project(value.project()) { sync(); }
  ~Impl() { *alive = false; if (future) { future->cancel(); } }
  AppStore &store; ProjectState &project;
  bridge::Client *client = nullptr;
  std::string session, project_id, handle, error;
  int64_t revision = -1, reviewed_revision = -1;
  uint64_t epoch = 0, edit_version = 0, version = 0, flight = 0;
  Json draft = blank(), record, input, reply;
  std::shared_ptr<bool> alive = std::make_shared<bool>(true);
  std::optional<bridge::Future<Json>> future;
  std::optional<Created> created;
  bool busy = false, verify_saved_when_ready = false;
  double now = 0, due = -1, deadline = -1;
  void changed(bool edit = false) { ++version; if (edit) { ++edit_version; } store.changed(); }
  std::string phase() const { return io::get_string(draft, "phase"); }
  bool pending() const { return phase().ends_with("_pending"); }
  bool dirty() const { return busy || pending() || (phase() != "saved" && !same(draft, blank())); }
  void invalidate()
  {
    ++epoch; ++flight; ++edit_version; reviewed_revision = -1; busy = false;
    record = input = reply = nullptr; created.reset(); due = deadline = -1; verify_saved_when_ready = false;
    auto old = std::move(future); future.reset(); if (old) { old->cancel(); }
  }
  void sync()
  {
    project.sync(); auto *next = store.bridge();
    const auto next_session = next && next->state() == bridge::BridgeState::Ready ?
        std::to_string(next->bridge_pid()) + ":" + std::to_string(next->stats().spawned) : std::string();
    const auto *p = project.project() ? &*project.project() : nullptr;
    const auto id = p ? p->id : std::string(), opened = p ? p->handle : std::string();
    if (client != next || session != next_session || project_id != id || handle != opened) {
      invalidate(); client = next; session = next_session; project_id = id; handle = opened; error.clear(); changed();
    }
    const auto rev = p ? p->revision : int64_t(-1);
    if (revision != rev) { revision = rev; reviewed_revision = -1; ++edit_version; changed(); }
  }
  bool supports(const std::string &method) const
  {
    if (store.bridge() != client || !client || session.empty() || !project.ready() || !project.loaded() ||
        !project.project() || project.project()->handle != handle || project.project()->id != project_id) { return false; }
    const auto hello = client->hello_info(); return hello && hello->has_method(method);
  }
  bool current(Token token)
  {
    sync(); return token.epoch == epoch && token.edit == edit_version && !busy &&
        (io::get_string(draft, "project_id").empty() || draft.at("project_id") == project_id);
  }
  template<typename F> bool guarded(Token token, F &&fn)
  {
    if (!current(token)) { return false; }
    try { return fn(); }
    catch (const std::exception &e) { error = e.what(); changed(); return false; }
  }
  bool call(const std::string &method, Json params, bool read, std::function<void(const Json &)> accept)
  {
    sync(); if (busy || !supports(method) || project.busy() ||
        (!io::get_string(draft, "project_id").empty() && draft.at("project_id") != project_id)) { return false; }
    params["handle"] = handle;
    require(bridge::ProtocolSchema::embedded().check_request({{"id", 1}, {"method", method}, {"params", params}}).empty(),
            "Invalid report operation parameters");
    const auto e = epoch, f = ++flight; const auto rev = revision;
    const std::weak_ptr<bool> weak = alive;
    bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
    busy = true; error.clear();
    future = client->call(method, params, options);
    future->then([this, weak, e, f, rev, read, method, accept = std::move(accept)](bridge::Result<Json> result) {
      const auto life = weak.lock(); if (!life || !*life) { return; }
      sync(); if (e != epoch || f != flight) { return; }
      busy = false; future.reset();
      if (read && rev != revision) { error = "Project changed while reading; explicitly read the original identity again"; changed(); return; }
      if (!result) {
        error = result.error().describe(); due = deadline = -1;
        // All uncertain identities survive errors and NotFound. No callback ever replays
        // message/request creation, a model start, cancellation, recovery or a report save.
        if (result.error().code == bridge::ErrorCode::Conflict) { project.refresh(); }
      }
      else {
        try {
          bounded(result.value(), 2 * 1024 * 1024);
          require(bridge::ProtocolSchema::embedded().check_response({{"id", 1}, {"result", result.value()}}, method).empty(),
                  "Invalid report operation response");
          accept(result.value());
        }
        catch (const std::exception &e) { error = e.what(); due = deadline = -1; }
      }
      changed();
    });
    changed(); return true;
  }
  void validate_message(const Json &message, const Json *expected = nullptr) const
  {
    const auto &intent = expected ? *expected : draft;
    shape(message, "projectDiscussionMessage", 400 * 1024);
    text(io::get_string(message, "text"), true);
    require(message.at("id") == intent.at("message_id") && message.at("project_id") == intent.at("project_id") &&
        message.at("context_id") == intent.at("context_id") && message.at("role") == "user" &&
        message.at("text") == intent.at("question"), "Saved question differs from its original intent");
  }
  void validate_record(const Json &r, const Json *expected = nullptr) const
  {
    const auto &intent = expected ? *expected : draft;
    shape(r, "projectRequest", 16 * 1024);
    require(r.at("id") == intent.at("request_id") && r.at("project_id") == intent.at("project_id") &&
        r.at("context_id") == intent.at("context_id") && r.at("message_id") == intent.at("message_id") &&
        r.at("prompt_version") == "stk.report-draft/1" && same(r.at("configuration"), intent.at("configuration")) &&
        (io::get_string(intent, "input_sha256").empty() || r.at("input_sha256") == intent.at("input_sha256")),
        "Saved report request differs from its original identity");
    const auto status = io::get_string(r, "status");
    const bool cancelled = r.at("cancel_requested").get<bool>(), owner = !r.at("executor_id").is_null();
    require(io::get_int(r, "source_revision", -1) <= revision, "Request source revision is newer than this project");
    if (status == "pending") {
      require(!owner && !cancelled && r.at("error_code").is_null() && r.at("result").is_null(), "Invalid pending request state");
    }
    else if (status == "running") {
      require(owner && !cancelled && r.at("error_code").is_null() && r.at("result").is_null(), "Invalid running request state");
    }
    else if (status == "completed") {
      require(owner && r.at("error_code").is_null() && r.at("result").is_object() &&
          r.at("result").at("message_id") == r.at("assistant_message_id"), "Invalid completed request state");
    }
    else {
      const auto code = io::get_string(r, "error_code");
      require(r.at("result").is_null() && !code.empty() && (code == "cancelled_before_start" ? !owner : owner) &&
          (status != "cancelled" || cancelled) && (code != "cancel_unconfirmed" || cancelled), "Invalid settled request state");
    }
    if (record.is_object()) {
      for (const auto *key : {"assistant_message_id", "source_revision", "created_at", "input_sha256"}) {
        require(r.at(key) == record.at(key), "Immutable report request identity changed");
      }
      const auto prior = io::get_string(record, "status"), status = io::get_string(r, "status");
      if (prior == "completed" || prior == "cancelled" || prior == "failed") {
        require(prior == status && same(r.at("result"), record.at("result")), "Terminal report request regressed");
      }
      if (prior != "pending") { require(status != "pending", "Report request regressed to pending"); }
    }
  }
  void accept_bundle(const Json &result)
  {
    Json candidate = draft;
    const auto &r = result.at("request"), &frozen_input = result.at("input"), &response = result.at("response");
    const auto rev = io::get_int(result, "revision", -1);
    bounded(frozen_input, 1024 * 1024);
    const auto &primary = frozen_input.at("context"), &message = frozen_input.at("message"), &selected = frozen_input.at("report_input");
    require(rev == revision, "Generation request was read at another project revision");
    context(primary, project_id, rev); frozen(selected, primary, project_id, rev);
    require(io::get_string(r, "id") == io::get_string(candidate, "request_id") && io::get_string(r, "project_id") == project_id &&
        r.at("prompt_version") == "stk.report-draft/1" && frozen_input.at("prompt_version") == r.at("prompt_version") &&
        same(frozen_input.at("configuration"), r.at("configuration")) && hash(frozen_input) == io::get_string(r, "input_sha256") &&
        r.at("context_id") == primary.at("id") && r.at("source_revision") == primary.at("source_revision") &&
        r.at("message_id") == message.at("id"), "Frozen report input checksum or identity differs");
    if (phase() == "import_pending") {
      // Import cannot establish whether another caller attempted a send. Never enable
      // start from this read-only path; a saved local unsent draft retains its own bit.
      candidate["send_attempted"] = true;
      candidate["context_id"] = primary.at("id"); candidate["context_sha256"] = hash(primary);
      candidate["message_id"] = message.at("id"); candidate["question"] = message.at("text");
      candidate["configuration"] = r.at("configuration"); candidate["snapshot_sha256"] = selected.at("snapshot_sha256");
      candidate["assets_sha256"] = hash(selected.at("assets"));
      Json sources = Json::array(), assets = Json::array();
      for (const auto &source : selected.at("sources")) { sources.push_back({{"kind", source.at("kind")}, {"id", source.at("id")}}); }
      for (const auto &asset : selected.at("assets")) { assets.push_back({{"record_id", asset.at("record_id")}, {"path", asset.at("path")}}); }
      candidate["selection"] = {{"expected_revision", selected.at("source_revision")}, {"snapshot_id", selected.at("snapshot_id")},
          {"sources", sources}, {"expected_sources_sha256", hash(selected.at("sources"))}, {"assets", assets}};
    }
    validate_record(r, &candidate); validate_message(message, &candidate);
    const auto &selection = candidate.at("selection");
    require(hash(primary) == io::get_string(candidate, "context_sha256") && selected.at("source_revision") == selection.at("expected_revision") &&
        selected.at("snapshot_id") == selection.at("snapshot_id") && selected.at("snapshot_sha256") == candidate.at("snapshot_sha256") &&
        hash(selected.at("assets")) == io::get_string(candidate, "assets_sha256") &&
        (selection.at("expected_sources_sha256").is_null() || hash(selected.at("sources")) == io::get_string(selection, "expected_sources_sha256")),
        "Frozen report sources differ from the reviewed intent");
    Json sources = Json::array(), assets = Json::array();
    for (const auto &source : selected.at("sources")) { sources.push_back({{"kind", source.at("kind")}, {"id", source.at("id")}}); }
    for (const auto &asset : selected.at("assets")) { assets.push_back({{"record_id", asset.at("record_id")}, {"path", asset.at("path")}}); }
    require(same(sources, selection.at("sources")) && same(assets, selection.at("assets")), "Frozen report selection changed");
    if (r.at("status") == "completed") {
      require(response.is_object() && r.at("result").is_object(), "Missing complete report reply");
      text(io::get_string(response, "text"), true);
      require(response.at("id") == r.at("assistant_message_id") && response.at("project_id") == project_id &&
          response.at("context_id") == r.at("context_id") && response.at("role") == "assistant" &&
          r.at("result").at("message_id") == response.at("id") &&
          core::Sha256::hex(io::get_string(response, "text")) == io::get_string(r.at("result"), "text_sha256") &&
          (candidate.at("response_sha256") == "" || candidate.at("response_sha256") == r.at("result").at("text_sha256")),
          "Complete report response identity or checksum differs");
    }
    else { require(response.is_null() && r.at("result").is_null(), "Non-complete request carried a reply"); }
    // Publish only after validating the whole bundle; candidate response edits survive refresh.
    candidate["input_sha256"] = r.at("input_sha256");
    if (r.at("status") == "completed") {
      candidate["response_sha256"] = r.at("result").at("text_sha256");
      if (!candidate.at("body_initialized").get<bool>()) {
        // Provider text may contain forbidden report controls. Preserve it in response();
        // reject admission into the report body instead of silently sanitizing evidence.
        try {
          text(io::get_string(response, "text"), true, true);
          candidate["body"] = response.at("text"); candidate["body_initialized"] = true;
        }
        catch (const std::exception &) { error = "The original reply contains report controls; explicitly edit a clean body before saving"; }
      }
    }
    if (candidate.at("pending_save").is_null() && phase() != "saved") {
      const auto status = io::get_string(r, "status");
      candidate["phase"] = status == "completed" ? "completed" : status == "pending" ?
          (candidate.at("send_attempted").get<bool>() ? "start_pending" : "prepared") :
          status == "running" || status == "uncertain" ? "running" : "terminal";
    }
    validate_workspace(candidate);
    draft = std::move(candidate); record = r; input = frozen_input; reply = response;
    changed(true);
  }
  bool read_bundle(std::function<void()> after = {})
  {
    const auto id = io::get_string(draft, "request_id"); if (id.empty()) { return false; }
    return call("project.reports.generation_request", {{"request_id", id}}, true, [this, after](const Json &result) {
      accept_bundle(result); if (after) { after(); }
    });
  }
  bool create_request()
  {
    Json params = {{"request_id", draft.at("request_id")}, {"message_id", draft.at("message_id")},
        {"configuration", draft.at("configuration")}, {"prompt_version", "stk.report-draft/1"}, {"report_selection", draft.at("selection")}};
    draft["phase"] = "request_pending"; changed(true);
    if (!call("project.requests.create", params, false, [this](const Json &result) {
      validate_record(result.at("request")); draft["input_sha256"] = result.at("request").at("input_sha256");
      // Reading complete frozen evidence never grants permission to send.
      read_bundle();
    })) { draft["phase"] = "message_saved"; changed(true); return false; }
    return true;
  }
  std::string blocked()
  {
    sync(); if (!input.is_object() || !record.is_object()) { return "reports.generation.review_required"; }
    auto &models = store.models(); models.sync();
    if (!models.loaded() || models.busy()) { return "reports.generation.models_loading"; }
    const auto *endpoint = models.by_adapter(io::get_string(record.at("configuration"), "adapter"));
    if (!endpoint) { return "ai.send.unknown_endpoint"; }
    const auto &models_offered = endpoint->at("models");
    if (!models_offered.is_array() || std::find(models_offered.begin(), models_offered.end(), record.at("configuration").at("model")) == models_offered.end()) {
      return "reports.generation.model_unavailable";
    }
    if (!io::get_bool(*endpoint, "allowed", false)) { return "ai.send.network"; }
    const auto key = endpoint->value("key", Json::object());
    if (io::get_bool(*endpoint, "builtin", false) && !io::get_bool(key, "configured", false)) { return "ai.missing_key"; }
    if (io::get_string(*endpoint, "location") == "external") {
      auto &labels = store.data_labels(); labels.sync();
      if (!labels.loaded() || labels.busy()) { return "reports.generation.labels_loading"; }
      const auto sources = combined_sources(input.at("context"), input.at("report_input").at("sources"), project_id, revision);
      for (const auto &source : sources) {
        if (source.at("kind") != "context" || !labels.is_public("table", io::get_string(source.at("context").at("selection"), "table_id"))) {
          return "ai.send.private";
        }
      }
      for (const auto &asset : input.at("report_input").at("assets")) {
        if (!labels.is_public("file", io::get_string(asset, "record_id"))) { return "ai.send.private"; }
      }
    }
    return {};
  }
  bool mutate_request(const std::string &method, const std::string &next)
  {
    if (!record.is_object()) { return false; }
    const auto before = phase(); draft["phase"] = next; due = deadline = -1; changed(true);
    if (!call(method, {{"request_id", draft.at("request_id")}}, false, [this](const Json &result) {
      validate_record(result.at("request"));
      deadline = -2; due = now; read_bundle();
    })) { draft["phase"] = before; changed(true); return false; }
    return true;
  }
  bool read_saved()
  {
    if (!draft.at("pending_save").is_object() || !input.is_object() || !reply.is_object()) { return false; }
    const auto save = draft.at("pending_save");
    return call("project.reports.get", {{"report_id", save.at("report_id")}}, true, [this, save](const Json &result) {
      const auto &item = result.at("report"); const auto &m = item.at("manifest");
      require(item.at("state") == "readable" && item.at("id") == save.at("report_id") && item.at("name") == save.at("name") &&
          item.at("format") == "stk.report/2" && m.at("format") == "stk.report/2" &&
          io::get_string(result, "table_id") == reports_table && io::get_int(result, "revision", -1) > io::get_int(save, "expected_revision", -1),
          "Saved report receipt differs from the original create");
      bounded(m, 384 * 1024); const auto &f = input.at("report_input"), &g = m.at("generation");
      const auto body = io::get_string(draft, "body"), body_sha = core::Sha256::hex(body);
      const Json expected = {{"format", "stk.report-generation/1"}, {"request_id", record.at("id")},
          {"message_id", record.at("message_id")}, {"assistant_message_id", record.at("assistant_message_id")},
          {"input_sha256", record.at("input_sha256")}, {"report_input_sha256", hash(f)},
          {"response_sha256", record.at("result").at("text_sha256")}, {"input_revision", f.at("source_revision")},
          {"configuration", record.at("configuration")}, {"response_metadata", record.at("result").at("metadata")},
          {"edited", body_sha != io::get_string(record.at("result"), "text_sha256")}, {"body", body}};
      require(same(g, expected) && m.at("project_id") == draft.at("project_id") && m.at("source_revision") == save.at("expected_revision") &&
          m.at("snapshot_id") == f.at("snapshot_id") && m.at("snapshot_sha256") == f.at("snapshot_sha256") &&
          m.at("entry_path") == save.at("entry_path") && same(m.at("sources"), combined_sources(input.at("context"), f.at("sources"), project_id, revision)) &&
          m.at("assets").size() == f.at("assets").size() + 1 && hash(m) == io::get_string(item, "source_sha256"),
          "Saved report content differs from the original frozen input or edited body");
      const auto &entry = m.at("assets").front(); const auto id = io::get_string(entry, "record_id");
      // Exact UUIDv5 derivation remains a backend journal check; no invented SHA-1 implementation.
      require(canonical_uuid(id) && id[14] == '5' && std::string("89ab").find(id[19]) != std::string::npos &&
          entry.at("path") == save.at("entry_path") && entry.at("mime") == mime(io::get_string(save, "entry_path")) &&
          entry.at("sha256") == body_sha && io::get_int(entry, "size", -1) == int64_t(body.size()), "Saved generated entry differs");
      for (size_t i = 0; i < f.at("assets").size(); ++i) { require(same(m.at("assets")[i + 1], f.at("assets")[i]), "Saved attachment differs"); }
      created = Created{project_id, io::get_string(save, "report_id"), io::get_string(item, "source_sha256")};
      draft["pending_save"] = nullptr; draft["phase"] = "saved"; changed(true);
    });
  }
};

ProjectReportGeneration::ProjectReportGeneration(AppStore &store) : impl_(std::make_unique<Impl>(store)) {}
ProjectReportGeneration::~ProjectReportGeneration() = default;
void ProjectReportGeneration::sync() { impl_->sync(); }
bool ProjectReportGeneration::supported() const
{
  for (const auto *method : {"project.discussion.add", "project.discussion.get", "project.requests.create", "project.requests.start",
      "project.requests.cancel", "project.requests.recover", "project.reports.generation_request", "project.reports.create_generated", "project.reports.get"}) {
    if (!impl_->supports(method)) { return false; }
  }
  return true;
}
bool ProjectReportGeneration::busy() const { return impl_->busy; }
bool ProjectReportGeneration::dirty() const { return impl_->dirty(); }
bool ProjectReportGeneration::pending() const { return impl_->pending(); }
ProjectReportGeneration::Token ProjectReportGeneration::token() { sync(); return {impl_->epoch, impl_->edit_version}; }
uint64_t ProjectReportGeneration::version() const { return impl_->version; }
const std::string &ProjectReportGeneration::error() const { return impl_->error; }
const Json &ProjectReportGeneration::draft() const { return impl_->draft; }
const Json &ProjectReportGeneration::request() const { return impl_->record; }
const Json &ProjectReportGeneration::frozen_input() const { return impl_->input; }
const Json &ProjectReportGeneration::response() const { return impl_->reply; }
bool ProjectReportGeneration::set_input(Token token, const Json &primary, std::string question,
    const Json &configuration, const Json &selection, const Json &sources, const Json &assets, const Json &snapshot_sha)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if (!supported() || s.phase() != "draft" || s.draft.at("request_id") != "") { return false; }
    text(question, false); shape(configuration, "projectRequestConfiguration", 2048);
    shape(selection, "projectReportRequestSelection", 32 * 1024);
    context(primary, s.project_id, s.revision);
    bounded(sources, 192 * 1024); bounded(assets, 192 * 1024);
    require(io::get_int(selection, "expected_revision", -1) == s.revision, "Review report inputs at the current project revision");
    Json f = {{"format", "stk.report-input/1"}, {"project_id", s.project_id}, {"source_revision", s.revision},
        {"sources", sources}, {"snapshot_id", selection.at("snapshot_id")}, {"snapshot_sha256", snapshot_sha}, {"assets", assets}};
    frozen(f, primary, s.project_id, s.revision);
    Json selected_sources = Json::array(), selected_assets = Json::array();
    for (const auto &source : sources) { selected_sources.push_back({{"kind", source.at("kind")}, {"id", source.at("id")}}); }
    for (const auto &asset : assets) { selected_assets.push_back({{"record_id", asset.at("record_id")}, {"path", asset.at("path")}}); }
    require(same(selection.at("sources"), selected_sources) && same(selection.at("assets"), selected_assets) &&
        ((sources.empty() && selection.at("expected_sources_sha256").is_null()) || hash(sources) == io::get_string(selection, "expected_sources_sha256")),
        "Report selection differs from its reviewed sources");
    Json next = s.draft; next["project_id"] = s.project_id; next["context_id"] = primary.at("id");
    next["context_sha256"] = hash(primary); next["question"] = std::move(question); next["configuration"] = configuration;
    if (!next["configuration"].contains("max_output_tokens")) { next["configuration"]["max_output_tokens"] = 4096; }
    if (next["configuration"].contains("temperature")) { next["configuration"]["temperature"] = next["configuration"].at("temperature").get<double>(); }
    next["selection"] = selection; next["snapshot_sha256"] = snapshot_sha; next["assets_sha256"] = hash(assets);
    validate_workspace(next); s.draft = std::move(next); s.reviewed_revision = s.revision; s.changed(true); return true;
  });
}
bool ProjectReportGeneration::edit(Token token, const std::string &field, std::string value)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if (s.pending() || (field == "question" && s.draft.at("request_id") != "")) { return false; }
    if (field != "question" && field != "body" && field != "name" && field != "entry_path") { return false; }
    if (field == "question" || field == "body") { text(value, false, field == "body"); }
    if (field == "name") { require(value.empty() || title(value), "Report title exceeds 256 characters"); }
    if (field == "entry_path") { require(!mime(value).empty(), "Generated entry must be Markdown or HTML"); }
    if (s.draft.at(field) == value) { return true; }
    auto next = s.draft; next[field] = std::move(value);
    if (field == "body") { next["body_initialized"] = true; }
    if (s.phase() == "saved") { next["phase"] = "completed"; }
    validate_workspace(next); s.draft = std::move(next); s.created.reset(); s.changed(true); return true;
  });
}
bool ProjectReportGeneration::prepare(Token token)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if (s.phase() == "message_saved") { return s.create_request(); }
    if (s.phase() != "draft" || s.reviewed_revision != s.revision || s.draft.at("request_id") != "") { return false; }
    text(io::get_string(s.draft, "question"), true);
    s.draft["message_id"] = uuid(); s.draft["request_id"] = uuid(); s.draft["phase"] = "message_pending"; s.changed(true);
    if (!s.call("project.discussion.add", {{"message_id", s.draft.at("message_id")}, {"context_id", s.draft.at("context_id")},
        {"role", "user"}, {"text", s.draft.at("question")}}, false, [&s](const Json &result) {
      s.validate_message(result.at("message")); s.draft["phase"] = "message_saved"; s.changed(true); s.create_request();
    })) {
      s.draft["phase"] = "draft"; s.draft["message_id"] = s.draft["request_id"] = ""; s.changed(true); return false;
    }
    return true;
  });
}
bool ProjectReportGeneration::start(Token token)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if (s.phase() != "prepared" || s.draft.at("send_attempted").get<bool>() || !s.record.is_object() || s.record.at("status") != "pending") { return false; }
    const auto reason = s.blocked(); if (!reason.empty()) { s.error = reason; s.changed(); return false; }
    s.draft["send_attempted"] = true;
    // Once dispatch is accepted this bit is never cleared, including a lost reply whose
    // first read still observes pending. Only a new explicitly discarded draft can send.
    if (!s.mutate_request("project.requests.start", "start_pending")) { s.draft["send_attempted"] = false; return false; }
    return true;
  });
}
bool ProjectReportGeneration::cancel(Token token)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if ((s.pending() && s.phase() != "start_pending") || !s.record.is_object() || !s.draft.at("pending_save").is_null() ||
        io::get_bool(s.record, "cancel_requested", false)) { return false; }
    const auto status = io::get_string(s.record, "status");
    if (status != "pending" && status != "running" && status != "uncertain") { return false; }
    return s.mutate_request("project.requests.cancel", "cancel_pending");
  });
}
bool ProjectReportGeneration::recover(Token token)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if (s.pending() || !s.record.is_object() || !s.draft.at("pending_save").is_null()) { return false; }
    const auto status = io::get_string(s.record, "status");
    return (status == "running" || status == "uncertain") && s.mutate_request("project.requests.recover", "recover_pending");
  });
}
bool ProjectReportGeneration::refresh(Token token)
{
  auto &s = *impl_; return s.guarded(token, [&] { return s.draft.at("request_id") != "" && s.read_bundle(); });
}
bool ProjectReportGeneration::check_pending(Token token)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if (s.phase() == "message_pending" || s.phase() == "message_saved") {
      return s.call("project.discussion.get", {{"message_id", s.draft.at("message_id")}}, true, [&s](const Json &result) {
        s.validate_message(result.at("message")); s.draft["phase"] = "message_saved"; s.changed(true);
      });
    }
    if (!s.draft.at("pending_save").is_null()) {
      return s.read_bundle([&s] { s.read_saved(); });
    }
    return s.draft.at("request_id") != "" && s.read_bundle();
  });
}
bool ProjectReportGeneration::open_saved_request(Token token, const std::string &id)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if (s.dirty() || !canonical_uuid(id)) { return false; }
    s.invalidate(); // A saved report's previous request cannot become this import's baseline.
    s.draft = blank(); s.draft["project_id"] = s.project_id; s.draft["request_id"] = id;
    s.draft["phase"] = "import_pending"; s.changed(true);
    return s.read_bundle();
  });
}
bool ProjectReportGeneration::create_report(Token token)
{
  auto &s = *impl_; return s.guarded(token, [&] {
    if (s.phase() != "completed" || !s.record.is_object() || s.record.at("status") != "completed" || !s.reply.is_object()) { return false; }
    text(io::get_string(s.draft, "body"), true, true); require(title(io::get_string(s.draft, "name")), "Enter a report title");
    require(!mime(io::get_string(s.draft, "entry_path")).empty(), "Generated entry must be Markdown or HTML");
    const auto id = uuid(); const auto expected = s.revision;
    s.draft["pending_save"] = {{"report_id", id}, {"expected_revision", expected}, {"name", s.draft.at("name")},
        {"entry_path", s.draft.at("entry_path")}, {"body_sha256", core::Sha256::hex(io::get_string(s.draft, "body"))}};
    s.draft["phase"] = "save_pending"; s.changed(true);
    Json params = {{"report_id", id}, {"request_id", s.draft.at("request_id")}, {"name", s.draft.at("name")},
        {"entry_path", s.draft.at("entry_path")}, {"body", s.draft.at("body")}, {"expected_revision", expected},
        {"expected_input_sha256", s.draft.at("input_sha256")}, {"expected_response_sha256", s.draft.at("response_sha256")}};
    if (!s.call("project.reports.create_generated", params, false, [&s, id, expected](const Json &result) {
      require(result.at("record_id") == id && io::get_string(result, "table_id") == reports_table &&
          io::get_int(result, "revision", -1) == expected + 1, "Report write receipt differs; check the original UUID");
      // project.changed can precede this response. Re-read only once shared state reaches
      // its new revision; otherwise leave pending for the explicit check action.
      s.project.refresh();
      s.verify_saved_when_ready = true; s.deadline = -2;
    })) { s.draft["pending_save"] = nullptr; s.draft["phase"] = "completed"; s.changed(true); return false; }
    return true;
  });
}
double ProjectReportGeneration::pump(double now)
{
  auto &s = *impl_; s.sync(); s.now = now;
  if (s.verify_saved_when_ready) {
    if (s.deadline == -2) { s.deadline = now + 90; }
    if (s.deadline < 0 || now > s.deadline) {
      s.verify_saved_when_ready = false; s.due = s.deadline = -1;
      s.error = "Save-result tracking timed out; explicitly check the original report identity";
      s.changed(); return -1;
    }
    if (!s.busy && !s.project.busy() && s.project.loaded() &&
        s.revision >= io::get_int(s.draft.at("pending_save"), "expected_revision", -1) + 1) {
      s.verify_saved_when_ready = false; s.read_bundle([&s] { s.read_saved(); });
    }
    return now + .3;
  }
  if (s.deadline == -2) { s.deadline = now + 90; }
  if (s.deadline < 0 || now > s.deadline || !s.record.is_object() || !s.draft.at("pending_save").is_null()) { s.due = s.deadline = -1; return -1; }
  const auto status = io::get_string(s.record, "status");
  if (status != "running" && status != "uncertain" && status != "pending") { s.due = s.deadline = -1; return -1; }
  if (s.busy) { return now + .3; }
  if (now >= s.due) { s.due = now + .3; if (!s.read_bundle()) { s.due = s.deadline = -1; } }
  return s.due;
}
std::string ProjectReportGeneration::send_blocked()
{
  try { return impl_->blocked(); } catch (const std::exception &) { return "reports.generation.review_required"; }
}
bool ProjectReportGeneration::discard(Token token, bool acknowledge_pending)
{
  auto &s = *impl_; s.sync();
  // Discard only changes this editor's local draft. Keep old-project text until an
  // explicit current control discards it, while remote operations retain their binding.
  if (token.epoch != s.epoch || token.edit != s.edit_version || s.busy ||
      ((s.pending() || s.draft.at("send_attempted").get<bool>()) && !acknowledge_pending)) { return false; }
  s.invalidate(); s.draft = blank(); s.error.clear(); s.changed(true); return true;
}
std::optional<ProjectReportGeneration::Created> ProjectReportGeneration::take_created()
{
  auto result = std::move(impl_->created); impl_->created.reset(); return result;
}
nlohmann::json ProjectReportGeneration::save_workspace_state() const { validate_workspace(impl_->draft); return impl_->draft; }
bool ProjectReportGeneration::valid_workspace_state(const nlohmann::json &state)
{
  try { if (!workspace_budget(state)) { return false; } const Json value = state; validate_workspace(value); return true; } catch (...) { return false; }
}
bool ProjectReportGeneration::load_workspace_state(const nlohmann::json &state)
{
  try {
    if (!workspace_budget(state)) { return false; }
    const Json value = state; validate_workspace(value);
    impl_->invalidate(); impl_->draft = value; impl_->error.clear(); impl_->changed(true); return true;
  }
  catch (...) { return false; }
}
} // namespace stk::app
