/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

namespace stk::app {
class AppStore;
class ProjectState;

/** Editor-local analysis document browser. Reads and explicit writes use the project bridge;
 * no operation configures/evaluates a Viewer. Lost write replies keep a stable identity for an
 * explicit read-back, never an automatic replay. Closing/reopening a project fences callbacks. */
class ProjectAnalyses {
 public:
  explicit ProjectAnalyses(AppStore &store);
  ~ProjectAnalyses();
  ProjectAnalyses(const ProjectAnalyses &) = delete;
  ProjectAnalyses &operator=(const ProjectAnalyses &) = delete;

  void sync();
  bool supported() const;
  bool busy() const { return busy_; }
  const std::string &handle() const { return handle_; }
  uint64_t epoch() const { return epoch_; }
  uint64_t version() const { return version_; }
  const std::string &error() const { return error_; }
  const std::string &notice() const { return notice_; }
  const io::Json &page() const { return page_; }
  const io::Json &selected() const { return selected_; }
  int64_t selected_revision() const { return selected_revision_; }
  uint64_t selected_version() const { return selected_version_; }
  bool stale() const;
  bool page_stale() const;
  bool uncertain() const { return uncertain_; }
  std::string pending_id() const;

  bool load_page(int64_t offset = 0);
  bool load(const std::string &id);
  bool save_new(const std::string &name, const io::Json &document);
  /** Replace only the display name of the selected, fully read definition at its read revision. */
  bool rename(const std::string &name);
  /** Replace submitted overrides only, preserving the selected graph, outputs and name. */
  bool replace_parameters(const io::Json &parameters, uint64_t expected_selected_version);
  /** Replace submitted overrides and requested output order in one CAS write, preserving the
   * selected graph, name and identity. Explicit empty outputs remain empty. */
  bool replace_submission(const io::Json &parameters, const io::Json &outputs,
                          uint64_t expected_selected_version);
  /** Observe the existing identity after an ambiguous reply; never sends the mutation again. */
  bool check_pending();

 private:
  void reset();
  void changed();
  bool call(const std::string &method, io::Json params,
            std::function<void(const io::Json &)> done,
            std::function<void(const bridge::Error &)> failed = {});
  bool write(const std::string &method, const std::string &id, const std::string &name,
             const io::Json &document, int64_t revision);
  void accept_read(const io::Json &response, const std::string &id);

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string handle_, session_, error_, notice_;
  uint64_t epoch_ = 0, version_ = 0, selected_version_ = 0;
  bool busy_ = false, uncertain_ = false;
  int64_t selected_revision_ = -1;
  io::Json page_, selected_, pending_;
  std::optional<bridge::Future<io::Json>> future_;
};
}  // namespace stk::app
