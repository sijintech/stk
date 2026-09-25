/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Live-window test of the WP10 Viewer (run through tests/wm/run_with_display.py: a private Xvfb or
 * a headless weston on unix sockets). The application shell with its default layout and the real
 * Python bridge:
 *   a fake muFerro run is written -> opened in the Viewer (muferro-domains evaluated locally) ->
 *   the view is drawn (pixels) -> a synthesized left drag orbits (pixels change) -> a click picks ->
 *   the Probe editor shows the original value from the bridge `probe` -> screenshot -> close ->
 *   guardedalloc leak check.
 *
 *   stk-viewer-live --python PY --repo DIR --workdir DIR [--gpu-backend B] [--screenshot PNG]
 * Exit codes: 0 pass, 1 failure, 77 skipped (no display, or the Python cannot evaluate graphs).
 */

#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>

#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/client.hh"
#include "stk/bridge/process.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/viewer/format.hh"
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

int run_python(const std::string &python, const std::string &repo, const std::vector<std::string> &args, std::string &out)
{
  bridge::SpawnOptions o;
  o.argv = {python, repo + "/desktop/tests/bridge/bridge_fixture.py"};
  o.argv.insert(o.argv.end(), args.begin(), args.end());
  o.env["PYTHONPATH"] = repo;
  std::string err;
  auto child = bridge::ChildProcess::spawn(o, err);
  if (!child) {
    out = err;
    return -1;
  }
  child->close_stdin();
  char buf[4096];
  std::ptrdiff_t n;
  while ((n = child->read(bridge::ChildProcess::Stream::Stdout, buf, sizeof(buf))) > 0) {
    out.append(buf, size_t(n));
  }
  const auto st = child->wait(300);
  return st ? st->code : -1;
}

double differing_fraction(const gfx::Image &a, const gfx::Image &b, const wm::Rect &r)
{
  if (a.width != b.width || a.height != b.height) {
    return 1.0;
  }
  size_t n = 0, total = 0;
  for (int y = r.ymin; y < r.ymax; y++) {
    for (int x = r.xmin; x < r.xmax; x++) {
      const uint8_t *p = a.px_bl(x, y), *q = b.px_bl(x, y);
      int d = 0;
      for (int k = 0; k < 3; k++) {
        d = std::max(d, std::abs(int(p[k]) - int(q[k])));
      }
      n += d > 24 ? 1 : 0;
      total++;
    }
  }
  return total ? double(n) / double(total) : 0.0;
}

size_t colored_pixels(const gfx::Image &img, const wm::Rect &r)
{
  size_t n = 0;
  for (int y = r.ymin; y < r.ymax; y++) {
    for (int x = r.xmin; x < r.xmax; x++) {
      const uint8_t *p = img.px_bl(x, y);
      const int hi = std::max({p[0], p[1], p[2]}), lo = std::min({p[0], p[1], p[2]});
      n += hi - lo > 40 ? 1 : 0;
    }
  }
  return n;
}

struct Options {
  std::string backend, python, repo, workdir, screenshot;
};

