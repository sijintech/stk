/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Live-window smoke test for stk_wm (needs an X11 or Wayland server; run through
 * run_with_display.py, which starts Xvfb or a headless weston on private unix sockets).
 *
 * Opens a window with the sample screen and walks a scripted sequence driven by timers:
 *   first frame -> window pixels read back (header / region colors) -> client resize request ->
 *   user scale change (DpiChange + redraw) -> cursor shapes -> clipboard round trip ->
 *   request_close (Close event, window destroyed, loop quits) -> guardedalloc leak check.
 *
 * Exit codes: 0 pass, 1 failure, 77 skipped (no display).
 *   stk-wm-smoke [--gpu-backend B] [--leak-selftest]
 */

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "MEM_guardedalloc.h"

#include "stk/gfx/gpu.hh"
#include "stk/wm/window.hh"

#include "sample_layout.hh"
#include "sample_screen.hh"

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

bool near_color(const uint8_t *px, const float rgba[4], const int tol = 3)
{
  for (int c = 0; c < 3; c++) {
    if (std::abs(int(px[c]) - int(std::lround(rgba[c] * 255.0f))) > tol) {
      return false;
    }
  }
  return true;
}

struct Log {
  int resize = 0, expose = 0, dpi = 0, close = 0, focus = 0;
  float last_scale = 0.0f;
};

