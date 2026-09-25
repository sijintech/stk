/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * STK shims: the few blenkernel / editors / imbuf / gpu_pass symbols that the vendored
 * GHOST + GPU + BLF code references, implemented without compiling any of those modules.
 */

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <optional>
#include <string>
#include <utility>

#include "MEM_guardedalloc.h"

#include "BLI_fileops.h"
#include "BLI_math_base.h"
#include "BLI_math_color.h"
#include "BLI_math_vector.h"
#include "BLI_path_utils.hh"
#include "BLI_string.h"

#include "BKE_appdir.hh"
#include "BKE_global.hh"
#include "BKE_material.hh"

#include "DNA_userdef_types.h"

#include "GPU_pass.hh"
#include "IMB_imbuf.hh"
#include "UI_resources.hh"

#ifndef STK_BLENDER_DATAFILES_DIR
#  define STK_BLENDER_DATAFILES_DIR ""
#endif

namespace blender {

/* -------------------------------------------------------------------- */
/** \name Globals (blenkernel/intern/blender.cc)
 * \{ */

Global G{};

UserDef U{};

/** Blender defaults for the few preferences the GPU / BLF code reads. */
static const bool stk_userdef_init = [] {
  U.pixelsize = 1.0f;
  U.scale_factor = 1.0f;
  U.inv_scale_factor = 1.0f;
  U.dpi = 72;
  U.anisotropic_filter = 2;
  return true;
}();

/** \} */

/* -------------------------------------------------------------------- */
/** \name BKE_appdir (datafiles = $STK_BLENDER_DATAFILES or the build-time default)
 * \{ */

static std::string stk_datafiles_root()
{
  const char *env = getenv("STK_BLENDER_DATAFILES");
  return (env && env[0]) ? env : STK_BLENDER_DATAFILES_DIR;
}

std::optional<std::string> BKE_appdir_folder_id(const int folder_id, const char *subfolder)
{
  if (folder_id != BLENDER_DATAFILES) {
    return std::nullopt;
  }
  char path[FILE_MAX];
  BLI_path_join(path, sizeof(path), stk_datafiles_root().c_str(), subfolder ? subfolder : "");
  if (!BLI_is_dir(path)) {
    return std::nullopt;
  }
  return std::string(path);
}

void BKE_appdir_folder_caches(char *path, const size_t path_maxncpy)
{
  const char *xdg = getenv("XDG_CACHE_HOME");
#ifdef _WIN32
  const char *home = getenv("LOCALAPPDATA"); /* -> %LOCALAPPDATA%\.cache\stk-desktop */
#else
  const char *home = getenv("HOME");
#endif
  if (xdg && xdg[0]) {
    BLI_path_join(path, path_maxncpy, xdg, "stk-desktop", SEP_STR);
  }
  else if (home && home[0]) {
    BLI_path_join(path, path_maxncpy, home, ".cache", "stk-desktop", SEP_STR);
  }
  else {
    path[0] = '\0';
  }
}

const char *BKE_tempdir_session()
{
#ifdef _WIN32
  const char *tmp = getenv("TEMP");
  return (tmp && tmp[0]) ? tmp : "C:\\Windows\\Temp\\";
#else
  const char *tmp = getenv("TMPDIR");
  return (tmp && tmp[0]) ? tmp : "/tmp/";
#endif
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name BKE_material, UI theme, GPU_pass (material pipeline is not vendored)
 * \{ */

void BKE_material_defaults_free_gpu() {}

namespace ui::theme {
/* GPU code only asks for a handful of theme colors (immUniformTheme*, checker); a neutral grey
 * stands in for all of them. The STK UI has its own theme. */
static void stk_theme_rgba(int colorid, float col[4])
{
  const float v = (colorid == TH_TRANSPARENT_CHECKER_PRIMARY) ? 0.25f : 0.2f;
  col[0] = col[1] = col[2] = v;
  col[3] = 1.0f;
}
void get_color_4fv(int colorid, float col[4])
{
  stk_theme_rgba(colorid, col);
}
void get_color_3fv(int colorid, float col[3])
{
  float c[4];
  stk_theme_rgba(colorid, c);
  copy_v3_v3(col, c);
}
void get_color_shade_4fv(int colorid, int offset, float col[4])
{
  stk_theme_rgba(colorid, col);
  add_v3_fl(col, offset / 255.0f);
}
void get_color_shade_alpha_4fv(int colorid, int coloffset, int alphaoffset, float col[4])
{
  get_color_shade_4fv(colorid, coloffset, col);
  col[3] = clamp_f(col[3] + alphaoffset / 255.0f, 0.0f, 1.0f);
}
void get_color_shade_alpha_4ubv(int colorid, int coloffset, int alphaoffset, uchar col[4])
{
  float c[4];
  get_color_shade_alpha_4fv(colorid, coloffset, alphaoffset, c);
  rgba_float_to_uchar(col, c);
}
void get_color_blend_shade_4fv(int colorid1, int colorid2, float fac, int offset, float col[4])
{
  float a[4], b[4];
  get_color_shade_4fv(colorid1, offset, a);
  get_color_shade_4fv(colorid2, offset, b);
  interp_v4_v4v4(col, a, b, fac);
}
void get_color_blend_3ubv(int colorid1, int colorid2, float fac, uchar col[3])
{
  float c[4];
  get_color_blend_shade_4fv(colorid1, colorid2, fac, 0, c);
  unit_float_to_uchar_clamp_v3(col, c);
}
int get_value(int colorid)
{
  return (colorid == TH_TRANSPARENT_CHECKER_SIZE) ? 8 : 0;
}
}  // namespace ui::theme

void GPU_pass_cache_init() {}
void GPU_pass_cache_update() {}
void GPU_pass_cache_wait_for_all() {}
void GPU_pass_cache_free() {}

/** \} */

/* -------------------------------------------------------------------- */
/** \name IMB (GHOST clipboard / drag & drop images)
 * \{ */

static const StkImbufCodec *stk_codec = nullptr;

void stk_imbuf_set_codec(const StkImbufCodec *codec)
{
  stk_codec = codec;
}

ImBuf *IMB_allocImBuf(unsigned int x, unsigned int y, ImBufFlags /*flags*/)
{
  ImBuf *ibuf = MEM_new<ImBuf>(__func__);
  ibuf->x = int(x);
  ibuf->y = int(y);
  ibuf->byte_buffer.data = MEM_new_array_zeroed<uint8_t>(size_t(x) * y * 4, __func__);
  return ibuf;
}

ImBuf *IMB_allocFromBuffer(
    const uint8_t *byte_buffer, const float * /*float_buffer*/, unsigned w, unsigned h, unsigned)
{
  ImBuf *ibuf = IMB_allocImBuf(w, h, ImBufFlags::ByteData);
  if (byte_buffer) {
    memcpy(ibuf->byte_buffer.data, byte_buffer, size_t(w) * h * 4);
  }
  return ibuf;
}

void IMB_freeImBuf(ImBuf *ibuf)
{
  if (ibuf) {
    if (ibuf->byte_buffer.data) {
      MEM_delete_void(static_cast<void *>(ibuf->byte_buffer.data));
    }
    MEM_delete(ibuf);
  }
}

ImBuf *IMB_load_image_from_memory(
    const unsigned char *mem, size_t size, ImBufFlags, const char *, const char *, char *)
{
  uint8_t *rgba = nullptr;
  int w = 0, h = 0;
  if (!stk_codec || !stk_codec->decode || !stk_codec->decode(mem, size, &rgba, &w, &h)) {
    return nullptr;
  }
  ImBuf *ibuf = MEM_new<ImBuf>(__func__);
  ibuf->x = w;
  ibuf->y = h;
  ibuf->byte_buffer.data = rgba;
  return ibuf;
}

ImBuf *IMB_load_image_from_filepath(const char *filepath, ImBufFlags flags, char *)
{
  size_t size = 0;
  void *mem = BLI_file_read_binary_as_mem(filepath, 0, &size);
  if (!mem) {
    return nullptr;
  }
  ImBuf *ibuf = IMB_load_image_from_memory(
      static_cast<const unsigned char *>(mem), size, flags, filepath, filepath, nullptr);
  MEM_delete_void(mem);
  return ibuf;
}

bool IMB_test_image(const char *filepath)
{
  ImBuf *ibuf = IMB_load_image_from_filepath(filepath, ImBufFlags::ByteData);
  IMB_freeImBuf(ibuf);
  return ibuf != nullptr;
}

Vector<uint8_t> IMB_save_image_to_buffer(ImBuf *ibuf, ImBufFlags /*flags*/)
{
  Vector<uint8_t> bytes;
  if (stk_codec && stk_codec->encode_png) {
    stk_codec->encode_png(ibuf->byte_data(), ibuf->x, ibuf->y, bytes);
  }
  return bytes;
}

/** \} */

}  // namespace blender
