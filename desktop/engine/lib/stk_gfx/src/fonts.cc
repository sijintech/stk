/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/gfx/fonts.hh"

#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <system_error>
#include <vector>

#if defined(_WIN32)
#  ifndef NOMINMAX
#    define NOMINMAX
#  endif
#  include <windows.h>
#elif defined(__APPLE__)
#  include <climits>
#  include <cstdint>
#  include <mach-o/dyld.h>
#endif

#include "BLF_api.hh"

#include "stk/core/paths.hh"

#ifndef STK_GFX_SOURCE_DATAFILES
#  define STK_GFX_SOURCE_DATAFILES ""
#endif

namespace stk::gfx {

namespace fs = std::filesystem;

static constexpr const char *kUiFont = "Inter.woff2";
static constexpr const char *kMonoFont = "DejaVuSansMono.woff2";
static constexpr const char *kCjkFont = "Noto Sans CJK Regular.woff2";

void font_size(const int font, const float points, const float ui_scale)
{
  blender::BLF_size(font, font_px(points, ui_scale));
}

void fonts_dpi_changed()
{
  blender::BLF_cache_clear();
}

static std::string path_utf8(const fs::path &p)
{
  return core::path_to_utf8(p);
}

static fs::path path_from_utf8(const std::string &s)
{
  return core::path_from_utf8(s);
}

std::string executable_dir()
{
  fs::path exe;
#if defined(_WIN32)
  std::wstring buf(32768, L'\0');
  const DWORD n = GetModuleFileNameW(nullptr, buf.data(), DWORD(buf.size()));
  if (n == 0 || n >= buf.size()) {
    return {};
  }
  buf.resize(n);
  exe = fs::path(buf);
#elif defined(__APPLE__)
  uint32_t size = 0;
  _NSGetExecutablePath(nullptr, &size);
  std::string buf(size, '\0');
  if (_NSGetExecutablePath(buf.data(), &size) != 0) {
    return {};
  }
  buf.resize(strnlen(buf.c_str(), buf.size()));
  exe = fs::path(buf);
#else
  std::error_code ec;
  exe = fs::read_symlink("/proc/self/exe", ec);
  if (ec) {
    return {};
  }
#endif
  std::error_code ec2;
  const fs::path canonical = fs::weakly_canonical(exe, ec2);
  return path_utf8((ec2 ? exe : canonical).parent_path());
}

static bool has_fonts(const fs::path &root)
{
  std::error_code ec;
  return fs::is_regular_file(root / "fonts" / kUiFont, ec);
}

std::string locate_datafiles(std::string_view override_dir, std::string *r_tried)
{
  std::vector<fs::path> candidates;
  if (!override_dir.empty()) {
    candidates.push_back(path_from_utf8(std::string(override_dir)));
  }
  if (const auto env = core::getenv_utf8("STK_BLENDER_DATAFILES"); env && !env->empty()) {
    candidates.push_back(path_from_utf8(*env));
  }
  const std::string exe_dir = executable_dir();
  if (!exe_dir.empty()) {
    const fs::path dir = path_from_utf8(exe_dir);
    candidates.push_back(dir / "datafiles");
    candidates.push_back(dir / ".." / "share" / "stk-desktop" / "datafiles");
    candidates.push_back(dir / ".." / "Resources" / "datafiles");
  }
  if (STK_GFX_SOURCE_DATAFILES[0]) {
    candidates.push_back(path_from_utf8(STK_GFX_SOURCE_DATAFILES));
  }
  for (const fs::path &c : candidates) {
    if (r_tried) {
      *r_tried += " " + path_utf8(c);
    }
    if (has_fonts(c)) {
      std::error_code ec;
      const fs::path canonical = fs::weakly_canonical(c, ec);
      return path_utf8(ec ? c : canonical);
    }
  }
  return {};
}

static int load_font(const fs::path &path, const blender::FontFlags flags, std::string &r_error)
{
  const std::string p = path_utf8(path);
  const int id = blender::BLF_load(p.c_str());
  if (id < 0) {
    r_error = "failed to load font " + p;
    return -1;
  }
  /* BLF_DEFAULT: take part in the fallback stack of every other font. */
  blender::BLF_enable(id, blender::FontFlags(flags | blender::BLF_DEFAULT));
  return id;
}

bool fonts_load(const std::string &datafiles, FontStack &r_fonts, std::string &r_error)
{
  const fs::path dir = path_from_utf8(datafiles) / "fonts";
  r_fonts = FontStack{};
  r_fonts.datafiles = datafiles;
  r_fonts.fonts_dir = path_utf8(dir);

  if ((r_fonts.ui = load_font(dir / kUiFont, blender::FontFlags(0), r_error)) < 0 ||
      (r_fonts.mono = load_font(dir / kMonoFont, blender::BLF_MONOSPACED, r_error)) < 0 ||
      (r_fonts.cjk = load_font(dir / kCjkFont, blender::FontFlags(0), r_error)) < 0)
  {
    return false;
  }

  /* Any further fonts shipped next to them (e.g. more Noto scripts) join the fallback stack. */
  std::error_code ec;
  for (const fs::directory_entry &entry : fs::directory_iterator(dir, ec)) {
    const fs::path &p = entry.path();
    const std::string ext = path_utf8(p.extension());
    const std::string name = path_utf8(p.filename());
    if (!entry.is_regular_file(ec) || name == kUiFont || name == kMonoFont || name == kCjkFont) {
      continue;
    }
    if (ext == ".woff2" || ext == ".woff" || ext == ".ttf" || ext == ".otf") {
      std::string ignored;
      load_font(p, blender::FontFlags(0), ignored);
    }
  }

  blender::BLF_default_set(r_fonts.ui);
  blender::BLF_default_size(kUiTextPoints);
  return true;
}

}  // namespace stk::gfx
