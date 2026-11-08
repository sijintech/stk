/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_ax_protocol.hh"

#include <bit>
#include <cmath>
#include <limits>
#include <vector>

namespace stk::reports_native_test::ax {
namespace {
constexpr uint64_t kRequestMagic = 0x53544b4158520001ULL, kResponseMagic = 0x53544b4158530003ULL;
constexpr uint64_t kProgressMagic = 0x53544b4158500001ULL;
template<size_t N> void word(std::array<uint8_t, N> &bytes, size_t &at, uint64_t value) {
  for (int shift = 56; shift >= 0; shift -= 8) bytes[at++] = uint8_t(value >> shift);
}
uint64_t word(std::span<const uint8_t> bytes, size_t &at) {
  uint64_t value = 0;
  for (int i = 0; i < 8; ++i) value = (value << 8) | bytes[at++];
  return value;
}
template<size_t N> void real(std::array<uint8_t, N> &bytes, size_t &at, double value) {
  word(bytes, at, std::bit_cast<uint64_t>(value));
}
double real(std::span<const uint8_t> bytes, size_t &at) { return std::bit_cast<double>(word(bytes, at)); }
template<size_t N> void rect(std::array<uint8_t, N> &bytes, size_t &at, Rect value) {
  real(bytes, at, value.x); real(bytes, at, value.y); real(bytes, at, value.width); real(bytes, at, value.height);
}
Rect rect(std::span<const uint8_t> bytes, size_t &at) {
  Rect result; result.x = real(bytes, at); result.y = real(bytes, at);
  result.width = real(bytes, at); result.height = real(bytes, at); return result;
}
template<class E> bool enumeration(uint64_t value) { return value < uint64_t(E::Count); }
template<class E, size_t N> std::string_view enum_name(E value, const char *const (&names)[N]) {
  const auto index = size_t(value); return index < N ? names[index] : "invalid";
}
}

bool valid_rect(Rect r) {
  return std::isfinite(r.x) && std::isfinite(r.y) && std::isfinite(r.width) && std::isfinite(r.height) &&
      std::isfinite(r.x + r.width) && std::isfinite(r.y + r.height) && r.width > 0 && r.height > 0;
}
bool same_rect(Rect a, Rect b) {
  return a.x == b.x && a.y == b.y && a.width == b.width && a.height == b.height;
}
bool contains(Rect outer, Rect inner) {
  return valid_rect(outer) && valid_rect(inner) && inner.x >= outer.x && inner.y >= outer.y &&
      inner.x + inner.width <= outer.x + outer.width && inner.y + inner.height <= outer.y + outer.height;
}
bool valid_request(const Request &r) {
  const auto bounded = [](Rect v) { return valid_rect(v) && std::abs(v.x) <= 1e7 && std::abs(v.y) <= 1e7 &&
      v.width <= 1e7 && v.height <= 1e7; };
  return r.parent_pid > 1 && r.parent_pid <= uint64_t(std::numeric_limits<int32_t>::max()) &&
      bounded(r.window) && bounded(r.viewport) && bounded(r.video) && contains(r.window, r.viewport) &&
      contains(r.viewport, r.video) && std::isfinite(r.current_time) && std::isfinite(r.duration) &&
      r.duration > 0 && r.current_time >= 0 && r.current_time < r.duration &&
      std::isfinite(.01 + .10 / r.duration);
}
bool matching_slider(const Request &r, Rect f, double lo, double hi, double value) {
  if (!valid_request(r) || !contains(r.video, f) || f.width < r.video.width * .20 ||
      f.height < 2 || f.width < f.height * 4 || !std::isfinite(lo) || !std::isfinite(hi) ||
      !std::isfinite(value) || !(hi > lo && value >= lo && value <= hi)) return false;
  const double span = hi - lo, offset = value - lo;
  if (!std::isfinite(span) || !std::isfinite(offset)) return false;
  const double ratio = offset / span;
  return std::isfinite(ratio) && std::abs(ratio - r.current_time / r.duration) <= .01 + .10 / r.duration;
}
ViewportSelection select_viewport(const Request &q, std::span<const TreeNode> nodes) {
  ViewportSelection out;
  const auto reject = [&](Reason reason) { out.reason = reason; return out; };
  if (!valid_request(q)) return reject(Reason::InvalidRequest);
  if (nodes.empty() || nodes.size() > kNodeLimit) return reject(Reason::TreeBudget);
  std::array<size_t, kNodeLimit> depths{};
  for (size_t i = 0; i < nodes.size(); ++i) {
    const auto &node = nodes[i];
    if (size_t(node.role) >= size_t(TreeRole::Count)) return reject(Reason::RoleType);
    if (i == 0) {
      if (node.parent != kNodeLimit || node.role != TreeRole::Window) return reject(Reason::WindowRole);
      if (!same_rect(node.rect, q.window)) return reject(Reason::GeometryChanged);
    }
    else {
      if (node.parent >= i) return reject(Reason::SharedTree);
      depths[i] = depths[node.parent] + 1;
      if (depths[i] > kDepthLimit) return reject(Reason::TreeDepth);
    }
    if (node.role != TreeRole::Other && !valid_rect(node.rect)) return reject(Reason::InvalidFrame);
  }
  const auto below = [&](size_t child, size_t ancestor) {
    for (size_t step = 0; step <= kDepthLimit && child < nodes.size(); ++step) {
      if (child == ancestor) return true;
      child = nodes[child].parent;
    }
    return false;
  };
  std::vector<size_t> groups;
  for (size_t i = 0; i < nodes.size(); ++i)
    if (nodes[i].role == TreeRole::Group && same_rect(nodes[i].rect, q.viewport)) groups.push_back(i);
  out.matches = groups.size();
  if (groups.empty()) return reject(Reason::NoViewport);
  size_t innermost = kNodeLimit;
  for (const auto group : groups) {
    bool has_matching_descendant = false;
    for (const auto other : groups)
      if (other != group && below(other, group)) { has_matching_descendant = true; break; }
    if (!has_matching_descendant) { ++out.chains; innermost = group; }
  }
  if (out.chains != 1) return reject(Reason::MultipleViewports);
  for (const auto group : groups) if (below(innermost, group)) ++out.chain_length;
  if (out.chain_length != out.matches) return reject(Reason::MultipleViewports);
  const auto outermost = groups.front();
  size_t webarea = kNodeLimit;
  for (size_t i = 0; i < nodes.size(); ++i)
    if (nodes[i].role == TreeRole::WebArea && below(i, outermost)) { ++out.webareas; webarea = i; }
  if (out.webareas != 1) return reject(out.webareas ? Reason::MultipleWebareas : Reason::NoWebarea);
  // Record only already-validated numeric ancestry. This does not publish successful selection indices.
  auto &witness = out.witness;
  witness.available = true; witness.outer = outermost; witness.inner = innermost; witness.webarea = webarea;
  witness.relation = below(webarea, innermost) ? TopologyRelation::WebareaBelowInner :
      below(innermost, webarea) ? TopologyRelation::WebareaAboveInner : TopologyRelation::Divergent;
  std::array<bool, kNodeLimit> included{};
  for (auto start : {innermost, webarea}) {
    for (size_t step = 0; step <= kDepthLimit && start < nodes.size(); ++step) {
      included[start] = true; start = nodes[start].parent;
    }
  }
  for (size_t i = 0; i < nodes.size(); ++i) {
    if (!included[i]) continue;
    if (witness.count >= kWitnessLimit) { witness = {}; return reject(Reason::TreeBudget); }
    const auto &node = nodes[i];
    witness.rows[witness.count++] = {i, node.parent, node.role, depths[i],
        node.role == TreeRole::Group && same_rect(node.rect, q.viewport)};
  }
  if (!below(webarea, innermost)) return reject(Reason::WebareaAssociation);
  if (!contains(nodes[webarea].rect, q.video)) return reject(Reason::WebareaGeometry);
  out.viewport = innermost; out.webarea = webarea; out.reason = Reason::Unique;
  out.complete = true; return out;
}
RequestWire encode(const Request &r) {
  RequestWire bytes{}; size_t at = 0;
  for (auto value : {kRequestMagic, r.parent_pid, r.request_generation, r.navigation_generation, r.viewport_generation}) word(bytes, at, value);
  rect(bytes, at, r.window); rect(bytes, at, r.viewport); rect(bytes, at, r.video);
  real(bytes, at, r.current_time); real(bytes, at, r.duration); return bytes;
}
ResponseWire encode(const Response &r) {
  ResponseWire bytes{}; size_t at = 0;
  for (auto value : {kResponseMagic, uint64_t(r.status), uint64_t(r.reason), uint64_t(r.phase),
       uint64_t(r.operation), uint64_t(r.attribute), uint64_t(int64_t(r.api_error)), uint64_t(r.trusted),
       r.request_generation, r.navigation_generation, r.viewport_generation}) word(bytes, at, value);
  real(bytes, at, r.elapsed_ms);
  for (auto value : {r.calls, r.nodes, r.tree_nodes, r.deepest, r.windows, r.window_matches, r.viewport_matches,
       r.viewport_chains, r.viewport_chain_length, r.webareas, r.sliders, r.candidates,
       r.leaf_no_value, r.leaf_unsupported}) word(bytes, at, value);
  rect(bytes, at, r.slider); real(bytes, at, r.minimum); real(bytes, at, r.maximum); real(bytes, at, r.value);
  const auto &w = r.witness;
  for (auto value : {uint64_t(w.available), w.outer, w.inner, w.webarea, uint64_t(w.relation), w.count}) word(bytes, at, value);
  for (const auto &row : w.rows)
    for (auto value : {row.index, row.parent, uint64_t(row.role), row.depth, uint64_t(row.viewport_match)}) word(bytes, at, value);
  return bytes;
}
ProgressWire encode(const Progress &r) {
  ProgressWire bytes{}; size_t at = 0;
  for (auto value : {kProgressMagic, r.request_generation, r.navigation_generation, r.viewport_generation,
      r.sequence, uint64_t(r.stage), uint64_t(r.edge), r.call_sequence, uint64_t(r.phase),
      uint64_t(r.operation), uint64_t(r.attribute), r.node_index, r.node_depth, uint64_t(r.role)}) word(bytes, at, value);
  real(bytes, at, r.elapsed_ms);
  word(bytes, at, uint64_t(int64_t(r.api_error))); word(bytes, at, r.dropped);
  return bytes;
}
bool decode(std::span<const uint8_t> bytes, Request &request) {
  if (bytes.size() != kRequestBytes) return false;
  size_t at = 0; if (word(bytes, at) != kRequestMagic) return false;
  Request r; r.parent_pid = word(bytes, at); r.request_generation = word(bytes, at);
  r.navigation_generation = word(bytes, at); r.viewport_generation = word(bytes, at);
  r.window = rect(bytes, at); r.viewport = rect(bytes, at); r.video = rect(bytes, at);
  r.current_time = real(bytes, at); r.duration = real(bytes, at);
  if (!valid_request(r)) return false;
  request = r; return true;
}
bool decode(std::span<const uint8_t> bytes, Response &response) {
  if (bytes.size() != kResponseBytes) return false;
  size_t at = 0; if (word(bytes, at) != kResponseMagic) return false;
  const uint64_t status = word(bytes, at), reason = word(bytes, at), phase = word(bytes, at),
      operation = word(bytes, at), attribute = word(bytes, at), error = word(bytes, at), trusted = word(bytes, at);
  if (!enumeration<Status>(status) || !enumeration<Reason>(reason) || !enumeration<Phase>(phase) ||
      !enumeration<Operation>(operation) || !enumeration<Attribute>(attribute) || trusted > 1) return false;
  const int64_t signed_error = std::bit_cast<int64_t>(error);
  if (signed_error < std::numeric_limits<int32_t>::min() || signed_error > std::numeric_limits<int32_t>::max()) return false;
  Response r; r.status = Status(status); r.reason = Reason(reason); r.phase = Phase(phase);
  r.operation = Operation(operation); r.attribute = Attribute(attribute); r.api_error = int32_t(signed_error); r.trusted = bool(trusted);
  r.request_generation = word(bytes, at); r.navigation_generation = word(bytes, at); r.viewport_generation = word(bytes, at);
  r.elapsed_ms = real(bytes, at);
  uint64_t *counts[] = {&r.calls, &r.nodes, &r.tree_nodes, &r.deepest, &r.windows, &r.window_matches,
      &r.viewport_matches, &r.viewport_chains, &r.viewport_chain_length, &r.webareas,
      &r.sliders, &r.candidates, &r.leaf_no_value, &r.leaf_unsupported};
  for (auto *count : counts) *count = word(bytes, at);
  r.slider = rect(bytes, at); r.minimum = real(bytes, at); r.maximum = real(bytes, at); r.value = real(bytes, at);
  const uint64_t available = word(bytes, at);
  auto &w = r.witness;
  w.outer = word(bytes, at); w.inner = word(bytes, at); w.webarea = word(bytes, at);
  const uint64_t relation = word(bytes, at); w.count = word(bytes, at);
  if (available > 1 || !enumeration<TopologyRelation>(relation) || w.count > kWitnessLimit) return false;
  w.available = bool(available); w.relation = TopologyRelation(relation);
  for (auto &row : w.rows) {
    row.index = word(bytes, at); row.parent = word(bytes, at);
    const auto role = word(bytes, at); row.depth = word(bytes, at); const auto match = word(bytes, at);
    if (!enumeration<TreeRole>(role) || match > 1) return false;
    row.role = TreeRole(role); row.viewport_match = bool(match);
  }
  if (!std::isfinite(r.elapsed_ms) || r.elapsed_ms < 0 || r.calls > 100000 || r.nodes > kNodeLimit ||
      r.tree_nodes > kNodeLimit || r.deepest > kDepthLimit || r.windows > kWindowLimit ||
      r.window_matches > kWindowLimit || r.viewport_matches > kNodeLimit ||
      r.viewport_chains > r.viewport_matches || r.viewport_chain_length > r.viewport_matches || r.webareas > kNodeLimit ||
      r.sliders > kNodeLimit || r.candidates > kNodeLimit || r.leaf_no_value > kNodeLimit || r.leaf_unsupported > kNodeLimit ||
      !std::isfinite(r.slider.x) || !std::isfinite(r.slider.y) || !std::isfinite(r.slider.width) ||
      !std::isfinite(r.slider.height) || !std::isfinite(r.minimum) || !std::isfinite(r.maximum) || !std::isfinite(r.value) ||
      !witness_valid(r)) return false;
  response = r; return true;
}
bool witness_valid(const Response &r) {
  const auto &w = r.witness;
  if (w.count > kWitnessLimit || !enumeration<TopologyRelation>(uint64_t(w.relation))) return false;
  for (size_t i = size_t(w.count); i < kWitnessLimit; ++i) {
    const auto &row = w.rows[i];
    if (row.index || row.parent || row.role != TreeRole::Window || row.depth || row.viewport_match) return false;
  }
  if (!w.available) {
    return w.count == 0 && w.outer == kNodeLimit && w.inner == kNodeLimit && w.webarea == kNodeLimit &&
        w.relation == TopologyRelation::Unknown && r.status != Status::Success && r.reason != Reason::WebareaAssociation;
  }
  if (w.count < 3 || r.tree_nodes > kNodeLimit || r.viewport_chains != 1 ||
      r.viewport_matches == 0 || r.viewport_chain_length != r.viewport_matches || r.webareas != 1 ||
      w.relation == TopologyRelation::Unknown) return false;
  const auto find = [&](uint64_t index) -> const WitnessRow * {
    for (size_t i = 0; i < w.count; ++i) if (w.rows[i].index == index) return &w.rows[i];
    return nullptr;
  };
  uint64_t matches = 0;
  for (size_t i = 0; i < w.count; ++i) {
    const auto &row = w.rows[i];
    if (row.index >= r.tree_nodes || !enumeration<TreeRole>(uint64_t(row.role)) ||
        row.depth > kDepthLimit || row.depth > r.deepest || (i && row.index <= w.rows[i - 1].index)) return false;
    if (!i) {
      if (row.index != 0 || row.parent != kNodeLimit || row.role != TreeRole::Window || row.depth || row.viewport_match) return false;
    }
    else {
      const auto *parent = find(row.parent);
      if (!parent || row.parent >= row.index || row.depth != parent->depth + 1) return false;
    }
    if (row.viewport_match) {
      if (row.role != TreeRole::Group) return false;
      ++matches;
    }
  }
  const auto *outer = find(w.outer), *inner = find(w.inner), *webarea = find(w.webarea);
  if (!outer || !inner || !webarea || !outer->viewport_match || !inner->viewport_match ||
      outer->role != TreeRole::Group || inner->role != TreeRole::Group || webarea->role != TreeRole::WebArea ||
      matches != r.viewport_matches) return false;
  const auto below = [&](uint64_t child, uint64_t ancestor) {
    for (size_t step = 0; step <= kDepthLimit; ++step) {
      const auto *row = find(child);
      if (!row) return false;
      if (child == ancestor) return true;
      child = row->parent;
    }
    return false;
  };
  if (!below(w.inner, w.outer) || !below(w.webarea, w.outer)) return false;
  // All viewport matches belong to that exact chain, with outer/inner its first/last matches.
  const WitnessRow *first_match = nullptr, *last_match = nullptr;
  for (size_t i = 0; i < w.count; ++i) if (w.rows[i].viewport_match) {
    if (!below(w.inner, w.rows[i].index)) return false;
    if (!first_match) first_match = &w.rows[i];
    last_match = &w.rows[i];
  }
  if (!first_match || first_match->index != w.outer || last_match->index != w.inner) return false;
  uint64_t webareas = 0;
  for (size_t i = 0; i < w.count; ++i) {
    const auto &row = w.rows[i];
    if (!below(w.inner, row.index) && !below(w.webarea, row.index)) return false;
    if (row.role == TreeRole::WebArea && below(row.index, w.outer)) ++webareas;
  }
  if (webareas != 1) return false;
  const auto relation = below(w.webarea, w.inner) ? TopologyRelation::WebareaBelowInner :
      below(w.inner, w.webarea) ? TopologyRelation::WebareaAboveInner : TopologyRelation::Divergent;
  if (relation != w.relation) return false;
  if (r.status == Status::Success && relation != TopologyRelation::WebareaBelowInner) return false;
  return r.reason != Reason::WebareaAssociation || relation == TopologyRelation::WebareaAboveInner ||
      relation == TopologyRelation::Divergent;
}
bool decode(std::span<const uint8_t> bytes, Progress &progress) {
  if (bytes.size() != kProgressBytes) return false;
  size_t at = 0; if (word(bytes, at) != kProgressMagic) return false;
  Progress r;
  r.request_generation = word(bytes, at); r.navigation_generation = word(bytes, at); r.viewport_generation = word(bytes, at);
  r.sequence = word(bytes, at);
  const auto stage = word(bytes, at), edge = word(bytes, at); r.call_sequence = word(bytes, at);
  const auto phase = word(bytes, at), operation = word(bytes, at), attribute = word(bytes, at);
  r.node_index = word(bytes, at); r.node_depth = word(bytes, at); const auto role = word(bytes, at);
  r.elapsed_ms = real(bytes, at); const auto error = std::bit_cast<int64_t>(word(bytes, at)); r.dropped = word(bytes, at);
  if (!enumeration<ProgressStage>(stage) || !enumeration<ProgressEdge>(edge) || !enumeration<Phase>(phase) ||
      !enumeration<Operation>(operation) || !enumeration<Attribute>(attribute) || !enumeration<TreeRole>(role) ||
      !r.request_generation || !r.navigation_generation || !r.viewport_generation || !r.sequence ||
      r.sequence > kProgressRecordLimit || r.dropped > kProgressRecordLimit ||
      !std::isfinite(r.elapsed_ms) || r.elapsed_ms < 0 || r.elapsed_ms >= 2000 ||
      error < std::numeric_limits<int32_t>::min() || error > std::numeric_limits<int32_t>::max()) return false;
  r.stage = ProgressStage(stage); r.edge = ProgressEdge(edge); r.phase = Phase(phase);
  r.operation = Operation(operation); r.attribute = Attribute(attribute); r.role = TreeRole(role); r.api_error = int32_t(error);
  if (r.node_index == kNodeLimit) {
    if (r.node_depth != kDepthLimit + 1 || r.role != TreeRole::Other) return false;
  }
  else if (r.node_index > kNodeLimit || r.node_depth > kDepthLimit) return false;
  if (r.edge == ProgressEdge::Enter && r.api_error) return false;
  if (r.stage == ProgressStage::Api) {
    if (!r.call_sequence || r.call_sequence > kProgressCallLimit || r.phase == Phase::None ||
        r.operation == Operation::None || r.attribute == Attribute::None) return false;
  }
  else if (r.call_sequence || r.phase != Phase::None || r.operation != Operation::None ||
      r.attribute != Attribute::None || r.api_error) return false;
  progress = r; return true;
}
bool correlated(const Request &q, const Progress &p) {
  return p.request_generation == q.request_generation && p.navigation_generation == q.navigation_generation &&
      p.viewport_generation == q.viewport_generation;
}
bool accepted(const Request &q, const Response &r) {
  return valid_request(q) && r.status == Status::Success && r.reason == Reason::Unique && r.api_error == 0 &&
      r.request_generation == q.request_generation && r.navigation_generation == q.navigation_generation &&
      r.viewport_generation == q.viewport_generation && std::isfinite(r.elapsed_ms) && r.elapsed_ms >= 0 && r.elapsed_ms < 2000 &&
      r.windows > 0 && r.windows <= kWindowLimit && r.window_matches == 1 &&
      r.viewport_matches >= 1 && r.viewport_matches <= kNodeLimit && r.viewport_chains == 1 &&
      r.viewport_chain_length == r.viewport_matches && r.viewport_chain_length + 2 <= r.deepest &&
      r.webareas == 1 && r.candidates == 1 && r.sliders >= 1 && r.sliders <= kNodeLimit &&
      r.tree_nodes >= r.viewport_matches + r.webareas + r.sliders + 1 && r.tree_nodes <= kNodeLimit &&
      r.nodes == r.windows + r.tree_nodes &&
      r.nodes <= kNodeLimit && r.deepest <= kDepthLimit &&
      matching_slider(q, r.slider, r.minimum, r.maximum, r.value);
}
std::string_view name(Status v) { static constexpr const char *n[] = {"success","rejected","api_error","deadline","parent_changed","invalid_request"}; return enum_name(v,n); }
std::string_view name(Reason v) {
  static constexpr const char *n[] = {"unique_time_matched_slider","not_completed","parent_changed","deadline","invalid_request",
    "target_is_not_real_parent","application_unavailable","ax_api_error","null_value","role_type","frame_type","frame_encoding",
    "invalid_frame","array_budget","array_changed","window_association","numeric_type","window_type","window_role","multiple_windows",
    "no_window","tree_budget","shared_tree","tree_depth","child_type","multiple_viewports","no_viewport","multiple_webareas",
    "no_webarea","webarea_geometry","enabled_type","multiple_sliders","no_slider","geometry_changed","windows_changed",
    "webarea_outside_viewport_chain"};
  static_assert(std::size(n) == size_t(Reason::Count)); return enum_name(v,n);
}
std::string_view name(Phase v) { static constexpr const char *n[] = {"none","window","tree","bind","slider","recheck"}; return enum_name(v,n); }
std::string_view name(Operation v) { static constexpr const char *n[] = {"none","attribute","attribute_count","array"}; return enum_name(v,n); }
std::string_view name(Attribute v) { static constexpr const char *n[] = {"none","role","position","size","windows","children","window","enabled","min","max","value"}; return enum_name(v,n); }
std::string_view name(TreeRole v) { static constexpr const char *n[] = {"window","group","scroll_area","webarea","slider","other"}; return enum_name(v,n); }
std::string_view name(TopologyRelation v) { static constexpr const char *n[] = {"unknown","webarea_below_inner","webarea_above_inner","divergent"}; return enum_name(v,n); }
std::string_view name(ProgressStage v) { static constexpr const char *n[] = {"request","trust","application","api","select","response"}; return enum_name(v,n); }
std::string_view name(ProgressEdge v) { static constexpr const char *n[] = {"enter","returned"}; return enum_name(v,n); }
} // namespace stk::reports_native_test::ax
