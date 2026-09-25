/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Live-window test of the application shell (run through run_with_display.py: private Xvfb or
 * headless weston on unix sockets). Opens the default screen, then walks timer-driven steps:
 *   first frame -> pixels read back (bars, header, viewer, splitter gap) -> a splitter dragged with
 *   synthesized events -> window resize (minimum sizes hold) -> UI scale change (header height) ->
 *   client-side decorations (with --expect-csd: GNOME on Wayland) -> close (layout saved and
 *   reloadable) -> guardedalloc leak check.
 *
 *   stk-app-smoke [--gpu-backend B] --layout-out FILE [--expect-csd]
 * Exit codes: 0 pass, 1 failure, 77 skipped (no display).
 */

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>

#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/gpu.hh"
#include "stk/wm/csd.hh"
#include "stk/wm/layout_store.hh"
#include "stk/wm/window.hh"

using namespace stk;

namespace {

int g_failures = 0;

void check(const bool ok, const char *what, const std::string &detail = {})
{
  printf("%s %s%s%s\n", ok ? "ok  " : "FAIL", what, detail.empty() ? "" : ": ", detail.c_str());
  if (!ok) {
    g_failures++;
  }
  fflush(stdout);
}

bool near(const uint8_t *px, const ui::Color c, const int tol = 4)
{
  return std::abs(px[0] - c.r) <= tol && std::abs(px[1] - c.g) <= tol && std::abs(px[2] - c.b) <= tol;
}

std::string hex(const uint8_t *px)
{
  char buf[16];
  snprintf(buf, sizeof(buf), "#%02x%02x%02x", px[0], px[1], px[2]);
  return buf;
}

std::string g_screenshot;

int run(const gfx::Backend backend, const std::string &layout_out, const bool expect_csd)
{
  app::ShellOptions so;
  so.language = "en";
  app::AppShell shell(so);
  check(shell.catalogs_loaded(), "catalogs", shell.options().i18n_dir);

  wm::WmOptions opts;
  opts.gpu.backend = backend;
  /* weston's kiosk shell drops clients larger than its 1280x800 output. */
  opts.window = {"STK app smoke", 1100, 700, false};
  std::string err;
  std::unique_ptr<wm::WindowManager> wm = wm::WindowManager::create(opts, err);
  if (!wm) {
    printf("SKIP: %s\n", err.c_str());
    return err.find("no display") != std::string::npos ? 77 : 1;
  }
  printf("system %s, GPU %s, CSD %s\n", wm->system_backend(), wm->gpu().backend_name(),
         wm->csd_active() ? "on" : "off");
  wm::Window *win = wm->main_window();
  wm::Screen &screen = win->screen();
  shell.install(screen, win);
  shell.build_default_layout(screen);
  shell.layout_path = core::path_from_utf8(layout_out);
  bool saved = false;
  int resizes = 0;
  win->on_event = [&](const wm::Event &e) {
    if (e.type == wm::EventType::Close) {
      saved = shell.save(screen, win, shell.layout_path);
    }
    if (e.type == wm::EventType::Resize) {
      resizes++;
    }
    return false;
  };
  auto area = [&](const char *id) { return dynamic_cast<app::EditorArea *>(screen.find_area(id)); };
  auto dctx = [&]() {
    wm::DrawContext c;
    c.window = win;
    c.ui_scale = win->ui_scale();
    c.fonts = &wm->gpu().fonts();
    c.rect = {0, 0, win->width(), win->height()};
    return c;
  };
  uint64_t t_event = wm->time_ms();
  auto send = [&](wm::EventType type, int x, int y) {
    wm::Event e;
    e.type = type;
    e.window = win;
    e.x = x;
    e.y = y;
    e.button = wm::MouseButton::Left;
    e.time_ms = (t_event += 20);
    screen.dispatch(e, dctx());
  };

  int step = 0;
  uint64_t step_start = wm->time_ms(), frames_at_step = 0;
  int drag_x = 0, drag_w0 = 0;
  auto next = [&] {
    step++;
    step_start = wm->time_ms();
    frames_at_step = win->frames_drawn();
  };
  auto elapsed = [&] { return wm->time_ms() - step_start; };
  auto new_frame = [&] { return win->frames_drawn() > frames_at_step; };

  wm->add_timer(30, 30, [&] {
    switch (step) {
      case 0:
        if (win->frames_drawn() > 0) {
          check(screen.areas().size() == 4, "default layout", std::to_string(screen.areas().size()) + " areas");
          next();
        }
        else if (elapsed() > 10000) {
          check(false, "first frame", "timeout");
          wm->quit(1);
        }
        break;
      case 1: {
        gfx::Image img;
        const bool ok = win->read_pixels(img, err);
        if (ok && !g_screenshot.empty()) {
          gfx::png_write(g_screenshot, img);
        }
        check(ok && img.width == win->width(), "read_pixels", err);
        if (ok) {
          const wm::Area *top = screen.global_area(wm::RegionAlign::Top);
          const wm::Rect jobs_h = area("a1")->find_region("header")->rect();
          const wm::Rect viewer = area("a2")->find_region("main")->rect();
          const wm::Splitter &s = screen.splitters().front();
          const uint8_t *p_top = img.px_bl(top->rect().xmax - 3, top->rect().ymin + 2);
          const uint8_t *p_head = img.px_bl(jobs_h.xmin + jobs_h.width() / 2, jobs_h.ymin + 1);
          const uint8_t *p_view = img.px_bl(viewer.xmax - 8, viewer.ymin + 8);
          const uint8_t *p_gap = img.px_bl(s.rect.xmin, s.rect.ymin + s.rect.height() / 2);
          check(near(p_top, ui::Color::rgb(0x181818)), "top bar color", hex(p_top));
          check(near(p_head, ui::Color::rgb(0x303030)), "area header color", hex(p_head));
          check(near(p_view, ui::Color::rgb(0x3d3d3d)), "viewer background", hex(p_view));
          check(near(p_gap, ui::Color::rgb(0x161616)), "splitter gap color", hex(p_gap));
        }
        /* Drag the Jobs | Viewer splitter 80 px to the right with synthesized events. */
        const wm::Splitter *s = nullptr;
        for (const wm::Splitter &sp : screen.splitters()) {
          if (sp.dir == wm::SplitDir::Horizontal && sp.node->children[size_t(sp.index)]->area.get() == area("a1")) {
            s = &sp;
          }
        }
        check(s != nullptr, "jobs | viewer splitter");
        if (!s) {
          wm->quit(1);
          break;
        }
        drag_x = (s->rect.xmin + s->rect.xmax) / 2;
        drag_w0 = area("a1")->rect().width();
        const int y = (s->rect.ymin + s->rect.ymax) / 2;
        send(wm::EventType::MouseMove, drag_x, y);
        send(wm::EventType::MouseDown, drag_x, y);
        check(screen.capture() == wm::Screen::Capture::Splitter, "splitter captures the pointer",
              std::to_string(int(screen.capture())));
        for (int i = 1; i <= 4; i++) {
          send(wm::EventType::MouseMove, drag_x + 20 * i, y);
        }
        send(wm::EventType::MouseUp, drag_x + 80, y);
        printf("  jobs width after the drag: %d\n", area("a1")->rect().width());
        next();
        break;
      }
      case 2:
        if (new_frame()) {
          check(area("a1")->rect().width() == drag_w0 + 80, "splitter drag",
                std::to_string(drag_w0) + " -> " + std::to_string(area("a1")->rect().width()));
          gfx::Image img;
          if (win->read_pixels(img, err)) {
            const wm::Rect m = area("a1")->find_region("main")->rect();
            /* The old bar position is now inside the Jobs area. */
            const uint8_t *p = img.px_bl(drag_x, m.ymin + 4);
            check(near(p, ui::Color::rgb(0x282828)), "splitter moved on screen", hex(p));
          }
          win->set_client_size(900, 600);
          next();
        }
        else if (elapsed() > 5000) {
          check(false, "redraw after splitter drag", "timeout");
          next();
        }
        break;
      case 3: /* Resize (compositors may refuse; informative, but minimum sizes must hold). */
        if ((resizes > 0 && new_frame()) || elapsed() > 1500) {
          if (resizes == 0) {
            printf("note: resize request not honored by the server\n");
          }
          const float s = win->ui_scale();
          bool ok = true;
          for (const wm::Area *a : screen.areas()) {
            ok &= a->rect().width() >= a->min_width(s) && a->rect().height() >= a->min_height(s) &&
                  a->rect().xmax <= win->width();
          }
          check(ok, "areas keep their minimum size", std::to_string(win->width()) + "x" + std::to_string(win->height()));
          shell.set_ui_scale(1.25f);
          next();
        }
        break;
      case 4:
        if (new_frame()) {
          const int want = wm::ui_bar_height_px(win->ui_scale());
          const int got = area("a2")->find_region("header")->rect().height();
          check(std::fabs(win->ui_scale() - 1.25f * win->dpi_factor()) < 1e-3f && got == want,
                "UI scale 1.25 applied", std::to_string(got) + " px header");
          shell.set_ui_scale(1.0f);
          next();
        }
        else if (elapsed() > 5000) {
          check(false, "redraw after UI scale change", "timeout");
          next();
        }
        break;
      case 5: {
        const bool csd = wm->csd_active();
        if (expect_csd) {
          const wm::CsdLayout l = wm::csd_layout(*win);
          /* The close button is part of every GNOME button layout. */
          bool drawn = false;
          if (screen.ui()) {
            for (const auto &b : screen.ui()->blocks()) {
              for (const ui::Widget &w : b->widgets()) {
                drawn |= w.key.find("/csd_") != std::string::npos;
              }
            }
          }
          check(csd && !l.buttons.empty() && drawn, "client-side decorations drawn",
                std::to_string(l.buttons.size()) + " button(s)");
          /* GHOST asks for the decoration layout on compositor configures after the first one
           * (on GNOME: activation, resize, state changes). Maximize to get one here. */
          printf("  layout callbacks before maximize: %llu\n", (unsigned long long)wm::csd_layout_calls());
          win->set_maximized(true);
        }
        else {
          printf("note: client-side decorations %s\n", csd ? "on" : "off (server-side or X11)");
        }
        next();
        break;
      }
      case 6:
        if (!expect_csd || (wm::csd_layout_calls() > 0 && new_frame()) || elapsed() > 3000) {
          if (expect_csd) {
            check(wm::csd_layout_calls() > 0, "GHOST decoration layout callback",
                  std::to_string(wm::csd_layout_calls()) + " call(s), maximized " +
                      (win->maximized() ? "yes" : "no"));
            win->set_maximized(false);
          }
          win->request_close();
          next();
        }
        break;
      default:
        if (elapsed() > 5000) {
          check(false, "close", "window did not close");
          wm->quit(1);
        }
        break;
    }
  });
  wm->add_timer(60000, 0, [&] {
    check(false, "overall timeout");
    wm->quit(1);
  });
  const int rc = wm->run();
  check(wm->windows().empty(), "window closed");
  check(saved, "layout saved on close", layout_out);
  wm.reset();
  if (saved) {
    wm::LayoutFile f;
    std::string e;
    const bool ok = wm::load_layout_file(core::path_from_utf8(layout_out), f, &e) == wm::LayoutLoad::Ok;
    check(ok && f.language == "en" && f.window.width > 0, "saved layout reloads", e);
  }
  return (rc != 0 || g_failures) ? 1 : 0;
}

}  // namespace

