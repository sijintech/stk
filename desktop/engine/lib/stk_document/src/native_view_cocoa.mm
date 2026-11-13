/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/document/native_view.hh"
#include "stk/document/media_pause_verification.hh"
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
#  include "stk/document/test_media_probe.hh"
#endif

#import <AppKit/AppKit.h>
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
#  import <CoreFoundation/CoreFoundation.h>
#endif
#import <WebKit/WebKit.h>
#import <dispatch/dispatch.h>

#include <algorithm>
#include <memory>
#include <utility>

namespace stk::document_preview::cocoa {

struct PauseRequest;
struct ReleaseRequest;

struct State {
  std::shared_ptr<ResourceSession> resources;
  NativeViewState result;
  __weak NSWindow *parent = nil;
  __strong WKWebView *view = nil;
  __strong NSObject *delegate = nil;
  __strong WKNavigation *navigation = nil;
  __strong NSView *focus_before = nil;
  __strong NSView *focus_after = nil;
  __weak NSResponder *focus_wait_responder = nil;
  FocusExitHandler focus_exit;
  uint64_t focus_generation = 0;
  uint64_t media_generation = 0;
  uint64_t visibility_generation = 0;
  uint64_t focus_after_media = 0;
  detail::MediaPlaybackSuspension suspension;
  std::shared_ptr<PauseRequest> hide_pause;
  std::shared_ptr<ReleaseRequest> release;
  std::optional<detail::MediaPauseVerification::Clock::time_point> release_started;
  bool media_interaction_blocked = false;
  std::string requested_url;
  bool closed = false;
  bool policy_ready = false;
  bool policy_failed = false;
  bool visible = false;
  bool has_bounds = false;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  test::NativePauseSnapshot test_last_pause;
  std::shared_ptr<test::NativeCloseObservation> test_close_observation;
  std::weak_ptr<test::VisiblePauseObservation> test_visible_pause;
  uint64_t test_retain_visible_pause_generation = 0;
  uint64_t test_isolated_pause_navigation = 0;
  bool test_owns_playback_suspension = false;
  bool test_release_waits_for_owner = false;
#endif
};
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
static std::vector<std::weak_ptr<State>> test_states;

static test::NativePauseSnapshot test_pause_snapshot(const std::shared_ptr<State> &state)
{
  const auto &pause = state->test_last_pause;
  if (pause.available && pause.media_generation == state->media_generation &&
      pause.navigation_generation == state->result.navigation_generation) {
    return pause;
  }
  return {}; // No matching request observation; not evidence of a missing ACK.
}
#endif

static NSString *string(std::string_view value)
{
  return [[NSString alloc] initWithBytes:value.data()
                                 length:value.size()
                               encoding:NSUTF8StringEncoding];
}

static std::string utf8(NSString *value)
{
  const char *bytes = value.UTF8String;
  return bytes ? std::string(bytes) : std::string();
}

static bool live(const std::shared_ptr<State> &state)
{
  return state && !state->closed && state->parent && state->resources->active();
}

static bool admitted_url(const std::shared_ptr<State> &state, std::string_view url)
{
  // ResourceSession also understands the Windows HTTPS form; WK must never fetch that URL.
  return url.starts_with("stk-preview://local/") && state->resources->allows_navigation(url) &&
         url.substr(0, url.find('#')) ==
             std::string_view(state->requested_url).substr(0, state->requested_url.find('#'));
}

static void blocked(const std::shared_ptr<State> &state)
{
  if (state && !state->closed) {
    ++state->result.blocked_requests;
  }
}

static void fail(const std::shared_ptr<State> &state, const char *message)
{
  state->result.status = NativeViewStatus::Failed;
  state->result.message = message;
}

static bool owns_focus(const std::shared_ptr<State> &state)
{
  NSResponder *responder = state->parent.firstResponder;
  return responder &&
         (responder == state->focus_before || responder == state->focus_after ||
          ([responder isKindOfClass:[NSView class]] &&
           (responder == state->view || [(NSView *)responder isDescendantOf:state->view])));
}

static bool relinquish_focus(const std::shared_ptr<State> &state)
{
  if (!owns_focus(state)) {
    return true;
  }
  NSWindow *parent = state->parent;
  [parent makeFirstResponder:parent.contentView];
  if (owns_focus(state)) {
    [parent makeFirstResponder:nil];
  }
  return !owns_focus(state);
}

static void shutdown(const std::shared_ptr<State> &state, NativeViewStatus status, const char *message);
static constexpr char kPauseWatchdogFailure[] = "Could not verify paused document media playback";
static constexpr char kPauseReplyFailure[] = "Could not pause document media playback";
static constexpr char kSuspensionFailure[] = "Could not verify document media playback suspension";
static void reconcile_media(const std::shared_ptr<State> &state);
static bool request_hidden_pause(const std::shared_ptr<State> &state, std::string &error);

static bool actually_visible(const std::shared_ptr<State> &state)
{
  if (!live(state) || !state->visible || !state->has_bounds) { return false; }
  NSWindow *parent = state->parent;
  WKWebView *view = state->view;
  return view && view.superview == parent.contentView && view.window == parent &&
         !view.isHiddenOrHasHiddenAncestor && !NSIsEmptyRect(view.visibleRect) &&
         parent.isVisible && !parent.isMiniaturized;
}
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
static constexpr char kIsolatedPauseFailure[] = "The isolated test pause did not pause its media element";

static bool visible_for_pause_control(const std::shared_ptr<State> &state)
{
  NSWindow *parent = state->parent;
  WKWebView *view = state->view;
  return parent && view && view.superview == parent.contentView && view.window == parent &&
         !view.isHiddenOrHasHiddenAncestor && !NSIsEmptyRect(view.visibleRect) &&
         parent.isVisible && !parent.isMiniaturized;
}

static void observe_hide_pause(const std::shared_ptr<State> &state, std::string_view phase,
                               detail::MediaPauseVerification::Clock::time_point now,
                               std::optional<int> playback = {})
{
  const auto &observation = state->test_close_observation;
  if (!observation || !observation->hide_pause) { return; }
  auto &trace = *observation->hide_pause;
  if (trace.media_generation != state->media_generation ||
      trace.navigation_generation != state->result.navigation_generation) { return; }
  if (trace.event_count == 0) {
    if (phase != "dispatch") { return; }
    trace.dispatched = now;
  }
  if (trace.event_count == trace.events.size()) {
    trace.overflow = true;
    return;
  }
  trace.events[trace.event_count++] = {phase, std::chrono::duration<double>(now - trace.dispatched).count(),
      visible_for_pause_control(state), bool(state->view.hidden), owns_focus(state), playback};
}
#endif

struct PauseRequest {
  std::weak_ptr<State> state;
  __weak WKWebView *view = nil;
  detail::MediaPauseVerification verification;
  uint64_t generation, navigation;
  bool acknowledged = false;
  bool query_inflight = false;
  bool held_for_hide = false;
  bool verified = false;
  bool pause_requested_under_suspension = false;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  detail::MediaPauseVerification::Clock::time_point started;
  std::shared_ptr<test::VisiblePauseObservation> visible_control;

  void observe(std::string_view phase, const std::shared_ptr<State> &current,
               detail::MediaPauseVerification::Clock::time_point now, std::optional<int> playback = {})
  {
    if (!visible_control) { return; }
    auto &trace = *visible_control;
    if (trace.event_count == trace.events.size()) {
      trace.overflow = true;
      return;
    }
    trace.events[trace.event_count++] = {phase, std::chrono::duration<double>(now - started).count(),
                                        visible_for_pause_control(current), playback};
  }
#endif

  PauseRequest(const std::shared_ptr<State> &source, uint64_t generation,
               detail::MediaPauseVerification::Clock::time_point now)
      : state(source),
        view(source->view),
        verification(generation, source->result.navigation_generation, now),
        generation(generation), navigation(source->result.navigation_generation)
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
        , started(now)
#endif
  {
  }
};

static void verify_pause(std::shared_ptr<PauseRequest> request)
{
  auto current = request->state.lock();
  if (!live(current) || current->view != request->view) {
    return;
  }
  using Check = detail::MediaPauseVerification;
  const auto now = Check::Clock::now();
  const auto pending = request->verification.expire(
      current->media_generation, current->result.navigation_generation, now);
  if (pending == Check::Result::Failed) {
    shutdown(current, NativeViewStatus::Failed, kPauseWatchdogFailure);
    return;
  }
  if (pending != Check::Result::Waiting) {
    return;
  }
  // The watchdog is independent of WebKit replies and never owns the view or
  // State. There is at most one state query or suspended pause in flight.
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 25 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
    verify_pause(request);
  });
  if (!request->acknowledged || request->query_inflight ||
      (request->held_for_hide && !current->suspension.ready(true))) {
    return;
  }
  request->query_inflight = true;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  auto &pause = current->test_last_pause;
  if (++pause.query_count == 1) {
    pause.first_query_seconds = std::chrono::duration<double>(now - request->started).count();
  }
  request->observe("query", current, now);
  observe_hide_pause(current, "query", now);
