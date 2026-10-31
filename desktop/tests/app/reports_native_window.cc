/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Production ReportsEditor -> real bridge -> production native Host -> OS client capture.
 * Synthetic fixtures only. App controls use normal Screen routing. The opt-in media tests
 * also deliver bounded local user events to this window's native child, never global hardware
 * input. Fixed read-only probes supplement independent OS pixels; no direct Host construction,
 * renderer injection or offscreen proof is accepted. */
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
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
#  include "stk/document/test_media_probe.hh"
#  include "reports_native_input.hh"
#endif

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iterator>
#include <optional>
#include <set>
#include <stdexcept>

using namespace stk;
using io::Json;
namespace fs = std::filesystem;
namespace {
constexpr const char *kReport = "a1111111-1111-4111-8111-111111111111";
constexpr const char *kMediaSha256 = "a54fb5baf8ca34545a8e31ea46c8801347db722cc9c876279186ab8c94f860d1";
using Clock = std::chrono::steady_clock;
void require(bool ok, const std::string &message) { if (!ok) { throw std::runtime_error(message); } }
void write(const fs::path &path, const std::string &text)
{
  std::ofstream out(path, std::ios::binary);
  out.write(text.data(), std::streamsize(text.size()));
  require(out.good(), "Cannot write public fixture/evidence: " + core::path_to_utf8(path));
}
struct Options { std::string python, backend, source = "markdown"; fs::path output, media_fixture; };
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
using Media = document_preview::test::MediaSnapshot;
Json media_json(const Media &media)
{
  return {{"paused", media.paused}, {"ended", media.ended}, {"seeking", media.seeking},
      {"current_time", media.current_time}, {"duration_known", media.duration_known},
      {"duration", media.duration}, {"ready_state", media.ready_state},
      {"network_state", media.network_state}, {"error_code", media.error_code},
      {"video_size", {media.video_width, media.video_height}},
      {"video_rect_css", {media.rect_x, media.rect_y, media.rect_width, media.rect_height}},
      {"viewport_size_css", {media.viewport_width, media.viewport_height}},
      {"navigation_generation", media.navigation_generation}};
}
#  ifdef __APPLE__
Json activation_json(const reports_native_test::WindowActivationObservation &observed)
{
  return {{"policy", observed.policy}, {"main_thread", observed.main_thread},
      {"valid_target", observed.valid_target}, {"own_window", observed.own_window},
      {"app_active", observed.app_active}, {"window_key", observed.window_key},
      {"exact_key_window", observed.exact_key_window}, {"visible", observed.visible},
      {"miniaturized", observed.miniaturized}, {"can_become_key", observed.can_become_key}};
}
#  endif
#endif

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
    result_["layout_preparation"] = {{"action", "one mouse drag of default upper-row/table splitter"},
        {"client_size", {window_.width(), window_.height()}},
        {"report_area_before_bottom_left", {before.xmin, before.ymin, before.width(), before.height()}},
        {"drag_from_bottom_left", {x, from_y}}, {"drag_to_bottom_left", {x, to_y}}};
    const auto record = [&](const char *phase) {
      result_["layout_preparation"][phase] = input_state(); save();
    };
    record("before_down");
    wm::Event e; e.x = x; e.y = from_y; e.type = wm::EventType::MouseMove; event(e);
    e.type = wm::EventType::MouseDown; e.button = wm::MouseButton::Left; event(e);
    record("after_down"); frame(); record("after_down_frame");
    require(screen_.capture() == wm::Screen::Capture::Splitter, "Mouse must capture the row splitter");
    e.type = wm::EventType::MouseMove; e.y = to_y; event(e); frame(); record("after_move_frame");
    e.type = wm::EventType::MouseUp; event(e); frame(); record("after_up_frame");
    ++layout_drags;
    require(screen_.capture() == wm::Screen::Capture::None && area.rect().height() > before.height(),
        "Actual row drag must enlarge the report area and release capture");
    const auto after = area.rect();
    result_["layout_preparation"]["report_area_after_bottom_left"] =
        {after.xmin, after.ymin, after.width(), after.height()};
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
  Json input_state() const
  {
    const auto *context = screen_.ui();
    return {{"screen_capture", int(screen_.capture())}, {"frames_drawn", window_.frames_drawn()},
        {"ui_editing", context && context->editing() != 0},
        {"ui_popup_open", context && context->popup_open()},
        {"native_interaction_blocked", context && context->native_view_interaction_blocked()}};
  }
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
#  ifdef __APPLE__
  void activate_native_window()
  {
    std::string error;
    reports_native_test::WindowActivationRequest request;
    reports_native_test::WindowActivationObservation last;
    size_t observations = 0;
    bool confirmed = false;
    const auto start = Clock::now();
    const auto record = [&] {
      result_["native_window_activation_observation"] = {
          {"before_request", activation_json(request.before)},
          {"after_request", activation_json(request.after)},
          {"final_observation", activation_json(last)},
          {"policy_change_attempted", request.policy_change_attempted},
          {"policy_change_succeeded", request.policy_change_succeeded},
          {"policy_after_change", request.policy_after_change},
          {"activation_requested", request.activation_requested}, {"confirmed", confirmed},
          {"observation_count", observations}, {"deadline_seconds", 5},
          {"elapsed_seconds", std::chrono::duration<double>(Clock::now() - start).count()}};
      save();
    };
    try {
      const bool requested = native_input_.request_window_activation(
          window_.native_window_handle(), request, error);
      last = request.after;
      require(requested, error);
      wait([&] {
        ++observations;
        const bool active = native_input_.window_is_active(window_.native_window_handle(), last, error);
        require(error.empty(), error);
        return active;
      }, "Explicit own-window activation before fixture layout and native media inputs", 5);
      confirmed = true;
    }
    catch (...) { record(); throw; }
    result_["native_window_activation"] = "Explicit request, then UI-loop observation of active application and exact key window; no key sent";
    record();
  }
#  endif
  Media media(const std::string &session)
  {
    auto reply = std::make_shared<std::optional<document_preview::test::MediaProbeResult>>();
    std::string error;
    require(document_preview::test::probe_media(window_.native_window_handle(), session,
        [reply](auto result) { *reply = std::move(result); }, error), error);
    wait([&] { return reply->has_value(); }, "Fixed native media observation", 10);
    require(reply->value().ok, reply->value().error);
    const auto observed = reply->value().media;
    require(observed.error_code == 0, "System media decoder reported an error");
    return observed;
  }
  Media media_until(const std::string &session, const std::function<bool(const Media &)> &predicate,
                    const std::string &reason, double seconds = 10)
  {
    Media observed;
    wait([&] { observed = media(session); return predicate(observed); }, reason, seconds);
    return observed;
  }
  Media observe_input(const std::string &session, const std::function<bool(const Media &)> &predicate,
                       double seconds = 0.60)
  {
    const auto start = Clock::now();
    Media observed;
    wait([&] {
      observed = media(session);
      return predicate(observed) || std::chrono::duration<double>(Clock::now() - start).count() >= seconds;
    }, "Bounded native input observation", seconds + 10);
    return observed;
  }
  Media held_media(int cycle, const std::string &phase, const std::string &session,
                   const Media &before, double seconds)
  {
    const auto start = Clock::now();
    Media after;
    wait([&] {
      after = media(session);
      require(after.navigation_generation == before.navigation_generation && after.paused && !after.ended &&
          !after.seeking && std::abs(after.current_time - before.current_time) <= 0.10,
          "Paused media advanced, resumed, ended or changed navigation during " + phase);
      return std::chrono::duration<double>(Clock::now() - start).count() >= seconds;
    }, "Paused media hold " + phase, seconds + 10);
    result_["media_holds"].push_back({{"cycle", cycle}, {"phase", phase},
        {"observed_wall_seconds", std::chrono::duration<double>(Clock::now() - start).count()},
        {"before", media_json(before)}, {"after", media_json(after)}});
    save(); return after;
  }
  std::shared_ptr<document_preview::ResourceSession> media_session(const std::string &session)
  {
    std::string error;
    auto resources = document_preview::test::resource_session(window_.native_window_handle(), session, error);
    require(bool(resources) && resources->active(), error.empty() ? "Missing actual native resource session" : error);
    return resources;
  }
  void native_media_click(int cycle, const std::string &phase, ui::Rect bounds, const Media &observed,
                          double x, double y)
  {
    // Parent UI hover state is independent of the native child's local input. Leave
    // toolbar buttons so their delayed tooltip cannot hide/pause the playing child.
    move_pointer({bounds.cx(), bounds.cy()});
    require(observed.viewport_width > 0 && observed.viewport_height > 0 &&
        observed.rect_width > 0 && observed.rect_height > 0, "Media control geometry must be observed");
    const double nx = (observed.rect_x + observed.rect_width * x) / observed.viewport_width;
    const double ny = (observed.rect_y + observed.rect_height * y) / observed.viewport_height;
    const auto viewport = native_bounds(bounds);
    std::string delivery, error;
    require(native_input_.click_document(window_.native_window_handle(), viewport, window_.width(),
        window_.height(), nx, ny, delivery, error), error);
    result_["native_media_inputs"].push_back({{"cycle", cycle}, {"phase", phase}, {"action", "click"},
        {"video_normalized_top_left", {x, y}}, {"viewport_normalized_top_left", {nx, ny}},
        {"delivery", delivery}, {"before", media_json(observed)}});
    save(); process();
  }
  void native_media_key(int cycle, const std::string &phase, ui::Rect bounds, wm::Key key,
                        const char *name, const Media &before)
  {
    move_pointer({bounds.cx(), bounds.cy()});
    std::string delivery, error;
    require(native_input_.key_document(window_.native_window_handle(), native_bounds(bounds),
        window_.width(), window_.height(), key, delivery, error), error);
    result_["native_media_inputs"].push_back({{"cycle", cycle}, {"phase", phase}, {"action", "key"},
        {"key", name}, {"delivery", delivery}, {"before", media_json(before)}});
    save(); process();
  }
#  ifdef __APPLE__
  void native_media_seek(int cycle, const std::string &phase, ui::Rect bounds, const Media &before,
                         double fraction)
  {
    move_pointer({bounds.cx(), bounds.cy()});
    require(before.paused && before.duration_known && before.duration > 0 &&
        before.viewport_width > 0 && before.viewport_height > 0,
        "Native timeline lookup requires observed paused media geometry and duration");
    const reports_native_test::TimelineInput input{before.rect_x / before.viewport_width,
        before.rect_y / before.viewport_height, before.rect_width / before.viewport_width,
        before.rect_height / before.viewport_height, before.current_time, before.duration, fraction};
    // A first accessibility read may enable WebKit's tree asynchronously. Repeat
    // only an empty completed read, never a partially delivered input or a limit
    // failure. All successful input still has to pass unchanged DOM/OS gates.
    for (int attempt = 0; attempt < 4; ++attempt) {
      reports_native_test::TimelineObservation observed;
      std::string delivery, error;
      const bool sent = native_input_.seek_document(window_.native_window_handle(), native_bounds(bounds),
          window_.width(), window_.height(), input, observed, delivery, error);
      result_["native_media_inputs"].push_back({{"cycle", cycle}, {"phase", phase},
          {"action", "observed-timeline-click"}, {"lookup_attempt", attempt + 1},
          {"lookup_complete", observed.lookup_complete}, {"visited_nodes", observed.visited_nodes},
          {"deepest_node", observed.deepest_node}, {"sliders", observed.sliders},
          {"time_matched_candidates", observed.candidates},
          {"slider_screen_points_bottom_left", {observed.screen_x, observed.screen_y,
              observed.screen_width, observed.screen_height}},
          {"slider_range_value", {observed.minimum, observed.maximum, observed.value}},
          {"target_fraction", fraction}, {"viewport_normalized_top_left",
              {observed.normalized_x, observed.normalized_y}}, {"delivered", sent},
          {"delivery", delivery}, {"error", error}, {"before", media_json(before)}});
      save();
      if (sent) { process(); return; }
      require(observed.lookup_complete && observed.candidates == 0 && attempt < 3, error);
      frame();
    }
  }
#  endif
  Media fit_decoded_media(app::EditorArea &area, app::EditorArea &viewer_area,
                          const std::string &session, Media observed)
  {
    // A decoded HTML video can be taller than its preload=none placeholder.
    // Resize the actual report/Viewer divider while paused; keep the renderer,
    // document bytes and complete-element pixel criterion unchanged.
    const auto original = observed;
    for (int attempt = 0; attempt <= 3; ++attempt) {
      if (observed.rect_x >= -0.5 && observed.rect_y >= -0.5 &&
          observed.rect_x + observed.rect_width <= observed.viewport_width + 0.5 &&
          observed.rect_y + observed.rect_height <= observed.viewport_height + 0.5) { return observed; }
      require(attempt < 3, "Complete decoded media did not fit after bounded real layout drags");
      require(observed.paused && observed.ready_state >= 2 && observed.rect_width >= 100 &&
          observed.rect_height >= 75 && observed.viewport_width > 0 && observed.rect_x >= 0,
          "Only a decoded, paused media element can guide a real layout drag");
      const double available_height = observed.viewport_height - observed.rect_y - 2.0;
      const double video_width = std::floor(available_height * observed.rect_width / observed.rect_height);
      require(available_height >= 75 && video_width >= 100,
          "Actual client is too short to contain the full decoded video");
      const double target_width = 2 * observed.rect_x + video_width;
      const auto *viewport = widget("reports_document_viewport");
      require(viewport && target_width < observed.viewport_width,
          "Decoded media needs a narrower actual report viewport");
      const double pixels_per_css = viewport->rect.w / observed.viewport_width;
      const int shrink = int(std::ceil((observed.viewport_width - target_width) * pixels_per_css));
      auto *row = area.node() ? area.node()->parent : nullptr;
      require(row && row->dir == wm::SplitDir::Horizontal && row->children.size() == 2,
          "Expected report and retained Viewer in the same two-child row");
      const bool report_left = row->children[0].get() == area.node();
      require(row->children[report_left ? 0 : 1].get() == area.node() &&
          row->children[report_left ? 1 : 0]->area.get() == &viewer_area &&
          viewer_area.editor().type().id == app::kEditorViewer,
          "The report divider must retain the original adjacent Viewer");
      const auto splitter = std::find_if(screen_.splitters().begin(), screen_.splitters().end(),
          [row](const wm::Splitter &s) { return s.node == row && s.index == 0; });
      require(splitter != screen_.splitters().end(), "Report/Viewer divider must exist");
      const auto before = area.rect();
      const auto viewer_before = viewer_area.rect();
      const int delta = report_left ? -shrink : shrink;
      const int from_x = (splitter->rect.xmin + splitter->rect.xmax) / 2;
      const int y = (splitter->rect.ymin + splitter->rect.ymax) / 2;
      result_["decoded_media_layout_drags"].push_back({{"before", media_json(observed)},
          {"shrink_framebuffer_pixels", shrink}, {"requested_viewport_css_width", target_width},
          {"report_child_index", report_left ? 0 : 1}, {"divider_delta_framebuffer_pixels", delta},
          {"report_width_before", before.width()}, {"viewer_width_before", viewer_before.width()},
          {"before_down", input_state()}});
      const auto record = [&](const char *phase) {
        auto &item = result_["decoded_media_layout_drags"].back();
        item[phase] = input_state();
        item["report_width_after"] = area.rect().width();
        item["viewer_width_after"] = viewer_area.rect().width(); save();
      };
      wm::Event e; e.x = from_x; e.y = y; e.type = wm::EventType::MouseMove; event(e);
      e.type = wm::EventType::MouseDown; e.button = wm::MouseButton::Left; event(e);
      record("after_down"); frame(); record("after_down_frame");
      require(screen_.capture() == wm::Screen::Capture::Splitter, "Mouse must capture report/Viewer divider");
      e.type = wm::EventType::MouseMove; e.x += delta; event(e); frame(); record("after_move_frame");
      e.type = wm::EventType::MouseUp; event(e); frame(); record("after_up_frame");
      ++layout_drags;
      require(screen_.capture() == wm::Screen::Capture::None && area.rect().width() < before.width() &&
          viewer_area.rect().width() > viewer_before.width(),
          "Actual divider drag must narrow the report, enlarge the retained Viewer and release capture");
      save();
      wait([&] { const auto *focus = widget("reports_document_focus");
        return focus && focus->enabled && widget("reports_document_viewport"); }, "Native viewport after real divider drag");
      observed = media(session);
      require(observed.paused && !observed.ended && !observed.seeking &&
          observed.navigation_generation == original.navigation_generation &&
          std::abs(observed.current_time - original.current_time) <= 0.10,
          "Layout resizing must preserve this paused navigation and playback time");
    }
    throw std::runtime_error("Complete decoded media did not fit after bounded real layout drags");
  }
  ui::Rect media_rectangle(ui::Rect bounds, const Media &observed) const
  {
    const auto native = native_bounds(bounds);
    require(observed.viewport_width > 0 && observed.viewport_height > 0 && observed.rect_width >= 100 &&
        observed.rect_height >= 75 && observed.rect_x >= -0.5 && observed.rect_y >= -0.5 &&
        observed.rect_x + observed.rect_width <= observed.viewport_width + 0.5 &&
        observed.rect_y + observed.rect_height <= observed.viewport_height + 0.5,
        "The complete native media element must fit inside its observed viewport");
    require(observed.video_width == 320 && observed.video_height == 180,
        "Decoded video dimensions must match the pinned public fixture");
    const double scale = std::min(observed.rect_width / observed.video_width,
        observed.rect_height / observed.video_height);
    const double width = scale * observed.video_width, height = scale * observed.video_height;
    // Standalone wrappers use object-fit:contain; ordinary HTML preserves intrinsic ratio.
    const double left = observed.rect_x + (observed.rect_width - width) * 0.5;
    const double top = observed.rect_y + (observed.rect_height - height) * 0.5;
    return {float(native.x + left / observed.viewport_width * native.width),
        float(window_.height() - native.y - native.height + top / observed.viewport_height * native.height),
        float(width / observed.viewport_width * native.width), float(height / observed.viewport_height * native.height)};
  }
  void media_capture(int cycle, const std::string &phase, int color, ui::Rect rectangle,
                     const Media &observed, const std::string &live_session = {})
  {
    // Observe the middle of the actual video, excluding native controls and letterbox edges.
    // Red/blue frames come from the pinned MP4 only; the HTML fixture has no poster/image.
    const int x = int(std::ceil(rectangle.x + rectangle.w * 0.15f));
    const int y = int(std::ceil(rectangle.y + rectangle.h * 0.20f));
    const int right = int(std::floor(rectangle.x + rectangle.w * 0.85f));
    const int bottom = int(std::floor(rectangle.y + rectangle.h * 0.65f));
    require(x >= 0 && y >= 0 && right <= window_.width() && bottom <= window_.height() &&
        right - x >= 32 && bottom - y >= 24, "Independent media pixel region must fit this STK client");
    std::unique_ptr<document_preview::WindowEvidenceCapture> pending;
    int consecutive = 0;
    wait([&] {
      if (!pending) { pending = document_preview::capture_window_evidence(window_.native_window_handle()); return false; }
      auto captured = pending->poll();
      if (!captured) { return false; } pending.reset();
      require(captured->error.empty(), "OS media client capture: " + captured->error);
      const auto &pixels = captured->image;
      require(pixels.channels == 4 && pixels.width == uint32_t(window_.width()) &&
          pixels.height == uint32_t(window_.height()), "Media OS capture must match this STK client framebuffer");
      Media current = observed;
      if (!live_session.empty()) {
        current = media(live_session);
        require(current.navigation_generation == observed.navigation_generation && current.paused &&
            !current.ended && !current.seeking && std::abs(current.current_time - observed.current_time) <= 0.10,
            "Media must remain paused at the observed time during each completed OS capture");
      }
      size_t red = 0, blue = 0, total = 0;
      for (int row = y; row < bottom; row += 2) for (int column = x; column < right; column += 2) {
        const auto *p = pixels.pixel(uint32_t(column), uint32_t(row)); ++total;
        if (p[0] >= 120 && p[0] >= int(p[1]) * 2 + 30 && p[0] >= int(p[2]) * 2 + 30) { ++red; }
        if (p[2] >= 120 && p[2] >= int(p[0]) * 2 + 30 && p[2] >= int(p[1]) * 2 + 30) { ++blue; }
      }
      const double red_fraction = double(red) / double(total), blue_fraction = double(blue) / double(total);
      const bool matched = color == 1 ? red_fraction >= 0.80 && blue_fraction <= 0.05 :
                           color == 2 ? blue_fraction >= 0.80 && red_fraction <= 0.05 :
                                        red_fraction <= 0.05 && blue_fraction <= 0.05;
      consecutive = matched ? consecutive + 1 : 0;
      const auto filename = "cycle-" + std::to_string(cycle) + "-" + phase +
          (consecutive >= 2 ? ".png" : "-waiting.png");
      const auto png = io::encode_png(pixels); io::write_png(directory_ / filename, pixels);
      result_["last_media_observation"] = {{"cycle", cycle}, {"phase", phase}, {"file", filename},
          {"sha256", core::Sha256::hex(png)}, {"backend", captured->backend},
          {"client_size", {pixels.width, pixels.height}}, {"sample_region_top_left", {x, y, right - x, bottom - y}},
          {"expected_color", color == 1 ? "red" : color == 2 ? "blue" : "neither"},
          {"red_fraction", red_fraction}, {"blue_fraction", blue_fraction},
          {"consecutive_matches", consecutive}, {"media_before_capture", media_json(observed)},
          {"live_pause_verified_at_capture", !live_session.empty()}, {"media_at_capture", media_json(current)}};
      if (consecutive >= 2) { result_["images"].push_back(result_["last_media_observation"]); }
      save(); return consecutive >= 2;
    }, "Independent OS media pixels " + phase, 25);
  }
#endif
  int clicks = 0, wheels = 0, layout_drags = 0, pointer_moves = 0;
 private:
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  document_preview::ViewBounds native_bounds(ui::Rect bounds) const
  {
    const auto r = screen_.rect();
    const int x = r.xmin + int(std::ceil(bounds.x));
    const int y = r.ymax - int(std::floor(bounds.y + bounds.h));
    return {x, y, r.xmin + int(std::floor(bounds.x + bounds.w)) - x,
        r.ymax - int(std::ceil(bounds.y)) - y};
  }
  reports_native_test::NativeInput native_input_;
#endif
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
#if defined(STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES) && defined(__APPLE__)
  // Confirm activation before the first layout mouseDown, not only after a
  // video is prepared: an intervening FocusOut cancels Screen pointer capture.
  ui.activate_native_window();
#endif
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
            preview = result['preview']
            item.update({k: preview[k] for k in ('revision', 'project_id', 'report_id', 'source_sha256', 'session_id',
                'path', 'renderer', 'mime', 'source_mime', 'content_sha256', 'source_content_sha256', 'size', 'source_size')})
            item['source_path'] = preview.get('source_path', preview['path'])
            data = base64.b64decode(preview['data'], validate=True)
            item.update(data_sha256=hashlib.sha256(data).hexdigest(), data_size=len(data),
                resources=result['resources'], total_size=result['total_size'])
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
  const bool video = options.source == "video" || options.source == "html-video";
  const bool html_video = options.source == "html-video";
  std::string media_bytes;
  if (video) {
    std::ifstream file(options.media_fixture, std::ios::binary);
    require(file.good(), "Pinned public MP4 fixture is required");
    media_bytes.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
    require(media_bytes.size() == 41558 && core::Sha256::hex(media_bytes) == kMediaSha256,
        "Public MP4 fixture must match the complete pinned H264/AAC bytes");
  }
  const std::string entry = pdf ? "report.pdf" : video ? html_video ? "report.html" : "clip.mp4" :
      options.source == "html" ? "report.html" : "report.md";
  const std::string body_marker = "██  ████  ███  █████\n█████  ██  ████  ███\n███  █████  ██  ████";
  const std::string source_bytes = video ? html_video ?
      "<!doctype html><html><body><video controls preload='none'>"
      "<source src='clip.mp4' type='video/mp4'></video></body></html>" : media_bytes :
      pdf ? document_preview::make_pdf_fixture() : options.source == "html" ?
      "<!doctype html><html><body><img src='marker.png' alt='Native evidence marker'><pre><code>" + body_marker +
      "</code></pre><h1>Frozen HTML report</h1><p>Public synthetic values: A 300 K; B 325 K.</p></body></html>" :
      "![Native evidence marker](marker.png)\n\n```text\n" + body_marker +
      "\n```\n\n# Frozen Markdown report\n\n| Sample | Temperature / K |\n| --- | --- |\n| A | 300 |\n| B | 325 |\n";
  write(folder / entry, source_bytes);
  Json paths = Json::array({core::path_to_utf8(folder / entry)});
  if (html_video) { write(folder / "clip.mp4", media_bytes); paths.push_back(core::path_to_utf8(folder / "clip.mp4")); }
  else if (!pdf && !video) { io::write_png(folder / "marker.png", marker()); paths.push_back(core::path_to_utf8(folder / "marker.png")); }
  const auto indexed = call("project.files.index", {{"handle", handle}, {"expected_revision", 0},
      {"paths", paths}});
  const auto ids = indexed.at("record_ids");
  const auto snapshot = call("project.snapshots.capture", {{"handle", handle}, {"record_ids", ids}, {"expected_revision", 1}});
  Json report_assets = Json::array({{{"record_id", ids.at(0)}, {"path", entry}}});
  if (html_video) { report_assets.push_back({{"record_id", ids.at(1)}, {"path", "clip.mp4"}}); }
  else if (!pdf && !video) { report_assets.push_back({{"record_id", ids.at(1)}, {"path", "marker.png"}}); }
  call("project.reports.create", {{"handle", handle}, {"report_id", kReport}, {"name", "Frozen native acceptance"},
      {"snapshot_id", snapshot.at("snapshot").at("id")}, {"entry_record_id", ids.at(0)}, {"expected_revision", 2},
      {"assets", report_assets},
      {"sources", Json::array()}});
  const auto report = call("project.reports.get", {{"handle", handle}, {"report_id", kReport}}).at("report");
  require(fs::remove(folder / entry) && (html_video ? fs::remove(folder / "clip.mp4") :
      (pdf || video || fs::remove(folder / "marker.png"))), "Delete all live sources after freezing");
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
  std::set<std::string> sessions;
  int prepares = 0, image_reads = 0;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  std::shared_ptr<document_preview::ResourceSession> final_media_resources;
  std::string final_media_url;
  ui::Rect final_media_rectangle;
  Media final_media_observed;
  if (video) {
    result["media_fixture"] = {{"size", media_bytes.size()}, {"sha256", kMediaSha256},
        {"container", "MP4"}, {"video_codec", "H264 Baseline"}, {"audio_codec", "AAC"},
        {"duration_seconds", 6}, {"live_source_deleted_before_prepare", true}};
    result["required_images"] = 161;
    result["body_text_pixel_criterion"] = "Pinned MP4 decoded red/blue picture region in independent OS client captures; HTML contains no poster/image/script";
    result["not_proven_here"] = "Physical hardware input, audio output, arbitrary codec support, IME, physical scanout and browser memory stability; final guarded memory remains the separate after-static spike gate";
    result["native_media_inputs"] = Json::array(); result["media_holds"] = Json::array();
    result["media_scope_revocations"] = Json::array(); result["media_transitions"] = Json::array();
    auto latest_session = [&] {
      std::ifstream input(trace); std::string text, session;
      while (std::getline(input, text)) {
        const auto item = Json::parse(text);
        if (item.at("action") == "preview_resources") { session = item.at("session_id").get<std::string>(); }
      }
      require(!session.empty(), "Actual bridge must return a prepared video session"); return session;
    };
    auto paused = [&](const std::string &session, const std::string &phase) {
      return ui.media_until(session, [](const Media &m) { return m.paused && !m.seeking && !m.ended; }, phase);
    };
    auto play = [&](int cycle, const std::string &phase, const std::string &session, ui::Rect bounds) {
      const auto before = ui.media(session);
      require(before.paused && !before.ended && before.current_time <= 1.25,
          "Explicit Play must start paused in the early part of the clip");
      // These are bounded local user events, never DOM media setters or injected play().
      ui.native_media_click(cycle, phase, bounds, before, 0.50, 0.50);
      auto after = ui.observe_input(session, [](const Media &m) { return !m.paused; });
      if (after.paused) {
        ui.native_media_key(cycle, phase + "-space", bounds, wm::Key::Space, "Space", after);
      }
      after = ui.media_until(session, [&](const Media &m) {
        return !m.paused && !m.ended && !m.seeking && m.ready_state >= 2 &&
            m.current_time >= before.current_time + 0.10;
      }, "Actual native Play advances the decoded clip", 8);
      require(after.navigation_generation == before.navigation_generation && after.duration_known &&
          std::abs(after.duration - 6.0) < 0.10 && after.current_time < 2.5,
          "Play must advance this navigation well before natural ending");
      result["media_transitions"].push_back({{"cycle", cycle}, {"phase", phase},
          {"before", media_json(before)}, {"after", media_json(after)}}); ui.save(); return after;
    };
    auto seek = [&](int cycle, bool late, const std::string &session, ui::Rect bounds) {
      const std::string phase = late ? "seek-blue" : "seek-early";
      const auto original = ui.media(session);
      require(original.paused && !original.ended, "Native seek starts explicitly paused");
      auto target = [&](const Media &m) {
        return m.paused && !m.ended && !m.seeking && m.ready_state >= 2 && m.duration_known &&
            (late ? m.current_time >= 3.5 && m.current_time <= 5.65 : m.current_time <= 0.90);
      };
#ifdef __APPLE__
      // Use the actual time slider's AX frame/value, not a fraction of the
      // video or an arrow sent to whichever document control happens to focus.
      ui.native_media_seek(cycle, phase, bounds, original, late ? 0.80 : 0.07);
      auto observed = ui.observe_input(session, target);
#else
      ui.native_media_key(cycle, phase, bounds, late ? wm::Key::RightArrow : wm::Key::LeftArrow,
          late ? "RightArrow" : "LeftArrow", original);
      auto observed = ui.observe_input(session, target);
      // Native controls differ by system. A fixed, bounded set of real timeline clicks
      // is allowed, and every attempt is recorded; only observed seek+OS color can pass.
      for (const double y : {0.94, 0.86, 0.98, 0.78}) {
        if (target(observed)) { break; }
        if (!observed.paused) { ui.click("reports_document_pause", *area); observed = paused(session, phase); }
        ui.native_media_click(cycle, phase + "-timeline", bounds, observed, late ? 0.78 : 0.14, y);
        observed = ui.observe_input(session, target);
      }
#endif
      if (!observed.paused) { ui.click("reports_document_pause", *area); }
      observed = ui.media_until(session, target, "Native seek reaches the requested clip segment", 5);
      require(observed.navigation_generation == original.navigation_generation &&
          std::abs(observed.current_time - original.current_time) > 2.0,
          "Seek must change actual media time without changing navigation");
      result["media_transitions"].push_back({{"cycle", cycle}, {"phase", phase},
          {"before", media_json(original)}, {"after", media_json(observed)}}); ui.save(); return observed;
    };
    for (int cycle = 1; cycle <= 20; ++cycle) {
      ui.wait(ready, "Video report visible");
      const auto session = latest_session();
      require(sessions.insert(session).second, "Each explicit video preparation must use a fresh session");
      ++prepares;
      auto resources = ui.media_session(session);
      require(resources->identity().project_id == project.project()->id &&
          resources->identity().resource_id == kReport && resources->identity().source_version ==
          report.at("source_sha256").get<std::string>(), "Observed native session must bind this frozen report");
      const auto old_url = resources->url("clip.mp4");
      const auto complete = resources->read(old_url);
      require(complete.status == 200 && complete.mime == "video/mp4" && complete.content_length == 41558 &&
          core::Sha256::hex(complete.bytes) == kMediaSha256 && !resources->allows_navigation(old_url),
          "Actual native session must contain the exact verified MP4 and deny its top-level navigation");
      const auto slice = resources->read(old_url, "GET", "bytes=0-31");
      require(slice.status == 206 && slice.content_length == 32 && slice.content_range == "bytes 0-31/41558" &&
          slice.bytes == std::vector<uint8_t>(complete.bytes.begin(), complete.bytes.begin() + 32),
          "Actual native session single Range must retain the verified full MP4 identity");
      auto initial = ui.media(session);
      require(initial.paused && !initial.ended && initial.current_time <= 0.10,
          "Initial or explicitly reprepared video must never autoplay");
      ui.held_media(cycle, "initial-no-autoplay", session, initial, 0.50);
      auto bounds = ui.widget("reports_document_viewport")->rect;
      play(cycle, "explicit-play", session, bounds);
      ui.click("reports_document_pause", *area);
      auto red = paused(session, "Explicit Pause button");
      require(red.current_time > 0.05 && red.current_time < 2.6 && !red.ended,
          "Explicit pause must stop actual playback before the blue/ended segment");
      ui.held_media(cycle, "explicit-pause", session, red, 0.25);
      red = ui.fit_decoded_media(*area, *viewer_area, session, red);
      bounds = ui.widget("reports_document_viewport")->rect;
      auto rectangle = ui.media_rectangle(bounds, red);
      ui.media_capture(cycle, "played-red-paused", 1, rectangle, red, session);
      // Observe a natural red-to-blue transition after explicit Play, before any seek.
      // Pausing only after >3.3s gives OS capture ample time without allowing ended
      // or capture latency to masquerade as a successful pause.
      play(cycle, "explicit-play-color-transition", session, bounds);
      const auto progressing = ui.media_until(session, [](const Media &m) {
        return !m.paused && !m.ended && !m.seeking && m.current_time >= 3.30;
      }, "Explicit native Play crosses the actual MP4 color boundary", 8);
      require(progressing.current_time < 4.50, "Natural frame transition must be observed well before ending");
      ui.click("reports_document_pause", *area);
      auto natural_blue = paused(session, "Explicit Pause after natural color transition");
      require(natural_blue.current_time >= 3.30 && natural_blue.current_time < 4.80 && !natural_blue.ended,
          "Pause after actual natural playback must not be a natural ended state");
      ui.media_capture(cycle, "natural-play-blue-paused", 2, ui.media_rectangle(bounds, natural_blue), natural_blue, session);
      const auto sought_red = seek(cycle, false, session, bounds);
      ui.media_capture(cycle, "seek-early-red-paused", 1, ui.media_rectangle(bounds, sought_red), sought_red, session);
      auto blue = seek(cycle, true, session, bounds);
      ui.media_capture(cycle, "seek-blue-paused", 2, ui.media_rectangle(bounds, blue), blue, session);
      auto early = seek(cycle, false, session, bounds);
      ui.held_media(cycle, "seek-early-paused", session, early, 0.25);
      const auto playing = play(cycle, "play-before-hide", session, bounds);
      require(!playing.paused && playing.current_time < 2.5, "Hide must interrupt a playing early clip");
      ui.tab(*area, 1);
      auto hidden = paused(session, "Hide must pause the actual native media");
      require(hidden.current_time < 2.9 && hidden.current_time >= playing.current_time - 0.05 && !hidden.ended,
          "Hidden pause must precede the color transition and natural ending");
      hidden = ui.held_media(cycle, "hidden-tab-pause", session, hidden, 0.75);
      ui.media_capture(cycle, "hidden-video-tab", 0, rectangle, hidden, session);
      require(area->tab(1).save_workspace_state() == draft_state, "Video hide preserves the Python draft");
      ui.tab(*area, 0); ui.wait(ready, "Paused video report shown again");
      auto reshown = ui.held_media(cycle, "reshown-no-autoresume", session, hidden, 0.50);
      ui.media_capture(cycle, "reshown-red-paused", 1, ui.media_rectangle(bounds, reshown), reshown, session);
      // Return to the earliest segment before a second explicit Play. Rewinding is
      // itself local input; showing the tab must never provide that playback action.
      if (reshown.current_time > 0.90) {
        ui.native_media_key(cycle, "rewind-after-show", bounds, wm::Key::LeftArrow, "LeftArrow", reshown);
        reshown = ui.media_until(session, [](const Media &m) {
          return m.paused && !m.ended && !m.seeking && m.current_time <= 0.90;
        }, "Native LeftArrow rewinds before explicit resume", 5);
      }
      play(cycle, "explicit-play-after-show", session, bounds);
      ui.click("reports_document_pause", *area);
      auto resumed = paused(session, "Pause after explicit Play on shown tab");
      require(resumed.current_time < 2.9 && !resumed.ended, "Explicit resume must still be observed before natural ending");
      ui.media_capture(cycle, "explicit-resume-red-paused", 1, ui.media_rectangle(bounds, resumed), resumed, session);
      ui.click("reports_document_close", *area);
      require(!resources->active() && resources->read(old_url, "GET", "bytes=0-1").status == 410 &&
          resources->read(old_url, "HEAD").status == 410,
          "Actual preview close must revoke the retained session and old media URL");
      result["media_scope_revocations"].push_back({{"cycle", cycle}, {"scope", "preview-close"},
          {"session_id", session}, {"old_url_get_range_status", 410}, {"old_url_head_status", 410}});
      ui.media_capture(cycle, "closed-video", 0, rectangle, resumed);
      ui.wait([&] { const auto *w = ui.widget("reports_preview"); return w && w->enabled; }, "Explicit video prepare action");
      ui.click("reports_preview", *area); ui.wait(ready, "Explicit video prepare creates the next view");
      const auto next = latest_session();
      require(next != session, "Video prepare must not reuse the closed session");
      initial = ui.media(next);
      require(initial.paused && !initial.ended && initial.current_time <= 0.10, "Newly prepared video must remain paused");
      ui.held_media(cycle, "reprepared-no-autoplay", next, initial, 0.25);
      final_media_resources = ui.media_session(next); final_media_url = final_media_resources->url("clip.mp4");
      final_media_rectangle = rectangle; final_media_observed = initial;
      result["completed_cycles"] = cycle; ui.save();
    }
    require(sessions.insert(latest_session()).second, "The final explicit video preparation is also unique"); ++prepares;
  }
  else
#endif
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
  const auto &assets = report.at("manifest").at("assets");
  const auto image_asset = std::find_if(assets.begin(), assets.end(), [](const Json &asset) {
    return asset.at("path") == "marker.png";
  });
  const auto entry_asset = std::find_if(assets.begin(), assets.end(), [&](const Json &asset) { return asset.at("path") == entry; });
  require(entry_asset != assets.end() && entry_asset->at("sha256") == core::Sha256::hex(source_bytes) &&
      entry_asset->at("size") == source_bytes.size(), "Frozen entry must match the complete fixture bytes");
  require(video ? assets.size() == (html_video ? 2 : 1) : pdf ? assets.size() == 1 : image_asset != assets.end(),
      "Exact frozen report asset set");
  std::ifstream calls(trace); std::string line;
  int trace_prepares = 0;
  bool awaiting_image = false;
  while (std::getline(calls, line)) {
    const auto item = Json::parse(line);
    require(item.at("project_id") == project.project()->id && item.at("report_id") == kReport &&
        item.at("source_sha256") == report.at("source_sha256"), "Every preparation must bind the frozen report");
    if (video) {
      if (item.at("action") == "preview_resources") {
        require(!awaiting_image && item.at("revision") == 3 && item.at("source_path") == entry &&
            item.at("renderer") == "stk.report-renderer/2" && item.at("mime") == "text/html; charset=utf-8" &&
            item.at("source_mime") == (html_video ? "text/html; charset=utf-8" : "video/mp4") &&
            item.at("source_content_sha256") == entry_asset->at("sha256") &&
            item.at("source_size") == entry_asset->at("size") && item.at("data_size") == item.at("size") &&
            item.at("data_sha256") == item.at("content_sha256") && item.at("resources").size() == 1 &&
            item.at("resources").at(0).at("path") == "clip.mp4" &&
            item.at("resources").at(0).at("mime") == "video/mp4" &&
            item.at("resources").at(0).at("sha256") == kMediaSha256 &&
            item.at("resources").at(0).at("size") == 41558 &&
            item.at("total_size").get<uint64_t>() == item.at("size").get<uint64_t>() + 41558,
            "Every video preparation must bind complete frozen source/wrapper and exactly one listed MP4");
        const auto session = item.at("session_id").get<std::string>();
        require(sessions.contains(session), "Every bridge preparation must correspond to an observed real native session");
        require(html_video ? item.at("path") == entry :
            item.at("path") == "_stk-preview/" + session + "/player.html",
            "Standalone MP4 uses a separate virtual HTML wrapper and retains the exact source_path");
        ++trace_prepares; awaiting_image = true;
      }
      else {
        require(item.at("action") == "asset" && awaiting_image && item.at("path") == "clip.mp4" &&
            item.at("content_sha256") == kMediaSha256 && item.at("size") == 41558,
            "Video preparation may read only the exact frozen MP4 after its descriptor");
        ++image_reads; awaiting_image = false;
      }
    }
    else if (pdf) {
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
  require(prepares == 21 && (video ? trace_prepares == 21 : true) &&
      image_reads == (pdf ? 0 : 21) && !awaiting_image,
      "Exactly 21 explicit preparations; PDF has no extra assets and text/video has one frozen resource read each");
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
  require(result.at("images").size() == (video ? 160 : pdf ? 160 : 140) && result.at("completed_cycles") == 20,
      "All 20 production reading cycles and the source-specific OS observation count must complete");
  require(pdf ? result.at("native_scroll_requests").size() >= 20 : result.at("native_scroll_requests").empty(),
      "Each PDF cycle requires native wheel input; text acceptance must not claim native scrolling");
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  if (video) {
    require(final_media_resources && final_media_resources->active(), "Final native session must still be live before closing the project scope");
    auto completion = std::make_shared<std::optional<bridge::Result<bool>>>();
    require(project.close([completion](auto reply) { *completion = std::move(reply); }),
        "Actual ProjectState close must accept the final scope action");
    // Production invalidation must happen synchronously, before the close ACK.
    require(!final_media_resources->active() &&
        final_media_resources->read(final_media_url, "GET", "bytes=0-1").status == 410 &&
        final_media_resources->read(final_media_url, "HEAD").status == 410,
        "Actual project close intent must revoke old media URLs before its bridge ACK");
    result["media_scope_revocations"].push_back({{"cycle", 21}, {"scope", "project-close-before-ACK"},
        {"session_id", final_media_resources->identity().session_id},
        {"old_url_get_range_status", 410}, {"old_url_head_status", 410}});
    ui.wait([&] { return completion->has_value(); }, "Project close ACK");
    require(completion->value().ok() && completion->value().value(), "Actual project close must complete successfully");
    ui.media_capture(21, "project-scope-closed", 0, final_media_rectangle, final_media_observed);
    require(result.at("images").size() == 161 && result.at("media_scope_revocations").size() == 21,
        "All twenty playback cycles and the final actual project-scope revocation must complete");
    // This trace observes explicit bridge asset RPCs. prepare also reads and
    // validates the frozen MP4 internally before returning its descriptors.
    result["explicit_frozen_media_asset_rpc_reads"] = image_reads;
  }
#endif
  result["explicit_preparations"] = prepares; result["frozen_image_reads"] = video ? 0 : image_reads;
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
    else if (arg == "--media-fixture") { options.media_fixture = core::path_from_utf8(argv[++i]); }
    else { return 2; }
  }
  if (options.python.empty() || options.output.empty() ||
      (options.source != "markdown" && options.source != "html" && options.source != "pdf"
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
       && options.source != "video" && options.source != "html-video"
#endif
      )) {
    std::fprintf(stderr, "usage: stk-reports-native-window --python PATH --gpu-backend BACKEND --evidence-dir DIR --source markdown|html|pdf|video|html-video [--media-fixture MP4]\n"); return 2;
  }
  Json result = {{"format", "stk.reports-native-evidence/1"}, {"status", "running"}, {"required_cycles", 20},
      {"completed_cycles", 0}, {"images", Json::array()}, {"native_scroll_requests", Json::array()},
      {"claim", "Production ReportsEditor app actions, frozen bridge resources and OS-composited STK client pixels; opt-in media also records bounded local native child input and fixed read-only media observations"},
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
