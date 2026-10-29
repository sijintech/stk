/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_scroll.hh"
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <WebKit/WebKit.h>
#include <cmath>

namespace stk::reports_native_test {
struct ScrollGuard::Impl {};
ScrollGuard::ScrollGuard() = default;
ScrollGuard::~ScrollGuard() = default;
bool ScrollGuard::check(std::string &error) const { error.clear(); return true; }
bool ScrollGuard::scroll_document(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                     int framebuffer_width, int framebuffer_height, int direction,
                     std::string &delivery, std::string &error)
{
  delivery.clear(); error.clear();
  auto fail = [&](const char *text) { error = text; return false; };
  if (![NSThread isMainThread] || handle.kind != wm::NativeWindowKind::Cocoa || !handle.value ||
      (direction != -1 && direction != 1)) { return fail("Invalid Cocoa wheel target/thread"); }
  NSWindow *parent = (__bridge NSWindow *)handle.value;
  if (![NSApp.windows containsObject:parent] || !parent.visible || parent.miniaturized || !parent.contentView) {
    return fail("Wheel delivery requires this application's visible window");
  }
  NSView *content = parent.contentView;
  const NSRect backing = [content convertRectToBacking:content.bounds];
  if (std::abs(backing.size.width - framebuffer_width) > 0.5 ||
      std::abs(backing.size.height - framebuffer_height) > 0.5 || bounds.x < 0 || bounds.y < 0 ||
      bounds.width <= 0 || bounds.height <= 0 || bounds.width > framebuffer_width - bounds.x ||
      bounds.height > framebuffer_height - bounds.y) { return fail("Cocoa wheel framebuffer geometry differs"); }
  const CGFloat y = content.isFlipped ? NSMaxY(backing) - bounds.y - bounds.height : NSMinY(backing) + bounds.y;
  const NSRect pixels = NSMakeRect(NSMinX(backing) + bounds.x, y, bounds.width, bounds.height);
  const NSRect frame = [content convertRectFromBacking:pixels];
  const NSPoint point = NSMakePoint(NSMidX(frame), NSMidY(frame));
  // hitTest expects a point in the receiver's superview coordinates.
  NSView *target = [content hitTest:[content convertPoint:point toView:content.superview]];
  if (!target || target == content || target.window != parent || target.hiddenOrHasHiddenAncestor) {
    return fail("No visible native document view at the viewport center");
  }
  WKWebView *web = nil;
  bool reached_content = false;
  for (NSView *view = target; view; view = view.superview) {
    if (view == content) { reached_content = true; break; }
    if ([view isKindOfClass:WKWebView.class]) { web = (WKWebView *)view; }
  }
  if (!web || !reached_content) { return fail("Wheel target is not a WKWebView descendant of this content view"); }
  const auto attached = [&] {
    if (![NSApp.windows containsObject:parent] || !parent.visible || parent.miniaturized ||
        parent.contentView != content || target.window != parent || target.hiddenOrHasHiddenAncestor ||
        web.window != parent || web.hiddenOrHasHiddenAncestor || ![web isDescendantOf:content] ||
        (target != web && ![target isDescendantOf:web])) { return false; }
    const NSRect current_backing = [content convertRectToBacking:content.bounds];
    const NSRect actual = [content convertRectToBacking:[web convertRect:web.bounds toView:content]];
    return std::abs(current_backing.size.width - framebuffer_width) <= 0.5 &&
        std::abs(current_backing.size.height - framebuffer_height) <= 0.5 &&
        std::abs(NSMinX(actual) - NSMinX(pixels)) <= 0.5 &&
        std::abs(NSMinY(actual) - NSMinY(pixels)) <= 0.5 &&
        std::abs(actual.size.width - pixels.size.width) <= 0.5 &&
        std::abs(actual.size.height - pixels.size.height) <= 0.5 &&
        [content hitTest:[content convertPoint:point toView:content.superview]] == target;
  };
  if (!attached()) { return fail("Wheel WKWebView must match the exact own-window viewport and hit target"); }
  const NSPoint in_window = [content convertPoint:point toView:nil];
  NSScreen *first_screen = NSScreen.screens.firstObject;
  if (!first_screen || !std::isfinite(first_screen.frame.size.height) || first_screen.frame.size.height <= 0) {
    return fail("No valid first-screen geometry for local Cocoa wheel conversion");
  }
  CGEventRef cg = CGEventCreateScrollWheelEvent(nullptr, kCGScrollEventUnitLine, 1, direction * 3);
  if (!cg) { return fail("Cannot create local CoreGraphics wheel event"); }
  // A CG-created wheel has no AppKit window association. Like WebKit's own
  // EventSenderProxy::mouseScrollBy, compensate eventWithCGEvent's first-screen
  // flip using WINDOW-LOCAL coordinates. A global screen point would become an
  // incorrect locationInWindow. This event is only sent directly to the verified
  // own-window descendant; it never enters a global/system/session event queue.
  CGEventSetLocation(cg, CGPointMake(in_window.x, first_screen.frame.size.height - in_window.y));
  NSEvent *event = [NSEvent eventWithCGEvent:cg];
  CFRelease(cg);
  // Accept only WebKit's unassociated event form or this exact owned window.
  // A nonzero foreign window number/object is never admitted, even though direct
  // responder dispatch (rather than event metadata) selects the receiving window.
  const bool unassociated = event && !event.window && event.windowNumber == 0;
  const bool own_window = event && event.window == parent && event.windowNumber == parent.windowNumber;
  if (!event || event.type != NSEventTypeScrollWheel || (!unassociated && !own_window) ||
      !std::isfinite(event.locationInWindow.x) || !std::isfinite(event.locationInWindow.y) ||
      std::abs(event.locationInWindow.x - in_window.x) > 1 || std::abs(event.locationInWindow.y - in_window.y) > 1 ||
      !std::isfinite(event.scrollingDeltaX) || !std::isfinite(event.scrollingDeltaY) ||
      std::abs(event.scrollingDeltaX) > 0.001 || event.scrollingDeltaY * direction <= 0 ||
      !event.CGEvent || CGEventGetType(event.CGEvent) != kCGEventScrollWheel ||
      CGEventGetIntegerValueField(event.CGEvent, kCGScrollWheelEventDeltaAxis1) != direction * 3) {
    error = "Converted local wheel event has invalid type/identity/location/delta; window=" +
        std::to_string(event.windowNumber) + "; associated=" + (event.window ? "true" : "false") +
        "; location=" + std::to_string(event.locationInWindow.x) + "," + std::to_string(event.locationInWindow.y) +
        "; expected=" + std::to_string(in_window.x) + "," + std::to_string(in_window.y);
    return false;
  }
  if (!attached()) { return fail("Cocoa wheel target changed before local delivery"); }
  [target scrollWheel:event];
  if (!attached()) { return fail("Cocoa wheel target changed during local delivery"); }
  delivery = "Cocoa local scrollWheel:; window=" + std::to_string(parent.windowNumber) +
      "; descendant=" + std::string(NSStringFromClass(target.class).UTF8String) +
      "; event_window=" + std::string(unassociated ? "unassociated-local" : "exact-owned-window") +
      "; exact_WKWebView_bounds_and_hit_target=true" +
      "; window_point=" + std::to_string(in_window.x) + "," + std::to_string(in_window.y) +
      "; line_delta=" + std::to_string(direction * 3) + "; no global event post";
  return true;
}
}  // namespace stk::reports_native_test