#endif
  [current->view requestMediaPlaybackStateWithCompletionHandler:^(WKMediaPlaybackState playback) {
    request->query_inflight = false;
    auto completed = request->state.lock();
    if (!live(completed) || completed->view != request->view) {
      return;
    }
    const auto replied = Check::Clock::now();
    const auto waiting = request->verification.expire(
        completed->media_generation, completed->result.navigation_generation, replied);
    const bool needs_suspended_pause = request->held_for_hide && completed->hide_pause == request &&
        completed->suspension.ready(true) && !request->pause_requested_under_suspension &&
        playback == WKMediaPlaybackStateSuspended;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    // Keep the isolated actuator and its explicit diagnostic follow-up independent.
    const bool use_native_pause = !completed->test_last_pause.isolated_actuator;
#else
    const bool use_native_pause = true;
#endif
    if (waiting == Check::Result::Waiting && needs_suspended_pause && use_native_pause) {
      // Suspension can remember prior playing intent. Pause once under our own suspension before
      // accepting the proof that allows release, with the same request and original deadline.
      request->pause_requested_under_suspension = true;
      request->query_inflight = true;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
      observe_hide_pause(completed, "pause-under-suspension", replied, int(playback));
#endif
      [completed->view pauseAllMediaPlaybackWithCompletionHandler:^{
        request->query_inflight = false;
        const auto active = request->state.lock();
        if (!live(active) || active->view != request->view || active->hide_pause != request ||
            active->media_generation != request->generation || active->result.navigation_generation != request->navigation) {
          return;
        }
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
        observe_hide_pause(active, "pause-under-suspension-ack", Check::Clock::now());
#endif
        // The existing watchdog owns the next query and the deadline.
      }];
      return;
    }
    const bool playing = playback == WKMediaPlaybackStatePlaying;
    const auto result = waiting == Check::Result::Waiting ? request->verification.observe(
        playing, completed->media_generation, completed->result.navigation_generation, replied) : waiting;
    request->verified |= result == Check::Result::Paused;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    if (result != Check::Result::Ignored) {
      auto &pause = completed->test_last_pause;
      ++pause.reply_count;
      pause.playing_reply_count += playing;
      pause.last_reply_seconds = std::chrono::duration<double>(replied - request->started).count();
      pause.verified = result == Check::Result::Paused;
      request->observe("reply", completed, replied, int(playback));
      observe_hide_pause(completed, "reply", replied, int(playback));
      if (request->visible_control) { request->visible_control->verified = pause.verified; }
    }
#endif
    if (result == Check::Result::Failed) {
      shutdown(completed, NativeViewStatus::Failed, kPauseReplyFailure);
    }
    else if (result == Check::Result::Paused && completed->hide_pause == request) {
      reconcile_media(completed);
    }
  }];
}

struct ReleaseRequest {
  std::weak_ptr<State> state;
  __weak WKWebView *view = nil;
  detail::MediaPauseVerification verification;
  uint64_t visibility;
  bool query_inflight = false;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  bool first_reply_recorded = false;
#endif

  ReleaseRequest(const std::shared_ptr<State> &source, detail::MediaPauseVerification::Clock::time_point started)
      : state(source), view(source->view),
        verification(source->media_generation, source->result.navigation_generation, started),
        visibility(source->visibility_generation)
  {
  }
};

static bool continue_release(const std::shared_ptr<State> &state, const std::shared_ptr<ReleaseRequest> &request)
{
  if (!live(state) || state->view != request->view || state->release != request) { return false; }
  if (state->visibility_generation == request->visibility && actually_visible(state) &&
      state->suspension.ready(false)) { return true; }
  // AppKit can obscure or miniaturize the view between host layout callbacks.
  // Retire this proof so the next visible frame can verify its own release.
  state->release.reset();
  state->release_started.reset();
  reconcile_media(state);
  return false;
}

static void verify_release(std::shared_ptr<ReleaseRequest> request)
{
  auto state = request->state.lock();
  if (!continue_release(state, request)) { return; }
  using Check = detail::MediaPauseVerification;
  const auto pending = request->verification.expire(
      state->media_generation, state->result.navigation_generation, Check::Clock::now());
  if (pending == Check::Result::Failed) {
    shutdown(state, NativeViewStatus::Failed, kSuspensionFailure);
    return;
  }
  if (pending != Check::Result::Waiting) { return; }
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 25 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
    verify_release(request);
  });
  if (request->query_inflight) { return; }
  request->query_inflight = true;
  [state->view requestMediaPlaybackStateWithCompletionHandler:^(WKMediaPlaybackState playback) {
    request->query_inflight = false;
    auto current = request->state.lock();
    if (!continue_release(current, request)) { return; }
    const auto now = Check::Clock::now();
    const bool unpaused = playback != WKMediaPlaybackStatePaused && playback != WKMediaPlaybackStateNone;
    const auto result = request->verification.observe(
        unpaused, current->media_generation, current->result.navigation_generation, now);
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    // The diagnostic owns another balanced YES/NO pair. Observe its exact hold,
    // then require a fresh Paused/None proof when that owner submits its NO.
    if (result == Check::Result::Waiting && playback == WKMediaPlaybackStateSuspended &&
        current->test_owns_playback_suspension) {
      current->test_release_waits_for_owner = true;
      current->release.reset();
      observe_hide_pause(current, "release-test-held", now, int(playback));
      return;
    }
    if (!request->first_reply_recorded || result != Check::Result::Waiting) {
      request->first_reply_recorded = true;
      observe_hide_pause(current, "release-state", now, int(playback));
    }
#endif
    if (result == Check::Result::Failed) {
      shutdown(current, NativeViewStatus::Failed, kSuspensionFailure);
    }
    else if (result == Check::Result::Paused) {
      current->release.reset();
      current->release_started.reset();
      current->hide_pause.reset();
      current->media_interaction_blocked = false;
      const auto focus = std::exchange(current->focus_after_media, 0);
      NSResponder *responder = current->focus_wait_responder;
      current->focus_wait_responder = nil;
      if (focus && focus == current->focus_generation && current->parent.isKeyWindow &&
          current->parent.firstResponder == responder &&
          ![current->parent makeFirstResponder:current->view]) {
        shutdown(current, NativeViewStatus::Failed, "Could not focus the document.");
      }
    }
  }];
}

static void reconcile_media(const std::shared_ptr<State> &state)
{
  if (!live(state) || !state->view || !state->media_interaction_blocked) { return; }
  using Lease = detail::MediaPlaybackSuspension;
  const auto &pause = state->hide_pause;
  const bool same_pause = pause && pause->generation == state->media_generation &&
      pause->navigation == state->result.navigation_generation && pause->view == state->view;
  const bool proved = same_pause && pause->verified;
  const bool visible = actually_visible(state);
  if (!visible) {
    state->focus_after_media = 0;
    state->focus_wait_responder = nil;
  }
  if (!visible || !proved) {
    state->release.reset();
    state->release_started.reset();
  }
  state->suspension.require(!visible || !proved);
  const auto now = Lease::Clock::now();
  if (const auto command = state->suspension.next(now)) {
    if (!command->suspend) { state->release_started = now; }
    const std::weak_ptr<State> weak = state;
    __weak WKWebView *view = state->view;
    const auto operation = *command;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    const auto media = state->media_generation, navigation = state->result.navigation_generation;
#endif
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
      const auto current = weak.lock();
      if (live(current) && current->view == view && current->suspension.expired(operation, Lease::Clock::now())) {
        shutdown(current, NativeViewStatus::Failed, kSuspensionFailure);
      }
    });
    [state->view setAllMediaPlaybackSuspended:operation.suspend completionHandler:^{
      const auto current = weak.lock();
      if (!live(current) || current->view != view) { return; }
      const auto reply = current->suspension.acknowledge(operation, Lease::Clock::now());
      if (reply == Lease::Reply::Failed) {
        shutdown(current, NativeViewStatus::Failed, kSuspensionFailure);
        return;
      }
      if (reply != Lease::Reply::Accepted) { return; }
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
      if (current->media_generation == media && current->result.navigation_generation == navigation) {
        observe_hide_pause(current, operation.suspend ? "suspend-ack" : "release-ack", Lease::Clock::now());
      }
#endif
      reconcile_media(current); // Settle an old effect before applying the latest desired state.
    }];
    return;
  }
  if (visible && proved && state->suspension.ready(false) && !state->release) {
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    if (state->test_release_waits_for_owner) { return; }
#endif
    state->release = std::make_shared<ReleaseRequest>(state, state->release_started.value_or(Lease::Clock::now()));
    verify_release(state->release);
  }
}

