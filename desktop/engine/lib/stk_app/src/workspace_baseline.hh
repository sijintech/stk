/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_document.hh"
#include "stk/core/utf8.hh"
#include "stk/io/json.hh"

#include <stdexcept>

namespace stk::app {
inline io::Json workspace_json_text(const io::Json &encoded, const size_t byte_limit,
                                    const size_t depth_limit = AnalysisDocumentLimits::max_depth + 1)
{
  if (!encoded.is_string()) { throw std::invalid_argument("Workspace baseline must be JSON text"); }
  const auto &text = encoded.get_ref<const std::string &>();
  if (text.size() > byte_limit || !core::utf8::is_valid(text)) {
    throw std::invalid_argument("Workspace baseline exceeds its text bounds");
  }
  // Bound nesting before constructing a DOM or invoking recursive serializers. Escaped quotes
  // and braces inside strings do not contribute to nesting; the parser validates the grammar.
  size_t depth = 0; bool quoted = false, escaped = false;
  for (const char ch : text) {
    if (quoted) {
      if (escaped) { escaped = false; }
      else if (ch == '\\') { escaped = true; }
      else if (ch == '"') { quoted = false; }
    }
    else if (ch == '"') { quoted = true; }
    else if (ch == '{' || ch == '[') {
      if (++depth > depth_limit) { throw std::invalid_argument("Workspace baseline is too deep"); }
    }
    else if (ch == '}' || ch == ']') {
      if (!depth) { throw std::invalid_argument("Invalid workspace baseline nesting"); }
      --depth;
    }
  }
  const auto baseline = io::parse_json(text);
  // Requiring the encoding emitted by save also rejects duplicate keys, trailing data,
  // overflowed integers and altered integer/float representations without silent coercion.
  if (io::python_json_dumps(baseline, true, true) != text) {
    throw std::invalid_argument("Workspace baseline must use canonical JSON");
  }
  return baseline;
}
/** Saved database documents retain their original path spelling. Workspace candidates may
 * relocate paths, so their comparison baseline travels as bounded canonical JSON text. */
inline io::Json workspace_baseline(const io::Json &envelope, const size_t byte_limit)
{
  return envelope.contains("baseline_json") ? workspace_json_text(envelope.at("baseline_json"), byte_limit) : envelope.at("baseline");
}
}  // namespace stk::app
