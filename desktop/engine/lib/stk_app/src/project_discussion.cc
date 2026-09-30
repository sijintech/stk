/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_discussion.hh"
#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace stk::app {
using io::Json;

void ProjectDiscussion::reset()
{
  ++epoch_;
  ++version_;
  busy_ = false;
  error_.clear();
  origin_draft_.clear();
  contexts_ = messages_ = proposals_ = request_page_ = {};
  context_ = message_ = origin_ = requests_ = generation_request_ = Json::object();
  provider_ = Json::object(); provider_loaded_ = false;
  ++exchange_generation_; ++exchange_flight_;
  exchange_request_ = exchange_context_ = exchange_question_ = exchange_reply_ = exchange_progress_ = Json::object();
  exchange_id_.clear(); exchange_error_.clear();
  exchange_preparing_ = exchange_reading_ = exchange_pending_ = exchange_following_ = false;
  exchange_clock_seen_ = false;
  exchange_now_ = exchange_due_ = exchange_wake_scheduled = 0; exchange_deadline_ = -1;
}

bool ProjectDiscussion::supported() const
{
  if (!project_.ready() || !project_.loaded() || project_.project()->format_version < 7) { return false; }
  const auto hello = store_.bridge()->hello_info();
  for (const auto *method : {"project.contexts.capture", "project.contexts.get", "project.contexts.list",
       "project.discussion.add", "project.discussion.get", "project.discussion.list",
       "project.discussion.link_draft", "project.discussion.proposals"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

const ProjectDiscussionPage &ProjectDiscussion::page(const std::string &kind) const
{
  return kind == "contexts" ? contexts_ : kind == "messages" ? messages_ : kind == "requests" ? request_page_ : proposals_;
}

bool ProjectDiscussion::requests_supported() const
{
  if (!supported() || project_.project()->format_version < 8) { return false; }
  const auto hello = store_.bridge()->hello_info();
  for (const auto *method : {"project.requests.create", "project.requests.get", "project.requests.list", "project.requests.cancel"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

bool ProjectDiscussion::call(const std::string &method, Json params,
                            std::function<void(const Json &)> done, const bool preserve_error,
                            std::function<void(const std::string &)> failed)
{
  if (!supported() || busy_ || project_.busy()) { return false; }
  if (method.rfind("project.requests.", 0) == 0 && !requests_supported()) { return false; }
  const auto handle = project_.project()->handle;
  params["handle"] = handle;
  busy_ = true;
  if (!preserve_error) { error_.clear(); }
  std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  store_.bridge()->call(method, params, options).then(
      [this, weak, epoch, handle, done = std::move(done), failed = std::move(failed)](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || !project_.project() || project_.project()->handle != handle) { return; }
    busy_ = false;
    if (!result.ok()) {
      error_ = result.error().message;
      store_.log(error_);
      if (failed) { failed(error_); }
      // An external writer can advance the project without a bridge event.
      project_.refresh();
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &exc) { error_ = exc.what(); if (failed) { failed(error_); } }
    }
    ++version_;
    store_.changed();
  });
  store_.changed();
  return true;
}

bool ProjectDiscussion::generation_supported() const
{
  if (!requests_supported()) { return false; }
  const auto hello = store_.bridge()->hello_info();
  for (const auto *method : {"project.requests.provider", "project.requests.start", "project.requests.recover"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

bool ProjectDiscussion::progress_supported() const
{
  if (!requests_supported()) { return false; }
  const auto hello = store_.bridge()->hello_info();
  return hello && hello->has_method("project.requests.progress");
}

bool ProjectDiscussion::load_provider()
{
  if (!generation_supported()) { return false; }
  const bool accepted = call("project.requests.provider", Json::object(), [this](const Json &result) {
    provider_ = result.at("provider");
  }, true);
  if (accepted) { provider_loaded_ = true; }
  return accepted;
}

bool ProjectDiscussion::create_request(const std::string &model)
{
  if (!generation_supported() || busy_ || project_.busy() || provider_.empty() || message_.empty() ||
      message_.at("role") != "user") { return false; }
  auto params = request("generation", {{"message_id", message_.at("id")}, {"configuration",
      {{"adapter", provider_.at("adapter")}, {"model", model}, {"max_output_tokens", 4096}}}}, "request_id");
  return call("project.requests.create", std::move(params), [this](const Json &result) {
    generation_request_ = result.at("request"); request_page_.loaded = false;
  });
}

bool ProjectDiscussion::start_request(const std::string &id)
{
  if (!generation_supported()) { return false; }
  return mutate_request("project.requests.start", id);
}

bool ProjectDiscussion::recover_request(const std::string &id)
{
  if (!generation_supported()) { return false; }
  return mutate_request("project.requests.recover", id);
}

Json ProjectDiscussion::request(const std::string &kind, Json params, const std::string &id_key)
{
  // Keep the caller identity after errors/lost replies. Changing the request creates a new ID.
  if (requests_.contains(kind) && requests_.at(kind).at("params") == params) {
    params[id_key] = requests_.at(kind).at("id");
    return params;
  }
  const auto hex = new_idempotency_key();
  const auto id = hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) + "-" +
                  hex.substr(16, 4) + "-" + hex.substr(20);
  requests_[kind] = {{"params", params}, {"id", id}};
  params[id_key] = id;
  return params;
}

bool ProjectDiscussion::load_page(const std::string &kind, const int64_t offset, const bool preserve_error)
{
  if ((kind != "contexts" && kind != "messages" && kind != "proposals" && kind != "requests") || offset < 0) { return false; }
  const auto method = kind == "contexts" ? "project.contexts.list" :
                      kind == "messages" ? "project.discussion.list" : kind == "requests" ? "project.requests.list" : "project.discussion.proposals";
  const bool accepted = call(method, {{"offset", offset}, {"limit", 100}}, [this, kind, offset](const Json &result) {
    auto &page = kind == "contexts" ? contexts_ : kind == "messages" ? messages_ : kind == "requests" ? request_page_ : proposals_;
    page.items = result.at(kind);
    page.offset = offset;
    page.next = result.at("next_offset").is_null() ? -1 : result.at("next_offset").get<int64_t>();
    page.loaded = true;
  }, preserve_error);
  // A failed read remains inspectable until explicit refresh, instead of retrying every frame.
  if (accepted) { (kind == "contexts" ? contexts_ : kind == "messages" ? messages_ : kind == "requests" ? request_page_ : proposals_).loaded = true; }
  return accepted;
}

bool ProjectDiscussion::load_context(const std::string &id)
{
  return call("project.contexts.get", {{"context_id", id}}, [this](const Json &result) {
    context_ = result.at("context");
  });
}

bool ProjectDiscussion::load_message(const std::string &id)
{
  return call("project.discussion.get", {{"message_id", id}}, [this](const Json &result) {
    message_ = result.at("message");
  });
}

bool ProjectDiscussion::load_request(const std::string &id)
{
  return call("project.requests.get", {{"request_id", id}}, [this](const Json &result) {
    generation_request_ = result.at("request");
    for (auto &item : request_page_.items) {
      if (item.at("id") == generation_request_.at("id")) { item = generation_request_; }
    }
  });
}

bool ProjectDiscussion::cancel_request(const std::string &id)
{
  return mutate_request("project.requests.cancel", id);
}

bool ProjectDiscussion::mutate_request(const std::string &method, const std::string &id)
{
  const bool accepted = call(method, {{"request_id", id}}, [this, id](const Json &result) {
    generation_request_ = result.at("request"); request_page_.loaded = false;
    if (exchange_id_ == id) {
      // Keep the last coherent bundle until the new request and any saved reply
      // have been read together. Earlier polling snapshots are already fenced.
      exchange_pending_ = true;
      exchange_deadline_ = -1;
      exchange_due_ = exchange_now_;
      exchange_error_.clear();
    }
  }, false, [this, id](const std::string &error) {
    if (exchange_id_ == id) { exchange_failed(error); }
  });
  if (accepted && exchange_id_ == id) {
    ++exchange_generation_;
    exchange_pending_ = exchange_following_ = false;
    if (method == "project.requests.cancel") { exchange_progress_ = Json::object(); }
    exchange_error_.clear();
    exchange_wake_scheduled = 0;
  }
  return accepted;
}

void ProjectDiscussion::exchange_changed()
{
  ++version_;
  store_.changed();
}

void ProjectDiscussion::exchange_failed(const std::string &error)
{
  exchange_preparing_ = exchange_pending_ = exchange_following_ = false;
  exchange_error_ = error;
  exchange_wake_scheduled = 0;
  exchange_changed();
}

bool ProjectDiscussion::prepare_question(const std::string &context_id, const std::string &text,
                                         const std::string &model)
{
  if (!generation_supported() || busy_ || project_.busy() || exchange_reading_ || provider_.empty() || context_.empty() ||
      io::get_string(context_, "id") != context_id || text.empty() || model.empty()) { return false; }
  const Json saved_context = context_;
  const auto message_params = request("exchange_message", {{"context_id", context_id}, {"text", text}, {"role", "user"}},
                                      "message_id");
  const auto request_params = request("exchange_generation", {{"message_id", message_params.at("message_id")},
      {"configuration", {{"adapter", provider_.at("adapter")}, {"model", model}, {"max_output_tokens", 4096}}}},
      "request_id");
  const auto id = request_params.at("request_id").get<std::string>();
  const bool accepted = call("project.discussion.add", message_params,
      [this, saved_context, message_params, request_params](const Json &result) {
    const auto question = result.at("message");
    if (question.at("id") != message_params.at("message_id") ||
        question.at("context_id") != saved_context.at("id") ||
        question.at("role") != "user" || question.at("text") != message_params.at("text")) {
      throw std::runtime_error("Saved question does not match its prepared input");
    }
    messages_.loaded = false;
    if (!call("project.requests.create", request_params,
        [this, saved_context, question, request_params](const Json &created) {
      const auto record = created.at("request");
      if (record.at("id") != request_params.at("request_id") ||
          io::canonical_json(record.at("configuration")) != io::canonical_json(request_params.at("configuration"))) {
        throw std::runtime_error("Saved request does not match its prepared input");
      }
      generation_request_ = record; request_page_.loaded = false;
      exchange_preparing_ = false;
      // Repeating Prepare may retrieve an already completed request. Fetch its
      // actual saved answer; never replace it with a new empty exchange.
      if (io::get_string(record, "status") == "completed") {
        exchange_pending_ = true;
        begin_exchange_read();
      }
      else {
        publish_exchange({{"request", record}, {"context", saved_context},
                          {"question", question}, {"reply", Json::object()}});
      }
    }, false, [this](const std::string &error) { exchange_failed(error); })) {
      exchange_failed("Question saved; request preparation was interrupted. Prepare again to resume.");
    }
  }, false, [this](const std::string &error) { exchange_failed(error); });
  if (accepted) {
    ++exchange_generation_;
    exchange_id_ = id;
    exchange_request_ = exchange_context_ = exchange_question_ = exchange_reply_ = exchange_progress_ = Json::object();
    exchange_error_.clear();
    exchange_preparing_ = true;
    exchange_pending_ = exchange_following_ = false;
    exchange_deadline_ = -1;
    exchange_wake_scheduled = 0;
  }
  return accepted;
}

bool ProjectDiscussion::load_exchange(const std::string &id)
{
  if (!requests_supported() || busy_ || project_.busy() || id.empty()) { return false; }
  if (exchange_id_ == id) { return refresh_exchange(); }
  ++exchange_generation_;
  exchange_id_ = id;
  exchange_request_ = exchange_context_ = exchange_question_ = exchange_reply_ = exchange_progress_ = Json::object();
  exchange_error_.clear();
  exchange_pending_ = true;
  exchange_following_ = false;
  exchange_deadline_ = -1;
  exchange_wake_scheduled = 0;
  begin_exchange_read();
  exchange_changed();
  return true;
}

bool ProjectDiscussion::refresh_exchange()
{
  if (!requests_supported() || busy_ || project_.busy() || exchange_id_.empty()) { return false; }
  ++exchange_generation_;
  exchange_error_.clear();
  exchange_pending_ = true;
  exchange_following_ = false;
  exchange_deadline_ = -1;
  exchange_wake_scheduled = 0;
  begin_exchange_read();
  exchange_changed();
  return true;
}

bool ProjectDiscussion::begin_exchange_read()
{
  if (!requests_supported() || busy_ || project_.busy() || exchange_reading_ || exchange_id_.empty()) { return false; }
  exchange_reading_ = true;
  exchange_pending_ = false;
  const auto generation = exchange_generation_, flight = ++exchange_flight_;
  exchange_read(progress_supported() ? "project.requests.progress" : "project.requests.get",
      {{"request_id", exchange_id_}}, generation, flight,
      [this, generation, flight](const Json &result) {
    auto bundle = std::make_shared<Json>(Json{{"request", result.at("request")},
        {"progress", result.value("progress", Json())}});
    read_exchange_parts(std::move(bundle), generation, flight);
  });
  return true;
}

void ProjectDiscussion::exchange_read(const std::string &method, Json params, const uint64_t generation,
                                     const uint64_t flight, std::function<void(const Json &)> done)
{
  const auto handle = project_.project()->handle;
  params["handle"] = handle;
  const auto epoch = epoch_;
  std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  options.timeout_s = 15;
  store_.bridge()->call(method, params, options).then(
      [this, weak, epoch, handle, generation, flight, done = std::move(done)](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || flight != exchange_flight_ ||
        !project_.project() || project_.project()->handle != handle) { return; }
    if (generation != exchange_generation_) {
      exchange_reading_ = false;
      exchange_changed();
      return;
    }
    if (!result.ok()) { exchange_reading_ = false; exchange_failed(result.error().message); return; }
    try { done(result.value()); }
    catch (const std::exception &error) { exchange_reading_ = false; exchange_failed(error.what()); }
  });
}

void ProjectDiscussion::read_exchange_parts(std::shared_ptr<Json> bundle, const uint64_t generation,
                                          const uint64_t flight)
{
  // Json uses a vector-backed ordered object. Adding cached context/question
  // entries below may reallocate it, so the request must not be a reference.
  const auto record = bundle->at("request");
  if (io::get_string(record, "id") != exchange_id_) { throw std::runtime_error("Unexpected request identity"); }
  const auto fetch = [this, bundle, generation, flight](const std::string &method, Json params,
                                                       const std::string &key, const std::string &result_key) {
    exchange_read(method, std::move(params), generation, flight,
        [this, bundle, generation, flight, key, result_key](const Json &result) {
      (*bundle)[key] = result.at(result_key);
      read_exchange_parts(bundle, generation, flight);
    });
  };
  if (!bundle->contains("context")) {
    if (!exchange_context_.empty() && exchange_context_.at("id") == record.at("context_id")) {
      (*bundle)["context"] = exchange_context_;
    }
    else {
      fetch("project.contexts.get", {{"context_id", record.at("context_id")}}, "context", "context");
      return;
    }
  }
  if (!bundle->contains("question")) {
    if (!exchange_question_.empty() && exchange_question_.at("id") == record.at("message_id")) {
      (*bundle)["question"] = exchange_question_;
    }
    else {
      fetch("project.discussion.get", {{"message_id", record.at("message_id")}}, "question", "message");
      return;
    }
  }
  if (io::get_string(record, "status") == "completed" && !bundle->contains("reply")) {
    const auto id = record.at("result").at("message_id");
    if (!exchange_reply_.empty() && exchange_reply_.at("id") == id) { (*bundle)["reply"] = exchange_reply_; }
    else {
      fetch("project.discussion.get", {{"message_id", id}}, "reply", "message");
      return;
    }
  }
  if (!bundle->contains("reply")) { (*bundle)["reply"] = Json::object(); }
  publish_exchange(*bundle);
}

void ProjectDiscussion::publish_exchange(const Json &bundle)
{
  const auto &record = bundle.at("request"), &context = bundle.at("context");
  const auto &question = bundle.at("question"), &reply = bundle.at("reply");
  const auto progress = bundle.value("progress", Json());
  if (record.at("id") != exchange_id_ || context.at("id") != record.at("context_id") ||
      context.at("project_id") != record.at("project_id") || context.at("source_revision") != record.at("source_revision") ||
      question.at("id") != record.at("message_id") || question.at("context_id") != context.at("id") ||
      question.at("project_id") != record.at("project_id") || question.at("role") != "user" ||
      (io::get_string(record, "status") == "completed" &&
       (reply.empty() || reply.at("id") != record.at("assistant_message_id") ||
        reply.at("id") != record.at("result").at("message_id") || reply.at("context_id") != context.at("id") ||
        reply.at("project_id") != record.at("project_id") || reply.at("role") != "assistant"))) {
    throw std::runtime_error("Saved exchange has inconsistent provenance");
  }
  if (!progress.is_null()) {
    if (!progress.at("sequence").is_number_integer() || progress.at("sequence") < 0 ||
        progress.at("sequence") > std::numeric_limits<int64_t>::max() ||
        !progress.at("text_bytes").is_number_integer() || progress.at("text_bytes") < 0) {
      throw std::runtime_error("Invalid temporary reply counters");
    }
    const auto text = progress.at("text").get<std::string>();
    const auto sequence = progress.at("sequence").get<int64_t>();
    if (record.at("status") != "running" || record.at("cancel_requested") != false ||
        progress.at("executor_id") != record.at("executor_id") || sequence < 0 ||
        text.size() > 65536 || progress.at("text_bytes") != text.size()) {
      throw std::runtime_error("Invalid temporary reply identity or size");
    }
    if (!exchange_progress_.empty() && exchange_request_.at("id") == record.at("id") &&
        exchange_progress_.at("executor_id") == progress.at("executor_id")) {
      const auto previous_sequence = exchange_progress_.at("sequence").get<int64_t>();
      const auto previous_text = exchange_progress_.at("text").get<std::string>();
      if (sequence < previous_sequence || !text.starts_with(previous_text) ||
          (sequence == previous_sequence && text != previous_text)) {
        throw std::runtime_error("Temporary reply moved backwards");
      }
    }
  }
  exchange_request_ = record; exchange_context_ = context;
  exchange_question_ = question; exchange_reply_ = reply;
  exchange_progress_ = progress.is_null() ? Json::object() : progress;
  // Keep visible history labels consistent with the newly read status without
  // changing its selection, pagination or starting another bridge call.
  for (auto &item : request_page_.items) {
    if (item.at("id") == record.at("id")) { item = record; break; }
  }
  exchange_reading_ = exchange_preparing_ = exchange_pending_ = false;
  exchange_error_.clear();
  const auto status = io::get_string(record, "status");
  exchange_following_ = (status == "running" || status == "uncertain") &&
      (exchange_deadline_ < 0 || !exchange_clock_seen_ || exchange_now_ < exchange_deadline_);
  exchange_due_ = exchange_now_ + 1;
  if (!exchange_following_) { exchange_wake_scheduled = 0; }
  exchange_changed();
}

double ProjectDiscussion::pump(const double now_seconds)
{
  const double never = std::numeric_limits<double>::infinity();
  if (!std::isfinite(now_seconds)) { return never; }
  const double previous = exchange_now_;
  exchange_now_ = now_seconds;
  if (!exchange_clock_seen_) {
    exchange_clock_seen_ = true;
    // A headless test may load before its first clock tick, just as a newly
    // visible editor may load before the first scheduled redraw.
    exchange_due_ = now_seconds + std::max(0.0, exchange_due_ - previous);
  }
  if (!requests_supported() || exchange_id_.empty()) { return never; }
  if (exchange_following_ && exchange_deadline_ < 0) { exchange_deadline_ = now_seconds + 90; }
  if (exchange_following_ && now_seconds >= exchange_deadline_) {
    exchange_following_ = false;
    exchange_changed();
  }
  if (exchange_reading_ || exchange_preparing_ || busy_ || project_.busy()) { return never; }
  if (exchange_pending_ || (exchange_following_ && now_seconds >= exchange_due_)) {
    begin_exchange_read();
    return never;  // The response wakes the UI; it will schedule the next read.
  }
  return exchange_following_ ? std::min(exchange_due_, exchange_deadline_) : never;
}

bool ProjectDiscussion::load_origin(const std::string &draft_id, const bool preserve_error)
{
  const bool accepted = call("project.discussion.proposals", {{"draft_id", draft_id}, {"limit", 1}},
      [this, draft_id](const Json &result) {
    const auto &items = result.at("proposals");
    origin_ = items.empty() ? Json::object() : items.front();
    origin_draft_ = draft_id;
  }, preserve_error);
  if (accepted) { origin_draft_ = draft_id; origin_ = Json::object(); }
  return accepted;
}

bool ProjectDiscussion::capture(const std::string &table_id, const std::vector<std::string> &records,
                                const std::vector<std::string> &fields, const std::string &title)
{
  if (!supported() || busy_ || project_.busy()) { return false; }
  auto params = request("context", {{"table_id", table_id}, {"record_ids", records}, {"field_ids", fields},
      {"expected_revision", project_.project()->revision}, {"title", title}}, "context_id");
  return call("project.contexts.capture", std::move(params), [this](const Json &result) {
    context_ = result.at("context");
    contexts_.loaded = false;
  });
}

bool ProjectDiscussion::add_message(const std::string &text)
{
  if (!supported() || busy_ || project_.busy() || context_.empty()) { return false; }
  auto params = request("message", {{"context_id", context_.at("id")}, {"text", text}, {"role", "user"}}, "message_id");
  return call("project.discussion.add", std::move(params), [this](const Json &result) {
    message_ = result.at("message");
    messages_.loaded = false;
  });
}

bool ProjectDiscussion::link_review()
{
  if (!supported() || busy_ || project_.busy() || message_.empty() || project_.saved_review().empty()) { return false; }
  auto params = request("proposal", {{"message_id", message_.at("id")},
                        {"draft_id", project_.saved_review().at("id")}}, "proposal_id");
  return call("project.discussion.link_draft", std::move(params), [this](const Json &result) {
    origin_ = result.at("proposal");
    origin_draft_ = io::get_string(origin_, "draft_id");
    proposals_.loaded = false;
  });
}
}  // namespace stk::app
