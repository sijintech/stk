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
  const NSRect frame = [content convertRectFromBacking:NSMakeRect(NSMinX(backing) + bounds.x, y,
                                                                bounds.width, bounds.height)];
  const NSPoint point = NSMakePoint(NSMidX(frame), NSMidY(frame));
  // hitTest expects a point in the receiver's superview coordinates.
  NSView *target = [content hitTest:[content convertPoint:point toView:content.superview]];
  if (!target || target == content || target.window != parent || target.hiddenOrHasHiddenAncestor) {
    return fail("No visible native document view at the viewport center");
  }
  bool web_child = false, reached_content = false;
  for (NSView *view = target; view; view = view.superview) {
    if (view == content) { reached_content = true; break; }
    if ([view isKindOfClass:WKWebView.class]) { web_child = true; }
  }
  if (!web_child || !reached_content) { return fail("Wheel target is not a WKWebView descendant of this content view"); }
  const NSPoint in_window = [content convertPoint:point toView:nil];
  const NSPoint in_screen = [parent convertPointToScreen:in_window];
  const CGRect main_display = CGDisplayBounds(CGMainDisplayID());
  CGEventRef cg = CGEventCreateScrollWheelEvent(nullptr, kCGScrollEventUnitLine, 1, direction * 3);
  if (!cg) { return fail("Cannot create local CoreGraphics wheel event"); }
  // Quartz global coordinates are top-left; AppKit screen coordinates are bottom-left.
  // Only geometry is used; this event is never posted to a system/session event queue.
  CGEventSetLocation(cg, CGPointMake(in_screen.x, CGRectGetMaxY(main_display) - in_screen.y));
  CGEventSetIntegerValueField(cg, kCGMouseEventWindowUnderMousePointer, parent.windowNumber);
  CGEventSetIntegerValueField(cg, kCGMouseEventWindowUnderMousePointerThatCanHandleThisEvent, parent.windowNumber);
  NSEvent *event = [NSEvent eventWithCGEvent:cg];
  CFRelease(cg);
  if (!event || event.type != NSEventTypeScrollWheel || event.window != parent ||
      event.windowNumber != parent.windowNumber || std::abs(event.locationInWindow.x - in_window.x) > 1 ||
      std::abs(event.locationInWindow.y - in_window.y) > 1) {
    return fail("Converted wheel event did not retain the exact STK window/location");
  }
  [target scrollWheel:event];
  delivery = "Cocoa local scrollWheel:; window=" + std::to_string(parent.windowNumber) +
      "; descendant=" + std::string(NSStringFromClass(target.class).UTF8String) +
      "; window_point=" + std::to_string(in_window.x) + "," + std::to_string(in_window.y) +
      "; line_delta=" + std::to_string(direction * 3) + "; no global event post";
  return true;
}
}  // namespace stk::reports_native_test
