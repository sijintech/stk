/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/bridge/python.hh"

#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"

namespace stk::bridge {

std::optional<std::string> find_python(const PythonLookup &lookup, std::string &r_error)
{
  const auto explicit_choice = [&](const std::string &value, const char *origin) -> std::optional<std::string> {
    if (auto found = find_executable(value)) {
      return found;
    }
    r_error = std::string(origin) + " names a Python interpreter that does not exist: " + value;
    return std::nullopt;
  };
  if (!lookup.configured.empty()) {
    return explicit_choice(lookup.configured, "The Python setting");
  }
  if (const std::optional<std::string> env = core::getenv_utf8("STK_PYTHON"); env && !env->empty()) {
    return explicit_choice(*env, "STK_PYTHON");
  }
  for (const std::string &candidate : lookup.bundled) {
    if (auto found = find_executable(candidate)) {
      return found;
    }
  }
  for (const std::string &name : lookup.path_names) {
    if (auto found = find_executable(name)) {
      return found;
    }
  }
  r_error = "No Python interpreter found (set STK_PYTHON or the Python setting)";
  return std::nullopt;
}

}  // namespace stk::bridge