static void sync_visibility(const std::shared_ptr<State> &state)
{
  const bool show = live(state) && state->visible && state->has_bounds;
  const bool visibility_transition = bool(state->view.hidden) == show;
  if (visibility_transition) {
    ++state->visibility_generation;
    state->release.reset();
  }
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  using PauseClock = detail::MediaPauseVerification::Clock;
#endif
  if (!show) {
    state->focus_after_media = 0;
    state->focus_wait_responder = nil;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    if (visibility_transition) { observe_hide_pause(state, "focus-release-before", PauseClock::now()); }
    if (const auto trace = state->test_visible_pause.lock()) { trace->visibility_lost = true; }
#endif
    ++state->focus_generation;
    if (!relinquish_focus(state)) {
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
      if (visibility_transition) { observe_hide_pause(state, "focus-release-failed", PauseClock::now()); }
#endif
      shutdown(state, NativeViewStatus::Failed, "Could not relinquish document keyboard focus.");
      return;
    }
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    if (visibility_transition) { observe_hide_pause(state, "focus-release-after", PauseClock::now()); }
#endif
  }
  state->view.hidden = !show;
  state->focus_before.hidden = !show;
  state->focus_after.hidden = !show;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  if (visibility_transition) { observe_hide_pause(state, show ? "show" : "hide", PauseClock::now()); }
#endif
  if (state->media_interaction_blocked && state->result.status == NativeViewStatus::Ready &&
      (!state->hide_pause || state->hide_pause->navigation != state->result.navigation_generation)) {
    std::string error;
    if (!request_hidden_pause(state, error)) {
      shutdown(state, NativeViewStatus::Failed, kSuspensionFailure);
      return;
    }
  }
  reconcile_media(state);
}

// All calls and delegate callbacks are on the main thread. The returned WKNavigation is the
// identity of this load; a cancelled older load may still report its failure afterwards.
static void load_requested(const std::shared_ptr<State> &state)
{
  if (!live(state) || !state->policy_ready || state->requested_url.empty()) {
    return;
  }
  NSURL *url = [NSURL URLWithString:string(state->requested_url)];
  NSURLRequest *request = [NSURLRequest requestWithURL:url
                                         cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                     timeoutInterval:30.0];
  state->navigation = [state->view loadRequest:request];
  if (!state->navigation) {
    fail(state, "WKWebView did not accept the document load.");
  }
}

static void begin_navigation(const std::shared_ptr<State> &state, std::string url)
{
  ++state->result.navigation_generation;
  state->release.reset();
  state->release_started.reset();
  state->focus_after_media = 0;
  state->focus_wait_responder = nil;
  state->navigation = nil;
  [state->view stopLoading];
  state->requested_url = std::move(url);
  state->result.status = NativeViewStatus::Loading;
  state->result.message = state->policy_ready ? "Loading admitted document bytes." :
                                               "Preparing the offline resource policy.";
  reconcile_media(state);
  load_requested(state);
}

static bool current(const std::shared_ptr<State> &state,
                    WKWebView *view,
                    WKNavigation *navigation)
{
  return live(state) && state->view == view && navigation && state->navigation == navigation;
}

}  // namespace stk::document_preview::cocoa

// The candidate intentionally has no context menu: WebKit/PDF menu items can otherwise expose
// "download" or "open with" operations outside the document navigation policy. Copy shortcuts
// remain native. Menu/keyboard/PDF behaviour still needs real macOS acceptance.
// Public AppKit key-view boundaries let WebKit finish native Tab/IME handling before handing
// focus back. They have no pixels, hit testing or key replay into the application.
@interface STKPreviewFocusBoundary : NSView {
 @public
  std::weak_ptr<stk::document_preview::cocoa::State> state_;
  stk::document_preview::NativeFocusExit direction_;
}
@end

@implementation STKPreviewFocusBoundary
- (BOOL)acceptsFirstResponder
{
  return YES;
}
- (BOOL)canBecomeKeyView
{
  auto state = state_.lock();
  return stk::document_preview::cocoa::live(state) && !state->media_interaction_blocked && state->visible && state->has_bounds &&
         self.window == state->parent && !self.isHiddenOrHasHiddenAncestor;
}
- (NSView *)hitTest:(NSPoint)point
{
  return nil;
}
- (void)keyDown:(NSEvent *)event
{
  // The handoff is pending. Never replay a later event against an unrelated host control.
}
- (BOOL)becomeFirstResponder
{
  using namespace stk::document_preview;
  auto state = state_.lock();
  if (![self canBecomeKeyView] || !state) {
    return NO;
  }
  const auto generation = ++state->focus_generation;
  const auto direction = direction_;
  std::weak_ptr<cocoa::State> weak = state;
  __weak NSView *boundary = self;
  // makeFirstResponder has not yet installed us while becomeFirstResponder is running.
  dispatch_async(dispatch_get_main_queue(), ^{
    auto target = weak.lock();
    NSView *view = boundary;
    if (!cocoa::live(target) || !target->visible || !target->has_bounds || !view ||
        target->focus_generation != generation || target->parent.firstResponder != view) {
      return;
    }
    if (!cocoa::relinquish_focus(target)) {
      cocoa::shutdown(target, NativeViewStatus::Failed, "Could not return document keyboard focus.");
      return;
    }
    if (!cocoa::live(target) || !target->visible || !target->has_bounds ||
        target->focus_generation != generation) {
      return;
    }
    auto callback = target->focus_exit;
    if (callback) {
      try {
        callback(direction);
      }
      catch (...) {
        cocoa::shutdown(target, NativeViewStatus::Failed, "The document focus handoff failed.");
      }
    }
  });
  return YES;
}
@end

@interface STKPreviewWebView : WKWebView {
 @public
  std::weak_ptr<stk::document_preview::cocoa::State> state_;
}
@end

@implementation STKPreviewWebView
- (BOOL)acceptsFirstResponder
{
  const auto state = state_.lock();
  return state && !state->media_interaction_blocked && [super acceptsFirstResponder];
}
- (BOOL)canBecomeKeyView
{
  const auto state = state_.lock();
  return state && !state->media_interaction_blocked && [super canBecomeKeyView];
}
- (NSView *)nextValidKeyView
{
  auto state = state_.lock();
  return state && [state->focus_after canBecomeKeyView] ? state->focus_after : [super nextValidKeyView];
}
- (NSView *)previousValidKeyView
{
  auto state = state_.lock();
  return state && [state->focus_before canBecomeKeyView] ? state->focus_before : [super previousValidKeyView];
}
- (NSView *)hitTest:(NSPoint)point
{
  const auto state = state_.lock();
  if (!state || state->media_interaction_blocked) { return nil; }
  NSView *hit = [super hitTest:point];
  NSEvent *event = NSApp.currentEvent;
  if (hit && event.window == self.window &&
      (event.type == NSEventTypeRightMouseDown ||
       (event.type == NSEventTypeLeftMouseDown &&
        (event.modifierFlags & NSEventModifierFlagControl)))) {
    // WKContentView is a child: route context-clicks here before it builds a native menu.
    return self;
  }
  return hit;
}
- (NSMenu *)menuForEvent:(NSEvent *)event
{
  return nil;
}
- (void)rightMouseDown:(NSEvent *)event
{
}
- (void)willOpenMenu:(NSMenu *)menu withEvent:(NSEvent *)event
{
  [menu removeAllItems];
}
@end

