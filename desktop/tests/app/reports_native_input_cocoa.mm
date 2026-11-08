/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_input.hh"
#include "stk/document/resources.hh"
#include "stk/document/test_media_probe.hh"
#import <AppKit/AppKit.h>
#import <WebKit/WebKit.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <functional>
#include <limits>
#include <optional>
#include <unistd.h>
#include <utility>

namespace stk::reports_native_test {
namespace {
struct Target {
  NSWindow *parent = nil;
  NSView *content = nil;
  NSView *hit = nil;
  WKWebView *web = nil;
  NSPoint in_window{};
  NSRect pixels{};
  int width = 0, height = 0;
};

bool resolve(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
             int width, int height, double nx, double ny, Target &result, std::string &error)
{
  auto fail = [&](const char *text) { error = text; return false; };
  if (![NSThread isMainThread] || handle.kind != wm::NativeWindowKind::Cocoa || !handle.value ||
      !std::isfinite(nx) || !std::isfinite(ny) || nx < 0 || nx > 1 || ny < 0 || ny > 1) {
    return fail("Invalid Cocoa native input target/thread/coordinates");
  }
  NSWindow *parent = (__bridge NSWindow *)handle.value;
  if (![NSApp.windows containsObject:parent] || !parent.visible || parent.miniaturized || !parent.contentView) {
    return fail("Native input requires this application's visible window");
  }
  NSView *content = parent.contentView;
  const NSRect backing = [content convertRectToBacking:content.bounds];
  if (width <= 0 || height <= 0 || std::abs(backing.size.width - width) > 0.5 ||
      std::abs(backing.size.height - height) > 0.5 || bounds.x < 0 || bounds.y < 0 ||
      bounds.width <= 0 || bounds.height <= 0 || bounds.width > width - bounds.x ||
      bounds.height > height - bounds.y) {
    return fail("Cocoa native input framebuffer geometry differs");
  }
  const CGFloat top = content.isFlipped ? NSMaxY(backing) - bounds.y - bounds.height :
                                        NSMinY(backing) + bounds.y;
  const NSRect pixels = NSMakeRect(NSMinX(backing) + bounds.x, top, bounds.width, bounds.height);
  // Endpoints select the center of the first/last pixel, never the adjacent view.
  const double px = 0.5 + nx * (bounds.width - 1);
  const double py = 0.5 + ny * (bounds.height - 1);
  const NSPoint point = [content convertPointFromBacking:NSMakePoint(
      NSMinX(pixels) + px, content.isFlipped ? NSMinY(pixels) + py : NSMaxY(pixels) - py)];
  NSView *hit = [content hitTest:[content convertPoint:point toView:content.superview]];
  if (!hit || hit == content || hit.window != parent || hit.hiddenOrHasHiddenAncestor) {
    return fail("No visible native document view at the input point");
  }
  WKWebView *web = nil;
  bool reached_content = false;
  for (NSView *view = hit; view; view = view.superview) {
    if (view == content) { reached_content = true; break; }
    if ([view isKindOfClass:WKWebView.class]) { web = (WKWebView *)view; }
  }
  if (!web || !reached_content) {
    return fail("Native input target is not a WKWebView descendant of this content view");
  }
  const NSRect actual = [content convertRectToBacking:[web convertRect:web.bounds toView:content]];
  if (std::abs(NSMinX(actual) - NSMinX(pixels)) > 0.5 ||
      std::abs(NSMinY(actual) - NSMinY(pixels)) > 0.5 ||
      std::abs(actual.size.width - pixels.size.width) > 0.5 ||
      std::abs(actual.size.height - pixels.size.height) > 0.5) {
    return fail("WKWebView does not match the exact input viewport");
  }
  result = {parent, content, hit, web, [content convertPoint:point toView:nil], pixels, width, height};
  return true;
}

bool attached(const Target &target)
{
  if (![NSApp.windows containsObject:target.parent] || !target.parent.visible ||
      target.parent.miniaturized || target.parent.contentView != target.content ||
      target.hit.window != target.parent || target.hit.hiddenOrHasHiddenAncestor ||
      (target.hit != target.web && ![target.hit isDescendantOf:target.web]) ||
      ![target.web isDescendantOf:target.content]) { return false; }
  const NSRect backing = [target.content convertRectToBacking:target.content.bounds];
  const NSRect actual = [target.content convertRectToBacking:
      [target.web convertRect:target.web.bounds toView:target.content]];
  return std::abs(backing.size.width - target.width) <= 0.5 &&
         std::abs(backing.size.height - target.height) <= 0.5 &&
         std::abs(NSMinX(actual) - NSMinX(target.pixels)) <= 0.5 &&
         std::abs(NSMinY(actual) - NSMinY(target.pixels)) <= 0.5 &&
         std::abs(actual.size.width - target.pixels.size.width) <= 0.5 &&
         std::abs(actual.size.height - target.pixels.size.height) <= 0.5;
}

struct ClientSeek {
  Target target;
  wm::NativeWindowHandle handle;
  document_preview::ViewBounds bounds;
  TimelineInput input;
  std::shared_ptr<document_preview::ResourceSession> resources;
  NSRect primary_screen{};
  ax::Request request;
  std::unique_ptr<ax::ProbeProcess> process;
  std::optional<ax::ProcessResult> result;
  std::optional<document_preview::test::MediaProbeResult> media;
  TimelineObservation provider_observation;
  ax::Rect candidate;
  double minimum = 0, maximum = 0, value = 0;
  std::chrono::steady_clock::time_point began = std::chrono::steady_clock::now();
  bool public_client = false, cancelled = false, media_requested = false;
};

ax::Rect ax_rect(NSRect native, NSRect primary)
{
  return {NSMinX(native), NSMaxY(primary) - NSMaxY(native), native.size.width, native.size.height};
}
NSRect native_rect(ax::Rect value, NSRect primary)
{
  return NSMakeRect(value.x, NSMaxY(primary) - value.y - value.height, value.width, value.height);
}
bool same_native_rect(NSRect a, NSRect b)
{
  return a.origin.x == b.origin.x && a.origin.y == b.origin.y && a.size.width == b.size.width && a.size.height == b.size.height;
}
bool client_bound(const ClientSeek &state)
{
  if (!state.input.deadline.permits(std::chrono::steady_clock::now()) ||
      ![NSThread isMainThread] || !state.resources || !state.resources->active() || !attached(state.target) ||
      !NSApp.active || !state.target.parent.keyWindow || NSApp.keyWindow != state.target.parent ||
      NSScreen.screens.count == 0 || !same_native_rect(NSScreen.screens.firstObject.frame, state.primary_screen)) return false;
  std::string ignored;
  const auto current = document_preview::test::resource_session(state.handle, state.resources->identity().session_id, ignored);
  if (current != state.resources || !document_preview::test::matches_native_view(
          state.handle, state.resources->identity().session_id,
          (__bridge const void *)state.target.web, state.input.navigation_generation)) return false;
  Target target;
  if (!resolve(state.handle, state.bounds, state.target.width, state.target.height,
          state.input.left + state.input.width * .5, state.input.top + state.input.height * .5, target, ignored) ||
      target.parent != state.target.parent || target.content != state.target.content || target.web != state.target.web) return false;
  const NSRect viewport = [target.parent convertRectToScreen:[target.web convertRect:target.web.bounds toView:nil]];
  return ax::same_rect(ax_rect(target.parent.frame, state.primary_screen), state.request.window) &&
      ax::same_rect(ax_rect(viewport, state.primary_screen), state.request.viewport) &&
      state.input.deadline.permits(std::chrono::steady_clock::now());
}

bool local_click(const Target &target, double nx, double ny, std::string &delivery, std::string &error,
                 const std::function<bool()> &still_current = {})
{
  auto valid = [&] { return attached(target) && (!still_current || still_current()); };
  if (!valid()) { error = "Local click lost its frozen native owner before input"; return false; }
  const NSTimeInterval timestamp = NSProcessInfo.processInfo.systemUptime;
  NSEvent *down = [NSEvent mouseEventWithType:NSEventTypeLeftMouseDown location:target.in_window
      modifierFlags:0 timestamp:timestamp windowNumber:target.parent.windowNumber context:nil
      eventNumber:0 clickCount:1 pressure:1];
  NSEvent *up = [NSEvent mouseEventWithType:NSEventTypeLeftMouseUp location:target.in_window
      modifierFlags:0 timestamp:timestamp + .001 windowNumber:target.parent.windowNumber context:nil
      eventNumber:1 clickCount:1 pressure:0];
  if (!down || !up || down.window != target.parent || up.window != target.parent || !valid()) {
    error = "Local Cocoa mouse events lost the exact STK window"; return false;
  }
  [target.hit mouseDown:down];
  if (!valid()) { error = "Native click owner invalidated before mouseUp"; return false; }
  [target.hit mouseUp:up];
  if (!valid()) { error = "Native click owner invalidated during delivery"; return false; }
  delivery = "Cocoa local mouseDown:/mouseUp:; window=" + std::to_string(target.parent.windowNumber) +
      "; WKWebView_descendant=true; window_point=" + std::to_string(target.in_window.x) + "," +
      std::to_string(target.in_window.y) + "; normalized=" + std::to_string(nx) + "," +
      std::to_string(ny) + "; no global event post";
  return true;
}

bool key_spec(wm::Key key, unsigned short &code, NSString *__strong &characters, NSEventModifierFlags &flags)
{
  flags = 0;
  unichar character = 0;
  switch (key) {
    case wm::Key::Space: code = 0x31; character = ' '; break;
    case wm::Key::Esc: code = 0x35; character = 0x1b; break;
    case wm::Key::LeftArrow: code = 0x7b; character = NSLeftArrowFunctionKey; break;
    case wm::Key::RightArrow: code = 0x7c; character = NSRightArrowFunctionKey; break;
    case wm::Key::Home: code = 0x73; character = NSHomeFunctionKey; break;
    case wm::Key::End: code = 0x77; character = NSEndFunctionKey; break;
    default: return false;
  }
  if (key != wm::Key::Space && key != wm::Key::Esc) {
    flags = NSEventModifierFlagFunction | NSEventModifierFlagNumericPad;
  }
  characters = [NSString stringWithCharacters:&character length:1];
  return true;
}

WindowActivationObservation activation_observation(wm::NativeWindowHandle handle)
{
  WindowActivationObservation observed;
  observed.main_thread = [NSThread isMainThread];
  observed.valid_target = handle.kind == wm::NativeWindowKind::Cocoa && handle.value;
  if (!observed.main_thread) { return observed; }
  observed.policy = NSApp ? static_cast<int>([NSApp activationPolicy]) : -1;
  observed.app_active = NSApp.active;
  if (!observed.valid_target) { return observed; }
  NSWindow *parent = (__bridge NSWindow *)handle.value;
  observed.own_window = [NSApp.windows containsObject:parent];
  if (!observed.own_window) { return observed; }
  observed.window_key = parent.keyWindow;
  observed.exact_key_window = NSApp.keyWindow == parent;
  observed.visible = parent.visible;
  observed.miniaturized = parent.miniaturized;
  observed.can_become_key = parent.canBecomeKeyWindow;
  return observed;
}

// WebKit's public accessibility wrappers still implement the attribute-based
// API. Read only named structural/numeric attributes, never labels, URLs, text,
// actions or setters. The root is the exact WKWebView verified by resolve().
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
id ax_attribute(id element, NSString *attribute)
{
  id value = [element respondsToSelector:@selector(accessibilityAttributeValue:)] ?
      [element accessibilityAttributeValue:attribute] : nil;
  if (value) { return value; }
  if ([attribute isEqualToString:NSAccessibilityRoleAttribute] &&
      [element respondsToSelector:@selector(accessibilityRole)]) { return [element accessibilityRole]; }
  if ([attribute isEqualToString:NSAccessibilityChildrenAttribute] &&
      [element respondsToSelector:@selector(accessibilityChildren)]) { return [element accessibilityChildren]; }
  if ([attribute isEqualToString:NSAccessibilityEnabledAttribute] &&
      [element respondsToSelector:@selector(isAccessibilityEnabled)]) { return @([element isAccessibilityEnabled]); }
  if ([attribute isEqualToString:NSAccessibilityMinValueAttribute] &&
      [element respondsToSelector:@selector(accessibilityMinValue)]) { return [element accessibilityMinValue]; }
  if ([attribute isEqualToString:NSAccessibilityMaxValueAttribute] &&
      [element respondsToSelector:@selector(accessibilityMaxValue)]) { return [element accessibilityMaxValue]; }
  if ([attribute isEqualToString:NSAccessibilityValueAttribute] &&
      [element respondsToSelector:@selector(accessibilityValue)]) { return [element accessibilityValue]; }
  return nil;
}

bool ax_number(id element, NSString *attribute, double &value)
{
  id number = ax_attribute(element, attribute);
  if (![number isKindOfClass:NSNumber.class]) { return false; }
  value = [number doubleValue];
  return std::isfinite(value);
}

NSRect ax_frame(id element)
{
  if ([element respondsToSelector:@selector(accessibilityFrame)]) {
    const NSRect frame = [element accessibilityFrame];
    if (std::isfinite(frame.origin.x) && std::isfinite(frame.origin.y) &&
        std::isfinite(frame.size.width) && std::isfinite(frame.size.height) &&
        frame.size.width > 0 && frame.size.height > 0) { return frame; }
  }
  // AppKit NSAccessibilityPositionAttribute is the lower-left screen-relative
  // point, in points: the same coordinates as accessibilityFrame/NSWindow,
  // not the separate AXUIElement API's top-left coordinate convention.
  id position = ax_attribute(element, NSAccessibilityPositionAttribute);
  id size = ax_attribute(element, NSAccessibilitySizeAttribute);
  if (![position isKindOfClass:NSValue.class] || ![size isKindOfClass:NSValue.class] ||
      std::strcmp([position objCType], @encode(NSPoint)) ||
      std::strcmp([size objCType], @encode(NSSize))) { return NSZeroRect; }
  return {[position pointValue], [size sizeValue]};
}

// Diagnostic reads never supply children/roles to the acceptance traversal.
// They query only the already visited node in this exact own-WKWebView tree.
std::string diagnostic_role(id value)
{
  if (!value) { return "nil"; }
  if (![value isKindOfClass:NSString.class]) { return "other-type"; }
  if ([value isEqualToString:NSAccessibilitySliderRole]) { return "slider"; }
  if ([value isEqualToString:@"AXWebArea"]) { return "webarea"; }
  if ([value isEqualToString:NSAccessibilityGroupRole]) { return "group"; }
  if ([value isEqualToString:NSAccessibilityScrollAreaRole]) { return "scrollarea"; }
  return "other";
}

TimelineChildListObservation diagnostic_children(id value)
{
  if (!value) { return {"nil", 0, false}; }
  if (![value isKindOfClass:NSArray.class]) { return {"other", 0, false}; }
  const NSUInteger count = [value count];
  return {"array", int(std::min(count, NSUInteger(257))), count > 256};
}

// Capture only values already selected by the original walk. The local array
// owns at most 32 visited nodes until this lookup returns; Observation has no id.
void record_node(id element, id role, NSArray *selected, NSUInteger depth,
                 bool paged_count_observed, NSUInteger paged_count,
                 std::chrono::steady_clock::time_point began, NSMutableArray *retained,
                 TimelineObservation &observed)
{
  if (observed.nodes.size() >= 32) { observed.diagnostics_truncated = true; return; }
  TimelineNodeObservation node;
  node.ordinal = int(observed.nodes.size()) + 1; node.depth = int(depth);
  node.elapsed_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - began).count();
  node.paged_count_observed = paged_count_observed;
  node.paged_count = int(std::min(paged_count, NSUInteger(257)));
  node.paged_count_over_budget = paged_count > 256;
  node.selected_role = diagnostic_role(role);
  node.selected_children = diagnostic_children(selected);
  [retained addObject:element];
  observed.nodes.push_back(std::move(node));
}

// Only a completed, unsuccessful original lookup may query alternate getters.
// They never replace/merge the selected tree or change its error/candidates.
void diagnose_failed_nodes(NSArray *retained, TimelineObservation &observed)
{
  const auto began = std::chrono::steady_clock::now();
  auto budget = [&] {
    const auto elapsed = std::chrono::steady_clock::now() - began;
    observed.diagnostic_elapsed_ms = std::chrono::duration<double, std::milli>(elapsed).count();
    if (elapsed > std::chrono::seconds(2)) {
      observed.diagnostics_timeout = true; observed.diagnostics_truncated = true; return false;
    }
    return true;
  };
  for (NSUInteger index = 0; index < retained.count && index < observed.nodes.size(); ++index) {
    if (!budget()) { return; }
    id element = retained[index];
    auto &node = observed.nodes[index];
    node.extra_getters_started = true;
    @try {
      // Fixed class categories only; no arbitrary class names are serialized.
      Class remote = NSClassFromString(@"NSAccessibilityRemoteUIElement");
      if ([element isKindOfClass:WKWebView.class]) { node.category = "webview"; }
      else if (remote && [element isKindOfClass:remote]) { node.category = "remote"; }
      node.legacy_selector = [element respondsToSelector:@selector(accessibilityAttributeValue:)];
      node.modern_children_selector = [element respondsToSelector:@selector(accessibilityChildren)];
      node.modern_role_selector = [element respondsToSelector:@selector(accessibilityRole)];
      node.paged_count_selector = [element respondsToSelector:@selector(accessibilityArrayAttributeCount:)];
      node.paged_values_selector = [element respondsToSelector:@selector(accessibilityArrayAttributeValues:index:maxCount:)];
      if (node.legacy_selector) {
        if (!budget()) { return; }
        @try { node.legacy_children = diagnostic_children([element accessibilityAttributeValue:NSAccessibilityChildrenAttribute]); }
        @catch (NSException *exception) { (void)exception; node.legacy_children.type = "exception"; }
        if (!budget()) { return; }
        @try { node.legacy_role = diagnostic_role([element accessibilityAttributeValue:NSAccessibilityRoleAttribute]); }
        @catch (NSException *exception) { (void)exception; node.legacy_role = "exception"; }
      }
      if (node.modern_children_selector) {
        if (!budget()) { return; }
        @try { node.modern_children = diagnostic_children([element accessibilityChildren]); }
        @catch (NSException *exception) { (void)exception; node.modern_children.type = "exception"; }
      }
      if (node.modern_role_selector) {
        if (!budget()) { return; }
        @try { node.modern_role = diagnostic_role([element accessibilityRole]); }
        @catch (NSException *exception) { (void)exception; node.modern_role = "exception"; }
      }
      if (!budget()) { return; }
      node.extra_getters_complete = true;
    }
    @catch (NSException *exception) { (void)exception; node.diagnostic_exception = true; }
  }
  budget();
}

bool timeline(const Target &target, const TimelineInput &input, NSRect video,
              TimelineObservation &observed, NSRect &found, std::string &error)
{
  constexpr NSUInteger node_limit = 256, depth_limit = 16;
  NSMutableArray *pending = [NSMutableArray arrayWithObject:target.web];
  NSMutableArray<NSNumber *> *depths = [NSMutableArray arrayWithObject:@0];
  NSHashTable *seen = [NSHashTable hashTableWithOptions:NSPointerFunctionsObjectPointerPersonality];
  // This target is built with -fobjc-arc. This owned local container is
  // cleared before normal return; ARC also releases it on early errors.
  // No retained AX object escapes into Observation, logs or persistent state.
  NSMutableArray *diagnostic_nodes = [[NSMutableArray alloc] initWithCapacity:32];
  const auto began = std::chrono::steady_clock::now();
  struct Elapsed {
    TimelineObservation &observed;
    std::chrono::steady_clock::time_point began;
    ~Elapsed() { if (!observed.lookup_complete) {
      observed.elapsed_ms = std::chrono::duration<double, std::milli>(
          std::chrono::steady_clock::now() - began).count();
    } }
  } elapsed{observed, began};
  while (pending.count) {
    if (std::chrono::steady_clock::now() - began > std::chrono::seconds(2)) {
      error = "Bounded own-WKWebView accessibility lookup expired"; return false;
    }
    id element = pending.lastObject;
    const NSUInteger depth = depths.lastObject.unsignedIntegerValue;
    [pending removeLastObject]; [depths removeLastObject];
    if ([seen containsObject:element]) { continue; }
    if (seen.count >= node_limit || depth > depth_limit) {
      error = "Own-WKWebView accessibility subtree exceeds the node/depth bound"; return false;
    }
    [seen addObject:element];
    ++observed.visited_nodes;
    observed.deepest_node = std::max(observed.deepest_node, int(depth));
    id role = ax_attribute(element, NSAccessibilityRoleAttribute);
    if ([role isKindOfClass:NSString.class] && [role isEqualToString:NSAccessibilitySliderRole]) {
      ++observed.sliders;
      const NSRect frame = ax_frame(element);
      double minimum = 0, maximum = 0, value = 0;
      id enabled = ax_attribute(element, NSAccessibilityEnabledAttribute);
      // A unique horizontal range must lie wholly in this observed video and
      // report the paused DOM time. Volume or another document slider cannot
      // qualify merely because it has the same accessibility role.
      if ([enabled isKindOfClass:NSNumber.class] && [enabled boolValue] &&
          std::isfinite(frame.origin.x) && std::isfinite(frame.origin.y) &&
          std::isfinite(frame.size.width) && std::isfinite(frame.size.height) &&
          frame.size.width >= video.size.width * 0.20 && frame.size.height >= 2 &&
          frame.size.width >= frame.size.height * 4 && NSContainsRect(video, frame) &&
          ax_number(element, NSAccessibilityMinValueAttribute, minimum) &&
          ax_number(element, NSAccessibilityMaxValueAttribute, maximum) &&
          ax_number(element, NSAccessibilityValueAttribute, value) && maximum > minimum &&
          value >= minimum && value <= maximum &&
          std::abs((value - minimum) / (maximum - minimum) - input.current_time / input.duration) <=
              0.01 + 0.10 / input.duration) {
        ++observed.candidates; found = frame;
        observed.screen_x = frame.origin.x; observed.screen_y = frame.origin.y;
        observed.screen_width = frame.size.width; observed.screen_height = frame.size.height;
        observed.minimum = minimum; observed.maximum = maximum; observed.value = value;
      }
    }
    NSArray *children = nil;
    bool paged_count_observed = false;
    NSUInteger paged_count = 0;
    if ([element respondsToSelector:@selector(accessibilityArrayAttributeCount:)] &&
        [element respondsToSelector:@selector(accessibilityArrayAttributeValues:index:maxCount:)]) {
      const NSUInteger count = [element accessibilityArrayAttributeCount:NSAccessibilityChildrenAttribute];
      paged_count_observed = true; paged_count = count;
      if (count > node_limit - seen.count || pending.count > node_limit - seen.count - count) {
        error = "Own-WKWebView accessibility children exceed the remaining node budget"; return false;
      }
      if (count) {
        children = [element accessibilityArrayAttributeValues:NSAccessibilityChildrenAttribute
            index:0 maxCount:count];
        if (![children isKindOfClass:NSArray.class] || children.count != count) {
          error = "Own-WKWebView accessibility child page changed during lookup"; return false;
        }
      }
      else { children = ax_attribute(element, NSAccessibilityChildrenAttribute); }
    }
    else {
      id value = ax_attribute(element, NSAccessibilityChildrenAttribute);
      if (value && ![value isKindOfClass:NSArray.class]) {
        error = "Own-WKWebView accessibility children are not an array"; return false;
      }
      children = value;
    }
    if (children && ![children isKindOfClass:NSArray.class]) {
      error = "Own-WKWebView accessibility children are not an array"; return false;
    }
    if (children.count > node_limit - seen.count ||
        pending.count > node_limit - seen.count - children.count) {
      error = "Own-WKWebView accessibility children exceed the remaining node budget"; return false;
    }
    if (children.count && depth == depth_limit) {
      error = "Own-WKWebView accessibility children exceed the depth budget"; return false;
    }
    // The original child list and candidate decision above are unchanged.
    // Diagnostics do not merge, replace or descend any alternative child list.
    record_node(element, role, children, depth, paged_count_observed, paged_count, began, diagnostic_nodes, observed);
    for (id child in children) { [pending addObject:child]; [depths addObject:@(depth + 1)]; }
  }
  observed.lookup_complete = true;
  observed.elapsed_ms = std::chrono::duration<double, std::milli>(
      std::chrono::steady_clock::now() - began).count();
  if (observed.candidates != 1) {
    error = "Own-WKWebView must expose exactly one time-matched horizontal video slider";
    diagnose_failed_nodes(diagnostic_nodes, observed);
    diagnostic_nodes = nil;
    return false;
  }
  diagnostic_nodes = nil;
  return true;
}
#pragma clang diagnostic pop
}  // namespace

