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
constexpr size_t kWitnessLimit = 2 * kDepthLimit + 1;
constexpr size_t kRequestBytes = 19 * 8, kResponseBytes = (33 + 6 + 5 * kWitnessLimit) * 8;
constexpr int kProgressFd = 3;
constexpr size_t kProgressBytes = 17 * 8, kProgressRecordLimit = 8192, kProgressCallLimit = 4096;
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
enum class TreeRole { Window, Group, ScrollArea, WebArea, Slider, Other, Count };
struct TreeNode { size_t parent = kNodeLimit; TreeRole role = TreeRole::Other; Rect rect; };
enum class TopologyRelation : uint64_t { Unknown, WebareaBelowInner, WebareaAboveInner, Divergent, Count };
// Local indices from this one parent-before-child tree, never AX object addresses or reusable identities.
struct WitnessRow {
  uint64_t index = 0, parent = 0;
  TreeRole role = TreeRole::Window;
  uint64_t depth = 0;
  bool viewport_match = false;
};
struct TopologyWitness {
  bool available = false;
  uint64_t outer = kNodeLimit, inner = kNodeLimit, webarea = kNodeLimit;
  TopologyRelation relation = TopologyRelation::Unknown;
  uint64_t count = 0;
  std::array<WitnessRow, kWitnessLimit> rows{};
};
enum class Status : uint64_t { Success, Rejected, ApiError, Deadline, ParentChanged, InvalidRequest, Count };
enum class Reason : uint64_t {
  Unique, NotCompleted, ParentChanged, Deadline, InvalidRequest, NotParent, ApplicationUnavailable,
  ApiError, NullValue, RoleType, FrameType, FrameEncoding, InvalidFrame, ArrayBudget,
  ArrayChanged, WindowAssociation, NumericType, WindowType, WindowRole, MultipleWindows, NoWindow,
  TreeBudget, SharedTree, TreeDepth, ChildType, MultipleViewports, NoViewport, MultipleWebareas,
  NoWebarea, WebareaGeometry, EnabledType, MultipleSliders, NoSlider, GeometryChanged, WindowsChanged,
  WebareaAssociation, Count
};
struct ViewportSelection {
  bool complete = false;
  Reason reason = Reason::NoViewport;
  size_t viewport = kNodeLimit, webarea = kNodeLimit;
  uint64_t matches = 0, chains = 0, chain_length = 0, webareas = 0;
  TopologyWitness witness; // Diagnostic only; rejected selections retain the successful-index sentinels.
};
// A complete parent-before-child tree. Coextensive wrappers must form one strict ancestor chain;
// the outer subtree has exactly one WebArea and it must lie below the innermost matching Group.
ViewportSelection select_viewport(const Request &request, std::span<const TreeNode> nodes);
enum class Phase : uint64_t { None, Window, Tree, Bind, Slider, Recheck, Count };
enum class Operation : uint64_t { None, Attribute, AttributeCount, Array, Count };
enum class Attribute : uint64_t { None, Role, Position, Size, Windows, Children, Window, Enabled, Min, Max, Value, Count };
enum class ProgressStage : uint64_t { Request, Trust, Application, Api, Select, Response, Count };
enum class ProgressEdge : uint64_t { Enter, Returned, Count };
struct Progress {
  uint64_t request_generation = 0, navigation_generation = 0, viewport_generation = 0, sequence = 0;
  ProgressStage stage = ProgressStage::Request;
  ProgressEdge edge = ProgressEdge::Enter;
  uint64_t call_sequence = 0;
  Phase phase = Phase::None;
  Operation operation = Operation::None;
  Attribute attribute = Attribute::None;
  uint64_t node_index = kNodeLimit, node_depth = kDepthLimit + 1;
  TreeRole role = TreeRole::Other;
  double elapsed_ms = 0;
  int32_t api_error = 0;
  uint64_t dropped = 0;
};
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
  uint64_t viewport_matches = 0, viewport_chains = 0, viewport_chain_length = 0;
  uint64_t webareas = 0, sliders = 0, candidates = 0, leaf_no_value = 0, leaf_unsupported = 0;
  Rect slider;
  double minimum = 0, maximum = 0, value = 0;
  TopologyWitness witness;
};
using RequestWire = std::array<uint8_t, kRequestBytes>;
using ResponseWire = std::array<uint8_t, kResponseBytes>;
using ProgressWire = std::array<uint8_t, kProgressBytes>;

bool valid_rect(Rect value);
bool same_rect(Rect a, Rect b);
bool contains(Rect outer, Rect inner);
bool valid_request(const Request &request);
bool matching_slider(const Request &request, Rect frame, double minimum, double maximum, double value);
RequestWire encode(const Request &request);
ResponseWire encode(const Response &response);
ProgressWire encode(const Progress &progress);
bool decode(std::span<const uint8_t> bytes, Request &request);
bool decode(std::span<const uint8_t> bytes, Response &response);
bool decode(std::span<const uint8_t> bytes, Progress &progress);
bool witness_valid(const Response &response);
bool correlated(const Request &request, const Progress &progress);
// Child echoes are correlation only. The Cocoa owner must separately authenticate its live session and objects.
bool accepted(const Request &request, const Response &response);
std::string_view name(Status value);
std::string_view name(Reason value);
std::string_view name(Phase value);
std::string_view name(Operation value);
std::string_view name(Attribute value);
std::string_view name(TreeRole value);
std::string_view name(TopologyRelation value);
std::string_view name(ProgressStage value);
std::string_view name(ProgressEdge value);
} // namespace stk::reports_native_test::ax
