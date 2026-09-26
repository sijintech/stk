/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk-jobs-live: the Jobs editor in a live window (run through run_with_display.py: private Xvfb
 * or headless weston on unix sockets) against the fake bridge (stk-bridge-fake --jobs). Timer-driven
 * steps: first frame and bridge ready -> connect the "lab" Runtime -> maximize the Jobs area ->
 * click the task-name field and type Chinese through synthesized IME events (preedit, then commit;
 * what GHOST delivers on Wayland text-input-v3 / macOS / Windows) plus plain key text -> Submit ->
 * the task appears in the watched list under that name -> screenshot -> close (the bridge gets
 * EOF, never task.cancel) -> guardedalloc leak check.
 *
 *   stk-jobs-live [--gpu-backend B] --fake-bridge PATH --work DIR [--screenshot out.png]
 * Exit codes: 0 pass, 1 failure, 77 skipped (no display).
 */

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/shell.hh"
#include "stk/bridge/client.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/wm/window.hh"

using namespace stk;

namespace {

int g_failures = 0;

void check(const bool ok, const char *what, const std::string &detail = {})
{
  printf("%s %s%s%s\n", ok ? "ok  " : "FAIL", what, detail.empty() ? "" : ": ", detail.c_str());
  fflush(stdout);
  if (!ok) {
    g_failures++;
  }
}

int run(const gfx::Backend backend, const std::string &fake, const std::string &work, const std::string &shot)
{
  app::ShellOptions so;
  so.language = "zh_CN";
  app::AppShell shell(so);
  check(shell.catalogs_loaded(), "catalogs", shell.options().i18n_dir);

  wm::WmOptions opts;
  opts.gpu.backend = backend;
  opts.window = {"STK jobs live", 1100, 740, false};
  std::string err;
  std::unique_ptr<wm::WindowManager> wm = wm::WindowManager::create(opts, err);
  if (!wm) {
    printf("SKIP: %s\n", err.c_str());
    return err.find("no display") != std::string::npos ? 77 : 1;
  }
  wm::Window *win = wm->main_window();
  wm::Screen &screen = win->screen();
  shell.install(screen, win);
  shell.build_default_layout(screen);
  shell.layout_path.clear();

  app::JobsState &jobs = shell.store().jobs();
  app::use_gpu_textures(jobs);
  jobs.open_external = [](const std::string &, std::string *) { return true; };
  jobs.schedule = [&wm](double s, std::function<void()> fn) { wm->add_timer(uint64_t(s * 1000.0), 0, std::move(fn)); };
  bridge::ClientOptions bo;
  bo.command = {fake, "--jobs", work};
  bo.executor = wm->executor();
  std::unique_ptr<bridge::Client> client = bridge::Client::create(std::move(bo));
  shell.store().set_bridge(client.get());
  auto status = std::make_unique<app::BridgeStatus>(shell.store(), *client, wm.get());
  jobs.attach(client.get());
  check(client->start(&err), "bridge start", err);

  auto dctx = [&]() {
    wm::DrawContext c;
    c.window = win;
    c.ui_scale = win->ui_scale();
    c.fonts = &wm->gpu().fonts();
    c.rect = {0, 0, win->width(), win->height()};
    return c;
  };
  uint64_t t_event = wm->time_ms();
  auto send = [&](wm::Event e) {
    e.window = win;
    e.time_ms = (t_event += 15);
    screen.dispatch(e, dctx());
  };
  auto widget_pos = [&](const std::string &key, int &x, int &y) {
    const ui::Widget *w = screen.ui() ? screen.ui()->find(key) : nullptr;
    if (!w) {
      return false;
    }
    x = int(w->rect.cx());
    y = win->height() - 1 - int(w->rect.cy());
    return true;
  };
  auto click = [&](const std::string &key) {
    int x, y;
    if (!widget_pos(key, x, y)) {
      return false;
    }
    wm::Event e;
    e.x = x;
    e.y = y;
    e.button = wm::MouseButton::Left;
    e.type = wm::EventType::MouseMove;
    send(e);
    e.type = wm::EventType::MouseDown;
    send(e);
    e.type = wm::EventType::MouseUp;
    send(e);
    return true;
  };
  auto key_text = [&](const std::string &text, wm::Key k = wm::Key::Unknown) {
    wm::Event e;
    e.type = wm::EventType::KeyDown;
    e.key = k;
    e.text = text;
    send(e);
    e.type = wm::EventType::KeyUp;
    e.text.clear();
    send(e);
  };

  const std::string name = "铁电畴 300K";
  int step = 0;
  uint64_t step_start = wm->time_ms();
  auto next = [&] {
    step++;
    step_start = wm->time_ms();
  };
  auto timeout = [&](uint64_t ms, const char *what) {
    if (wm->time_ms() - step_start > ms) {
      check(false, what, "timeout");
      wm->quit(1);
      return true;
    }
    return false;
  };
  wm->add_timer(30, 30, [&] {
    switch (step) {
      case 0:
        if (win->frames_drawn() > 0 && jobs.ready() && jobs.connections().size() >= 2) {
          check(true, "first frame, bridge ready");
          jobs.select_connection("runtime:lab");
          next();
        }
        else {
          timeout(20000, "first frame / bridge");
        }
        break;
      case 1:
        if (!jobs.workspace().empty() && jobs.snapshot_time() > 0) {
          check(shell.store().connection().find("lab") != std::string::npos, "status bar connection",
                shell.store().connection());
          screen.set_maximized(screen.find_area("a1"));
          win->request_redraw();
          next();
        }
        else {
          timeout(10000, "workspace");
        }
        break;
      case 2: {
        if (wm->time_ms() - step_start < 200) {
          break;
        }
        check(click("a1/main/submit/name"), "click the task-name field");
        check(screen.ui()->text_input_active(), "text input active (IME enabled)");
        wm::Event e;
        e.type = wm::EventType::ImeStart;
        send(e);
        e.type = wm::EventType::ImeUpdate;
        e.ime.composite = "tiedianchou";
        e.ime.cursor = int(e.ime.composite.size());
        send(e);
        check(screen.ui()->edit_state() && screen.ui()->edit_state()->composing(), "inline preedit shown");
        e.ime = {};
        e.ime.result = "铁电畴";
        send(e);
        e.type = wm::EventType::ImeEnd;
        e.ime = {};
        send(e);
        for (const char *t : {" ", "3", "0", "0", "K"}) {
          key_text(t);
        }
        key_text("", wm::Key::Enter);
        check(jobs.form().name == name, "IME text committed", jobs.form().name);
        win->request_redraw();
        next();
        break;
      }
      case 3:
        if (wm->time_ms() - step_start < 100) {
          break;
        }
        check(click("a1/main/submit/submit_form"), "click Submit");
        next();
        break;
      case 4: {
        bool listed = false;
        for (const app::TaskRow &t : jobs.tasks()) {
          listed |= t.name == name;
        }
        if (jobs.submission() && jobs.submission()->state == app::SubmitState::Done && listed) {
          check(true, "submitted and listed", jobs.submission()->task_id);
          win->request_redraw();
          next();
        }
        else {
          timeout(15000, "submission");
        }
        break;
      }
      case 5:
        if (wm->time_ms() - step_start < 400) {
          break;
        }
        if (!shot.empty()) {
          gfx::Image img;
          if (win->read_pixels(img, err)) {
            gfx::png_write(shot, img);
            printf("screenshot %s\n", shot.c_str());
          }
        }
        wm->quit(0);
        next();
        break;
      default:
        break;
    }
  });
  wm->add_timer(60000, 0, [&wm] {
    check(false, "overall", "timeout");
    wm->quit(1);
  });
  const int rc = wm->run();
  /* Close like the application: jobs, status mirror, bridge (EOF), windows. */
  jobs.attach(nullptr);
  jobs.clear_preview();
  jobs.create_texture = nullptr;
  jobs.free_texture = nullptr;
  jobs.schedule = nullptr;
  status.reset();
  shell.store().set_bridge(nullptr);
  client.reset();
  std::ifstream log(work + "/methods.log");
  std::string line, last;
  bool cancel = false;
  while (std::getline(log, line)) {
    cancel |= line == "task.cancel";
    last = line;
  }
  check(!cancel, "closing did not cancel tasks");
  check(last == "EOF", "the bridge got EOF", last);
  wm.reset();
  /* The window is gone: the shell forgot its screen, and store changes are harmless. */
  check(shell.screen_count() == 0, "shell forgot the closed window's screen");
  shell.store().changed();
  shell.store().toast("closed", ui::ToastKind::Info);
  return rc != 0 ? rc : (g_failures ? 1 : 0);
}

}  // namespace

