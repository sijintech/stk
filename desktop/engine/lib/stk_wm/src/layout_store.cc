/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/wm/layout_store.hh"

#include <cmath>
#include <fstream>
#include <sstream>
#include <system_error>

#include "stk/core/paths.hh"

namespace stk::wm {

namespace fs = std::filesystem;

nlohmann::json layout_to_json(const LayoutFile &f)
{
  nlohmann::json j = nlohmann::json::object();
  j["format"] = kLayoutFormat;
  j["version"] = kLayoutVersion;
  nlohmann::json w = {{"width", f.window.width}, {"height", f.window.height}, {"maximized", f.window.maximized}};
  if (f.window.has_position) {
    w["x"] = f.window.x;
    w["y"] = f.window.y;
  }
  j["window"] = std::move(w);
  j["language"] = f.language;
  j["ui_scale"] = std::round(double(f.ui_scale) * 1000.0) / 1000.0;
  j["screen"] = f.screen.is_null() ? nlohmann::json::object() : f.screen;
  return j;
}

bool layout_from_json(const nlohmann::json &j, LayoutFile &r_file, std::string *r_error)
{
  auto fail = [&](const std::string &msg) {
    if (r_error) {
      *r_error = msg;
    }
    return false;
  };
  if (!j.is_object()) {
    return fail("not a JSON object");
  }
  const auto format = j.find("format");
  if (format == j.end() || *format != kLayoutFormat) {
    return fail(std::string("format is not '") + kLayoutFormat + "'");
  }
  const auto version = j.find("version");
  if (version == j.end() || !version->is_number_integer()) {
    return fail("missing integer version");
  }
  const int v = version->get<int>();
  if (v < 1 || v > kLayoutVersion) {
    return fail("unsupported layout version " + std::to_string(v));
  }
  LayoutFile f;
  f.version = v;
  if (const auto w = j.find("window"); w != j.end()) {
    if (!w->is_object()) {
      return fail("window must be an object");
    }
    auto int_field = [&](const char *name, int lo, int hi, int &out) {
      const auto it = w->find(name);
      if (it == w->end()) {
        return true;
      }
      if (!it->is_number_integer() || it->get<long long>() < lo || it->get<long long>() > hi) {
        return false;
      }
      out = it->get<int>();
      return true;
    };
    if (!int_field("width", 0, 16384, f.window.width) || !int_field("height", 0, 16384, f.window.height)) {
      return fail("invalid window size");
    }
    const bool has_x = w->contains("x"), has_y = w->contains("y");
    if (has_x != has_y || !int_field("x", -100000, 100000, f.window.x) || !int_field("y", -100000, 100000, f.window.y)) {
      return fail("invalid window position");
    }
    f.window.has_position = has_x;
    if (const auto m = w->find("maximized"); m != w->end()) {
      if (!m->is_boolean()) {
        return fail("window.maximized must be a boolean");
      }
      f.window.maximized = m->get<bool>();
    }
  }
  if (const auto l = j.find("language"); l != j.end()) {
    if (!l->is_string() || l->get_ref<const std::string &>().size() > 16) {
      return fail("language must be a short string");
    }
    f.language = l->get<std::string>();
  }
  if (const auto s = j.find("ui_scale"); s != j.end()) {
    if (!s->is_number() || !std::isfinite(s->get<double>()) || s->get<double>() < 0.25 || s->get<double>() > 4.0) {
      return fail("ui_scale must be between 0.25 and 4");
    }
    f.ui_scale = float(s->get<double>());
  }
  const auto screen = j.find("screen");
  if (screen == j.end() || !screen->is_object()) {
    return fail("missing screen object");
  }
  f.screen = *screen;
  r_file = std::move(f);
  return true;
}

fs::path default_layout_path()
{
  return core::user_config_dir() / "desktop" / "layout.json";
}

bool save_layout_file(const fs::path &path, const LayoutFile &file, std::string *r_error)
{
  auto fail = [&](const std::string &msg) {
    if (r_error) {
      *r_error = msg;
    }
    return false;
  };
  std::error_code ec;
  if (path.has_parent_path()) {
    fs::create_directories(path.parent_path(), ec);
    if (ec) {
      return fail("cannot create " + core::path_to_utf8(path.parent_path()) + ": " + ec.message());
    }
  }
  fs::path tmp = path;
  tmp += ".tmp";
  {
    std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
    if (!out) {
      return fail("cannot write " + core::path_to_utf8(tmp));
    }
    out << layout_to_json(file).dump(2) << '\n';
    out.close();
    if (!out) {
      fs::remove(tmp, ec);
      return fail("write failed: " + core::path_to_utf8(tmp));
    }
  }
  fs::rename(tmp, path, ec);
  if (ec) {
    fs::remove(tmp, ec);
    return fail("cannot replace " + core::path_to_utf8(path) + ": " + ec.message());
  }
  return true;
}

LayoutLoad load_layout_file(const fs::path &path, LayoutFile &r_file, std::string *r_error)
{
  std::error_code ec;
  if (!fs::exists(path, ec)) {
    if (r_error) {
      *r_error = "no layout file";
    }
    return LayoutLoad::Missing;
  }
  const auto size = fs::file_size(path, ec);
  if (ec || size > kLayoutMaxBytes) {
    if (r_error) {
      *r_error = ec ? ec.message() : "layout file too large";
    }
    return LayoutLoad::Corrupt;
  }
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    if (r_error) {
      *r_error = "cannot read " + core::path_to_utf8(path);
    }
    return LayoutLoad::Corrupt;
  }
  std::ostringstream ss;
  ss << in.rdbuf();
  const nlohmann::json j = nlohmann::json::parse(ss.str(), nullptr, false);
  if (j.is_discarded()) {
    if (r_error) {
      *r_error = "not valid JSON";
    }
    return LayoutLoad::Corrupt;
  }
  return layout_from_json(j, r_file, r_error) ? LayoutLoad::Ok : LayoutLoad::Corrupt;
}

fs::path quarantine_layout_file(const fs::path &path)
{
  fs::path aside = path;
  aside += ".corrupt";
  std::error_code ec;
  fs::remove(aside, ec);
  fs::rename(path, aside, ec);
  return ec ? fs::path() : aside;
}

}  // namespace stk::wm
