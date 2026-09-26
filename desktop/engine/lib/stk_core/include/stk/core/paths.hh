/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Paths are UTF-8 std::string at API boundaries (JSON, UI); conversion to std::filesystem::path
 * goes through char8_t so non-ASCII names work on Windows (UTF-16) as well as POSIX. */

#include <filesystem>
#include <optional>
#include <string>
#include <string_view>

namespace stk::core {

std::filesystem::path path_from_utf8(std::string_view utf8);
std::string path_to_utf8(const std::filesystem::path &path);

/** Environment variable as UTF-8 (nullopt when unset). */
std::optional<std::string> getenv_utf8(const char *name);

std::filesystem::path home_dir();
/** Per-user cache root for STK: $XDG_CACHE_HOME/stk (~/.cache/stk), ~/Library/Caches/stk, %LOCALAPPDATA%\stk\cache. */
std::filesystem::path user_cache_dir();
/** Per-user config root: $XDG_CONFIG_HOME/stk (~/.config/stk), ~/Library/Application Support/stk, %APPDATA%\stk. */
std::filesystem::path user_config_dir();
/** Content-addressed blob cache root shared with the bridge: <cache>/blobs. */
std::filesystem::path default_blob_cache_dir();

/**
 * A graph-relative path inside a binding (stk-graph-v1 §2.1): non-empty, no leading '/' or
 * backslash, no drive letter, no '..' segment, no backslash or NUL anywhere.
 */
bool is_safe_relative_path(std::string_view path);

/** `base / relative` for a safe relative path, else nullopt. */
std::optional<std::filesystem::path> join_safe(const std::filesystem::path &base, std::string_view relative);

}  // namespace stk::core
