/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Production ReportsEditor -> real bridge -> production native Host -> OS client capture.
 * Synthetic fixtures only. Mouse actions use Screen's normal event routing; they are not OS
 * hardware input. No direct browser/Host construction, renderer injection or offscreen proof. */
#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/client.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/gfx/gpu.hh"
#include "stk/io/payload.hh"
#include "stk/io/png.hh"
#include "stk/wm/window.hh"
#include "../../spike/document_preview/window_evidence.hh"
#include "../../spike/document_preview/evidence_pixels.hh"
#include "../../spike/document_preview/fixture.hh"
#include "reports_native_scroll.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <functional>
#include <optional>
#include <set>
#include <stdexcept>

using namespace stk;
using io::Json;
namespace fs = std::filesystem;
namespace {
constexpr const char *kReport = "a1111111-1111-4111-8111-111111111111";
using Clock = std::chrono::steady_clock;
void require(bool ok, const std::string &message) { if (!ok) { throw std::runtime_error(message); } }
void write(const fs::path &path, const std::string &text)
{
  std::ofstream out(path, std::ios::binary);
  out.write(text.data(), std::streamsize(text.size()));
  require(out.good(), "Cannot write public fixture/evidence: " + core::path_to_utf8(path));
}
struct Options { std::string python, backend, source = "markdown"; fs::path output; };

void log_last_observation(const Json &result) noexcept
{
  try {
    const auto observation = result.find("last_observation");
    if (observation == result.end() || !observation->is_object()) {
      std::fputs("STK_NATIVE_LAST_OBSERVATION unavailable\n", stderr);
      return;
    }
    // Copy only synthetic pixel measurements, never file/backend strings or resource URLs.
    Json diagnostic = Json::object();
    for (const auto *key : {"page1_marker_in_viewport", "page2_marker_in_viewport",
             "marker_outside_viewport", "body_text_required", "body_text_marker_in_viewport",
             "body_text_marker_outside_viewport"}) {
      const auto value = observation->find(key);
      diagnostic[key] = value != observation->end() && value->is_boolean() ? *value : Json(nullptr);
    }
    for (const auto *key : {"cycle", "expected_page", "consecutive_matches",
             "native_scroll_requests_this_phase", "host_colored_samples"}) {
      const auto value = observation->find(key);
      diagnostic[key] = value != observation->end() && value->is_number_integer() ? *value : Json(nullptr);
    }
    const auto geometry = [&](const char *key, size_t size) {
      const auto value = observation->find(key);
      diagnostic[key] = value != observation->end() && value->is_array() && value->size() == size &&
          std::all_of(value->begin(), value->end(), [](const Json &v) { return v.is_number_integer(); }) ?
          *value : Json(nullptr);
    };
    geometry("viewport_top_left", 4);
    geometry("client_size", 2);
    diagnostic["phase"] = nullptr;
    const auto phase = observation->find("phase");
    if (phase != observation->end() && phase->is_string()) {
      const auto &name = phase->get_ref<const std::string &>();
      for (const auto *allowed : {"visible-page1", "scrolled-page2", "hidden-tab", "reshown",
               "popup", "after-popup", "closed", "reprepared-page1"}) {
        if (name == allowed) { diagnostic["phase"] = name; break; }
      }
    }
    std::fprintf(stderr, "STK_NATIVE_LAST_OBSERVATION %s\n", diagnostic.dump().c_str());
  }
  catch (...) { std::fputs("STK_NATIVE_LAST_OBSERVATION unavailable\n", stderr); }
}

io::Image marker()
{
  io::Image image(240, 24);
  for (uint32_t y = 0; y < image.height; ++y) for (uint32_t x = 0; x < image.width; ++x) {
    const auto &color = document_preview::kEvidenceColors[x / 40];
    std::copy(color.begin(), color.end(), image.pixel(x, y)); image.pixel(x, y)[3] = 255;
  }
  return image;
}

class Exercise {
 public:
  Exercise(wm::WindowManager &manager, wm::Window &window, Json &result, fs::path directory)
      : manager_(manager), window_(window), screen_(window.screen()), result_(result), directory_(std::move(directory)) {}
  void process()
  {
    const bool alive = manager_.process(true);
    check_native_scroll();
    require(alive && manager_.main_window() == &window_, "STK window closed unexpectedly");
  }
  void wait(const std::function<bool()> &predicate, const std::string &reason, double seconds = 45)
  {
    const auto start = Clock::now();
    while (!predicate()) {
      require(std::chrono::duration<double>(Clock::now() - start).count() < seconds, reason + " timed out");
      process();
    }
  }
  void frame()
  {
    const auto previous = window_.frames_drawn(); window_.request_redraw();
    wait([&] { return window_.frames_drawn() > previous; }, "UI frame");
    // This is only a scheduling boundary. OS captures below prove composition independently.
  }
  const ui::Widget *widget(const std::string &key) const { return screen_.ui() ? screen_.ui()->find(key) : nullptr; }
  bool visible(const ui::Widget *w) const
  {
    if (!w) { return false; }
    const auto clip = w->rect.intersect(w->clip).intersect({0, 0, float(window_.width()), float(window_.height())});
    return !clip.empty() && clip.w >= w->rect.w - 1 && clip.h >= w->rect.h - 1;
  }
  void event(wm::Event e)
  {
    e.window = &window_; e.time_ms = manager_.time_ms();
    wm::DrawContext ctx; ctx.window = &window_; ctx.fonts = &manager_.gpu().fonts();
    ctx.ui_scale = window_.ui_scale(); ctx.rect = {0, 0, window_.width(), window_.height()};
    ctx.ui = screen_.ui(); ctx.now = double(e.time_ms) / 1000;
    screen_.dispatch(e, ctx); window_.request_redraw();
  }
  void key(wm::Key value, uint32_t modifiers = wm::ModNone)
  {
    wm::Event e; e.type = wm::EventType::KeyDown; e.key = value; e.modifiers = modifiers; event(e);
    e.type = wm::EventType::KeyUp; event(e); frame();
  }
  void move_pointer(ui::Vec2 point)
  {
    wm::Event e; e.type = wm::EventType::MouseMove;
    e.x = int(point.x); e.y = window_.height() - 1 - int(point.y);
    event(e); ++pointer_moves; frame();
  }
  void enlarge_report_row(app::EditorArea &area)
  {
    // Window servers may clamp the requested 1440x1000 window (macOS CI is
    // 1024x653). Resize the real upper row, retaining the adjacent Viewer and
    // every live editor; do not replace the layout or assume requested pixels.
    frame();
    auto *row = area.node() ? area.node()->parent : nullptr;
    auto *work = row ? row->parent : nullptr;
    require(work && work->dir == wm::SplitDir::Vertical && work->children.size() == 2 &&
        work->children[0].get() == row, "Expected default report/Viewer row above table");
    const auto found = std::find_if(screen_.splitters().begin(), screen_.splitters().end(),
        [work](const wm::Splitter &splitter) { return splitter.node == work && splitter.index == 0; });
    require(found != screen_.splitters().end(), "Report row splitter must exist");
    const auto bar = found->rect;
    const auto before = area.rect();
    const int x = (before.xmin + before.xmax) / 2;
    const int from_y = (bar.ymin + bar.ymax) / 2;
    const int to_y = work->rect.ymin + int(std::ceil(std::max(
        4.0f * screen_.ui()->style().unit, float(work->rect.height()) * 0.12f)));
    require(to_y < from_y, "Actual client is too small to enlarge the report row");
    wm::Event e; e.x = x; e.y = from_y; e.type = wm::EventType::MouseMove; event(e);
    e.type = wm::EventType::MouseDown; e.button = wm::MouseButton::Left; event(e); frame();
    require(screen_.capture() == wm::Screen::Capture::Splitter, "Mouse must capture the row splitter");
    e.type = wm::EventType::MouseMove; e.y = to_y; event(e); frame();
    e.type = wm::EventType::MouseUp; event(e); frame();
    ++layout_drags;
    require(screen_.capture() == wm::Screen::Capture::None && area.rect().height() > before.height(),
        "Actual row drag must enlarge the report area and release capture");
    const auto after = area.rect();
    result_["layout_preparation"] = {{"action", "one mouse drag of default upper-row/table splitter"},
        {"client_size", {window_.width(), window_.height()}},
        {"report_area_before_bottom_left", {before.xmin, before.ymin, before.width(), before.height()}},
        {"report_area_after_bottom_left", {after.xmin, after.ymin, after.width(), after.height()}},
        {"drag_from_bottom_left", {x, from_y}}, {"drag_to_bottom_left", {x, to_y}}};
    move_pointer({float(after.xmin + after.width() / 2),
        float(window_.height() - 1 - (after.ymin + after.height() / 2))});
    save();
  }
  void text(const std::string &value)
  {
    // Same UTF-8 commit path that GHOST key events use; no widget binding/setter invocation.
    wm::Event e; e.type = wm::EventType::KeyDown; e.text = value; event(e); frame();
  }
  void scroll_to(const std::string &key, app::EditorArea &area)
  {
    for (int i = 0; i < 80 && !visible(widget(key)); ++i) {
      const auto *w = widget(key); require(w, "Missing control: " + key);
      const auto r = area.find_region(app::EditorArea::kMain)->ui_rect();
      wm::Event e; e.type = wm::EventType::Wheel;
      e.x = int(r.x1() - 2); e.y = window_.height() - 1 - int(r.cy());
      e.wheel_y = w->rect.cy() > r.cy() ? -1 : 1;
      event(e); ++wheels; frame();
    }
    require(visible(widget(key)), "Control is not fully visible: " + key);
  }
  void click(const std::string &key, app::EditorArea &area, int row = -1)
  {
    scroll_to(key, area);
    const auto *w = widget(key); require(w && w->enabled, "Disabled control: " + key);
    ui::Vec2 p{w->rect.cx(), w->rect.cy()};
    if (row >= 0) {
      require(w->list && row < w->list->count, "Missing report row");
      p.y = w->rect.y + screen_.ui()->style().pixel + screen_.ui()->style().unit * (row + 0.5f);
    }
    click_point(p); ++clicks;
  }
  void tab(app::EditorArea &area, int index)
  {
    const auto key = area.id() + "/header/tabs";
    const auto *w = widget(key); require(w && w->enabled && visible(w), "Tab selector must be fully visible");
    if (w->type == ui::WidgetType::Tabs) {
      click_point({w->rect.x + w->rect.w * (float(index) + 0.5f) / float(w->items.size()), w->rect.cy()});
      ++clicks;
    }
    else {
      require(w->type == ui::WidgetType::Dropdown, "Expected tab selector");
      click(key, area); keypress_tab_choice(index);
    }
    wait([&] { return area.active_tab() == index; }, "Tab selection"); frame();
  }
  void native_scroll(int cycle, ui::Rect bounds)
  {
    std::string delivery, error;
    // The host clips native children inward to whole framebuffer pixels. Match that
    // admitted rectangle so fractional UI geometry cannot target its neighbouring edge.
    const auto screen = screen_.rect();
    const int x = screen.xmin + int(std::ceil(bounds.x));
    const int y = screen.ymax - int(std::floor(bounds.y + bounds.h));
    const int right = screen.xmin + int(std::floor(bounds.x + bounds.w));
    const int top = screen.ymax - int(std::ceil(bounds.y));
    const document_preview::ViewBounds viewport{x, y, right - x, top - y};
    require(scroll_guard_.scroll_document(window_.native_window_handle(), viewport,
        window_.width(), window_.height(), -1, delivery, error), error);
    result_["native_scroll_requests"].push_back({{"cycle", cycle}, {"direction", "down"},
        {"delivery", delivery}, {"viewport_bottom_left", {viewport.x, viewport.y, viewport.width, viewport.height}},
        {"request_number", result_["native_scroll_requests"].size() + 1}});
    save(); process();
  }
  void capture(int cycle, const std::string &phase, int expected_page, ui::Rect bounds,
               bool require_text, bool scroll_to_second_page = false)
  {
    int consecutive = 0;
    int scrolls = 0;
    if (scroll_to_second_page) { native_scroll(cycle, bounds); ++scrolls; }
    std::unique_ptr<document_preview::WindowEvidenceCapture> pending;
    wait([&] {
      if (!pending) { pending = document_preview::capture_window_evidence(window_.native_window_handle()); return false; }
      auto image = pending->poll();
      check_native_scroll();
      if (!image) { return false; } pending.reset();
      require(image->error.empty(), "OS client capture: " + image->error);
      const auto &pixels = image->image;
      require(pixels.channels == 4 && pixels.width == uint32_t(window_.width()) &&
          pixels.height == uint32_t(window_.height()), "OS capture must match the exact STK client framebuffer");
      const int x = int(std::round(bounds.x)), y = int(std::round(bounds.y));
      const int width = int(std::round(bounds.w)), height = int(std::round(bounds.h));
      require(x >= 0 && y >= 0 && width > 0 && height > 0 && x + width <= window_.width() &&
          y + height <= window_.height(), "Native viewport lies outside this STK client");
      io::Image crop{uint32_t(width), uint32_t(height)};
      auto outside = pixels;
      for (int row = 0; row < height; ++row) {
        std::copy_n(pixels.pixel(uint32_t(x), uint32_t(y + row)), size_t(width) * 4, crop.row(uint32_t(row)));
        std::fill_n(outside.pixel(uint32_t(x), uint32_t(y + row)), size_t(width) * 4, uint8_t(0));
      }
      size_t colored = 0;
      for (uint32_t py = 0; py < outside.height; py += 2) for (uint32_t px = 0; px < outside.width; px += 2) {
        const auto *p = outside.pixel(px, py);
        if (*std::max_element(p, p + 3) - *std::min_element(p, p + 3) > 45) { ++colored; }
      }
      const bool first = document_preview::evidence_marker(crop, 1);
      const bool second = document_preview::evidence_marker(crop, 2);
      const bool elsewhere = document_preview::evidence_marker(outside, 1) ||
                             document_preview::evidence_marker(outside, 2);
      const bool text = require_text && document_preview::evidence_text_marker(crop);
      const bool text_elsewhere = require_text && document_preview::evidence_text_marker(outside);
      const bool pages_match = first == (expected_page == 1) && second == (expected_page == 2);
      const bool text_match = !require_text || (text == (expected_page != 0) && !text_elsewhere);
      const bool matched = colored >= 256 && !elsewhere && pages_match && text_match;
      consecutive = matched ? consecutive + 1 : 0;
      const auto filename = "cycle-" + std::to_string(cycle) + "-" + phase +
          (consecutive >= 2 ? ".png" : "-waiting.png");
      check_native_scroll();  // A painted page cannot excuse a wheel that escaped its container.
      const auto bytes = io::encode_png(pixels); io::write_png(directory_ / filename, pixels);
      result_["last_observation"] = {{"file", filename}, {"sha256", core::Sha256::hex(bytes)},
          {"backend", image->backend}, {"cycle", cycle}, {"phase", phase}, {"consecutive_matches", consecutive},
          {"expected_page", expected_page}, {"page1_marker_in_viewport", first},
          {"page2_marker_in_viewport", second}, {"marker_outside_viewport", elsewhere},
          {"body_text_required", require_text}, {"body_text_marker_in_viewport", text},
          {"body_text_marker_outside_viewport", text_elsewhere}, {"native_scroll_requests_this_phase", scrolls},
          {"host_colored_samples", colored}, {"viewport_top_left", {x, y, width, height}},
          {"client_size", {pixels.width, pixels.height}}};
      if (consecutive >= 2) { result_["images"].push_back(result_["last_observation"]); }
      save();
      // Deliver at most one local wheel event after an actual nonmatching OS frame. Never
      // advance after the first matching frame; the second must confirm stable page pixels.
      if (scroll_to_second_page && !matched) {
        require(scrolls < 80, "PDF second page not reached within 80 native wheel requests");
        native_scroll(cycle, bounds); ++scrolls;
      }
      return consecutive >= 2;
    }, "OS pixels " + phase, 45);
  }
  void save()
  {
    check_native_scroll();
    result_["actual_mouse_clicks"] = clicks; result_["wheel_steps"] = wheels;
    result_["layout_mouse_drags"] = layout_drags; result_["pointer_moves"] = pointer_moves;
    write(directory_ / "result.json", result_.dump(2));
  }
  int clicks = 0, wheels = 0, layout_drags = 0, pointer_moves = 0;
 private:
  void check_native_scroll() const
  {
    std::string error;
    require(scroll_guard_.check(error), error);
  }
  void click_point(ui::Vec2 p)
  {
    wm::Event e; e.x = int(p.x); e.y = window_.height() - 1 - int(p.y);
    e.type = wm::EventType::MouseMove; event(e);
    e.type = wm::EventType::MouseDown; e.button = wm::MouseButton::Left; event(e);
    e.type = wm::EventType::MouseUp; event(e); frame();
  }
  void keypress_tab_choice(int index)
  {
    key(wm::Key::Home); for (int i = 0; i < index; ++i) { key(wm::Key::DownArrow); } key(wm::Key::Enter);
  }
  wm::WindowManager &manager_; wm::Window &window_; wm::Screen &screen_;
  Json &result_; fs::path directory_;
  reports_native_test::ScrollGuard scroll_guard_;
};

void run(const Options &options, Json &result, const fs::path &directory)
{
  const auto environment = document_preview::native_evidence_environment_error();
  require(environment.empty(), environment);
  std::fputs("STK_NATIVE_STAGE name=reports.after-environment-probe\n", stdout); std::fflush(stdout);
  gfx::Backend backend; std::string error;
  require(gfx::resolve_backend(options.backend, backend, error), error);
  std::fputs("STK_NATIVE_STAGE name=reports.app-shell.before\n", stdout); std::fflush(stdout);
  app::AppShell shell({.language = "en", .interactive = false});
  std::fputs("STK_NATIVE_STAGE name=reports.app-shell.after\n", stdout); std::fflush(stdout);
  wm::WmOptions wm_options; wm_options.gpu.backend = backend;
  wm_options.window = {"STK public frozen report native acceptance", 1440, 1000, false};
  std::fputs("STK_NATIVE_STAGE name=reports.window-manager.before\n", stdout); std::fflush(stdout);
  auto manager = wm::WindowManager::create(wm_options, error);
  std::fputs("STK_NATIVE_STAGE name=reports.window-manager.after\n", stdout); std::fflush(stdout);
  require(bool(manager), error);
  auto *window = manager->main_window(); auto &screen = window->screen();
  result["system_backend"] = manager->system_backend();
  result["gpu_backend"] = manager->gpu().backend_name();
  result["initial_client_size"] = {window->width(), window->height()};
  shell.install(screen, window); shell.build_default_layout(screen);
  auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a3"));
  require(area && area->set_tabs({app::kEditorReports, app::kEditorPython}, 1), "Production Reports/Python tabs");
  area->set_sidebar_open(false); area->set_toolbar_open(false);
  struct RedrawTimer {
    wm::WindowManager &manager; uint64_t id;
    void reset() { if (id) { manager.remove_timer(id); id = 0; } }
    ~RedrawTimer() { reset(); }
  } redraw_timer{*manager, manager->add_timer(50, 50, [window] { window->request_redraw(); })};
  require(redraw_timer.id != 0, "Cannot install bounded-wait redraw timer");
  Exercise ui(*manager, *window, result, directory);
  ui.enlarge_report_row(*area);
  const auto scratch = directory / "public-fixture"; fs::create_directory(scratch);
  const auto trace = scratch / "calls.jsonl";
  const auto wrapper = scratch / "observe.py";
  write(wrapper, R"PY(from pathlib import Path
import base64, hashlib, json, sys
from suan.desktop_bridge.projects import ProjectSessions
from suan.desktop_bridge.__main__ import main
trace = Path(sys.argv.pop(1))
original = ProjectSessions.reports
def observed(self, action, params):
    result = original(self, action, params)
    if action in ('asset', 'preview', 'preview_resources'):
        item = {'action': action}
        if action == 'preview_resources':
            item.update({k: result['preview'][k] for k in ('project_id', 'report_id', 'source_sha256', 'session_id')})
        elif action == 'preview':
            item.update({k: result[k] for k in ('revision', 'project_id', 'report_id', 'source_sha256', 'session_id',
                'path', 'renderer', 'mime', 'source_mime', 'content_sha256', 'source_content_sha256', 'size', 'source_size')})
            data = base64.b64decode(result['data'], validate=True)
            item.update(data_sha256=hashlib.sha256(data).hexdigest(), data_size=len(data))
        elif action == 'asset':
            item.update({k: result[k] for k in ('project_id', 'report_id', 'source_sha256', 'path', 'content_sha256', 'size')})
        with trace.open('a', encoding='utf-8') as output:
            output.write(json.dumps(item) + '\n')
    return result
ProjectSessions.reports = observed
raise SystemExit(main())
)PY");
  bridge::ClientOptions connection;
  connection.python.configured = options.python; connection.executor = manager->executor();
  connection.state_dir = core::path_to_utf8(scratch / "bridge"); connection.cache_dir = core::path_to_utf8(scratch / "cache");
  connection.command = {options.python, "-u", core::path_to_utf8(wrapper), core::path_to_utf8(trace), "--stdio", "--strict",
      "--state-dir", connection.state_dir, "--cache-dir", connection.cache_dir};
  connection.env["PYTHONPATH"] = STK_REPO_ROOT;
  connection.env["STK_STATE_DIR"] = core::path_to_utf8(scratch / "runtime");
  connection.env["STK_PROFILES_FILE"] = core::path_to_utf8(scratch / "profiles.json");
  connection.env["STK_TOKEN_PLAN_API_KEY"] = ""; connection.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
  connection.strict = connection.validate = true;
  auto client = bridge::Client::create(connection);
  struct Cleanup {
    app::AppShell &shell; bridge::Client &client; wm::WindowManager &manager; wm::Window *window;
    RedrawTimer &timer;
    ~Cleanup() {
      timer.reset();
      shell.store().project().attach(nullptr); shell.store().set_bridge(nullptr); client.close();
      shell.store().viewer().close(); manager.close_window(window);
    }
  } cleanup{shell, *client, *manager, window, redraw_timer};
  shell.store().set_bridge(client.get()); app::BridgeStatus bridge_status(shell.store(), *client, manager.get());
  require(client->start(&error), error);
  ui.wait([&] { return client->state() == bridge::BridgeState::Ready; }, "Python bridge", 60);
  auto call = [&](const std::string &method, Json params) {
    auto reply = std::make_shared<std::optional<bridge::Result<Json>>>();
    auto future = client->call(method, params); future.then([reply](auto value) { *reply = std::move(value); });
    ui.wait([&] { return reply->has_value(); }, method);
    require(reply->value().ok(), method + ": " + (reply->value() ? "" : reply->value().error().describe()));
    return reply->value().value();
  };
  auto &project = shell.store().project();
  // Client::Ready precedes its queued UI listeners; wait for the project controller as well.
  ui.wait([&] { project.sync(); return project.ready() && !project.busy(); }, "Project UI ready", 60);
  const auto folder = scratch / "project";
  if (!project.create(core::path_to_utf8(folder), "Public synthetic native report")) {
    const auto hello = client->hello_info();
    const Json diagnostics = {{"project_error", project.error()}, {"project_ready", project.ready()},
                              {"project_busy", project.busy()},
                              {"project_apply", hello && hello->has_method("project.apply")}};
    require(false, "Create fixture project: " + diagnostics.dump());
  }
  ui.wait([&] { return project.loaded() && !project.busy(); }, "Project loaded");
  const auto handle = project.project()->handle;
  const bool pdf = options.source == "pdf";
  const std::string entry = pdf ? "report.pdf" : options.source == "html" ? "report.html" : "report.md";
  const std::string body_marker = "██  ████  ███  █████\n█████  ██  ████  ███\n███  █████  ██  ████";
  const std::string source_bytes = pdf ? document_preview::make_pdf_fixture() : options.source == "html" ?
      "<!doctype html><html><body><img src='marker.png' alt='Native evidence marker'><pre>" + body_marker +
      "</pre><h1>Frozen HTML report</h1><p>Public synthetic values: A 300 K; B 325 K.</p></body></html>" :
      "![Native evidence marker](marker.png)\n\n```text\n" + body_marker +
      "\n```\n\n# Frozen Markdown report\n\n| Sample | Temperature / K |\n| --- | --- |\n| A | 300 |\n| B | 325 |\n";
  write(folder / entry, source_bytes);
  Json paths = Json::array({core::path_to_utf8(folder / entry)});
  if (!pdf) { io::write_png(folder / "marker.png", marker()); paths.push_back(core::path_to_utf8(folder / "marker.png")); }
  const auto indexed = call("project.files.index", {{"handle", handle}, {"expected_revision", 0},
      {"paths", paths}});
  const auto ids = indexed.at("record_ids");
  const auto snapshot = call("project.snapshots.capture", {{"handle", handle}, {"record_ids", ids}, {"expected_revision", 1}});
  Json report_assets = Json::array({{{"record_id", ids.at(0)}, {"path", entry}}});
  if (!pdf) { report_assets.push_back({{"record_id", ids.at(1)}, {"path", "marker.png"}}); }
  call("project.reports.create", {{"handle", handle}, {"report_id", kReport}, {"name", "Frozen native acceptance"},
      {"snapshot_id", snapshot.at("snapshot").at("id")}, {"entry_record_id", ids.at(0)}, {"expected_revision", 2},
      {"assets", report_assets},
      {"sources", Json::array()}});
  const auto report = call("project.reports.get", {{"handle", handle}, {"report_id", kReport}}).at("report");
  require(fs::remove(folder / entry) && (pdf || fs::remove(folder / "marker.png")), "Delete live source after freezing");
  project.refresh(); ui.wait([&] { return project.loaded() && !project.busy(); }, "Frozen project refresh");
  require(project.project()->revision == 3, "Expected exact fixture revision");
  auto &viewer = shell.store().viewer(); viewer.set_auto_evaluate(false); viewer.prefetch_neighbours = false;
  viewer.open_payload(std::make_shared<io::Payload>(io::read_stkp(
      std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp")), "Public existing Viewer fixture");
  // Normal Viewer catalog replies are unrelated to report reading. Complete them before
  // freezing the preservation baseline, so a late read-only reply cannot look like a mutation.
  viewer.refresh_metadata();
  ui.wait([&] { return viewer.presets_loaded() && !viewer.catalog().is_null() && viewer.colormaps(); },
      "Viewer metadata baseline");
  const auto viewer_state = viewer.save_workspace_state();
  const auto camera = viewer.camera_serial(), payload = viewer.payload_serial();
  const auto history = call("project.history", {{"handle", handle}});
  ui.frame();
  auto *viewer_area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
  require(viewer_area && viewer_area->editor().type().id == app::kEditorViewer, "Viewer remains in the starting layout");
  const auto viewer_editor_state = viewer_area->editor().save_workspace_state();
  ui.click("python_source", *area);
#ifdef __APPLE__
  ui.key(wm::Key::A, wm::ModOS);
#else
  ui.key(wm::Key::A, wm::ModCtrl);
#endif
  const std::string draft = "print('retained public synthetic draft')";
  ui.text(draft); ui.click("python_output_open", *area);
  const auto draft_state = area->tab(1).save_workspace_state();
  require(area->tab(1).has_unsaved_changes() && draft_state.at("source") == draft, "Exact unsaved Python draft");
  ui.tab(*area, 0); ui.clicks = ui.wheels = 0;
  ui.wait([&] { const auto *w = ui.widget("reports_list"); return w && w->list && w->list->count == 1 && w->enabled; }, "Report list");
  require(!fs::exists(trace), "Opening Reports must not prepare/read any content");
  ui.click("reports_list", *area, 0);
  ui.wait([&] { const auto *w = ui.widget("reports_preview"); return w && w->enabled; }, "Selected report metadata");
  require(!fs::exists(trace), "Selecting a report must not prepare/read any content");
  result["project_id"] = project.project()->id; result["report_id"] = kReport;
  result["source_sha256"] = report.at("source_sha256"); result["source_kind"] = options.source;
  result["body_text_pixel_criterion"] = pdf ? "not applied: PDF page identities use independent page-embedded RGB stripes" :
      "Three aligned 20-column U+2588/space rows, independently required beside the frozen PNG";
  result["required_images"] = pdf ? 160 : 140;
  result["starting_layout"] = "Actual client size recorded; default a3 Reports/Python with one recorded upper-row splitter drag; Viewer stays beside report; Reports selected by one mouse click";
  auto ready = [&] {
    const auto *v = ui.widget("reports_document_viewport"), *f = ui.widget("reports_document_focus");
    return v && v->type == ui::WidgetType::NativeViewport && ui.visible(v) && f && f->enabled &&
        !screen.ui()->native_view_interaction_blocked();
  };
  ui.click("reports_preview", *area); ui.wait(ready, "Production native report ready");
  result["initial_reading_clicks"] = ui.clicks;
  for (int cycle = 1; cycle <= 20; ++cycle) {
    ui.wait(ready, "Native report visible");
    const auto bounds = ui.widget("reports_document_viewport")->rect;
    require(bounds.h >= 10.0f * screen.ui()->style().unit,
        "Actual native viewport is too short for the complete three-line body fixture");
    ui.capture(cycle, "visible-page1", 1, bounds, !pdf);
    if (pdf) { ui.capture(cycle, "scrolled-page2", 2, bounds, false, true); }
    const int retained_page = pdf ? 2 : 1;
    ui.tab(*area, 1); ui.capture(cycle, "hidden-tab", 0, bounds, !pdf);
    require(area->tab(1).save_workspace_state() == draft_state, "Tab change must preserve exact Python draft");
    ui.tab(*area, 0); ui.wait(ready, "Report shown again"); ui.capture(cycle, "reshown", retained_page, bounds, !pdf);
    ui.click(area->area_menu_key(), *area);
    require(screen.ui()->popup_open(), "Area menu opens through actual mouse routing");
    ui.capture(cycle, "popup", 0, bounds, !pdf);
    ui.key(wm::Key::Esc);
    // Leaving the pointer over the menu button creates its tooltip on the next
    // frame. All tooltips deliberately hide the production child, even outside
    // this viewport; move to its passive interior before awaiting visible pixels.
    ui.move_pointer({bounds.cx(), bounds.cy()});
    ui.wait([&] { return ready() && !screen.ui()->popup_open(); }, "Report returns after popup and tooltip");
    ui.capture(cycle, "after-popup", retained_page, bounds, !pdf);
    ui.click("reports_document_close", *area); ui.capture(cycle, "closed", 0, bounds, !pdf);
    ui.wait([&] { const auto *w = ui.widget("reports_preview"); return w && w->enabled; }, "Explicit reopen action");
    ui.click("reports_preview", *area); ui.wait(ready, "Explicit prepare creates next native preview");
    ui.capture(cycle, "reprepared-page1", 1, ui.widget("reports_document_viewport")->rect, !pdf);
    result["completed_cycles"] = cycle; ui.save();
  }
  std::set<std::string> sessions;
  const auto &assets = report.at("manifest").at("assets");
  const auto image_asset = std::find_if(assets.begin(), assets.end(), [](const Json &asset) {
    return asset.at("path") == "marker.png";
  });
  const auto entry_asset = std::find_if(assets.begin(), assets.end(), [&](const Json &asset) { return asset.at("path") == entry; });
  require(entry_asset != assets.end() && entry_asset->at("sha256") == core::Sha256::hex(source_bytes) &&
      entry_asset->at("size") == source_bytes.size(), "Frozen entry must match the complete fixture bytes");
  require(pdf ? assets.size() == 1 : image_asset != assets.end(), "Exact frozen report asset set");
  std::ifstream calls(trace); std::string line; int prepares = 0, image_reads = 0;
  bool awaiting_image = false;
  while (std::getline(calls, line)) {
    const auto item = Json::parse(line);
    require(item.at("project_id") == project.project()->id && item.at("report_id") == kReport &&
        item.at("source_sha256") == report.at("source_sha256"), "Every preparation must bind the frozen report");
    if (pdf) {
      require(item.at("action") == "preview" && item.at("revision") == 3 && item.at("path") == entry &&
          item.at("renderer") == "identity" && item.at("mime") == "application/pdf" &&
          item.at("source_mime") == "application/pdf" && item.at("content_sha256") == entry_asset->at("sha256") &&
          item.at("source_content_sha256") == entry_asset->at("sha256") && item.at("data_sha256") == entry_asset->at("sha256") &&
          item.at("size") == entry_asset->at("size") && item.at("source_size") == entry_asset->at("size") &&
          item.at("data_size") == entry_asset->at("size"), "PDF prepare must return exact frozen identity and complete binary bytes");
      ++prepares;
      require(sessions.insert(item.at("session_id").get<std::string>()).second, "PDF reprepare requires a fresh session");
    }
    else if (item.at("action") == "preview_resources") {
      require(!awaiting_image, "Each preparation must finish its explicit frozen image read");
      ++prepares; awaiting_image = true;
      require(sessions.insert(item.at("session_id").get<std::string>()).second, "Explicit reprepare requires a new session");
    }
    else {
      require(item.at("action") == "asset" && awaiting_image && item.at("path") == "marker.png" &&
          item.at("content_sha256") == image_asset->at("sha256") && item.at("size") == image_asset->at("size"),
          "Preparation may read only its single frozen image; no raw entry read or independent preview");
      ++image_reads; awaiting_image = false;
    }
  }
  require(prepares == 21 && image_reads == (pdf ? 0 : 21) && !awaiting_image,
      "Exactly 21 explicit preparations; PDF has no asset/preview_resources calls, text has one image read per prepare");
  require(area->tab(1).save_workspace_state() == draft_state && area->tab(1).has_unsaved_changes() &&
      shell.store().scripts().history().empty(), "Reading must preserve hidden unexecuted Python draft");
  require(viewer.save_workspace_state() == viewer_state && viewer.camera_serial() == camera &&
      viewer.payload_serial() == payload && viewer.evaluations_started() == 0 &&
      viewer_area->editor().save_workspace_state() == viewer_editor_state, "Viewer payload and per-window camera must remain unchanged");
  require(call("project.history", {{"handle", handle}}) == history, "Reading must not edit project history");
  for (const auto *method : {"project.runs.list", "project.analysis_runs.list", "project.workflow_runs.list"}) {
    require(call(method, {{"handle", handle}}).at("runs").empty(), "No simulation, workflow or analysis may run");
  }
  require(client->stats().schema_violations == 0, "Bridge schema violations");
  require(result.at("images").size() == (pdf ? 160 : 140) && result.at("completed_cycles") == 20,
      "All 20 production reading cycles and the source-specific OS observation count must complete");
  require(pdf ? result.at("native_scroll_requests").size() >= 20 : result.at("native_scroll_requests").empty(),
      "Each PDF cycle requires native wheel input; text acceptance must not claim native scrolling");
  result["explicit_preparations"] = prepares; result["frozen_image_reads"] = image_reads;
  result["unique_sessions"] = sessions.size();
  result["actual_mouse_clicks"] = ui.clicks; result["wheel_steps"] = ui.wheels;
  result["viewer_preserved"] = true; result["python_draft_preserved"] = true;
  result["status"] = "capture_complete"; ui.save();
}
}  // namespace

int main(int argc, char **argv)
{
  Options options;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (i + 1 >= argc) { return 2; }
    if (arg == "--python") { options.python = argv[++i]; }
    else if (arg == "--gpu-backend") { options.backend = argv[++i]; }
    else if (arg == "--evidence-dir") { options.output = core::path_from_utf8(argv[++i]); }
    else if (arg == "--source") { options.source = argv[++i]; }
    else { return 2; }
  }
  if (options.python.empty() || options.output.empty() ||
      (options.source != "markdown" && options.source != "html" && options.source != "pdf")) {
    std::fprintf(stderr, "usage: stk-reports-native-window --python PATH --gpu-backend BACKEND --evidence-dir DIR --source markdown|html|pdf\n"); return 2;
  }
  Json result = {{"format", "stk.reports-native-evidence/1"}, {"status", "running"}, {"required_cycles", 20},
      {"completed_cycles", 0}, {"images", Json::array()}, {"native_scroll_requests", Json::array()},
      {"claim", "Production ReportsEditor mouse actions, frozen bridge resources and OS-composited STK client pixels"},
      {"not_proven_here", "OS hardware input, IME, arbitrary PDF fidelity/search/selection, modal same-OS-batch ordering, physical scanout and browser memory stability; URL410/parent-close are separate Host CPU and spike native tests; final guarded memory is the separate after-static spike gate"}};
  fs::path directory;
  try {
    fs::create_directories(options.output);
    directory = options.output / ("run-" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count()));
    require(fs::create_directory(directory), "Evidence run directory must be new");
    write(directory / "result.json", result.dump(2));
    { gfx::Runtime runtime; run(options, result, directory); }
    // The window, bridge, manager and Runtime have now returned from normal destruction.
    // Engine static destructors and the final guarded leak gate belong to the separate spike.
    result["status"] = "passed";
    write(directory / "result.json", result.dump(2));
    std::fprintf(stdout, "PASS: production ReportsEditor native evidence; cycles=20; OS images=%zu; %s\n",
        result.at("images").size(), core::path_to_utf8(directory).c_str());
    return 0;
  }
  catch (const std::exception &error) {
    std::fprintf(stderr, "FAIL: %s\n", error.what());
    log_last_observation(result);
    try {
      result["status"] = "failed"; result["error"] = error.what();
      if (!directory.empty()) { write(directory / "result.json", result.dump(2)); }
    }
    catch (...) {}
    return 1;
  }
}
