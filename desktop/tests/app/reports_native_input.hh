/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/document/native_view.hh"
#include "stk/wm/event.hh"
#include <string>
#include <vector>
#include <memory>
#include <cstdint>
#include <optional>
#ifdef __APPLE__
#  include "reports_native_ax_process.hh"
#endif

namespace stk::reports_native_test {
#ifdef __APPLE__
// Bounded test-host facts only: never identify another app or window.
struct WindowActivationObservation {
  int policy = -1;
  bool main_thread = false, valid_target = false, own_window = false;
  bool app_active = false, window_key = false, exact_key_window = false;
  bool visible = false, miniaturized = false, can_become_key = false;
};
struct WindowActivationRequest {
  WindowActivationObservation before, after;
  int policy_after_change = -1;
  bool policy_change_attempted = false, policy_change_succeeded = false;
  bool activation_requested = false;
};
struct TimelineInput {
  // Video-element bounds normalized to the exact document viewport, top-left.
  double left = 0, top = 0, width = 0, height = 0;
  double current_time = 0, duration = 0, target_fraction = 0;
  uint64_t navigation_generation = 0, viewport_generation = 0;
  ax::Deadline deadline; // Same absolute seek budget, never serialized to the AX child.
};
// Fixed categories/counts only: never retain AX objects, labels, text or URLs.
struct TimelineChildListObservation {
  std::string type = "unsupported"; // nil / array / other / exception.
  int count = 0;                  // Capped at node_limit + 1.
  bool over_budget = false;
};
struct TimelineNodeObservation {
  int ordinal = 0, depth = 0;
  double elapsed_ms = 0;
  std::string category = "other"; // webview / remote / other.
  std::string selected_role = "other", legacy_role = "unsupported", modern_role = "unsupported";
  bool legacy_selector = false, modern_children_selector = false, modern_role_selector = false;
  bool paged_count_selector = false, paged_values_selector = false;
  bool paged_count_observed = false, paged_count_over_budget = false, diagnostic_exception = false;
  bool extra_getters_started = false, extra_getters_complete = false;
  int paged_count = 0;
  TimelineChildListObservation selected_children, legacy_children, modern_children;
};
struct TimelineObservation {
  double elapsed_ms = 0, diagnostic_elapsed_ms = 0;
  bool diagnostics_truncated = false, diagnostics_timeout = false;
  std::vector<TimelineNodeObservation> nodes;
  bool lookup_complete = false;
  int visited_nodes = 0, deepest_node = 0, sliders = 0, candidates = 0;
  double screen_x = 0, screen_y = 0, screen_width = 0, screen_height = 0;
  double minimum = 0, maximum = 0, value = 0;
  double normalized_x = 0, normalized_y = 0;
  bool public_client_attempted = false, public_client_revalidated = false;
  ax::ProcessResult public_client;
};
enum class TimelinePoll { Pending, Delivered, Failed };
#endif
/** Test-only delivery to this application's exact native document child.
 * The viewport is in parent framebuffer pixels with a bottom-left origin;
 * normalized click coordinates are top-left and inclusive in [0, 1].
 * Keys are limited to Space, LeftArrow, RightArrow, Home, End and Esc.
 * No global input queue is used. Success proves local event delivery only;
 * callers must independently prove playback/seek/pause with DOM and OS pixels.
 */
class NativeInput {
 public:
#ifdef __APPLE__
  // Request activation separately from key delivery, then observe it after the
  // caller pumps the real UI loop. Neither method sends keyboard input.
  bool request_window_activation(wm::NativeWindowHandle parent, WindowActivationRequest &request,
                                 std::string &error);
  bool window_is_active(wm::NativeWindowHandle parent, WindowActivationObservation &observation,
                        std::string &error);
  // Candidate lookup only. poll_seek asynchronously revalidates native media before any local mouse input.
  bool begin_provider_seek(wm::NativeWindowHandle parent, document_preview::ViewBounds viewport,
                     int framebuffer_width, int framebuffer_height, const TimelineInput &input,
                     std::shared_ptr<document_preview::ResourceSession> resources,
                     TimelineObservation &observation, std::string &error);
  // Called only after all original provider attempts completed empty. Never waits for a subprocess on the UI thread.
  bool begin_client_seek(wm::NativeWindowHandle parent, document_preview::ViewBounds viewport,
                         int framebuffer_width, int framebuffer_height, const TimelineInput &input,
                         std::shared_ptr<document_preview::ResourceSession> resources, std::string &error);
  TimelinePoll poll_seek(TimelineObservation &observation, std::string &delivery, std::string &error);
  void cancel_seek() noexcept;
  // Cleanup path: no AppKit/DOM call and no input. nullopt means the cancelled worker still owns cleanup.
  std::optional<ax::ProcessResult> poll_cancelled_seek() noexcept;
  bool seek_pending() const { return bool(client_seek_); }
  bool child_cleanup_confirmed() const noexcept { return child_cleanup_confirmed_; }
#endif
  bool click_document(wm::NativeWindowHandle parent, document_preview::ViewBounds viewport,
                      int framebuffer_width, int framebuffer_height,
                      double normalized_x, double normalized_y,
                      std::string &delivery, std::string &error);
  bool key_document(wm::NativeWindowHandle parent, document_preview::ViewBounds viewport,
                    int framebuffer_width, int framebuffer_height, wm::Key key,
                    std::string &delivery, std::string &error);
 private:
#ifdef __APPLE__
  bool prepare_seek(wm::NativeWindowHandle parent, document_preview::ViewBounds viewport,
                    int width, int height, const TimelineInput &input,
                    std::shared_ptr<document_preview::ResourceSession> resources, bool public_client, std::string &error);
  std::shared_ptr<void> client_seek_; // Cocoa ownership stays on the UI thread; the worker holds numeric DTOs only.
  uint64_t seek_generation_ = 0;
  bool child_cleanup_confirmed_ = true;
#endif
};
}  // namespace stk::reports_native_test
