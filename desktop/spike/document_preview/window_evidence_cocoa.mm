/* SPDX-License-Identifier: GPL-2.0-or-later */
#import <AppKit/AppKit.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#include "window_evidence.hh"
#include <algorithm>
#include <cmath>
#include <mutex>
#include <stdexcept>
#include <utility>

namespace stk::document_preview {
namespace {
struct Delivery {
  std::mutex mutex;
  bool closed = false;
  std::optional<WindowEvidence> value;
  bool active()
  {
    std::lock_guard lock(mutex);
    return !closed;
  }
  void finish(WindowEvidence result)
  {
    std::lock_guard lock(mutex);
    if (!closed) { value = std::move(result); }
  }
};
class Capture final : public WindowEvidenceCapture {
 public:
  explicit Capture(wm::NativeWindowHandle parent) : delivery_(std::make_shared<Delivery>())
  {
    const auto delivery = delivery_;
    const auto fail = [delivery](const std::string &message) {
      delivery->finish({{}, "screencapturekit-own-window-client", message});
    };
    if (parent.kind != wm::NativeWindowKind::Cocoa || !parent.value) {
      fail("Evidence capture needs a Cocoa STK window"); return;
    }
    NSWindow *window = (__bridge NSWindow *)parent.value;
    if (![NSThread isMainThread] || !window.visible || window.miniaturized || !window.contentView) {
      fail("Evidence capture needs the visible STK window on its UI thread"); return;
    }
    if (@available(macOS 14.4, *)) {
      const CGWindowID window_id = CGWindowID(window.windowNumber);
      const NSRect outer = window.frame;
      const NSRect client = [window convertRectToScreen:
          [window.contentView convertRect:window.contentView.bounds toView:nil]];
      // Only this process's windows are enumerated; no desktop or other-app screenshots.
      // All NSWindow geometry is copied now. Late callbacks own no borrowed NSWindow/NSView.
      [SCShareableContent getCurrentProcessShareableContentWithCompletionHandler:
          ^(SCShareableContent *content, NSError *error) {
        if (!delivery->active()) { return; }
        if (error || !content) { fail("ScreenCaptureKit could not enumerate this process's window"); return; }
        SCWindow *target = nil;
        for (SCWindow *candidate in content.windows) {
          if (candidate.windowID == window_id) { target = candidate; break; }
        }
        if (!target) { fail("The STK fixture window is absent from ScreenCaptureKit"); return; }
        SCContentFilter *filter = [[SCContentFilter alloc] initWithDesktopIndependentWindow:target];
        const double scale = filter.pointPixelScale;
        const CGRect rect = filter.contentRect;
        const double width = std::ceil(rect.size.width * scale);
        const double height = std::ceil(rect.size.height * scale);
        if (!std::isfinite(scale) || !std::isfinite(width) || !std::isfinite(height) || scale <= 0 ||
            std::abs(rect.size.width - outer.size.width) > 1 ||
            std::abs(rect.size.height - outer.size.height) > 1 ||
            width < 1 || height < 1 || width > 8192 || height > 8192 ||
            width * height > 16 * 1024 * 1024) {
          fail("ScreenCaptureKit window geometry does not match the bounded STK client"); return;
        }
        const int x = int(std::lround((NSMinX(client) - NSMinX(outer)) * scale));
        const int y = int(std::lround((NSMaxY(outer) - NSMaxY(client)) * scale));
        const int w = int(std::lround(client.size.width * scale));
        const int h = int(std::lround(client.size.height * scale));
        if (x < 0 || y < 0 || w <= 0 || h <= 0 || x + w > width || y + h > height) {
          fail("STK client crop is outside the captured window"); return;
        }
        SCStreamConfiguration *config = [SCStreamConfiguration new];
        config.width = size_t(width); config.height = size_t(height);
        config.showsCursor = NO;
        config.ignoreShadowsSingleWindow = YES;
        [SCScreenshotManager captureImageWithFilter:filter configuration:config
            completionHandler:^(CGImageRef image, NSError *capture_error) {
          if (!delivery->active()) { return; }
          if (capture_error || !image) {
            fail("ScreenCaptureKit capture failed; screen capture permission/session must be available"); return;
          }
          WindowEvidence out;
          out.backend = "screencapturekit-own-window-client";
          try {
            if (CGImageGetWidth(image) != size_t(width) || CGImageGetHeight(image) != size_t(height)) {
              throw std::runtime_error("ScreenCaptureKit returned unexpected dimensions");
            }
            // AppKit performs the CGImage orientation/channel conversion; PNG decode is bounded.
            NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc] initWithCGImage:image];
            NSData *png = [bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
            if (!png || png.length > 80 * 1024 * 1024) {
              throw std::runtime_error("ScreenCaptureKit image conversion failed or exceeded budget");
            }
            const auto full = io::decode_png(
                {static_cast<const uint8_t *>(png.bytes), size_t(png.length)},
                {.max_width = 8192, .max_height = 8192, .max_pixels = 16 * 1024 * 1024});
            out.image = io::Image(uint32_t(w), uint32_t(h));
            for (int row = 0; row < h; ++row) {
              std::copy_n(full.pixel(uint32_t(x), uint32_t(y + row)), size_t(w) * 4,
                          out.image.row(uint32_t(row)));
            }
          }
          catch (const std::exception &e) { out.error = e.what(); }
          delivery->finish(std::move(out));
        }];
      }];
    }
    else {
      // This is an evidence-helper restriction, not a change to STK's macOS 13.3 minimum.
      fail("Native evidence requires macOS 14.4 or newer; the preview candidate still supports 13.3");
    }
  }
  ~Capture() override
  {
    std::lock_guard lock(delivery_->mutex);
    delivery_->closed = true;
    delivery_->value.reset();
  }
  std::optional<WindowEvidence> poll() override
  {
    std::lock_guard lock(delivery_->mutex);
    return std::exchange(delivery_->value, std::nullopt);
  }
 private:
  std::shared_ptr<Delivery> delivery_;
};
}
std::string native_evidence_environment_error()
{
  if (@available(macOS 14.4, *)) { return {}; }
  return "OS evidence needs macOS 14.4 or newer; STK's product minimum remains 13.3";
}
std::unique_ptr<WindowEvidenceCapture> capture_window_evidence(wm::NativeWindowHandle parent)
{
  return std::make_unique<Capture>(parent);
}
}  // namespace stk::document_preview
