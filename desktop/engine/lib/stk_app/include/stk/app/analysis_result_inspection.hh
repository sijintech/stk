/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include <cstddef>
#include <memory>
#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace stk::app {
// Typed components: object key "0" differs from array index0. Rows carry only one
// component, avoiding64 copies of an unusually long ancestor key per page.
using AnalysisJsonComponent = std::variant<std::string, size_t>;
using AnalysisJsonPath = std::vector<AnalysisJsonComponent>;
enum class AnalysisJsonType { Null, Boolean, Integer, UnsignedInteger, Float, String, Array, Object };
struct AnalysisJsonDescription {
  AnalysisJsonType type = AnalysisJsonType::Null;
  std::string preview;                 // <=240 UTF-8 bytes, JSON strings quoted/escaped
  bool preview_truncated = false;      // containers use counts, not recursive dumps
  size_t child_count = 0;              // object members/array items, zero for primitives
};
struct AnalysisJsonProperty {
  AnalysisJsonComponent component;     // exact key/index, never abbreviated identity
  std::string label;                   // bounded escaped display of key/index
  bool label_truncated = false;
  AnalysisJsonDescription value;
};
struct AnalysisJsonPropertyPage {
  AnalysisJsonDescription value;
  std::vector<AnalysisJsonProperty> rows;
  size_t offset = 0, total = 0;
  std::optional<size_t> next_offset;
};
// Construct explicitly once per selected scalar/path; UI holds it across frames.
// Concatenation reproduces exact JSON encoding (scalar) or RFC6901 pointer (path).
// Each chunk<=4096 bytes, complete UTF-8 codepoints; scalar chunks also never cut
// JSON escapes. Chunks need not each be valid JSON. Empty pointer has1 empty page.
struct AnalysisJsonText {
  std::vector<std::string> pages;
  size_t total_bytes = 0;
};
struct AnalysisResultOutput {
  std::string name;                    // exact requested name, original order
  bool delivered = false;              // key presence; null remains delivered
  std::string delivery_type;           // seven recognized types, empty if unknown
  bool content_not_loaded = false;     // blob table/value, or image/plot/file
  bool metadata_only = false;          // dataset descriptor, not loaded data
  AnalysisJsonPath path;               // {"outputs", name}; missing not navigable
};
struct AnalysisResultIssues {
  bool present = false;
  AnalysisJsonPath path;               // {"errors"} or {"warnings"}, raw values retained
  AnalysisJsonDescription value;
};
class AnalysisResultInspection {
 public:
  static constexpr size_t max_result_bytes = 4 * 1024 * 1024;
  static constexpr size_t max_depth = 64, page_size = 64, preview_bytes = 240;
  static constexpr size_t scalar_page_bytes = 4096;
  // Throws invalid_argument. Iterative preflight BEFORE copying/recursive encoding:
  // depth<=64(root0, keys depth+1), plain finite UTF-8 JSON, exact Python compact
  // UTF-8 encoding<=4MiB counting delimiters/escapes and preserving1.0/-0.0.
  // Schedule/item bounds precede traversal allocations. No canonical_json.
  // Requested: distinct graph IDs<=256, [] valid; schema tag + outputs object required;
  // delivered keys subset of requested. Full output/receipt validation stays backend.
  // Malformed/unknown delivery metadata stays inspectable rather than coerced.
  static std::shared_ptr<const AnalysisResultInspection> from_result(
      const io::Json &requested_outputs, const io::Json &archived_result);
  const io::Json &result() const { return result_; } // single detached immutable document
  size_t encoded_bytes() const { return encoded_bytes_; }
  const std::string &encoded_sha256() const { return encoded_sha256_; }
  const std::vector<AnalysisResultOutput> &outputs() const { return outputs_; }
  const AnalysisResultIssues &errors() const { return errors_; }
  const AnalysisResultIssues &warnings() const { return warnings_; }
  // Public paths preflight<=64 components, UTF-8 key bytes total<=4MiB.
  // Wrong/missing component, bad index or path bound throws invalid_argument.
  AnalysisJsonDescription describe(const AnalysisJsonPath &path) const;
  // Containers only, scalar throws. offset>size throws, ==size empty; limit1..64.
  // Object/document and array order preserved, every child reachable.
  AnalysisJsonPropertyPage children(const AnalysisJsonPath &path, size_t offset = 0,
                                    size_t limit = page_size) const;
  // Scalars only; explicitly create/cache once per selection, never dump each frame.
  AnalysisJsonText scalar_text(const AnalysisJsonPath &path) const;
  // Exact reversible RFC6901 path with ~0/~1 escaping, also paged. Typed traversal
  // stays authoritative for numeric keys vs array indices; empty path=root.
  AnalysisJsonText path_text(const AnalysisJsonPath &path) const;
 private:
  // Private owned JSON+frozen summaries; no mutation/lazy I/O/Viewer effects.
  AnalysisResultInspection() = default;
  const io::Json &resolve(const AnalysisJsonPath &path) const;
  io::Json result_;
  size_t encoded_bytes_ = 0;
  std::string encoded_sha256_;
  std::vector<AnalysisResultOutput> outputs_;
  AnalysisResultIssues errors_, warnings_;
};
} // namespace stk::app