@interface STKPreviewDelegate : NSObject <WKNavigationDelegate, WKUIDelegate, WKURLSchemeHandler> {
 @public
  std::weak_ptr<stk::document_preview::cocoa::State> state_;
 @private
  NSMutableSet<id<WKURLSchemeTask>> *tasks_;
}
- (void)invalidate;
@end

@implementation STKPreviewDelegate

- (instancetype)init
{
  self = [super init];
  if (self) {
    tasks_ = [NSMutableSet set];
  }
  return self;
}

- (void)invalidate
{
  state_.reset();
  [tasks_ removeAllObjects];
}

- (void)webView:(WKWebView *)webView startURLSchemeTask:(id<WKURLSchemeTask>)task
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  if (!live(state) || state->view != webView) {
    [task didFailWithError:[NSError errorWithDomain:NSURLErrorDomain
                                             code:NSURLErrorCancelled
                                         userInfo:nil]];
    return;
  }
  [tasks_ addObject:task];
  // ResourceSession never opens a path or contacts a server; only admitted immutable bytes are
  // copied here. No task is queued onto another thread. WebKit may reenter stop during callbacks.
  const auto method = utf8(task.request.HTTPMethod);
  NSString *range_header = [task.request valueForHTTPHeaderField:@"Range"];
  const auto range = utf8(range_header);
  const auto response = state->resources->read(utf8(task.request.URL.absoluteString), method,
      range_header && range.empty() ? std::string_view{"invalid-range"} : std::string_view{range});
  if (response.status != 200 && response.status != 206) {
    blocked(state);
  }
  NSMutableDictionary *headers = [@{
    @"Content-Type" : string(response.mime),
    @"Content-Security-Policy" : string(response.content_security_policy),
    @"Cache-Control" : @"no-store",
    @"X-Content-Type-Options" : @"nosniff",
    @"Referrer-Policy" : @"no-referrer",
    @"Permissions-Policy" : @"camera=(), microphone=(), geolocation=(), fullscreen=()",
    @"Content-Length" : [NSString stringWithFormat:@"%llu", (unsigned long long)response.content_length]
  } mutableCopy];
  if (response.accept_ranges) { headers[@"Accept-Ranges"] = @"bytes"; }
  if (!response.content_range.empty()) { headers[@"Content-Range"] = string(response.content_range); }
  NSHTTPURLResponse *reply = [[NSHTTPURLResponse alloc] initWithURL:task.request.URL
                                                      statusCode:response.status
                                                     HTTPVersion:@"HTTP/1.1"
                                                    headerFields:headers];
  if (![tasks_ containsObject:task] || !live(state)) {
    return;
  }
  [task didReceiveResponse:reply];
  if (![tasks_ containsObject:task] || !live(state)) {
    return;
  }
  if (!response.bytes.empty()) {
    [task didReceiveData:[NSData dataWithBytes:response.bytes.data() length:response.bytes.size()]];
  }
  if (![tasks_ containsObject:task] || !live(state)) {
    return;
  }
  // Remove before the terminal callback so any reentrant stop cannot resurrect this task.
  [tasks_ removeObject:task];
  [task didFinish];
}

- (void)webView:(WKWebView *)webView stopURLSchemeTask:(id<WKURLSchemeTask>)task
{
  // Apple forbids every task callback after stop, including didFailWithError.
  [tasks_ removeObject:task];
}

- (void)webView:(WKWebView *)webView
    decidePolicyForNavigationAction:(WKNavigationAction *)action
                        preferences:(WKWebpagePreferences *)preferences
                    decisionHandler:(void (^)(WKNavigationActionPolicy,
                                               WKWebpagePreferences *))decisionHandler
{
  using namespace stk::document_preview::cocoa;
  preferences.allowsContentJavaScript = NO;
  auto state = state_.lock();
  const auto url = utf8(action.request.URL.absoluteString);
  const bool allowed = live(state) && state->view == webView && state->policy_ready &&
                       action.targetFrame.isMainFrame && !action.shouldPerformDownload &&
                       [action.request.HTTPMethod isEqualToString:@"GET"] &&
                       admitted_url(state, url);
  if (allowed && action.navigationType == WKNavigationTypeOther &&
      url == state->requested_url) {
    decisionHandler(WKNavigationActionPolicyAllow, preferences);
    return;
  }
  // Reissue an admitted user link as a tracked load. Do not let redirects, forms, new windows,
  // subframes or automatic document navigation create an untracked source identity.
  if (allowed && action.navigationType == WKNavigationTypeLinkActivated) {
    const auto generation = state->result.navigation_generation;
    std::weak_ptr<State> weak = state;
    decisionHandler(WKNavigationActionPolicyCancel, preferences);
    dispatch_async(dispatch_get_main_queue(), ^{
      auto target = weak.lock();
      if (live(target) && target->result.navigation_generation == generation &&
          admitted_url(target, url)) {
        begin_navigation(target, url);
      }
    });
    return;
  }
  blocked(state);
  decisionHandler(WKNavigationActionPolicyCancel, preferences);
}

- (void)webView:(WKWebView *)webView
    decidePolicyForNavigationResponse:(WKNavigationResponse *)response
                     decisionHandler:(void (^)(WKNavigationResponsePolicy))decisionHandler
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  NSHTTPURLResponse *http = [response.response isKindOfClass:[NSHTTPURLResponse class]] ?
                               (NSHTTPURLResponse *)response.response :
                               nil;
  // A custom scheme may be surfaced as NSURLResponse rather than NSHTTPURLResponse. The exact
  // admitted URL still has to resolve in our immutable manifest, independently of that wrapper.
  const bool allowed = live(state) && state->view == webView && response.isForMainFrame &&
                       response.canShowMIMEType && (!http || http.statusCode == 200) &&
                       admitted_url(state, utf8(response.response.URL.absoluteString));
  if (!allowed) {
    blocked(state);
  }
  decisionHandler(allowed ? WKNavigationResponsePolicyAllow : WKNavigationResponsePolicyCancel);
}

- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  if (current(state, webView, navigation)) {
    state->result.status = stk::document_preview::NativeViewStatus::Ready;
    state->result.message = "WKWebView navigation completed; display and input require native acceptance.";
    if (state->media_interaction_blocked) { sync_visibility(state); }
  }
}

- (void)webView:(WKWebView *)webView
    didFailProvisionalNavigation:(WKNavigation *)navigation
                      withError:(NSError *)error
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  if (current(state, webView, navigation)) {
    // Do not copy WebKit diagnostics containing local resource URLs into public state/logs.
    fail(state, "WKWebView could not load the admitted document.");
  }
}

- (void)webView:(WKWebView *)webView
    didFailNavigation:(WKNavigation *)navigation
            withError:(NSError *)error
{
  [self webView:webView didFailProvisionalNavigation:navigation withError:error];
}

- (void)webViewWebContentProcessDidTerminate:(WKWebView *)webView
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  if (live(state) && state->view == webView) {
    state->navigation = nil;
    fail(state, "The WebKit content process exited; reopen the document explicitly.");
  }
}

- (void)webView:(WKWebView *)webView
    didReceiveAuthenticationChallenge:(NSURLAuthenticationChallenge *)challenge
                   completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition,
                                                NSURLCredential *))completionHandler
{
  stk::document_preview::cocoa::blocked(state_.lock());
  completionHandler(NSURLSessionAuthChallengeCancelAuthenticationChallenge, nil);
}

- (void)webView:(WKWebView *)webView
    navigationAction:(WKNavigationAction *)action
   didBecomeDownload:(WKDownload *)download
{
  stk::document_preview::cocoa::blocked(state_.lock());
  [download cancel:nil];
}

- (void)webView:(WKWebView *)webView
    navigationResponse:(WKNavigationResponse *)response
     didBecomeDownload:(WKDownload *)download
{
  stk::document_preview::cocoa::blocked(state_.lock());
  [download cancel:nil];
}

- (WKWebView *)webView:(WKWebView *)webView
    createWebViewWithConfiguration:(WKWebViewConfiguration *)configuration
              forNavigationAction:(WKNavigationAction *)action
                   windowFeatures:(WKWindowFeatures *)features
{
  stk::document_preview::cocoa::blocked(state_.lock());
  return nil;
}

