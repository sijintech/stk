/* SPDX-License-Identifier: GPL-2.0-or-later */
// macOS-only acceptance helper. Public CF accessibility client, never an ObjC remote-object cast.
#include "reports_native_ax_protocol.hh"
#include <ApplicationServices/ApplicationServices.h>
#include <poll.h>
#include <unistd.h>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <optional>
#include <utility>
#include <vector>

namespace ax = stk::reports_native_test::ax;
namespace {
using Clock = std::chrono::steady_clock;
template<class T> struct Owned {
  T p = nullptr;
  Owned() = default;
  explicit Owned(T value) : p(value) {}
  ~Owned() { if (p) CFRelease(p); }
  Owned(const Owned &) = delete;
  Owned &operator=(const Owned &) = delete;
  Owned(Owned &&other) noexcept : p(std::exchange(other.p, nullptr)) {}
  Owned &operator=(Owned &&other) noexcept {
    if (this != &other) { if (p) CFRelease(p); p = std::exchange(other.p, nullptr); } return *this;
  }
};
struct Probe {
  const pid_t parent = getppid();
  const Clock::time_point began = Clock::now();
  ax::Response response;
  bool failed = false;
  double elapsed() const { return std::chrono::duration<double, std::milli>(Clock::now() - began).count(); }
  bool reject(ax::Reason reason, ax::Status status = ax::Status::Rejected) {
    if (!failed) { failed = true; response.reason = reason; response.status = status; } return false;
  }
  bool check() {
    if (failed) return false;
    if (parent <= 1 || getppid() != parent) return reject(ax::Reason::ParentChanged, ax::Status::ParentChanged);
    if (elapsed() >= 2000) return reject(ax::Reason::Deadline, ax::Status::Deadline);
    return true;
  }
  template<class F> std::optional<AXError> invoke(ax::Phase phase, ax::Operation operation, ax::Attribute attribute, F fn) {
    if (!check()) return std::nullopt;
    response.phase = phase; response.operation = operation; response.attribute = attribute; ++response.calls;
    const AXError error = fn(); // The external parent watchdog can kill this process if the API blocks.
    if (!check()) return std::nullopt;
    return error;
  }
  bool apiFail(AXError error) { response.api_error = int32_t(error); return reject(ax::Reason::ApiError, ax::Status::ApiError); }
};

bool read_request(Probe &p, ax::Request &q) {
  std::array<uint8_t, ax::kRequestBytes + 1> bytes{};
  size_t count = 0;
  for (;;) {
    if (!p.check()) return false;
    pollfd input{STDIN_FILENO, POLLIN, 0};
    int ready = poll(&input, 1, std::max(1, int(2000 - p.elapsed())));
    if (ready < 0 && errno == EINTR) continue;
    if (ready <= 0) return p.reject(ax::Reason::InvalidRequest, ax::Status::InvalidRequest);
    ssize_t got = read(STDIN_FILENO, bytes.data() + count, bytes.size() - count);
    if (got < 0 && errno == EINTR) continue;
    if (got < 0) return p.reject(ax::Reason::InvalidRequest, ax::Status::InvalidRequest);
    if (!got) break;
    count += size_t(got);
    if (count > ax::kRequestBytes) return p.reject(ax::Reason::InvalidRequest, ax::Status::InvalidRequest);
  }
  if (!ax::decode(std::span(bytes.data(), count), q)) return p.reject(ax::Reason::InvalidRequest, ax::Status::InvalidRequest);
  p.response.request_generation = q.request_generation; p.response.navigation_generation = q.navigation_generation;
  p.response.viewport_generation = q.viewport_generation;
  if (q.parent_pid != uint64_t(p.parent)) return p.reject(ax::Reason::NotParent, ax::Status::InvalidRequest);
  return p.check();
}
bool attribute(Probe &p, AXUIElementRef e, CFStringRef name, ax::Attribute category, ax::Phase phase, Owned<CFTypeRef> &out) {
  CFTypeRef raw = nullptr;
  auto error = p.invoke(phase, ax::Operation::Attribute, category, [&] { return AXUIElementCopyAttributeValue(e, name, &raw); });
  out = Owned<CFTypeRef>(raw);
  if (!error) return false;
  if (*error != kAXErrorSuccess) return p.apiFail(*error);
  return raw ? true : p.reject(ax::Reason::NullValue);
}
using Role = ax::TreeRole;
bool role(Probe &p, AXUIElementRef e, ax::Phase phase, Role &out) {
  Owned<CFTypeRef> value;
  if (!attribute(p, e, kAXRoleAttribute, ax::Attribute::Role, phase, value)) return false;
  if (CFGetTypeID(value.p) != CFStringGetTypeID()) return p.reject(ax::Reason::RoleType);
  out = CFEqual(value.p, kAXWindowRole) ? Role::Window : CFEqual(value.p, kAXGroupRole) ? Role::Group :
      CFEqual(value.p, kAXScrollAreaRole) ? Role::ScrollArea : CFEqual(value.p, CFSTR("AXWebArea")) ? Role::WebArea :
      CFEqual(value.p, kAXSliderRole) ? Role::Slider : Role::Other;
  return true;
}
bool frame(Probe &p, AXUIElementRef e, ax::Phase phase, ax::Rect &out) {
  Owned<CFTypeRef> position, size;
  if (!attribute(p, e, kAXPositionAttribute, ax::Attribute::Position, phase, position) ||
      !attribute(p, e, kAXSizeAttribute, ax::Attribute::Size, phase, size)) return false;
  if (CFGetTypeID(position.p) != AXValueGetTypeID() || CFGetTypeID(size.p) != AXValueGetTypeID()) return p.reject(ax::Reason::FrameType);
  // Type-checked CF AXValues only; no ObjC NSAccessibility object is converted to an AXUIElement.
  AXValueRef point = (AXValueRef)position.p, extent = (AXValueRef)size.p;
  CGPoint origin{}; CGSize dimensions{};
  if (AXValueGetType(point) != kAXValueTypeCGPoint || AXValueGetType(extent) != kAXValueTypeCGSize ||
      !AXValueGetValue(point, kAXValueTypeCGPoint, &origin) || !AXValueGetValue(extent, kAXValueTypeCGSize, &dimensions))
    return p.reject(ax::Reason::FrameEncoding);
  out = {origin.x, origin.y, dimensions.width, dimensions.height};
  return ax::valid_rect(out) ? true : p.reject(ax::Reason::InvalidFrame);
}
bool array(Probe &p, AXUIElementRef e, CFStringRef name, ax::Attribute category, ax::Phase phase,
           size_t limit, bool allow_leaf, Owned<CFArrayRef> &out) {
  CFIndex count = 0;
  auto error = p.invoke(phase, ax::Operation::AttributeCount, category,
      [&] { return AXUIElementGetAttributeValueCount(e, name, &count); });
  if (!error) return false;
  if (allow_leaf && (*error == kAXErrorNoValue || *error == kAXErrorAttributeUnsupported)) {
    if (*error == kAXErrorNoValue) ++p.response.leaf_no_value; else ++p.response.leaf_unsupported;
    return true; // Defined absent children, never a messaging error interpreted as success.
  }
  if (*error != kAXErrorSuccess) return p.apiFail(*error);
  if (count < 0 || size_t(count) > limit) return p.reject(ax::Reason::ArrayBudget);
  if (!count) return true;
  CFArrayRef raw = nullptr;
  error = p.invoke(phase, ax::Operation::Array, category,
      [&] { return AXUIElementCopyAttributeValues(e, name, 0, count, &raw); });
  out = Owned<CFArrayRef>(raw);
  if (!error) return false;
  if (*error != kAXErrorSuccess) return p.apiFail(*error);
  if (!raw || CFGetTypeID(raw) != CFArrayGetTypeID() || CFArrayGetCount(raw) != count) return p.reject(ax::Reason::ArrayChanged);
  CFIndex after = 0;
  error = p.invoke(phase, ax::Operation::AttributeCount, category,
      [&] { return AXUIElementGetAttributeValueCount(e, name, &after); });
  if (!error) return false;
  if (*error != kAXErrorSuccess) return p.apiFail(*error);
  return after == count ? true : p.reject(ax::Reason::ArrayChanged);
}
bool same_window(Probe &p, AXUIElementRef e, AXUIElementRef window) {
  Owned<CFTypeRef> value;
  if (!attribute(p, e, kAXWindowAttribute, ax::Attribute::Window, ax::Phase::Bind, value)) return false;
  return CFGetTypeID(value.p) == AXUIElementGetTypeID() && CFEqual(value.p, window) ? true : p.reject(ax::Reason::WindowAssociation);
}
bool numeric(Probe &p, AXUIElementRef e, CFStringRef name, ax::Attribute category, double &out) {
  Owned<CFTypeRef> value;
  if (!attribute(p, e, name, category, ax::Phase::Slider, value)) return false;
  if (CFGetTypeID(value.p) != CFNumberGetTypeID() || !CFNumberGetValue((CFNumberRef)value.p, kCFNumberDoubleType, &out))
    return p.reject(ax::Reason::NumericType);
  return true; // matching_slider rejects all non-finite arithmetic.
}
struct Node { Owned<AXUIElementRef> element; size_t parent, depth; Role role; ax::Rect rect; };
bool descendant(const std::vector<Node> &nodes, size_t child, size_t ancestor) {
  for (size_t i = 0; i <= ax::kDepthLimit && child < nodes.size(); ++i) {
    if (child == ancestor) return true;
    child = nodes[child].parent;
  }
  return false;
}
bool run(Probe &p, const ax::Request &q) {
  if (!p.check()) return false;
  auto &r = p.response;
  r.trusted = AXIsProcessTrusted(); // No prompt/options, entitlement change, or TCC request.
  if (!p.check()) return false;
  Owned<AXUIElementRef> app(AXUIElementCreateApplication(getppid()));
  if (!app.p) return p.reject(ax::Reason::ApplicationUnavailable);
  Owned<CFArrayRef> windows;
  if (!array(p, app.p, kAXWindowsAttribute, ax::Attribute::Windows, ax::Phase::Window, ax::kWindowLimit, false, windows)) return false;
  r.windows = windows.p ? uint64_t(CFArrayGetCount(windows.p)) : 0; r.nodes = r.windows + 1;
  Owned<AXUIElementRef> window;
  for (size_t i = 0; i < r.windows; ++i) {
    CFTypeRef raw = CFArrayGetValueAtIndex(windows.p, CFIndex(i));
    if (!raw || CFGetTypeID(raw) != AXUIElementGetTypeID()) return p.reject(ax::Reason::WindowType);
    AXUIElementRef candidate = (AXUIElementRef)raw;
    Role kind; ax::Rect rect;
    if (!role(p, candidate, ax::Phase::Window, kind) || !frame(p, candidate, ax::Phase::Window, rect)) return false;
    if (kind != Role::Window) return p.reject(ax::Reason::WindowRole);
    if (ax::same_rect(rect, q.window)) {
      ++r.window_matches;
      if (!window.p) window = Owned<AXUIElementRef>((AXUIElementRef)CFRetain(candidate));
    }
  }
  if (r.window_matches != 1) return p.reject(r.window_matches ? ax::Reason::MultipleWindows : ax::Reason::NoWindow);
  struct Pending { Owned<AXUIElementRef> element; size_t parent, depth; };
  std::vector<Pending> pending;
  pending.push_back({Owned<AXUIElementRef>((AXUIElementRef)CFRetain(window.p)), ax::kNodeLimit, 0});
  std::vector<Node> nodes;
  while (!pending.empty()) {
    if (!p.check()) return false;
    Pending next = std::move(pending.back()); pending.pop_back();
    if (r.windows + nodes.size() >= ax::kNodeLimit || next.depth > ax::kDepthLimit) return p.reject(ax::Reason::TreeBudget);
    for (const auto &old : nodes) if (CFEqual(old.element.p, next.element.p)) return p.reject(ax::Reason::SharedTree);
    Node node{std::move(next.element), next.parent, next.depth, Role::Other, {}};
    if (!role(p, node.element.p, ax::Phase::Tree, node.role)) return false;
    if (node.role != Role::Other && !frame(p, node.element.p, ax::Phase::Tree, node.rect)) return false;
    const size_t index = nodes.size(); nodes.push_back(std::move(node));
    r.tree_nodes = nodes.size(); r.nodes = r.windows + r.tree_nodes; r.deepest = std::max(r.deepest, uint64_t(next.depth));
    Owned<CFArrayRef> children;
    if (!array(p, nodes[index].element.p, kAXChildrenAttribute, ax::Attribute::Children, ax::Phase::Tree,
        ax::kNodeLimit - size_t(r.windows) - nodes.size() - pending.size(), true, children)) return false;
    const size_t count = children.p ? size_t(CFArrayGetCount(children.p)) : 0;
    if (count && next.depth == ax::kDepthLimit) return p.reject(ax::Reason::TreeDepth);
    for (size_t i = 0; i < count; ++i) {
      CFTypeRef raw = CFArrayGetValueAtIndex(children.p, CFIndex(i));
      if (!raw || CFGetTypeID(raw) != AXUIElementGetTypeID()) return p.reject(ax::Reason::ChildType);
      pending.push_back({Owned<AXUIElementRef>((AXUIElementRef)CFRetain(raw)), index, next.depth + 1});
    }
  }
  std::vector<ax::TreeNode> topology;
  topology.reserve(nodes.size());
  for (const auto &node : nodes) topology.push_back({node.parent, node.role, node.rect});
  const auto selected = ax::select_viewport(q, topology);
  r.viewport_matches = selected.matches; r.viewport_chains = selected.chains;
  r.viewport_chain_length = selected.chain_length; r.webareas = selected.webareas;
  if (!selected.complete) return p.reject(selected.reason);
  const size_t viewport = selected.viewport, webarea = selected.webarea;
  size_t slider = ax::kNodeLimit;
  // Every coextensive wrapper in the proven chain must refer to this exact own window.
  for (const auto &node : nodes)
    if (node.role == Role::Group && ax::same_rect(node.rect, q.viewport) &&
        !same_window(p, node.element.p, window.p)) return false;
  if (!same_window(p, nodes[webarea].element.p, window.p)) return false;
  for (size_t i = 0; i < nodes.size(); ++i) {
    const Node &node = nodes[i];
    if (node.role != Role::Slider || !descendant(nodes, i, webarea)) continue;
    ++r.sliders;
    if (!ax::contains(q.video, node.rect) || node.rect.width < q.video.width * .20 || node.rect.height < 2 ||
        node.rect.width < node.rect.height * 4) continue;
    Owned<CFTypeRef> enabled;
    if (!attribute(p, node.element.p, kAXEnabledAttribute, ax::Attribute::Enabled, ax::Phase::Slider, enabled)) return false;
    if (CFGetTypeID(enabled.p) != CFBooleanGetTypeID()) return p.reject(ax::Reason::EnabledType);
    if (!CFBooleanGetValue((CFBooleanRef)enabled.p)) continue;
    double lo = 0, hi = 0, value = 0;
    if (!numeric(p, node.element.p, kAXMinValueAttribute, ax::Attribute::Min, lo) ||
        !numeric(p, node.element.p, kAXMaxValueAttribute, ax::Attribute::Max, hi) ||
        !numeric(p, node.element.p, kAXValueAttribute, ax::Attribute::Value, value)) return false;
    if (!ax::matching_slider(q, node.rect, lo, hi, value)) continue;
    if (!same_window(p, node.element.p, window.p)) return false;
    ++r.candidates; slider = i; r.slider = node.rect; r.minimum = lo; r.maximum = hi; r.value = value;
  }
  if (r.candidates != 1) return p.reject(r.candidates ? ax::Reason::MultipleSliders : ax::Reason::NoSlider);
  ax::Rect last_window, last_viewport, last_slider;
  if (!frame(p, window.p, ax::Phase::Recheck, last_window) ||
      !frame(p, nodes[viewport].element.p, ax::Phase::Recheck, last_viewport) ||
      !frame(p, nodes[slider].element.p, ax::Phase::Recheck, last_slider)) return false;
  if (!ax::same_rect(last_window, q.window) || !ax::same_rect(last_viewport, q.viewport) || !ax::same_rect(last_slider, r.slider))
    return p.reject(ax::Reason::GeometryChanged);
  Owned<CFArrayRef> last_windows;
  if (!array(p, app.p, kAXWindowsAttribute, ax::Attribute::Windows, ax::Phase::Recheck, ax::kWindowLimit, false, last_windows)) return false;
  if (!last_windows.p || !CFEqual(last_windows.p, windows.p)) return p.reject(ax::Reason::WindowsChanged);
  if (!p.check()) return false;
  r.status = ax::Status::Success; r.reason = ax::Reason::Unique; return true;
}
}
int main(int argc, char *[]) {
  alarm(2); // Local backstop only; the parent still owns the absolute deadline, kill and reap.
  Probe probe; ax::Request request;
  if (argc != 1) probe.reject(ax::Reason::InvalidRequest, ax::Status::InvalidRequest);
  else if (read_request(probe, request)) run(probe, request);
  probe.check(); probe.response.elapsed_ms = probe.elapsed();
  auto bytes = ax::encode(probe.response);
  // Fixed numeric wire: no arbitrary text, label, URL, stderr diagnostics or private tokens.
  size_t sent = 0;
  while (sent < bytes.size()) {
    const ssize_t n = write(STDOUT_FILENO, bytes.data() + sent, bytes.size() - sent);
    if (n < 0 && errno == EINTR) continue;
    if (n <= 0) return 2;
    sent += size_t(n);
  }
  return probe.failed || probe.response.status != ax::Status::Success ? 1 : 0;
}