bool NativeInput::request_window_activation(wm::NativeWindowHandle handle,
                                            WindowActivationRequest &request, std::string &error)
{
  error.clear();
  request = {};
  request.before = activation_observation(handle);
  request.after = request.before;
  if (!request.before.main_thread || !request.before.valid_target) {
    error = "Invalid Cocoa activation target/thread"; return false;
  }
  if (!request.before.own_window || !request.before.visible || request.before.miniaturized) {
    error = "Activation requires this application's visible window"; return false;
  }
  NSWindow *parent = (__bridge NSWindow *)handle.value;
  // This unbundled acceptance executable has no app Info.plist. Make its GUI
  // activation policy explicit before requesting focus; this does not prove focus.
  request.policy_change_attempted = true;
  request.policy_change_succeeded = [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
  request.after = activation_observation(handle);
  request.policy_after_change = request.after.policy;
  if (!request.policy_change_succeeded ||
      request.policy_after_change != static_cast<int>(NSApplicationActivationPolicyRegular)) {
    error = "Cocoa test host could not adopt the regular activation policy"; return false;
  }
  if (!request.after.own_window || !request.after.visible || request.after.miniaturized) {
    error = "Activation policy change lost this application's visible window"; return false;
  }
  // Direct view mouseDown:/mouseUp: calls do not perform the normal window
  // activation that precedes a physical click. Make that test setup explicit.
  [NSApp activateIgnoringOtherApps:YES];
  [parent makeKeyAndOrderFront:nil];
  request.activation_requested = true;
  request.after = activation_observation(handle);
  return true; // Request only; window_is_active must independently confirm it.
}

bool NativeInput::window_is_active(wm::NativeWindowHandle handle,
                                  WindowActivationObservation &observation, std::string &error)
{
  error.clear();
  observation = activation_observation(handle);
  if (!observation.main_thread || !observation.valid_target) {
    error = "Invalid Cocoa activation observation target/thread"; return false;
  }
  if (!observation.own_window || !observation.visible || observation.miniaturized) {
    error = "Activation observation lost this application's visible window"; return false;
  }
  NSWindow *parent = (__bridge NSWindow *)handle.value;
  return NSApp.active && parent.keyWindow && NSApp.keyWindow == parent;
}

bool NativeInput::prepare_seek(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                               int width, int height, const TimelineInput &input,
                               std::shared_ptr<document_preview::ResourceSession> resources,
                               bool public_client, std::string &error)
{
  error.clear();
  if (client_seek_ || !child_cleanup_confirmed_ || !resources || !resources->active() || bounds.width <= 1 || bounds.height <= 1 ||
      !std::isfinite(input.target_fraction) || input.target_fraction <= 0 || input.target_fraction >= 1 ||
      input.viewport_generation == std::numeric_limits<uint64_t>::max() ||
      seek_generation_ == std::numeric_limits<uint64_t>::max()) {
    error = "Invalid or overlapping public AX test seek"; return false;
  }
  auto state = std::make_shared<ClientSeek>();
  state->handle = handle; state->bounds = bounds; state->input = input; state->resources = std::move(resources);
  if (!resolve(handle, bounds, width, height, input.left + input.width * .5, input.top + input.height * .5, state->target, error)) return false;
  if (NSScreen.screens.count == 0) { error = "No primary screen for exact AX point conversion"; return false; }
  state->primary_screen = NSScreen.screens.firstObject.frame;
  if (NSMinX(state->primary_screen) != 0 || NSMinY(state->primary_screen) != 0) {
    error = "Unsupported primary screen origin for exact AX conversion"; return false;
  }
  const auto &target = state->target;
  const NSRect viewport = [target.parent convertRectToScreen:[target.web convertRect:target.web.bounds toView:nil]];
  const NSRect pixels = NSMakeRect(NSMinX(target.pixels) + input.left * bounds.width,
      target.content.isFlipped ? NSMinY(target.pixels) + input.top * bounds.height :
          NSMaxY(target.pixels) - (input.top + input.height) * bounds.height,
      input.width * bounds.width, input.height * bounds.height);
  const NSRect video = [target.parent convertRectToScreen:[target.content convertRect:
      [target.content convertRectFromBacking:pixels] toView:nil]];
  state->request.parent_pid = uint64_t(getpid());
  state->request.request_generation = ++seek_generation_;
  state->request.viewport_generation = input.viewport_generation; // Screen invalidation generation, frozen by the UI owner.
  state->request.navigation_generation = input.navigation_generation;
  state->request.window = ax_rect(target.parent.frame, state->primary_screen);
  state->request.viewport = ax_rect(viewport, state->primary_screen);
  state->request.video = ax_rect(video, state->primary_screen);
  state->request.current_time = input.current_time; state->request.duration = input.duration;
  if (!ax::valid_request(state->request) || !client_bound(*state)) {
    error = "Public AX test request lost the exact window, viewport or resource session"; return false;
  }
#ifdef STK_REPORTS_NATIVE_AX_HELPER
  // Only numeric request/process state reaches the worker. All AppKit/resource objects remain in this UI-owned state.
  state->public_client = public_client;
  if (public_client) state->process = std::make_unique<ax::ProbeProcess>(STK_REPORTS_NATIVE_AX_HELPER, state->request);
  client_seek_ = state;
  return true;
#else
  error = "The macOS public AX test helper was not built"; return false;
#endif
}

bool NativeInput::begin_client_seek(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                                    int width, int height, const TimelineInput &input,
                                    std::shared_ptr<document_preview::ResourceSession> resources,
                                    std::string &error)
{
  return prepare_seek(handle, bounds, width, height, input, std::move(resources), true, error);
}

void NativeInput::cancel_seek() noexcept
{
  if (const auto state = std::static_pointer_cast<ClientSeek>(client_seek_)) {
    state->cancelled = true;
    if (state->process) state->process->cancel(); // No join/wait. poll_seek observes cleanup while the caller pumps UI.
  }
}

std::optional<ax::ProcessResult> NativeInput::poll_cancelled_seek() noexcept
{
  const auto state = std::static_pointer_cast<ClientSeek>(client_seek_);
  ax::ProcessResult result; result.status = ax::ProcessStatus::Cancelled;
  if (!state) return result;
  cancel_seek();
  if (state->process) {
    const auto value = state->process->poll();
    if (!value) return std::nullopt;
    result = *value;
    if (result.child_pid > 0 && !result.reaped) child_cleanup_confirmed_ = false;
  }
  client_seek_.reset(); // Every actual worker is finished; no Cocoa owner is dropped ahead of its child cleanup.
  return result;
}

TimelinePoll NativeInput::poll_seek(TimelineObservation &observation, std::string &delivery, std::string &error)
{
  observation = {}; delivery.clear(); error.clear();
  const auto state = std::static_pointer_cast<ClientSeek>(client_seek_);
  if (!state || ![NSThread isMainThread]) { error = "No UI-owned AX seek"; return TimelinePoll::Failed; }
  observation = state->provider_observation;
  observation.public_client_attempted = state->public_client;
  auto fail = [&](const char *message) {
    error = message; client_seek_.reset(); return TimelinePoll::Failed;
  };
  if (!state->cancelled && (!client_bound(*state) ||
      std::chrono::steady_clock::now() - state->began >= std::chrono::seconds(4))) {
    state->cancelled = true;
    if (state->process) state->process->cancel();
  }
  if (state->public_client) {
    if (!state->result) state->result = state->process->poll();
    if (!state->input.deadline.permits(std::chrono::steady_clock::now())) {
      state->cancelled = true;
      state->process->cancel();
    }
    // A stale/cancelled client remains pending until the worker has completed owned-child cleanup.
    if (!state->result) return TimelinePoll::Pending;
    observation.public_client = *state->result;
    const auto &result = *state->result;
    if (result.child_pid > 0 && !result.reaped) child_cleanup_confirmed_ = false;
    const auto &response = result.response;
    observation.visited_nodes = int(response.nodes); observation.deepest_node = int(response.deepest);
    observation.sliders = int(response.sliders); observation.candidates = int(response.candidates);
    observation.lookup_complete = response.status == ax::Status::Success || response.reason == ax::Reason::NoSlider ||
        response.reason == ax::Reason::MultipleSliders;
    if (state->cancelled) return fail("AX seek cancelled after owner, layout or session invalidation");
    if (result.status != ax::ProcessStatus::Response || !result.reaped || !ax::accepted(state->request, response))
      return fail("Public AX client did not prove one time-matched slider in the exact own viewport");
    state->candidate = response.slider; state->minimum = response.minimum;
    state->maximum = response.maximum; state->value = response.value;
  }
  if (state->cancelled || !state->input.deadline.permits(std::chrono::steady_clock::now()))
    return fail("AX seek cancelled or expired before consuming its result");
  observation.elapsed_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - state->began).count();
  if (!state->media_requested) {
    state->media_requested = true;
    const std::weak_ptr<ClientSeek> weak = state;
    std::string ignored;
    if (!document_preview::test::probe_media(state->handle, state->resources->identity().session_id,
        [weak](document_preview::test::MediaProbeResult value) {
          if (const auto current = weak.lock()) current->media = std::move(value);
        }, ignored)) return fail("AX seek could not revalidate its native media session");
    return TimelinePoll::Pending;
  }
  if (!state->media) return TimelinePoll::Pending;
  const auto &media = state->media->media;
  if (!state->media->ok || !client_bound(*state) || media.navigation_generation != state->input.navigation_generation ||
      !media.paused || media.ended || media.seeking || media.error_code || !media.duration_known ||
      media.duration != state->input.duration || std::abs(media.current_time - state->input.current_time) > .10 ||
      media.viewport_width <= 0 || media.viewport_height <= 0 ||
      media.rect_x / media.viewport_width != state->input.left || media.rect_y / media.viewport_height != state->input.top ||
      media.rect_width / media.viewport_width != state->input.width || media.rect_height / media.viewport_height != state->input.height)
    return fail("AX seek media/navigation changed before native input");
  auto fresh = state->request; fresh.current_time = media.current_time; fresh.duration = media.duration;
  if (!ax::matching_slider(fresh, state->candidate, state->minimum, state->maximum, state->value))
    return fail("AX slider no longer matches the freshly paused media time");
  const NSRect slider = native_rect(state->candidate, state->primary_screen);
  const NSPoint screen = NSMakePoint(NSMinX(slider) + slider.size.width * state->input.target_fraction, NSMidY(slider));
  const auto &target = state->target;
  const NSPoint point = [target.content convertPointToBacking:[target.content convertPoint:
      [target.parent convertPointFromScreen:screen] fromView:nil]];
  observation.screen_x = slider.origin.x; observation.screen_y = slider.origin.y;
  observation.screen_width = slider.size.width; observation.screen_height = slider.size.height;
  observation.minimum = state->minimum; observation.maximum = state->maximum; observation.value = state->value;
  observation.normalized_x = (point.x - NSMinX(target.pixels) - .5) / (state->bounds.width - 1);
  observation.normalized_y = ((target.content.isFlipped ? point.y - NSMinY(target.pixels) : NSMaxY(target.pixels) - point.y) - .5) /
      (state->bounds.height - 1);
  if (state->cancelled || !client_bound(*state)) return fail("AX seek detached immediately before native click");
  Target clicked;
  if (!resolve(state->handle, state->bounds, target.width, target.height, observation.normalized_x,
      observation.normalized_y, clicked, error) || clicked.web != target.web || clicked.parent != target.parent ||
      clicked.content != target.content) return fail("AX seek click target differs from its frozen native view");
  observation.public_client_revalidated = state->public_client;
  if (!local_click(clicked, observation.normalized_x, observation.normalized_y, delivery, error,
      [&] { return !state->cancelled && client_bound(*state); })) {
    client_seek_.reset(); return TimelinePoll::Failed;
  }
  delivery += state->public_client ? "; public own-parent AX child; numeric DTO; session/navigation revalidated" :
      "; unique provider AX slider; session/navigation revalidated";
  client_seek_.reset(); return TimelinePoll::Delivered;
}

