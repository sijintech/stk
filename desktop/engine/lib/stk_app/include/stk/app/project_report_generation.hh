/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/bridge/client.hh"
#include <memory>
#include <optional>

namespace stk::app {
class AppStore;
/** Editor-local report composer. Neither construction, sync nor workspace restoration
 * sends, prepares a request, reads an asset or starts an executor. */
class ProjectReportGeneration {
 public:
  struct Token { uint64_t epoch = 0, edit = 0; };
  struct Created { std::string project_id, report_id, source_sha256; };
  explicit ProjectReportGeneration(AppStore &store);
  ~ProjectReportGeneration();
  ProjectReportGeneration(const ProjectReportGeneration &) = delete;
  ProjectReportGeneration &operator=(const ProjectReportGeneration &) = delete;
  void sync();
  bool supported() const;
  bool busy() const;
  bool dirty() const;
  bool pending() const;
  Token token();
  uint64_t version() const;
  const std::string &error() const;
  const io::Json &draft() const;
  const io::Json &request() const;
  const io::Json &frozen_input() const;
  const io::Json &response() const;
  /** The shared input picker supplies full reviewed metadata, never asset bodies.
   * selection is the exact backend five-field report_selection. Inputs are pinned
   * to the current project revision. Updating input after preparation needs discard. */
  bool set_input(Token, const io::Json &context, std::string question,
                 const io::Json &configuration, const io::Json &selection,
                 const io::Json &reviewed_sources, const io::Json &asset_descriptors,
                 const io::Json &snapshot_sha256);
  /** name, entry_path, question or body. Body is independent of the original reply.
   * Retained controls must pass the token from the frame that installed their binding. */
  bool edit(Token, const std::string &field, std::string value);
  bool prepare(Token); // Saves message and request only. Explicitly continues message_saved.
  bool start(Token);   // At most one attempt for this local saved request identity.
  bool cancel(Token);
  bool recover(Token); // Explicit backend recovery; never a new model send.
  bool refresh(Token); // Read original generation_request only.
  bool check_pending(Token); // Read-only message/request/report identity lookup; no replays.
  bool open_saved_request(Token, const std::string &request_id);
  bool create_report(Token); // CAS create_generated, then verify saved report by original UUID.
  /** Read-only following after an explicit action, bounded to 90 seconds. Caller owns
   * a UI timer. Returns next due monotonic time, or -1; never sends/cancels/recovers. */
  double pump(double now);
  /** UI explanation only; backend atomically rechecks all current labels at send. */
  std::string send_blocked();
  bool discard(Token, bool acknowledge_pending = false);
  std::optional<Created> take_created();
  nlohmann::json save_workspace_state() const;
  static bool valid_workspace_state(const nlohmann::json &);
  bool load_workspace_state(const nlohmann::json &);
 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};
} // namespace stk::app
