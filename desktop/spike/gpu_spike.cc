/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Phase 0 extraction spike: headless GHOST context -> GPU_init -> offscreen framebuffer.
 * Draws a filled rectangle (immediate mode), a smooth-colored triangle batch and
 * `BLF_draw("STK 你好")` (default font + CJK fallback stack, and Noto Sans CJK directly),
 * reads the pixels back, writes a PNG and optionally compares with a golden image.
 *
 *   stk-gpu-spike --backend vulkan|opengl --out out.png [--golden golden.png] [--update-golden]
 *   stk-gpu-spike --leak-selftest   (must fail: verifies the guardedalloc leak check)
 *
 * Exit codes: 0 ok, 1 check/golden mismatch, 2 setup failure; a guardedalloc leak aborts
 * at exit (MEM_enable_fail_on_memleak), so ctest fails on leaks too.
 */

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "MEM_guardedalloc.h"

#include "CLG_log.h"

#include "BLI_path_utils.hh"
#include "BLI_threads.h"

#include "GHOST_ISystem.hh"

#include "GPU_batch.hh"
#include "GPU_context.hh"
#include "GPU_framebuffer.hh"
#include "GPU_immediate.hh"
#include "GPU_immediate_util.hh"
#include "GPU_init_exit.hh"
#include "GPU_matrix.hh"
#include "GPU_platform.hh"
#include "GPU_state.hh"
#include "GPU_vertex_buffer.hh"

#include "BLF_api.hh"

#include "png_min.hh"

using namespace blender;
using stk::spike::Image;

static constexpr int W = 320, H = 160;
static const char *TEXT = "STK \xe4\xbd\xa0\xe5\xa5\xbd"; /* "STK 你好" */

/* Layout shared by the renderer and the golden checks (pixels, origin bottom-left). */
struct Box {
  int x0, y0, x1, y1;
};
static constexpr Box RECT = {16, 96, 112, 144};
static constexpr Box TRI = {136, 88, 216, 152};  /* Bounding box of the triangle. */
static constexpr Box TEXT_FALLBACK = {16, 20, 300, 76};
static constexpr float BG[3] = {0.08f, 0.09f, 0.10f};

static int fail(const char *msg)
{
  fprintf(stderr, "stk-gpu-spike: %s\n", msg);
  return 2;
}

static void draw_scene(int font_default, int font_cjk)
{
  GPU_clear_color(BG[0], BG[1], BG[2], 1.0f);
  GPU_matrix_push_projection();
  GPU_matrix_ortho_set(0.0f, float(W), 0.0f, float(H), -1.0f, 1.0f);
  GPU_matrix_push();
  GPU_matrix_identity_set();

  /* 1. Filled rectangle (immediate mode). */
  {
    GPUVertFormat *format = immVertexFormat();
    const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
    immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
    immUniformColor4f(0.90f, 0.35f, 0.10f, 1.0f);
    immRectf(pos, RECT.x0, RECT.y0, RECT.x1, RECT.y1);
    immUnbindProgram();
  }

  /* 2. Triangle batch with per-vertex colors. */
  {
    GPUVertFormat format = {0};
    const uint pos = GPU_vertformat_attr_add(&format, "pos", gpu::VertAttrType::SFLOAT_32_32_32);
    const uint col = GPU_vertformat_attr_add(
        &format, "color", gpu::VertAttrType::SFLOAT_32_32_32_32);
    gpu::VertBuf *vbo = GPU_vertbuf_create_with_format(format);
    GPU_vertbuf_data_alloc(*vbo, 3);
    const float p[3][3] = {{float(TRI.x0), float(TRI.y0), 0.0f},
                           {float(TRI.x1), float(TRI.y0), 0.0f},
                           {0.5f * (TRI.x0 + TRI.x1), float(TRI.y1), 0.0f}};
    const float c[3][4] = {{1, 0, 0, 1}, {0, 1, 0, 1}, {0, 0, 1, 1}};
    GPU_vertbuf_attr_fill(vbo, pos, p);
    GPU_vertbuf_attr_fill(vbo, col, c);
    gpu::Batch *batch = GPU_batch_create_ex(GPU_PRIM_TRIS, vbo, nullptr, GPU_BATCH_OWNS_VBO);
    GPU_batch_program_set_builtin(batch, GPU_SHADER_3D_SMOOTH_COLOR);
    GPU_batch_draw(batch);
    GPU_batch_discard(batch);
  }

  /* 3. Text: default UI font (Inter) with the fallback stack for CJK, then Noto CJK directly. */
  GPU_blend(GPU_BLEND_ALPHA);
  BLF_size(font_default, 28.0f);
  BLF_color4f(font_default, 1.0f, 1.0f, 1.0f, 1.0f);
  BLF_position(font_default, 20.0f, 52.0f, 0.0f);
  BLF_draw(font_default, TEXT, strlen(TEXT));

  BLF_size(font_cjk, 20.0f);
  BLF_color4f(font_cjk, 0.6f, 0.9f, 1.0f, 1.0f);
  BLF_position(font_cjk, 20.0f, 24.0f, 0.0f);
  BLF_draw(font_cjk, TEXT, strlen(TEXT));
  GPU_blend(GPU_BLEND_NONE);

  GPU_matrix_pop();
  GPU_matrix_pop_projection();
}