int main(int argc, char **argv)
{
  std::string backend_name, fake, work, shot;
  for (int i = 1; i < argc; i++) {
    const std::string a = argv[i];
    auto next = [&]() { return i + 1 < argc ? std::string(argv[++i]) : std::string(); };
    if (a == "--gpu-backend") {
      backend_name = next();
    }
    else if (a == "--fake-bridge") {
      fake = next();
    }
    else if (a == "--work") {
      work = next();
    }
    else if (a == "--screenshot") {
      shot = next();
    }
  }
  if (fake.empty() || work.empty()) {
    fprintf(stderr, "usage: stk-jobs-live [--gpu-backend B] --fake-bridge PATH --work DIR [--screenshot out.png]\n");
    return 2;
  }
  std::error_code ec;
  std::filesystem::remove_all(work, ec);
  gfx::Backend backend;
  std::string err;
  if (!gfx::resolve_backend(backend_name, backend, err)) {
    fprintf(stderr, "FAIL: %s\n", err.c_str());
    return 2;
  }
  int rc;
  {
    gfx::Runtime runtime;
    rc = run(backend, fake, work, shot);
  }
  if (rc == 77) {
    return 77;
  }
  /* Engine statics may hold blocks until static destruction (Metal): the leak verdict is
   * guardedalloc's at-exit check (it aborts, and ctest matches its report). */
  printf("guardedalloc: %u block(s) in use after shutdown\n", gfx::Runtime::memory_blocks_in_use());
  if (rc == 0 && g_failures == 0) {
    printf("PASS\n");
    return 0;
  }
  return 1;
}
