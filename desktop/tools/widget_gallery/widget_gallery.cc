/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * STK widget gallery: every stk_ui widget, the muFerro preset form and the overlays (dropdown
 * popup, tooltip, toast, modal, IME preedit) painted by ui_gpu on WP1's stk_gfx / stk_wm.
 *
 *   widget_gallery --headless --export out.png [--lang zh|en] [--scale S] [--backend B]
 *                  [--screen gallery|widgets|lists|form|overlays] [--golden g.png [--update-golden]]
 *   widget_gallery [--lang zh|en] [--scale S] [--backend B] [--screen ...] [--exit-after-frames N]
 *                  (interactive window for the manual IME matrix: GNOME+ibus, KDE+fcitx5, macOS
 *                  Pinyin inline, X11 commit-only)
 *
 * B: auto, opengl, vulkan or metal (default: $STK_GPU_BACKEND, else the platform default).
 * Headless exit codes: 0 ok, 1 check or golden mismatch, 2 setup failure. The golden compare is
 * tolerant (anti-aliasing and glyph rasterization differ between drivers); structural checks
 * sample theme colours at resolved widget rects.
 */
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

#include "GPU_framebuffer.hh"

#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/wm/window.hh"

#include "gallery_wm.hh"
#include "screens.hh"

using namespace stk::ui;
namespace g = stk::ui::gallery;
namespace gfx = stk::gfx;