int main(int argc, char **argv)
{
  std::string backend_arg, layout_out;
  bool expect_csd = false;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--gpu-backend") && i + 1 < argc) {
      backend_arg = argv[++i];
    }
    else if (!strcmp(argv[i], "--layout-out") && i + 1 < argc) {
      layout_out = argv[++i];
    }
    else if (!strcmp(argv[i], "--screenshot") && i + 1 < argc) {
      g_screenshot = argv[++i];
    }
    else if (!strcmp(argv[i], "--expect-csd")) {
      expect_csd = true;
    }
    else {
      fprintf(stderr, "usage: %s [--gpu-backend B] --layout-out FILE [--expect-csd] [--screenshot PNG]\n", argv[0]);
      return 2;
    }
  }
  if (layout_out.empty()) {
    fprintf(stderr, "--layout-out is required\n");
    return 2;
  }
  std::error_code ec;
  std::filesystem::remove(core::path_from_utf8(layout_out), ec);
  gfx::Backend backend;
  std::string err;
  if (!gfx::resolve_backend(backend_arg, backend, err)) {
    fprintf(stderr, "%s\n", err.c_str());
    return 2;
  }
  int rc;
  {
    gfx::Runtime runtime;
    rc = run(backend, layout_out, expect_csd);
  }
  if (rc == 77) {
    return rc;
  }
  const unsigned blocks = gfx::Runtime::memory_blocks_in_use();
  check(blocks == 0, "no guardedalloc leaks", std::to_string(blocks) + " block(s)");
  printf("%s\n", (rc == 0 && g_failures == 0) ? "PASS" : "FAIL");
  return (rc == 0 && g_failures == 0) ? 0 : 1;
}
