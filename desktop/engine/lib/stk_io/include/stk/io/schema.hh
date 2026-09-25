/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* The JSON-Schema subset of node parameter declarations (docs/specs/stk-graph-v1.md §4.2), a port of
 * suan.graph.schema.check_value / normalize_value that produces the same (JSON pointer, message)
 * list for the same value and schema: type (incl. lists), enum, const, minimum/maximum,
 * exclusiveMinimum/exclusiveMaximum, minLength/maxLength (code points), pattern (Python re.search,
 * see pyregex.hh), items/prefixItems, minItems/maxItems/uniqueItems, properties/patternProperties/
 * required/additionalProperties/propertyNames/minProperties/maxProperties, anyOf/oneOf/allOf/not,
 * if/then/else. Annotations (title, description, default, x-stk-*) are ignored. */

#include "stk/io/json.hh"

#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace stk::io {

struct SchemaIssue {
  std::string path; /* RFC 6901 pointer relative to the validated value */
  std::string message;
  bool operator==(const SchemaIssue &) const = default;
};

/** A schema the subset cannot evaluate (unknown `type` name, bad pattern); Python raises there too. */
class SchemaError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

/** check_value(value, schema, path): every problem found (empty = valid). */
std::vector<SchemaIssue> check_value(const Json &value, const Json &schema, const std::string &path = {});

/** normalize_value: integral numbers as integers where the schema says integer, floats where it says
 * number (-0.0 -> 0.0); anyOf/oneOf use the first matching branch. The value must be valid. */
Json normalize_value(const Json &value, const Json &schema);

/** RFC 6901 escaping of one reference token ("~" -> "~0", "/" -> "~1"). */
std::string pointer_token(std::string_view key);
std::string pointer_join(const std::string &path, std::string_view key);
std::string pointer_join(const std::string &path, size_t index);

/** difflib.get_close_matches(word, possibilities, n, cutoff) over code points. */
std::vector<std::string> close_matches(std::string_view word,
                                       const std::vector<std::string> &possibilities,
                                       size_t n = 3,
                                       double cutoff = 0.6);

/** Python's JSON equality of schema values (1 == 1.0, booleans are not numbers). */
bool json_equal(const Json &a, const Json &b);

/** suan.graph.schema._short: json.dumps(ensure_ascii=False) cut to `limit` code points with "...". */
std::string short_json(const Json &value, size_t limit = 60);

}  // namespace stk::io