namespace {

struct Args {
  bool headless = false;
  std::string out;
  std::string lang = "zh";
  float scale = 1.0f;
  std::string backend;
  long exit_after_frames = 0;
  std::string golden;
  bool update_golden = false;
  g::Screen screen = g::Screen::Gallery;
};

int fail(const std::string &msg)
{
  std::fprintf(stderr, "widget_gallery: %s\n", msg.c_str());
  return 2;
}

const uint8_t *px(const gfx::Image &img, float x, float y)
{
  const int ix = std::clamp(int(x), 0, img.width - 1), iy = std::clamp(int(y), 0, img.height - 1);
  return img.px(ix, iy);
}

bool near_color(const uint8_t *p, Color c, int tol)
{
  return std::abs(p[0] - c.r) <= tol && std::abs(p[1] - c.g) <= tol && std::abs(p[2] - c.b) <= tol;
}

int count_ink(const gfx::Image &img, const Rect &r, Color bg)
{
  int n = 0;
  for (int y = int(r.y); y < int(r.y1()); y++) {
    for (int x = int(r.x); x < int(r.x1()); x++) {
      const uint8_t *p = px(img, float(x), float(y));
      n += (std::abs(p[0] - bg.r) + std::abs(p[1] - bg.g) + std::abs(p[2] - bg.b)) > 120;
    }
  }
  return n;
}

/** Samples theme colours and text ink at resolved widget rects. */
bool check_structure(const Context &ctx, const gfx::Image &img, std::string &why)
{
  const Theme &th = ctx.theme();
  const Style &st = ctx.style();
  bool ok = true;
  /* Region widgets sit under the modal's dimming layer. */
  bool modal = false;
  for (const auto &b : ctx.blocks()) {
    modal |= b->kind() == Block::Kind::Modal;
  }
  auto expect = [&](const char *what, const uint8_t *p, Color c, int tol) {
    if (modal) {
      c = c.blend(Color{0, 0, 0, 255}, th.modal_dim.a / 255.0f);
    }
    if (!near_color(p, c, tol)) {
      char buf[160];
      std::snprintf(buf, sizeof(buf), "%s: got #%02x%02x%02x, want %s; ", what, p[0], p[1], p[2], c.to_hex().c_str());
      why += buf;
      ok = false;
    }
  };
  if (const Widget *w = ctx.find("run")) {
    expect("button inner", px(img, w->rect.x + 2 * st.pixel + 2, w->rect.cy()), th.regular.inner, 10);
  }
  if (const Widget *w = ctx.find("grid")) {
    /* Upper-left quarter of the check box square: blue fill, away from the check mark. */
    const float delta = std::floor((w->rect.h - 2 * st.pixel) / 6.0f);
    const float side = w->rect.h - 2 * delta;
    expect("checked checkbox", px(img, w->rect.x + 0.25f * side, w->rect.y + delta + 0.22f * side),
           th.option.inner_sel, 16);
  }
  if (const Widget *w = ctx.find("disabled")) {
    /* Disabled: half-alpha inner over the region background. */
    expect("disabled button", px(img, w->rect.x + 2 * st.pixel + 2, w->rect.cy()),
           th.region_back.blend(th.regular.inner, 0.5f), 12);
  }
  for (const auto &b : ctx.blocks()) {
    for (const Widget &w : b->widgets()) {
      if (w.type == WidgetType::Progress) {
        expect("progress fill", px(img, w.rect.x + 3 * st.pixel, w.rect.y + 3 * st.pixel), th.progress.item, 12);
      }
      if (w.type == WidgetType::Label && w.key.find("widgets/") == 0 && w.text == ctx.tr("gallery.title")) {
        if (count_ink(img, w.rect, th.region_back) < int(20 * st.scale * st.scale)) {
          why += "title label has no text ink; ";
          ok = false;
        }
      }
      if (w.type == WidgetType::Paragraph && b->kind() == Block::Kind::Region && w.key.find("widgets/") == 0) {
        if (count_ink(img, w.rect, th.region_back) < int(400 * st.scale * st.scale)) {
          why += "paragraph (CJK) has too little ink; ";
          ok = false;
        }
      }
    }
  }
  if (const Widget *w = ctx.find("colormap")) {
    /* viridis swatch: dark purple at its left end. */
    expect("viridis(0)", px(img, w->rect.x + st.text_margin + 1, w->rect.cy()), Color::rgb(0x440154), 24);
  }
  return ok;
}

bool compare_golden(const gfx::Image &img, const std::string &path, std::string &why)
{
  gfx::Image golden;
  if (!gfx::png_read(path, golden, why)) {
    return false;
  }
  if (golden.width != img.width || golden.height != img.height) {
    why = "golden size differs";
    return false;
  }
  int bad = 0;
  for (size_t i = 0; i < img.rgba.size(); i += 4) {
    int d = 0;
    for (int c = 0; c < 3; c++) {
      d = std::max(d, std::abs(int(img.rgba[i + c]) - int(golden.rgba[i + c])));
    }
    bad += d > 48;
  }
  const double frac = double(bad) / (double(img.width) * img.height);
  std::printf("golden: %d / %d pixels differ by > 48 (%.3f%%)\n", bad, img.width * img.height, frac * 100);
  if (frac > 0.02) {
    why = "too many pixels differ from the golden";
    return false;
  }
  return true;
}

g::Screen parse_screen(const std::string &s)
{
  if (s == "widgets") {
    return g::Screen::Widgets;
  }
  if (s == "lists") {
    return g::Screen::Lists;
  }
  if (s == "form") {
    return g::Screen::Form;
  }
  if (s == "overlays") {
    return g::Screen::Overlays;
  }
  return g::Screen::Gallery;
}

std::string env_or(const char *name, const char *fallback)
{
  const char *v = std::getenv(name);
  return v && *v ? v : fallback;
}

/** Catalogs and the preset form (both modes). */
void init_state(g::State &state, const std::string &lang)
{
  std::string err;
  if (!g::init_state(state, env_or("STK_DESKTOP_DIR", STK_DESKTOP_DIR), lang, &err)) {
    std::fprintf(stderr, "widget_gallery: i18n catalogs: %s\n", err.c_str());
  }
  if (!g::load_form(state, env_or("STK_REPO_ROOT", STK_REPO_ROOT), &err)) {
    std::fprintf(stderr, "widget_gallery: form: %s\n", err.c_str());
  }
}

int run_headless(const Args &a, gfx::Backend backend, const std::string &lang)
{
  std::string err;
  GHOST_ISystem *system = gfx::create_background_system(err);
  if (!system) {
    return fail(err);
  }
  int rc = 0;
  {
    gfx::GpuOptions opts;
    opts.backend = backend;
    std::unique_ptr<gfx::Gpu> gpu = gfx::Gpu::create(*system, opts, err);
    if (!gpu) {
      gfx::dispose_system();
      return fail(err);
    }
    gfx::set_ui_scale(a.scale);
    g::State state;
    init_state(state, lang);
    state.image_texture = g::create_demo_texture(state.image_w, state.image_h);
    {
      gpu::BlfTextMeasurer measurer(gpu->fonts());
      MemoryClipboard clipboard;
      ContextConfig cfg;
      cfg.measurer = &measurer;
      cfg.clipboard = &clipboard;
      cfg.catalog = &state.catalog;
      Context ctx(cfg);
      ctx.set_scale(1.0f, a.scale);
      gpu::GpuPainter painter(gpu->fonts());
      painter.set_pixel_size(ctx.style().pixel);

      const Vec2 base = g::screen_size(a.screen);
      const Vec2 win{std::round(base.x * a.scale), std::round(base.y * a.scale)};
      if (a.screen == g::Screen::Gallery || a.screen == g::Screen::Overlays) {
        g::build_staged(ctx, state, a.screen, win, 100.0);
      }
      else {
        g::build(ctx, state, a.screen, win, 100.0);
      }
      gfx::Image img;
      const bool ok = gfx::render_offscreen(
          int(win.x), int(win.y),
          [&]() {
            blender::GPU_clear_color(0.0f, 0.0f, 0.0f, 1.0f);
            painter.paint(ctx.draw_list(), win);
          },
          img, err);
      if (!ok) {
        rc = fail("render failed: " + err);
      }
      else {
        /* A window ignores the framebuffer alpha; keep exported PNGs opaque the same way. */
        for (size_t i = 3; i < img.rgba.size(); i += 4) {
          img.rgba[i] = 255;
        }
        std::printf("rendered %d x %d (%s, lang %s, scale %.2f, %zu draw commands)\n", img.width, img.height,
                    gpu->backend_name(), lang.c_str(), a.scale, ctx.draw_list().size());
        if (!a.out.empty()) {
          if (!gfx::png_write(a.out, img)) {
            rc = fail("cannot write " + a.out);
          }
          else {
            std::printf("wrote %s\n", a.out.c_str());
          }
        }
        std::string why;
        if (a.screen == g::Screen::Gallery && !check_structure(ctx, img, why)) {
          std::fprintf(stderr, "widget_gallery: structure check FAILED: %s\n", why.c_str());
          rc = 1;
        }
        if (!a.golden.empty()) {
          if (a.update_golden) {
            if (!gfx::png_write(a.golden, img)) {
              rc = fail("cannot write " + a.golden);
            }
            else {
              std::printf("updated golden %s\n", a.golden.c_str());
            }
          }
          else if (!compare_golden(img, a.golden, why)) {
            std::fprintf(stderr, "widget_gallery: golden check FAILED: %s\n", why.c_str());
            rc = 1;
          }
        }
      }
    }
    g::free_texture(state.image_texture);
  }
  gfx::dispose_system();
  return rc;
}

int run_gui(const Args &a, gfx::Backend backend, const std::string &lang)
{
  stk::wm::WmOptions opts;
  opts.gpu.backend = backend;
  opts.user_scale = a.scale;
  opts.window.title = "STK widget gallery";
  const Vec2 base = g::screen_size(a.screen);
  opts.window.width = int(base.x);
  opts.window.height = int(base.y);
  std::string err;
  std::unique_ptr<stk::wm::WindowManager> wm = stk::wm::WindowManager::create(opts, err);
  if (!wm) {
    return fail(err);
  }
  g::State state;
  init_state(state, lang);
  state.image_texture = g::create_demo_texture(state.image_w, state.image_h);
  g::WmClipboard clipboard(*wm);
  ContextConfig cfg;
  cfg.clipboard = &clipboard;
  cfg.catalog = &state.catalog;
#ifdef __APPLE__
  cfg.mac_shortcuts = true;
#endif
  const g::Screen screen = a.screen;
  g::UiRegion &region = wm->main_window()->screen().add_area("gallery").emplace_region<g::UiRegion>(
      "gallery", *wm, cfg, [&state, screen](Context &ctx, Vec2 size, double now) {
        g::build(ctx, state, screen, size, now);
      });
  long frames = 0;
  if (a.exit_after_frames > 0) {
    /* Smoke test: keep presenting frames, then quit cleanly. */
    region.after_draw = [&]() {
      if (++frames >= a.exit_after_frames) {
        wm->quit(0);
      }
      else {
        region.tag_redraw();
      }
    };
  }
  std::printf("widget_gallery: %s, %s, UI scale %.3g\n", wm->system_backend(), wm->gpu().backend_name(),
              wm->main_window()->ui_scale());
  const int rc = wm->run();
  if (a.exit_after_frames > 0) {
    std::printf("widget_gallery: presented %ld frames\n", frames);
  }
  g::free_texture(state.image_texture);
  return rc;
}

}  // namespace

