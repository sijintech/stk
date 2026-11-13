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
#include "reports_native_wait.hh"
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
#  include "stk/document/media_pause_verification.hh"
#  include "stk/document/test_media_probe.hh"
#  include "reports_native_input.hh"
#endif

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iterator>
#include <optional>
#include <set>
#include <stdexcept>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

using namespace stk;
using io::Json;
namespace fs = std::filesystem;
namespace {
constexpr const char *kReport = "a1111111-1111-4111-8111-111111111111";
constexpr const char *kMediaSha256 = "a54fb5baf8ca34545a8e31ea46c8801347db722cc9c876279186ab8c94f860d1";
constexpr size_t kMediaSize = 41558;
// Frame-clock controls read this separate public synthetic clip, generated and
// verified by spike/document_preview/fixtures/make_frame_clock_fixture.py. Same geometry, rate,
// codecs and red/blue halves as frozen-preview.mp4, plus a per-frame ID marker.
constexpr const char *kFrameClockMediaSha256 = "c2bbcb873b7628c22b512051443adde6ff2e6c8688c6d84f0307d6bab2a34eef";
constexpr size_t kFrameClockMediaSize = 44339;
using Clock = std::chrono::steady_clock;
// The optional first-pause pair uses the same real toolbar click with or without a passive wait.
[[maybe_unused]] constexpr auto kPassiveDelay = std::chrono::milliseconds(270);
// Allow bounded setup or event-pump overhead before requesting the toolbar click.
[[maybe_unused]] constexpr auto kPassiveDelayTolerance = std::chrono::milliseconds(20);
void require(bool ok, const std::string &message) { if (!ok) { throw std::runtime_error(message); } }
void write(const fs::path &path, const std::string &text)
{
  std::ofstream out(path, std::ios::binary);
  out.write(text.data(), std::streamsize(text.size()));
  require(out.good(), "Cannot write public fixture/evidence: " + core::path_to_utf8(path));
}
struct Options {
  enum class FreshPause { None, Hidden, Visible };
  enum class FirstToolbarFrames { None, Playing, Paused };
  std::string python, backend, source = "markdown";
  fs::path output, media_fixture;
  bool pre_seek_hide_control = false;
  bool quiet_hidden_hold = false;
  bool isolated_pause_control = false;
  bool pause_during_hidden_suspension = false;
  bool visible_pause_control = false;
  bool second_visible_pause_control = false;
  bool visible_pause_diagnostic() const { return visible_pause_control || second_visible_pause_control; }
  bool hide_after_verified_pause_control = false;
  bool repeat_verified_visible_pause_control = false;
  bool retain_visible_pause_control = false;
  bool hidden_dom_tail_control = false;
  FreshPause fresh_pause = FreshPause::None;
  // Runs the fresh-visible sequence with the frame-clock clip; adds OS frame-ID captures only.
  bool frame_clock_control = false;
  bool first_toolbar_pause_control = false;
  bool first_toolbar_immediate = false;
  FirstToolbarFrames first_toolbar_frames = FirstToolbarFrames::None;
  bool suspend_reveal_control = false;
  bool fresh_pause_diagnostic() const { return fresh_pause != FreshPause::None; }
  bool pause_order_diagnostic() const
  {
    return visible_pause_diagnostic() || hide_after_verified_pause_control || repeat_verified_visible_pause_control;
  }
  int reading_cycles() const
  {
    return (pre_seek_hide_control || pause_order_diagnostic() || fresh_pause_diagnostic() ||
            first_toolbar_pause_control || suspend_reveal_control) ? 1 : 20;
  }
};
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
using Media = document_preview::test::MediaSnapshot;
using NativePause = document_preview::test::NativePauseSnapshot;
using NativePausePair = std::array<NativePause, 2>;
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
Json native_pause_json(const NativePause &pause)
{
  if (!pause.available) return nullptr;
  return {{"media_generation", pause.media_generation},
      {"navigation_generation", pause.navigation_generation},
      {"acknowledged", pause.acknowledged}, {"verified", pause.verified},
      {"visible_at_dispatch", pause.visible_at_dispatch},
      {"pause_actuator", pause.isolated_actuator ? "isolated_world" : "native"},
      {"isolated_reply", pause.isolated_reply.empty() ? Json(nullptr) : Json(std::string(pause.isolated_reply))},
      {"query_count", pause.query_count}, {"reply_count", pause.reply_count},
      {"playing_reply_count", pause.playing_reply_count},
      {"first_query_seconds", pause.query_count ? Json(pause.first_query_seconds) : Json(nullptr)},
      {"last_reply_seconds", pause.reply_count ? Json(pause.last_reply_seconds) : Json(nullptr)}};
}
Json native_pause_pair_json(const std::optional<NativePausePair> &pause)
{
  if (!pause) return nullptr;
  return {{"dispatch", native_pause_json((*pause)[0])},
      {"callback", native_pause_json((*pause)[1])}};
}
struct MediaProbeObservation {
  Clock::time_point started = Clock::now();
  std::optional<Clock::time_point> dispatched, callback, finished;
  std::optional<bool> accepted;
  std::optional<document_preview::test::MediaProbeResult> reply;
};
using MediaHoldExit = std::function<void(Clock::time_point, Clock::time_point,
    std::optional<Clock::time_point>, size_t, bool)>;
struct HiddenMediaObservation {
  int cycle = 0;
  Clock::time_point started = Clock::now();
  const char *stage = "play-return";
  std::string session, session_sha256;
  Media playing, before;
  std::optional<Media> current, failed, last_valid;
  bool current_valid = false;
  std::optional<bool> requested_session_matches;
  size_t samples = 0;
  std::optional<Clock::time_point> tab_begin, tab_returned, paused_begin, paused_returned, hold_begin;
  std::optional<Clock::time_point> failure_detected;
  const char *failure_kind = nullptr;
  std::optional<std::array<bool, 3>> hidden_checks;
  std::optional<std::array<bool, 5>> hold_checks;
  std::optional<NativePausePair> playing_native_pause, first_paused_native_pause;
};
double media_seconds(Clock::time_point start, Clock::time_point end)
{
  return std::chrono::duration<double>(end - start).count();
}
Json media_time(Clock::time_point start, const std::optional<Clock::time_point> &end)
{
  return end ? Json(media_seconds(start, *end)) : Json(nullptr);
}
void log_last_media_observation(const Json &result) noexcept
{
  try {
    for (const auto *key : {"last_hidden_media_observation", "last_explicit_pause_observation",
                            "hidden_media_native_close", "frame_clock_verdict",
                            "first_toolbar_pause_delay", "first_toolbar_pause_trace",
                            "first_toolbar_pause_immediate", "first_toolbar_pause_immediate_trace",
                            "first_toolbar_frame_clock",
                            "repeat_verified_visible_pause", "suspend_reveal",
                            "last_failed_timeline_seek",
                            "failed_reveal_observation", "failed_reveal_native_pause_trace",
                            "failed_reshown_hold", "reshown_hold_native_observation"}) {
      const auto item = result.find(key);
      if (item == result.end() || !item->is_object()) continue;
      // These objects contain only fixed phase names, hashes and numerical probe facts.
      const auto text = item->dump();
      if (text.size() <= 8192) std::fprintf(stderr, "STK_NATIVE_LAST_MEDIA_OBSERVATION %s\n", text.c_str());
      else std::fputs("STK_NATIVE_LAST_MEDIA_OBSERVATION unavailable\n", stderr);
    }
  }
  catch (...) { std::fputs("STK_NATIVE_LAST_MEDIA_OBSERVATION unavailable\n", stderr); }
}
// Marker of frame-clock-preview.mp4; the generator documents the same layout. Two rows of eight
// 25x16 source-pixel cells in the top-left band (x 0-200, y 0-32 of 320x180), above the central
// red/blue sample and clear of the WebKit inline controls. Row 0: guard white, ID bits b5..b0,
// even parity; row 1 complements every column. Any inconsistency is ambiguous, never another ID.
namespace frame_clock {
constexpr int kSourceWidth = 320, kSourceHeight = 180, kCellWidth = 25, kCellHeight = 16;
constexpr int kColumns = 8, kIdBits = 6, kFrames = 60, kFps = 10;
struct Reading {
  std::optional<int> id;     // Unambiguous marker whose ordinal also matches the central half.
  std::optional<int> marker; // Self-consistent marker value before the red/blue cross-check.
  const char *reason = "ok";
  double red_fraction = 0, blue_fraction = 0;
  const char *half = "neither";
  size_t min_cell_samples = 0;
};
// picture: decoded 320x180 video picture in client pixels, top-left origin (media_rectangle).
[[maybe_unused]] Reading read(const io::Image &pixels, ui::Rect picture)
{
  Reading out;
  if (pixels.channels != 4 || !(picture.w >= 32 && picture.h >= 18) || picture.x < 0 || picture.y < 0 ||
      picture.x + picture.w > float(pixels.width) || picture.y + picture.h > float(pixels.height)) {
    out.reason = "picture_outside_client";
    return out;
  }
  // Same region, stride and thresholds as Exercise::media_capture.
  const int cx = int(std::ceil(picture.x + picture.w * 0.15f)), cy = int(std::ceil(picture.y + picture.h * 0.20f));
  const int cr = int(std::floor(picture.x + picture.w * 0.85f)), cb = int(std::floor(picture.y + picture.h * 0.65f));
  size_t red = 0, blue = 0, total = 0;
  for (int row = cy; row < cb; row += 2) for (int column = cx; column < cr; column += 2) {
    const auto *p = pixels.pixel(uint32_t(column), uint32_t(row)); ++total;
    if (p[0] >= 120 && p[0] >= int(p[1]) * 2 + 30 && p[0] >= int(p[2]) * 2 + 30) { ++red; }
    if (p[2] >= 120 && p[2] >= int(p[0]) * 2 + 30 && p[2] >= int(p[1]) * 2 + 30) { ++blue; }
  }
  out.red_fraction = total ? double(red) / double(total) : 0;
  out.blue_fraction = total ? double(blue) / double(total) : 0;
  out.half = out.red_fraction >= 0.80 && out.blue_fraction <= 0.05 ? "red" :
             out.blue_fraction >= 0.80 && out.red_fraction <= 0.05 ? "blue" : "neither";
  std::array<int, 2 * kColumns> cells{};
  out.min_cell_samples = SIZE_MAX;
  for (int row = 0; row < 2; ++row) for (int column = 0; column < kColumns; ++column) {
    // Central half of each cell only; edges may blend under scaling and 4:2:0 chroma.
    const double left = picture.x + (column * kCellWidth + kCellWidth * 0.25) / kSourceWidth * picture.w;
    const double right = picture.x + (column * kCellWidth + kCellWidth * 0.75) / kSourceWidth * picture.w;
    const double top = picture.y + (row * kCellHeight + kCellHeight * 0.25) / kSourceHeight * picture.h;
    const double bottom = picture.y + (row * kCellHeight + kCellHeight * 0.75) / kSourceHeight * picture.h;
    size_t white = 0, black = 0, samples = 0;
    for (int y = int(std::ceil(top - 0.5)); y + 0.5 < bottom; ++y) {
      for (int x = int(std::ceil(left - 0.5)); x + 0.5 < right; ++x) {
        const auto *p = pixels.pixel(uint32_t(x), uint32_t(y));
        const int low = std::min({int(p[0]), int(p[1]), int(p[2])});
        const int high = std::max({int(p[0]), int(p[1]), int(p[2])});
        ++samples;
        if (low >= 170 && high - low <= 60) { ++white; }
        else if (high <= 80 && high - low <= 50) { ++black; }
      }
    }
    out.min_cell_samples = std::min(out.min_cell_samples, samples);
    if (samples < 4) { out.reason = "cell_too_small"; return out; }
    if (double(white) >= 0.85 * double(samples)) { cells[size_t(row * kColumns + column)] = 1; }
    else if (double(black) >= 0.85 * double(samples)) { cells[size_t(row * kColumns + column)] = 0; }
    else { out.reason = "ambiguous_cell"; return out; }
  }
  for (int column = 0; column < kColumns; ++column) {
    if (cells[size_t(column)] == cells[size_t(kColumns + column)]) { out.reason = "complement_mismatch"; return out; }
  }
  if (cells[0] != 1) { out.reason = "guard_mismatch"; return out; }
  int ordinal = 0, parity = 0;
  for (int bit = 1; bit <= kIdBits; ++bit) { ordinal = ordinal * 2 + cells[size_t(bit)]; parity ^= cells[size_t(bit)]; }
  if (parity != cells[size_t(kColumns - 1)]) { out.reason = "parity_mismatch"; return out; }
  if (ordinal >= kFrames) { out.reason = "out_of_range"; return out; }
  out.marker = ordinal;
  if (std::string_view(out.half) != (ordinal < kFrames / 2 ? "red" : "blue")) { out.reason = "half_mismatch"; return out; }
  out.id = ordinal;
  return out;
}
// DOM currentTime expressed as the 10 fps frame it falls in, for comparison with picture IDs.
[[maybe_unused]] int dom_frame(double seconds) { return int(std::floor(seconds * kFps + 1e-6)); }
struct Verdict { const char *outcome, *reason; };
// last_playing: ID of the last completed baseline capture during playback. stable_paused: ID of
// two consecutive completed post-pause captures. dom_paused_times: the bounded DOM samples.
[[maybe_unused]] Verdict classify(int last_playing, int stable_paused, double playing_time,
                                  const std::vector<std::pair<bool, double>> &dom)
{
  if (stable_paused < last_playing) {
    return {"picture_backward", "stable paused picture ID is below the last completed playing picture ID"};
  }
  if (dom.size() != 2 || !std::isfinite(playing_time) ||
      std::any_of(dom.begin(), dom.end(), [](const auto &s) { return !s.first || !std::isfinite(s.second); })) {
    return {"inconclusive", "DOM did not report paused in every bounded sample"};
  }
  const auto below = std::count_if(dom.begin(), dom.end(), [&](const auto &s) { return dom_frame(s.second) < last_playing; });
  const auto temporal_below = std::count_if(dom.begin(), dom.end(), [&](const auto &s) {
    return s.second < playing_time - 0.05; // Same temporal floor recorded by the bounded DOM observations.
  });
  if (temporal_below == std::ptrdiff_t(dom.size())) {
    return {"clock_reset_within_observation",
        "both paused DOM times fell below the earlier playing DOM time while the observed picture did not move backward; uncaptured transients are not excluded"};
  }
  if (temporal_below == 0 && below == 0) {
    return {"no_clock_reset_observed", "neither bounded DOM sample nor the stable visible picture shows a rollback"};
  }
  return {"inconclusive", "the bounded observations do not establish a temporal clock rollback or a consistent forward position"};
}
// Bounds of the two OS-capture arms. A capture completing after its arm deadline is late.
constexpr auto kPlayingBudget = std::chrono::milliseconds(2000); // From the play() return.
constexpr auto kPausedBudget = std::chrono::milliseconds(3000);  // From the end of native settle.
constexpr int kMaxCapturesPerArm = 8;
constexpr int kPlayingMaxId = 24; // Playing baseline must stay well before the 3 s colour boundary.
struct Plan {
  ui::Rect picture;               // media_rectangle of the play() snapshot; no new DOM read.
  ui::Rect viewport;              // Native viewport layout that picture was mapped through.
  Clock::time_point play_returned;
  std::string source_sha256;
};
struct Capture {
  std::string arm;
  int index = 0;
  Clock::time_point requested, completed;
  // completed: delivered before the arm deadline and bound at request and completion.
  const char *status = "pending"; // completed | unbound | late | capture_error
  std::string backend, error;
  Reading reading;
  io::Image crop; // Picture region only; written after all timed observations.
  std::array<int, 4> crop_top_left{};
  std::string file, sha256;
};
[[maybe_unused]] bool audit_complete(const std::vector<Capture> &captures)
{
  for (const auto arm : {"playing", "paused"}) {
    int checked = 0;
    for (auto it = captures.rbegin(); it != captures.rend() && checked < 2; ++it) {
      if (it->arm != arm) { continue; }
      if (std::string_view(it->status) != "completed" || !it->reading.id || it->file.empty() ||
          !core::is_sha256_hex(it->sha256)) { return false; }
      ++checked;
    }
    if (checked != 2) { return false; }
  }
  return true;
}
[[maybe_unused]] Json capture_json(const Capture &c, Clock::time_point origin,
                                   const std::optional<Clock::time_point> &pause_dispatched)
{
  const auto seconds = [](Clock::time_point a, Clock::time_point b) { return std::chrono::duration<double>(b - a).count(); };
  return {{"arm", c.arm}, {"index", c.index}, {"status", c.status},
      {"requested_seconds_from_play_return", seconds(origin, c.requested)},
      {"completed_seconds_from_play_return", seconds(origin, c.completed)},
      {"requested_seconds_from_pause_dispatch", pause_dispatched ? Json(seconds(*pause_dispatched, c.requested)) : Json(nullptr)},
      {"completed_seconds_from_pause_dispatch", pause_dispatched ? Json(seconds(*pause_dispatched, c.completed)) : Json(nullptr)},
      {"latency_seconds", seconds(c.requested, c.completed)},
      {"backend", c.backend.empty() ? Json(nullptr) : Json(c.backend)},
      {"error", c.error.empty() ? Json(nullptr) : Json(c.error)},
      {"frame_id", c.reading.id ? Json(*c.reading.id) : Json(nullptr)},
      {"marker_value", c.reading.marker ? Json(*c.reading.marker) : Json(nullptr)},
      {"reason", std::string(std::string_view(c.status) == "completed" ? c.reading.reason : c.status)},
      {"central_half", c.reading.half}, {"red_fraction", c.reading.red_fraction},
      {"blue_fraction", c.reading.blue_fraction},
      {"min_cell_samples", c.reading.min_cell_samples == SIZE_MAX ? Json(nullptr) : Json(c.reading.min_cell_samples)},
      {"picture_crop_top_left", c.crop.width ? Json(c.crop_top_left) : Json(nullptr)},
      {"file", c.file.empty() ? Json(nullptr) : Json(c.file)},
      {"sha256", c.sha256.empty() ? Json(nullptr) : Json(c.sha256)}};
}
}  // namespace frame_clock
#  ifdef __APPLE__
Json ax_progress_json(const std::optional<reports_native_test::ax::Progress> &value)
{
  if (!value) return nullptr;
  namespace ax = reports_native_test::ax;
  const auto &p = *value;
  const bool node_known = p.node_index != ax::kNodeLimit;
  const bool role_known = node_known && !(p.stage == ax::ProgressStage::Api && p.attribute == ax::Attribute::Role);
  return {{"sequence", p.sequence}, {"stage", ax::name(p.stage)}, {"edge", ax::name(p.edge)},
      {"call_sequence", p.call_sequence}, {"api_phase", ax::name(p.phase)},
      {"api_operation", ax::name(p.operation)}, {"api_attribute", ax::name(p.attribute)},
      {"node_index", node_known ? Json(p.node_index) : Json(nullptr)},
      {"node_depth", node_known ? Json(p.node_depth) : Json(nullptr)},
      {"node_role", role_known ? Json(ax::name(p.role)) : Json(nullptr)},
      {"elapsed_ms", p.elapsed_ms}, {"dropped", p.dropped},
      {"api_error", p.stage == ax::ProgressStage::Api && p.edge == ax::ProgressEdge::Returned ?
          Json(p.api_error) : Json(nullptr)}};
}
Json ax_witness_json(const reports_native_test::ax::Response &response)
{
  namespace ax = reports_native_test::ax;
  const auto &w = response.witness;
  if (!w.available) return nullptr;
  Json rows = Json::array();
  for (size_t i = 0; i < w.count; ++i) {
    const auto &row = w.rows[i];
    rows.push_back({{"index", row.index}, {"parent", row.parent == ax::kNodeLimit ? Json(nullptr) : Json(row.parent)},
        {"role", ax::name(row.role)}, {"depth", row.depth}, {"viewport_match", row.viewport_match}});
  }
  return {{"outer_group_index", w.outer}, {"inner_group_index", w.inner}, {"webarea_index", w.webarea},
      {"relation", ax::name(w.relation)}, {"rows", std::move(rows)}};
}
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
      : manager_(manager), window_(window), screen_(window.screen()), result_(result), directory_(std::move(directory))
  {
#if defined(__APPLE__) && defined(STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES)
    layout_observer_ = screen_.observe_layout([this](const wm::DrawContext &) { layout_epoch_.ready(); }, [this] {
      layout_epoch_.invalidated();
      native_input_.cancel_seek(); // Invalidate before the layout changes, even if it later returns to the same geometry.
    });
#endif
  }
#ifdef _WIN32
  void lease_capture_item()
  {
    capture_source_ = document_preview::window_evidence_capture_source(window_.native_window_handle());
  }
#endif
  void release_capture_source() { capture_source_.reset(); }
  bool drain_native_seek() noexcept
  {
#if defined(__APPLE__) && defined(STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES)
    native_input_.cancel_seek();
    const auto deadline = Clock::now() + std::chrono::seconds(3);
    while (native_input_.seek_pending()) {
      const auto result = native_input_.poll_cancelled_seek();
      if (result) return (result->child_pid == 0 || result->reaped) && native_input_.child_cleanup_confirmed();
      if (Clock::now() >= deadline) return false;
      try { manager_.process(false); } catch (...) {} // Preserve cancellation/reaping even when the run is already failing.
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
#endif
#if defined(__APPLE__) && defined(STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES)
    return native_input_.child_cleanup_confirmed();
#else
    return true;
#endif
  }
  void process(bool wait_for_event = false)
  {
    const bool alive = manager_.process(wait_for_event);
    check_native_scroll();
    require(alive && manager_.main_window() == &window_, "STK window closed unexpectedly");
    // WGC/AX completion may arrive without an OS event. Also yield for the standalone AX loop.
    if (!wait_for_event) { std::this_thread::sleep_for(std::chrono::milliseconds(1)); }
  }
  void wait(const std::function<bool()> &predicate, const std::string &reason, double seconds = 45)
  {
    const auto deadline = Clock::now() + std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double>(seconds));
    const bool completed = reports_native_test::poll_before<Clock>(deadline, predicate,
        [this](bool wait_for_event) { process(wait_for_event); }, [] {});
    require(completed, reason + " timed out");
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
  std::string_view tab(app::EditorArea &area, int index)
  {
    const int count = area.tab_count();
    require(index >= 0 && index < count, "Tab selection must name an existing tab");
    const int before_clicks = clicks;
    int key_presses = 0;
    const char *route = nullptr;
    const auto selector_key = area.id() + "/header/tabs";
    if (const auto *w = widget(selector_key)) {
      require(w->enabled && visible(w), "Tab selector must be fully visible");
      if (w->type == ui::WidgetType::Tabs) {
        route = "tabs";
        click_point({w->rect.x + w->rect.w * (float(index) + 0.5f) / float(w->items.size()), w->rect.cy()});
        ++clicks;
      }
      else {
        require(w->type == ui::WidgetType::Dropdown, "Expected tab selector");
        route = "tabs_dropdown";
        click(selector_key, area); keypress_tab_choice(index); key_presses = index + 2;
      }
    }
    else {
      // Production headers below 300 UI pixels expose their tabs at the end of
      // the area menu. Use that existing visible control through normal events.
      const auto menu_key = area.id() + "/header/area_menu";
      const auto *menu = widget(menu_key);
      require(menu && menu->enabled && visible(menu) && menu->type == ui::WidgetType::MenuButton &&
          count > 1 && menu->menu.size() >= size_t(count), "Narrow-area tab menu must be fully visible");
      for (int i = 0; i < count; ++i) {
        const auto &entry = menu->menu[menu->menu.size() - size_t(count) + size_t(i)];
        require(entry.enabled && bool(entry.action), "Every existing tab must have an enabled menu entry");
      }
      route = "area_menu";
      click(menu_key, area);
      key(wm::Key::End); ++key_presses;
      for (int i = count - 1; i > index; --i) { key(wm::Key::UpArrow); ++key_presses; }
      key(wm::Key::Enter); ++key_presses;
    }
    wait([&] { return area.active_tab() == index; }, "Tab selection"); frame();
    result_["tab_navigation"].push_back({{"target_index", index}, {"route", route},
        {"area_width", area.rect().width()}, {"mouse_clicks", clicks - before_clicks}, {"key_presses", key_presses}});
    save();
    return route;
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
    const bool windows = window_.native_window_handle().kind == wm::NativeWindowKind::Win32;
    const auto started = Clock::now();
    const auto starting_frames = window_.frames_drawn();
    auto last_activity = started;
    int64_t longest_start_ms = 0, longest_poll_ms = 0;
    uint64_t capture_requests = 0, polls = 0, empty_polls = 0, samples = 0, restarts = 0;
    reports_native_test::StalledCaptureRestart restart;
    const auto elapsed_ms = [](Clock::time_point from, Clock::time_point to) -> int64_t {
      return std::chrono::duration_cast<std::chrono::milliseconds>(to - from).count();
    };
    const auto capture_progress = [&] {
      const auto now = Clock::now();
      const auto *viewport = widget("reports_document_viewport");
      const auto *focus = widget("reports_document_focus");
      return Json{{"cycle", cycle}, {"phase", phase}, {"requests", capture_requests}, {"polls", polls},
          {"empty_polls", empty_polls}, {"samples", samples}, {"abandoned_empty_sessions", restarts},
          {"host_frames", window_.frames_drawn() - starting_frames}, {"elapsed_ms", elapsed_ms(started, now)},
          {"longest_start_ms", longest_start_ms}, {"longest_poll_ms", longest_poll_ms},
          {"since_capture_activity_ms", elapsed_ms(last_activity, now)},
          {"viewport_layout_visible", viewport && visible(viewport)}, {"focus_enabled", focus && focus->enabled}};
    };
    auto next = [&] {
      const auto began = Clock::now();
      if (!pending) {
        ++capture_requests; ++os_capture_requests_;
        const auto parent = window_.native_window_handle();
        pending = capture_source_ ? capture_source_->capture(parent) : document_preview::capture_window_evidence(parent);
        last_activity = Clock::now();
        longest_start_ms = std::max(longest_start_ms, elapsed_ms(began, last_activity));
        restart.started(last_activity);
        return false;
      }
      ++polls;
      auto image = pending->poll();
      last_activity = Clock::now();
      longest_poll_ms = std::max(longest_poll_ms, elapsed_ms(began, last_activity));
      check_native_scroll();
      if (!image) {
        ++empty_polls;
        if (windows && restart.due(last_activity)) {
          pending.reset();
          ++restarts;
        }
        return false;
      }
      pending.reset();
      require(image->error.empty(), "OS client capture: " + image->error);
      ++samples;
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
      if (windows) { result_["last_observation"]["capture_progress"] = capture_progress(); }
      if (consecutive >= 2) { result_["images"].push_back(result_["last_observation"]); }
      save();
      // Deliver at most one local wheel event after an actual nonmatching OS frame. Never
      // advance after the first matching frame; the second must confirm stable page pixels.
      if (scroll_to_second_page && !matched) {
        require(scrolls < 80, "PDF second page not reached within 80 native wheel requests");
        native_scroll(cycle, bounds); ++scrolls;
      }
      return consecutive >= 2;
    };
    try { wait(next, "OS pixels " + phase, 45); }
    catch (...) {
      if (windows) {
        try {
          result_["last_capture_failure"] = capture_progress();
          std::fprintf(stderr, "STK_NATIVE_CAPTURE_FAILURE %s\n", result_["last_capture_failure"].dump().c_str());
        }
        catch (...) {} // Keep the original timeout or capture error.
      }
      throw;
    }
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
  Media media(const std::string &session, double timeout_seconds = 10)
  {
    auto reply = std::make_shared<MediaProbeObservation>();
    last_media_probe_ = reply;
    ++dom_probe_requests_;
    if (hidden_media_) {
      auto &phase = *hidden_media_;
      if (phase.current_valid) phase.last_valid = phase.current;
      phase.current.reset(); phase.failed.reset(); phase.current_valid = false;
      phase.hold_checks.reset();
      phase.requested_session_matches = session == phase.session;
      ++phase.samples;
    }
    try {
      std::string error;
      const bool accepted = document_preview::test::probe_media(window_.native_window_handle(), session,
          [reply](auto result) {
            reply->callback = Clock::now(); reply->reply = std::move(result);
          }, error);
      reply->accepted = accepted; reply->dispatched = Clock::now();
      require(accepted, error);
      wait([&] { return reply->reply.has_value(); }, "Fixed native media observation", timeout_seconds);
      require(reply->reply->ok, reply->reply->error);
      const auto observed = reply->reply->media;
      if (hidden_media_) hidden_media_->current = observed;
      require(observed.error_code == 0, "System media decoder reported an error");
      if (hidden_media_) hidden_media_->current_valid = true;
      reply->finished = Clock::now(); return observed;
    }
    catch (...) {
      reply->finished = Clock::now();
      // A valid callback can arrive during a pump that crosses the unchanged deadline.
      // Retain that observation without accepting its late result or inventing a snapshot.
      if (hidden_media_) {
        auto &phase = *hidden_media_;
        phase.failure_kind = "probe-or-wait"; phase.failure_detected = reply->finished;
        if (reply->reply && reply->reply->ok) {
          phase.current = reply->reply->media;
          if (phase.current->error_code != 0) phase.failed = phase.current;
        }
      }
      throw;
    }
  }
  std::optional<NativePausePair> last_native_pause() const noexcept
  {
    if (!last_media_probe_ || !last_media_probe_->reply) return std::nullopt;
    const auto &reply = *last_media_probe_->reply;
    return NativePausePair{reply.native_pause_before, reply.native_pause_after};
  }
  Json last_media_probe_evidence(Clock::time_point origin) const
  {
    if (!last_media_probe_) { return nullptr; }
    const auto &probe = *last_media_probe_;
    return {{"started_seconds", media_seconds(origin, probe.started)},
        {"dispatched_seconds", media_time(origin, probe.dispatched)},
        {"callback_seconds", media_time(origin, probe.callback)},
        {"finished_seconds", media_time(origin, probe.finished)},
        {"media", probe.reply && probe.reply->ok ? media_json(probe.reply->media) : Json(nullptr)}};
  }
  void begin_hidden_media(int cycle, const std::string &session, const Media &playing,
                          Clock::time_point playing_returned) noexcept
  {
    try {
      hidden_media_.emplace();
      auto &phase = *hidden_media_;
      phase.started = playing_returned;
      phase.cycle = cycle; phase.session = session; phase.session_sha256 = core::Sha256::hex(session);
      phase.playing = playing; phase.before = playing; phase.last_valid = playing;
      phase.playing_native_pause = last_native_pause();
      last_media_probe_.reset();
    }
    catch (...) { hidden_media_.reset(); }
  }
#ifdef __APPLE__
  bool arm_isolated_pause(const std::string &session, uint64_t navigation)
  {
    return document_preview::test::arm_isolated_pause(window_.native_window_handle(), session, navigation);
  }
  bool pause_suspended_hidden_playback(const std::string &session,
                                      const document_preview::test::NativeHidePauseTrace &trace)
  {
    return document_preview::test::pause_suspended_hidden_playback(window_.native_window_handle(), session, trace);
  }
  std::shared_ptr<const document_preview::test::NativeCloseObservation> observe_native_close(
      const std::string &session, uint64_t watch_pause_navigation = 0) noexcept
  {
    try {
      return document_preview::test::observe_native_close(
          window_.native_window_handle(), session, watch_pause_navigation);
    }
    catch (...) { return {}; }
  }
  static Json visible_pause_events(const document_preview::test::VisiblePauseObservation &observation)
  {
    Json events = Json::array();
    for (size_t i = 0; i < observation.event_count; ++i) {
      const auto &event = observation.events[i];
      events.push_back({{"phase", event.phase}, {"elapsed_seconds", event.elapsed_seconds},
          {"visible", event.visible},
          {"raw_playback_state", event.playback_state ? Json(*event.playback_state) : Json(nullptr)}});
    }
    return events;
  }
  void visible_pause_diagnostic(const std::string &session, const Media &playing,
                                const std::shared_ptr<document_preview::ResourceSession> &resources,
                                const NativePause *previous = nullptr)
  {
    const auto close = observe_native_close(session);
    require(bool(close), "Visible pause diagnostic needs the exact native close observer");
    const auto parent = window_.native_window_handle();
    const auto last_dom_probe = last_media_probe_;
    const auto started = Clock::now();
    const auto observation = document_preview::test::begin_visible_pause_control(
        parent, session, playing.navigation_generation);
    require(bool(observation), "Could not request the production pause on the exact visible navigation");
    bool stayed_visible = true;
    const auto record = [&] {
      result_["visible_pause_observation"] = {{"session_sha256", core::Sha256::hex(session)},
          {"media_generation", observation->media_generation},
          {"navigation_generation", observation->navigation_generation},
          {"playing", media_json(playing)}, {"events", visible_pause_events(*observation)},
          {"native_non_playing_verified", observation->verified}, {"trace_overflow", observation->overflow},
          {"visible_at_poll_checks", stayed_visible}, {"host_visibility_lost", observation->visibility_lost},
          {"session_active_before_dom_probe", resources->active()},
          {"dom_probe_dispatched_during_hold", last_media_probe_ != last_dom_probe},
          {"elapsed_seconds", media_seconds(started, Clock::now())},
          {"close_reason", close->reason.empty() ? Json(nullptr) : Json(close->reason)},
          {"close_visible", observation->visible_at_close ? Json(*observation->visible_at_close) : Json(nullptr)},
          {"close_media_generation", close->reason.empty() ? Json(nullptr) : Json(close->media_generation)},
          {"close_navigation_generation", close->reason.empty() ? Json(nullptr) : Json(close->navigation_generation)},
          {"close_elapsed_seconds", close->reason.empty() ? Json(nullptr) : Json(media_seconds(started, close->when))}};
      if (previous) {
        result_["visible_pause_observation"]["previous_native_pause"] = native_pause_json(*previous);
      }
    };
    try {
      const auto until = Clock::now() + document_preview::detail::MediaPauseVerification::timeout +
                         std::chrono::milliseconds(250);
      // Only the production watchdog and native state callbacks run before the post-hold DOM probe.
      wait([&] {
        if (!resources->active()) { return true; }
        stayed_visible = document_preview::test::visible_pause_target(parent, session, *observation);
        return !stayed_visible || Clock::now() >= until;
      }, "Visible pause hold without DOM observation", 3);
    }
    catch (...) {
      try { record(); } catch (...) {} // Preserve the original wait failure.
      throw;
    }
    record(); save();
    require(!previous || observation->media_generation == previous->media_generation + 1,
        "Visible control must dispatch one new native pause after the previous pause");
    require(resources->active(), "Native media session closed during the visible hold without DOM observation");
    const auto end = observation->events.begin() + observation->event_count;
    require(stayed_visible && std::all_of(observation->events.begin(), end,
        [](const auto &event) { return event.visible; }), "The exact native pause target must remain visible");
    require(last_media_probe_ == last_dom_probe, "Visible pause hold must not dispatch a DOM sample");
    require(observation->verified && !observation->overflow,
        "Visible pause must pass the original native verification with a complete diagnostic trace");
    const auto after = media(session);
    result_["visible_pause_observation"]["after"] = media_json(after);
    result_["visible_pause_observation"]["paused_time_delta_seconds"] = after.current_time - playing.current_time;
    save();
    require(after.navigation_generation == playing.navigation_generation && after.paused && !after.ended && !after.seeking,
        "The first post-hold DOM sample must show the same visible media paused");
  }
  void hide_after_verified_pause_diagnostic(app::EditorArea &area, const std::string &session,
                                            const Media &playing, const NativePause &previous,
                                            const std::shared_ptr<document_preview::ResourceSession> &resources,
                                            const bool retain_visible_pause, const bool sample_hidden_dom)
  {
    using namespace document_preview;
    const auto parent = window_.native_window_handle();
    const auto close = observe_native_close(session, retain_visible_pause ? playing.navigation_generation : 0);
    require(bool(close), "Hide-after-verified-pause diagnostic needs the exact native close observer");
    const auto last_dom_probe = last_media_probe_;
    const auto started = Clock::now();
    const auto visible = test::begin_visible_pause_control(parent, session, playing.navigation_generation);
    require(bool(visible), "Could not request the native pause on the exact visible navigation");
    std::optional<Clock::time_point> confirmed, hide_requested, hold_started;
    std::optional<NativePause> hidden;
    std::optional<int> passive_playback;
    const auto record = [&] {
      const auto key = retain_visible_pause ? "hide_without_repeat_pause_observation" :
                                              "hide_after_verified_pause_observation";
      result_[key] = {
          {"session_sha256", core::Sha256::hex(session)}, {"playing", media_json(playing)},
          {"previous_native_pause", native_pause_json(previous)},
          {"visible_native_pause", {{"media_generation", visible->media_generation},
              {"navigation_generation", visible->navigation_generation}, {"verified", visible->verified},
              {"trace_overflow", visible->overflow}, {"events", visible_pause_events(*visible)}}},
          {"visible_confirmation_seconds", media_time(started, confirmed)},
          {"tab_request_seconds", media_time(started, hide_requested)},
          {"hold_begin_seconds", media_time(started, hold_started)},
          {"hide_dispatch_seconds", !retain_visible_pause && close->hide_pause && close->hide_pause->event_count ?
              Json(media_seconds(started, close->hide_pause->dispatched)) : Json(nullptr)},
          {"elapsed_seconds", media_seconds(started, Clock::now())},
          {"hidden_native_pause", hidden ? native_pause_json(*hidden) : Json(nullptr)},
          {"session_active", resources->active()},
          {"dom_probe_dispatched_during_control", last_media_probe_ != last_dom_probe}};
      if (retain_visible_pause) {
        result_[key]["passive_hidden_playback_state"] = passive_playback ? Json(*passive_playback) : Json(nullptr);
      }
      record_native_pause_trace(close.get(), session);
      record_hidden_native_close(close.get(), session, started);
    };
    try {
      constexpr auto hold = detail::MediaPauseVerification::timeout + std::chrono::milliseconds(250);
      wait([&] {
        return visible->verified || !resources->active() ||
            !test::visible_pause_target(parent, session, *visible) || Clock::now() - started >= hold;
      }, "Visible native non-Playing before hide", 3);
      require(resources->active() && test::visible_pause_target(parent, session, *visible) &&
          visible->verified && !visible->overflow && visible->event_count > 0 &&
          visible->media_generation == previous.media_generation + 1 &&
          visible->events[visible->event_count - 1].phase == "reply" &&
          visible->events[visible->event_count - 1].playback_state.has_value(),
          "The next native pause must verify on the same visible navigation before hiding");
      confirmed = Clock::now();

      if (retain_visible_pause) {
        require(test::retain_visible_pause_on_hide(parent, session, *visible),
            "Could not retain the verified visible pause through the next tab hide");
      }
      else {
        // The production listener issues its own pause before hiding. Watch that distinct generation.
        require(observe_native_close(session, playing.navigation_generation) == close && close->hide_pause &&
            close->hide_pause->media_generation == visible->media_generation + 1,
            "Could not arm the trace for the production hide pause");
      }
      hide_requested = Clock::now();
      tab(area, 1);
      hold_started = Clock::now();
      wait([&] { return !resources->active() || Clock::now() - *hold_started >= hold; },
          "Hidden native hold without DOM observation", 3);

      const auto &trace = *close->hide_pause;
      hidden = test::hidden_pause_target(parent, session, trace);
      require(resources->active() && hidden && hidden->acknowledged && hidden->verified &&
          !hidden->isolated_actuator && !trace.overflow,
          retain_visible_pause ? "The verified visible pause must still identify the exact hidden view" :
                                 "The production hide pause must independently verify on the exact hidden navigation");
      if (retain_visible_pause) {
        struct PendingPlayback { bool returned = false; std::optional<int> state; };
        const auto reply = std::make_shared<PendingPlayback>();
        require(test::probe_hidden_playback(parent, session, trace, [reply](std::optional<int> state) {
          reply->state = state;
          reply->returned = true;
        }), "Could not query playback on the exact hidden view");
        wait([&] { return reply->returned; }, "Read-only hidden native playback state", 3);
        passive_playback = reply->state;
        require(passive_playback.has_value() && resources->active() && close->reason.empty(),
            "The native playback reply must belong to the exact live hidden view");
      }
      require(last_media_probe_ == last_dom_probe, "Pause verification and hidden hold must not sample the DOM");
      const auto end = trace.events.begin() + trace.event_count;
      const auto hide = std::find_if(trace.events.begin(), end, [](const auto &event) { return event.phase == "hide"; });
      const auto reply_phase = retain_visible_pause ? "passive-reply" : "reply";
      require(!trace.overflow && hide != end && trace.events.front().phase == "dispatch" && trace.events.front().visible &&
          std::any_of(hide, end, [reply_phase](const auto &event) {
            return event.phase == reply_phase && event.playback_state.has_value();
          }) && std::all_of(hide, end, [](const auto &event) {
            return !event.visible && event.webview_hidden && !event.owns_focus &&
                event.phase != "superseded" && event.phase != "close";
          }), "The matching native reply must be observed after the actual tab hide");
      if (retain_visible_pause) {
        const auto suppressed = std::find_if(trace.events.begin(), hide, [](const auto &event) {
          return event.phase == "repeat-pause-suppressed";
        });
        require(trace.media_generation == visible->media_generation && trace.dispatched < *confirmed &&
            suppressed != hide && suppressed->visible &&
            suppressed->elapsed_seconds >= media_seconds(trace.dispatched, *hide_requested) &&
            std::count_if(trace.events.begin(), end, [](const auto &event) { return event.phase == "dispatch"; }) == 1 &&
            end - hide == 3 && (hide + 1)->phase == "passive-query" && (hide + 2)->phase == "passive-reply",
            "The actual tab hide must retain the visible pause and issue only the read-only playback query");
      }
      else {
        require(trace.dispatched >= *hide_requested, "The repeated pause must be dispatched by the tab hide");
      }
    }
    catch (...) {
      try { record(); } catch (...) {} // Keep the diagnostic failure even if evidence capture also fails.
      throw;
    }
    record(); save();
    if (sample_hidden_dom) { hidden_dom_tail(area, session, resources, *close); }
  }
  void repeat_verified_visible_pause_diagnostic(
      app::EditorArea &area, const std::string &session, const Media &playing, const NativePause &previous,
      const std::shared_ptr<document_preview::ResourceSession> &resources)
  {
    using namespace document_preview;
    const auto parent = window_.native_window_handle();
    const auto close = observe_native_close(session);
    const auto *viewport = widget("reports_document_viewport");
    require(close && visible(viewport), "Visible repeat needs the exact ready report and close observer");
    const auto started = Clock::now();
    const auto bounds = viewport->rect;
    const auto *focus = screen_.focused_region();
    const auto dom_reads = dom_probe_requests_, captures = os_capture_requests_;
    const auto input_clicks = clicks, input_wheels = wheels;
    const auto bound = [&] {
      const auto *current = widget("reports_document_viewport");
      const auto handle = window_.native_window_handle();
      return resources->active() && handle.kind == parent.kind && handle.value == parent.value && area.active_tab() == 0 &&
          visible(current) && current->rect.x == bounds.x && current->rect.y == bounds.y &&
          current->rect.w == bounds.w && current->rect.h == bounds.h &&
          screen_.focused_region() == focus && !screen_.ui()->native_view_interaction_blocked() &&
          dom_probe_requests_ == dom_reads && os_capture_requests_ == captures &&
          clicks == input_clicks && wheels == input_wheels;
    };
    using Pause = test::VisiblePauseObservation;
    std::array<std::shared_ptr<const Pause>, 2> observations;
    std::array<bool, 2> exact_targets{};
    const auto record = [&] {
      auto &summary = result_["repeat_verified_visible_pause"];
      summary = {{"session_sha256", core::Sha256::hex(session)},
          {"navigation_generation", playing.navigation_generation},
          {"previous_media_generation", previous.media_generation}, {"same_visible_route", bound()},
          {"dom_and_capture_counts_unchanged", dom_probe_requests_ == dom_reads && os_capture_requests_ == captures},
          {"session_active", resources->active()},
          {"close_reason", close->reason.empty() ? Json(nullptr) : Json(close->reason)}};
      auto &traces = result_["repeat_verified_visible_pause_traces"];
      traces = {{"playing", media_json(playing)}, {"previous_native_pause", native_pause_json(previous)}};
      if (!close->reason.empty()) {
        traces["native_close"] = {{"reason", close->reason}, {"elapsed_seconds", media_seconds(started, close->when)},
            {"media_generation", close->media_generation}, {"navigation_generation", close->navigation_generation},
            {"native_pause", native_pause_json(close->pause)}};
      }
      for (size_t i = 0; i < observations.size(); ++i) {
        const auto &pause = observations[i];
        const char *label = i == 0 ? "first" : "repeat";
        summary[label] = nullptr;
        if (!pause) { continue; }
        const auto end = pause->events.begin() + pause->event_count;
        const auto ack = std::find_if(pause->events.begin(), end, [](const auto &event) { return event.phase == "ack"; });
        // The production verifier stops recording accepted replies at the first non-Playing result.
        const auto *reply = pause->verified && pause->event_count && (end - 1)->phase == "reply" &&
            (end - 1)->playback_state ? &*(end - 1) : nullptr;
        summary[label] = {{"media_generation", pause->media_generation},
            {"navigation_generation", pause->navigation_generation}, {"exact_native_target", exact_targets[i]},
            {"verified", pause->verified}, {"visibility_lost", pause->visibility_lost},
            {"visible_at_close", pause->visible_at_close ? Json(*pause->visible_at_close) : Json(nullptr)},
            {"trace_overflow", pause->overflow},
            {"ack_seconds", ack != end ? Json(ack->elapsed_seconds) : Json(nullptr)},
            {"first_non_playing_seconds", reply ? Json(reply->elapsed_seconds) : Json(nullptr)},
            {"first_non_playing_state", reply ? Json(*reply->playback_state) : Json(nullptr)}};
        traces[label] = visible_pause_events(*pause);
      }
    };
    try {
      for (size_t i = 0; i < observations.size(); ++i) {
        require(bound(), "Visible repeat changed its viewport, focus, input or observation scope");
        require(i == 0 || test::visible_pause_target(parent, session, *observations.front()),
            "Visible repeat no longer targets the first verified native view");
        auto &pause = observations[i];
        pause = test::begin_visible_pause_control(parent, session, playing.navigation_generation);
        require(bool(pause), "Could not request the next pause on the exact visible navigation");
        const auto current = [&] { return bound() && test::visible_pause_target(parent, session, *pause); };
        const auto deadline = Clock::now() + detail::MediaPauseVerification::timeout + std::chrono::milliseconds(250);
        wait([&] { return pause->verified || !current() || Clock::now() >= deadline; },
            "Independent native verification of the visible pause", 3);
        exact_targets[i] = current();
        const auto end = pause->events.begin() + pause->event_count;
        require(exact_targets[i] && pause->verified && !pause->overflow && pause->event_count > 0 &&
            pause->media_generation == previous.media_generation + i + 1 &&
            pause->navigation_generation == playing.navigation_generation &&
            pause->events.front().phase == "dispatch" && (end - 1)->phase == "reply" &&
            (end - 1)->playback_state.has_value() &&
            std::any_of(pause->events.begin(), end, [](const auto &event) { return event.phase == "ack"; }) &&
            std::all_of(pause->events.begin(), end, [](const auto &event) { return event.visible; }),
            i == 0 ? "The first visible pause must verify before the repeat" :
                     "The already-paused repeat must verify on the same visible navigation");
      }
    }
    catch (...) {
      try { record(); } catch (...) {} // Keep the diagnostic failure even if evidence capture also fails.
      throw;
    }
    record(); save();
  }
  void suspend_reveal_diagnostic(app::EditorArea &area, const std::string &session, uint64_t navigation,
                                 const std::shared_ptr<document_preview::ResourceSession> &resources,
                                 const std::function<Media(const char *)> &explicit_play)
  {
    using namespace document_preview;
    using test::PlaybackState;
    constexpr auto budget = detail::MediaPauseVerification::timeout;
    constexpr auto hold = std::chrono::milliseconds(750);
    const auto parent = window_.native_window_handle();
    const auto started = Clock::now();
    std::shared_ptr<const test::NativeCloseObservation> close;
    const auto starting_dom_probe = last_media_probe_;
    Json evidence = {{"stage", "initial-inline-play"}, {"session_sha256", core::Sha256::hex(session)},
        {"navigation_generation", navigation},
        {"native_requests", Json::object()}, {"hold_seconds", std::chrono::duration<double>(hold).count()},
        {"native_callback_budget_seconds", std::chrono::duration<double>(budget).count()}};
    const auto record = [&] {
      evidence["session_active"] = resources->active();
      if (last_media_probe_ && last_media_probe_ != starting_dom_probe) {
        const auto &probe = *last_media_probe_;
        evidence["last_dom_read"] = {{"accepted", probe.accepted},
            {"dispatch_seconds", media_time(probe.started, probe.dispatched)},
            {"callback_seconds", media_time(probe.started, probe.callback)},
            {"finished_seconds", media_time(probe.started, probe.finished)}, {"ok", probe.reply && probe.reply->ok},
            {"media", probe.reply && probe.reply->ok ? media_json(probe.reply->media) : Json(nullptr)}};
      }
      result_["suspend_reveal"] = std::move(evidence);
      record_native_pause_trace(close.get(), session, "suspend_reveal_hide_pause_trace");
      record_hidden_native_close(close.get(), session, started);
      save();
    };
    try {
      const auto playing = explicit_play("suspend-reveal-initial-play");
      evidence["playing_before_suspend"] = media_json(playing);
      evidence["stage"] = "bind-visible-navigation";
      require(playing.navigation_generation == navigation, "Initial Play must advance the original navigation");
      close = observe_native_close(session, navigation);
      require(close && close->hide_pause, "Suspension control needs the exact native hide trace");
      const auto &trace = *close->hide_pause;
      evidence["initial_media_generation"] = trace.media_generation - 1;
      evidence["hide_media_generation"] = trace.media_generation;
      const auto visible_target = [&](bool before_hide) {
        return resources->active() && close->reason.empty() && !trace.overflow && area.active_tab() == 0 &&
            test::visible_playback_target(parent, session, trace, before_hide);
      };
      const auto poll = [&](Clock::time_point deadline, const auto &predicate) {
        return reports_native_test::poll_before<Clock>(deadline, predicate,
            [this](bool wait_for_event) { process(wait_for_event); }, [] {});
      };
      struct NativeReply {
        std::optional<int> value;
        std::optional<Clock::time_point> when;
      };
      const auto request = [&](const char *phase, bool before_hide, const char *field, int expected, auto dispatch) {
        evidence["stage"] = phase;
        auto &entry = evidence["native_requests"][phase];
        const auto requested = Clock::now();
        const auto reply = std::make_shared<NativeReply>();
        const bool accepted = dispatch([reply](std::optional<int> value) {
          reply->value = value; reply->when = Clock::now();
        });
        entry = {{"accepted", accepted}, {"expected", expected}, {"requested_seconds", media_seconds(started, requested)}};
        const auto deadline = requested + budget;
        if (accepted) { poll(deadline, [&] { return reply->when || !visible_target(before_hide); }); }
        entry["callback_seconds"] = media_time(requested, reply->when);
        entry["same_visible_target"] = visible_target(before_hide);
        entry[field] = reply->value ? Json(*reply->value) : Json(nullptr);
        require(accepted && reply->when && *reply->when < deadline && reply->value && visible_target(before_hide),
            std::string("Missing, late or stale Cocoa receipt for ") + phase);
        require(*reply->value == expected, std::string("Unexpected Cocoa receipt for ") + phase);
      };
      const auto state = [&](const char *phase, bool before_hide, PlaybackState expected) {
        request(phase, before_hide, "raw_playback_state", int(expected), [&](auto reply) {
          return test::probe_visible_playback(parent, session, trace, before_hide,
              [reply](std::optional<PlaybackState> value) {
                reply(value ? std::optional<int>(int(*value)) : std::nullopt);
              });
        });
      };
      const auto suspend = [&](const char *phase, bool suspend_playback) {
        request(phase, suspend_playback, "acknowledged", 1, [&](auto reply) {
          return test::set_visible_playback_suspended(parent, session, trace, suspend_playback,
              [reply](bool bound) { reply(int(bound)); });
        });
      };
      state("initial-playing", true, PlaybackState::Playing);
      suspend("suspend", true);
      state("visible-suspended", true, PlaybackState::Suspended);

      evidence["stage"] = "ordinary-tab-hide";
      const auto prior_dom = dom_probe_requests_, prior_captures = os_capture_requests_;
      tab(area, 1);
      require(trace.event_count && trace.events.front().phase == "dispatch" && trace.events.front().visible,
          "Ordinary tab hide must dispatch the native pause while still visible");
      const auto hidden_pause = [&] { return test::hidden_pause_target(parent, session, trace); };
      const auto deadline = trace.dispatched + budget + std::chrono::milliseconds(250);
      poll(deadline, [&] {
        const auto pause = hidden_pause();
        return !resources->active() || !pause || pause->verified;
      });
      const auto pause = hidden_pause();
      evidence["hidden_pause"] = pause ? native_pause_json(*pause) : Json(nullptr);
      require(pause && pause->acknowledged && pause->verified && !pause->isolated_actuator && !trace.overflow,
          "Ordinary hide pause must acknowledge and verify while the exact suspension is held");
      evidence["stage"] = "hidden-hold";
      require(!poll(Clock::now() + hold, [&] { return !hidden_pause(); }) && hidden_pause() &&
          dom_probe_requests_ == prior_dom && os_capture_requests_ == prior_captures,
          "The hidden hold must retain the exact paused view without DOM reads or captures");

      evidence["stage"] = "reveal-same-navigation";
      tab(area, 0);
      const auto *viewport = widget("reports_document_viewport");
      require(visible(viewport), "The returned report needs a visible viewport");
      // Leave any header tooltip before measuring the no-input interval.
      move_pointer({viewport->rect.cx(), viewport->rect.cy()});
      require(poll(Clock::now() + budget, [&] { return visible_target(false); }),
          "The same Cocoa view must return before releasing the suspension");
      suspend("release", false);
      state("released-paused", false, PlaybackState::Paused);
      evidence["stage"] = "released-first-dom";
      const auto paused = media(session, std::chrono::duration<double>(budget).count());
      evidence["first_revealed_dom"] = media_json(paused);
      require(visible_target(false) && paused.navigation_generation == playing.navigation_generation &&
          paused.paused && !paused.ended && !paused.seeking, "Released media must still be paused without Play");
      evidence["stage"] = "released-no-input-hold";
      const auto held = held_media(1, "released-no-input-hold", session, paused,
          std::chrono::duration<double>(hold).count());
      evidence["held_revealed_dom"] = media_json(held);
      state("released-hold-paused", false, PlaybackState::Paused);

      evidence["stage"] = "explicit-inline-play";
      const auto resumed = explicit_play("suspend-reveal-explicit-play");
      evidence["resumed_dom"] = media_json(resumed);
      require(visible_target(false) && resumed.navigation_generation == held.navigation_generation &&
          !resumed.paused && resumed.current_time >= held.current_time + 0.10,
          "Explicit native Play must advance the released media on the same navigation");
      state("explicit-playing", false, PlaybackState::Playing);
      evidence["stage"] = "observed";
    }
    catch (...) {
      try { record(); } catch (...) {} // Preserve the diagnostic failure.
      throw;
    }
    record();
  }
  void hidden_dom_tail(app::EditorArea &area, const std::string &session,
                       const std::shared_ptr<document_preview::ResourceSession> &resources,
                       const document_preview::test::NativeCloseObservation &close)
  {
    using namespace document_preview;
    constexpr auto hold = std::chrono::milliseconds(400);
    constexpr double stable_delta = 0.10, advancing_delta = 0.15;
    const auto parent = window_.native_window_handle();
    const auto &trace = *close.hide_pause;
    const auto event_count = trace.event_count;
    const auto same_hidden = [&] {
      return area.active_tab() == 1 && resources->active() && close.reason.empty() &&
          !trace.overflow && trace.event_count == event_count &&
          test::hidden_pause_target(parent, session, trace).has_value();
    };
    const auto started = Clock::now();
    auto &evidence = result_["hidden_dom_tail"];
    evidence = {{"session_sha256", core::Sha256::hex(session)},
        {"media_generation", trace.media_generation}, {"navigation_generation", trace.navigation_generation},
        {"hold_seconds", std::chrono::duration<double>(hold).count()},
        {"stable_delta_seconds", stable_delta}, {"advancing_delta_seconds", advancing_delta},
        {"samples", Json::array()}, {"outcome", "incomplete"}};
    save();
    const auto sample = [&] {
      require(same_hidden(), "DOM tail requires the exact hidden view before sampling");
      const auto observed = media(session, 3);
      const auto &probe = *last_media_probe_;
      const bool exact_hidden = same_hidden() && observed.navigation_generation == trace.navigation_generation;
      evidence["samples"].push_back({{"media", media_json(observed)}, {"exact_hidden", exact_hidden},
          {"dispatch_seconds", media_time(started, probe.dispatched)},
          {"reply_seconds", media_time(started, probe.callback)}});
      save();
      require(exact_hidden, "DOM tail reply must belong to the exact hidden view");
      return observed;
    };
    const auto before = sample();
    const auto until = Clock::now() + hold;
    wait([&] { return !resources->active() || Clock::now() >= until; }, "Quiet hidden DOM interval", 2);
    const auto after = sample();
    const auto delta = after.current_time - before.current_time;
    const bool comparable = !before.ended && !after.ended && !before.seeking && !after.seeking &&
        before.ready_state >= 2 && after.ready_state >= 2;
    evidence["current_time_delta_seconds"] = delta;
    if (comparable && before.paused && after.paused && std::abs(delta) <= stable_delta) {
      evidence["outcome"] = "paused_stable";
    }
    else if (comparable && !before.paused && !after.paused && delta >= advancing_delta) {
      evidence["outcome"] = "playing_advancing";
    }
    else { evidence["outcome"] = "inconclusive"; }
    save();
  }
  void first_toolbar_pause(app::EditorArea &area, const std::string &session, const Media &playing,
                           Clock::time_point play_returned,
                           const std::shared_ptr<document_preview::ResourceSession> &resources, bool immediate,
                           Options::FirstToolbarFrames frames)
  {
    const auto delay = immediate ? std::chrono::milliseconds(0) : kPassiveDelay;
    constexpr auto budget = document_preview::detail::MediaPauseVerification::timeout;
    constexpr auto first_offset = std::chrono::milliseconds(200);
    constexpr auto second_offset = std::chrono::milliseconds(600);
    constexpr auto dispatch_limit = std::chrono::milliseconds(100);
    constexpr auto sample_window = std::chrono::milliseconds(100);
    const auto close = observe_native_close(session, playing.navigation_generation);
    require(close && close->hide_pause && close->hide_pause->event_count == 0 &&
        close->hide_pause->media_generation == 1, "First toolbar pause needs the exact first native trace");
    const auto &trace = *close->hide_pause;
    const auto *viewport = widget("reports_document_viewport");
    require(viewport && visible(viewport), "First toolbar pause needs the visible report viewport");
    const auto rect = viewport->rect;
    const int width = window_.width(), height = window_.height();
    const auto layout_bound = [&] {
      const auto *current = widget("reports_document_viewport");
      return resources->active() && close->reason.empty() && !trace.overflow && area.active_tab() == 0 &&
          current && visible(current) && current->rect.x == rect.x && current->rect.y == rect.y &&
          current->rect.w == rect.w && current->rect.h == rect.h && window_.width() == width &&
          window_.height() == height && !screen_.ui()->native_view_interaction_blocked();
    };
    const auto prior_probe = last_media_probe_;
    const auto prior_dom_requests = dom_probe_requests_, prior_os_requests = os_capture_requests_;
    const auto delay_bound = [&] {
      return layout_bound() && trace.event_count == 0 && last_media_probe_ == prior_probe &&
          dom_probe_requests_ == prior_dom_requests && os_capture_requests_ == prior_os_requests;
    };
    auto &evidence = result_[immediate ? "first_toolbar_pause_immediate" : "first_toolbar_pause_delay"];
    evidence = {{"stage", immediate ? "immediate" : "passive-delay"}, {"outcome", "inconclusive"},
        {"session_sha256", core::Sha256::hex(session)}, {"navigation_generation", trace.navigation_generation},
        {"media_generation", trace.media_generation}, {"playing", media_json(playing)},
        {"delay_seconds", std::chrono::duration<double>(delay).count()},
        {"request_tolerance_seconds", std::chrono::duration<double>(kPassiveDelayTolerance).count()},
        {"dispatch_limit_seconds_after_request", std::chrono::duration<double>(dispatch_limit).count()},
        {"sample_budget_seconds_from_dispatch", std::chrono::duration<double>(budget).count()},
        {"later_sample_min_seconds_from_dispatch", {0.20, 0.60}},
        {"later_sample_window_seconds", std::chrono::duration<double>(sample_window).count()},
        {"samples", Json::array()}};
    const auto poll = [&](Clock::time_point deadline, const auto &ready) {
      return reports_native_test::poll_before<Clock>(deadline, ready,
          [this](bool wait_for_event) { process(wait_for_event); }, [] {});
    };
    std::optional<Clock::time_point> requested, click_returned;
    const auto record = [&] {
      evidence["play_return_to_pause_request_seconds"] = media_time(play_returned, requested);
      evidence["play_return_to_click_return_seconds"] = media_time(play_returned, click_returned);
      evidence["play_return_to_native_dispatch_seconds"] = trace.event_count ?
          Json(media_seconds(play_returned, trace.dispatched)) : Json(nullptr);
      evidence["native_close_reason"] = close->reason.empty() ? Json(nullptr) : Json(close->reason);
      record_native_pause_trace(close.get(), session,
          immediate ? "first_toolbar_pause_immediate_trace" : "first_toolbar_pause_trace");
      save();
    };
    const auto frame_target = [&](bool before_pause) {
      return layout_bound() && document_preview::test::visible_playback_target(
          window_.native_window_handle(), session, trace, before_pause);
    };
    if (frames == Options::FirstToolbarFrames::Playing) {
      evidence["stage"] = "playing-frame-clock";
      first_toolbar_frame_clock(rect, playing, play_returned, std::nullopt, [&] {
        return last_media_probe_ == prior_probe && frame_target(true);
      });
      save();
      return;
    }
    std::optional<Media> settled;
    try {
      const auto delay_end = play_returned + delay;
      const bool drifted = !immediate && poll(delay_end, [&] { return !delay_bound(); });
      evidence["dom_probe_counter_unchanged_during_delay"] =
          dom_probe_requests_ == prior_dom_requests && last_media_probe_ == prior_probe;
      evidence["os_capture_counter_unchanged_during_delay"] = os_capture_requests_ == prior_os_requests;
      require(!drifted && delay_bound(), immediate ? "Immediate toolbar pause lost its binding before the click" :
          "First toolbar pause lost its binding during the passive delay");
      evidence["stage"] = "toolbar-click";
      requested = Clock::now();
      const bool request_in_bound = *requested >= delay_end && *requested <= delay_end + kPassiveDelayTolerance;
      evidence["pause_request_within_declared_bound"] = request_in_bound;
      require(request_in_bound, immediate ? "Immediate toolbar pause request exceeded its timing bound" :
          "First toolbar pause request exceeded the passive timing bound");
      click("reports_document_pause", area);
      click_returned = Clock::now();
      require(trace.event_count && trace.events.front().phase == "dispatch" &&
          trace.dispatched >= *requested && trace.dispatched <= *click_returned,
          "Toolbar click did not dispatch the exact first native pause");
      require(trace.dispatched <= *requested + dispatch_limit, "Toolbar native dispatch exceeded the diagnostic window");
      const auto same_target = [&] {
        const auto end = trace.events.begin() + trace.event_count;
        return layout_bound() && std::none_of(trace.events.begin(), end, [](const auto &event) {
          return event.phase == "superseded";
        });
      };
      const auto deadline = trace.dispatched + budget;
      const auto sample = [&](const char *phase, Clock::time_point sample_deadline) {
        evidence["stage"] = phase;
        const auto now = Clock::now();
        require(now < sample_deadline && same_target(), "Toolbar pause sample lost its target or timing window");
        const auto observed = media(session, std::chrono::duration<double>(sample_deadline - now).count());
        const auto &probe = *last_media_probe_;
        const bool bound = probe.callback && *probe.callback < sample_deadline && same_target() &&
            observed.navigation_generation == trace.navigation_generation;
        evidence["samples"].push_back({{"phase", phase}, {"media", media_json(observed)},
            {"dispatch_seconds_from_pause", media_time(trace.dispatched, probe.dispatched)},
            {"reply_seconds_from_pause", media_time(trace.dispatched, probe.callback)},
            {"delta_from_playing_seconds", observed.current_time - playing.current_time},
            {"native_pause", native_pause_pair_json(last_native_pause())}, {"within_bound", bound}});
        require(bound, "Toolbar pause DOM reply lost its navigation or timing window");
        return observed;
      };
      // Sample once after the same click as the mandatory case, which instead waits for a paused DOM predicate.
      const auto early = sample("early-dom", trace.dispatched + first_offset);
      const auto later_sample = [&](const char *phase, auto offset) {
        evidence["stage"] = phase;
        const auto earliest = trace.dispatched + offset;
        const auto sample_deadline = std::min(earliest + sample_window, deadline);
        require(poll(sample_deadline, [&] { return !same_target() || Clock::now() >= earliest; }) &&
            same_target(), "Toolbar pause lost its target before the later sample");
        return sample(phase, sample_deadline);
      };
      const auto first = later_sample("first-bounded-dom", first_offset);
      const auto second = later_sample("second-bounded-dom", second_offset);
      const auto paused = [](const Media &m) { return m.paused && !m.ended && !m.seeking; };
      evidence["early_pause_checks"] = {{"lower_time_gt_0_05", early.current_time > 0.05},
          {"upper_time_lt_2_6", early.current_time < 2.6}, {"not_ended", !early.ended}};
      evidence["later_samples_paused"] = paused(first) && paused(second);
      evidence["later_samples_delta_seconds"] = second.current_time - first.current_time;
      evidence["stage"] = "observed";
      evidence["outcome"] = !paused(early) ? "early_sample_not_paused" : early.current_time > 0.05 ?
          "early_paused_above_floor" : "early_paused_at_or_below_floor";
      if (paused(first) && paused(second) && std::abs(second.current_time - first.current_time) <= 0.10) {
        settled = second;
      }
    }
    catch (...) {
      try { record(); } catch (...) {} // Keep the original failure and any samples already observed.
      throw;
    }
    record();
    if (frames == Options::FirstToolbarFrames::Paused) {
      const auto settled_probe = last_media_probe_;
      first_toolbar_frame_clock(rect, settled.value_or(playing), play_returned, trace.dispatched, [&] {
        return settled.has_value() && last_media_probe_ == settled_probe && frame_target(false);
      });
      save();
    }
  }
  void first_toolbar_frame_clock(ui::Rect viewport, const Media &geometry, Clock::time_point play_returned,
                                 std::optional<Clock::time_point> pause_dispatch,
                                 const std::function<bool()> &bound)
  {
    const bool paused = pause_dispatch.has_value();
    const auto deadline = paused ? Clock::now() + frame_clock::kPausedBudget : play_returned + frame_clock::kPlayingBudget;
    const auto *arm = paused ? "paused" : "uninterrupted_play";
    ui::Rect picture;
    try { picture = media_rectangle(viewport, geometry); }
    catch (const std::runtime_error &error) {
      result_["first_toolbar_frame_clock"] = {{"arm", arm}, {"outcome", "inconclusive"},
          {"geometry_error", error.what()}, {"navigation_generation", geometry.navigation_generation},
          {"dom_time_at_geometry_sample", geometry.current_time}, {"samples", Json::array()}};
      return;
    }
    std::vector<frame_clock::Capture> captures;
    std::optional<int> first, previous, stable;
    std::optional<Clock::time_point> first_nonzero_requested, first_nonzero_completed;
    for (int index = 1; index <= frame_clock::kMaxCapturesPerArm; ++index) {
      captures.push_back(frame_clock_capture(paused ? "paused" : "playing", index, picture, deadline, bound));
      const auto &capture = captures.back();
      if (std::string_view(capture.status) != "completed") { break; }
      const auto id = capture.reading.id;
      if (!id) { previous.reset(); continue; }
      if (*id > frame_clock::kPlayingMaxId) { break; }
      if (!first) { first = id; }
      if (paused && previous == id) { stable = id; break; }
      if (!paused && *id > 0) {
        first_nonzero_requested = capture.requested;
        first_nonzero_completed = capture.completed;
        break;
      }
      previous = id;
    }
    frame_clock_write(captures);
    const bool persisted = std::all_of(captures.begin(), captures.end(), [](const auto &capture) {
      return std::string_view(capture.status) != "completed" ||
          (!capture.file.empty() && core::is_sha256_hex(capture.sha256));
    });
    const bool observed = persisted && (paused ? stable.has_value() : first_nonzero_requested.has_value());
    Json samples = Json::array();
    for (const auto &capture : captures) {
      samples.push_back(frame_clock::capture_json(capture, play_returned, pause_dispatch));
    }
    result_["first_toolbar_frame_clock"] = {{"arm", arm},
        {"outcome", observed ? "observed" : "inconclusive"}, {"samples", std::move(samples)},
        {"navigation_generation", geometry.navigation_generation},
        {"picture_rect_client_top_left", {picture.x, picture.y, picture.w, picture.h}},
        {"dom_time_at_geometry_sample", geometry.current_time},
        {"dom_frame_at_geometry_sample", frame_clock::dom_frame(geometry.current_time)},
        {"first_decoded_frame", first ? Json(*first) : Json(nullptr)},
        {"stable_paused_frame", stable ? Json(*stable) : Json(nullptr)},
        {"first_nonzero_requested_seconds", media_time(play_returned, first_nonzero_requested)},
        {"first_nonzero_completed_seconds", media_time(play_returned, first_nonzero_completed)}};
  }
  void fresh_native_pause_dom_diagnostic(app::EditorArea &area, const std::string &session,
                                         const Media &playing, const Media &last_seek, const NativePause &previous,
                                         const std::shared_ptr<document_preview::ResourceSession> &resources,
                                         bool keep_visible, const frame_clock::Plan *plan = nullptr)
  {
    using namespace document_preview;
    require(!plan || keep_visible, "The frame-clock diagnostic only extends the visible sequence");
    constexpr auto budget = detail::MediaPauseVerification::timeout;
    constexpr auto first_sample_offset = std::chrono::milliseconds(200);
    constexpr auto interval = std::chrono::milliseconds(400);
    const auto parent = window_.native_window_handle();
    const auto close = observe_native_close(session, playing.navigation_generation);
    require(previous.available && previous.navigation_generation == playing.navigation_generation &&
        close && close->hide_pause, "Fresh pause needs the previous pause and exact next native trace");
    const auto &trace = *close->hide_pause;
    require(trace.media_generation == previous.media_generation + 1, "Fresh control must observe the next pause");
    const char *reply_key = keep_visible ? "first_visible_native_reply" : "first_hidden_native_reply";
    // ordered_json objects are vector-backed: later result_ insertions (trace, close, verdict)
    // must not reallocate under the evidence reference below.
    result_.get_ref<Json::object_t &>().reserve(result_.size() + 16);
    auto &evidence = result_[plan ? "visible_frame_clock" : keep_visible ? "fresh_native_visible_dom" : "fresh_native_hide_dom"];
    evidence = {{"session_sha256", core::Sha256::hex(session)}, {"media_generation", trace.media_generation},
        {"navigation_generation", trace.navigation_generation},
        {keep_visible ? "playing_before_pause" : "playing_before_hide", media_json(playing)},
        {"last_seek", media_json(last_seek)}, {"previous_native_pause", native_pause_json(previous)},
        {reply_key, nullptr}, {"samples", Json::array()}, {"stage", keep_visible ? "pause" : "tab"},
        {"deadline_origin", keep_visible ? "before visible native pause request" : "before actual tab click"},
        {"budget_seconds", std::chrono::duration<double>(budget).count()},
        {"first_sample_min_seconds_from_dispatch", std::chrono::duration<double>(first_sample_offset).count()},
        {"sample_interval_seconds", std::chrono::duration<double>(interval).count()}};
    std::vector<frame_clock::Capture> clock_captures;
    std::optional<int> last_playing_id, stable_paused_id;
    std::optional<Clock::time_point> clock_pause_dispatched;
    const auto *clock_viewport = widget("reports_document_viewport");
    const auto clock_layout = clock_viewport ? clock_viewport->rect : ui::Rect{};
    const int clock_width = window_.width(), clock_height = window_.height();
    // No resize, scroll, tab or popup between the geometry source and every capture.
    const auto clock_layout_same = [&] {
      const auto *v = widget("reports_document_viewport");
      return clock_viewport && v && visible(v) && v->rect.x == clock_layout.x && v->rect.y == clock_layout.y &&
          v->rect.w == clock_layout.w && v->rect.h == clock_layout.h && window_.width() == clock_width &&
          window_.height() == clock_height && screen_.ui() && !screen_.ui()->native_view_interaction_blocked();
    };
    const auto clock_record = [&](const char *outcome, const char *reason) noexcept {
      try {
        frame_clock_write(clock_captures);
        if (std::string_view(outcome) != "inconclusive" && !frame_clock::audit_complete(clock_captures)) {
          outcome = "inconclusive";
          reason = "the final two playing and paused OS captures were not all persisted with their SHA-256";
        }
        Json captures = Json::array(), playing_ids = Json::array(), paused_ids = Json::array();
        for (const auto &capture : clock_captures) {
          captures.push_back(frame_clock::capture_json(capture, plan->play_returned, clock_pause_dispatched));
          const Json id = capture.reading.id ? Json(*capture.reading.id) : Json(nullptr);
          (capture.arm == "playing" ? playing_ids : paused_ids).push_back(id);
        }
        Json dom_frames = Json::array();
        for (const auto &sample : evidence.at("samples")) {
          dom_frames.push_back(frame_clock::dom_frame(sample.at("media").at("current_time").get<double>()));
        }
        evidence["captures"] = std::move(captures);
        evidence["last_playing_frame_id"] = last_playing_id ? Json(*last_playing_id) : Json(nullptr);
        evidence["stable_paused_frame_id"] = stable_paused_id ? Json(*stable_paused_id) : Json(nullptr);
        evidence["outcome"] = outcome; evidence["outcome_reason"] = reason;
        result_["frame_clock_verdict"] = {{"outcome", outcome}, {"reason", reason}, {"stage", evidence.at("stage")},
            {"session_sha256", evidence.at("session_sha256")},
            {"navigation_generation", evidence.at("navigation_generation")},
            {"playing_ids", std::move(playing_ids)}, {"paused_ids", std::move(paused_ids)},
            {"dom_frames", std::move(dom_frames)}, {"last_playing_frame_id", evidence.at("last_playing_frame_id")},
            {"stable_paused_frame_id", evidence.at("stable_paused_frame_id")}};
        save();
        return std::string_view(outcome) != "inconclusive";
      }
      catch (...) { return false; } // Keep any original observation failure.
    };
    const auto clock_fail = [&](const char *reason) {
      clock_record("inconclusive", reason);
      throw std::runtime_error(std::string("Visible frame clock inconclusive: ") + reason);
    };
    const auto clock_status = [&](const frame_clock::Capture &capture, const char *late, const char *unbound,
                                  const char *failed) {
      const std::string_view status = capture.status;
      if (status == "late") { clock_fail(late); }
      if (status == "unbound") { clock_fail(unbound); }
      if (status != "completed") { clock_fail(failed); }
    };
    if (plan) {
      evidence["fixture"] = {{"name", "frame-clock-preview.mp4"}, {"size", kFrameClockMediaSize},
          {"sha256", kFrameClockMediaSha256}};
      evidence["source_sha256"] = plan->source_sha256;
      evidence["picture_rect_client_top_left"] = {plan->picture.x, plan->picture.y, plan->picture.w, plan->picture.h};
      evidence["marker"] = "Top-left 2x8 luma cells of 25x16 source px: guard, ID b5..b0, even parity; row 1 complements";
      evidence["binding"] = "Every capture: same session resources active, no native close, exact layout and client size, "
          "no DOM probe. Playing arm: next-pause trace still empty, Reports tab active; the exact navigation is then "
          "required by the visible pause request. Paused arm: exact verified visible pause target";
      evidence["limits"] = {{"playing_budget_seconds_from_play_return", std::chrono::duration<double>(frame_clock::kPlayingBudget).count()},
          {"paused_budget_seconds_after_settle", std::chrono::duration<double>(frame_clock::kPausedBudget).count()},
          {"max_captures_per_arm", frame_clock::kMaxCapturesPerArm}, {"playing_max_frame_id", frame_clock::kPlayingMaxId},
          {"late", "a capture not delivered before its arm budget"}};
      evidence["stage"] = "playing-baseline";
      if (!clock_viewport || plan->viewport.x != clock_layout.x || plan->viewport.y != clock_layout.y ||
          plan->viewport.w != clock_layout.w || plan->viewport.h != clock_layout.h) {
        clock_fail("native viewport layout changed after the picture geometry was taken");
      }
      const auto prior_dom = last_media_probe_;
      const auto playing_deadline = plan->play_returned + frame_clock::kPlayingBudget;
      const auto bound = [&] {
        return resources->active() && close->reason.empty() && !trace.overflow && trace.event_count == 0 &&
            area.active_tab() == 0 && clock_layout_same() && last_media_probe_ == prior_dom;
      };
      std::optional<int> prior_id, highest;
      bool increasing = false;
      for (int index = 1; index <= frame_clock::kMaxCapturesPerArm && !increasing; ++index) {
        clock_captures.push_back(frame_clock_capture("playing", index, plan->picture, playing_deadline, bound));
        const auto &capture = clock_captures.back();
        clock_status(capture, "a playing capture was late", "a playing capture lost its exact binding",
                     "a playing OS capture failed");
        const auto id = capture.reading.id;
        if (!id) { prior_id.reset(); continue; } // An ambiguous capture breaks the consecutive pair.
        if (*id > frame_clock::kPlayingMaxId) { clock_fail("playing baseline ran past its early-range frame guard"); }
        if (highest && *id < *highest) { clock_fail("playing picture IDs decreased during the baseline"); }
        increasing = prior_id && *id > *prior_id;
        prior_id = id; highest = id;
      }
      if (!increasing) { clock_fail("no two consecutive completed unambiguous playing captures with increasing IDs"); }
      last_playing_id = prior_id;
      evidence["stage"] = "pause";
      save();
    }
    std::shared_ptr<const test::VisiblePauseObservation> visible_pause;
    const auto requested = Clock::now();
    if (plan) {
      // Stated deviation from the matched fresh-visible control: playback runs longer before the pause.
      evidence["play_return_to_pause_request_seconds"] = media_seconds(plan->play_returned, requested);
    }
    // Both observation arms start their budget before the native actuator is dispatched.
    const auto deadline = requested + budget;
    const auto poll = [&](const auto &predicate) {
      return reports_native_test::poll_before<Clock>(deadline, predicate,
          [this](bool wait_for_event) { process(wait_for_event); }, [] {});
    };
    const auto same_target = [&] {
      if (!resources->active() || !close->reason.empty() || trace.overflow ||
          std::any_of(trace.events.begin(), trace.events.begin() + trace.event_count, [&](const auto &event) {
            return event.phase == "show" || event.phase == "superseded" || event.phase == "repeat-pause-suppressed" ||
                   (keep_visible && (!event.visible || event.webview_hidden));
          })) { return false; }
      if (keep_visible) {
        return area.active_tab() == 0 && visible_pause && !visible_pause->overflow &&
            visible_pause->media_generation == trace.media_generation &&
            test::visible_pause_target(parent, session, *visible_pause);
      }
      const auto pause = test::hidden_pause_target(parent, session, trace);
      return area.active_tab() == 1 && pause && pause->acknowledged && !pause->isolated_actuator;
    };
    const auto record = [&] {
      if (keep_visible) {
        record_native_pause_trace(close.get(), session, "visible_media_native_pause_trace");
        evidence["native_non_playing_verified"] = visible_pause && visible_pause->verified;
        evidence["close_reason"] = close->reason.empty() ? Json(nullptr) : Json(close->reason);
        evidence["close_elapsed_seconds"] = close->reason.empty() ? Json(nullptr) :
            Json(media_seconds(requested, close->when));
      }
      else {
        record_native_pause_trace(close.get(), session);
        record_hidden_native_close(close.get(), session, requested);
      }
      save();
    };
    try {
      const auto prior_dom = last_media_probe_;
      if (keep_visible) {
        // A toolbar mouse-down hides the native child. Use the same pause actuator without that hide.
        visible_pause = test::begin_visible_pause_control(parent, session, playing.navigation_generation);
        require(bool(visible_pause), "Could not pause the exact visible navigation");
      }
      else { tab(area, 1); }
      evidence["stage"] = keep_visible ? "first-visible-native-reply" : "first-hidden-native-reply";
      std::optional<test::NativeHidePauseEvent> first_reply;
      const auto received = poll([&] {
        const auto end = trace.events.begin() + trace.event_count;
        const auto start = keep_visible ? trace.events.begin() : std::find_if(trace.events.begin(), end, [](const auto &event) {
          return event.phase == "hide" && event.webview_hidden && !event.visible && !event.owns_focus;
        });
        const auto reply = std::find_if(start, end, [&](const auto &event) {
          return event.phase == "reply" && event.playback_state &&
              (keep_visible ? event.visible && !event.webview_hidden :
                              event.webview_hidden && !event.visible && !event.owns_focus);
        });
        if (reply != end) { first_reply = *reply; }
        return first_reply.has_value() || !resources->active();
      });
      require(received && first_reply && same_target() && trace.dispatched >= requested &&
          trace.events.front().phase == "dispatch" && trace.events.front().visible &&
          last_media_probe_ == prior_dom, "Fresh pause needs an exact native reply before any DOM probe");
      evidence[reply_key] = {
          {"raw_playback_state", *first_reply->playback_state}, {"seconds_from_dispatch", first_reply->elapsed_seconds}};
      const auto sample = [&] {
        const auto now = Clock::now();
        require(now < deadline && same_target(), "Fresh pause DOM probe needs the exact target within budget");
        const auto observed = media(session, std::chrono::duration<double>(deadline - now).count());
        const auto &probe = *last_media_probe_;
        require(probe.callback && *probe.callback < deadline && same_target() &&
            observed.navigation_generation == trace.navigation_generation,
            "Fresh pause DOM reply must match the exact target within budget");
        evidence["samples"].push_back({{"media", media_json(observed)},
            {"dispatch_seconds_from_pause", media_time(trace.dispatched, probe.dispatched)},
            {"reply_seconds_from_pause", media_time(trace.dispatched, probe.callback)},
            {"delta_from_playing_seconds", observed.current_time - playing.current_time},
            {"delta_from_last_seek_seconds", observed.current_time - last_seek.current_time},
            {"below_baseline_playback_floor", observed.current_time < playing.current_time - 0.05}});
        if (plan) {
          evidence["samples"].back()["dom_frame"] = frame_clock::dom_frame(observed.current_time);
          evidence["samples"].back()["dom_frame_below_last_playing_picture"] =
              frame_clock::dom_frame(observed.current_time) < *last_playing_id;
        }
        return observed;
      };
      evidence["stage"] = "first-dom-window";
      const auto first_sample = trace.dispatched + first_sample_offset;
      require(poll([&] { return !same_target() || Clock::now() >= first_sample; }) && same_target(),
          "First DOM sampling window did not fit the exact target's budget");
      evidence["stage"] = "first-dom";
      const auto before = sample();
      evidence["stage"] = "sample-interval";
      const auto next_sample = *last_media_probe_->callback + interval;
      require(next_sample < deadline &&
          poll([&] { return !same_target() || Clock::now() >= next_sample; }) && same_target(),
          "Fresh pause DOM interval did not fit the exact target's budget");
      evidence["stage"] = "second-dom";
      const auto after = sample();
      const double delta = after.current_time - before.current_time;
      const auto paused = [](const Media &media) {
        return media.paused && !media.ended && !media.seeking && media.ready_state >= 2;
      };
      evidence["dom_pause_observed_twice"] = paused(before) && paused(after);
      evidence["second_minus_first_seconds"] = delta;
      evidence["hold_time_within_0_10"] = std::abs(delta) <= 0.10;
      evidence["rollback_exceeds_hold_limit"] = delta < -0.10;
      evidence["stage"] = "observed";
      // Let the unchanged native watchdog finish after the DOM observations.
      const auto settle = trace.dispatched + budget + std::chrono::milliseconds(125);
      reports_native_test::poll_before<Clock>(settle, [&] {
        if (keep_visible) { return visible_pause->verified || !resources->active(); }
        const auto pause = test::hidden_pause_target(parent, session, trace);
        return (pause && pause->verified) || !resources->active();
      }, [this](bool wait_for_event) { process(wait_for_event); }, [] {});
      if (!keep_visible) {
        const auto final_pause = test::hidden_pause_target(parent, session, trace);
        evidence["native_pause_after_sampling"] = final_pause ? native_pause_json(*final_pause) : Json(nullptr);
      }
      evidence["session_active_after_sampling"] = resources->active();
      if (plan) {
        // After the unchanged DOM samples and native settle: no new pause, seek, play, DOM probe,
        // visibility or layout change. Only completed captures of the same verified target count.
        clock_pause_dispatched = trace.dispatched;
        evidence["stage"] = "paused-pictures";
        if (!visible_pause->verified) { clock_fail("native visible pause was not verified within its original deadline"); }
        const auto settled_dom = last_media_probe_;
        const auto paused_deadline = Clock::now() + frame_clock::kPausedBudget;
        const auto bound = [&] {
          return same_target() && visible_pause->verified && clock_layout_same() && last_media_probe_ == settled_dom;
        };
        std::optional<int> prior_id;
        for (int index = 1; index <= frame_clock::kMaxCapturesPerArm && !stable_paused_id; ++index) {
          clock_captures.push_back(frame_clock_capture("paused", index, plan->picture, paused_deadline, bound));
          const auto &capture = clock_captures.back();
          clock_status(capture, "a paused capture was late", "a paused capture lost the exact visible pause target",
                       "a paused OS capture failed");
          const auto id = capture.reading.id;
          if (!id) { prior_id.reset(); continue; }
          if (prior_id && *id == *prior_id) { stable_paused_id = id; }
          prior_id = id;
        }
        if (!stable_paused_id) { clock_fail("no two consecutive completed unambiguous paused captures with one ID"); }
        const auto verdict = frame_clock::classify(*last_playing_id, *stable_paused_id, playing.current_time,
            {{paused(before), before.current_time}, {paused(after), after.current_time}});
        evidence["stage"] = "classified";
        if (!clock_record(verdict.outcome, verdict.reason)) {
          throw std::runtime_error("Visible frame clock classification or its persisted OS evidence is inconclusive");
        }
      }
    }
    catch (...) {
      try { record(); } catch (...) {} // Keep the original observation failure.
      if (plan && !evidence.contains("outcome")) {
        clock_record("inconclusive", "the visible pause sequence failed before frame-clock classification");
      }
      throw;
    }
    record();
  }
  static Json native_hide_pause_event(const document_preview::test::NativeHidePauseEvent &event)
  {
    return {{"phase", event.phase}, {"elapsed_seconds", event.elapsed_seconds},
        {"visible", event.visible}, {"webview_hidden", event.webview_hidden}, {"owns_focus", event.owns_focus},
        {"raw_playback_state", event.playback_state ? Json(*event.playback_state) : Json(nullptr)}};
  }
  static Json native_hide_pause_trace(const document_preview::test::NativeHidePauseTrace &pause,
                                      const std::string &session)
  {
    Json events = Json::array();
    for (size_t i = 0; i < pause.event_count; ++i) { events.push_back(native_hide_pause_event(pause.events[i])); }
    return {{"session_sha256", core::Sha256::hex(session)}, {"media_generation", pause.media_generation},
        {"navigation_generation", pause.navigation_generation}, {"overflow", pause.overflow},
        {"events", std::move(events)}};
  }
  void record_native_pause_trace(const document_preview::test::NativeCloseObservation *close,
                                 const std::string &session,
                                 const char *key = "hidden_media_native_pause_trace") noexcept
  {
    try {
      if (close && close->hide_pause) {
        result_[key] = native_hide_pause_trace(*close->hide_pause, session);
      }
    }
    catch (...) {} // Diagnostics must never replace the original test exception.
  }
  void record_reshown_hold_native_observation(int cycle, const std::string &session,
      const document_preview::test::NativeCloseObservation *close, const std::optional<NativePause> &hidden_pause,
      Clock::time_point reveal_started, Clock::time_point hold_started, Clock::time_point exited,
      std::optional<Clock::time_point> failed_predicate, size_t samples, bool success) noexcept
  {
    try {
      // The observer is already attached. Reading its trace and the existing DOM receipt is passive.
      const auto *trace = close && close->hide_pause ? &*close->hide_pause : nullptr;
      const bool comparable = hidden_pause && trace;
      const bool matched = comparable && trace->media_generation == hidden_pause->media_generation &&
                           trace->navigation_generation == hidden_pause->navigation_generation;
      const auto dispatch = trace && trace->event_count ? std::optional(trace->dispatched) : std::nullopt;
      const auto last_event = [&](std::string_view phase) -> Json {
        if (!matched || !dispatch) { return nullptr; }
        for (size_t i = trace->event_count; i > 0; --i) {
          const auto &event = trace->events[i - 1];
          if (event.phase != phase) { continue; }
          auto raw = native_hide_pause_event(event);
          raw["seconds_from_reveal"] = media_seconds(reveal_started, *dispatch) + event.elapsed_seconds;
          return raw;
        }
        return nullptr;
      };
      Json probe = nullptr;
      if (last_media_probe_ && last_media_probe_->started >= hold_started) {
        const auto &r = *last_media_probe_;
        probe = {{"started_seconds", media_seconds(reveal_started, r.started)},
            {"dispatched_seconds", media_time(reveal_started, r.dispatched)},
            {"callback_seconds", media_time(reveal_started, r.callback)},
            {"finished_seconds", media_time(reveal_started, r.finished)},
            {"dispatch_accepted", r.accepted ? Json(*r.accepted) : Json(nullptr)},
            {"reply_ok", r.reply ? Json(r.reply->ok) : Json(nullptr)},
            {"media", r.reply && r.reply->ok ? media_json(r.reply->media) : Json(nullptr)}};
      }
      result_["reshown_hold_native_observation"] = {{"cycle", cycle}, {"phase", "reshown-no-autoresume"},
          {"session_sha256", core::Sha256::hex(session)}, {"clock_origin", "before-reveal-tab"},
          {"success", success}, {"completed_dom_samples", samples},
          {"hold_started_seconds", media_seconds(reveal_started, hold_started)},
          {"hold_exit_seconds", media_seconds(reveal_started, exited)},
          {"first_failed_predicate_seconds", media_time(reveal_started, failed_predicate)},
          {"last_dom_probe", std::move(probe)}, {"observer_attached", close != nullptr},
          {"hidden_pause", hidden_pause ? native_pause_json(*hidden_pause) : Json(nullptr)},
          {"matches_hidden_pause", comparable ? Json(matched) : Json(nullptr)},
          {"native_dispatch_seconds", media_time(reveal_started, dispatch)},
          {"show", last_event("show")}, {"release_ack", last_event("release-ack")},
          {"last_recorded_release_state", last_event("release-state")},
          {"native_trace", trace ? native_hide_pause_trace(*trace, session) : Json(nullptr)}};
    }
    catch (...) {} // Preserve the original hold result.
  }
  void record_hidden_native_close(const document_preview::test::NativeCloseObservation *close,
                                  const std::string &session, Clock::time_point playing_returned) noexcept
  {
    try {
      const bool recorded = close && !close->reason.empty();
      result_["hidden_media_native_close"] = {
          {"phase", "hidden-native-close"}, {"session_sha256", core::Sha256::hex(session)},
          {"observer_attached", close != nullptr},
          {"shutdown", recorded ? Json{{"reason", std::string(close->reason)},
              {"elapsed_seconds", media_seconds(playing_returned, close->when)},
              {"media_generation", close->media_generation},
              {"navigation_generation", close->navigation_generation},
              {"native_pause", native_pause_json(close->pause)}} : Json(nullptr)}};
    }
    catch (...) {} // Preserve the original test failure.
  }
  void record_failed_media_reveal(int cycle, const app::EditorArea &area, const std::string &session,
                                  const document_preview::ResourceSession &resources,
                                  const document_preview::test::NativeCloseObservation *close,
                                  Clock::time_point playing_returned, Clock::time_point reveal_started) noexcept
  {
    record_native_pause_trace(close, session, "failed_reveal_native_pause_trace");
    record_hidden_native_close(close, session, playing_returned);
    try {
      const auto *context = screen_.ui();
      const auto *viewport = widget("reports_document_viewport"), *focus = widget("reports_document_focus");
      const auto *main = area.find_region("main");
      const auto parent = window_.native_window_handle();
      const auto *trace = close && close->hide_pause ? &*close->hide_pause : nullptr;
      const auto bounds = [](ui::Rect rect) { return Json::array({rect.x, rect.y, rect.w, rect.h}); };
      Json overlays = {{"modal", false}, {"popup", false}, {"tooltip", false}, {"toast", false}};
      if (context) {
        for (const auto &block : context->blocks()) {
          switch (block->kind()) {
            case ui::Block::Kind::Modal: overlays["modal"] = true; break;
            case ui::Block::Kind::Popup: overlays["popup"] = true; break;
            case ui::Block::Kind::Tooltip: overlays["tooltip"] = true; break;
            case ui::Block::Kind::Toast: overlays["toast"] = true; break;
            case ui::Block::Kind::Region: break;
          }
        }
      }
      using namespace document_preview;
      std::string lookup_error;
      const bool same_resource = test::resource_session(parent, session, lookup_error).get() == &resources;
      const auto hidden_pause = trace ? test::hidden_pause_target(parent, session, *trace) : std::nullopt;
      result_["failed_reveal_observation"] = {
          {"phase", "quiet-html-video-reveal"}, {"cycle", cycle}, {"session_sha256", core::Sha256::hex(session)},
          {"elapsed_seconds", media_seconds(reveal_started, Clock::now())},
          {"active_tab", area.active_tab()}, {"client_size", {window_.width(), window_.height()}},
          {"main_rect", main ? bounds(screen_.to_ui(main->rect())) : Json(nullptr)},
          {"input", input_state()}, {"overlays", std::move(overlays)},
          {"viewport", viewport ? Json{{"native_widget", viewport->type == ui::WidgetType::NativeViewport},
              {"enabled", viewport->enabled}, {"fully_visible", visible(viewport)},
              {"rect", bounds(viewport->rect)}, {"clip", bounds(viewport->clip)}} : Json(nullptr)},
          {"focus_control_enabled", focus ? Json(focus->enabled) : Json(nullptr)},
          {"resources_active", resources.active()}, {"same_native_resource", same_resource},
          {"exact_visible_native_target", trace ? Json(test::visible_playback_target(parent, session, *trace, false)) : Json(nullptr)},
          {"exact_hidden_pause", hidden_pause ? native_pause_json(*hidden_pause) : Json(nullptr)}};
    }
    catch (...) {} // Keep the original reveal failure even if evidence collection fails.
  }
#endif
  void hidden_media_checkpoint(const char *stage) noexcept
  {
    if (!hidden_media_) return;
    auto &phase = *hidden_media_; phase.stage = stage;
    const auto now = Clock::now();
    if (std::string_view(stage) == "tab-begin") phase.tab_begin = now;
    else if (std::string_view(stage) == "tab-returned") phase.tab_returned = now;
    else if (std::string_view(stage) == "paused-begin") phase.paused_begin = now;
    else if (std::string_view(stage) == "paused-returned") phase.paused_returned = now;
  }
  void hidden_media_snapshot(const Media &hidden, const Media &playing) noexcept
  {
    if (!hidden_media_) return;
    auto &phase = *hidden_media_;
    phase.first_paused_native_pause = last_native_pause();
    phase.hidden_checks = std::array<bool, 3>{
        hidden.current_time < 2.9, hidden.current_time >= playing.current_time - 0.05, !hidden.ended};
    if (!std::all_of(phase.hidden_checks->begin(), phase.hidden_checks->end(), [](bool value) { return value; })) {
      phase.failed = hidden; phase.failure_kind = "hidden-predicate"; phase.failure_detected = Clock::now();
    }
  }
  void finish_hidden_media(bool success) noexcept
  {
    if (!hidden_media_) return;
    try {
      const auto &p = *hidden_media_;
      const auto now = Clock::now();
      const auto sample = [](const std::optional<Media> &value) {
        return value ? media_json(*value) : Json(nullptr);
      };
      Json probe = nullptr;
      if (last_media_probe_) {
        const auto &r = *last_media_probe_;
        const bool available = r.reply && r.reply->ok;
        probe = {{"dispatch_accepted", r.accepted ? Json(*r.accepted) : Json(nullptr)},
            {"callback_received", bool(r.reply)}, {"reply_ok", r.reply ? Json(r.reply->ok) : Json(nullptr)},
            {"snapshot_available", available},
            {"decoder_ok", available ? Json(r.reply->media.error_code == 0) : Json(nullptr)},
            {"native_pause_before", r.reply ? native_pause_json(r.reply->native_pause_before) : Json(nullptr)},
            {"native_pause_after", r.reply ? native_pause_json(r.reply->native_pause_after) : Json(nullptr)},
            {"started_seconds", media_seconds(p.started, r.started)},
            {"dispatched_seconds", media_time(p.started, r.dispatched)},
            {"callback_seconds", media_time(p.started, r.callback)},
            {"finished_seconds", media_time(p.started, r.finished)}};
      }
      Json observation = {{"cycle", p.cycle}, {"phase", "hidden-tab-pause"}, {"stage", p.stage},
          {"success", success}, {"session_sha256", p.session_sha256},
          {"requested_session_matches", p.requested_session_matches ? Json(*p.requested_session_matches) : Json(nullptr)},
          {"expected_navigation_generation", p.playing.navigation_generation},
          {"playing_before_hide", media_json(p.playing)}, {"before", media_json(p.before)},
          {"playing_native_pause", native_pause_pair_json(p.playing_native_pause)},
          {"first_paused_native_pause", native_pause_pair_json(p.first_paused_native_pause)},
          {"current", sample(p.current)}, {"failed", sample(p.failed)},
          {"last_valid", sample(p.last_valid)},
          {"last_valid_meaning", "previous successful probe; initialized from play-before-hide"},
          {"failure_kind", p.failure_kind ? Json(p.failure_kind) : Json(nullptr)},
          {"failure_detected_seconds", media_time(p.started, p.failure_detected)},
          {"sample_count", p.samples}, {"probe", std::move(probe)},
          {"elapsed_seconds", media_seconds(p.started, now)},
          {"hold_elapsed_seconds", p.hold_begin ? Json(media_seconds(*p.hold_begin, now)) : Json(nullptr)},
          {"checkpoints_seconds", {{"play_return", 0}, {"tab_begin", media_time(p.started, p.tab_begin)},
              {"tab_returned", media_time(p.started, p.tab_returned)},
              {"paused_begin", media_time(p.started, p.paused_begin)},
              {"paused_returned", media_time(p.started, p.paused_returned)},
              {"hold_begin", media_time(p.started, p.hold_begin)}}},
          {"hidden_checks", p.hidden_checks ? Json{{"upper_time_lt_2_9", (*p.hidden_checks)[0]},
              {"lower_time_ge_playing_minus_0_05", (*p.hidden_checks)[1]},
              {"not_ended", (*p.hidden_checks)[2]}} : Json(nullptr)},
          {"hold_checks", p.hold_checks ? Json{{"navigation_equal", (*p.hold_checks)[0]},
              {"paused", (*p.hold_checks)[1]}, {"not_ended", (*p.hold_checks)[2]},
              {"not_seeking", (*p.hold_checks)[3]}, {"abs_time_delta_le_0_10", (*p.hold_checks)[4]}} : Json(nullptr)}};
      // Copy now: a pending callback owns only its separate shared probe and cannot revise this evidence.
      result_["last_hidden_media_observation"] = observation;
      auto &cycles = result_["hidden_media_observations"];
      if (cycles.is_null()) cycles = Json::array();
      if (cycles.is_array() && cycles.size() < 20) cycles.push_back(std::move(observation));
    }
    catch (...) {} // Diagnostics must never replace the original test exception.
    hidden_media_.reset(); last_media_probe_.reset();
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
                   const Media &before, double seconds, bool record_failed_reshown_hold = false,
                   MediaHoldExit observe_exit = {})
  {
    const auto start = Clock::now();
    if (hidden_media_) {
      hidden_media_->stage = "hold"; hidden_media_->hold_begin = start; hidden_media_->before = before;
    }
    Media after;
    size_t samples = 0;
    std::optional<Clock::time_point> failed_predicate;
    const auto sample = [&] {
      after = media(session);
      ++samples;
      const auto delta = after.current_time - before.current_time;
      const std::array<bool, 5> checks{
          after.navigation_generation == before.navigation_generation, after.paused, !after.ended,
          !after.seeking, std::abs(delta) <= 0.10};
      const bool hold_ok = std::all_of(checks.begin(), checks.end(), [](bool value) { return value; });
      if (observe_exit && !hold_ok) { failed_predicate = Clock::now(); }
      if (hidden_media_) {
        auto &observation = *hidden_media_;
        observation.hold_checks = checks;
        if (!hold_ok) {
          observation.failed = after; observation.failure_kind = "hold-predicate";
          observation.failure_detected = Clock::now();
        }
      }
      if (record_failed_reshown_hold && !hold_ok) {
        try {
          const auto elapsed = media_seconds(start, Clock::now());
          result_["failed_reshown_hold"] = {{"cycle", cycle}, {"phase", phase},
              {"session_sha256", core::Sha256::hex(session)}, {"sample", samples}, {"elapsed_seconds", elapsed},
              {"before", media_json(before)}, {"failed", media_json(after)}, {"time_delta_seconds", delta},
              {"hold_checks", {{"navigation_equal", checks[0]}, {"paused", checks[1]},
                  {"not_ended", checks[2]}, {"not_seeking", checks[3]}, {"abs_time_delta_le_0_10", checks[4]}}},
              {"native_pause", native_pause_pair_json(last_native_pause())}};
        }
        catch (...) {} // Keep the original failed hold assertion.
      }
      require(hold_ok, "Paused media advanced, resumed, ended or changed navigation during " + phase);
      return std::chrono::duration<double>(Clock::now() - start).count() >= seconds;
    };
    try {
      wait(sample, "Paused media hold " + phase, seconds + 10);
    }
    catch (...) {
      if (observe_exit) { observe_exit(start, Clock::now(), failed_predicate, samples, false); }
      throw;
    }
    const auto exited = Clock::now();
    if (observe_exit) { observe_exit(start, exited, failed_predicate, samples, true); }
    result_["media_holds"].push_back({{"cycle", cycle}, {"phase", phase},
        {"observed_wall_seconds", media_seconds(start, exited)},
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
  void native_media_seek(int cycle, const std::string &phase, const std::string &session, ui::Rect bounds, const Media &before,
                         double fraction)
  {
    move_pointer({bounds.cx(), bounds.cy()});
    require(before.paused && before.duration_known && before.duration > 0 &&
        before.viewport_width > 0 && before.viewport_height > 0,
        "Native timeline lookup requires observed paused media geometry and duration");
    const auto viewport_generation = layout_epoch_.freeze();
    require(viewport_generation.has_value(), "Native seek requires this layout observer's ready state");
    const auto lookup_began = Clock::now();
    const reports_native_test::ax::Deadline seek_deadline(lookup_began + std::chrono::seconds(8));
    const reports_native_test::TimelineInput input{before.rect_x / before.viewport_width,
        before.rect_y / before.viewport_height, before.rect_width / before.viewport_width,
        before.rect_height / before.viewport_height, before.current_time, before.duration, fraction,
        before.navigation_generation, *viewport_generation, seek_deadline};
    const auto resources = media_session(session);
    const auto record_seek_surface = [&]() noexcept {
      try {
        const auto *view = widget("reports_document_viewport");
        const auto *context = screen_.ui();
        const auto rectangle = [](ui::Rect r) { return Json::array({r.x, r.y, r.w, r.h}); };
        Json overlays = Json::array();
        if (context) {
          for (const auto &block : context->blocks()) {
            if (block->kind() != ui::Block::Kind::Region) {
              overlays.push_back({{"kind", int(block->kind())}, {"frame", rectangle(block->frame())}});
            }
          }
        }
        result_["last_failed_timeline_seek"] = {{"cycle", cycle}, {"phase", phase},
            {"input", input_state()}, {"expected_viewport", rectangle(bounds)},
            {"actual_viewport", view ? rectangle(view->rect) : Json(nullptr)},
            {"viewport_clip", view ? rectangle(view->clip) : Json(nullptr)},
            {"viewport_enabled", view && view->enabled}, {"viewport_fully_visible", visible(view)},
            {"layout_current", layout_epoch_.matches(input.viewport_generation)},
            {"session_active", resources->active()}, {"overlays", std::move(overlays)}};
      }
      catch (...) {} // Optional evidence cannot replace the original seek failure.
    };
    // A first accessibility read may enable WebKit's tree asynchronously. Repeat
    // only an empty completed read, never a partially delivered input or a limit
    // failure. All successful input still has to pass unchanged DOM/OS gates.
    bool provider_all_empty = true;
    auto finish = [&](reports_native_test::TimelineObservation &observed, std::string &delivery, std::string &error) {
      for (;;) {
        require(seek_deadline.permits(Clock::now()), "Bounded asynchronous AX seek expired before result consumption");
        const auto state = native_input_.poll_seek(observed, delivery, error);
        require(seek_deadline.permits(Clock::now()), "AX poll crossed the original seek deadline");
        if (state != reports_native_test::TimelinePoll::Pending) return state == reports_native_test::TimelinePoll::Delivered;
        require(seek_deadline.permits(Clock::now()), "Bounded asynchronous AX seek expired");
        process(); // Keep the real UI/OS queue running; no read/wait/join on this thread.
      }
    };
    try {
      for (int attempt = 0; attempt < 4; ++attempt) {
        require(seek_deadline.permits(Clock::now()), "Bounded provider AX seek expired");
        require(layout_epoch_.matches(input.viewport_generation), "AX provider lookup belongs to an invalidated layout");
        reports_native_test::TimelineObservation observed;
        std::string delivery, error;
        const bool candidate = native_input_.begin_provider_seek(window_.native_window_handle(), native_bounds(bounds),
            window_.width(), window_.height(), input, resources, observed, error);
        require(seek_deadline.permits(Clock::now()), "Provider AX query crossed the original seek deadline");
        const bool sent = candidate && finish(observed, delivery, error);
        if (!sent && (candidate || !observed.lookup_complete || observed.candidates != 0)) {
          record_seek_surface();
        }
        provider_all_empty = provider_all_empty && observed.sliders == 0;
        auto list_json = [](const reports_native_test::TimelineChildListObservation &value) {
          return Json{{"type", value.type}, {"count", value.count}, {"over_budget", value.over_budget}};
        };
        Json nodes = Json::array();
        for (const auto &node : observed.nodes) {
          nodes.push_back({{"ordinal", node.ordinal}, {"depth", node.depth}, {"elapsed_ms", node.elapsed_ms},
              {"category", node.category}, {"selected_role", node.selected_role},
              {"legacy_role", node.legacy_role}, {"modern_role", node.modern_role},
              {"legacy_selector", node.legacy_selector}, {"modern_children_selector", node.modern_children_selector},
              {"modern_role_selector", node.modern_role_selector}, {"paged_count_selector", node.paged_count_selector},
              {"paged_values_selector", node.paged_values_selector}, {"paged_count_observed", node.paged_count_observed},
              {"paged_count", node.paged_count}, {"paged_count_over_budget", node.paged_count_over_budget},
              {"selected_children", list_json(node.selected_children)}, {"legacy_children", list_json(node.legacy_children)},
              {"modern_children", list_json(node.modern_children)}, {"diagnostic_exception", node.diagnostic_exception},
              {"extra_getters_started", node.extra_getters_started}, {"extra_getters_complete", node.extra_getters_complete}});
        }
        result_["native_media_inputs"].push_back({{"cycle", cycle}, {"phase", phase},
            {"lookup_elapsed_ms", observed.elapsed_ms}, {"diagnostic_elapsed_ms", observed.diagnostic_elapsed_ms},
            {"diagnostics_timeout", observed.diagnostics_timeout}, {"attempts_elapsed_ms",
                std::chrono::duration<double, std::milli>(Clock::now() - lookup_began).count()},
            {"frame_number", window_.frames_drawn()}, {"ax_nodes", std::move(nodes)},
            {"ax_nodes_truncated", observed.diagnostics_truncated},
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
        require(!candidate && observed.lookup_complete && observed.candidates == 0, error);
        if (attempt == 3) break;
        // A frame can complete in milliseconds while WebContent still initializes
        // its remote AX tree. Give each empty read a real scheduling interval,
        // pumping this window's UI throughout; keep the same four lookup attempts.
        const auto retry_after = Clock::now() + std::chrono::milliseconds(250);
        do { frame(); } while (Clock::now() < retry_after);
      }
      // Only four completed empty provider reads can reach the single public-client attempt.
      reports_native_test::TimelineObservation observed;
      std::string delivery, error;
      require(provider_all_empty, "A nonempty provider AX tree cannot authorize a client fallback");
      require(seek_deadline.permits(Clock::now()), "Bounded AX seek expired before public client start");
      require(layout_epoch_.matches(input.viewport_generation), "Public AX fallback belongs to an invalidated layout");
      const bool client_started = native_input_.begin_client_seek(window_.native_window_handle(), native_bounds(bounds),
          window_.width(), window_.height(), input, resources, error);
      if (!client_started) { record_seek_surface(); }
      require(client_started, error);
      const bool sent = finish(observed, delivery, error);
      const auto &child = observed.public_client; const auto &reply = child.response;
      const auto api = [&](auto value) -> Json { return child.response_available ? Json(value) : Json(nullptr); };
      result_["native_media_inputs"].push_back({{"cycle", cycle}, {"phase", phase}, {"action", "public-client-timeline-click"},
          {"delivered", sent}, {"delivery", delivery}, {"error", error}, {"before", media_json(before)},
          {"client_status", reports_native_test::ax::name(child.status)}, {"client_pid", child.child_pid},
          {"client_reaped", child.reaped}, {"client_killed", child.killed}, {"client_ownership_lost", child.ownership_lost},
          {"client_exit_code", child.exit_code}, {"client_signal", child.signal}, {"client_system_error", child.system_error},
          {"client_stderr_bytes", child.stderr_bytes}, {"client_elapsed_ms", child.elapsed_ms},
          {"api_response_available", child.response_available}, {"progress_available", child.progress_available},
          {"progress_incomplete", child.progress_incomplete}, {"progress_invalid", child.progress_invalid},
          {"progress_dropped", child.progress_dropped}, {"progress_bytes", child.progress_bytes},
          {"progress_records", child.progress_records}, {"request_bytes_sent", child.request_bytes_sent},
          {"response_bytes_received", child.response_bytes_received},
          {"last_progress", ax_progress_json(child.last_progress)},
          {"last_started_api", ax_progress_json(child.last_api_enter)},
          {"last_returned_api", ax_progress_json(child.last_api_return)},
          {"topology_witness", child.response_available ? ax_witness_json(reply) : Json(nullptr)},
          {"api_status", api(reports_native_test::ax::name(reply.status))}, {"api_reason", api(reports_native_test::ax::name(reply.reason))},
          {"api_phase", api(reports_native_test::ax::name(reply.phase))}, {"api_operation", api(reports_native_test::ax::name(reply.operation))},
          {"api_attribute", api(reports_native_test::ax::name(reply.attribute))}, {"api_error", api(reply.api_error)},
          {"trusted", api(reply.trusted)}, {"nodes", api(reply.nodes)}, {"deepest", api(reply.deepest)}, {"sliders", api(reply.sliders)},
          {"windows", api(reply.windows)}, {"window_matches", api(reply.window_matches)}, {"viewport_matches", api(reply.viewport_matches)},
          {"viewport_chains", api(reply.viewport_chains)}, {"viewport_chain_length", api(reply.viewport_chain_length)},
          {"webareas", api(reply.webareas)}, {"time_matched_candidates", api(reply.candidates)},
          {"native_session_revalidated", observed.public_client_revalidated},
          {"slider_screen_points_bottom_left", {observed.screen_x, observed.screen_y, observed.screen_width, observed.screen_height}},
          {"slider_range_value", {observed.minimum, observed.maximum, observed.value}}, {"target_fraction", fraction},
          {"viewport_normalized_top_left", {observed.normalized_x, observed.normalized_y}}});
      if (!sent) { record_seek_surface(); }
      save(); require(sent, error); process();
    }
    catch (...) {
      const bool drained = drain_native_seek();
      result_["native_ax_cleanup_complete"] = drained;
      throw;
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
      struct DragEvents {
        Json events = Json::array();
        std::string phase = "before_down";
        size_t omitted = 0;
      };
      const auto native_events = std::make_shared<DragEvents>();
      // Observe only this window's normal event route. Keep every original
      // handler/event/frame: these diagnostics do not filter or synthesize input.
      const auto window_alive = std::make_shared<bool>(true);
      window_.add_close_listener([weak = std::weak_ptr<bool>(window_alive)](wm::Window &) {
        if (const auto alive = weak.lock()) { *alive = false; }
      });
      struct RestoreEventHandler {
        wm::Window &window;
        std::function<bool(const wm::Event &)> previous;
        std::shared_ptr<bool> alive;
        ~RestoreEventHandler() { if (*alive) { window.on_event = std::move(previous); } }
      } restore{window_, window_.on_event, window_alive};
      window_.on_event = [&, previous = restore.previous, native_events](const wm::Event &e) {
        const char *kind = e.type == wm::EventType::MouseMove ? "mouse_move" :
            e.type == wm::EventType::MouseDown ? "mouse_down" :
            e.type == wm::EventType::MouseUp ? "mouse_up" :
            e.type == wm::EventType::FocusIn ? "focus_in" :
            e.type == wm::EventType::FocusOut ? "focus_out" :
            e.type == wm::EventType::Resize ? "resize" : nullptr;
        if (kind) {
          if (native_events->events.size() < 32) {
            native_events->events.push_back({{"event", kind}, {"phase", native_events->phase},
                {"position_bottom_left", {e.x, e.y}}, {"time_ms", e.time_ms},
                {"frames_drawn", window_.frames_drawn()}, {"screen_capture_before_routing", int(screen_.capture())},
                {"report_width_before_routing", area.rect().width()},
                {"viewer_width_before_routing", viewer_area.rect().width()}});
          }
          else { ++native_events->omitted; }
        }
        return previous ? previous(e) : false;
      };
      result_["decoded_media_layout_drags"].push_back({{"before", media_json(observed)},
          {"shrink_framebuffer_pixels", shrink}, {"requested_viewport_css_width", target_width},
          {"report_child_index", report_left ? 0 : 1}, {"divider_delta_framebuffer_pixels", delta},
          {"requested_drag_from_bottom_left", {from_x, y}},
          {"requested_drag_to_bottom_left", {from_x + delta, y}},
          {"report_min_width", area.min_width(window_.ui_scale())},
          {"viewer_min_width", viewer_area.min_width(window_.ui_scale())},
          {"report_width_before", before.width()}, {"viewer_width_before", viewer_before.width()},
          {"before_down", input_state()}});
      const auto record = [&](const char *phase) {
        auto &item = result_["decoded_media_layout_drags"].back();
        auto state = input_state();
        state["report_width"] = area.rect().width();
        state["viewer_width"] = viewer_area.rect().width();
        item[phase] = std::move(state);
        item["native_events"] = native_events->events;
        item["native_events_omitted"] = native_events->omitted;
        item["report_width_after"] = area.rect().width();
        item["viewer_width_after"] = viewer_area.rect().width(); save();
        native_events->phase = phase;
      };
      wm::Event e; e.x = from_x; e.y = y; e.type = wm::EventType::MouseMove; event(e);
      e.type = wm::EventType::MouseDown; e.button = wm::MouseButton::Left; event(e);
      record("after_down"); frame(); record("after_down_frame");
      require(screen_.capture() == wm::Screen::Capture::Splitter, "Mouse must capture report/Viewer divider");
      // Finish this locally dispatched gesture before pumping the OS queue.
      // Windows can enqueue a hover move at the physical pointer position when
      // hiding the child; while capture is held it would become another drag.
      // Leave that original event queued for normal routing after MouseUp.
      e.type = wm::EventType::MouseMove; e.x += delta; event(e); record("after_move");
      e.type = wm::EventType::MouseUp; event(e); record("after_up"); frame(); record("after_up_frame");
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
      if (!pending) {
        ++os_capture_requests_;
        pending = document_preview::capture_window_evidence(window_.native_window_handle());
        return false;
      }
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
  // One own-window OS capture for the frame-clock diagnostic. Unlike media_capture it neither
  // requires a paused DOM state nor reads the DOM. It only pumps the UI loop, never later than
  // the arm's absolute deadline; the in-flight capture is cancelled on return. Decoding is in
  // memory; PNG encoding is deferred so it cannot delay the timed native/DOM observations.
  frame_clock::Capture frame_clock_capture(const char *arm, int index, ui::Rect picture,
                                           Clock::time_point deadline, const std::function<bool()> &bound)
  {
    frame_clock::Capture out;
    out.arm = arm; out.index = index;
    out.requested = Clock::now();
    if (out.requested >= deadline) { out.completed = out.requested; out.status = "late"; return out; }
    if (!bound()) { out.completed = out.requested; out.status = "unbound"; return out; }
    ++os_capture_requests_;
    auto pending = document_preview::capture_window_evidence(window_.native_window_handle());
    std::optional<document_preview::WindowEvidence> image;
    const bool delivered = reports_native_test::poll_before<Clock>(deadline, [&] {
      if (!image) { image = pending->poll(); }
      return image.has_value();
    }, [this](bool wait_for_event) { process(wait_for_event); }, [] {});
    out.completed = Clock::now();
    pending.reset();
    if (!delivered) { out.status = "late"; return out; }
    out.backend = image->backend;
    if (!image->error.empty()) { out.status = "capture_error"; out.error = image->error; return out; }
    const auto &pixels = image->image;
    if (pixels.channels != 4 || pixels.width != uint32_t(window_.width()) || pixels.height != uint32_t(window_.height())) {
      out.status = "capture_error"; out.error = "OS capture does not match this STK client framebuffer"; return out;
    }
    if (!bound()) { out.status = "unbound"; return out; }
    out.reading = frame_clock::read(pixels, picture);
    const int x = std::max(0, int(std::floor(picture.x))), y = std::max(0, int(std::floor(picture.y)));
    const int right = std::min(int(pixels.width), int(std::ceil(picture.x + picture.w)));
    const int bottom = std::min(int(pixels.height), int(std::ceil(picture.y + picture.h)));
    if (right > x && bottom > y) {
      out.crop = io::Image(uint32_t(right - x), uint32_t(bottom - y));
      for (int row = y; row < bottom; ++row) {
        std::copy_n(pixels.pixel(uint32_t(x), uint32_t(row)), size_t(right - x) * 4, out.crop.row(uint32_t(row - y)));
      }
      out.crop_top_left = {x, y, right - x, bottom - y};
    }
    out.status = "completed";
    return out;
  }
  void frame_clock_write(std::vector<frame_clock::Capture> &captures) noexcept
  {
    try {
      // Separate from the required screenshots and result["images"]; picture-region crops only.
      const auto folder = directory_ / "frame-clock";
      fs::create_directories(folder);
      for (auto &capture : captures) {
        if (!capture.crop.width || !capture.file.empty()) { continue; }
        const auto name = "frame-clock-" + capture.arm + "-" + std::to_string(capture.index) + ".png";
        const auto png = io::encode_png(capture.crop);
        write(folder / name, std::string(png.begin(), png.end()));
        std::ifstream saved(folder / name, std::ios::binary);
        const std::string bytes{std::istreambuf_iterator<char>(saved), {}};
        require(!saved.bad() && bytes.size() == png.size() && core::Sha256::hex(bytes) == core::Sha256::hex(png),
                "Frame-clock OS evidence was not persisted completely");
        capture.file = "frame-clock/" + name; capture.sha256 = core::Sha256::hex(png);
      }
    }
    catch (...) {} // Optional crops never replace the measured outcome or the original failure.
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
  // Every own-window OS capture request; the delay control proves it unchanged.
  size_t os_capture_requests_ = 0;
  std::unique_ptr<document_preview::WindowEvidenceCaptureSource> capture_source_;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  std::shared_ptr<MediaProbeObservation> last_media_probe_;
  size_t dom_probe_requests_ = 0; // Every media() DOM probe request.
  std::optional<HiddenMediaObservation> hidden_media_;
#endif
  reports_native_test::ScrollGuard scroll_guard_;
#if defined(__APPLE__) && defined(STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES)
  reports_native_test::ax::LayoutEpoch layout_epoch_;
  wm::Screen::LayoutObserver layout_observer_;
#endif
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
#ifdef _WIN32
  // Isolate the lease to the Windows PDF gate, which has exhibited repeated target startup stalls.
  if (options.source == "pdf") { ui.lease_capture_item(); }
#endif
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
    Exercise &ui;
    Json &result;
    ~Cleanup() {
      const bool drained = ui.drain_native_seek();
      result["native_ax_cleanup_complete"] = drained;
      if (!drained) std::fputs("FAIL: native AX owned-child cleanup was not confirmed\n", stderr);
      timer.reset();
      shell.store().project().attach(nullptr); shell.store().set_bridge(nullptr); client.close();
      shell.store().viewer().close();
      ui.release_capture_source(); // Release the item and its apartment on this UI thread before HWND destruction.
      manager.close_window(window);
    }
  } cleanup{shell, *client, *manager, window, redraw_timer, ui, result};
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
  const bool marked_clip = options.frame_clock_control || options.first_toolbar_frames != Options::FirstToolbarFrames::None;
  const size_t media_size = marked_clip ? kFrameClockMediaSize : kMediaSize;
  const std::string media_sha256 = marked_clip ? kFrameClockMediaSha256 : kMediaSha256;
  if (video) {
    std::ifstream file(options.media_fixture, std::ios::binary);
    require(file.good(), "Pinned public MP4 fixture is required");
    media_bytes.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
    require(media_bytes.size() == media_size && core::Sha256::hex(media_bytes) == media_sha256,
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
  if (!options.visible_pause_control && !options.first_toolbar_pause_control && !options.suspend_reveal_control) {
    result["body_text_pixel_criterion"] = pdf ? "not applied: PDF page identities use independent page-embedded RGB stripes" :
        "Three aligned 20-column U+2588/space rows, independently required beside the frozen PNG";
  }
  const int cycles = options.reading_cycles();
  const size_t required_images = (options.visible_pause_control || options.first_toolbar_pause_control ||
      options.suspend_reveal_control) ? 0 :
      options.fresh_pause_diagnostic() ? 4 : options.pause_order_diagnostic() ? 1 :
      (video ? (options.pre_seek_hide_control ? 6 : 161) : (pdf ? 160 : 140));
  result["required_images"] = required_images;
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
    result["media_fixture"] = {{"size", media_bytes.size()}, {"sha256", media_sha256},
        {"container", "MP4"}, {"video_codec", "H264 Baseline"}, {"audio_codec", "AAC"},
        {"duration_seconds", 6}, {"live_source_deleted_before_prepare", true}};
    if (!options.visible_pause_control && !options.suspend_reveal_control) {
      result["body_text_pixel_criterion"] = "Pinned MP4 decoded red/blue picture region in independent OS client captures; HTML contains no poster/image/script";
    }
    result["not_proven_here"] = options.suspend_reveal_control ?
        "This observation samples native playback state and the DOM clock on one pinned MP4. It has no decoded-frame or audio evidence." :
        "Physical hardware input, audio output, arbitrary codec support, IME, physical scanout and browser memory stability; final guarded memory remains the separate after-static spike gate";
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
      ui.native_media_seek(cycle, phase, session, bounds, original, late ? 0.80 : 0.07);
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
    for (int cycle = 1; cycle <= cycles; ++cycle) {
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
      require(complete.status == 200 && complete.mime == "video/mp4" && complete.content_length == media_size &&
          core::Sha256::hex(complete.bytes) == media_sha256 && !resources->allows_navigation(old_url),
          "Actual native session must contain the exact verified MP4 and deny its top-level navigation");
      const auto slice = resources->read(old_url, "GET", "bytes=0-31");
      require(slice.status == 206 && slice.content_length == 32 &&
          slice.content_range == "bytes 0-31/" + std::to_string(media_size) &&
          slice.bytes == std::vector<uint8_t>(complete.bytes.begin(), complete.bytes.begin() + 32),
          "Actual native session single Range must retain the verified full MP4 identity");
      auto initial = ui.media(session);
      require(initial.paused && !initial.ended && initial.current_time <= 0.10,
          "Initial or explicitly reprepared video must never autoplay");
      ui.held_media(cycle, "initial-no-autoplay", session, initial, 0.50);
      auto bounds = ui.widget("reports_document_viewport")->rect;
#ifdef __APPLE__
      if (options.suspend_reveal_control) {
        ui.suspend_reveal_diagnostic(*area, session, initial.navigation_generation, resources, [&](const char *phase) {
          const auto *viewport = ui.widget("reports_document_viewport");
          require(ui.visible(viewport), "Explicit Play needs the visible report viewport");
          return play(cycle, phase, session, viewport->rect);
        });
        require(area->tab(1).save_workspace_state() == draft_state && area->tab(1).has_unsaved_changes() &&
            shell.store().scripts().history().empty(), "Suspension observation preserves the unexecuted Python draft");
        require(viewer.save_workspace_state() == viewer_state && viewer.camera_serial() == camera &&
            viewer.payload_serial() == payload && viewer.evaluations_started() == 0 &&
            viewer_area->editor().save_workspace_state() == viewer_editor_state, "Suspension observation preserves the Viewer");
        result["viewer_preserved"] = true;
        result["python_draft_preserved"] = true;
        result["completed_cycles"] = cycle;
        ui.save();
        return;
      }
      if (options.visible_pause_control) {
        const auto playing = play(cycle, "visible-pause-control-play", session, bounds);
        ui.visible_pause_diagnostic(session, playing, resources);
        result["completed_cycles"] = cycle;
        ui.save();
        return; // This diagnostic has its own success marker and evidence contract.
      }
#endif
      try {
        result["last_explicit_pause_observation"] = {{"cycle", cycle}, {"phase", "explicit-pause"},
            {"playing", nullptr}, {"paused", nullptr}};
      }
      catch (...) {}
      const auto explicitly_playing = play(cycle, "explicit-play", session, bounds);
      const auto explicit_play_returned = Clock::now();
#ifdef __APPLE__
      if (options.first_toolbar_pause_control) {
        ui.first_toolbar_pause(*area, session, explicitly_playing, explicit_play_returned, resources,
                               options.first_toolbar_immediate, options.first_toolbar_frames);
        require(area->tab(1).save_workspace_state() == draft_state && area->tab(1).has_unsaved_changes() &&
            shell.store().scripts().history().empty(), "Toolbar pause control preserves the unexecuted Python draft");
        require(viewer.save_workspace_state() == viewer_state && viewer.camera_serial() == camera &&
            viewer.payload_serial() == payload && viewer.evaluations_started() == 0 &&
            viewer_area->editor().save_workspace_state() == viewer_editor_state, "Toolbar pause control preserves the Viewer");
        result["actual_mouse_clicks"] = ui.clicks;
        result["wheel_steps"] = ui.wheels;
        result["viewer_preserved"] = true;
        result["python_draft_preserved"] = true;
        result["completed_cycles"] = cycle;
        ui.save();
        return;
      }
#endif
      const auto explicit_play_native_pause = ui.last_native_pause();
      ui.click("reports_document_pause", *area);
      const auto explicit_click_returned = Clock::now();
      auto red = paused(session, "Explicit Pause button");
      const auto explicit_paused_returned = Clock::now();
      try {
        result["last_explicit_pause_observation"] = {{"cycle", cycle}, {"phase", "explicit-pause"},
            {"session_sha256", core::Sha256::hex(session)}, {"playing", media_json(explicitly_playing)},
            {"paused", media_json(red)},
            {"playing_native_pause", native_pause_pair_json(explicit_play_native_pause)},
            {"first_paused_native_pause", native_pause_pair_json(ui.last_native_pause())},
            {"first_paused_dom_probe", ui.last_media_probe_evidence(explicit_play_returned)},
            {"click_return_seconds", media_seconds(explicit_play_returned, explicit_click_returned)},
            {"paused_return_seconds", media_seconds(explicit_play_returned, explicit_paused_returned)},
            {"checks", {{"lower_time_gt_0_05", red.current_time > 0.05},
                {"upper_time_lt_2_6", red.current_time < 2.6}, {"not_ended", !red.ended}}}};
      }
      catch (...) {} // Preserve the original assertion even if optional evidence cannot be copied.
      require(red.current_time > 0.05 && red.current_time < 2.6 && !red.ended,
          "Explicit pause must stop actual playback before the blue/ended segment");
      const auto record_explicit_hold = [&](bool success) noexcept {
        try {
          auto &observation = result.at("last_explicit_pause_observation");
          observation["hold_success"] = success;
          observation["hold_last_dom_probe"] = ui.last_media_probe_evidence(explicit_play_returned);
          observation["hold_last_native_pause"] = native_pause_pair_json(ui.last_native_pause());
        }
        catch (...) {}
      };
      try {
        ui.held_media(cycle, "explicit-pause", session, red, 0.25);
        record_explicit_hold(true);
      }
      catch (...) { record_explicit_hold(false); throw; }
      red = ui.fit_decoded_media(*area, *viewer_area, session, red);
      bounds = ui.widget("reports_document_viewport")->rect;
      auto rectangle = ui.media_rectangle(bounds, red);
      ui.media_capture(cycle, "played-red-paused", 1, rectangle, red, session);
#ifdef __APPLE__
      std::optional<Media> last_seek;
#endif
      if (!options.pre_seek_hide_control && !options.pause_order_diagnostic()) {
        // Observe a natural red-to-blue transition after explicit Play, before any seek.
        // Pausing after >3.3s leaves time for an OS capture before the clip ends.
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
#ifdef __APPLE__
        if (options.fresh_pause_diagnostic()) { last_seek = early; }
#endif
      }
      const auto playing = play(cycle, "play-before-hide", session, bounds);
      const auto playing_returned = Clock::now();
      require(!playing.paused && playing.current_time < 2.5, "Hide must interrupt a playing early clip");
      const auto before_hide_pause = ui.last_native_pause();
#ifdef __APPLE__
      if (options.fresh_pause_diagnostic()) {
        require(last_seek && before_hide_pause && last_seek->navigation_generation == playing.navigation_generation &&
            result.at("images").size() == required_images, "Fresh pause needs the full baseline seek history");
        std::optional<frame_clock::Plan> clock_plan;
        if (options.frame_clock_control) {
          // Geometry of the play() snapshot; the frame-clock arms add no DOM read of their own.
          clock_plan = frame_clock::Plan{ui.media_rectangle(bounds, playing), bounds, playing_returned,
                                         report.at("source_sha256").get<std::string>()};
        }
        ui.fresh_native_pause_dom_diagnostic(*area, session, playing, *last_seek, (*before_hide_pause)[1], resources,
                                             options.fresh_pause == Options::FreshPause::Visible,
                                             clock_plan ? &*clock_plan : nullptr);
        require(area->tab(1).save_workspace_state() == draft_state && area->tab(1).has_unsaved_changes() &&
            shell.store().scripts().history().empty(), "Fresh pause preserves the unexecuted Python draft");
        require(viewer.save_workspace_state() == viewer_state && viewer.camera_serial() == camera &&
            viewer.payload_serial() == payload && viewer.evaluations_started() == 0 &&
            viewer_area->editor().save_workspace_state() == viewer_editor_state, "Fresh pause preserves the Viewer");
        result["actual_mouse_clicks"] = ui.clicks;
        result["wheel_steps"] = ui.wheels;
        result["viewer_preserved"] = true;
        result["python_draft_preserved"] = true;
        result["completed_cycles"] = cycle;
        ui.save();
        return;
      }
      if (options.second_visible_pause_control || options.hide_after_verified_pause_control ||
          options.repeat_verified_visible_pause_control) {
        // Share the quiet pre-seek hide history and change only the second pause ordering.
        require(before_hide_pause.has_value(), "Matched control needs the first native pause observation");
        const auto &previous = (*before_hide_pause)[1];
        require(previous.available && previous.acknowledged && previous.verified && !previous.isolated_actuator &&
            previous.navigation_generation == playing.navigation_generation,
            "Matched control needs a verified first native pause on the resumed navigation");
        if (options.hide_after_verified_pause_control) {
          ui.hide_after_verified_pause_diagnostic(*area, session, playing, previous, resources,
                                                  options.retain_visible_pause_control, options.hidden_dom_tail_control);
          require(area->tab(1).save_workspace_state() == draft_state, "Diagnostic tab hide preserves the Python draft");
        }
        else if (options.repeat_verified_visible_pause_control) {
          require(result.at("images").size() == required_images, "Visible repeat needs the matched pre-seek evidence");
          ui.repeat_verified_visible_pause_diagnostic(*area, session, playing, previous, resources);
          require(area->tab(1).save_workspace_state() == draft_state, "Visible repeat preserves the Python draft");
          require(viewer.save_workspace_state() == viewer_state && viewer.camera_serial() == camera &&
              viewer.payload_serial() == payload && viewer.evaluations_started() == 0 &&
              viewer_area->editor().save_workspace_state() == viewer_editor_state, "Visible repeat preserves the Viewer");
          result["actual_mouse_clicks"] = ui.clicks;
          result["wheel_steps"] = ui.wheels;
          result["viewer_preserved"] = true;
          result["python_draft_preserved"] = true;
        }
        else {
          ui.visible_pause_diagnostic(session, playing, resources, &previous);
        }
        result["completed_cycles"] = cycle;
        ui.save();
        return;
      }
#endif
      ui.begin_hidden_media(cycle, session, playing, playing_returned);
#ifdef __APPLE__
      const auto close = ui.observe_native_close(session, playing.navigation_generation);
      std::optional<NativePause> quiet_hidden_pause;
#endif
      auto hidden = [&] {
        try {
#ifdef __APPLE__
          if (options.quiet_hidden_hold) {
            require(bool(close), "Quiet hidden hold needs the exact native close observer");
          }
          if (options.isolated_pause_control) {
            require(ui.arm_isolated_pause(session, playing.navigation_generation),
                "Could not arm the isolated pause on the playing report navigation");
          }
#endif
          ui.hidden_media_checkpoint("tab-begin");
          ui.tab(*area, 1);
          ui.hidden_media_checkpoint("tab-returned");
          if (options.quiet_hidden_hold) {
            // Pump only the window event loop until the original native verification can finish.
            const auto started = Clock::now();
            constexpr auto hold = document_preview::detail::MediaPauseVerification::timeout +
                                  std::chrono::milliseconds(250);
            ui.hidden_media_checkpoint("quiet-native-hold");
#ifdef __APPLE__
            const auto *trace = close && close->hide_pause ? &*close->hide_pause : nullptr;
            bool extra_pause_dispatched = false;
#endif
            ui.wait([&] {
              const bool finished = !resources->active() || Clock::now() - started >= hold;
#ifdef __APPLE__
              if (!finished && options.pause_during_hidden_suspension && !extra_pause_dispatched && trace) {
                extra_pause_dispatched = ui.pause_suspended_hidden_playback(session, *trace);
              }
#endif
              return finished;
            }, "Hidden hold without DOM observation", 3);
            result["quiet_hidden_observation"] = {{"session_sha256", core::Sha256::hex(session)},
                {"elapsed_seconds", media_seconds(started, Clock::now())},
                {"session_active_before_dom_probe", resources->active()}};
            require(resources->active(), "Native media session closed during the hold without DOM observation");
#ifdef __APPLE__
            if (options.pause_during_hidden_suspension) {
              require(extra_pause_dispatched && trace && !trace->overflow &&
                  std::any_of(trace->events.begin(), trace->events.begin() + trace->event_count, [](const auto &event) {
                    return event.phase == "pause-during-suspension-ack" && event.webview_hidden && !event.visible;
                  }), "The extra pause needs its exact acknowledgement before the original quiet hold ends");
            }
#endif
          }
          ui.hidden_media_checkpoint("paused-begin");
          auto hidden = options.quiet_hidden_hold ? ui.media(session) :
              paused(session, "Hide must pause the actual native media");
          ui.hidden_media_checkpoint("paused-returned");
          ui.hidden_media_snapshot(hidden, playing);
          if (options.quiet_hidden_hold) {
            const auto after_hold = ui.last_native_pause();
            require(before_hide_pause && after_hold, "Quiet hidden hold needs both native pause observations");
            const auto &previous = (*before_hide_pause)[1];
            const auto &pause = (*after_hold)[0]; // Sampled before the post-hold DOM evaluation.
            result["quiet_hidden_observation"]["native_pause_before_dom_probe"] = native_pause_json(pause);
            require(previous.available && pause.available &&
                previous.navigation_generation == playing.navigation_generation &&
                pause.navigation_generation == playing.navigation_generation &&
                pause.media_generation == previous.media_generation + 1 && pause.visible_at_dispatch &&
                pause.acknowledged && pause.verified &&
                pause.isolated_actuator == options.isolated_pause_control &&
                (!options.isolated_pause_control || pause.isolated_reply == "paused"),
                "Quiet hidden hold must verify one new native pause on the same navigation before DOM sampling");
            require(hidden.navigation_generation == playing.navigation_generation && hidden.paused && !hidden.seeking,
                "The first post-hold DOM sample must show the same media paused");
#ifdef __APPLE__
            quiet_hidden_pause = pause;
#endif
          }
          require(hidden.current_time < 2.9 && hidden.current_time >= playing.current_time - 0.05 && !hidden.ended,
              "Hidden pause must precede the color transition and natural ending");
          if (!options.quiet_hidden_hold) {
            hidden = ui.held_media(cycle, "hidden-tab-pause", session, hidden, 0.75);
          }
          ui.finish_hidden_media(true);
          ui.media_capture(cycle, "hidden-video-tab", 0, rectangle, hidden,
              options.quiet_hidden_hold ? std::string{} : session);
#ifdef __APPLE__
          ui.record_native_pause_trace(close.get(), session);
#endif
          return hidden;
        }
        catch (...) {
          ui.finish_hidden_media(false);
#ifdef __APPLE__
          ui.record_hidden_native_close(close.get(), session, playing_returned);
          ui.record_native_pause_trace(close.get(), session);
#endif
          throw;
        }
      }();
      require(area->tab(1).save_workspace_state() == draft_state, "Video hide preserves the Python draft");
#ifdef __APPLE__
      const auto reveal_started = Clock::now();
      try {
#endif
        [[maybe_unused]] const auto reveal_route = ui.tab(*area, 0);
#ifdef __APPLE__
        if (html_video && options.quiet_hidden_hold && reveal_route == "area_menu") {
          // Keyboard selection leaves the pointer on the menu button, whose tooltip blocks the native view.
          auto &pointer = result["quiet_reveal_pointer"];
          pointer = {{"tab_route", std::string(reveal_route)}, {"moved", false}, {"before", ui.input_state()}};
          const auto *viewport = ui.widget("reports_document_viewport");
          if (viewport && viewport->type == ui::WidgetType::NativeViewport && viewport->enabled && ui.visible(viewport)) {
            const ui::Vec2 center{viewport->rect.cx(), viewport->rect.cy()};
            pointer["viewport_center"] = {center.x, center.y};
            ui.move_pointer(center);
            pointer["moved"] = true;
            pointer["after"] = ui.input_state();
          }
        }
#endif
        ui.wait(ready, "Paused video report shown again");
#ifdef __APPLE__
      }
      catch (...) {
        if (html_video && options.quiet_hidden_hold) {
          ui.record_failed_media_reveal(cycle, *area, session, *resources, close.get(), playing_returned, reveal_started);
        }
        throw;
      }
#endif
      MediaHoldExit observe_hold_exit;
#ifdef __APPLE__
      if (options.quiet_hidden_hold) {
        observe_hold_exit = [&](Clock::time_point start, Clock::time_point exited,
                               std::optional<Clock::time_point> failure, size_t samples, bool success) {
          ui.record_reshown_hold_native_observation(cycle, session, close.get(), quiet_hidden_pause,
              reveal_started, start, exited, failure, samples, success);
        };
      }
#endif
      auto reshown = ui.held_media(cycle, "reshown-no-autoresume", session, hidden, 0.50,
                                   options.isolated_pause_control, std::move(observe_hold_exit));
#ifdef __APPLE__
      if (options.pause_during_hidden_suspension) {
        const auto &hold = result.at("reshown_hold_native_observation");
        const auto &release = hold.at("last_recorded_release_state");
        const auto &ack = hold.at("release_ack");
        using Playback = document_preview::test::PlaybackState;
        require(hold.at("matches_hidden_pause") == true && !ack.is_null() && !release.is_null() &&
            (release.at("raw_playback_state") == int(Playback::Paused) ||
             release.at("raw_playback_state") == int(Playback::None)) &&
            release.at("seconds_from_reveal").get<double>() < hold.at("hold_exit_seconds").get<double>(),
            "The hold needs an exact release acknowledgement and Paused/None before it exits");
      }
#endif
      ui.media_capture(cycle, "reshown-red-paused", 1, ui.media_rectangle(bounds, reshown), reshown, session);
      // Return to the earliest segment before a second explicit Play. Rewinding is
      // itself local input; showing the tab must never provide that playback action.
      if (!options.pre_seek_hide_control && reshown.current_time > 0.90) {
        const auto navigation = reshown.navigation_generation;
#ifdef __APPLE__
        ui.native_media_seek(cycle, "rewind-after-show", session, bounds, reshown, 0.07);
#else
        ui.native_media_key(cycle, "rewind-after-show", bounds, wm::Key::LeftArrow, "LeftArrow", reshown);
#endif
        reshown = ui.media_until(session, [navigation](const Media &m) {
          return m.navigation_generation == navigation && m.paused && !m.ended &&
              !m.seeking && m.current_time <= 0.90;
        }, "Native input rewinds before explicit resume", 5);
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
  const int expected_preparations = cycles + 1;
  require(prepares == expected_preparations && (!video || trace_prepares == expected_preparations) &&
      image_reads == (pdf ? 0 : expected_preparations) && !awaiting_image,
      "Explicit preparations and frozen asset reads must match the required cycle count");
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
  require(result.at("images").size() == required_images - (video ? 1 : 0) && result.at("completed_cycles") == cycles,
      "Every required reading cycle and source-specific OS observation must complete");
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
    result["media_scope_revocations"].push_back({{"cycle", expected_preparations}, {"scope", "project-close-before-ACK"},
        {"session_id", final_media_resources->identity().session_id},
        {"old_url_get_range_status", 410}, {"old_url_head_status", 410}});
    ui.wait([&] { return completion->has_value(); }, "Project close ACK");
    require(completion->value().ok() && completion->value().value(), "Actual project close must complete successfully");
    ui.media_capture(expected_preparations, "project-scope-closed", 0, final_media_rectangle, final_media_observed);
    require(result.at("images").size() == required_images &&
        result.at("media_scope_revocations").size() == size_t(expected_preparations),
        "Every playback cycle and the final actual project-scope revocation must complete");
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
#if defined(__APPLE__) && defined(STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES)
    if (arg == "--visible-frame-clock-control") {
      // Rides the fresh-visible sequence; every other control mode is rejected below.
      if (options.fresh_pause_diagnostic()) { return 2; }
      options.fresh_pause = Options::FreshPause::Visible;
      options.frame_clock_control = true;
      continue;
    }
    if (arg == "--first-toolbar-pause-delay-control" || arg == "--first-toolbar-pause-immediate-control") {
      if (options.first_toolbar_pause_control) { return 2; }
      options.first_toolbar_pause_control = true;
      options.first_toolbar_immediate = arg == "--first-toolbar-pause-immediate-control";
      continue;
    }
    if (arg == "--first-toolbar-frame-clock-playing" || arg == "--first-toolbar-frame-clock-paused") {
      if (options.first_toolbar_pause_control) { return 2; }
      options.first_toolbar_pause_control = true;
      options.first_toolbar_immediate = true;
      options.first_toolbar_frames = arg == "--first-toolbar-frame-clock-playing" ?
          Options::FirstToolbarFrames::Playing : Options::FirstToolbarFrames::Paused;
      continue;
    }
    if (arg == "--suspend-reveal-control") {
      if (options.suspend_reveal_control) { return 2; }
      options.suspend_reveal_control = true;
      continue;
    }
    if (arg == "--fresh-native-hide-dom-control" || arg == "--fresh-native-visible-dom-control") {
      if (options.fresh_pause_diagnostic()) { return 2; }
      options.fresh_pause = arg == "--fresh-native-visible-dom-control" ? Options::FreshPause::Visible :
                                                                         Options::FreshPause::Hidden;
      continue;
    }
    if (arg == "--visible-native-pause-control") { options.visible_pause_control = true; continue; }
    if (arg == "--second-visible-native-pause-control") { options.second_visible_pause_control = true; continue; }
    if (arg == "--repeat-verified-visible-native-pause-control") {
      if (options.repeat_verified_visible_pause_control) { return 2; }
      options.repeat_verified_visible_pause_control = true;
      continue;
    }
    if (arg == "--hide-after-verified-native-pause-control" || arg == "--hide-without-repeat-native-pause-control" ||
        arg == "--hide-without-repeat-native-pause-dom-control") {
      if (options.hide_after_verified_pause_control) { return 2; }
      options.hide_after_verified_pause_control = true;
      options.retain_visible_pause_control = arg != "--hide-after-verified-native-pause-control";
      options.hidden_dom_tail_control = arg == "--hide-without-repeat-native-pause-dom-control";
      continue;
    }
    if (arg == "--pre-seek-hide-control") { options.pre_seek_hide_control = true; continue; }
    if (arg == "--pause-during-hidden-suspension") { options.pause_during_hidden_suspension = true; continue; }
    if (arg == "--quiet-pre-seek-hide-control" || arg == "--isolated-quiet-pre-seek-hide-control") {
      options.pre_seek_hide_control = true;
      options.quiet_hidden_hold = true;
      options.isolated_pause_control = arg == "--isolated-quiet-pre-seek-hide-control";
      continue;
    }
#endif
    if (i + 1 >= argc) { return 2; }
    if (arg == "--python") { options.python = argv[++i]; }
    else if (arg == "--gpu-backend") { options.backend = argv[++i]; }
    else if (arg == "--evidence-dir") { options.output = core::path_from_utf8(argv[++i]); }
    else if (arg == "--source") { options.source = argv[++i]; }
    else if (arg == "--media-fixture") { options.media_fixture = core::path_from_utf8(argv[++i]); }
    else { return 2; }
  }
  if (options.python.empty() || options.output.empty() ||
      (options.visible_pause_control && options.second_visible_pause_control) ||
      (options.hide_after_verified_pause_control && options.visible_pause_diagnostic()) ||
      (options.repeat_verified_visible_pause_control &&
          (options.hide_after_verified_pause_control || options.visible_pause_diagnostic())) ||
      (options.pause_order_diagnostic() && options.pre_seek_hide_control) ||
      (options.fresh_pause_diagnostic() && (options.pause_order_diagnostic() || options.pre_seek_hide_control)) ||
      (options.first_toolbar_pause_control && (options.pause_order_diagnostic() || options.pre_seek_hide_control ||
                                               options.fresh_pause_diagnostic())) ||
      (options.suspend_reveal_control && (options.source != "video" || options.pause_order_diagnostic() ||
          options.pre_seek_hide_control || options.fresh_pause_diagnostic() || options.first_toolbar_pause_control)) ||
      (options.pause_during_hidden_suspension && (!options.isolated_pause_control || options.source != "video")) ||
      ((options.pause_order_diagnostic() || options.pre_seek_hide_control || options.fresh_pause_diagnostic() ||
        options.first_toolbar_pause_control) &&
          options.source != "video" && options.source != "html-video") ||
      (options.source != "markdown" && options.source != "html" && options.source != "pdf"
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
       && options.source != "video" && options.source != "html-video"
#endif
      )) {
    std::fprintf(stderr, "usage: stk-reports-native-window --python PATH --gpu-backend BACKEND --evidence-dir DIR --source markdown|html|pdf|video|html-video [--media-fixture MP4] [--pre-seek-hide-control|--quiet-pre-seek-hide-control|--isolated-quiet-pre-seek-hide-control|--visible-native-pause-control|--second-visible-native-pause-control|--repeat-verified-visible-native-pause-control|--hide-after-verified-native-pause-control|--hide-without-repeat-native-pause-control|--hide-without-repeat-native-pause-dom-control|--fresh-native-hide-dom-control|--fresh-native-visible-dom-control|--visible-frame-clock-control|--first-toolbar-pause-delay-control|--first-toolbar-pause-immediate-control|--first-toolbar-frame-clock-playing|--first-toolbar-frame-clock-paused|--suspend-reveal-control] [--pause-during-hidden-suspension]\n"); return 2;
  }
  Json result = {{"format", "stk.reports-native-evidence/1"}, {"status", "running"}, {"required_cycles", options.reading_cycles()},
      {"completed_cycles", 0}, {"images", Json::array()}, {"native_scroll_requests", Json::array()},
      {"claim", "Production ReportsEditor app actions, frozen bridge resources and OS-composited STK client pixels; opt-in media also records bounded local native child input and fixed read-only media observations"},
      {"not_proven_here", "OS hardware input, IME, arbitrary PDF fidelity/search/selection, modal same-OS-batch ordering, physical scanout and browser memory stability; URL410/parent-close are separate Host CPU and spike native tests; final guarded memory is the separate after-static spike gate"}};
  if (options.visible_pause_diagnostic()) {
    result["scenario"] = options.second_visible_pause_control ?
        "second-visible-native-pause-control" : "visible-native-pause-control";
    result["claim"] = options.second_visible_pause_control ?
        "Cocoa native pause after resuming the quiet pre-seek playback history while the same report stays visible" :
        "Cocoa baseline for the first native pause after initial playback in a visible frozen report";
    if (options.second_visible_pause_control) {
      result["matched_control"] = "quiet-pre-seek-hide-control";
    }
    result["production_ui_acceptance"] = false;
  }
  if (options.hide_after_verified_pause_control) {
    result["scenario"] = options.retain_visible_pause_control ? "hide-without-repeat-native-pause-control" :
                                                               "hide-after-verified-native-pause-control";
    result["claim"] = options.retain_visible_pause_control ?
        "The ordinary tab hide retains the exact verified visible pause; a read-only query reports hidden playback" :
        "The ordinary tab hide issues its own native pause after the exact visible pause has verified";
    result["matched_control"] = options.retain_visible_pause_control ? "hide-after-verified-native-pause-control" :
                                                                      "quiet-pre-seek-hide-control";
    result["production_ui_acceptance"] = false;
  }
  if (options.repeat_verified_visible_pause_control) {
    result["scenario"] = "repeat-verified-visible-native-pause-control";
    result["claim"] = "Repeat a verified native pause while the same already-paused report stays visible";
    result["matched_control"] = "hide-after-verified-native-pause-control";
    result["production_ui_acceptance"] = false;
  }
  if (options.hidden_dom_tail_control) {
    result["scenario"] = "hide-without-repeat-native-pause-dom-control";
    result["claim"] = "After one hidden native reply without a repeated pause, two fixed DOM samples report playback and media-time progression";
    result["matched_control"] = "hide-without-repeat-native-pause-control";
  }
  if (options.fresh_pause_diagnostic()) {
    const bool keep_visible = options.fresh_pause == Options::FreshPause::Visible;
    result["scenario"] = keep_visible ? "fresh-native-visible-dom-control" : "fresh-native-hide-dom-control";
    result["claim"] = keep_visible ?
        "Keep the report visible through one native pause after the full seek history and two bounded DOM samples" :
        "After the ordinary fresh pause on real tab hide, capture the first hidden native reply and two bounded DOM samples";
    result["matched_control"] = keep_visible ? "reports_fresh_native_hide_dom_" + options.source + "_metal" :
                                               "reports_native_" + options.source + "_metal";
    result["production_ui_acceptance"] = false;
  }
  if (options.frame_clock_control) {
    result["scenario"] = "visible-frame-clock-control";
    result["claim"] = "Fresh-visible sequence on a separately pinned frame-ID clip: OS picture IDs during playback and "
        "after the same visible native pause, compared with the bounded DOM currentTime samples";
    result["matched_control"] = "reports_fresh_native_visible_dom_" + options.source + "_metal";
    result["not_a_gate"] = "Non-gating diagnostic; frame-ID captures are kept out of images and required_images";
  }
  if (options.first_toolbar_immediate) {
    result["scenario"] = "first-toolbar-pause-immediate-control";
    result["claim"] = "First actual Reports toolbar pause without a deliberate wait after Play returns, on the original clip without seeking";
    result["matched_control"] = "reports_first_toolbar_pause_delay_" + options.source + "_metal";
    result["comparison"] = "Both optional arms sample immediately after the click and again in the 200–300 ms and 600–700 ms windows "
        "from native dispatch. The mandatory test waits for a paused DOM sample before checking its floor.";
    result["production_ui_acceptance"] = false;
    result["not_a_gate"] = "An early DOM reading may differ from the later observations. The native trace may still be awaiting a reply.";
  }
  else if (options.first_toolbar_pause_control) {
    result["scenario"] = "first-toolbar-pause-delay-control";
    result["claim"] = "One passive 270 ms interval before the first actual Reports toolbar pause, on the original clip without seeking";
    result["matched_control"] = "reports_native_" + options.source + "_metal";
    result["comparison"] = "Compare the first DOM sample after the click with last_explicit_pause_observation "
        "in the same-run mandatory test. Subsequent samples characterize the optional arm only.";
    result["production_ui_acceptance"] = false;
    result["not_a_gate"] = "The outcome describes the observed sample. Extra elapsed playback can mask a rollback.";
  }
  if (options.first_toolbar_frames != Options::FirstToolbarFrames::None) {
    const bool playing = options.first_toolbar_frames == Options::FirstToolbarFrames::Playing;
    result["scenario"] = playing ? "first-toolbar-frame-clock-playing" : "first-toolbar-frame-clock-paused";
    result["claim"] = playing ? "Frame markers immediately after first Play, with playback continuing" :
        "Stable frame marker after the first immediate toolbar Pause and all three existing DOM samples";
    result["matched_control"] = "reports_first_toolbar_frame_clock_" +
        std::string(playing ? "paused_" : "playing_") + options.source + "_metal";
    result["not_a_gate"] = "The arms use separate sessions. Discrete captures may miss transient pictures.";
  }
  if (options.suspend_reveal_control) {
    result["scenario"] = "suspend-reveal-control";
    result["claim"] = "Test-owned Cocoa suspension through the ordinary hide pause, release on the same revealed view, "
        "and explicit native Play after a quiet hold";
    result["production_ui_acceptance"] = false;
  }
  if (options.pre_seek_hide_control) {
    result["scenario"] = options.isolated_pause_control ? "isolated-quiet-pre-seek-hide-control" :
        (options.quiet_hidden_hold ? "quiet-pre-seek-hide-control" : "pre-seek-hide-control");
    if (options.isolated_pause_control) {
      result["control"] = "One fixed test-only pause action in a private WKContentWorld; native playback state and the original deadline decide verification";
    }
    if (options.pause_during_hidden_suspension) {
      result["scenario"] = "pause-during-hidden-suspension";
      result["matched_control"] = "reports_isolated_quiet_pre_seek_hide_video_metal";
      result["intervention"] = "One native pause after the exact hidden suspension is verified and before the original reveal";
      result["production_ui_acceptance"] = false;
    }
  }
  fs::path directory;
  try {
    fs::create_directories(options.output);
    directory = options.output / ("run-" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count()));
    require(fs::create_directory(directory), "Evidence run directory must be new");
    write(directory / "result.json", result.dump(2));
    {
      gfx::Runtime runtime;
      run(options, result, directory);
      require(result.value("native_ax_cleanup_complete", true), "Native AX child cleanup was not confirmed");
    }
    // The window, bridge, manager and Runtime have now returned from normal destruction.
    // Engine static destructors and the final guarded leak gate belong to the separate spike.
    std::string outcome;
    if (options.frame_clock_control) {
      const auto evidence = result.find("visible_frame_clock");
      outcome = evidence != result.end() && evidence->is_object() ? evidence->value("outcome", "") : "";
      require(outcome == "picture_backward" || outcome == "clock_reset_within_observation" ||
          outcome == "no_clock_reset_observed", "Visible frame clock finished without a conclusive outcome");
    }
    if (options.first_toolbar_frames == Options::FirstToolbarFrames::None && options.first_toolbar_pause_control) {
      outcome = result.at(options.first_toolbar_immediate ? "first_toolbar_pause_immediate" :
                                                          "first_toolbar_pause_delay").value("outcome", "");
      require(outcome == "early_paused_above_floor" || outcome == "early_paused_at_or_below_floor" ||
          outcome == "early_sample_not_paused", options.first_toolbar_immediate ?
          "First toolbar pause immediate control finished without a valid observation" :
          "First toolbar pause delay control finished without a valid observation");
    }
    result["status"] = "passed";
    write(directory / "result.json", result.dump(2));
    if (options.suspend_reveal_control) {
      std::fprintf(stdout, "PASS: Cocoa suspend reveal diagnostic; %s\n", core::path_to_utf8(directory).c_str());
      return 0;
    }
    if (options.frame_clock_control) {
      std::fprintf(stdout, "PASS: Cocoa visible frame clock diagnostic; outcome=%s; cycles=%d; %s\n",
          outcome.c_str(), options.reading_cycles(), core::path_to_utf8(directory).c_str());
      return 0;
    }
    if (options.first_toolbar_frames != Options::FirstToolbarFrames::None) {
      outcome = result.at("first_toolbar_frame_clock").at("outcome").get<std::string>();
      std::fprintf(stdout, "PASS: Cocoa first toolbar frame clock diagnostic; outcome=%s; %s\n",
          outcome.c_str(), core::path_to_utf8(directory).c_str());
      return 0;
    }
    if (options.first_toolbar_pause_control) {
      std::fprintf(stdout, "PASS: Cocoa first toolbar pause %s control diagnostic; outcome=%s; cycles=%d; %s\n",
          options.first_toolbar_immediate ? "immediate" : "delay", outcome.c_str(),
          options.reading_cycles(), core::path_to_utf8(directory).c_str());
      return 0;
    }
    if (options.fresh_pause_diagnostic()) {
      std::fprintf(stdout, "PASS: Cocoa fresh native %s dom diagnostic; cycles=%d; %s\n",
          options.fresh_pause == Options::FreshPause::Visible ? "visible" : "hide",
          options.reading_cycles(), core::path_to_utf8(directory).c_str());
      return 0;
    }
    if (options.visible_pause_diagnostic()) {
      std::fprintf(stdout, "PASS: Cocoa %svisible native pause diagnostic; cycles=%d; %s\n",
          options.second_visible_pause_control ? "second " : "", options.reading_cycles(),
          core::path_to_utf8(directory).c_str());
      return 0;
    }
    if (options.repeat_verified_visible_pause_control) {
      std::fprintf(stdout, "PASS: Cocoa repeat verified visible native pause diagnostic; cycles=%d; %s\n",
          options.reading_cycles(), core::path_to_utf8(directory).c_str());
      return 0;
    }
    if (options.hide_after_verified_pause_control) {
      std::fprintf(stdout, "PASS: Cocoa %s diagnostic; cycles=%d; %s\n",
          options.hidden_dom_tail_control ? "hide without repeat native pause dom" :
          options.retain_visible_pause_control ? "hide without repeat native pause" : "hide after verified native pause",
          options.reading_cycles(), core::path_to_utf8(directory).c_str());
      return 0;
    }
    const char *scenario = "native evidence";
    if (options.pre_seek_hide_control) {
      scenario = options.isolated_pause_control ? "isolated quiet pre-seek hide control" :
          (options.quiet_hidden_hold ? "quiet pre-seek hide control" : "pre-seek hide control");
    }
    std::fprintf(stdout, "PASS: production ReportsEditor %s; cycles=%d; OS images=%zu; %s\n",
        scenario, options.reading_cycles(), result.at("images").size(), core::path_to_utf8(directory).c_str());
    return 0;
  }
  catch (const std::exception &error) {
    std::fprintf(stderr, "FAIL: %s\n", error.what());
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    log_last_media_observation(result);
#endif
    log_last_observation(result);
    try {
      result["status"] = "failed"; result["error"] = error.what();
      if (!directory.empty()) { write(directory / "result.json", result.dump(2)); }
    }
    catch (...) {}
    return 1;
  }
}