/* ------------------------------------------------------------------------------------------ */
/* Golden comparison: tolerant pixel compare plus structural checks. */

static bool is_ink(const uint8_t *p)
{
  const int d = std::abs(p[0] - int(BG[0] * 255 + 0.5f)) + std::abs(p[1] - int(BG[1] * 255 + 0.5f)) +
                std::abs(p[2] - int(BG[2] * 255 + 0.5f));
  return d > 96;
}

/** Box coordinates are bottom-left based; images are stored top row first. */
static const uint8_t *at(const Image &img, int x, int y)
{
  return img.px(x, img.height - 1 - y);
}

static int count_ink(const Image &img, const Box &b)
{
  int n = 0;
  for (int y = b.y0; y < b.y1; y++) {
    for (int x = b.x0; x < b.x1; x++) {
      n += is_ink(at(img, x, y));
    }
  }
  return n;
}

static bool check_structure(const Image &img, std::string &why)
{
  /* Rectangle interior is the flat fill color. */
  const uint8_t *r = at(img, (RECT.x0 + RECT.x1) / 2, (RECT.y0 + RECT.y1) / 2);
  if (std::abs(r[0] - 230) > 3 || std::abs(r[1] - 89) > 3 || std::abs(r[2] - 26) > 3) {
    why = "rectangle color wrong";
    return false;
  }
  /* Triangle: corners dominated by their vertex color, centroid mixed. */
  const uint8_t *tl = at(img, TRI.x0 + 6, TRI.y0 + 2), *tr = at(img, TRI.x1 - 6, TRI.y0 + 2);
  const uint8_t *tc = at(img, (TRI.x0 + TRI.x1) / 2, TRI.y0 + (TRI.y1 - TRI.y0) / 3);
  if (!(tl[0] > 180 && tr[1] > 180 && tc[0] > 40 && tc[1] > 40 && tc[2] > 40)) {
    why = "triangle colors wrong";
    return false;
  }
  if (is_ink(at(img, TRI.x0 + 2, TRI.y1 - 2))) {
    why = "triangle covers its bounding-box corner";
    return false;
  }
  /* Latin and CJK glyph regions contain ink: "STK" left, "你好" right of the space. */
  const int latin_w = 60;
  const Box latin = {20, 44, 20 + latin_w, 76}, cjk = {20 + latin_w + 8, 44, 170, 76};
  const Box cjk_small = {70, 18, 140, 44};
  const int n_latin = count_ink(img, latin), n_cjk = count_ink(img, cjk),
            n_cjk_small = count_ink(img, cjk_small);
  printf("ink: latin=%d cjk=%d cjk(noto)=%d\n", n_latin, n_cjk, n_cjk_small);
  if (n_latin < 60 || n_cjk < 120 || n_cjk_small < 80) {
    why = "text regions missing ink (CJK fallback or font load failed)";
    return false;
  }
  return true;
}

static bool compare_golden(const Image &img, const std::string &golden_path, std::string &why)
{
  Image golden;
  if (!stk::spike::png_read(golden_path, golden, why)) {
    return false;
  }
  if (golden.width != img.width || golden.height != img.height) {
    why = "golden size differs";
    return false;
  }
  /* Tolerance: anti-aliasing and glyph rasterization differ slightly between drivers. */
  int bad = 0;
  for (size_t i = 0; i < img.rgba.size(); i += 4) {
    int d = 0;
    for (int c = 0; c < 3; c++) {
      d = std::max(d, std::abs(int(img.rgba[i + c]) - int(golden.rgba[i + c])));
    }
    bad += d > 40;
  }
  const double frac = double(bad) / (img.width * img.height);
  printf("golden: %d / %d pixels differ by > 40 (%.3f%%)\n", bad, img.width * img.height, frac * 100);
  if (frac > 0.01) {
    why = "too many pixels differ from golden";
    return false;
  }
  return true;
}

/* ------------------------------------------------------------------------------------------ */

