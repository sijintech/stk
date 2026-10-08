/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/bridge/client.hh"

#include <map>
#include <optional>
#include <set>

namespace stk::app {
class AppStore;
class ProjectState;

struct ProjectDiscussionPage {
  io::Json items = io::Json::array();
  int64_t offset = 0, next = -1;
  bool loaded = false;
};

/** Whether a request's prompt version asks for a reply converted to a review draft (parameter edits or a sweep). */
bool structured_proposal(const io::Json &prompt_version);

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
  bool progress_supported() const;
  bool edit_proposals_supported() const;
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
  /** The contexts and requests lists show only active entries (the default) or only archived ones once the
   * service archives (format 11; project_archive.hh); one choice per project, shared by every view of them. */
  bool show_archived(const std::string &kind) const { return show_archived_.count(kind) != 0; }
  void set_show_archived(const std::string &kind, bool show);
  /** Views call this every frame: a page read with another archive filter or archived set is read again
   * (archiving never changes the revision); from the start when the filter itself changed. */
  void sync_archive();
  bool load_context(const std::string &id);
  bool load_message(const std::string &id);
  bool load_request(const std::string &id);
  bool cancel_request(const std::string &id);
  bool load_provider();
  /** Provider-reported token counts of this project's completed requests (project.requests.usage,
   * UX package U2); read again after a reply completes. Informational: the provider's console counts. */
  bool usage_supported() const;
  bool usage_loaded() const { return usage_loaded_; }
  const io::Json &usage() const { return usage_; }
  bool load_usage();
  /** Whether the Python service accepts a Token Plan key from the app (ai.credentials.*). */
  bool key_settings_supported() const;
  /** Hand the key to the Python service for its session, or remember it on this computer (a
   * private file in the service's state folder). The key travels only in this request and is not
   * kept here; the reply, errors and logs only say where a key comes from. Never sends to the provider. */
  bool set_key(std::string key, bool remember);
  /** Forget the key set in the app and any remembered key; an environment key is unaffected. */
  bool clear_key();
  bool create_request(const std::string &model);
  bool start_request(const std::string &id);
  bool recover_request(const std::string &id);
  /** Prepare a question against the currently inspected saved context. Never sends. */
  bool prepare_question(const std::string &context_id, const std::string &text, const std::string &model,
                        const std::string &prompt_version = "stk.text/1");
  /** Explicitly compile a completed parameter reply into a saved draft; never applies. */
  bool propose_exchange_edits();
  /** Explicitly re-read the selected request's saved candidate before opening Review. */
  bool read_exchange_edit_proposal(std::function<void(const io::Json &)> done);
  /** Local draft resolution invalidates only the matching saved candidate observation. */
  void draft_changed(const std::string &draft_id);
  /** Read one immutable exchange, independently of the legacy discussion browsing selection. */
  bool load_exchange(const std::string &request_id);
  bool refresh_exchange();
  /** Main-thread, local-only follow-up reads; caller schedules a redraw at the returned time. */
  double pump(double now_seconds);
  const io::Json &exchange_request() const { return exchange_request_; }
  const io::Json &exchange_context() const { return exchange_context_; }
  const io::Json &exchange_question() const { return exchange_question_; }
  const io::Json &exchange_reply() const { return exchange_reply_; }
  const io::Json &exchange_progress() const { return exchange_progress_; }
  const io::Json &exchange_edit_proposal() const { return exchange_edit_proposal_; }
  uint64_t exchange_generation() const { return exchange_generation_; }
  bool exchange_busy() const { return exchange_preparing_ || exchange_reading_ || exchange_pending_; }
  const std::string &exchange_error() const { return exchange_error_; }
  bool following() const { return exchange_following_; }
  double exchange_wake_scheduled = 0;
  bool load_origin(const std::string &draft_id, bool preserve_error = false);
  bool capture(const std::string &table_id, const std::vector<std::string> &records,
               const std::vector<std::string> &fields, const std::string &title,
               std::function<void(bool)> complete = {});
  bool add_message(const std::string &text);
  bool link_review();

 private:
  bool call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done,
            bool preserve_error = false, std::function<void(const std::string &)> failed = {});
  io::Json request(const std::string &kind, io::Json params, const std::string &id_key);
  bool mutate_request(const std::string &method, const std::string &id);
  void exchange_changed();
  void exchange_failed(const std::string &error);
  bool begin_exchange_read();
  void exchange_read(const std::string &method, io::Json params, uint64_t generation, uint64_t flight,
                     std::function<void(const io::Json &)> done);
  void read_exchange_parts(std::shared_ptr<io::Json> bundle, uint64_t generation, uint64_t flight);
  void publish_exchange(const io::Json &bundle);
  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t epoch_ = 0, version_ = 0;
  bool busy_ = false;
  std::string error_, origin_draft_;
  ProjectDiscussionPage contexts_, messages_, proposals_, request_page_;
  std::set<std::string> show_archived_;
  std::map<std::string, std::string> listed_archive_;  // kind -> the archive filter and version its page was read with
  std::optional<bool> archive_filter(const std::string &kind) const;
  std::string archive_key(const std::string &kind) const;
  io::Json context_ = io::Json::object(), message_ = io::Json::object(), origin_ = io::Json::object();
  io::Json requests_ = io::Json::object();
  io::Json generation_request_ = io::Json::object();
  io::Json provider_ = io::Json::object();
  bool provider_loaded_ = false;
  io::Json usage_ = io::Json::object();
  bool usage_loaded_ = false, usage_reading_ = false;
  std::string usage_completed_;  // the completed exchange the shown usage already includes
  bool credentials(const std::string &method, io::Json params);
  io::Json exchange_request_ = io::Json::object(), exchange_context_ = io::Json::object();
  io::Json exchange_question_ = io::Json::object(), exchange_reply_ = io::Json::object();
  io::Json exchange_progress_ = io::Json::object();
  io::Json exchange_edit_proposal_ = io::Json::object();
  std::string exchange_id_, exchange_error_;
  uint64_t exchange_generation_ = 0, exchange_flight_ = 0;
  bool exchange_preparing_ = false, exchange_reading_ = false, exchange_pending_ = false;
  bool exchange_following_ = false, exchange_clock_seen_ = false;
  double exchange_now_ = 0, exchange_due_ = 0, exchange_deadline_ = -1;
};
}  // namespace stk::app
