/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/json.hh"

#include "stk/core/mmap.hh"
#include "stk/core/paths.hh"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace stk::io {

Json parse_json(std::string_view text)
{
  try {
    return Json::parse(text.begin(), text.end());
  }
  catch (const nlohmann::json::exception &error) {
    throw JsonError(std::string("invalid JSON: ") + error.what());
  }
}

Json read_json_file(const std::filesystem::path &path)
{
  const std::string text = core::read_text_file(path);
  try {
    return parse_json(text);
  }
  catch (const JsonError &error) {
    throw JsonError(core::path_to_utf8(path.filename()) + ": " + error.what());
  }
}

namespace {

/* Shortest round-trip decimal digits of a finite non-zero |value| and the position of the decimal
 * point (value = 0.d1d2d3... x 10^decpt). */
void shortest_digits(double value, std::string &digits, int &decpt)
{
  char buffer[64];
  size_t length = 0;
#if defined(__cpp_lib_to_chars) && __cpp_lib_to_chars >= 201611L
  const auto result = std::to_chars(buffer, buffer + sizeof(buffer), value, std::chars_format::scientific);
  length = size_t(result.ptr - buffer);
#else
  /* The first precision whose correctly rounded %e form reads back exactly is the shortest
   * representation closest to the value (what Python's repr and std::to_chars produce). */
  for (int precision = 0; precision < 17; precision++) {
    std::snprintf(buffer, sizeof(buffer), "%.*e", precision, value);
    for (char *c = buffer; *c; c++) {
      if (*c == ',') {
        *c = '.'; /* locales with a decimal comma */
      }
    }
    if (std::strtod(buffer, nullptr) == value) {
      break;
    }
  }
  length = std::strlen(buffer);
#endif
  const std::string_view text(buffer, length);
  const size_t e = text.find('e');
  digits.clear();
  for (char c : text.substr(0, e)) {
    if (c >= '0' && c <= '9') {
      digits.push_back(c);
    }
  }
  while (digits.size() > 1 && digits.back() == '0') {
    digits.pop_back();
  }
  const int exponent = std::atoi(std::string(text.substr(e + 1)).c_str());
  decpt = exponent + 1;
}

void append_python_float(std::string &out, double value, bool json)
{
  if (std::isnan(value)) {
    out += json ? "NaN" : "nan";
    return;
  }
  if (std::isinf(value)) {
    out += value < 0 ? "-" : "";
    out += json ? "Infinity" : "inf";
    return;
  }
  if (value == 0.0) {
    out += std::signbit(value) ? "-0.0" : "0.0";
    return;
  }
  if (value < 0) {
    out.push_back('-');
    value = -value;
  }
  std::string digits;
  int decpt;
  shortest_digits(value, digits, decpt);
  const int n = int(digits.size());
  if (decpt > -4 && decpt <= 16) {
    if (decpt <= 0) {
      out += "0.";
      out.append(size_t(-decpt), '0');
      out += digits;
    }
    else if (decpt >= n) {
      out += digits;
      out.append(size_t(decpt - n), '0');
      out += ".0";
    }
    else {
      out.append(digits, 0, size_t(decpt));
      out.push_back('.');
      out.append(digits, size_t(decpt), std::string::npos);
    }
    return;
  }
  out.push_back(digits[0]);
  if (n > 1) {
    out.push_back('.');
    out.append(digits, 1, std::string::npos);
  }
  const int exponent = decpt - 1;
  char buffer[16];
  std::snprintf(buffer, sizeof(buffer), "e%c%02d", exponent < 0 ? '-' : '+', std::abs(exponent));
  out += buffer;
}

void append_string(std::string &out, const std::string &text)
{
  out.push_back('"');
  for (unsigned char c : text) {
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\r':
        out += "\\r";
        break;
      case '\t':
        out += "\\t";
        break;
      case '\b':
        out += "\\b";
        break;
      case '\f':
        out += "\\f";
        break;
      default:
        if (c < 0x20) {
          char buffer[8];
          std::snprintf(buffer, sizeof(buffer), "\\u%04x", c);
          out += buffer;
        }
        else {
          out.push_back(char(c));
        }
    }
  }
  out.push_back('"');
}

