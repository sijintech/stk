/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_document.hh"

#include <cstddef>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>

namespace stk::app {

/** Detached editor-local edits to one saved analysis's submitted parameters. No I/O, evaluation,
 * implicit defaults, rebasing or live-project observation occurs here. Call current() against the
 * live opening handle/revision before editing or saving. Backend structural validation remains
 * authoritative; pin() accepts an already-read document and checks its shape and storage bounds. */
class AnalysisParameterDraft {
 public:
  static constexpr size_t max_overrides = AnalysisDocumentLimits::max_overrides;
  static constexpr size_t max_parameters_bytes = AnalysisDocumentLimits::max_parameters_bytes;
  static constexpr size_t max_graph_bytes = AnalysisDocumentLimits::max_graph_bytes;
  static constexpr size_t max_document_bytes = AnalysisDocumentLimits::max_document_bytes;
  // Typed editing text may exceed canonical parameter bytes (for example many -0.0 values).
  static constexpr size_t max_text_bytes = max_document_bytes;
  static constexpr size_t max_depth = AnalysisDocumentLimits::max_depth;

  enum class TextMode { Json, LiteralString };
  struct EditResult {
    bool accepted = false;
    std::string error;
  };

  /** Explicit baseline replacement. Invalid identity, shape or bounds throws invalid_argument
   * before changing the existing draft. Re-pinning the same baseline also fences old callbacks. */
  void pin(std::string handle, std::string analysis_id, int64_t revision,
           std::string name, const io::Json &document);
  void reset();
  bool pinned() const { return !handle_.empty(); }
  bool current(const std::string &handle, int64_t revision) const;
  const std::string &handle() const { return handle_; }
  const std::string &analysis_id() const { return analysis_id_; }
  int64_t revision() const { return revision_; }
  const std::string &name() const { return name_; }
  const io::Json &baseline_document() const { return baseline_; }

  /** Generation changes only on pin/reset; version additionally changes on an actual edit.
   * A text editor may submit multiple edits against the same generation before being rebuilt. */
  uint64_t generation() const { return generation_; }
  uint64_t version() const { return version_; }
  bool dirty() const { return !edits_.empty(); }

  bool has_override(const std::string &name) const;
  /** Disengaged means no override; an engaged JSON null is an explicit submitted null. */
  std::optional<io::Json> override_value(const std::string &name) const;
  /** Detached copies. An unpinned draft returns an empty parameters object/null document. */
  io::Json parameters() const;
  io::Json candidate_document() const;

  /** Valid no-ops are accepted without changing version. Rejected edits preserve all state.
   * Keys are exact UTF-8 strings, including empty/unknown keys admitted by existing storage. */
  EditResult set(const std::string &name, const io::Json &value, uint64_t expected_generation);
  /** JSON mode rejects duplicate keys, trailing data, nonfinite/overflowed numbers and invalid
   * UTF-8. LiteralString stores exact text, so empty text and text "null" remain strings. */
  EditResult set_text(const std::string &name, std::string_view text, TextMode mode,
                      uint64_t expected_generation);
  EditResult remove(const std::string &name, uint64_t expected_generation);
  bool revert(uint64_t expected_generation);

  /** Current-state observation only, never a transaction receipt or automatic adoption.
   * Typed equality distinguishes integer/float and signed zero, ignoring object key order. */
  bool matches(const std::string &analysis_id, const std::string &name,
               const io::Json &document) const;

 private:
  bool accepts(uint64_t generation) const;
  io::Json document_with(const io::Json &parameters) const;
  std::string handle_, analysis_id_, name_;
  int64_t revision_ = -1;
  uint64_t generation_ = 0, version_ = 0;
  io::Json baseline_;
  // Disengaged optional removes a key; engaged JSON null is an explicit override.
  std::map<std::string, std::optional<io::Json>> edits_;
};

}  // namespace stk::app
