/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_parameter_draft.hh"
#include "stk/bridge/client.hh"
#include "stk/core/utf8.hh"

namespace stk::app {
class AppStore;
class ProjectState;

/** Editor-local browser and explicit writer of project workflows (project.workflows.*).
 * Selecting a workflow reads it and then validates the document read, so the step summaries
 * (referenced names, ports) always describe the shown document. Writes are explicit CAS saves;
 * a lost write reply marks the state uncertain until the workflow is read again (never replayed).
 * Candidate checks of an unsaved document have their own slot and never block reads. Nothing here
 * runs or prepares anything. Closing/reopening a project or replacing the bridge fences callbacks. */
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
  /** The bridge process this state talks to ("pid:spawn"), part of candidate check keys. */
  const std::string &session() const { return session_; }
  /** A write was sent and its reply was lost: read the workflow again before saving. */
  bool uncertain() const { return uncertain_; }
  /** Saved/created/not-found notices as catalog keys (empty when none). */
  const std::string &notice() const { return notice_; }
  /** The latest project.workflows.choices reply (null until read). */
  const io::Json &choices() const { return choices_; }

  /** Archive filters sent with later list reads: false lists only active objects, true only archived ones,
   * nullopt everything (projects before format 11; see project_archive.hh). */
  void set_archive_filters(std::optional<bool> workflows, std::optional<bool> runs) { list_archived_ = workflows; runs_archived_ = runs; }
  bool load_page(int64_t offset = 0);
  /** Read one workflow, then validate the document read. */
  bool load(const std::string &id);
  /** Read (and check) the selected workflow again, or the current page when none is selected. */
  bool reload();
  /** Check the shown workflow when it has no check yet (after a read or a save); false when not needed or busy. */
  bool validate_selected();
  bool load_choices();
  /** Forget the shown workflow (for example after deleting it) without a read. */
  void clear_selection();
  /** Save a new workflow under a fresh UUID at the current revision, then select it. */
  bool create(const std::string &name, const io::Json &document);
  /** Replace the selected workflow's name and document at the revision it was read at, then read it again. */
  bool update(const std::string &name, const io::Json &document, uint64_t expected_selected_version);
  /** Validate an unsaved candidate; the reply counts only for `key` (see AnalysisCandidateKey). */
  bool check(const io::Json &document, AnalysisCandidateKey key);
  const AnalysisCandidateValidation &candidate() const { return candidate_; }

  /* ---- Per-row runs (project format 10, project.workflow_runs.*) ---- */

  /** Whether the bridge offers workflow runs and the project is at format 10. */
  bool runs_supported() const;
  /** The selected workflow's runs, newest first (null until read). */
  const io::Json &runs() const { return runs_; }
  /** The shown run with its tasks (null until read). */
  const io::Json &run() const { return run_; }
  uint64_t run_version() const { return run_version_; }
  bool load_runs();
  bool load_run(const std::string &run_id);
  /** Freeze a run of the selected (saved, valid) workflow over these rows, then start it. Explicit; returns at once. */
  bool run_rows(const std::vector<std::string> &rows, io::Json simulation = nullptr);
  /** Start the shown run again (retries tasks that did not succeed), cancel it, or recover it after a restart. */
  bool start_run();
  bool cancel_run();
  bool recover_run();
  /** Which rows of the shown run no longer match the current definitions (null until read; read-only). */
  const io::Json &run_staleness() const { return stale_; }
  bool load_run_staleness();

  /** Explicit read-only compilation inspection. Separate from save/run requests;
   * reopening a workspace never calls these methods. Older attempts remain readable. */
  bool compilations_supported() const;
  bool load_compilation(const std::string &step, const std::string &row, int64_t attempt);
  bool load_compilation_log(const std::string &stream, int64_t offset = 0);
  bool read_compilation_source(size_t diagnostic, std::function<void(const io::Json &)> done);
  void clear_compilation();
  bool compilation_busy() const { return compilation_busy_; }
  const io::Json &compilation() const { return compilation_; }
  const io::Json &compilation_log() const { return compilation_log_; }
  const std::string &compilation_text() const { return compilation_text_; }
  const std::string &compilation_error() const { return compilation_error_; }

 private:
  void reset();
  void changed();
  bool call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done,
            std::function<void(const bridge::Error &)> failed = {});
  bool write(const std::string &method, const std::string &id, const std::string &name, const io::Json &document,
             int64_t revision);
  bool run_call(const std::string &method, io::Json params);
  void accept_run(const io::Json &result);
  bool compilation_call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done);

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string handle_, session_, error_, notice_;
  uint64_t epoch_ = 0, version_ = 0, selected_version_ = 0;
  bool busy_ = false, uncertain_ = false;
  int64_t selected_revision_ = -1;
  io::Json page_, selected_, validation_, choices_, runs_, run_, stale_;
  uint64_t run_version_ = 0;
  std::optional<bool> list_archived_, runs_archived_;
  std::optional<bridge::Future<io::Json>> future_, check_future_;
  AnalysisCandidateValidation candidate_;
  io::Json compilation_key_, compilation_, compilation_log_;
  std::string compilation_text_, compilation_error_;
  core::utf8::StreamDecoder compilation_decoder_;
  bool compilation_busy_ = false;
  uint64_t compilation_generation_ = 0;
  std::optional<bridge::Future<io::Json>> compilation_future_;
};
}  // namespace stk::app