int run(const gfx::Backend backend, const Options &opt)
{
  std::string out;
  if (run_python(opt.python, opt.repo, {"check", "graph"}, out) != 0) {
    printf("SKIP: %s cannot evaluate graphs: %s\n", opt.python.c_str(), out.c_str());
    return 77;
  }
  std::error_code ec;
  std::filesystem::remove_all(opt.workdir, ec);
  std::filesystem::create_directories(opt.workdir, ec);
  const std::string run_dir = opt.workdir + "/run";
  out.clear();
  if (run_python(opt.python, opt.repo, {"write-run", run_dir}, out) != 0) {
    check(false, "fake muFerro run", out);
    return 1;
  }

  app::ShellOptions so;
  so.language = "en";
  app::AppShell shell(so);
  check(shell.catalogs_loaded(), "catalogs", shell.options().i18n_dir);
  wm::WmOptions wo;
  wo.gpu.backend = backend;
  wo.window = {"STK viewer live", 1240, 780, false};
  std::string err;
  std::unique_ptr<wm::WindowManager> wm = wm::WindowManager::create(wo, err);
  if (!wm) {
    printf("SKIP: %s\n", err.c_str());
    return err.find("no display") != std::string::npos ? 77 : 1;
  }
  printf("system %s, GPU %s\n", wm->system_backend(), wm->gpu().backend_name());
  wm::Window *win = wm->main_window();
  wm::Screen &screen = win->screen();
  shell.install(screen, win);
  shell.build_default_layout(screen);
  shell.layout_path.clear();
  app::AppStore &store = shell.store();
  app::ViewerState &vs = store.viewer();

  bridge::ClientOptions bo;
  bo.executor = wm->executor();
  bo.python.configured = opt.python;
  bo.state_dir = opt.workdir + "/state";
  bo.cache_dir = opt.workdir + "/cache";
  bo.env["PYTHONPATH"] = opt.repo;
  bo.env["STK_PROFILES_FILE"] = opt.workdir + "/profiles/connections.json";
  bo.env["STK_STATE_DIR"] = opt.workdir + "/no-local-runtime";
  bo.env["STK_DESKTOP_BRIDGE_DIR"] = std::nullopt;
  bo.env["STK_RUNTIME_URL"] = std::nullopt;
  bo.env["STK_RUNTIME_TOKEN"] = std::nullopt;
  bo.env["MPLCONFIGDIR"] = opt.workdir + "/mpl";
  bo.env["STK_GRAPH_CACHE"] = opt.workdir + "/graph-cache";
  bo.call_timeout_s = 600;
  bo.hello_timeout_s = 120;
  auto client = bridge::Client::create(std::move(bo));
  check(client->start(&err), "bridge started", err);
  store.set_bridge(client.get());

  win->on_event = [&](const wm::Event &e) {
    if (e.type == wm::EventType::Close) {
      /* The screen dies with the window: store changes after this must not tag it. */
      store.on_change = nullptr;
      store.toast = nullptr;
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
  auto shot = [&](gfx::Image &img) {
    const bool ok = win->read_pixels(img, err);
    if (!ok) {
      check(false, "read_pixels", err);
    }
    return ok;
  };

  int step = 0;
  uint64_t step_start = wm->time_ms(), frames_at_step = 0;
  gfx::Image before;
  auto next = [&] {
    step++;
    step_start = wm->time_ms();
    frames_at_step = win->frames_drawn();
  };
  auto elapsed = [&] { return wm->time_ms() - step_start; };
  auto new_frame = [&] { return win->frames_drawn() > frames_at_step; };
  auto main_rect = [&]() { return area("a2")->find_region("main")->rect(); };

  wm->add_timer(30, 30, [&] {
    switch (step) {
      case 0: /* the bridge says hello */
        if (client->state() == bridge::BridgeState::Ready && win->frames_drawn() > 0) {
          check(vs.open_path(run_dir, "muferro-domains"), "open the run folder", vs.open_error());
          store.changed();
          next();
        }
        else if (client->state() == bridge::BridgeState::Failed || elapsed() > 120000) {
          check(false, "bridge ready", client->last_error() ? client->last_error()->describe() : "timeout");
          wm->quit(1);
        }
        break;
      case 1: /* evaluated and drawn */
        if (vs.payload() && !vs.evaluating() && new_frame()) {
          check(vs.last_eval() && !vs.last_eval()->evaluated.empty(), "muferro-domains evaluated",
                std::to_string(vs.last_eval() ? vs.last_eval()->evaluated.size() : 0) + " nodes");
          if (shot(before)) {
            const size_t colored = colored_pixels(before, main_rect());
            check(colored > 2000, "domain surfaces on screen", std::to_string(colored) + " coloured pixels");
          }
          /* Orbit: a left drag in the viewer (tool: orbit). */
          const wm::Rect r = main_rect();
          const int x = (r.xmin + r.xmax) / 2, y = (r.ymin + r.ymax) / 2;
          send(wm::EventType::MouseMove, x, y);
          send(wm::EventType::MouseDown, x, y);
          for (int i = 1; i <= 6; i++) {
            send(wm::EventType::MouseMove, x + 15 * i, y + 6 * i);
          }
          send(wm::EventType::MouseUp, x + 90, y + 36);
          win->request_redraw();
          next();
        }
        else if (!vs.eval_error().empty() || elapsed() > 300000) {
          check(false, "evaluation", vs.eval_error().empty() ? "timeout" : vs.eval_error());
          wm->quit(1);
        }
        break;
      case 2: /* the orbit changed the view; then click (pick) at the centre */
        if (new_frame()) {
          gfx::Image after;
          if (shot(after)) {
            const double d = differing_fraction(before, after, main_rect());
            char buf[64];
            snprintf(buf, sizeof(buf), "%.1f %% of the viewer pixels changed", d * 100.0);
            check(d > 0.02, "orbit by synthesized drag", buf);
          }
          vs.request_camera_reset(); /* back to the result's camera: the centre is on a surface */
          win->request_redraw();
          next();
        }
        else if (elapsed() > 10000) {
          check(false, "redraw after the drag", "timeout");
          wm->quit(1);
        }
        break;
      case 3:
        if (elapsed() > 10000) {
          check(false, "redraw after the camera reset", "timeout");
          wm->quit(1);
        }
        else if (new_frame()) {
          const wm::Rect r = main_rect();
          const int x = (r.xmin + r.xmax) / 2, y = (r.ymin + r.ymax) / 2;
          send(wm::EventType::MouseMove, x, y);
          send(wm::EventType::MouseDown, x, y);
          send(wm::EventType::MouseUp, x, y);
          next();
        }
        break;
      case 4: /* the probe answered */
        if (vs.probe().status == app::ProbeState::Status::Done || vs.probe().status == app::ProbeState::Status::Failed ||
            vs.probe().status == app::ProbeState::Status::Unavailable)
        {
          check(vs.probe().status == app::ProbeState::Status::Done, "pick probed through the bridge",
                vs.probe().error.empty() ? vs.probe().sample.dump() : vs.probe().error);
          area("a4")->set_active_tab(1); /* Logs | Probe | Transfers | Bridge log */
          store.changed();
          next();
        }
        else if (elapsed() > 120000) {
          check(false, "pick", "no pick or probe result (status " + std::to_string(int(vs.probe().status)) + ")");
          wm->quit(1);
        }
        break;
      case 5: /* the Probe editor shows the value */
        if (elapsed() > 10000) {
          check(false, "redraw with the Probe editor", "timeout");
          wm->quit(1);
        }
        else if (new_frame()) {
          std::string want;
          const io::Json &values = vs.probe().sample.value("values", io::Json());
          if (values.is_array() && !values.empty() && values[0].is_number()) {
            want = viewer::format_label(values[0].get<double>(), ".6g");
          }
          bool shown = false;
          for (const auto &b : screen.ui()->blocks()) {
            if (b->name().rfind("a4/", 0) != 0) {
              continue;
            }
            for (const ui::Widget &w : b->widgets()) {
              shown |= !want.empty() && w.text.find(want) != std::string::npos;
            }
          }
          check(shown, "Probe editor shows the value", want);
          gfx::Image final_shot;
          if (!opt.screenshot.empty() && shot(final_shot)) {
            std::filesystem::create_directories(std::filesystem::path(opt.screenshot).parent_path(), ec);
            gfx::png_write(opt.screenshot, final_shot);
            printf("screenshot %s\n", opt.screenshot.c_str());
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
  wm->add_timer(400000, 0, [&] {
    check(false, "overall timeout");
    wm->quit(1);
  });
  const int rc = wm->run();
  vs.close();
  store.set_bridge(nullptr);
  client->close();
  client.reset();
  wm.reset();
  return (rc != 0 || g_failures) ? 1 : 0;
}

}  // namespace

int main(int argc, char **argv)
{
  Options opt;
  for (int i = 1; i < argc; i++) {
    auto val = [&](std::string &dst) {
      if (i + 1 < argc) {
        dst = argv[++i];
      }
    };
    if (!std::strcmp(argv[i], "--gpu-backend")) {
      val(opt.backend);
    }
    else if (!std::strcmp(argv[i], "--python")) {
      val(opt.python);
    }
    else if (!std::strcmp(argv[i], "--repo")) {
      val(opt.repo);
    }
    else if (!std::strcmp(argv[i], "--workdir")) {
      val(opt.workdir);
    }
    else if (!std::strcmp(argv[i], "--screenshot")) {
      val(opt.screenshot);
    }
    else {
      fprintf(stderr, "usage: %s --python PY --repo DIR --workdir DIR [--gpu-backend B] [--screenshot PNG]\n", argv[0]);
      return 2;
    }
  }
  if (opt.python.empty() || opt.repo.empty() || opt.workdir.empty()) {
    fprintf(stderr, "--python, --repo and --workdir are required\n");
    return 2;
  }
  gfx::Backend backend;
  std::string err;
  if (!gfx::resolve_backend(opt.backend, backend, err)) {
    fprintf(stderr, "%s\n", err.c_str());
    return 2;
  }
  int rc;
  {
    gfx::Runtime runtime;
    rc = run(backend, opt);
  }
  if (rc == 77) {
    return rc;
  }
  const unsigned blocks = gfx::Runtime::memory_blocks_in_use();
  check(blocks == 0, "no guardedalloc leaks", std::to_string(blocks) + " block(s)");
  printf("%s\n", (rc == 0 && g_failures == 0) ? "PASS" : "FAIL");
  return (rc == 0 && g_failures == 0) ? 0 : 1;
}
