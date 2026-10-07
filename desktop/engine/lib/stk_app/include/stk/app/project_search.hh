/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

#include <optional>
#include <string>

namespace stk::app {
class AppStore;
class ProjectState;

/** One explicit search of the open project's names and text (project.search, UX package U3):
 * tables, fields and text cells, workflows, analyses, files, AI drafts and messages. Started by the
 * person, never while typing; results of a closed or replaced project, opening or bridge are
 * dropped. Searching reads only. */
class ProjectSearch {
 public:
  explicit ProjectSearch(AppStore &store);
  ~ProjectSearch();
  ProjectSearch(const ProjectSearch &) = delete;
  ProjectSearch &operator=(const ProjectSearch &) = delete;

  /** Follow the project opening (cheap to call every frame). */
  void sync();
  bool supported() const;
  bool busy() const { return future_.has_value(); }
  /** Search for `query` (trimmed, 1-200 characters); a search in flight is replaced. */
  bool search(const std::string &query);
  /** {revision, query, results, counts, truncated} of the last search, or null. */
  const io::Json &result() const { return result_; }
  const std::string &error() const { return error_; }
  uint64_t version() const { return version_; }
  void clear();

 private:
  void changed();

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string handle_, session_, error_;
  uint64_t epoch_ = 0, version_ = 0;
  io::Json result_;
  std::optional<bridge::Future<io::Json>> future_;
};
}  // namespace stk::app