int run(const gfx::Backend backend)
{
  wm::WmOptions opts;
  opts.gpu.backend = backend;
  opts.window = {"STK smoke", 400, 300, false};
  std::string err;
  std::unique_ptr<wm::WindowManager> wm = wm::WindowManager::create(opts, err);
  if (!wm) {
    printf("SKIP: %s\n", err.c_str());
    return err.find("no display") != std::string::npos ? 77 : 1;
  }
  printf("system %s, GPU %s (%s)\n", wm->system_backend(), wm->gpu().backend_name(),
         wm->gpu().device_info().c_str());

  wm::Window *win = wm->main_window();
  check(win != nullptr, "main window", err);
  if (!win) {
    return 1;
  }
  app::build_sample_screen(win->screen(), wm.get());
  check(win->width() > 0 && win->height() > 0, "framebuffer size",
        std::to_string(win->width()) + "x" + std::to_string(win->height()));
  check(win->ui_scale() >= 1.0f, "ui scale", std::to_string(win->ui_scale()));

  Log log;
  win->on_event = [&](const wm::Event &e) {
    switch (e.type) {
      case wm::EventType::Resize:
        log.resize++;
        printf("  event Resize %dx%d\n", e.width, e.height);
        break;
      case wm::EventType::Expose:
        log.expose++;
        break;
      case wm::EventType::DpiChange:
        log.dpi++;
        log.last_scale = e.ui_scale;
        printf("  event DpiChange scale %.3f\n", e.ui_scale);
        break;
      case wm::EventType::Close:
        log.close++;
        printf("  event Close\n");
        break;
      case wm::EventType::FocusIn:
      case wm::EventType::FocusOut:
        log.focus++;
        break;
      default:
        break;
    }
    return false;
  };

  /* Scripted steps, one per tick; each waits for its precondition with a per-step deadline. */
  int step = 0;
  uint64_t step_start = wm->time_ms(), frames_at_step = 0;
  int resize_at_step = 0;
  bool one_shot_fired = false;
  wm->add_timer(50, 0, [&] { one_shot_fired = true; });

  auto next = [&] {
    step++;
    step_start = wm->time_ms();
    frames_at_step = win->frames_drawn();
    resize_at_step = log.resize;
  };
  auto elapsed = [&] { return wm->time_ms() - step_start; };

  wm->add_timer(30, 30, [&] {
    switch (step) {
      case 0: /* First frame presented. */
        if (win->frames_drawn() > 0) {
          check(true, "first frame presented");
          next();
        }
        else if (elapsed() > 10000) {
          check(false, "first frame presented", "timeout");
          wm->quit(1);
        }
        break;
      case 1: { /* Window content through the window's own GPU context. */
        gfx::Image img;
        const bool ok = win->read_pixels(img, err);
        check(ok && img.width == win->width() && img.height == win->height(), "read_pixels", err);
        if (ok) {
          const app::SampleLayout l = app::sample_layout(img.width, img.height, win->ui_scale());
          const int mid_y = (l.accent_y0 + (img.height / 2)) / 2;
          check(near_color(img.px_bl(img.width - 4, img.height - 4), app::theme::kHeaderBack),
                "header color");
          check(near_color(img.px_bl(img.width - 4, mid_y), app::theme::kRegionBack),
                "content color");
          check(near_color(img.px_bl(img.width / 2, (l.accent_y0 + l.accent_y1) / 2), app::theme::kAccent),
                "accent line");
        }
        win->set_client_size(520, 380);
        next();
        break;
      }
      case 2: /* Resize request: compositors may refuse (kiosk / tiling), so this is informative. */
        if (log.resize > resize_at_step && win->frames_drawn() > frames_at_step) {
          check(true, "resize handled and redrawn",
                std::to_string(win->width()) + "x" + std::to_string(win->height()));
          next();
        }
        else if (elapsed() > 1500) {
          printf("note: resize request not honored by the server (%d resize events total)\n",
                 log.resize);
          next();
        }
        break;
      case 3:
        wm->set_user_scale(1.5f);
        check(log.dpi >= 1 && std::fabs(log.last_scale - 1.5f * win->dpi_factor()) < 1e-3f,
              "user scale -> DpiChange", std::to_string(log.last_scale));
        next();
        break;
      case 4: /* DPI change triggers a redraw. */
        if (win->frames_drawn() > frames_at_step) {
          check(true, "redraw after DPI change");
          wm->set_user_scale(1.0f);
          next();
        }
        else if (elapsed() > 5000) {
          check(false, "redraw after DPI change", "timeout");
          next();
        }
        break;
      case 5: { /* Cursors and clipboard. */
        for (auto c : {wm::Cursor::Text, wm::Cursor::HandPoint, wm::Cursor::ResizeLeftRight,
                       wm::Cursor::Wait, wm::Cursor::Default})
        {
          win->set_cursor(c);
        }
        check(win->cursor() == wm::Cursor::Default, "cursor shapes");
        const std::string text = "STK \xe5\x89\xaa\xe8\xb4\xb4\xe6\x9d\xbf \xe2\x9c\x93"; /* 剪贴板 ✓ */
        wm->set_clipboard_text(text);
        next();
        break;
      }
      case 6: {
        const std::string text = "STK \xe5\x89\xaa\xe8\xb4\xb4\xe6\x9d\xbf \xe2\x9c\x93";
        const std::string got = wm->clipboard_text();
        if (got == text) {
          check(true, "clipboard round trip (UTF-8)");
          next();
        }
        else if (elapsed() > 2000) {
          /* Some servers need a focused client before they accept a selection. */
          printf("note: clipboard round trip not available here (got '%s')\n", got.c_str());
          next();
        }
        break;
      }
      case 7:
        check(one_shot_fired, "one-shot timer fired");
        check(win->frames_drawn() >= 2, "frames presented", std::to_string(win->frames_drawn()));
        win->request_close();
        next();
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
  check(log.close == 1, "Close event delivered once");
  check(wm->windows().empty(), "window destroyed on close");
  wm.reset();
  return (rc != 0 || g_failures) ? 1 : 0;
}

}  // namespace

int main(int argc, char **argv)
{
  std::string backend_arg;
  bool leak_selftest = false;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--gpu-backend") && i + 1 < argc) {
      backend_arg = argv[++i];
    }
    else if (!strcmp(argv[i], "--leak-selftest")) {
      leak_selftest = true;
    }
    else {
      fprintf(stderr, "usage: %s [--gpu-backend B] [--leak-selftest]\n", argv[0]);
      return 2;
    }
  }
  if (leak_selftest) {
    /* Must FAIL: proves that stk::gfx::Runtime's leak detection is armed. */
    gfx::Runtime runtime;
    MEM_new_array_uninitialized<char>(64, "stk-wm-smoke leak self-test");
    return 0;
  }
  gfx::Backend backend;
  std::string err;
  if (!gfx::resolve_backend(backend_arg, backend, err)) {
    fprintf(stderr, "%s\n", err.c_str());
    return 2;
  }
  int rc;
  {
    gfx::Runtime runtime;
    rc = run(backend);
  }
  if (rc == 77) {
    return rc;
  }
  const unsigned blocks = gfx::Runtime::memory_blocks_in_use();
  check(blocks == 0, "no guardedalloc leaks", std::to_string(blocks) + " block(s)");
  printf("%s\n", (rc == 0 && g_failures == 0) ? "PASS" : "FAIL");
  return (rc == 0 && g_failures == 0) ? 0 : 1;
}
