/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

namespace stk::app {
class AppStore;
class ProjectState;

/** Editor-local, read-only browser of project workflows (project.workflows.list/get/validate).
 * Selecting a workflow reads it and then validates the document read, so the step summaries
 * (referenced names, ports) always describe the shown document. Nothing here writes, runs or
 * prepares anything. Closing/reopening a project or replacing the bridge fences callbacks. */
class ProjectWorkflows {
 public:
  explicit ProjectWorkflows(AppStore &store);
  ~ProjectWorkflows();
  ProjectWorkflows(const ProjectWorkflows &) = delete;
  ProjectWorkflows &operator=(const ProjectWorkflows &) = delete;

  void sync();
  bool supported() const;
  bool busy() const { return busy_; }
  const std::string &handle() const { return handle_; }
  uint64_t epoch() const { return epoch_; }
  uint64_t version() const { return version_; }
  const std::string &error() const { return error_; }
  const io::Json &page() const { return page_; }
  /** The read workflow summary + document (null until read). */
  const io::Json &selected() const { return selected_; }
  int64_t selected_revision() const { return selected_revision_; }
  /** The validation reply for selected()'s document at selected_revision() (null until checked). */
  const io::Json &validation() const { return validation_; }
  /** Changes whenever selected() or validation() changes. */
  uint64_t selected_version() const { return selected_version_; }
  /** The project changed after the selected workflow was read and checked. */
  bool stale() const;
  bool page_stale() const;

  bool load_page(int64_t offset = 0);
  /** Read one workflow, then validate the document read. */
  bool load(const std::string &id);
  /** Read (and check) the selected workflow again, or the current page when none is selected. */
  bool reload();

 private:
  void reset();
  void changed();
  bool call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done);

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string handle_, session_, error_;
  uint64_t epoch_ = 0, version_ = 0, selected_version_ = 0;
  bool busy_ = false;
  int64_t selected_revision_ = -1;
  io::Json page_, selected_, validation_;
  std::optional<bridge::Future<io::Json>> future_;
};
}  // namespace stk::app
