/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * SkillCatalogState: versioned skill browsing and explicit local user-library publication.
 * Shared by every Skills editor through AppStore::skills(), including unconfirmed publication
 * identities. Publication never changes project history or evaluates, prepares or runs a method.
 * Replies are bound to request generation, bridge process and reviewed source identity; a bridge
 * restart clears catalog reads while keeping an unconfirmed publication available for inspection.
 * Main thread only.
 */
#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "stk/bridge/client.hh"
#include "stk/io/json.hh"

namespace stk::bridge {
class Client;
}

namespace stk::app {

class AppStore;
class ProjectSkills;

/** One skills.list row. Texts are {"en", "zh_CN"?} objects; see #skill_text. */
struct SkillSummary {
  std::string id;
  int64_t version = 0;
  std::string ref; /**< "<id>@<version>" */
  std::string content_sha256;
  std::string entry_kind;
  std::string preset;
  std::string source;
  io::Json title;
  io::Json summary;
  std::string status; /**< available | limited | unavailable (another value is shown verbatim) */
  std::vector<std::string> unavailable_outputs;
  size_t issue_count = 0;
};

/** The display text of a localized skill text: the language's entry, else English. */
std::string skill_text(const io::Json &text, const std::string &language);
/** Parses a skills.list result; rows without an id, version or ref are skipped. */
std::vector<SkillSummary> parse_skill_summaries(const io::Json &result);

class SkillCatalogState {
 public:
  static constexpr int kPageSize = 50;
  static constexpr size_t kMaxQuery = 200;

  explicit SkillCatalogState(AppStore &store);
  ~SkillCatalogState();
  SkillCatalogState(const SkillCatalogState &) = delete;
  SkillCatalogState &operator=(const SkillCatalogState &) = delete;

  /** Follows the store's bridge: a new client or restarted bridge clears the catalog. */
  void sync();
  /** The bridge is ready (its hello is known). */
  bool bridge_ready() const;
  /** The ready bridge offers skills.list and skills.get (false for older bridges). */
  bool supported() const;

  /** Loads the first page once per bridge session; false when nothing was sent. */
  bool ensure_loaded();
  /** Explicitly reloads the current page (and the selected detail); false when nothing was sent. */
  bool refresh();
  /** Applies a query from the first page, cut to #kMaxQuery bytes on a UTF-8 boundary; false when nothing was sent. */
  bool search(const std::string &query);
  bool next_page();
  bool previous_page();
  /** Selects a row of the current page by ref and loads its full definition. */
  bool select(const std::string &ref);

  bool loaded() const { return loaded_; }
  bool loading() const { return list_future_.has_value(); }
  bool detail_loading() const { return detail_future_.has_value(); }
  const std::string &error() const { return error_; }
  const std::string &detail_error() const { return detail_error_; }
  const std::string &query() const { return query_; }
  int64_t offset() const { return offset_; }
  int64_t total() const { return total_; }
  bool has_next() const { return next_offset_.has_value(); }
  const std::vector<SkillSummary> &skills() const { return skills_; }
  /** Unusable definitions reported by the bridge (at most 50) and their total count. */
  const io::Json &problems() const { return problems_; }
  int64_t problem_count() const { return problem_count_; }
  const std::string &selected() const { return selected_; }
  /** The selected skill's skills.get document, or null. */
  const io::Json &detail() const { return detail_; }

  /** Explicit local-library publication is independent of project revisions and undo. */
  bool publication_supported() const;
  uint64_t publication_generation() const { return publication_request_; }
  bool publication_busy() const { return publication_future_.has_value(); }
  bool publication_uncertain() const { return !publication_pending_.is_null(); }
  const io::Json &publication_pending() const { return publication_pending_; }
  const io::Json &publication() const { return publication_; }
  const std::string &publication_error() const { return publication_error_; }
  const std::string &publication_notice() const { return publication_notice_; }
  bool publication_conflict(const ProjectSkills &skills) const;
  bool publish(ProjectSkills &skills, const std::string &mode, uint64_t expected_epoch, const std::string &digest);
  bool check_publication();

 private:
  bool load(int64_t offset, std::string query);
  bool load_detail();
  void clear();
  void invalidate();
  bool publication_call(const std::string &method, io::Json params);
  void accept_publication(const io::Json &result);

  AppStore &store_;
  bridge::Client *client_ = nullptr;
  std::string session_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t list_request_ = 0, detail_request_ = 0, publication_request_ = 0;
  bridge::ListenerHandle changed_listener_;
  std::optional<bridge::Future<io::Json>> list_future_, detail_future_;
  bool loaded_ = false, requested_ = false, dirty_ = false;
  std::string error_, detail_error_, query_, selected_, selected_id_, selected_digest_, selected_source_;
  int64_t selected_version_ = 0;
  int64_t offset_ = 0, total_ = 0, problem_count_ = 0;
  std::optional<int64_t> next_offset_;
  std::vector<SkillSummary> skills_;
  io::Json problems_ = io::Json::array();
  io::Json detail_;
  std::optional<bridge::Future<io::Json>> publication_future_;
  io::Json publication_pending_, publication_, publication_conflict_;
  std::string publication_error_, publication_notice_;
};

}  // namespace stk::app
