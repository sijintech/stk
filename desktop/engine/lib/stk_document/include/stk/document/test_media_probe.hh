/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES

#include "stk/wm/native_window.hh"

#ifdef __APPLE__
#  include <array>
#  include <chrono>
#  include <optional>
#endif
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <string_view>

namespace stk::document_preview {
class ResourceSession;

namespace test {

struct MediaSnapshot {
  bool paused = false, ended = false, seeking = false, duration_known = false;
  double current_time = 0, duration = 0;
  double rect_x = 0, rect_y = 0, rect_width = 0, rect_height = 0;
  double viewport_width = 0, viewport_height = 0;
  int ready_state = 0, network_state = 0, error_code = 0;
  int video_width = 0, video_height = 0;
  uint64_t navigation_generation = 0; // Native identity; never accepted from DOM JSON.
};

// Last native pause request, not the current playback state: a user may have
// played again since it completed. Unavailable is unknown, never a negative ACK.
// verified records only the existing native not-Playing check within its deadline;
// it does not assert that the DOM media time has settled.
struct NativePauseSnapshot {
  bool available = false;
  uint64_t media_generation = 0, navigation_generation = 0;
  bool acknowledged = false, verified = false;
  bool visible_at_dispatch = false;
  uint64_t query_count = 0, reply_count = 0, playing_reply_count = 0;
  double first_query_seconds = 0, last_reply_seconds = 0;
  bool isolated_actuator = false;
  std::string_view isolated_reply{};
};

struct MediaProbeResult {
  bool ok = false;
  std::string error;
  MediaSnapshot media;
  // Native facts sampled at probe dispatch and callback, outside the 17-field
  // DOM profile. Platforms without this instrumentation leave both unavailable.
  NativePauseSnapshot native_pause_before, native_pause_after;
};
using MediaProbeCallback = std::function<void(MediaProbeResult)>;

/** Test-only, exact in-process parent/session lookup; no bridge or persistent registry. */
bool probe_media(wm::NativeWindowHandle parent, std::string_view session_id,
                 MediaProbeCallback callback, std::string &error);
/** Retain the actual verified session so closing its scope can be checked against old URLs. */
std::shared_ptr<ResourceSession> resource_session(wm::NativeWindowHandle parent,
                                                 std::string_view session_id, std::string &error);
#ifdef __APPLE__
struct NativeHidePauseEvent {
  std::string_view phase;
  double elapsed_seconds = 0;
  bool visible = false, webview_hidden = false, owns_focus = false;
  std::optional<int> playback_state;
};

struct NativeHidePauseTrace {
  uint64_t media_generation = 0, navigation_generation = 0;
  std::chrono::steady_clock::time_point dispatched;
  bool overflow = false;
  // The original 1 s watchdog permits at most 40 query/reply pairs. Leave room
  // for dispatch, ACK, focus/visibility transitions and shutdown.
  std::array<NativeHidePauseEvent, 96> events{};
  std::size_t event_count = 0;
};

/** UI-thread only. Read the cached production watchdog receipt for the exact hidden target.
 * This issues neither a WebKit playback-state request nor a DOM probe. */
std::optional<NativePauseSnapshot> hidden_pause_target(wm::NativeWindowHandle parent,
                                                       std::string_view session_id,
                                                       const NativeHidePauseTrace &observation);

struct NativeCloseObservation {
  std::string_view reason; // Empty until the exact observed view enters shutdown.
  std::chrono::steady_clock::time_point when;
  uint64_t media_generation = 0, navigation_generation = 0;
  NativePauseSnapshot pause;
  std::optional<NativeHidePauseTrace> hide_pause;
};

/** UI-thread only. The observation survives view destruction without owning the view or its resources.
 * A matching nonzero navigation also records the next pause and its hide lifecycle. */
std::shared_ptr<const NativeCloseObservation> observe_native_close(wm::NativeWindowHandle parent,
                                                                 std::string_view session_id,
                                                                 uint64_t watch_pause_navigation = 0);
/** UI-thread only: arm a fixed, one-shot pause action on this visible test navigation. */
bool arm_isolated_pause(wm::NativeWindowHandle parent, std::string_view session_id,
                        uint64_t navigation_generation);
struct VisiblePauseEvent {
  std::string_view phase;
  double elapsed_seconds = 0;
  bool visible = false;
  std::optional<int> playback_state; // Only a WK playback-state reply carries a native enum value.
};

struct VisiblePauseObservation {
  uint64_t media_generation = 0, navigation_generation = 0;
  bool verified = false, visibility_lost = false, overflow = false;
  std::optional<bool> visible_at_close;
  // One dispatch and ACK plus at most one query/reply per 25 ms over the 1 s watchdog.
  std::array<VisiblePauseEvent, 84> events{};
  std::size_t event_count = 0;
};

/** UI-thread only: run the production native pause on an exact ready and actually visible test view. */
std::shared_ptr<const VisiblePauseObservation> begin_visible_pause_control(
    wm::NativeWindowHandle parent, std::string_view session_id, uint64_t navigation_generation);
/** UI-thread only: check visibility and native identity without a DOM read. */
bool visible_pause_target(wm::NativeWindowHandle parent, std::string_view session_id,
                          const VisiblePauseObservation &observation);

/** Test only: keep this verified visible pause through the next ordinary hide request. */
bool retain_visible_pause_on_hide(wm::NativeWindowHandle parent, std::string_view session_id,
                                  const VisiblePauseObservation &observation);
/** Sample WebKit on the exact hidden view. The reply is independent of pause verification. */
bool probe_hidden_playback(wm::NativeWindowHandle parent, std::string_view session_id,
                           const NativeHidePauseTrace &observation,
                           std::function<void(std::optional<int>)> callback);

/** UI-thread only: bind an input target to the unique ready session and its native navigation.
 * expected_view is compared with the real WKWebView; no native object is returned or sent over IPC.
 */
bool matches_native_view(wm::NativeWindowHandle parent, std::string_view session_id,
                         const void *expected_view, uint64_t navigation_generation);
#endif
/** Parse one bounded flat DOM snapshot. Failure leaves output unchanged; native generation is preserved. */
bool parse_media_snapshot(std::string_view json, MediaSnapshot &media, std::string &error);

// Fixed read-only probes. They do not change DOM, playback, seeking or page script settings.
// Zero/multiple video elements return null, which the strict parser rejects.
inline constexpr char kMediaProbeScript[] = R"JS((() => {
  const videos = document.querySelectorAll('video');
  if (videos.length !== 1) return null;
  const v = videos[0];
  const r = v.getBoundingClientRect();
  const known = Number.isFinite(v.duration);
  const failure = v.error;
  return {
    paused: v.paused,
    ended: v.ended,
    seeking: v.seeking,
    duration_known: known,
    current_time: v.currentTime,
    duration: known ? v.duration : 0,
    rect_x: r.x,
    rect_y: r.y,
    rect_width: r.width,
    rect_height: r.height,
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    ready_state: v.readyState,
    network_state: v.networkState,
    error_code: failure ? failure.code : 0,
    video_width: v.videoWidth,
    video_height: v.videoHeight
  };
})())JS";

inline constexpr wchar_t kMediaProbeScriptWide[] = LR"JS((() => {
  const videos = document.querySelectorAll('video');
  if (videos.length !== 1) return null;
  const v = videos[0];
  const r = v.getBoundingClientRect();
  const known = Number.isFinite(v.duration);
  const failure = v.error;
  return {
    paused: v.paused,
    ended: v.ended,
    seeking: v.seeking,
    duration_known: known,
    current_time: v.currentTime,
    duration: known ? v.duration : 0,
    rect_x: r.x,
    rect_y: r.y,
    rect_width: r.width,
    rect_height: r.height,
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    ready_state: v.readyState,
    network_state: v.networkState,
    error_code: failure ? failure.code : 0,
    video_width: v.videoWidth,
    video_height: v.videoHeight
  };
})())JS";

}  // namespace test
}  // namespace stk::document_preview

#endif  // STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
