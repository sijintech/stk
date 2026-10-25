/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

namespace stk::app {
class AppStore;
class ProjectState;

/** Editor-local saved skill browser. Explicit CAS writes never execute an analysis; ambiguous
 * replies retain the existing object identity for a read-only check, never automatic replay. */
class ProjectSkills {
 public:
  explicit ProjectSkills(AppStore &store);
  ~ProjectSkills();
  void sync();
  bool supported() const;
  bool can_publish() const;
  bool busy() const { return busy_; }
  bool uncertain() const { return !pending_.is_null(); }
  uint64_t epoch() const { return epoch_; }
  int64_t revision() const;
  const io::Json &page() const { return page_; }
  const io::Json &selected() const { return selected_; }
  const std::string &error() const { return error_; }
  const std::string &notice() const { return notice_; }
  const std::string &selected_id() const { return selected_id_; }
  const std::string &analysis_id() const { return analysis_id_; }
  bool current() const;
  void ensure_loaded();
  bool refresh();
  bool load_page(int64_t offset = 0);
  bool select(const std::string &id);
  bool write(const std::string &action, io::Json params, uint64_t expected_epoch);
  bool check_pending();
  static std::string new_id();

 private:
  void changed();
  bool call(const std::string &method, io::Json params,
            std::function<void(const io::Json &)> done,
            std::function<void(const bridge::Error &)> failed = {});
  bool load_selected();
  void accept_read(const io::Json &response, const std::string &id);
  void log_pending();
  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string handle_, session_, selected_id_, analysis_id_, error_, notice_;
  uint64_t epoch_ = 0;
  int64_t page_attempt_ = -1, selected_attempt_ = -1, selected_revision_ = -1;
  bool busy_ = false;
  io::Json page_, selected_, pending_;
  std::optional<bridge::Future<io::Json>> future_;
};
}  // namespace stk::app
