/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"
#include "stk/app/analysis_input_reuse.hh"

namespace stk::io { class Payload; }
namespace stk::app {
class AppStore;
class ProjectState;

/** Editor-local observer of durable, explicitly prepared analysis runs. Construction, sync,
 * project changes and reopening never execute or recover work. Bounded polling only reads
 * an identity the user has selected. No operation configures the shared Viewer. */
class ProjectAnalysisRuns {
 public:
  explicit ProjectAnalysisRuns(AppStore &store);
  ~ProjectAnalysisRuns();
  void sync();
  bool supported() const;
  bool reusable_inputs_supported() const;
  bool busy() const { return busy_; }
  bool uncertain() const { return uncertain_; }
  bool following() const { return following_; }
  const std::string &handle() const { return handle_; }
  uint64_t epoch() const { return epoch_; }
  uint64_t version() const { return version_; }
  uint64_t selection_generation() const { return selection_generation_; }
  const std::string &error() const { return error_; }
  const std::string &pending_id() const { return pending_id_; }
  const io::Json &page() const { return page_; }
  int64_t offset() const { return offset_; }
  const io::Json &run() const { return run_; }
  const io::Json &snapshots() const { return snapshots_; }
  size_t omitted_snapshots() const { return omitted_snapshots_; }
  const io::Json &result() const { return result_; }
  const std::optional<AnalysisReusedInputs> &reusable_inputs() const { return reusable_inputs_; }
  uint64_t reusable_inputs_generation() const { return reusable_inputs_generation_; }
  std::vector<std::string> payload_outputs() const;

  bool load_snapshots();
  bool load_page(int64_t offset = 0);
  bool load(const std::string &run_id);
  bool prepare(const std::string &analysis_id, int64_t expected_revision,
               const std::string &snapshot_id, const io::Json &bindings);
  bool start();
  bool cancel();
  bool recover();
  bool check_pending();
  bool read_result();
  /** Read exact snapshot metadata for the selected frozen run. Never copies file bytes or
   * prepares/starts a run. Published staging is independent of the editor's local input form. */
  bool read_reusable_inputs();
  /** Decode only an explicitly selected output from the previously verified archive. Payload
   * decoding verifies its referenced bytes again; failures never change the current Viewer. */
  std::shared_ptr<const io::Payload> decode_payload(const std::string &output);
  /** Returns next monotonic wake time, or infinity. Reads stop after 90 seconds, a terminal
   * status, an error, or a session change. Another explicit load/start resumes observation. */
  double pump(double now_seconds);
  double wake_scheduled = 0;

 private:
  void reset();
  void changed();
  void accept_run(const io::Json &value, const std::string &run_id);
  bool call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done,
            std::function<void(const bridge::Error &)> failed = {});
  bool command(const std::string &name);
  bool read(const std::string &id, bool follow);
  void follow();
  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string handle_, session_, error_, pending_id_, blob_dir_;
  uint64_t epoch_ = 0, version_ = 0, selection_generation_ = 0;
  uint64_t reusable_inputs_generation_ = 0;
  std::optional<AnalysisReusedInputs> reusable_inputs_;
  bool busy_ = false, uncertain_ = false, following_ = false, clock_seen_ = false;
  double now_ = 0, due_ = 0, deadline_ = -1;
  int64_t offset_ = 0;
  size_t omitted_snapshots_ = 0;
  io::Json page_, run_, result_, snapshots_ = io::Json::array();
  std::optional<bridge::Future<io::Json>> future_;
};
}  // namespace stk::app
