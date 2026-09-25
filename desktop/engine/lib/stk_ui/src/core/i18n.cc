/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/i18n.hh"

#include <filesystem>
#include <fstream>
#include <sstream>

#include <nlohmann/json.hpp>

namespace stk::ui {

/** UTF-8 path (std::filesystem::u8path is deprecated in C++20). */
static std::filesystem::path fs_path(const std::string &s)
{
  return std::filesystem::path(std::u8string(s.begin(), s.end()));
}

bool Catalog::load_json(const std::string &lang, std::string_view json_text, std::string *err)
{
  nlohmann::json doc = nlohmann::json::parse(json_text, nullptr, false);
  if (doc.is_discarded() || !doc.is_object()) {
    if (err) {
      *err = "catalog '" + lang + "' is not a JSON object";
    }
    return false;
  }
  auto &dst = langs_[lang];
  for (const auto &[key, value] : doc.items()) {
    if (!key.empty() && key[0] == '_') {
      continue;
    }
    if (!value.is_string()) {
      if (err) {
        *err = "catalog '" + lang + "': value of '" + key + "' is not a string";
      }
      return false;
    }
    dst[key] = value.get<std::string>();
  }
  return true;
}

bool Catalog::load_file(const std::string &lang, const std::string &path, std::string *err)
{
  std::ifstream f(fs_path(path), std::ios::binary);
  if (!f) {
    if (err) {
      *err = "cannot open " + path;
    }
    return false;
  }
  std::stringstream ss;
  ss << f.rdbuf();
  return load_json(lang, ss.str(), err);
}

int Catalog::load_dir(const std::string &dir, std::string *err)
{
  int n = 0;
  std::error_code ec;
  for (const auto &entry : std::filesystem::directory_iterator(fs_path(dir), ec)) {
    if (!entry.is_regular_file() || entry.path().extension() != ".json") {
      continue;
    }
    if (load_file(entry.path().stem().string(), entry.path().string(), err)) {
      n++;
    }
  }
  if (ec && err) {
    *err = "cannot list " + dir;
  }
  return n;
}

void Catalog::set(const std::string &lang, const std::string &key, std::string text)
{
  langs_[lang][key] = std::move(text);
}

std::vector<std::string> Catalog::languages() const
{
  std::vector<std::string> out;
  for (const auto &kv : langs_) {
    out.push_back(kv.first);
  }
  return out;
}

const std::string *Catalog::find(const std::string &lang, std::string_view key) const
{
  const auto l = langs_.find(lang);
  if (l == langs_.end()) {
    return nullptr;
  }
  const auto it = l->second.find(key);
  return it == l->second.end() ? nullptr : &it->second;
}

bool Catalog::has(const std::string &lang, std::string_view key) const
{
  return find(lang, key) != nullptr;
}

size_t Catalog::size(const std::string &lang) const
{
  const auto l = langs_.find(lang);
  return l == langs_.end() ? 0 : l->second.size();
}

std::string_view Catalog::tr_or(std::string_view key, std::string_view fallback) const
{
  if (const std::string *s = find(lang_, key)) {
    return *s;
  }
  if (const std::string *s = find(FALLBACK_LANGUAGE, key)) {
    return *s;
  }
  return fallback;
}

std::string_view Catalog::tr(std::string_view key) const
{
  return tr_or(key, key);
}

std::string Catalog::format(std::string_view key,
                            std::initializer_list<std::pair<std::string_view, std::string>> args) const
{
  std::string s(tr(key));
  for (const auto &[name, value] : args) {
    const std::string ph = "{" + std::string(name) + "}";
    for (size_t p = s.find(ph); p != std::string::npos; p = s.find(ph, p + value.size())) {
      s.replace(p, ph.size(), value);
    }
  }
  return s;
}

}  // namespace stk::ui