int main(int argc, char **argv)
{
  Args a;
  for (int i = 1; i < argc; i++) {
    const std::string s = argv[i];
    auto next = [&]() -> std::string { return i + 1 < argc ? argv[++i] : std::string(); };
    if (s == "--headless") {
      a.headless = true;
    }
    else if (s == "--export") {
      a.out = next();
    }
    else if (s == "--lang") {
      a.lang = next();
    }
    else if (s == "--scale") {
      a.scale = std::strtof(next().c_str(), nullptr);
    }
    else if (s == "--backend" || s == "--gpu-backend") {
      a.backend = next();
    }
    else if (s == "--golden") {
      a.golden = next();
    }
    else if (s == "--update-golden") {
      a.update_golden = true;
    }
    else if (s == "--exit-after-frames") {
      a.exit_after_frames = std::strtol(next().c_str(), nullptr, 10);
    }
    else if (s == "--screen") {
      a.screen = parse_screen(next());
    }
    else {
      std::fprintf(stderr,
                   "usage: %s [--headless --export PNG] [--lang zh|en] [--scale S]\n"
                   "          [--backend auto|opengl|vulkan|metal] [--screen gallery|widgets|lists|form|overlays]\n"
                   "          [--golden PNG [--update-golden]]\n",
                   argv[0]);
      return 2;
    }
  }
  if (!(a.scale > 0.25f && a.scale <= 4.0f)) {
    return fail("--scale must be in (0.25, 4]");
  }
  const std::string lang = (a.lang == "en") ? "en" : "zh_CN";
  gfx::Runtime runtime;
  gfx::Backend backend;
  std::string err;
  if (!gfx::resolve_backend(a.backend, backend, err)) {
    return fail(err);
  }
  const int rc = a.headless ? run_headless(a, backend, lang) : run_gui(a, backend, lang);
  /* Leaks are reported (and fail the process) by the Runtime at exit. */
  std::printf("%s\n", rc == 0 ? "PASS" : "FAIL");
  return rc;
}
