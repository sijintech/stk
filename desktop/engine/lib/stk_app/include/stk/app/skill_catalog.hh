/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * SkillCatalogState: read-only browsing of the bridge's versioned skill catalog (skills.list and
 * skills.get, bridge spec §16, experimental stk.skill/1). Shared by every Skills editor through
 * AppStore::skills(). It only reads: it never evaluates an entry, prepares a run, touches a
 * project or calls a model. Replies are applied only to the request generation, bridge client and
 * bridge process that sent them; a bridge restart or replacement clears the catalog.
 * Main thread only.
 */
#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "stk/bridge/future.hh"
#include "stk/io/json.hh"

namespace stk::bridge {
class Client;
}

namespace stk::app {

class AppStore;

/** One skills.list row. Texts are {"en", "zh_CN"?} objects; see #skill_text. */
struct SkillSummary {
  std::string id;
  int64_t version = 0;
  std::string ref; /**< "<id>@<version>" */
  std::string content_sha256;
  std::string entry_kind;
  std::string preset;
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

 private:
  bool load(int64_t offset, std::string query);
  bool load_detail();
  void clear();

  AppStore &store_;
  bridge::Client *client_ = nullptr;
  std::string session_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t list_request_ = 0, detail_request_ = 0;
  std::optional<bridge::Future<io::Json>> list_future_, detail_future_;
  bool loaded_ = false, requested_ = false;
  std::string error_, detail_error_, query_, selected_, selected_id_;
  int64_t selected_version_ = 0;
  int64_t offset_ = 0, total_ = 0, problem_count_ = 0;
  std::optional<int64_t> next_offset_;
  std::vector<SkillSummary> skills_;
  io::Json problems_ = io::Json::array();
  io::Json detail_;
};

}  // namespace stk::app