bool NativeInput::begin_provider_seek(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                                     int width, int height, const TimelineInput &input,
                                     std::shared_ptr<document_preview::ResourceSession> resources,
                                     TimelineObservation &observation, std::string &error)
{
  observation = {}; error.clear();
  if (!prepare_seek(handle, bounds, width, height, input, std::move(resources), false, error)) return false;
  const auto state = std::static_pointer_cast<ClientSeek>(client_seek_);
  NSRect slider = NSZeroRect;
  bool found = false;
  @try { found = timeline(state->target, input, native_rect(state->request.video, state->primary_screen), observation, slider, error); }
  @catch (NSException *exception) { (void)exception; error = "Own-WKWebView accessibility lookup failed"; }
  if (!input.deadline.permits(std::chrono::steady_clock::now())) {
    error = "Provider AX query crossed the original seek deadline";
    client_seek_.reset(); return false;
  }
  if (!found || state->cancelled || !client_bound(*state)) {
    if (found) error = "Provider AX target invalidated during lookup";
    client_seek_.reset(); return false;
  }
  state->candidate = ax_rect(slider, state->primary_screen);
  state->minimum = observation.minimum; state->maximum = observation.maximum; state->value = observation.value;
  state->provider_observation = observation;
  return true; // Candidate only: poll_seek must revalidate native media before delivering any input.
}

