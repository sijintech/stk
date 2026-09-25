/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/core/paths.hh"

#include "stk/core/utf8.hh"

#include <cstdlib>

#ifdef _WIN32
#  include <windows.h>
#endif

namespace stk::core {

std::filesystem::path path_from_utf8(std::string_view utf8)
{
  const std::u8string text(reinterpret_cast<const char8_t *>(utf8.data()), utf8.size());
  return std::filesystem::path(text);
}

std::string path_to_utf8(const std::filesystem::path &path)
{
  const std::u8string text = path.u8string();
  return std::string(reinterpret_cast<const char *>(text.data()), text.size());
}

std::optional<std::string> getenv_utf8(const char *name)
{
#ifdef _WIN32
  const std::u16string wide_name = utf8::to_utf16(name);
  const wchar_t *value = _wgetenv(reinterpret_cast<const wchar_t *>(wide_name.c_str()));
  if (!value) {
    return std::nullopt;
  }
  return utf8::from_utf16(std::u16string_view(reinterpret_cast<const char16_t *>(value)));
#else
  const char *value = std::getenv(name);
  if (!value) {
    return std::nullopt;
  }
  return std::string(value);
#endif
}

namespace {

std::optional<std::filesystem::path> env_dir(const char *name)
{
  const auto value = getenv_utf8(name);
  if (!value || value->empty()) {
    return std::nullopt;
  }
  std::filesystem::path path = path_from_utf8(*value);
  if (!path.is_absolute()) {
    return std::nullopt; /* XDG: relative values are ignored */
  }
  return path;
}

}  // namespace

std::filesystem::path home_dir()
{
#ifdef _WIN32
  if (auto profile = env_dir("USERPROFILE")) {
    return *profile;
  }
#endif
  if (auto home = env_dir("HOME")) {
    return *home;
  }
  return std::filesystem::temp_directory_path();
}

std::filesystem::path user_cache_dir()
{
#if defined(_WIN32)
  if (auto local = env_dir("LOCALAPPDATA")) {
    return *local / "stk" / "cache";
  }
  return home_dir() / "AppData" / "Local" / "stk" / "cache";
#elif defined(__APPLE__)
  return home_dir() / "Library" / "Caches" / "stk";
#else
  if (auto xdg = env_dir("XDG_CACHE_HOME")) {
    return *xdg / "stk";
  }
  return home_dir() / ".cache" / "stk";
#endif
}

std::filesystem::path user_config_dir()
{
#if defined(_WIN32)
  if (auto roaming = env_dir("APPDATA")) {
    return *roaming / "stk";
  }
  return home_dir() / "AppData" / "Roaming" / "stk";
#elif defined(__APPLE__)
  return home_dir() / "Library" / "Application Support" / "stk";
#else
  if (auto xdg = env_dir("XDG_CONFIG_HOME")) {
    return *xdg / "stk";
  }
  return home_dir() / ".config" / "stk";
#endif
}

std::filesystem::path default_blob_cache_dir()
{
  return user_cache_dir() / "blobs";
}

bool is_safe_relative_path(std::string_view path)
{
  if (path.empty() || path.front() == '/' || path.front() == '\\') {
    return false;
  }
  if (path.size() >= 2 && path[1] == ':' &&
      ((path[0] >= 'A' && path[0] <= 'Z') || (path[0] >= 'a' && path[0] <= 'z')))
  {
    return false;
  }
  for (char c : path) {
    if (c == '\\' || c == '\0') {
      return false;
    }
  }
  size_t start = 0;
  while (start <= path.size()) {
    size_t end = path.find('/', start);
    if (end == std::string_view::npos) {
      end = path.size();
    }
    if (path.substr(start, end - start) == "..") {
      return false;
    }
    start = end + 1;
  }
  return utf8::is_valid(path);
}

std::optional<std::filesystem::path> join_safe(const std::filesystem::path &base, std::string_view relative)
{
  if (!is_safe_relative_path(relative)) {
    return std::nullopt;
  }
  return base / path_from_utf8(relative);
}

}  // namespace stk::core
