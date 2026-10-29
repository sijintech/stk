/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES

#include "stk/wm/native_window.hh"

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

struct MediaProbeResult {
  bool ok = false;
  std::string error;
  MediaSnapshot media;
};
using MediaProbeCallback = std::function<void(MediaProbeResult)>;

/** Test-only, exact in-process parent/session lookup; no bridge or persistent registry. */
bool probe_media(wm::NativeWindowHandle parent, std::string_view session_id,
                 MediaProbeCallback callback, std::string &error);
/** Retain the actual verified session so closing its scope can be checked against old URLs. */
std::shared_ptr<ResourceSession> resource_session(wm::NativeWindowHandle parent,
                                                 std::string_view session_id, std::string &error);
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
