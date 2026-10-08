/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace stk::app {
class AppStore;
class ProjectState;

/** What the open project has archived (project.archive.*, project format 11; docs/design/project-archive.md),
 * shared by every list and editor: archived objects are left out of default lists and read-only until
 * restored. Read again after project.archive.changed or an own change; replies of a closed or replaced
 * project opening or bridge are ignored. Archiving never changes the project's revision. */
class ProjectArchive {
 public:
  explicit ProjectArchive(AppStore &store);
  ~ProjectArchive();
  ProjectArchive(const ProjectArchive &) = delete;
  ProjectArchive &operator=(const ProjectArchive &) = delete;

  /** Follow the project opening and read the archive when due (cheap to call every frame). */
  void sync();
  /** The service archives and the project is format 11 or later. */
  bool supported() const;
  bool busy() const { return read_.has_value() || write_.has_value(); }
  bool archived(const std::string &kind, const std::string &id) const;
  int64_t count(const std::string &kind) const;
  /** Changes whenever the archived set does: lists filtered by it read again. */
  uint64_t version() const { return version_; }
  const std::string &error() const { return error_; }
  /** Archive (or restore) objects of one kind; ``include_runs`` also covers a workflow's runs that are not running. */
  bool set(const std::string &kind, const std::vector<std::string> &ids, bool archived, bool include_runs = false);

 private:
  void reset();
  void changed();
  bool read();

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  bridge::ListenerHandle listener_;
  std::string handle_, session_, error_;
  uint64_t epoch_ = 0, version_ = 0;
  bool stale_ = true;
  std::map<std::string, std::set<std::string>> ids_;
  std::optional<bridge::Future<io::Json>> read_, write_;
};
}  // namespace stk::app
