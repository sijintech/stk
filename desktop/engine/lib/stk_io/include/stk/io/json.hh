/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* JSON documents of STK (payload manifests, graphs, catalogs, presets, results) use
 * nlohmann::ordered_json so object key order is kept exactly as in the source document
 * (validation messages and canonical forms depend on it, as in Python's dict). */

#include <nlohmann/json.hpp>

#include <filesystem>
#include <stdexcept>
#include <string>
#include <string_view>

namespace stk::io {

using Json = nlohmann::ordered_json;

class JsonError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

/** Parse UTF-8 JSON text (RFC 8259; NaN/Infinity literals are rejected). Throws JsonError. */
Json parse_json(std::string_view text);
Json read_json_file(const std::filesystem::path &path);

/** Python's repr(float): shortest round-trip digits, fixed notation for 1e-4 <= |x| < 1e16
 * ("1.0", "0.0001", "1e-05", "1e+16", "nan", "inf"). */
std::string python_float_repr(double value);

/** Python's str() of a JSON number (int or float) or json.dumps of other values. */
std::string python_str(const Json &value);

/**
 * json.dumps(value, ensure_ascii=False[, sort_keys][, separators]) as Python writes it:
 * `compact` uses (",", ":") separators, otherwise (", ", ": "); floats as python_float_repr
 * (NaN/Infinity written as NaN/Infinity).
 */
std::string python_json_dumps(const Json &value, bool sort_keys = false, bool compact = false);

/**
 * suan.graph.schema.canonical_json: sorted keys, no whitespace, shortest round-trip floats,
 * -0.0 -> 0.0, UTF-8 (not \u-escaped). Keys are sorted by code point, as Python sorts str.
 */
std::string canonical_json(const Json &value);

/** Python truthiness of a JSON value (null, false, 0, 0.0, "", [], {} are false). */
bool py_truthy(const Json &value);

/** A finite JSON number that is not a boolean. */
bool is_finite_number(const Json &value);
/** A JSON integer (integer token, not a float such as 3.0) that is not a boolean. */
bool is_integer_token(const Json &value);

/** Short JSON type name for messages: null, boolean, number, string, array, object. */
std::string_view json_type_name(const Json &value);

/** Numeric value of a JSON number (int, unsigned or float). */
double number_value(const Json &value);

/* Type-safe member access: the fallback when `object` is not an object, the key is missing or the
 * member has another JSON type (nlohmann's value() throws on a type mismatch instead). */
std::string get_string(const Json &object, std::string_view key, std::string_view fallback = {});
bool get_bool(const Json &object, std::string_view key, bool fallback);
double get_number(const Json &object, std::string_view key, double fallback);
int64_t get_int(const Json &object, std::string_view key, int64_t fallback);

}  // namespace stk::io
