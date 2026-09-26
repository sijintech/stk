/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Font stack on BLF: Inter (UI), DejaVu Sans Mono (code / logs) and Noto Sans CJK, all loaded
 * with BLF's fallback flag so that any font falls back to the others for missing glyphs
 * (Chinese in Inter, Latin in Noto CJK, ...).
 *
 * Fonts come from `<datafiles>/fonts`, where the datafiles root is found by #locate_datafiles.
 * Sizes are given in points at 1x (Blender's 72-DPI convention, UI default 11 pt) and converted to
 * BLF pixel sizes with the UI scale, so text is rasterized natively at every DPI (never scaled
 * bitmaps).
 */
#pragma once

#include <string>
#include <string_view>

namespace stk::gfx {

/** Default UI text size in points (Blender's `UI_DEFAULT_TEXT_POINTS`). */
inline constexpr float kUiTextPoints = 11.0f;

struct FontStack {
  /** Inter, the default UI font (falls back to Noto Sans CJK for Chinese). */
  int ui = -1;
  /** DejaVu Sans Mono (falls back to Noto Sans CJK for Chinese). */
  int mono = -1;
  /** Noto Sans CJK, addressed directly (e.g. to force CJK metrics). */
  int cjk = -1;
  /** Resolved datafiles root and fonts directory. */
  std::string datafiles;
  std::string fonts_dir;

  bool loaded() const
  {
    return ui >= 0 && mono >= 0 && cjk >= 0;
  }
};

/** BLF pixel size for `points` at `ui_scale`. */
inline float font_px(const float points, const float ui_scale)
{
  return points * ui_scale;
}

/** `BLF_size(font, font_px(points, ui_scale))`. */
void font_size(int font, float points, float ui_scale);

/**
 * Clears the BLF glyph caches. Call after a DPI change (glyphs are cached per size, so without
 * this every visited scale keeps its caches alive, as in Blender's WM).
 */
void fonts_dpi_changed();

/** Directory of the running executable (empty when unknown). */
std::string executable_dir();

/**
 * Finds the datafiles root (the directory containing `fonts/Inter.woff2`). Search order:
 *   1. `override_dir` (e.g. `--datafiles`), then `$STK_BLENDER_DATAFILES`;
 *   2. next to the executable: `datafiles/`, `../share/stk-desktop/datafiles/`,
 *      `../Resources/datafiles/` (macOS bundle);
 *   3. the vendored source tree (development builds only).
 * Returns an empty string when nothing is found; `r_tried` lists the candidates.
 */
std::string locate_datafiles(std::string_view override_dir, std::string *r_tried = nullptr);

/**
 * Loads the font stack from `<datafiles>/fonts`. Requires `BLF_init()` (done by #Gpu::create,
 * which calls this). Returns false with `r_error` when a required font is missing.
 */
bool fonts_load(const std::string &datafiles, FontStack &r_fonts, std::string &r_error);

}  // namespace stk::gfx
