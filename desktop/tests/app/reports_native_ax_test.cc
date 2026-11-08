/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_ax_protocol.hh"
#include "reports_native_ax_process.hh"
#include "reports_native_wait.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#ifndef _WIN32
#  include <cerrno>
#  include <fcntl.h>
#  include <signal.h>
#  include <sys/wait.h>
#  include <unistd.h>
#endif

namespace ax = stk::reports_native_test::ax;
namespace {
void check(bool value, const char *what) { if (!value) throw std::runtime_error(what); }
struct TestClock {
  using time_point = std::chrono::steady_clock::time_point;
  static inline time_point current;
  static time_point now() { return current; }
};
void waiting_cases() {
  using namespace std::chrono;
  const auto start = TestClock::time_point(seconds(100));
  const auto deadline = start + seconds(45);
  for (int ready_second : {44, 45, 46}) {
    TestClock::current = start;
    int predicates = 0, pumps = 0, yields = 0;
    bool externally_ready = false;
    const bool done = stk::reports_native_test::poll_before<TestClock>(deadline,
        [&] { ++predicates; return externally_ready; },
        [&](bool wait) { check(!wait, "external completion waits for an unrelated OS event"); ++pumps; },
        [&] { ++yields; TestClock::current = start + seconds(ready_second); externally_ready = true; });
    check(done == (ready_second == 44) && pumps == 1 && yields == 1 &&
        predicates == (ready_second == 44 ? 2 : 1), "external ready event renewed its original deadline");
  }
  TestClock::current = start;
  check(!stk::reports_native_test::poll_before<TestClock>(deadline,
      [&] { TestClock::current = deadline; return true; },
      [](bool) { throw std::runtime_error("pump after terminal predicate"); }, [] {}),
      "synchronous predicate crossing the deadline accepted");
  TestClock::current = start;
  int predicates = 0;
  check(!stk::reports_native_test::poll_before<TestClock>(deadline,
      [&] { ++predicates; return false; }, [&](bool wait) {
        check(!wait, "late pump may block"); TestClock::current = deadline + seconds(1);
      }, [] { throw std::runtime_error("yield after late pump"); }) && predicates == 1,
      "late UI pump caused another predicate dispatch");
  TestClock::current = deadline;
  check(!stk::reports_native_test::poll_before<TestClock>(deadline,
      []() -> bool { throw std::runtime_error("predicate after expired start"); },
      [](bool) { throw std::runtime_error("pump after expired start"); },
      [] { throw std::runtime_error("yield after expired start"); }), "expired wait accepted");
  std::cout << "PASS: external completion polls without an OS event and rejects late results\n";
}
ax::Request request() {
  ax::Request r;
#ifndef _WIN32
  r.parent_pid = uint64_t(getpid());
#else
  r.parent_pid = 123;
#endif
  r.request_generation = 7; r.navigation_generation = 8; r.viewport_generation = 9;
  r.window = {-1200, 100, 1000, 800}; r.viewport = {-1180, 150, 900, 700};
  r.video = {-1100, 200, 640, 360}; r.current_time = 3; r.duration = 6; return r;
}
void apply_topology(ax::Response &r, const ax::Request &q, const std::vector<ax::TreeNode> &nodes) {
  const auto selected = ax::select_viewport(q, nodes);
  r.status = selected.complete ? ax::Status::Success : ax::Status::Rejected;
  r.reason = selected.reason; r.witness = selected.witness;
  r.viewport_matches = selected.matches; r.viewport_chains = selected.chains;
  r.viewport_chain_length = selected.chain_length; r.webareas = selected.webareas;
  r.tree_nodes = nodes.size(); r.windows = r.window_matches = 1; r.nodes = r.tree_nodes + 1;
  r.deepest = r.sliders = 0;
  std::array<size_t, ax::kNodeLimit> depths{};
  for (size_t i = 0; i < nodes.size(); ++i) {
    if (i) { check(nodes[i].parent < i, "test topology parent order"); depths[i] = depths[nodes[i].parent] + 1; }
    r.deepest = std::max(r.deepest, uint64_t(depths[i]));
    if (nodes[i].role == ax::TreeRole::Slider) ++r.sliders;
  }
}
ax::Response response(const ax::Request &q) {
  ax::Response r; r.status = ax::Status::Success; r.reason = ax::Reason::Unique;
  r.request_generation = q.request_generation; r.navigation_generation = q.navigation_generation;
  r.viewport_generation = q.viewport_generation; r.elapsed_ms = 12; r.calls = 3;
  r.phase = ax::Phase::Tree; r.operation = ax::Operation::AttributeCount; r.attribute = ax::Attribute::Children;
  r.candidates = 1;
  r.slider = {q.video.x + 10, q.video.y + q.video.height - 12, q.video.width * .75, 4};
  r.minimum = 0; r.maximum = 6; r.value = 3;
  apply_topology(r, q, {{ax::kNodeLimit, ax::TreeRole::Window, q.window},
      {0, ax::TreeRole::Group, q.viewport}, {1, ax::TreeRole::WebArea, q.viewport},
      {2, ax::TreeRole::Slider, r.slider}});
  return r;
}
void topology_cases(const ax::Request &q, const ax::Response &good) {
  using Role = ax::TreeRole;
  using Node = ax::TreeNode;
  const std::vector<Node> single = {{ax::kNodeLimit, Role::Window, q.window},
      {0, Role::Group, q.viewport}, {1, Role::WebArea, q.viewport}, {2, Role::Slider, good.slider}};
  auto selected = ax::select_viewport(q, single);
  check(selected.complete && selected.reason == ax::Reason::Unique && selected.viewport == 1 &&
      selected.webarea == 2 && selected.matches == 1 && selected.chains == 1 &&
      selected.chain_length == 1 && selected.webareas == 1, "single viewport topology rejected");
  // Independently specified nested wrappers: raw matches stay four, logical viewport is one.
  const std::vector<Node> nested = {{ax::kNodeLimit, Role::Window, q.window},
      {0, Role::Group, q.viewport}, {1, Role::Group, q.viewport}, {2, Role::Group, q.viewport},
      {3, Role::Group, q.viewport}, {4, Role::WebArea, q.viewport}, {5, Role::Slider, good.slider}};
  selected = ax::select_viewport(q, nested);
  check(selected.complete && selected.viewport == 4 && selected.webarea == 5 &&
      selected.matches == 4 && selected.chains == 1 && selected.chain_length == 4 && selected.webareas == 1,
      "four nested wrappers were not proven as one viewport");
  auto nested_response = good;
  apply_topology(nested_response, q, nested);
  ax::Response roundtrip;
  check(ax::decode(ax::encode(nested_response), roundtrip) && ax::accepted(q, roundtrip) &&
      roundtrip.viewport_matches == 4 && roundtrip.viewport_chains == 1 && roundtrip.viewport_chain_length == 4,
      "nested proof was not retained by wire and acceptance");
  const auto reject = [&](const std::vector<Node> &tree, ax::Reason reason, const char *message) {
    const auto result = ax::select_viewport(q, tree);
    check(!result.complete && result.reason == reason && result.viewport == ax::kNodeLimit &&
        result.webarea == ax::kNodeLimit, message);
  };
  auto bad = nested; bad[4].parent = 0;
  reject(bad, ax::Reason::MultipleViewports, "sibling viewport branch accepted");
  bad = nested; bad.push_back({2, Role::Group, q.viewport});
  reject(bad, ax::Reason::MultipleViewports, "inner fork accepted");
  bad = nested; bad.push_back({1, Role::WebArea, q.viewport});
  reject(bad, ax::Reason::MultipleWebareas, "extra outer WebArea ignored");
  bad = nested; bad[5].parent = 1;
  reject(bad, ax::Reason::WebareaAssociation, "WebArea outside inner wrapper accepted");
  auto divergent = good; apply_topology(divergent, q, bad);
  const std::vector<Node> ancestor = {{ax::kNodeLimit, Role::Window, q.window},
      {0, Role::Group, q.viewport}, {1, Role::WebArea, q.viewport}, {2, Role::Group, q.viewport},
      {3, Role::Group, q.viewport}, {4, Role::Group, q.viewport}, {5, Role::Slider, good.slider}};
  reject(ancestor, ax::Reason::WebareaAssociation, "WebArea above inner wrapper accepted");
  auto above = good; apply_topology(above, q, ancestor);
  check(above.viewport_matches == 4 && above.viewport_chains == 1 && above.viewport_chain_length == 4 && above.webareas == 1 &&
      above.viewport_matches == divergent.viewport_matches && above.viewport_chains == divergent.viewport_chains &&
      above.viewport_chain_length == divergent.viewport_chain_length && above.webareas == divergent.webareas,
      "ancestor/divergent counterexamples do not retain identical summary counts");
  check(above.witness.relation == ax::TopologyRelation::WebareaAboveInner &&
      divergent.witness.relation == ax::TopologyRelation::Divergent &&
      ax::decode(ax::encode(above), roundtrip) && !ax::accepted(q, roundtrip) &&
      roundtrip.witness.relation == ax::TopologyRelation::WebareaAboveInner,
      "ancestor diagnostic disappeared or authorized delivery");
  check(ax::decode(ax::encode(divergent), roundtrip) && !ax::accepted(q, roundtrip) &&
      roundtrip.witness.relation == ax::TopologyRelation::Divergent && roundtrip.witness.webarea == 5 &&
      roundtrip.witness.inner == 4, "divergent diagnostic disappeared or authorized delivery");
  bad = nested; bad[5].role = Role::Other;
  reject(bad, ax::Reason::NoWebarea, "missing WebArea accepted");
  bad = single; bad[1].rect.width -= 1;
  reject(bad, ax::Reason::NoViewport, "nonmatching Group geometry accepted");
  bad = nested; bad[5].rect = q.video; bad[5].rect.width -= 1;
  reject(bad, ax::Reason::WebareaGeometry, "clipped video accepted");
  bad = nested; bad[4].parent = 4;
  reject(bad, ax::Reason::SharedTree, "self-parent cycle accepted");
  bad = nested; bad[2].parent = 4;
  reject(bad, ax::Reason::SharedTree, "out-of-order parent accepted");
  bad = nested; bad[4].parent = ax::kNodeLimit;
  reject(bad, ax::Reason::SharedTree, "second tree root accepted");
  bad = nested; bad[0].role = Role::Group;
  reject(bad, ax::Reason::WindowRole, "foreign root role accepted");
  bad = nested; bad[0].rect.x += 1;
  reject(bad, ax::Reason::GeometryChanged, "wrong window geometry accepted");
  bad = nested; bad[1].role = Role::Count;
  reject(bad, ax::Reason::RoleType, "unknown role accepted");
  bad = nested; bad[1].rect.width = std::numeric_limits<double>::quiet_NaN();
  reject(bad, ax::Reason::InvalidFrame, "nonfinite frame accepted");
  reject({}, ax::Reason::TreeBudget, "empty tree accepted");
  bad.assign(ax::kNodeLimit + 1, Node{});
  reject(bad, ax::Reason::TreeBudget, "oversized tree accepted");
  bad = {{ax::kNodeLimit, Role::Window, q.window}};
  for (size_t i = 1; i <= ax::kDepthLimit + 1; ++i) bad.push_back({i - 1, Role::Other, {}});
  reject(bad, ax::Reason::TreeDepth, "depth budget accepted");
  // Transparent intermediate roles do not break a genuine ancestor chain.
  const std::vector<Node> transparent = {{ax::kNodeLimit, Role::Window, q.window},
      {0, Role::Group, q.viewport}, {1, Role::Other, {}}, {2, Role::Group, q.viewport},
      {3, Role::WebArea, q.viewport}, {4, Role::Slider, good.slider}};
  selected = ax::select_viewport(q, transparent);
  check(selected.complete && selected.matches == 2 && selected.chain_length == 2 &&
      selected.viewport == 3 && selected.webarea == 4, "intermediate transparent role broke ancestry");
  auto depth_response = good;
  std::vector<Node> maximum = {{ax::kNodeLimit, Role::Window, q.window}};
  for (size_t i = 1; i <= 14; ++i) maximum.push_back({i - 1, Role::Group, q.viewport});
  maximum.push_back({14, Role::WebArea, q.viewport}); maximum.push_back({15, Role::Slider, good.slider});
  apply_topology(depth_response, q, maximum);
  check(ax::decode(ax::encode(depth_response), roundtrip) && ax::accepted(q, roundtrip), "maximum-depth wrapper proof rejected");
  depth_response.viewport_matches = 15; depth_response.viewport_chain_length = 15;
  depth_response.tree_nodes = 18; depth_response.nodes = 19;
  check(!ax::accepted(q, depth_response), "wrapper chain too deep for WebArea and slider accepted");
  for (int mutation = 0; mutation < 5; ++mutation) {
    auto r = nested_response;
    switch (mutation) {
      case 0: r.viewport_chains = 0; break;
      case 1: r.viewport_chains = 2; break;
      case 2: r.viewport_chain_length = 3; break;
      case 3: r.viewport_matches = 0; break;
      case 4: r.tree_nodes = 4; r.nodes = 5; break;
    }
    check(!ax::accepted(q, r), "missing/branched/impossible topology proof accepted");
  }
  auto bytes = ax::encode(nested_response); bytes[7] = 1;
  check(!ax::decode(bytes, roundtrip), "old response version accepted");
  check(!ax::decode(std::span(bytes.data(), bytes.size() - 16), roundtrip), "old response size accepted");
  bytes = ax::encode(nested_response);
  check(!ax::decode(std::span(bytes.data(), bytes.size() - 1), roundtrip), "truncated response accepted");
  auto impossible = good; impossible.viewport_chains = 2;
  check(!ax::decode(ax::encode(impossible), roundtrip), "impossible chain count decoded");
  for (int mutation = 0; mutation < 10; ++mutation) {
    auto malformed = nested_response;
    auto &w = malformed.witness;
    switch (mutation) {
      case 0: w = {}; break; // A bare old success is not a diagnostic-capable response.
      case 1: w.rows[w.count].index = 1; break;
      case 2: w.rows[1].parent = 2; break;
      case 3: ++w.rows[1].depth; break;
      case 4: w.rows[1].role = Role::Count; break;
      case 5: w.relation = ax::TopologyRelation::Divergent; break;
      case 6: w.rows[0].viewport_match = true; break;
      case 7: w.outer = ax::kNodeLimit; break;
      case 8: w.rows[2].index = w.rows[1].index; break;
      case 9: w.count = ax::kWitnessLimit + 1; break;
    }
    check(!ax::decode(ax::encode(malformed), roundtrip), "malformed numeric witness decoded");
  }
  std::cout << "PASS: viewport ancestor-chain proof and hostile topology rejection\n";
}
ax::Progress progress(const ax::Request &q) {
  ax::Progress p;
  p.request_generation = q.request_generation; p.navigation_generation = q.navigation_generation;
  p.viewport_generation = q.viewport_generation; p.sequence = 2; p.stage = ax::ProgressStage::Api;
  p.edge = ax::ProgressEdge::Enter; p.call_sequence = 1; p.phase = ax::Phase::Tree;
  p.operation = ax::Operation::AttributeCount; p.attribute = ax::Attribute::Children;
  p.node_index = 1; p.node_depth = 1; p.role = ax::TreeRole::Group; p.elapsed_ms = 12;
  return p;
}
void progress_cases(const ax::Request &q) {
  const auto good = progress(q); ax::Progress parsed;
  check(ax::decode(ax::encode(good), parsed) && ax::correlated(q, parsed), "numeric progress round trip");
  auto stale = good; ++stale.viewport_generation;
  check(ax::decode(ax::encode(stale), parsed) && !ax::correlated(q, parsed), "stale progress correlation accepted");
  auto lost = good; lost.sequence = 3; lost.dropped = 1;
  check(ax::decode(ax::encode(lost), parsed) && parsed.dropped == 1,
      "a bounded reported progress loss was not retained");
  for (int mutation = 0; mutation < 17; ++mutation) {
    auto p = good;
    switch (mutation) {
      case 0: p.request_generation = 0; break; case 1: p.sequence = 0; break;
      case 2: p.sequence = ax::kProgressRecordLimit + 1; break;
      case 3: p.stage = ax::ProgressStage::Count; break; case 4: p.edge = ax::ProgressEdge::Count; break;
      case 5: p.call_sequence = ax::kProgressCallLimit + 1; break; case 6: p.phase = ax::Phase::None; break;
      case 7: p.operation = ax::Operation::Count; break; case 8: p.attribute = ax::Attribute::None; break;
      case 9: p.node_index = ax::kNodeLimit + 1; break; case 10: p.node_depth = ax::kDepthLimit + 1; break;
      case 11: p.role = ax::TreeRole::Count; break; case 12: p.elapsed_ms = 2000; break;
      case 13: p.elapsed_ms = std::numeric_limits<double>::quiet_NaN(); break;
      case 14: p.api_error = -1; break; case 15: p.dropped = ax::kProgressRecordLimit + 1; break;
      case 16: p.stage = ax::ProgressStage::Select; break;
    }
    check(!ax::decode(ax::encode(p), parsed), "malformed numeric progress decoded");
  }
  auto returned = good; returned.edge = ax::ProgressEdge::Returned; returned.api_error = -42;
  check(ax::decode(ax::encode(returned), parsed) && parsed.api_error == -42, "returned API error lost");
  auto marker = good; marker.stage = ax::ProgressStage::Response; marker.edge = ax::ProgressEdge::Returned;
  marker.call_sequence = 0; marker.phase = ax::Phase::None; marker.operation = ax::Operation::None;
  marker.attribute = ax::Attribute::None; marker.node_index = ax::kNodeLimit;
  marker.node_depth = ax::kDepthLimit + 1; marker.role = ax::TreeRole::Other;
  check(ax::decode(ax::encode(marker), parsed), "valid terminal progress marker rejected");
  const auto bytes = ax::encode(good);
  check(!ax::decode(std::span(bytes.data(), bytes.size() - 1), parsed), "partial progress decoded");
  auto oversized = std::vector<uint8_t>(bytes.begin(), bytes.end()); oversized.push_back(0);
  check(!ax::decode(oversized, parsed), "oversized progress decoded");
  auto invalid = bytes; invalid[0] ^= 1;
  check(!ax::decode(invalid, parsed), "unknown progress magic decoded");
  invalid = bytes; invalid[15 * 8] = 0x7f;
  check(!ax::decode(invalid, parsed), "overflowing progress API error decoded");
  std::cout << "PASS: bounded numeric progress, correlation and hostile wire rejection\n";
}
#ifndef _WIN32
bool write_bytes(int fd, std::span<const uint8_t> bytes) {
  size_t sent = 0;
  while (sent < bytes.size()) {
    const auto n = write(fd, bytes.data() + sent, bytes.size() - sent);
    if (n < 0 && errno == EINTR) continue;
    if (n <= 0) return false;
    sent += size_t(n);
  }
  return true;
}
int fake(const std::string &mode, const char *path) {
  ax::RequestWire input{}; size_t got = 0;
  if (mode == "close") return 4;
  while (got < input.size()) {
    ssize_t count = read(STDIN_FILENO, input.data() + got, input.size() - got);
    if (count <= 0) return 3;
    got += size_t(count);
  }
  uint8_t extra;
  if (read(STDIN_FILENO, &extra, 1) != 0) return 3;
  ax::Request q;
  if (!ax::decode(input, q) || q.parent_pid != uint64_t(getppid())) return 3;
  if (mode == "ignore" || mode == "nochildwait") {
    struct sigaction action{};
    action.sa_handler = mode == "ignore" ? SIG_IGN : SIG_DFL;
    if (mode == "nochildwait") action.sa_flags = SA_NOCLDWAIT;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGCHLD, &action, nullptr)) return 3;
    auto own = q; own.parent_pid = uint64_t(getpid());
    ax::ProbeProcess forbidden(path, own);
    std::optional<ax::ProcessResult> finished;
    for (int i = 0; i < 100 && !finished; ++i) {
      finished = forbidden.poll(); std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    if (!finished || finished->status != ax::ProcessStatus::Unsupported || finished->child_pid || finished->killed) return 3;
  }
  auto r = response(q);
  if (mode == "stale" || mode == "zero-stale") ++r.request_generation;
  if (mode == "api") { r.status = ax::Status::ApiError; r.reason = ax::Reason::ApiError; r.api_error = -42; }
  if (mode == "multiple") r.candidates = 2;
  const auto old_flags = fcntl(ax::kProgressFd, F_GETFL);
  if (old_flags < 0 || fcntl(ax::kProgressFd, F_SETFL, old_flags | O_NONBLOCK) < 0) return 3;
  uint64_t sequence = 0, dropped = 0;
  const auto marker = [&](ax::ProgressStage stage, ax::ProgressEdge edge) {
    ax::Progress p; p.request_generation = q.request_generation; p.navigation_generation = q.navigation_generation;
    p.viewport_generation = q.viewport_generation; p.stage = stage; p.edge = edge; return p;
  };
  const auto send = [&](ax::Progress p) {
    p.sequence = ++sequence; p.elapsed_ms = double(sequence) * .01; p.dropped = dropped;
    return write_bytes(ax::kProgressFd, ax::encode(p));
  };
  if (mode.starts_with("progress-") && mode != "progress-flood") {
    auto p = marker(ax::ProgressStage::Request, ax::ProgressEdge::Returned);
    p.sequence = 1; p.elapsed_ms = .01;
    if (mode == "progress-zero") p.request_generation = 0;
    if (mode == "progress-stale") ++p.request_generation;
    if (mode == "progress-invalid") p.stage = ax::ProgressStage::Count;
    if (mode == "progress-gap") p.sequence = 2; // Unreported sequence loss is malformed.
    if (mode == "progress-lossy-prefix") {
      p = progress(q); p.sequence = 3; p.dropped = 2; p.edge = ax::ProgressEdge::Returned;
      // Request/Returned and the first API/Enter were lost; all later diagnostics are absent.
    }
    auto bytes = ax::encode(p);
    const size_t size = mode == "progress-partial" ? bytes.size() - 1 : bytes.size();
    if (!write_bytes(ax::kProgressFd, std::span(bytes.data(), size))) return 3;
    if (mode == "progress-oversize" && write(ax::kProgressFd, "x", 1) != 1) return 3;
    return write_bytes(STDOUT_FILENO, ax::encode(r)) ? 0 : 3;
  }
  if (mode == "progress-flood") {
    // The child deliberately never yields or exits: only the parent's bounded drain/absolute watchdog may stop it.
    for (uint64_t i = 1;; ++i) {
      auto p = i == 1 ? marker(ax::ProgressStage::Request, ax::ProgressEdge::Returned) : progress(q);
      p.sequence = i; p.elapsed_ms = .01;
      if (i > 1) { p.call_sequence = i / 2; p.edge = i % 2 ? ax::ProgressEdge::Returned : ax::ProgressEdge::Enter; }
      const auto bytes = ax::encode(p);
      for (;;) {
        const auto n = write(ax::kProgressFd, bytes.data(), bytes.size());
        if (n == ssize_t(bytes.size())) break;
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) continue;
        return 3;
      }
    }
  }
  const bool has_progress = !mode.starts_with("zero");
  if (has_progress) {
    if (!send(marker(ax::ProgressStage::Request, ax::ProgressEdge::Returned))) return 3;
    if (mode == "hang" || mode == "cancel" || mode == "destroy" || mode == "returned-hang") {
      auto p = progress(q);
      if (!send(p)) return 3;
      if (mode == "returned-hang") {
        p.edge = ax::ProgressEdge::Returned;
        if (!send(p) || !send(marker(ax::ProgressStage::Select, ax::ProgressEdge::Enter))) return 3;
      }
      if (mode == "cancel" || mode == "destroy") {
        std::ofstream ready(std::filesystem::path(path).parent_path() / (mode + "-ready"));
        ready << "ready"; ready.close();
        if (!ready.good()) return 3;
      }
      for (;;) pause();
    }
    for (uint64_t i = 1; i <= r.calls; ++i) {
      auto p = progress(q); p.call_sequence = i;
      if ((mode == "lossy" || mode == "lossy-no-response") && i == 1) {
        ++sequence; ++dropped; // The first enter event was attempted but its nonblocking write was dropped.
      }
      else if (!send(p)) return 3;
      p.edge = ax::ProgressEdge::Returned;
      if (i == r.calls) p.api_error = r.api_error;
      if (!send(p)) return 3;
    }
    if (!send(marker(ax::ProgressStage::Response, ax::ProgressEdge::Enter))) return 3;
  }
  if (mode == "lossy-no-response") {
    return send(marker(ax::ProgressStage::Response, ax::ProgressEdge::Returned)) ? 0 : 3;
  }
  if (mode == "zero-no-response") return 0;
  auto bytes = ax::encode(r);
  if (mode == "malformed") bytes[0] = 0;
  if (mode == "v2" || mode == "zero-v2" || mode == "v2-magic") bytes[7] = 2;
  if (mode == "stderr" && write(STDERR_FILENO, "x", 1) != 1) return 3;
  const size_t amount = mode == "v2" || mode == "zero-v2" ? 33 * 8 :
                        mode == "truncated" ? bytes.size() - 1 : bytes.size();
  if (!write_bytes(STDOUT_FILENO, std::span(bytes.data(), amount))) return 3;
  if (mode == "oversize" && write(STDOUT_FILENO, "x", 1) != 1) return 3;
  // Match the real helper: stdout is complete before the optional terminal progress write.
  if (has_progress && mode != "omit-returned" &&
      !send(marker(ax::ProgressStage::Response, ax::ProgressEdge::Returned))) return 3;
  return mode == "exit" ? 7 : mode == "api" ? 1 : 0;
}
template<class Process> ax::ProcessResult wait(Process &process, int &pumps) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (std::chrono::steady_clock::now() < deadline) {
    ++pumps;
    if (auto result = process.poll()) return *result;
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  throw std::runtime_error("owned worker did not finish");
}
void reaped(const ax::ProcessResult &r) {
  check(r.reaped && r.child_pid > 0, "owned child was not reaped");
  int status = 0; errno = 0;
  check(waitpid(pid_t(r.child_pid), &status, WNOHANG) == -1 && errno == ECHILD, "child remains unreaped");
}
void ready(const std::filesystem::path &marker) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!std::filesystem::exists(marker)) {
    check(std::chrono::steady_clock::now() < deadline, "controlled child did not reach its progress boundary");
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
}
#endif
}
int main(int argc, char **argv) {
  const std::string filename = std::filesystem::path(argv[0]).filename().string();
#ifndef _WIN32
  if (filename.starts_with("ax-stub-")) return fake(filename.substr(8), argv[0]);
#endif
  try {
    waiting_cases();
    const auto q = request(); const auto good = response(q);
    topology_cases(q, good);
    progress_cases(q);
    ax::LayoutEpoch layout;
    check(!layout.freeze(), "unobserved layout was freezeable");
    layout.ready(); const auto token = layout.freeze(); check(token.has_value(), "ready layout not freezeable");
    layout.invalidated();
    check(!layout.freeze() && !layout.matches(*token), "invalidated/coalesced layout retained a usable lease");
    layout.ready(); check(!layout.matches(*token), "move-away/back revived an old layout lease");
    check(layout.freeze().has_value(), "new ready layout has no fresh lease");
    const auto start = ax::Deadline::Clock::time_point(std::chrono::seconds(100));
    const ax::Deadline budget(start + std::chrono::seconds(8));
    const auto callback_budget = budget; // A later phase retains the original absolute deadline.
    const auto ready_generation = *layout.freeze();
    check(budget.permits(start + std::chrono::seconds(7)), "live seek budget rejected");
    check(!callback_budget.permits(start + std::chrono::seconds(8)), "exact-deadline callback accepted");
    check(layout.matches(ready_generation) && !callback_budget.permits(start + std::chrono::seconds(9)),
          "ready/same-layout late callback renewed its input budget");
    check(!ax::Deadline().permits(start), "uninitialized input budget accepted");
    auto wire = ax::encode(q); ax::Request decoded;
    check(ax::decode(wire, decoded) && ax::same_rect(decoded.video, q.video), "numeric request round trip");
    auto result = ax::encode(good); ax::Response parsed;
    check(ax::decode(result, parsed) && ax::accepted(q, parsed), "numeric response round trip");
    check(!ax::decode(std::span(wire.data(), wire.size() - 1), decoded), "truncated request accepted");
    wire[0] ^= 1; check(!ax::decode(wire, decoded), "wrong request version accepted");
    auto invalid = q; invalid.duration = std::numeric_limits<double>::quiet_NaN();
    check(!ax::decode(ax::encode(invalid), decoded), "NaN request accepted");
    invalid = q; invalid.video.x = q.viewport.x - 1;
    check(!ax::valid_request(invalid), "outside viewport accepted");
    check(!ax::matching_slider(q, good.slider, -1e308, 1e308, 0), "overflowing numeric range accepted");
    check(!ax::matching_slider(q, good.slider, 0, 6, std::numeric_limits<double>::quiet_NaN()), "NaN time accepted");
    auto short_slider = good.slider; short_slider.width = 20;
    check(!ax::matching_slider(q, short_slider, 0, 6, 3), "too short slider accepted");
    auto outside = good.slider; outside.x = q.video.x - 1;
    check(!ax::matching_slider(q, outside, 0, 6, 3), "partly clipped slider accepted");
    for (int mutation = 0; mutation < 8; ++mutation) {
      auto r = good;
      switch (mutation) {
        case 0: ++r.request_generation; break; case 1: ++r.navigation_generation; break;
        case 2: ++r.viewport_generation; break; case 3: r.candidates = 2; break;
        case 4: r.window_matches = 2; break; case 5: r.viewport_matches = 2; break;
        case 6: r.elapsed_ms = 2000; break; case 7: r.status = ax::Status::ApiError; r.api_error = -42; break;
      }
      check(!ax::accepted(q, r), "stale/ambiguous/late/error response accepted");
    }
    parsed = good; parsed.nodes = 257;
    check(!ax::decode(ax::encode(parsed), parsed), "node budget wire accepted");
    result = ax::encode(good); result[15] = uint8_t(ax::Status::Count);
    check(!ax::decode(result, parsed), "unknown status accepted");
    std::cout << "PASS: numeric AX contract, bounds, uniqueness and stale rejection\n";
#ifndef _WIN32
    check(argc == 1, "unexpected test arguments");
    const auto self = std::filesystem::canonical(argv[0]);
    const auto dir = std::filesystem::temp_directory_path() / ("stk-ax-owned-" + std::to_string(getpid()));
    check(std::filesystem::create_directory(dir), "owned test directory already exists");
    struct Cleanup { std::filesystem::path path; ~Cleanup() { std::error_code e; std::filesystem::remove_all(path, e); } } cleanup{dir};
    auto run = [&](const std::string &mode) {
      const auto path = dir / ("ax-stub-" + mode);
      std::filesystem::create_symlink(self, path);
      int pumps = 0; ax::ProbeProcess process(path.string(), q);
      auto r = wait(process, pumps); reaped(r); return r;
    };
    auto r = run("good");
    check(r.status == ax::ProcessStatus::Response && r.response_available && r.progress_available &&
        !r.progress_incomplete && !r.progress_invalid && !r.progress_dropped &&
        r.last_progress && r.last_progress->stage == ax::ProgressStage::Response &&
        r.last_progress->edge == ax::ProgressEdge::Returned && r.last_api_return &&
        r.last_api_return->call_sequence == good.calls && ax::accepted(q, r.response), "owned diagnostic success rejected");
    for (const auto *mode : {"malformed", "truncated", "oversize", "exit", "stderr", "close", "v2", "zero-v2", "v2-magic"}) {
      r = run(mode); check(r.status != ax::ProcessStatus::Response, "invalid child output authorized");
    }
    r = run("zero");
    check(r.status == ax::ProcessStatus::Response && r.response_available && !r.progress_available &&
        r.progress_incomplete && !r.progress_invalid && !r.progress_dropped && !r.progress_records &&
        !r.last_progress && !r.last_api_enter && !r.last_api_return &&
        ax::encode(r.response) == ax::encode(good) && ax::accepted(q, r.response),
        "complete v3 response rejected or diagnostics invented when all progress was absent");
    r = run("omit-returned");
    check(r.status == ax::ProcessStatus::Response && r.response_available && r.progress_available &&
        r.progress_incomplete && !r.progress_invalid && !r.progress_dropped && r.last_progress &&
        r.last_progress->stage == ax::ProgressStage::Response && r.last_progress->edge == ax::ProgressEdge::Enter &&
        r.last_api_return && r.last_api_return->call_sequence == good.calls &&
        r.progress_records == 2 * good.calls + 2 && ax::encode(r.response) == ax::encode(good) &&
        ax::accepted(q, r.response), "lost terminal progress invalidated an independently complete v3 response");
    r = run("zero-stale");
    check(r.status == ax::ProcessStatus::Response && r.response_available && !r.progress_available &&
        r.progress_incomplete && !ax::accepted(q, r.response), "absent diagnostics authorized stale response generations");
    r = run("zero-no-response");
    check(r.status == ax::ProcessStatus::ProtocolError && !r.response_available && !r.progress_available &&
        r.progress_incomplete && !ax::accepted(q, r.response), "absent diagnostics manufactured a valid response");
    r = run("progress-lossy-prefix");
    check(r.status == ax::ProcessStatus::Response && r.response_available && r.progress_available &&
        r.progress_dropped && r.progress_incomplete && !r.progress_invalid && r.progress_records == 1 &&
        !r.last_api_enter && r.last_api_return && r.last_api_return->call_sequence == 1 &&
        ax::encode(r.response) == ax::encode(good) && ax::accepted(q, r.response),
        "valid finite diagnostic prefix invalidated an independently complete v3 response");
    r = run("lossy");
    check(r.status == ax::ProcessStatus::Response && r.response_available && r.progress_available &&
        r.progress_dropped && r.progress_incomplete && !r.progress_invalid && r.last_progress &&
        r.last_progress->stage == ax::ProgressStage::Response && r.last_progress->edge == ax::ProgressEdge::Returned &&
        r.last_progress->sequence == 2 * good.calls + 3 && r.last_progress->dropped == 1 &&
        r.progress_records == 2 * good.calls + 2 && ax::accepted(q, r.response),
        "reported progress loss invalidated a separately valid response or lost its incompleteness flags");
    r = run("lossy-no-response");
    check(r.status == ax::ProcessStatus::ProtocolError && !r.response_available && r.progress_dropped &&
        r.progress_incomplete && !ax::accepted(q, r.response), "lossy progress manufactured a valid response");
    for (const auto *mode : {"progress-zero", "progress-stale", "progress-invalid", "progress-partial",
                             "progress-oversize", "progress-gap", "progress-flood"}) {
      r = run(mode);
      check(r.status != ax::ProcessStatus::Response && r.elapsed_ms < 4000 &&
          (r.progress_invalid || r.progress_incomplete), "invalid/flooded progress authorized or starved watchdog");
    }
    r = run("stale"); check(r.status == ax::ProcessStatus::Response && !ax::accepted(q, r.response), "stale echo authorized");
    r = run("multiple"); check(r.status == ax::ProcessStatus::Response && !ax::accepted(q, r.response), "multiple slider child authorized");
    r = run("api"); check(r.status == ax::ProcessStatus::Response && r.response.api_error == -42 && !ax::accepted(q, r.response), "API failure hidden");
    for (const auto *policy : {"ignore", "nochildwait"}) {
      r = run(policy); check(r.status == ax::ProcessStatus::Response && ax::accepted(q, r.response), "auto-reap policy was not refused before spawning");
    }
    const auto hang = dir / "ax-stub-hang"; std::filesystem::create_symlink(self, hang);
    int pumps = 0; ax::ProbeProcess hung(hang.string(), q);
    r = wait(hung, pumps); reaped(r);
    check(r.status == ax::ProcessStatus::Deadline && r.killed && pumps > 100 && r.elapsed_ms >= 1900 && r.elapsed_ms < 4000,
          "deadline did not kill/reap while caller kept polling");
    check(!r.response_available && r.progress_available && r.progress_incomplete && r.last_api_enter &&
        !r.last_api_return && r.last_api_enter->phase == ax::Phase::Tree &&
        r.last_api_enter->operation == ax::Operation::AttributeCount &&
        r.last_api_enter->attribute == ax::Attribute::Children,
        "deadline lost the last observed in-flight API boundary");
    r = run("returned-hang");
    check(r.status == ax::ProcessStatus::Deadline && r.killed && !r.response_available &&
        r.last_api_enter && r.last_api_return &&
        r.last_api_enter->call_sequence == r.last_api_return->call_sequence && r.last_progress &&
        r.last_progress->stage == ax::ProgressStage::Select,
        "a returned API followed by local hang was reported as an unfinished API");
    const auto cancel = dir / "ax-stub-cancel"; std::filesystem::create_symlink(self, cancel);
    ax::ProbeProcess cancelled(cancel.string(), q);
    ready(dir / "cancel-ready"); cancelled.cancel();
    r = wait(cancelled, pumps); reaped(r);
    check(r.status == ax::ProcessStatus::Cancelled && r.killed && !r.response_available && r.last_api_enter &&
        !r.last_api_return && r.progress_incomplete, "cancel did not retain progress and kill/reap owned child");
    const auto destroy = dir / "ax-stub-destroy"; std::filesystem::create_symlink(self, destroy);
    auto destroyed = std::make_unique<ax::ProbeProcess>(destroy.string(), q);
    auto completion = destroyed->completion();
    ready(dir / "destroy-ready");
    destroyed.reset(); // Simulates UI-owner destruction. The plain completion handle remains drainable.
    r = wait(completion, pumps); reaped(r);
    check(r.status == ax::ProcessStatus::Cancelled && r.killed && r.last_api_enter &&
        !r.response_available, "owner destruction lost child cleanup/progress");
    invalid = q; ++invalid.parent_pid;
    ax::ProbeProcess foreign(hang.string(), invalid);
    r = wait(foreign, pumps); check(r.status == ax::ProcessStatus::ProtocolError && r.child_pid == 0, "foreign target was spawned");
    std::cout << "PASS: owned subprocess, hostile outputs, API failure, hard deadline and cancellation\n";
#else
    (void)argc;
#endif
    return 0;
  }
  catch (const std::exception &e) { std::cerr << "FAIL: " << e.what() << '\n'; return 1; }
}