bool NativeInput::click_document(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                                int width, int height, double nx, double ny,
                                std::string &delivery, std::string &error)
{
  delivery.clear(); error.clear();
  Target target;
  if (!resolve(handle, bounds, width, height, nx, ny, target, error)) return false;
  return local_click(target, nx, ny, delivery, error);
}

bool NativeInput::key_document(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                              int width, int height, wm::Key key,
                              std::string &delivery, std::string &error)
{
  delivery.clear(); error.clear();
  unsigned short code = 0;
  NSString *characters = nil;
  NSEventModifierFlags flags = 0;
  if (!key_spec(key, code, characters, flags)) { error = "Unsupported native report test key"; return false; }
  Target target;
  if (!resolve(handle, bounds, width, height, 0.5, 0.5, target, error)) { return false; }
  if (!target.parent.keyWindow) { error = "Native key delivery requires the exact STK key window"; return false; }
  NSResponder *responder = target.parent.firstResponder;
  if (![responder isKindOfClass:NSView.class] ||
      (responder != target.web && ![(NSView *)responder isDescendantOf:target.web])) {
    if (![target.parent makeFirstResponder:target.web]) {
      error = "Cannot focus the exact native document view";
      return false;
    }
    responder = target.parent.firstResponder;
  }
  if (![responder isKindOfClass:NSView.class] ||
      (responder != target.web && ![(NSView *)responder isDescendantOf:target.web])) {
    error = "Native key focus escaped the exact WKWebView";
    return false;
  }
  const NSTimeInterval timestamp = NSProcessInfo.processInfo.systemUptime;
  NSEvent *down = [NSEvent keyEventWithType:NSEventTypeKeyDown location:target.in_window modifierFlags:flags
      timestamp:timestamp windowNumber:target.parent.windowNumber context:nil characters:characters
      charactersIgnoringModifiers:characters isARepeat:NO keyCode:code];
  NSEvent *up = [NSEvent keyEventWithType:NSEventTypeKeyUp location:target.in_window modifierFlags:flags
      timestamp:timestamp + 0.001 windowNumber:target.parent.windowNumber context:nil characters:characters
      charactersIgnoringModifiers:characters isARepeat:NO keyCode:code];
  if (!down || !up || down.window != target.parent || up.window != target.parent || !attached(target)) {
    error = "Local Cocoa key events lost their exact STK document target";
    return false;
  }
  [responder keyDown:down];
  if (!attached(target) || target.parent.firstResponder != responder) {
    error = "Native key target changed before keyUp";
    return false;
  }
  [responder keyUp:up];
  if (!attached(target)) { error = "Native key target detached during delivery"; return false; }
  delivery = "Cocoa local keyDown:/keyUp:; window=" + std::to_string(target.parent.windowNumber) +
      "; focused_WKWebView_descendant=true; key=" + std::to_string(static_cast<int>(key)) +
      "; native_keycode=" + std::to_string(code) + "; no global event post";
  return true;
}
}  // namespace stk::reports_native_test