void dump(std::string &out, const Json &value, bool sort_keys, bool compact, bool canonical)
{
  switch (value.type()) {
    case Json::value_t::null:
      out += "null";
      return;
    case Json::value_t::boolean:
      out += value.get<bool>() ? "true" : "false";
      return;
    case Json::value_t::number_integer:
      out += std::to_string(value.get<int64_t>());
      return;
    case Json::value_t::number_unsigned:
      out += std::to_string(value.get<uint64_t>());
      return;
    case Json::value_t::number_float: {
      double v = value.get<double>();
      if (canonical && v == 0.0) {
        v = 0.0;
      }
      append_python_float(out, v, true);
      return;
    }
    case Json::value_t::string:
      append_string(out, value.get_ref<const std::string &>());
      return;
    case Json::value_t::array: {
      out.push_back('[');
      bool first = true;
      for (const Json &item : value) {
        if (!first) {
          out += compact ? "," : ", ";
        }
        first = false;
        dump(out, item, sort_keys, compact, canonical);
      }
      out.push_back(']');
      return;
    }
    case Json::value_t::object: {
      out.push_back('{');
      std::vector<const std::string *> keys;
      keys.reserve(value.size());
      for (auto it = value.begin(); it != value.end(); ++it) {
        keys.push_back(&it.key());
      }
      if (sort_keys) {
        std::sort(keys.begin(), keys.end(), [](const std::string *a, const std::string *b) { return *a < *b; });
      }
      bool first = true;
      for (const std::string *key : keys) {
        if (!first) {
          out += compact ? "," : ", ";
        }
        first = false;
        append_string(out, *key);
        out += compact ? ":" : ": ";
        dump(out, value.at(*key), sort_keys, compact, canonical);
      }
      out.push_back('}');
      return;
    }
    case Json::value_t::binary:
    case Json::value_t::discarded:
      throw JsonError("value cannot be written as JSON");
  }
}

}  // namespace

std::string python_float_repr(double value)
{
  std::string out;
  append_python_float(out, value, false);
  return out;
}

std::string python_str(const Json &value)
{
  if (value.is_number_float()) {
    return python_float_repr(value.get<double>());
  }
  return python_json_dumps(value);
}

std::string python_json_dumps(const Json &value, bool sort_keys, bool compact)
{
  std::string out;
  dump(out, value, sort_keys, compact, false);
  return out;
}

std::string canonical_json(const Json &value)
{
  std::string out;
  dump(out, value, true, true, true);
  return out;
}

bool py_truthy(const Json &value)
{
  switch (value.type()) {
    case Json::value_t::null:
      return false;
    case Json::value_t::boolean:
      return value.get<bool>();
    case Json::value_t::number_integer:
      return value.get<int64_t>() != 0;
    case Json::value_t::number_unsigned:
      return value.get<uint64_t>() != 0;
    case Json::value_t::number_float:
      return value.get<double>() != 0.0;
    case Json::value_t::string:
      return !value.get_ref<const std::string &>().empty();
    case Json::value_t::array:
    case Json::value_t::object:
      return !value.empty();
    default:
      return true;
  }
}

bool is_finite_number(const Json &value)
{
  return value.is_number() && std::isfinite(value.get<double>());
}

bool is_integer_token(const Json &value)
{
  return value.is_number_integer();
}

std::string_view json_type_name(const Json &value)
{
  switch (value.type()) {
    case Json::value_t::null:
      return "null";
    case Json::value_t::boolean:
      return "boolean";
    case Json::value_t::number_integer:
    case Json::value_t::number_unsigned:
    case Json::value_t::number_float:
      return "number";
    case Json::value_t::string:
      return "string";
    case Json::value_t::array:
      return "array";
    case Json::value_t::object:
      return "object";
    default:
      return "binary";
  }
}

double number_value(const Json &value)
{
  return value.get<double>();
}

namespace {
const Json *member(const Json &object, std::string_view key)
{
  if (!object.is_object()) {
    return nullptr;
  }
  const auto it = object.find(key);
  return it == object.end() ? nullptr : &*it;
}
}  // namespace

std::string get_string(const Json &object, std::string_view key, std::string_view fallback)
{
  const Json *v = member(object, key);
  return v && v->is_string() ? v->get<std::string>() : std::string(fallback);
}

bool get_bool(const Json &object, std::string_view key, bool fallback)
{
  const Json *v = member(object, key);
  return v && v->is_boolean() ? v->get<bool>() : fallback;
}

double get_number(const Json &object, std::string_view key, double fallback)
{
  const Json *v = member(object, key);
  return v && v->is_number() ? v->get<double>() : fallback;
}

int64_t get_int(const Json &object, std::string_view key, int64_t fallback)
{
  const Json *v = member(object, key);
  return v && v->is_number_integer() ? v->get<int64_t>() : fallback;
}

}  // namespace stk::io
