/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Message catalogs keyed by stable ids ("ui.ok", "unit.grid_index", ...): one flat JSON object per
 * language (desktop/app/i18n/<lang>.json, keys starting with "_" are comments). Default language
 * zh_CN; switchable at runtime. Lookup falls back to en, then to the key itself.
 * desktop/app/i18n/check_i18n.py fails CI when a catalog misses a key.
 */
#pragma once

#include <initializer_list>
#include <map>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace stk::ui {

class Catalog {
 public:
  static constexpr const char *DEFAULT_LANGUAGE = "zh_CN";
  static constexpr const char *FALLBACK_LANGUAGE = "en";

  /** Parses a flat JSON object of strings. Returns false (with *err) on malformed input. */
  bool load_json(const std::string &lang, std::string_view json_text, std::string *err = nullptr);
  bool load_file(const std::string &lang, const std::string &path, std::string *err = nullptr);
  /** Loads every "<lang>.json" in `dir` (zh_CN.json, en.json, ...). Returns the number loaded. */
  int load_dir(const std::string &dir, std::string *err = nullptr);
  void set(const std::string &lang, const std::string &key, std::string text);

  void set_language(const std::string &lang) { lang_ = lang; }
  const std::string &language() const { return lang_; }
  std::vector<std::string> languages() const;
  bool has(const std::string &lang, std::string_view key) const;
  size_t size(const std::string &lang) const;

  /** Current language, then en, then the key. */
  std::string_view tr(std::string_view key) const;
  /** tr() with "{name}" placeholders replaced. */
  std::string format(std::string_view key,
                     std::initializer_list<std::pair<std::string_view, std::string>> args) const;
  /** Like tr() but returns `fallback` instead of the key when missing everywhere. */
  std::string_view tr_or(std::string_view key, std::string_view fallback) const;

 private:
  const std::string *find(const std::string &lang, std::string_view key) const;
  std::map<std::string, std::map<std::string, std::string, std::less<>>> langs_;
  std::string lang_ = DEFAULT_LANGUAGE;
};

}  // namespace stk::ui