int main(int argc, char **argv)
{
  std::string backend = "vulkan", out = "stk-gpu-spike.png", golden;
  bool update_golden = false;
  for (int i = 1; i < argc; i++) {
    const std::string a = argv[i];
    if (a == "--backend" && i + 1 < argc) {
      backend = argv[++i];
    }
    else if (a == "--out" && i + 1 < argc) {
      out = argv[++i];
    }
    else if (a == "--golden" && i + 1 < argc) {
      golden = argv[++i];
    }
    else if (a == "--update-golden") {
      update_golden = true;
    }
    else if (a == "--leak-selftest") {
      /* Proves the leak check is live: leak one block, the detector must fail the process. */
      MEM_use_guarded_allocator();
      MEM_init_memleak_detection();
      MEM_enable_fail_on_memleak();
      MEM_new_array_uninitialized<char>(64, "stk-gpu-spike leak self-test");
      return 0;
    }
    else {
      fprintf(stderr, "usage: %s --backend vulkan|opengl --out PNG [--golden PNG] [--update-golden]\n", argv[0]);
      return 2;
    }
  }

  /* Guarded allocator with leak detection, as Blender does at startup. */
  MEM_use_guarded_allocator();
  MEM_init_memleak_detection();
  MEM_enable_fail_on_memleak();
  CLG_init();
  BLI_threadapi_init();

  GPUBackendType type;
  GHOST_TDrawingContextType ctx_type;
  if (backend == "vulkan") {
    type = GPU_BACKEND_VULKAN;
    ctx_type = GHOST_kDrawingContextTypeVulkan;
  }
  else if (backend == "opengl") {
    type = GPU_BACKEND_OPENGL;
    ctx_type = GHOST_kDrawingContextTypeOpenGL;
  }
  else {
    return fail("unknown backend");
  }

  if (GHOST_ISystem::createSystemBackground() != GHOST_kSuccess) {
    return fail("GHOST_ISystem::createSystemBackground failed");
  }
  GHOST_ISystem *system = GHOST_ISystem::getSystem();
  GPU_backend_ghost_system_set(system);
  GPU_backend_type_selection_set(type);
  if (!GPU_backend_supported()) {
    return fail("GPU backend not supported on this system");
  }

  GHOST_GPUSettings settings = {0};
  settings.context_type = ctx_type;
  settings.preferred_device = GPU_backend_preferred_device_get();
  GHOST_IContext *ghost_ctx = system->createOffscreenContext(settings);
  if (!ghost_ctx) {
    return fail("createOffscreenContext failed");
  }
  ghost_ctx->activateDrawingContext();
  GPUContext *gpu_ctx = GPU_context_create(nullptr, ghost_ctx);
  GPU_context_active_set(gpu_ctx);
  GPU_init();
  const char *ghost_backend = GHOST_ISystem::getSystemBackend();
  printf("backend: %s, GHOST system: %s\n", GPU_backend_get_name(), ghost_backend ? ghost_backend : "headless");
  printf("device: %s | %s | %s\n", GPU_platform_vendor(), GPU_platform_renderer(), GPU_platform_version());

  BLF_init();
  const int font_default = BLF_load_default(false);
  BLF_load_font_stack();
  const char *datafiles = getenv("STK_BLENDER_DATAFILES");
  const std::string cjk_path = std::string(datafiles ? datafiles : STK_BLENDER_DATAFILES_DIR) +
                               "/fonts/Noto Sans CJK Regular.woff2";
  const int font_cjk = BLF_load(cjk_path.c_str());
  if (font_default < 0 || font_cjk < 0) {
    return fail("font loading failed");
  }

  GPU_render_begin();
  GPU_context_begin_frame(gpu_ctx);
  char err[256] = "";
  GPUOffScreen *ofs = GPU_offscreen_create(
      W, H, false, gpu::TextureFormat::UNORM_8_8_8_8, GPU_TEXTURE_USAGE_HOST_READ, false, err);
  if (!ofs) {
    return fail(err);
  }
  GPU_offscreen_bind(ofs, true);
  draw_scene(font_default, font_cjk);
  Image img;
  img.width = W;
  img.height = H;
  img.rgba.resize(size_t(W) * H * 4);
  std::vector<uint8_t> bottom_up(img.rgba.size());
  GPU_finish();
  GPU_offscreen_read_color(ofs, GPU_DATA_UBYTE, bottom_up.data());
  GPU_offscreen_unbind(ofs, true);
  GPU_offscreen_free(ofs);
  GPU_context_end_frame(gpu_ctx);
  GPU_render_end();
  for (int y = 0; y < H; y++) {
    memcpy(&img.rgba[size_t(H - 1 - y) * W * 4], &bottom_up[size_t(y) * W * 4], size_t(W) * 4);
  }

  /* Shutdown in Blender's order: fonts, GPU module, context, GHOST. */
  BLF_exit();
  GPU_exit();
  GPU_context_discard(gpu_ctx);
  system->disposeContext(ghost_ctx);
  GHOST_ISystem::disposeSystem();
  CLG_exit();

  int rc = 0;
  if (!stk::spike::png_write(out, img)) {
    return fail("PNG write failed");
  }
  printf("wrote %s\n", out.c_str());
  std::string why;
  if (!check_structure(img, why)) {
    fprintf(stderr, "stk-gpu-spike: structure check FAILED: %s\n", why.c_str());
    rc = 1;
  }
  if (!golden.empty()) {
    if (update_golden) {
      if (!stk::spike::png_write(golden, img)) {
        return fail("golden write failed");
      }
      printf("updated golden %s\n", golden.c_str());
    }
    else if (!compare_golden(img, golden, why)) {
      fprintf(stderr, "stk-gpu-spike: golden check FAILED: %s\n", why.c_str());
      rc = 1;
    }
  }
  const unsigned int blocks = MEM_get_memory_blocks_in_use();
  printf("guardedalloc: %u blocks in use at exit%s\n", blocks, blocks ? " (leak report follows)" : "");
  printf("%s\n", rc == 0 ? "PASS" : "FAIL");
  return rc;
}