- (void)webView:(WKWebView *)webView
    runOpenPanelWithParameters:(WKOpenPanelParameters *)parameters
             initiatedByFrame:(WKFrameInfo *)frame
            completionHandler:(void (^)(NSArray<NSURL *> *))completionHandler
{
  stk::document_preview::cocoa::blocked(state_.lock());
  completionHandler(nil);
}

- (void)webView:(WKWebView *)webView
    requestMediaCapturePermissionForOrigin:(WKSecurityOrigin *)origin
                         initiatedByFrame:(WKFrameInfo *)frame
                                     type:(WKMediaCaptureType)type
                          decisionHandler:(void (^)(WKPermissionDecision))decisionHandler
{
  stk::document_preview::cocoa::blocked(state_.lock());
  decisionHandler(WKPermissionDecisionDeny);
}

- (void)webView:(WKWebView *)webView
    runJavaScriptAlertPanelWithMessage:(NSString *)message
                     initiatedByFrame:(WKFrameInfo *)frame
                    completionHandler:(void (^)(void))completionHandler
{
  completionHandler();
}

- (void)webView:(WKWebView *)webView
    runJavaScriptConfirmPanelWithMessage:(NSString *)message
                       initiatedByFrame:(WKFrameInfo *)frame
                      completionHandler:(void (^)(BOOL))completionHandler
{
  completionHandler(NO);
}

- (void)webView:(WKWebView *)webView
    runJavaScriptTextInputPanelWithPrompt:(NSString *)prompt
                             defaultText:(NSString *)defaultText
                        initiatedByFrame:(WKFrameInfo *)frame
                       completionHandler:(void (^)(NSString *))completionHandler
{
  completionHandler(nil);
}

@end

namespace stk::document_preview {
namespace cocoa {

static void shutdown(const std::shared_ptr<State> &state, NativeViewStatus status, const char *message)
{
  if (state->closed) {
    return;
  }
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  if (const auto trace = state->test_visible_pause.lock();
      trace && trace->media_generation == state->media_generation &&
      trace->navigation_generation == state->result.navigation_generation) {
    trace->visible_at_close = visible_for_pause_control(state);
  }
  if (state->test_close_observation) {
    const std::string_view failure = message;
    const char *reason = "other";
    if (failure == kPauseWatchdogFailure) {
      reason = "pause_watchdog";
    }
    else if (failure == kPauseReplyFailure) {
      reason = "pause_reply_after_deadline";
    }
    else if (failure == kSuspensionFailure) {
      reason = "playback_suspension";
    }
    else if (failure == kIsolatedPauseFailure) {
      reason = "isolated_pause_actuator_failed";
    }
    auto &observation = *state->test_close_observation;
    observation.reason = reason;
    observation.when = detail::MediaPauseVerification::Clock::now();
    observation.media_generation = state->media_generation;
    observation.navigation_generation = state->result.navigation_generation;
    observation.pause = test_pause_snapshot(state);
    observe_hide_pause(state, "close", observation.when);
  }
#endif
  state->closed = true;
  state->focus_exit = {};
  ++state->focus_generation;
  ++state->media_generation;
  ++state->result.navigation_generation;
  state->release.reset();
  state->release_started.reset();
  state->hide_pause.reset();
  state->suspension = {};
  state->focus_after_media = 0;
  state->focus_wait_responder = nil;
  state->result.status = status;
  state->result.message = message;
  state->resources->close();
  state->navigation = nil;
  relinquish_focus(state);
  state->view.hidden = YES;
  state->focus_before.hidden = YES;
  state->focus_after.hidden = YES;
  [(STKPreviewDelegate *)state->delegate invalidate];
  [state->view stopLoading];
  state->view.navigationDelegate = nil;
  state->view.UIDelegate = nil;
  state->view.nextKeyView = nil;
  state->focus_before.nextKeyView = nil;
  state->focus_after.nextKeyView = nil;
  [state->focus_before removeFromSuperview];
  [state->focus_after removeFromSuperview];
  [state->view removeFromSuperview];
  state->focus_before = nil;
  state->focus_after = nil;
  state->view = nil;
  state->delegate = nil;
  state->parent = nil;
  state->requested_url.clear();
}

}  // namespace cocoa
namespace {

class CocoaDocumentView final : public NativeDocumentView {
 public:
  explicit CocoaDocumentView(std::shared_ptr<cocoa::State> state) : state_(std::move(state)) {}
  ~CocoaDocumentView() override { close(); }

  bool navigate(std::string_view asset_path, std::string &error) override
  {
    const auto state = state_;
    error.clear();
    if (!cocoa::live(state) || state->policy_failed) {
      error = "The preview is closed or its offline policy is unavailable.";
      return false;
    }
    const auto url = state->resources->url(asset_path, false);
    if (url.empty() || !state->resources->allows_navigation(url)) {
      error = "The document is not in the current preview resource manifest.";
      return false;
    }
    cocoa::begin_navigation(state, url);
    return true;
  }

  void set_bounds(ViewBounds bounds) override
  {
    const auto state = state_;
    if (!cocoa::live(state)) {
      return;
    }
    NSView *content = state->parent.contentView;
    const NSRect backing = [content convertRectToBacking:content.bounds];
    const CGFloat width = std::max(bounds.width, 0);
    const CGFloat height = std::max(bounds.height, 0);
    const CGFloat y = content.isFlipped ? NSMaxY(backing) - bounds.y - height :
                                         NSMinY(backing) + bounds.y;
    const NSRect pixels = NSMakeRect(NSMinX(backing) + bounds.x, y, width, height);
    const NSRect frame = NSIntersectionRect([content convertRectFromBacking:pixels], content.bounds);
    state->has_bounds = !NSIsEmptyRect(frame);
    cocoa::sync_visibility(state);
    if (!state->closed) {
      state->view.frame = frame;
      cocoa::reconcile_media(state);
    }
  }

  void set_visible(bool visible) override
  {
    const auto state = state_;
    if (!state->closed) {
      state->visible = visible;
      cocoa::sync_visibility(state);
    }
  }

  bool pause_media(std::string &error) override { return request_pause(state_, error, false); }
  bool pause_media_for_hide(std::string &error) override { return request_pause(state_, error, true); }

