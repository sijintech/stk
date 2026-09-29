/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_discussion.hh"
#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"

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
                            std::function<void(const Json &)> done, const bool preserve_error)
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
      [this, weak, epoch, handle, done = std::move(done)](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || !project_.project() || project_.project()->handle != handle) { return; }
    busy_ = false;
    if (!result.ok()) {
      error_ = result.error().message;
      store_.log(error_);
      // An external writer can advance the project without a bridge event.
      project_.refresh();
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &exc) { error_ = exc.what(); }
    }
    ++version_;
    store_.changed();
  });
  store_.changed();
  return true;
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
  return call("project.requests.cancel", {{"request_id", id}}, [this](const Json &result) {
    generation_request_ = result.at("request");
    request_page_.loaded = false;
  });
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
