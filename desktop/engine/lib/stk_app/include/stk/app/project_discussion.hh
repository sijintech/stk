/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/bridge/client.hh"

namespace stk::app {
class AppStore;
class ProjectState;

struct ProjectDiscussionPage {
  io::Json items = io::Json::array();
  int64_t offset = 0, next = -1;
  bool loaded = false;
};

/** Saved project discussion and explicitly started text requests. Never applies commands/tasks.
 * Requests are never replayed after a bridge restart; results are tied to the opening handle. */
class ProjectDiscussion {
 public:
  ProjectDiscussion(AppStore &store, ProjectState &project) : store_(store), project_(project) {}
  ~ProjectDiscussion() { alive_.reset(); }
  void reset();
  bool supported() const;
  bool requests_supported() const;
  bool generation_supported() const;
  bool provider_loaded() const { return provider_loaded_; }
  const io::Json &provider() const { return provider_; }
  bool busy() const { return busy_; }
  uint64_t version() const { return version_; }
  const std::string &error() const { return error_; }
  const ProjectDiscussionPage &page(const std::string &kind) const;
  const io::Json &context() const { return context_; }
  const io::Json &message() const { return message_; }
  const io::Json &origin() const { return origin_; }
  const io::Json &generation_request() const { return generation_request_; }
  const std::string &origin_draft() const { return origin_draft_; }
  bool load_page(const std::string &kind, int64_t offset = 0, bool preserve_error = false);
  bool load_context(const std::string &id);
  bool load_message(const std::string &id);
  bool load_request(const std::string &id);
  bool cancel_request(const std::string &id);
  bool load_provider();
  bool create_request(const std::string &model);
  bool start_request(const std::string &id);
  bool recover_request(const std::string &id);
  bool load_origin(const std::string &draft_id, bool preserve_error = false);
  bool capture(const std::string &table_id, const std::vector<std::string> &records,
               const std::vector<std::string> &fields, const std::string &title);
  bool add_message(const std::string &text);
  bool link_review();

 private:
  bool call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done,
            bool preserve_error = false);
  io::Json request(const std::string &kind, io::Json params, const std::string &id_key);
  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t epoch_ = 0, version_ = 0;
  bool busy_ = false;
  std::string error_, origin_draft_;
  ProjectDiscussionPage contexts_, messages_, proposals_, request_page_;
  io::Json context_ = io::Json::object(), message_ = io::Json::object(), origin_ = io::Json::object();
  io::Json requests_ = io::Json::object();
  io::Json generation_request_ = io::Json::object();
  io::Json provider_ = io::Json::object();
  bool provider_loaded_ = false;
};
}  // namespace stk::app