  static bool request_pause(std::shared_ptr<cocoa::State> state, std::string &error, bool for_hide
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
      , std::shared_ptr<test::VisiblePauseObservation> visible_control = {}
#endif
  )
  {
    error.clear();
    if (![NSThread isMainThread] || !cocoa::live(state) || !state->view) {
      error = "The native document view is closed or unavailable";
      return false;
    }
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    if (!visible_control && state->test_retain_visible_pause_generation) {
      const auto retained = std::exchange(state->test_retain_visible_pause_generation, 0);
      const auto pause = cocoa::test_pause_snapshot(state);
      const auto visible = state->test_visible_pause.lock();
      if (visible && !visible->visibility_lost && pause.media_generation == retained && pause.acknowledged && pause.verified &&
          cocoa::visible_for_pause_control(state)) {
        // The diagnostic lets the real host hide the view without issuing another actuator command.
        cocoa::observe_hide_pause(state, "repeat-pause-suppressed", detail::MediaPauseVerification::Clock::now());
        return true;
      }
    }
    cocoa::observe_hide_pause(state, "superseded", detail::MediaPauseVerification::Clock::now());
#endif
    const auto generation = ++state->media_generation;
    const auto request = std::make_shared<cocoa::PauseRequest>(
        state, generation, detail::MediaPauseVerification::Clock::now());
    if (for_hide || state->media_interaction_blocked) {
      request->held_for_hide = true;
      state->hide_pause = request;
      state->release.reset();
      state->media_interaction_blocked = true;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
      state->test_release_waits_for_owner = false;
#endif
      // Submit the suspension before the ordinary pause while the host still
      // shows this view. Both commands precede its synchronous focus/pixel hide.
      cocoa::reconcile_media(state);
    }
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    const auto navigation = state->result.navigation_generation;
    const auto isolated_navigation = std::exchange(state->test_isolated_pause_navigation, 0);
    if (isolated_navigation && isolated_navigation != navigation) {
      error = "The armed test pause navigation changed";
      return false;
    }
    state->test_last_pause = {true, generation, navigation, false, false, !state->view.hidden};
    if (visible_control) {
      visible_control->media_generation = generation;
      visible_control->navigation_generation = navigation;
      state->test_visible_pause = visible_control;
      request->visible_control = std::move(visible_control);
    }
#endif
    cocoa::verify_pause(request);
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    if (isolated_navigation) {
      state->test_last_pause.isolated_actuator = true;
      // Only the acceptance fixture arms this once. The production state query and deadline
      // still decide whether the pause succeeded; the script reply is an acknowledgement.
      NSString *script = @"(() => { const media = document.querySelectorAll('video, audio'); "
                          @"if (media.length !== 1) return false; "
                          @"media[0].pause(); return media[0].paused && !media[0].ended; })()";
      cocoa::observe_hide_pause(state, "dispatch", detail::MediaPauseVerification::Clock::now());
      [state->view evaluateJavaScript:script inFrame:nil
          inContentWorld:[WKContentWorld worldWithName:@"STKReportPauseControl"]
          completionHandler:^(id value, NSError *failure) {
        auto completed = request->state.lock();
        if (!cocoa::live(completed) || completed->view != request->view ||
            completed->media_generation != generation || completed->result.navigation_generation != navigation) {
          return;
        }
        auto &pause = completed->test_last_pause;
        if (failure || ![value isKindOfClass:NSNumber.class] ||
            CFGetTypeID((__bridge CFTypeRef)value) != CFBooleanGetTypeID()) {
          pause.isolated_reply = "error";
        }
        else {
          request->acknowledged = [(NSNumber *)value boolValue];
          pause.isolated_reply = request->acknowledged ? "paused" : "refused";
        }
        pause.acknowledged = request->acknowledged;
        cocoa::observe_hide_pause(completed, request->acknowledged ? "ack" : "actuator-failed",
                                 detail::MediaPauseVerification::Clock::now());
        if (!request->acknowledged) {
          cocoa::shutdown(completed, NativeViewStatus::Failed, cocoa::kIsolatedPauseFailure);
        }
      }];
      return true;
    }
#endif
    // Public macOS 12+ API; project JavaScript remains disabled. Pausing never resumes media.
    // Completion acknowledges the pause command; independently verify the resulting
    // state within the original deadline rather than treating the first sample as final.
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
    const auto dispatched = detail::MediaPauseVerification::Clock::now();
    request->observe("dispatch", state, dispatched);
    cocoa::observe_hide_pause(state, "dispatch", dispatched);
#endif
    [state->view pauseAllMediaPlaybackWithCompletionHandler:^{
      request->acknowledged = true;
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
      auto completed = request->state.lock();
      if (cocoa::live(completed) && completed->view == request->view &&
          completed->media_generation == generation &&
          completed->result.navigation_generation == navigation) {
        auto &pause = completed->test_last_pause;
        if (pause.available && pause.media_generation == generation &&
            pause.navigation_generation == navigation) {
          pause.acknowledged = true;
          const auto acknowledged = detail::MediaPauseVerification::Clock::now();
          request->observe("ack", completed, acknowledged);
          cocoa::observe_hide_pause(completed, "ack", acknowledged);
        }
      }
#endif
    }];
    return true;
  }

  void focus() override
  {
    const auto state = state_;
    if (cocoa::live(state) && state->visible && state->has_bounds && state->parent.isKeyWindow) {
      ++state->focus_generation;
      if (state->media_interaction_blocked) {
        if (!cocoa::actually_visible(state)) { return; }
        state->focus_after_media = state->focus_generation;
        state->focus_wait_responder = state->parent.firstResponder;
        return;
      }
      if (![state->parent makeFirstResponder:state->view]) {
        cocoa::shutdown(state, NativeViewStatus::Failed, "Could not focus the document.");
      }
    }
  }

  void set_focus_exit_handler(FocusExitHandler handler) override
  {
    if (!state_->closed) {
      ++state_->focus_generation;
      state_->focus_exit = std::move(handler);
    }
  }

  bool return_focus() override
  {
    const auto state = state_;
    ++state->focus_generation;
    if (!cocoa::relinquish_focus(state)) {
      cocoa::shutdown(state, NativeViewStatus::Failed, "Could not return document keyboard focus.");
      return false;
    }
    return true;
  }

  void close() override
  {
    const auto state = state_;
    cocoa::shutdown(state, NativeViewStatus::Closed, "Document preview closed.");
  }

  NativeViewState state() const override
  {
    auto result = state_->result;
    NSWindow *parent = state_->parent;
    WKWebView *view = state_->view;
    result.parent_attached = !state_->closed && parent && view &&
                             view.superview == parent.contentView && view.window == parent;
    result.visible = result.parent_attached && !view.isHiddenOrHasHiddenAncestor &&
                     !NSIsEmptyRect(view.visibleRect) && parent.isVisible && !parent.isMiniaturized;
    result.focused = !state_->closed && cocoa::owns_focus(state_);
    if (!state_->closed && !cocoa::live(state_)) {
      result.status = NativeViewStatus::Failed;
      result.message = "The parent window or preview resource session is no longer available.";
    }
    return result;
  }

