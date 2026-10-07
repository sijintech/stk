/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/json.hh"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace stk::app {

/** The stk.workflow/1 bounds storage enforces (suan/project/workflows.py). */
struct WorkflowDocumentLimits {
  static constexpr size_t max_steps = 200, max_document_bytes = 256 * 1024, max_parameters_bytes = 64 * 1024;
  static constexpr size_t max_inputs = 32, max_parameters = 64, max_after = 64, max_ref_entries = 8;
};

/** A lowercase identifier ("^[a-z][a-z0-9_]{0,63}$"): step ids, kinds, ports and parameter names. */
bool workflow_identifier(std::string_view value);

/** Throws invalid_argument unless `document` has the stk.workflow/1 shape storage accepts: exactly
 * format/steps/ui, identifier ids and keys, `x-` step keys, {"from": "step.port"} inputs, bounded
 * ref/label/parameters/after, finite positions within 1e6, and the byte limits. References and
 * links are not resolved here (that is project.workflows.validate). */
void check_workflow_document(const io::Json &document);

/** Detached editor-local edits to one saved workflow: its name and a candidate copy of its
 * document, made at the first edit. Keys an edit does not touch keep their exact JSON, and an edit
 * that returns the document to the saved one drops the copy. Edits address steps by id and refuse
 * ids that occur more than once. Removing a step also removes links from it, `after` entries
 * naming it and its position. No I/O happens here; saving and checking belong to the caller.
 * Every accepted document passes check_workflow_document, so storage accepts what is saved. */
class WorkflowDraft {
 public:
  struct EditResult {
    bool accepted = false;
    std::string error;
    /** add_step: the id given to the new step. */
    std::string id;
  };

  /** Explicit baseline replacement; an invalid identity, name or document throws invalid_argument
   * before anything changes. Re-pinning the same baseline also fences old callbacks. */
  void pin(std::string handle, std::string workflow_id, int64_t revision, std::string name, const io::Json &document);
  void reset();
  bool pinned() const { return !handle_.empty(); }
  bool current(const std::string &handle, int64_t revision) const;
  const std::string &handle() const { return handle_; }
  const std::string &workflow_id() const { return workflow_id_; }
  int64_t revision() const { return revision_; }
  const io::Json &baseline() const { return baseline_; }
  const std::string &baseline_name() const { return baseline_name_; }

  /** Generation changes only on pin/reset; version on every accepted change; check_version only on
   * changes a project.workflows.validate result could depend on (not positions or the name). */
  uint64_t generation() const { return generation_; }
  uint64_t version() const { return version_; }
  uint64_t check_version() const { return check_version_; }
  bool dirty() const { return document_.has_value() || name_.has_value(); }

  /** The candidate document (the saved one while it has no edits) and name. */
  const io::Json &document() const;
  const std::string &name() const;
  /** Steps that are new or differ from the saved document (anything but their position). */
  std::set<std::string> edited_steps() const;
  /** The step object of a unique id in the candidate, else null. */
  const io::Json *step(const std::string &id) const;

  /** Valid no-ops are accepted without changing version; rejected edits keep all state. */
  EditResult set_name(const std::string &name, uint64_t generation);
  /** Append a step {"id", "kind", "ref": {ref_key: ref_value}} at an optional position. Its id
   * derives from the kind and never collides: analysis, analysis_2, ... */
  EditResult add_step(const std::string &kind, const std::string &ref_key, const std::string &ref_value,
                      std::optional<std::pair<double, double>> position, uint64_t generation);
  EditResult remove_step(const std::string &step, uint64_t generation);
  /** Link (engaged "step.port") or unlink (nullopt) one input; the source step must exist once and
   * differ from this one. Port types and cycles are left to validation. */
  EditResult set_link(const std::string &step, const std::string &port, const std::optional<std::string> &source,
                      uint64_t generation);
  /** Replace the steps that must finish first (distinct, existing, not this one); empty removes them. */
  EditResult set_after(const std::string &step, const std::vector<std::string> &steps, uint64_t generation);
  /** Set (engaged) or remove (nullopt) one parameter; {"$field": UUID} is an ordinary value here. */
  EditResult set_parameter(const std::string &step, const std::string &name, const std::optional<io::Json> &value,
                           uint64_t generation);
  /** Set or remove (nullopt or empty) a step's display label. */
  EditResult set_label(const std::string &step, const std::optional<std::string> &label, uint64_t generation);
  /** Write ui.positions for unique steps (finite, |value| <= 1e6, rounded to whole units). */
  EditResult move_steps(const std::map<std::string, std::pair<double, double>> &positions, uint64_t generation);

  /** Keep the edits on a newer read of the same workflow: allowed only when that read's name and
   * document equal this draft's saved baseline (other project edits moved the revision, nobody
   * changed this workflow). The candidate check is invalidated because its key names the revision. */
  bool rebase(int64_t revision, const std::string &name, const io::Json &document);
  /** Discard every accepted edit. */
  bool revert(uint64_t expected_generation);
  /** Current-state observation: whether this saved workflow is exactly the candidate. */
  bool matches(const std::string &workflow_id, const std::string &name, const io::Json &document) const;

 private:
  bool accepts(uint64_t generation) const { return pinned() && generation == generation_; }
  /** Applies `change` to a copy of the candidate, tidies keys emptied that the saved step lacked,
   * checks the shape and commits only an actual difference. */
  EditResult edit(uint64_t generation, bool affects_check, const std::function<std::string(io::Json &)> &change);

  std::string handle_, workflow_id_, baseline_name_;
  int64_t revision_ = -1;
  uint64_t generation_ = 0, version_ = 0, check_version_ = 0;
  io::Json baseline_;
  std::optional<io::Json> document_;
  std::optional<std::string> name_;
};

}  // namespace stk::app
