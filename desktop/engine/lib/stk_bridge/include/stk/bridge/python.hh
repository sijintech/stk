/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Which Python runs the bridge (`python -m suan.desktop_bridge --stdio`). */
#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace stk::bridge {

struct PythonLookup {
  /** The app setting (empty: not set). A path or a name on PATH. */
  std::string configured;
  /** Bundled interpreters to try before PATH (a later packaging step fills these in). */
  std::vector<std::string> bundled;
  /** Names looked up on PATH, in order. */
  std::vector<std::string> path_names =
#if defined(_WIN32)
      {"python", "python3"};
#else
      {"python3", "python"};
#endif
};

/**
 * The interpreter: `lookup.configured`, else $STK_PYTHON, else the first existing `bundled` entry,
 * else the first of `path_names` on PATH. An explicitly configured interpreter (setting or
 * STK_PYTHON) that does not exist is an error rather than a silent fallback.
 */
std::optional<std::string> find_python(const PythonLookup &lookup, std::string &r_error);

}  // namespace stk::bridge