 private:
  std::shared_ptr<cocoa::State> state_;
};

}  // namespace

namespace cocoa {
static bool request_hidden_pause(const std::shared_ptr<State> &state, std::string &error)
{
  return CocoaDocumentView::request_pause(state, error, true);
}
}  // namespace cocoa

std::unique_ptr<NativeDocumentView> create_native_document_view(
    wm::NativeWindowHandle parent, std::shared_ptr<ResourceSession> resources, std::string &error)
{
  error.clear();
  if (![NSThread isMainThread] || parent.kind != wm::NativeWindowKind::Cocoa || !parent.value ||
      !resources || !resources->active()) {
    error = "WKWebView requires a live Cocoa parent and resource session on the main thread.";
    return nullptr;
  }
  NSWindow *window = (__bridge NSWindow *)parent.value;
  if (!window.contentView) {
    error = "The Cocoa parent has no content view.";
    return nullptr;
  }
  auto state = std::make_shared<cocoa::State>();
  state->resources = std::move(resources);
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
  cocoa::test_states.push_back(state);
#endif
  state->parent = window;
  state->result.message = "Preparing the offline resource policy.";
  NSBundle *webkit = [NSBundle bundleForClass:[WKWebView class]];
  state->result.runtime_version = cocoa::utf8([webkit objectForInfoDictionaryKey:@"CFBundleVersion"]);
  STKPreviewDelegate *delegate = [[STKPreviewDelegate alloc] init];
  delegate->state_ = state;
  state->delegate = delegate;
  WKWebViewConfiguration *configuration = [[WKWebViewConfiguration alloc] init];
  configuration.websiteDataStore = [WKWebsiteDataStore nonPersistentDataStore];
  configuration.defaultWebpagePreferences.allowsContentJavaScript = NO;
  configuration.preferences.javaScriptCanOpenWindowsAutomatically = NO;
  configuration.allowsAirPlayForMediaPlayback = NO;
  configuration.mediaTypesRequiringUserActionForPlayback = WKAudiovisualMediaTypeAll;
  [configuration setURLSchemeHandler:delegate forURLScheme:@"stk-preview"];
  STKPreviewWebView *web_view = [[STKPreviewWebView alloc] initWithFrame:NSZeroRect configuration:configuration];
  state->view = web_view;
  if (!state->view) {
    error = "WKWebView could not be created.";
    return nullptr;
  }
  state->view.navigationDelegate = delegate;
  state->view.UIDelegate = delegate;
  state->view.allowsBackForwardNavigationGestures = NO;
  state->view.allowsLinkPreview = NO;
  state->view.inspectable = NO;
  state->view.hidden = YES;
  web_view->state_ = state;
  STKPreviewFocusBoundary *before = [[STKPreviewFocusBoundary alloc] initWithFrame:NSZeroRect];
  STKPreviewFocusBoundary *after = [[STKPreviewFocusBoundary alloc] initWithFrame:NSZeroRect];
  before->state_ = state;
  after->state_ = state;
  before->direction_ = NativeFocusExit::Previous;
  after->direction_ = NativeFocusExit::Next;
  before.hidden = YES;
  after.hidden = YES;
  state->focus_before = before;
  state->focus_after = after;
  [window.contentView addSubview:before];
  [window.contentView addSubview:state->view];
  [window.contentView addSubview:after];
  before.nextKeyView = state->view;
  state->view.nextKeyView = after;
  after.nextKeyView = before;

  // Compile a constant, non-project-specific rule list. The store may persist compiled rules;
  // website data stays nonpersistent. No resource URL or project content enters that store.
  // The manifest handler gates the sole allowed scheme; CSP independently forbids active content.
  NSString *rules = @"[{\"trigger\":{\"url-filter\":\".*\"},\"action\":{\"type\":\"block\"}},"
                    "{\"trigger\":{\"url-filter\":\"^stk-preview://local/\"},"
                    "\"action\":{\"type\":\"ignore-previous-rules\"}}]";
  std::weak_ptr<cocoa::State> weak = state;
  [[WKContentRuleListStore defaultStore]
      compileContentRuleListForIdentifier:@"org.stk.document-preview.offline.v1"
                  encodedContentRuleList:rules
                       completionHandler:^(WKContentRuleList *list, NSError *compile_error) {
                         dispatch_async(dispatch_get_main_queue(), ^{
                           auto target = weak.lock();
                           if (!cocoa::live(target)) {
                             return;
                           }
                           if (compile_error || !list) {
                             target->policy_failed = true;
                             cocoa::fail(target, "The offline resource policy could not be installed.");
                             return;
                           }
                           [target->view.configuration.userContentController addContentRuleList:list];
                           target->policy_ready = true;
                           cocoa::load_requested(target);
                         });
                       }];
  return std::make_unique<CocoaDocumentView>(std::move(state));
}

#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
namespace test {
namespace {
std::shared_ptr<cocoa::State> find_view(wm::NativeWindowHandle parent, std::string_view session_id,
                                      std::string &error)
{
  error.clear();
  if (![NSThread isMainThread] || parent.kind != wm::NativeWindowKind::Cocoa || !parent.value ||
      session_id.size() != 36) {
    error = "Media test probe requires the exact Cocoa UI window and session"; return {};
  }
  NSWindow *window = (__bridge NSWindow *)parent.value;
  if (![NSApp.windows containsObject:window]) {
    error = "Media test probe window does not belong to this application"; return {};
  }
  std::erase_if(cocoa::test_states, [](const auto &weak) { return weak.expired(); });
  std::shared_ptr<cocoa::State> found;
  for (const auto &weak : cocoa::test_states) {
    const auto state = weak.lock();
    if (!cocoa::live(state) || state->parent != window || state->resources->identity().session_id != session_id) {
      continue;
    }
    if (found) { error = "Media test probe matched more than one live view"; return {}; }
    found = state;
  }
  if (!found) { error = "Media test probe session is no longer attached to this window"; }
  return found;
}

bool matches_pause_trace(const std::shared_ptr<cocoa::State> &state, const NativeHidePauseTrace &observation)
{
  return cocoa::live(state) && state->view && state->result.status == NativeViewStatus::Ready &&
         state->test_close_observation && state->test_close_observation->hide_pause &&
         &*state->test_close_observation->hide_pause == &observation &&
         state->result.navigation_generation == observation.navigation_generation;
}

bool matches_hidden_pause(const std::shared_ptr<cocoa::State> &state, const NativeHidePauseTrace &observation)
{
  return matches_pause_trace(state, observation) && !state->visible && state->view.hidden &&
         !cocoa::visible_for_pause_control(state) && !cocoa::owns_focus(state) &&
         state->media_generation == observation.media_generation;
}

bool matches_visible_playback(const std::shared_ptr<cocoa::State> &state,
                              const NativeHidePauseTrace &observation, bool before_hide)
{
  return matches_pause_trace(state, observation) && cocoa::visible_for_pause_control(state) &&
         (before_hide ? observation.event_count == 0 && state->media_generation + 1 == observation.media_generation :
                        state->media_generation == observation.media_generation);
}
}

std::shared_ptr<ResourceSession> resource_session(wm::NativeWindowHandle parent,
                                                std::string_view session_id, std::string &error)
{
  const auto state = find_view(parent, session_id, error);
  return state ? state->resources : nullptr;
}

std::shared_ptr<const NativeCloseObservation> observe_native_close(wm::NativeWindowHandle parent,
                                                                 std::string_view session_id,
                                                                 uint64_t watch_pause_navigation)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!state || !state->view || state->result.status != NativeViewStatus::Ready) {
    return {};
  }
  if (!state->test_close_observation) {
    state->test_close_observation = std::make_shared<NativeCloseObservation>();
  }
  auto &trace = state->test_close_observation->hide_pause;
  if (!trace && watch_pause_navigation && state->result.navigation_generation == watch_pause_navigation) {
    trace.emplace();
    trace->media_generation = state->media_generation + 1;
    trace->navigation_generation = watch_pause_navigation;
  }
  return state->test_close_observation;
}

std::optional<NativePauseSnapshot> hidden_pause_target(wm::NativeWindowHandle parent,
                                                       std::string_view session_id,
                                                       const NativeHidePauseTrace &observation)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!matches_hidden_pause(state, observation)) {
    return std::nullopt;
  }
  const auto pause = cocoa::test_pause_snapshot(state);
  return pause.available ? std::optional(pause) : std::nullopt;
}

bool pause_suspended_hidden_playback(wm::NativeWindowHandle parent, std::string_view session_id,
                                     const NativeHidePauseTrace &observation)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!matches_hidden_pause(state, observation) || !state->suspension.ready(true) ||
      state->test_owns_playback_suspension || observation.overflow ||
      observation.events.size() - observation.event_count < 2) {
    return false;
  }
  const auto pause = cocoa::test_pause_snapshot(state);
  if (!pause.isolated_actuator || !pause.acknowledged || !pause.verified) { return false; }
  const auto begin = observation.events.begin();
  const auto end = begin + observation.event_count;
  const auto reply = std::find_if(begin, end, [](const auto &event) {
    return event.phase == "reply" && event.playback_state == int(WKMediaPlaybackStateSuspended);
  });
  if (reply == end || std::any_of(reply, end, [](const auto &event) {
        return event.phase == "pause-during-suspension";
      })) {
    return false;
  }

  const auto close = state->test_close_observation;
  const auto visibility = state->visibility_generation;
  const std::weak_ptr<cocoa::State> weak = state;
  __weak WKWebView *expected_view = state->view;
  using Clock = detail::MediaPauseVerification::Clock;
  cocoa::observe_hide_pause(state, "pause-during-suspension", Clock::now());
  [state->view pauseAllMediaPlaybackWithCompletionHandler:^{
    const auto current = weak.lock();
    if (matches_hidden_pause(current, *close->hide_pause) && current->view == expected_view &&
        current->visibility_generation == visibility && current->suspension.ready(true) &&
        !current->test_owns_playback_suspension) {
      cocoa::observe_hide_pause(current, "pause-during-suspension-ack", Clock::now());
    }
  }];
  return true;
}

bool arm_isolated_pause(wm::NativeWindowHandle parent, std::string_view session_id,
                        uint64_t navigation_generation)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!state || !state->view || !state->visible || state->view.isHiddenOrHasHiddenAncestor ||
      state->result.status != NativeViewStatus::Ready || !navigation_generation ||
      state->result.navigation_generation != navigation_generation || state->test_isolated_pause_navigation) {
    return false;
  }
  state->test_isolated_pause_navigation = navigation_generation;
  return true;
}

std::shared_ptr<const VisiblePauseObservation> begin_visible_pause_control(
    wm::NativeWindowHandle parent, std::string_view session_id, uint64_t navigation_generation)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!state || state->result.status != NativeViewStatus::Ready || !navigation_generation ||
      state->result.navigation_generation != navigation_generation || state->test_isolated_pause_navigation ||
      !cocoa::visible_for_pause_control(state)) {
    return {};
  }
  auto observation = std::make_shared<VisiblePauseObservation>();
  return CocoaDocumentView::request_pause(state, error, false, observation) ? observation : nullptr;
}

bool visible_pause_target(wm::NativeWindowHandle parent, std::string_view session_id,
                          const VisiblePauseObservation &observation)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  return !observation.visibility_lost && state && state->result.status == NativeViewStatus::Ready &&
         state->test_visible_pause.lock().get() == &observation &&
         state->result.navigation_generation == observation.navigation_generation &&
         state->media_generation == observation.media_generation && cocoa::visible_for_pause_control(state);
}

