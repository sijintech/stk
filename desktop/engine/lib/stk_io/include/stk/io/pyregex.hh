/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* A regular-expression engine with Python `re` semantics for str patterns, used for JSON-Schema
 * `pattern` (suan.graph.schema uses re.search) so validation matches Python on every platform:
 *
 *  - matching is over Unicode code points of UTF-8 text (not bytes, not UTF-16 units);
 *  - `$` matches at the end or before a final "\n", `\Z` only at the end, `\A`/`^` at the start;
 *  - `.` is any code point except "\n"; `\d`, `\w`, `\s` (and `\b`) use Python's Unicode tables;
 *  - supported: literals, escapes (\n \t \r \f \v \a \xhh \uhhhh \Uhhhhhhhh, octal, escaped
 *    punctuation), classes with ranges/negation/\d\w\s, groups (capturing, (?:...), (?P<n>...)),
 *    alternation, * + ? {m} {m,} {,n} {m,n} (greedy or lazy), lookahead (?=...) (?!...).
 *  - rejected with RegexError: back-references, lookbehind, inline flags, possessive quantifiers,
 *    conditionals, \N{...}.
 *
 * It is a Thompson-NFA simulation (no backtracking): linear in the text length per lookahead
 * position, with no recursion on the text, so long inputs cannot overflow the stack. */

#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>

namespace stk::io {

class RegexError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

class PyRegex {
 public:
  /** Compile a pattern (UTF-8); throws RegexError for invalid or unsupported syntax. */
  explicit PyRegex(std::string_view pattern);
  ~PyRegex();
  PyRegex(PyRegex &&) noexcept;
  PyRegex &operator=(PyRegex &&) noexcept;

  /** re.search: a match anywhere in `text` (UTF-8; invalid bytes act as U+FFFD). */
  bool search(std::string_view text) const;
  /** re.match: a match starting at the beginning. */
  bool match(std::string_view text) const;
  /** re.fullmatch: the whole text. */
  bool fullmatch(std::string_view text) const;

  const std::string &pattern() const
  {
    return pattern_;
  }

  struct Program;

 private:
  std::string pattern_;
  std::unique_ptr<Program> program_;
};

/** re.search(pattern, text) with a small per-thread cache of compiled patterns. */
bool py_regex_search(std::string_view pattern, std::string_view text);

}  // namespace stk::io
