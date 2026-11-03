/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/literature_state.hh"
#include "stk/app/literature_contract.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/bridge/schema.hh"
#include "stk/core/clock.hh"
#include "stk/core/sha256.hh"
#include <algorithm>
#include <set>
#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {
const std::set<std::string> actions = {"corpora.create", "encoder.review", "encoder.select", "import.review", "import.commit",
    "import.recover", "versions.revoke", "index.start", "dense.build", "search", "citations.resolve", "pages.render"};
const std::set<std::string> reads = {"info", "corpora.list", "corpora.info", "encoder.info", "versions.list", "operations.list"};
bool content(const std::string &a) { return a == "search" || a == "citations.resolve" || a == "pages.render"; }
bool imported(const std::string &a) { return a == "corpora.create" || a == "import.review" || a == "import.commit" || a == "import.recover"; }
bool encoded(const std::string &a) { return a == "encoder.review" || a == "encoder.select"; }
std::string session(bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}
void require(bool ok) { if (!ok) { throw std::invalid_argument("literature.invalid_response"); } }
bool exact(const Json &a, const Json &b) { return io::python_json_dumps(a, true, true) == io::python_json_dumps(b, true, true); }
bool valid_reply(const std::string &action, const Json &value)
{
  check_analysis_json_bounds(value, 8 * 1024 * 1024 + 128 * 1024);
  const auto &schema = bridge::ProtocolSchema::embedded();
  return schema.check_response({{"id", 1}, {"result", value}}, "literature." + action).empty() &&
      literature_token_types(value, schema.resolved("#/$defs/methods/literature." + action + "/result"));
}
void cancel(std::map<std::string, std::shared_ptr<LiteratureState::Pending>> &);
}
struct LiteratureState::Pending { std::optional<bridge::Future<Json>> future; };
namespace {
void cancel(std::map<std::string, std::shared_ptr<LiteratureState::Pending>> &requests)
{
  auto old = std::move(requests); requests.clear();
  for (auto &[slot, pending] : old) { if (pending->future) { pending->future->cancel(); } }
}
}
LiteratureState::View::~View() { cancel(pending); }
bool LiteratureState::View::working() const { return io::get_string(operation, "state") == "running"; }
LiteratureState::LiteratureState(AppStore &store) : store_(store)
{
  const std::weak_ptr<bool> weak = alive_;
  // This observer is only a bridge-lifecycle wakeup. A project selection is not
  // a literature source or an authorization boundary.
  scope_observer_ = store_.observe_project_scope([this, weak] {
    if (auto alive = weak.lock(); alive && *alive) { follow_bridge(); }
  });
}
LiteratureState::~LiteratureState()
{
  *alive_ = false; scope_observer_.reset(); state_listener_.reset();
  for (const auto &weak : views_) { if (auto view = weak.lock()) { detach(view); } }
}
LiteratureState::ViewPtr LiteratureState::new_view()
{
  auto view = std::make_shared<View>(); views_.push_back(view); return view;
}
bool LiteratureState::corpus_id(const std::string &s)
{
  return s.size() == 38 && s.starts_with("local_") && std::all_of(s.begin() + 6, s.end(), [](char c) {
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
  });
}
std::string LiteratureState::new_uuid()
{
  auto s = new_idempotency_key(); s[12] = '4'; s[16] = "89ab"[s[16] % 4];
  return s.substr(0, 8) + "-" + s.substr(8, 4) + "-" + s.substr(12, 4) + "-" + s.substr(16, 4) + "-" + s.substr(20);
}
std::string LiteratureState::checksum(const Json &value)
{
  check_analysis_json_bounds(value, 8 * 1024 * 1024);
  return core::Sha256::hex(io::python_json_dumps(value, true, true));
}
std::string LiteratureState::request_sha256(const std::string &action, const Json &params)
{
  check_analysis_json_bounds(params, 32 * 1024);
  return core::Sha256::hex(io::python_json_dumps(Json{{"action", action}, {"params", params}}, true, true));
}
bool LiteratureState::operation_matches(const Json &operation, const std::string &id, const Expected *expected)
{
  try {
    check_analysis_json_bounds(operation, 128 * 1024);
    if (!canonical_uuid(id) || io::get_string(operation, "operation_id") != id ||
        !valid_reply("operations.get", {{"operation", operation}})) { return false; }
    const auto state = io::get_string(operation, "state");
    if (state == "completed" ? operation.at("result_sha256").is_null() || !operation.at("error").is_null() :
        !operation.at("result_sha256").is_null()) { return false; }
    return !expected || (io::get_string(operation, "action") == expected->action &&
        io::get_string(operation, "request_sha256") == expected->request_sha256);
  }
  catch (const std::exception &) { return false; }
}
void LiteratureState::clear_page(View &view)
{
  view.values.erase("citations.resolve"); view.values.erase("pages.render");
  view.citation = nullptr; view.historical_result = nullptr; ++view.page_epoch;
  if (view.on_content_invalidated) {
    try { view.on_content_invalidated(); }
    catch (...) { view.error = "literature.invalid_page"; }
  }
}
void LiteratureState::clear_content(View &view)
{
  view.values.erase("search"); clear_page(view);
}
void LiteratureState::detach(const ViewPtr &view)
{
  if (view->busy() || view->working()) { view->uncertain = true; }
  ++view->lifetime_epoch; view->follow_until = view->next_poll = 0; cancel(view->pending); clear_content(*view); ++view->version;
  view->values.erase("import.review"); view->values.erase("encoder.review");
}
void LiteratureState::follow_bridge()
{
  auto *client = store_.bridge(); const auto identity = session(client);
  if (client == client_ && identity == session_ && store_.bridge_epoch() == bridge_epoch_) { return; }
  if (client != client_) {
    state_listener_.reset();
    if (client) {
      const std::weak_ptr<bool> weak = alive_;
      state_listener_ = client->on_state([this, weak](auto, const auto &) {
        if (auto alive = weak.lock(); alive && *alive) { follow_bridge(); }
      });
    }
  }
  client_ = client; session_ = identity; bridge_epoch_ = store_.bridge_epoch(); ++epoch_; ++encoder_epoch_;
  corpora_.clear(); encoder_ = nullptr;
  std::erase_if(views_, [](const auto &weak) { return weak.expired(); });
  for (const auto &weak : views_) { if (auto view = weak.lock()) {
    detach(view); ++view->corpus_epoch; ++view->scope_epoch; view->values.clear();
    // Originals remain observations of the old session. They cannot repopulate a current form.
  } }
  store_.changed();
}
void LiteratureState::sync(const ViewPtr &) { follow_bridge(); }
bool LiteratureState::supported() const
{
  if (!client_ || session_.empty()) { return false; }
  const auto hello = client_->hello_info(); if (!hello) { return false; }
  for (const auto &action : actions) { if (!hello->has_method("literature." + action)) { return false; } }
  for (const auto &action : reads) { if (!hello->has_method("literature." + action)) { return false; } }
  return hello->has_method("literature.operations.get") && hello->has_method("literature.operations.result");
}
bool LiteratureState::set_corpus(const ViewPtr &view, const std::string &value)
{
  follow_bridge(); if (!value.empty() && !corpus_id(value)) { return false; }
  ++view->corpus_epoch; ++view->import_epoch; view->corpus = value; view->version_id.clear();
  for (const auto &key : {"import.review", "import.commit", "import.recover", "index.start", "versions.revoke", "dense.build", "versions.list"}) { view->values.erase(key); }
  ++view->version; store_.changed(); return true;
}
bool LiteratureState::set_scopes(const ViewPtr &view, std::vector<std::string> values)
{
  follow_bridge(); if (values.size() > 8 || std::any_of(values.begin(), values.end(), [](const auto &s) { return !corpus_id(s); })) { return false; }
  std::sort(values.begin(), values.end()); if (std::adjacent_find(values.begin(), values.end()) != values.end()) { return false; }
  ++view->scope_epoch; view->scopes = std::move(values); clear_content(*view); ++view->version; store_.changed(); return true;
}
bool LiteratureState::set_version(const ViewPtr &view, const std::string &value)
{
  follow_bridge(); if (!value.empty() && !canonical_uuid(value)) { return false; }
  ++view->corpus_epoch; view->version_id = value; ++view->version; store_.changed(); return true;
}
bool LiteratureState::set_citation(const ViewPtr &view, const Json &value)
{
  follow_bridge();
  try {
    Json params{{"operation_id", new_uuid()}, {"scopes", view->scopes}, {"citation", value}};
    if (!bridge::ProtocolSchema::embedded().check_request({{"id", 1}, {"method", "literature.citations.resolve"}, {"params", params}}).empty()) { return false; }
    const auto scope = io::get_string(value, "corpus_id"); const auto *known = corpus_info(scope);
    if (!known || io::get_string(*known, "database_id") != io::get_string(value, "database_id")) { return false; }
    clear_page(*view); view->citation = value; ++view->version; store_.changed(); return true;
  }
  catch (const std::exception &) { return false; }
}
void LiteratureState::invalidate_import_draft(const ViewPtr &view)
{
  ++view->import_epoch; view->values.erase("import.review"); ++view->version; store_.changed();
}
void LiteratureState::invalidate_query_draft(const ViewPtr &view)
{
  ++view->query_epoch; clear_content(*view); ++view->version; store_.changed();
}
void LiteratureState::invalidate_encoder_draft(const ViewPtr &view)
{
  ++view->encoder_draft_epoch; view->values.erase("encoder.review"); ++view->version; store_.changed();
}
const Json *LiteratureState::corpus_info(const std::string &id) const
{
  const auto found = corpora_.find(id); return found == corpora_.end() ? nullptr : &found->second;
}
void LiteratureState::invalidate_corpus(const std::string &id)
{
  for (const auto &weak : views_) { if (auto view = weak.lock()) {
    if (view->corpus == id) { ++view->corpus_epoch; view->values.erase("import.review"); }
    if (std::find(view->scopes.begin(), view->scopes.end(), id) != view->scopes.end()) { ++view->scope_epoch; clear_content(*view); }
    ++view->version;
  } }
}
void LiteratureState::observe_corpus(const Json &value)
{
  const auto id = io::get_string(value, "corpus_id"); const auto old = corpora_.find(id);
  if (old != corpora_.end() && (io::get_string(old->second, "database_id") != io::get_string(value, "database_id") ||
      io::get_int(value, "generation", -1) < io::get_int(old->second, "generation", -1))) {
    invalidate_corpus(id); corpora_.erase(id); require(false);
  }
  if (old != corpora_.end() && !exact(old->second, value)) { invalidate_corpus(id); }
  corpora_[id] = value;
}
void LiteratureState::observe_encoder(const Json &value)
{
  const bool invalid = !encoder_.is_null() && (io::get_int(value, "generation", -1) < io::get_int(encoder_, "generation", -1) ||
      (io::get_int(value, "generation", -1) == io::get_int(encoder_, "generation", -1) && !exact(encoder_, value)));
  if (!encoder_.is_null() && !exact(encoder_, value)) {
    ++encoder_epoch_;
    for (const auto &weak : views_) { if (auto view = weak.lock()) { clear_content(*view); ++view->version; } }
  }
  if (invalid) { encoder_ = nullptr; require(false); }
  encoder_ = value;
}
bool LiteratureState::current(const View &view, const Expected &e) const
{
  if (e.bridge_session != session_ || e.bridge_epoch != bridge_epoch_ || e.lifetime_epoch != view.lifetime_epoch) { return false; }
  if (imported(e.action) && (e.import_epoch != view.import_epoch || e.corpus_epoch != view.corpus_epoch)) { return false; }
  if (encoded(e.action) && e.encoder_draft_epoch != view.encoder_draft_epoch) { return false; }
  if (e.action == "encoder.select" && e.encoder_epoch != encoder_epoch_) { return false; }
  if (e.request.contains("corpus_id") && e.corpus_epoch != view.corpus_epoch) { return false; }
  if (content(e.action) && e.scope_epoch != view.scope_epoch) { return false; }
  if (e.action == "search" && (e.query_epoch != view.query_epoch || e.encoder_epoch != encoder_epoch_)) { return false; }
  if ((e.action == "citations.resolve" || e.action == "pages.render") && e.page_epoch != view.page_epoch) { return false; }
  for (const auto &[id, bound] : e.corpora) {
    const auto *info = corpus_info(id);
    if (!info || io::get_string(*info, "database_id") != bound.database_id || io::get_int(*info, "generation", -1) != bound.generation) { return false; }
  }
  return true;
}
bool LiteratureState::prepare(const View &view, Expected &e) const
{
  const auto &p = e.request;
  e.bridge_session = session_; e.bridge_epoch = bridge_epoch_; e.encoder_epoch = encoder_epoch_; e.lifetime_epoch = view.lifetime_epoch;
  e.corpus_epoch = view.corpus_epoch; e.scope_epoch = view.scope_epoch; e.import_epoch = view.import_epoch;
  e.query_epoch = view.query_epoch; e.encoder_draft_epoch = view.encoder_draft_epoch; e.page_epoch = view.page_epoch;
  auto bind = [&](const std::string &id) {
    const auto *info = corpus_info(id);
    if (!info || !canonical_uuid(io::get_string(*info, "database_id")) || io::get_int(*info, "generation", -1) < 0) { return false; }
    e.corpora[id] = {io::get_string(*info, "database_id"), io::get_int(*info, "generation", -1)}; return true;
  };
  if (p.contains("corpus_id") && (io::get_string(p, "corpus_id") != view.corpus || !bind(view.corpus))) { return false; }
  if (p.contains("scopes")) {
    if (!exact(p.at("scopes"), Json(view.scopes)) || view.scopes.empty()) { return false; }
    for (const auto &id : view.scopes) { if (!bind(id)) { return false; } }
  }
  if (p.contains("citation") && (!exact(p.at("citation"), view.citation) ||
      io::get_string(p.at("citation"), "database_id") != e.corpora.at(io::get_string(p.at("citation"), "corpus_id")).database_id)) { return false; }
  if ((e.action == "index.start" || e.action == "versions.revoke") && io::get_string(p, "version_id") != view.version_id) { return false; }
  if (e.action == "search" || e.action == "dense.build") {
    if (!encoder_.is_object() || !encoder_.contains("selection") || encoder_.at("selection").is_null() ||
        io::get_int(p, "encoder_generation", -1) != io::get_int(encoder_, "generation", -1)) { return false; }
    e.encoder_fingerprint = io::get_string(encoder_.at("selection"), "fingerprint");
    if (e.action == "dense.build" && io::get_int(p, "expected_generation", -1) != e.corpora.at(view.corpus).generation) { return false; }
  }
  if (e.action == "encoder.select" || e.action == "import.commit") {
    const auto review_action = e.action == "encoder.select" ? "encoder.review" : "import.review";
    const auto review = view.values.find(review_action); const auto latest = view.latest_operations.find(review_action);
    const auto original = view.originals.find(io::get_string(p, "review_id"));
    if (review == view.values.end() || latest == view.latest_operations.end() || latest->second != io::get_string(p, "review_id") ||
        original == view.originals.end() || !current(view, original->second) || checksum(review->second) != io::get_string(p, "review_sha256")) { return false; }
    if (e.action == "encoder.select" && io::get_int(p, "expected_generation", -1) != io::get_int(encoder_, "generation", -2)) { return false; }
    if (e.action == "import.commit" && !bind(io::get_string(review->second, "corpus_id"))) { return false; }
  }
  return true;
}
bool LiteratureState::call(const ViewPtr &view, const std::string &slot, const std::string &action, Json params, Apply apply, const Expected *expected)
{
  follow_bridge();
  if (!supported() || view->pending.contains(slot)) { return false; }
  try {
    check_analysis_json_bounds(params, 32 * 1024);
    if (!literature_shape(params, bridge::ProtocolSchema::embedded().resolved("#/$defs/methods/literature." + action + "/params"))) { return false; }
  }
  catch (const std::exception &) { return false; }
  const auto epoch = epoch_, lifetime = view->lifetime_epoch;
  const auto pending = std::make_shared<Pending>(); view->pending[slot] = pending;
  const std::weak_ptr<bool> alive = alive_; const std::weak_ptr<View> weak = view; const std::weak_ptr<Pending> request = pending;
  const auto bound = expected ? std::optional<Expected>(*expected) : std::nullopt;
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  pending->future = client_->call("literature." + action, std::move(params), options);
  pending->future->then([this, alive, weak, request, epoch, lifetime, slot, action, bound, apply = std::move(apply)](bridge::Result<Json> result) {
    const auto live = alive.lock(); const auto view = weak.lock(); const auto pending = request.lock();
    if (!live || !*live || !view || !pending) { return; }
    // Comparing the actual bridge protects replies queued before a same-client detach/reattach.
    if (epoch != epoch_ || store_.bridge() != client_ || store_.bridge_epoch() != bridge_epoch_ || session(store_.bridge()) != session_ ||
        lifetime != view->lifetime_epoch || !view->pending.contains(slot) || view->pending.at(slot) != pending) { return; }
    view->pending.erase(slot);
    if (bound && !current(*view, *bound)) {
      if (slot == "write") { view->uncertain = true; }
      view->follow_until = 0;
      ++view->version; store_.changed(); return;
    }
    if (!result) {
      view->error = result.error().message;
      if (slot == "write") { view->uncertain = true; }
      if (action == "operations.result") { clear_content(*view); }
      view->follow_until = 0;
    }
    else {
      try { require(valid_reply(action, result.value())); apply(view, result.value()); view->error.clear(); }
      catch (const std::exception &) { view->error = "literature.invalid_response"; if (slot == "write") { view->uncertain = true; } clear_content(*view); view->follow_until = 0; }
    }
    ++view->version; store_.changed();
  });
  store_.changed(); return true;
}
bool LiteratureState::read(const ViewPtr &view, const std::string &action, Json params)
{
  follow_bridge(); if (!reads.contains(action)) { return false; }
  if ((action == "corpora.info" || action == "versions.list") && io::get_string(params, "corpus_id") != view->corpus &&
      std::find(view->scopes.begin(), view->scopes.end(), io::get_string(params, "corpus_id")) == view->scopes.end()) { return false; }
  const auto target = io::get_string(params, "corpus_id"); const auto corpus_epoch = view->corpus_epoch, scope_epoch = view->scope_epoch;
  return call(view, "read:" + action + ":" + target, action, std::move(params),
      [this, action, target, corpus_epoch, scope_epoch](const ViewPtr &v, const Json &reply) {
    if (!target.empty() && (v->corpus_epoch != corpus_epoch || v->scope_epoch != scope_epoch)) { return; }
    if (action == "corpora.info") { require(io::get_string(reply, "corpus_id") == target); observe_corpus(reply); }
    if (action == "encoder.info") { observe_encoder(reply); }
    if (action == "info" || action == "corpora.list") {
      std::set<std::string> present;
      for (const auto &item : reply.at("corpora")) {
        const auto id = io::get_string(item, "corpus_id"); present.insert(id);
        const auto old = corpora_.find(id);
        if (old != corpora_.end() && io::get_string(old->second, "database_id") != io::get_string(item, "database_id")) { invalidate_corpus(id); corpora_.erase(id); }
      }
      std::vector<std::string> removed;
      for (const auto &[id, info] : corpora_) { if (!present.contains(id)) { removed.push_back(id); } }
      for (const auto &id : removed) { invalidate_corpus(id); corpora_.erase(id); }
    }
    v->values[action] = reply;
  });
}
bool LiteratureState::act(const ViewPtr &view, const std::string &action, Json params)
{
  follow_bridge();
  if (!actions.contains(action) || !params.is_object() || params.contains("python") || !supported() || view->busy() ||
      view->working() || view->originals.size() >= 128) { return false; }
  if (!params.contains("operation_id")) { params["operation_id"] = new_uuid(); }
  const auto id = io::get_string(params, "operation_id");
  if (!canonical_uuid(id) || view->originals.contains(id)) { return false; }
  Expected e{}; e.action = action; e.request = params;
  try {
    e.request_sha256 = request_sha256(action, params);
    if (!literature_shape(params, bridge::ProtocolSchema::embedded().resolved("#/$defs/methods/literature." + action + "/params")) || !prepare(*view, e)) { return false; }
  }
  catch (const std::exception &) { view->error = "literature.invalid_params"; return false; }
  // Revocation removes every tab's cached content before sending its explicit
  // request; a failed reply cannot silently put the old image back.
  if (action == "versions.revoke") { invalidate_corpus(view->corpus); if (!prepare(*view, e)) { return false; } }
  const auto old_id = view->operation_id; const auto old = view->operation; const auto old_uncertain = view->uncertain;
  const auto old_latest = view->latest_operations.find(action); const auto previous_latest = old_latest == view->latest_operations.end() ? std::string() : old_latest->second;
  const auto cached = view->values.find(action); const auto old_cached = cached == view->values.end() ? std::optional<Json>() : std::optional<Json>(cached->second);
  view->originals[id] = e; view->operation_id = id; view->operation = nullptr; view->uncertain = true;
  view->latest_operations[action] = id; view->values.erase(action); view->historical_result = nullptr;
  if (content(action)) { view->values.erase(action); }
  if (!call(view, "write", action, std::move(params), [this](const ViewPtr &v, const Json &reply) { accept_operation(v, reply); }, &e)) {
    view->originals.erase(id); view->latest_operations.erase(action); view->operation_id = old_id; view->operation = old;
    if (current(*view, e)) {
      if (!previous_latest.empty()) { view->latest_operations[action] = previous_latest; }
      if (old_cached) { view->values[action] = *old_cached; }
    }
    view->uncertain = old_uncertain; return false;
  }
  if (action == "search") { clear_content(*view); }
  view->started = core::monotonic_seconds();
  view->follow_until = view->started + (action == "dense.build" ? io::get_int(e.request, "timeout", 600) + 15 : action == "search" ? 140 : 85);
  view->next_poll = view->started + .3; return true;
}
void LiteratureState::accept_operation(const ViewPtr &view, const Json &reply)
{
  const auto &op = reply.at("operation");
  if (op.is_null()) { view->uncertain = true; view->follow_until = 0; return; }
  const auto found = view->originals.find(view->operation_id);
  require(operation_matches(op, view->operation_id, found == view->originals.end() ? nullptr : &found->second));
  view->operation = op; view->uncertain = io::get_string(op, "state") == "uncertain";
  if (view->uncertain) { view->follow_until = 0; }
  view->next_poll = core::monotonic_seconds() + .3;
}
bool LiteratureState::select_operation(const ViewPtr &view, const Json &operation)
{
  follow_bridge(); const auto id = io::get_string(operation, "operation_id");
  if (view->busy() || !operation_matches(operation, id)) { return false; }
  const auto e = view->originals.find(id);
  if (e != view->originals.end() && !operation_matches(operation, id, &e->second)) { return false; }
  detach(view); view->operation_id = id; view->operation = operation;
  view->uncertain = io::get_string(operation, "state") == "uncertain"; ++view->version; return true;
}
bool LiteratureState::check_operation(const ViewPtr &view)
{
  const auto id = view->operation_id;
  if (view->busy() || !canonical_uuid(id)) { return false; }
  const bool accepted = call(view, "operation", "operations.get", {{"operation_id", id}}, [this, id](const ViewPtr &v, const Json &reply) {
    if (v->operation_id == id) { accept_operation(v, reply); }
  });
  if (accepted && view->follow_until <= core::monotonic_seconds()) { view->follow_until = core::monotonic_seconds() + 90; }
  return accepted;
}
bool LiteratureState::result_matches(const Expected &e, const Json &r) const
{
  const auto &p = e.request;
  if (e.action == "corpora.create") {
    auto expected = io::get_string(p, "operation_id"); std::erase(expected, '-');
    return io::get_string(r, "corpus_id") == "local_" + expected;
  }
  if (e.action == "encoder.review") { return io::get_string(r, "assets") == io::get_string(p, "assets") && checksum(r.at("identity")) == io::get_string(r, "fingerprint"); }
  if (e.action == "encoder.select") { return io::get_int(r, "encoder_generation", -1) == io::get_int(p, "expected_generation", -2) + 1; }
  if (e.action == "import.review") {
    const auto id = io::get_string(p, "corpus_id"); const auto found = e.corpora.find(id);
    return found != e.corpora.end() && io::get_string(r, "corpus_id") == id && io::get_string(r, "database_id") == found->second.database_id &&
        io::get_int(r, "corpus_generation", -1) == found->second.generation && io::get_string(r, "source") == io::get_string(p, "source") &&
        io::get_string(r, "document_id") == io::get_string(p, "document_id") && io::get_string(r, "title") == io::get_string(p, "title") && exact(r.at("authorization"), p.at("authorization"));
  }
  if (e.action == "search") {
    if (io::get_string(r, "query_sha256") != core::Sha256::hex(io::get_string(p, "query")) || r.at("scopes").size() != e.corpora.size()) { return false; }
    std::set<std::string> seen;
    for (const auto &scope : r.at("scopes")) {
      const auto id = io::get_string(scope, "corpus_id"); const auto bound = e.corpora.find(id);
      if (bound == e.corpora.end() || !seen.insert(id).second || io::get_string(scope, "database_id") != bound->second.database_id ||
          io::get_int(scope, "corpus_generation", -1) != bound->second.generation || io::get_string(scope, "encoder_fingerprint") != e.encoder_fingerprint) { return false; }
    }
    for (const auto &hit : r.at("hits")) {
      const auto id = io::get_string(hit, "corpus_id"); const auto bound = e.corpora.find(id);
      if (bound == e.corpora.end() || io::get_string(hit, "database_id") != bound->second.database_id ||
          io::get_string(hit.at("citation"), "database_id") != bound->second.database_id ||
          io::get_string(hit.at("citation"), "corpus_id") != id) { return false; }
    }
  }
  else if (e.action == "citations.resolve" || e.action == "pages.render") { return exact(r.at("citation"), p.at("citation")); }
  else if (!encoded(e.action)) {
    if (io::get_string(r, "operation_id") != io::get_string(p, "operation_id")) { return false; }
    if (p.contains("version_id") && io::get_string(r.at("receipt"), "version_id") != io::get_string(p, "version_id")) { return false; }
    if (e.action == "dense.build" && (io::get_int(r.at("receipt"), "corpus_generation", -1) != io::get_int(p, "expected_generation", -2) ||
        io::get_string(r.at("receipt"), "encoder_fingerprint") != e.encoder_fingerprint)) { return false; }
  }
  return true;
}
void LiteratureState::accept_result(const ViewPtr &view, const Expected &e, const Json &result)
{
  require(result_matches(e, result));
  if (e.action == "encoder.select") { observe_encoder({{"generation", result.at("encoder_generation")}, {"selection", {{"assets_sha256", view->values.at("encoder.review").at("assets_sha256")}, {"fingerprint", result.at("fingerprint")}, {"review_id", e.request.at("review_id")}}}}); }
  if (e.action == "import.commit" || e.action == "import.recover" || e.action == "index.start" || e.action == "versions.revoke" || e.action == "dense.build") {
    const auto id = e.corpora.begin()->first; auto updated = corpora_.at(id); const auto &receipt = result.at("receipt");
    invalidate_corpus(id);
    if (e.action == "dense.build") {
      updated["dense_generation"] = receipt.at("generation"); updated["dense_source_generation"] = receipt.at("corpus_generation");
      updated["dense_encoder_fingerprint"] = receipt.at("encoder_fingerprint");
    }
    else { updated["generation"] = e.action == "import.recover" ? receipt.at("import").at("generation") : receipt.at("generation"); }
    corpora_[id] = updated;
    if (e.action == "import.commit" || e.action == "import.recover") { view->version_id = io::get_string(e.action == "import.recover" ? receipt.at("import") : receipt, "version_id"); }
  }
  view->values[e.action] = result;
}
bool LiteratureState::fetch_result(const ViewPtr &view, const bool explicit_read)
{
  const auto id = view->operation_id;
  if (view->busy() || !operation_matches(view->operation, id) || io::get_string(view->operation, "state") != "completed") { return false; }
  const auto op = view->operation; const auto found = view->originals.find(id);
  const auto expected = found == view->originals.end() ? std::optional<Expected>() : std::optional<Expected>(found->second);
  const bool eligible = expected && current(*view, *expected) && view->latest_operations[expected->action] == id;
  if ((!explicit_read || content(io::get_string(op, "action"))) && !eligible) { view->follow_until = 0; return false; }
  return call(view, "result", "operations.result", {{"operation_id", id}, {"expected_request_sha256", op.at("request_sha256")}},
      [this, id, op, expected, explicit_read](const ViewPtr &v, const Json &reply) {
    if (v->operation_id != id) { return; }
    require(exact(reply.at("operation"), op)); const auto &result = reply.at("result");
    require(checksum(result) == io::get_string(op, "result_sha256"));
    const bool eligible = expected && current(*v, *expected) && v->latest_operations[expected->action] == id;
    if (content(io::get_string(op, "action")) && !eligible) { v->follow_until = 0; return; }
    if (explicit_read) { v->historical_result = result; }
    if (eligible) { accept_result(v, *expected, result); }
    v->follow_until = 0;
  });
}
bool LiteratureState::load_result(const ViewPtr &view) { return fetch_result(view, true); }
void LiteratureState::pump(const ViewPtr &view)
{
  follow_bridge(); const auto now = core::monotonic_seconds();
  if (view->follow_until <= now) { view->follow_until = 0; return; }
  if (view->busy() || view->pending.contains("operation") || view->pending.contains("result") || now < view->next_poll) { return; }
  if (io::get_string(view->operation, "state") == "completed") { fetch_result(view, false); }
  else if (!check_operation(view)) { view->follow_until = 0; }
}
}  // namespace stk::app
