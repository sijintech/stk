/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_input.hh"
#import <AppKit/AppKit.h>
#import <WebKit/WebKit.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>

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

bool timeline(const Target &target, const TimelineInput &input, NSRect video,
              TimelineObservation &observed, NSRect &found, std::string &error)
{
  constexpr NSUInteger node_limit = 256, depth_limit = 16;
  NSMutableArray *pending = [NSMutableArray arrayWithObject:target.web];
  NSMutableArray<NSNumber *> *depths = [NSMutableArray arrayWithObject:@0];
  NSHashTable *seen = [NSHashTable hashTableWithOptions:NSPointerFunctionsObjectPointerPersonality];
  const auto began = std::chrono::steady_clock::now();
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
    if ([element respondsToSelector:@selector(accessibilityArrayAttributeCount:)] &&
        [element respondsToSelector:@selector(accessibilityArrayAttributeValues:index:maxCount:)]) {
      const NSUInteger count = [element accessibilityArrayAttributeCount:NSAccessibilityChildrenAttribute];
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
    for (id child in children) { [pending addObject:child]; [depths addObject:@(depth + 1)]; }
  }
  observed.lookup_complete = true;
  if (observed.candidates != 1) {
    error = "Own-WKWebView must expose exactly one time-matched horizontal video slider";
    return false;
  }
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

bool NativeInput::seek_document(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                               int width, int height, const TimelineInput &input,
                               TimelineObservation &observation, std::string &delivery, std::string &error)
{
  observation = {}; delivery.clear(); error.clear();
  if (!std::isfinite(input.left) || !std::isfinite(input.top) || !std::isfinite(input.width) ||
      !std::isfinite(input.height) || !std::isfinite(input.current_time) || !std::isfinite(input.duration) ||
      !std::isfinite(input.target_fraction) || input.left < 0 || input.top < 0 ||
      input.width <= 0 || input.height <= 0 || input.left + input.width > 1 || input.top + input.height > 1 ||
      input.duration <= 0 || input.current_time < 0 || input.current_time >= input.duration ||
      input.target_fraction <= 0 || input.target_fraction >= 1 || bounds.width <= 1 || bounds.height <= 1) {
    error = "Invalid bounded native timeline input"; return false;
  }
  Target target;
  if (!resolve(handle, bounds, width, height, input.left + input.width * 0.5,
          input.top + input.height * 0.5, target, error)) { return false; }
  if (!NSApp.active || !target.parent.keyWindow || NSApp.keyWindow != target.parent) {
    error = "Timeline input requires this application's exact active key window"; return false;
  }
  const NSRect pixels = NSMakeRect(NSMinX(target.pixels) + input.left * bounds.width,
      target.content.isFlipped ? NSMinY(target.pixels) + input.top * bounds.height :
          NSMaxY(target.pixels) - (input.top + input.height) * bounds.height,
      input.width * bounds.width, input.height * bounds.height);
  const NSRect video = [target.parent convertRectToScreen:[target.content convertRect:
      [target.content convertRectFromBacking:pixels] toView:nil]];
  NSRect slider = NSZeroRect;
  @try {
    if (!timeline(target, input, video, observation, slider, error)) { return false; }
  }
  @catch (NSException *exception) {
    (void)exception;
    error = "Own-WKWebView accessibility lookup failed"; return false;
  }
  if (!attached(target)) { error = "Native timeline target detached during lookup"; return false; }
  const NSPoint screen = NSMakePoint(NSMinX(slider) + slider.size.width * input.target_fraction,
                                     NSMidY(slider));
  const NSPoint point = [target.content convertPointToBacking:[target.content convertPoint:
      [target.parent convertPointFromScreen:screen] fromView:nil]];
  observation.normalized_x = (point.x - NSMinX(target.pixels) - 0.5) / (bounds.width - 1);
  observation.normalized_y = ((target.content.isFlipped ? point.y - NSMinY(target.pixels) :
      NSMaxY(target.pixels) - point.y) - 0.5) / (bounds.height - 1);
  if (!click_document(handle, bounds, width, height, observation.normalized_x,
          observation.normalized_y, delivery, error)) { return false; }
  delivery += "; unique read-only AX time-slider geometry; no AX action/setter or DOM mutation";
  return true;
}

bool NativeInput::click_document(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                                int width, int height, double nx, double ny,
                                std::string &delivery, std::string &error)
{
  delivery.clear(); error.clear();
  Target target;
  if (!resolve(handle, bounds, width, height, nx, ny, target, error)) { return false; }
  const NSTimeInterval timestamp = NSProcessInfo.processInfo.systemUptime;
  NSEvent *down = [NSEvent mouseEventWithType:NSEventTypeLeftMouseDown location:target.in_window
      modifierFlags:0 timestamp:timestamp windowNumber:target.parent.windowNumber context:nil
      eventNumber:0 clickCount:1 pressure:1];
  NSEvent *up = [NSEvent mouseEventWithType:NSEventTypeLeftMouseUp location:target.in_window
      modifierFlags:0 timestamp:timestamp + 0.001 windowNumber:target.parent.windowNumber context:nil
      eventNumber:1 clickCount:1 pressure:0];
  if (!down || !up || down.window != target.parent || up.window != target.parent) {
    error = "Local Cocoa mouse events did not retain the exact STK window";
    return false;
  }
  [target.hit mouseDown:down];
  if (!attached(target)) { error = "Native click target detached before mouseUp"; return false; }
  [target.hit mouseUp:up];
  if (!attached(target)) { error = "Native click target detached during delivery"; return false; }
  delivery = "Cocoa local mouseDown:/mouseUp:; window=" + std::to_string(target.parent.windowNumber) +
      "; WKWebView_descendant=true; window_point=" + std::to_string(target.in_window.x) + "," +
      std::to_string(target.in_window.y) + "; normalized=" + std::to_string(nx) + "," +
      std::to_string(ny) + "; no global event post";
  return true;
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
