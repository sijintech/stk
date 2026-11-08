/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <chrono>
#include <span>
#include <string_view>
#include <limits>
#include <optional>

namespace stk::reports_native_test::ax {
static_assert(sizeof(double) == sizeof(uint64_t) && std::numeric_limits<double>::is_iec559);
// Test-only, fixed-size numeric wire. Never carries paths, labels, URLs, text or a session token.
constexpr size_t kNodeLimit = 256, kDepthLimit = 16, kWindowLimit = 16;
constexpr size_t kRequestBytes = 19 * 8, kResponseBytes = 31 * 8;
// Host-only absolute budget. Passing it through phases cannot restart the clock.
class Deadline {
 public:
  using Clock = std::chrono::steady_clock;
  explicit Deadline(Clock::time_point end = {}) : end_(end) {}
  bool permits(Clock::time_point now) const { return now < end_; }
 private:
  Clock::time_point end_;
};
// UI-owner state, not part of the wire: invalidations can coalesce until a later ready callback.
class LayoutEpoch {
 public:
  void invalidated() { ready_ = false; if (generation_ != std::numeric_limits<uint64_t>::max()) ++generation_; }
  void ready() { ready_ = generation_ != std::numeric_limits<uint64_t>::max(); }
  std::optional<uint64_t> freeze() const { return ready_ ? std::optional(generation_) : std::nullopt; }
  bool matches(uint64_t generation) const { return ready_ && generation == generation_; }
 private:
  uint64_t generation_ = 1;
  bool ready_ = false;
};
struct Rect { double x = 0, y = 0, width = 0, height = 0; };
struct Request {
  uint64_t parent_pid = 0, request_generation = 0, navigation_generation = 0, viewport_generation = 0;
  Rect window, viewport, video; // Public AX top-left screen points, never backing pixels.
  double current_time = 0, duration = 0;
};
enum class Status : uint64_t { Success, Rejected, ApiError, Deadline, ParentChanged, InvalidRequest, Count };
enum class Reason : uint64_t {
  Unique, NotCompleted, ParentChanged, Deadline, InvalidRequest, NotParent, ApplicationUnavailable,
  ApiError, NullValue, RoleType, FrameType, FrameEncoding, InvalidFrame, ArrayBudget,
  ArrayChanged, WindowAssociation, NumericType, WindowType, WindowRole, MultipleWindows, NoWindow,
  TreeBudget, SharedTree, TreeDepth, ChildType, MultipleViewports, NoViewport, MultipleWebareas,
  NoWebarea, WebareaGeometry, EnabledType, MultipleSliders, NoSlider, GeometryChanged, WindowsChanged, Count
};
enum class Phase : uint64_t { None, Window, Tree, Bind, Slider, Recheck, Count };
enum class Operation : uint64_t { None, Attribute, AttributeCount, Array, Count };
enum class Attribute : uint64_t { None, Role, Position, Size, Windows, Children, Window, Enabled, Min, Max, Value, Count };
struct Response {
  Status status = Status::Rejected;
  Reason reason = Reason::NotCompleted;
  Phase phase = Phase::None;
  Operation operation = Operation::None;
  Attribute attribute = Attribute::None;
  int32_t api_error = 0;
  bool trusted = false;
  uint64_t request_generation = 0, navigation_generation = 0, viewport_generation = 0;
  double elapsed_ms = 0;
  uint64_t calls = 0, nodes = 0, tree_nodes = 0, deepest = 0, windows = 0, window_matches = 0;
  uint64_t viewport_matches = 0, webareas = 0, sliders = 0, candidates = 0, leaf_no_value = 0, leaf_unsupported = 0;
  Rect slider;
  double minimum = 0, maximum = 0, value = 0;
};
using RequestWire = std::array<uint8_t, kRequestBytes>;
using ResponseWire = std::array<uint8_t, kResponseBytes>;

bool valid_rect(Rect value);
bool same_rect(Rect a, Rect b);
bool contains(Rect outer, Rect inner);
bool valid_request(const Request &request);
bool matching_slider(const Request &request, Rect frame, double minimum, double maximum, double value);
RequestWire encode(const Request &request);
ResponseWire encode(const Response &response);
bool decode(std::span<const uint8_t> bytes, Request &request);
bool decode(std::span<const uint8_t> bytes, Response &response);
// Child echoes are correlation only. The Cocoa owner must separately authenticate its live session and objects.
bool accepted(const Request &request, const Response &response);
std::string_view name(Status value);
std::string_view name(Reason value);
std::string_view name(Phase value);
std::string_view name(Operation value);
std::string_view name(Attribute value);
} // namespace stk::reports_native_test::ax
