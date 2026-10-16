/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include <algorithm>
#include <initializer_list>
#include <string_view>

namespace stk::app {
/** Workspace hooks are explicit exports, independent of ordinary layout persistence. */
inline bool workspace_fields(const io::Json &value, const std::initializer_list<std::string_view> strings,
                             const std::initializer_list<std::string_view> integers = {},
                             const std::initializer_list<std::string_view> booleans = {},
                             const std::initializer_list<std::string_view> objects = {},
                             const size_t bytes = 4 * 1024 * 1024)
{
  if (!value.is_object() || !value.contains("version") || !value.at("version").is_number_integer() || value.at("version") != 1 || value.dump().size() > bytes) { return false; }
  for (const auto &[key, item] : value.items()) {
    if (key == "version") { continue; }
    if (std::find(strings.begin(), strings.end(), key) != strings.end()) {
      if (!item.is_string() || item.get_ref<const std::string &>().find('\0') != std::string::npos) { return false; }
    }
    else if (std::find(integers.begin(), integers.end(), key) != integers.end()) {
      if (!item.is_number_integer() || (item.is_number_unsigned() && item.get<uint64_t>() > 2147483647) || item.get<int64_t>() < -2147483647 || item.get<int64_t>() > 2147483647) { return false; }
    }
    else if (std::find(booleans.begin(), booleans.end(), key) != booleans.end()) {
      if (!item.is_boolean()) { return false; }
    }
    else if (std::find(objects.begin(), objects.end(), key) != objects.end()) {
      if (!item.is_object() && !item.is_array() && !item.is_null()) { return false; }
    }
    else { return false; }
  }
  return true;
}
}  // namespace stk::app