bool retain_visible_pause_on_hide(wm::NativeWindowHandle parent, std::string_view session_id,
                                  const VisiblePauseObservation &observation)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!state || !state->test_close_observation || !state->test_close_observation->hide_pause ||
      state->test_isolated_pause_navigation || state->test_retain_visible_pause_generation) {
    return false;
  }
  const auto visible = state->test_visible_pause.lock();
  const auto &trace = *state->test_close_observation->hide_pause;
  const auto pause = cocoa::test_pause_snapshot(state);
  if (visible.get() != &observation || !observation.verified || observation.visibility_lost || observation.overflow ||
      trace.overflow || trace.media_generation != observation.media_generation ||
      trace.navigation_generation != observation.navigation_generation ||
      !pause.acknowledged || !pause.verified || pause.media_generation != observation.media_generation ||
      pause.navigation_generation != observation.navigation_generation ||
      state->result.status != NativeViewStatus::Ready || !cocoa::visible_for_pause_control(state)) {
    return false;
  }
  state->test_retain_visible_pause_generation = observation.media_generation;
  return true;
}

bool probe_hidden_playback(wm::NativeWindowHandle parent, std::string_view session_id,
                           const NativeHidePauseTrace &observation,
                           std::function<void(std::optional<int>)> callback)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!callback || !matches_hidden_pause(state, observation)) { return false; }
  const auto close = state->test_close_observation;
  const std::weak_ptr<cocoa::State> weak = state;
  __weak WKWebView *expected_view = state->view;
  cocoa::observe_hide_pause(state, "passive-query", detail::MediaPauseVerification::Clock::now());
  [state->view requestMediaPlaybackStateWithCompletionHandler:^(WKMediaPlaybackState playback) {
    const auto current = weak.lock();
    if (!matches_hidden_pause(current, *close->hide_pause) || current->view != expected_view) {
      callback(std::nullopt);
      return;
    }
    cocoa::observe_hide_pause(current, "passive-reply", detail::MediaPauseVerification::Clock::now(), int(playback));
    callback(int(playback));
  }];
  return true;
}

bool visible_playback_target(wm::NativeWindowHandle parent, std::string_view session_id,
                             const NativeHidePauseTrace &observation, bool before_hide)
{
  std::string error;
  return matches_visible_playback(find_view(parent, session_id, error), observation, before_hide);
}

bool probe_visible_playback(wm::NativeWindowHandle parent, std::string_view session_id,
                            const NativeHidePauseTrace &observation, bool before_hide,
                            std::function<void(std::optional<PlaybackState>)> callback)
{
  static_assert(int(PlaybackState::None) == WKMediaPlaybackStateNone &&
      int(PlaybackState::Playing) == WKMediaPlaybackStatePlaying &&
      int(PlaybackState::Paused) == WKMediaPlaybackStatePaused &&
      int(PlaybackState::Suspended) == WKMediaPlaybackStateSuspended);
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!callback || !matches_visible_playback(state, observation, before_hide)) { return false; }
  const auto close = state->test_close_observation;
  const std::weak_ptr<cocoa::State> weak = state;
  __weak WKWebView *expected_view = state->view;
  [state->view requestMediaPlaybackStateWithCompletionHandler:^(WKMediaPlaybackState playback) {
    const auto current = weak.lock();
    if (!matches_visible_playback(current, *close->hide_pause, before_hide) || current->view != expected_view) {
      callback(std::nullopt);
      return;
    }
    callback(static_cast<PlaybackState>(playback));
  }];
  return true;
}

bool set_visible_playback_suspended(wm::NativeWindowHandle parent, std::string_view session_id,
                                    const NativeHidePauseTrace &observation, bool suspend,
                                    std::function<void(bool)> callback)
{
  std::string error;
  const auto state = find_view(parent, session_id, error);
  if (!callback || !matches_visible_playback(state, observation, suspend) ||
      state->test_owns_playback_suspension == suspend) {
    return false;
  }
  if (!suspend) {
    const auto pause = cocoa::test_pause_snapshot(state);
    if (!pause.available || !pause.acknowledged || !pause.verified) { return false; }
  }
  const auto close = state->test_close_observation;
  const std::weak_ptr<cocoa::State> weak = state;
  __weak WKWebView *expected_view = state->view;
  state->test_owns_playback_suspension = suspend;
  if (!suspend && state->media_interaction_blocked) {
    state->release_started = detail::MediaPauseVerification::Clock::now();
  }
  [state->view setAllMediaPlaybackSuspended:suspend completionHandler:^{
    const auto current = weak.lock();
    const bool bound = matches_visible_playback(current, *close->hide_pause, suspend) && current->view == expected_view &&
                       current->test_owns_playback_suspension == suspend;
    if (bound && !suspend) {
      current->test_release_waits_for_owner = false;
      cocoa::reconcile_media(current);
    }
    callback(bound);
  }];
  return true;
}

bool matches_native_view(wm::NativeWindowHandle parent, std::string_view session_id,
                         const void *expected_view, uint64_t navigation_generation)
{
  if (!expected_view) { return false; }
  std::string error;
  const auto state = find_view(parent, session_id, error);
  return state && state->view && state->result.status == NativeViewStatus::Ready &&
         (__bridge const void *)state->view == expected_view &&
         state->result.navigation_generation == navigation_generation;
}

bool probe_media(wm::NativeWindowHandle parent, std::string_view session_id,
                 MediaProbeCallback callback, std::string &error)
{
  const auto state = find_view(parent, session_id, error);
  if (!state || !callback || !state->view || state->result.status != NativeViewStatus::Ready) {
    if (error.empty()) { error = "Media test probe requires a ready native document and callback"; }
    return false;
  }
  const auto navigation = state->result.navigation_generation;
  const auto session = state->resources;
  const auto pause_before = cocoa::test_pause_snapshot(state);
  const std::weak_ptr<cocoa::State> weak = state;
  __weak WKWebView *expected_view = state->view;
  NSString *script = [NSString stringWithUTF8String:kMediaProbeScript];
  [state->view evaluateJavaScript:script completionHandler:^(id value, NSError *failure) {
    MediaProbeResult result;
    result.native_pause_before = pause_before;
    const auto current = weak.lock();
    if (!cocoa::live(current) || current->result.status != NativeViewStatus::Ready ||
        current->resources != session || !session->active() ||
        current->result.navigation_generation != navigation || current->view != expected_view) {
      // Keep this failure closed while recording only bounded native identity facts.
      // A no-longer-ready WebKit process is different from a replaced document;
      // never include resource URLs, DOM values or project content in diagnostics.
      const char *reason = "other";
      if (!current) { reason = "state_released"; }
      else if (current->result.message == cocoa::kPauseReplyFailure) {
        reason = "pause_failed";
      }
      else if (current->result.message == cocoa::kPauseWatchdogFailure) {
        reason = "pause_verification_timeout";
      }
      else if (current->result.message == "The WebKit content process exited; reopen the document explicitly.") {
        reason = "content_process_terminated";
      }
      else if (current->result.message == "WKWebView could not load the admitted document.") {
        reason = "navigation_failed";
      }
      else if (current->closed) { reason = "closed"; }
      result.error = "Media test probe source changed before its reply (live=" +
          std::to_string(cocoa::live(current)) + ", ready=" +
          std::to_string(current && current->result.status == NativeViewStatus::Ready) +
          ", session_matches=" + std::to_string(current && current->resources == session) +
          ", session_active=" + std::to_string(session->active()) +
          ", navigation_matches=" +
          std::to_string(current && current->result.navigation_generation == navigation) +
          ", view_matches=" + std::to_string(current && current->view == expected_view) +
          ", status=" + std::to_string(current ? int(current->result.status) : -1) +
          ", reason=" + reason + ")";
    }
    else if (failure || ![value isKindOfClass:NSDictionary.class]) {
      result.native_pause_after = cocoa::test_pause_snapshot(current);
      result.error = "Read-only media test probe failed";
    }
    else {
      result.native_pause_after = cocoa::test_pause_snapshot(current);
      NSError *encoding_error = nil;
      NSData *data = [NSJSONSerialization dataWithJSONObject:value options:0 error:&encoding_error];
      if (encoding_error || !data || data.length > 4096) { result.error = "Invalid media test probe response"; }
      else {
        result.media.navigation_generation = navigation;
        result.ok = parse_media_snapshot(std::string_view(static_cast<const char *>(data.bytes), data.length),
                                         result.media, result.error);
      }
    }
    callback(std::move(result));
  }];
  return true;
}
}  // namespace test
#endif

}  // namespace stk::document_preview
