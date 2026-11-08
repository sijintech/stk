/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_ax_protocol.hh"
#include "reports_native_ax_process.hh"

#include <chrono>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#ifndef _WIN32
#  include <cerrno>
#  include <signal.h>
#  include <sys/wait.h>
#  include <unistd.h>
#endif

namespace ax = stk::reports_native_test::ax;
namespace {
void check(bool value, const char *what) { if (!value) throw std::runtime_error(what); }
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
ax::Response response(const ax::Request &q) {
  ax::Response r; r.status = ax::Status::Success; r.reason = ax::Reason::Unique;
  r.request_generation = q.request_generation; r.navigation_generation = q.navigation_generation;
  r.viewport_generation = q.viewport_generation; r.elapsed_ms = 12; r.calls = 20;
  r.windows = 1; r.window_matches = 1; r.viewport_matches = 1; r.webareas = 1;
  r.viewport_chains = 1; r.viewport_chain_length = 1;
  r.sliders = 1; r.candidates = 1; r.tree_nodes = 4; r.nodes = 5; r.deepest = 3;
  r.slider = {q.video.x + 10, q.video.y + q.video.height - 12, q.video.width * .75, 4};
  r.minimum = 0; r.maximum = 6; r.value = 3; return r;
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
  nested_response.viewport_matches = 4; nested_response.viewport_chain_length = 4;
  nested_response.tree_nodes = 7; nested_response.nodes = 8; nested_response.deepest = 6;
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
  depth_response.viewport_matches = 14; depth_response.viewport_chain_length = 14;
  depth_response.tree_nodes = 17; depth_response.nodes = 18; depth_response.deepest = 16;
  check(ax::accepted(q, depth_response), "maximum-depth wrapper proof rejected");
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
  std::cout << "PASS: viewport ancestor-chain proof and hostile topology rejection\n";
}
#ifndef _WIN32
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
  if (mode == "hang") for (;;) pause();
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
  if (mode == "stale") ++r.request_generation;
  if (mode == "api") { r.status = ax::Status::ApiError; r.reason = ax::Reason::ApiError; r.api_error = -42; }
  if (mode == "multiple") r.candidates = 2;
  auto bytes = ax::encode(r);
  if (mode == "malformed") bytes[0] = 0;
  if (mode == "stderr" && write(STDERR_FILENO, "x", 1) != 1) return 3;
  const size_t amount = mode == "truncated" ? bytes.size() - 1 : bytes.size();
  if (write(STDOUT_FILENO, bytes.data(), amount) != ssize_t(amount)) return 3;
  if (mode == "oversize" && write(STDOUT_FILENO, "x", 1) != 1) return 3;
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
#endif
}
int main(int argc, char **argv) {
  const std::string filename = std::filesystem::path(argv[0]).filename().string();
#ifndef _WIN32
  if (filename.starts_with("ax-stub-")) return fake(filename.substr(8), argv[0]);
#endif
  try {
    const auto q = request(); const auto good = response(q);
    topology_cases(q, good);
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
    auto r = run("good"); check(r.status == ax::ProcessStatus::Response && ax::accepted(q, r.response), "owned success rejected");
    for (const auto *mode : {"malformed", "truncated", "oversize", "exit", "stderr", "close"}) {
      r = run(mode); check(r.status != ax::ProcessStatus::Response, "invalid child output authorized");
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
    ax::ProbeProcess cancelled(hang.string(), q);
    std::this_thread::sleep_for(std::chrono::milliseconds(30)); cancelled.cancel();
    r = wait(cancelled, pumps); reaped(r);
    check(r.status == ax::ProcessStatus::Cancelled && r.killed, "cancel did not kill/reap owned child");
    auto destroyed = std::make_unique<ax::ProbeProcess>(hang.string(), q);
    auto completion = destroyed->completion();
    std::this_thread::sleep_for(std::chrono::milliseconds(30));
    destroyed.reset(); // Simulates UI-owner destruction. The plain completion handle remains drainable.
    r = wait(completion, pumps); reaped(r);
    check(r.status == ax::ProcessStatus::Cancelled && r.killed, "owner destruction lost child cleanup");
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
