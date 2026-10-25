/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Opt-in native child-view experiment. It never opens a user project or starts a bridge. */
#include "fixture.hh"
#include "native_document_view.hh"
#include "window_evidence.hh"
#include "evidence_pixels.hh"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <optional>
#include <nlohmann/json.hpp>
#include "stk/core/mmap.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include <stdexcept>

#include "MEM_guardedalloc.h"

#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/fonts.hh"
#include "stk/wm/window.hh"

using namespace stk;
using namespace stk::document_preview;

namespace {
constexpr const char *kEditor = "document_preview_spike";

struct Host : std::enable_shared_from_this<Host> {
  app::Editor *owner = nullptr;  // Only compared; the editor clears this before destruction.
  wm::Window *window = nullptr;  // Cleared by the pre-destruction close listener.
  std::shared_ptr<ResourceSession> resources;
  std::unique_ptr<NativeDocumentView> view;
  std::string error;
  bool attempted = false;
  bool desired_visible = false;
  ViewBounds last_bounds{};
  wm::Screen *observed_screen = nullptr;  // Only dereferenced inside its ready callback.
  wm::Screen::LayoutObserver layout_observer;
  bool closed = false;

  Host()
  {
    resources = make_fixture(error);
    if (!resources) { throw std::runtime_error(error); }
  }
  ~Host() { close(); }

  void hide()
  {
    desired_visible = false;
    if (view) { view->set_visible(false); }
  }

  void close()
  {
    layout_observer.reset();
    observed_screen = nullptr;
    closed = true;
    hide();
    if (view) { view->close(); }
    if (resources) { resources->close(); }
    window = nullptr;
  }

  void load(std::string_view path)
  {
    if (view) { view->navigate(path, error); }
    if (window) { window->request_redraw(); }
  }

  void observe(wm::Screen *screen)
  {
    if (closed || !owner || (screen == observed_screen && layout_observer)) { return; }
    layout_observer.reset();
    observed_screen = nullptr;
    hide();
    if (window) {
      // A moved editor must never keep a native child in its old parent window. Recreate the
      // public fixture session on the next ready callback; old close listeners cannot close it.
      if (view) { view->close(); }
      view.reset();
      resources->close();
      window = nullptr;
      attempted = false;
    }
    if (!screen) { return; }
    observed_screen = screen;
    const std::weak_ptr<Host> weak = shared_from_this();
    layout_observer = screen->observe_layout(
        [weak, screen](const wm::DrawContext &ctx) {
          if (auto host = weak.lock(); host && host->observed_screen == screen && !host->closed) {
            try { host->ready(*screen, ctx); }
            catch (const std::exception &e) { host->error = e.what(); host->hide(); }
            catch (...) { host->error = "Native document layout synchronization failed"; host->hide(); }
          }
        },
        [weak, screen] {
          if (auto host = weak.lock(); host && host->observed_screen == screen) { host->hide(); }
        });
  }

  void ready(wm::Screen &screen, const wm::DrawContext &ctx)
  {
    // The observer sees every completed layout, including when this owner is hidden. Only
    // this callback borrows resolved Regions/UI; no widget or layout pointer is retained.
    // This layout hook does not establish same-event-batch native input interception.
    if (!owner || !ctx.ui || !ctx.window || &ctx.window->screen() != &screen) { hide(); return; }
    wm::Region *main = nullptr;
    for (auto *region : screen.visible_regions()) {
      auto *area = dynamic_cast<app::EditorArea *>(region->area());
      if (area && &area->editor() == owner && region->name() == app::EditorArea::kMain &&
          !region->rect().empty()) {
        main = region;
        break;
      }
    }
    if (!main) { hide(); return; }
    const auto rect = main->rect();
    const auto capture = screen.capture();
    if (capture == wm::Screen::Capture::Splitter || capture == wm::Screen::Capture::RegionEdge) {
      hide(); return;
    }
    for (const auto &block : ctx.ui->blocks()) {
      if (block->kind() == ui::Block::Kind::Modal ||
          (block->kind() != ui::Block::Kind::Region &&
           !block->frame().intersect(screen.to_ui(rect)).empty())) {
        // Every modal owns the whole window's input; other floating blocks hide this child
        // when they overlap. The prototype still occupies the whole main region.
        hide(); return;
      }
    }
    if (!attempted) {
      attempted = true;
      if (!resources || !resources->active()) {
        resources = make_fixture(error);
        if (!resources) { return; }
      }
      window = ctx.window;
      const std::weak_ptr<Host> weak = shared_from_this();
      window->add_close_listener([weak](wm::Window &closing) {
        if (auto host = weak.lock(); host && host->window == &closing) { host->close(); }
      });
      view = create_native_document_view(window->native_window_handle(), resources, error);
      if (view) { load("index.html"); }
    }
    if (!view || window != ctx.window) { hide(); return; }
    last_bounds = {rect.xmin, rect.ymin, rect.width(), rect.height()};
    view->set_bounds(last_bounds);
    desired_visible = true;
    view->set_visible(true);
  }
};

class DocumentEditor final : public app::Editor {
 public:
  DocumentEditor(const app::EditorType &type, std::shared_ptr<Host> host)
      : Editor(type), host_(std::move(host))
  {
    host_->owner = this;
  }
  ~DocumentEditor() override
  {
    host_->owner = nullptr;
    host_->close();
  }
  void draw_header(ui::Layout &row, app::EditorContext &) override
  {
    const auto host = host_;
    row.button("html", "HTML", [host] { host->load("index.html"); }).width(2.5f);
    row.button("pdf", "PDF", [host] { host->load("fixture.pdf"); }).width(2.5f);
    row.button("focus", "Focus", [host] { if (host->view) { host->view->focus(); } }).width(2.5f);
  }
  void draw_main(ui::Layout &layout, app::EditorContext &ctx) override
  {
    host_->observe(ctx.area.screen());
    layout.label("Native document preview experiment");
    if (!host_->error.empty()) { layout.label(host_->error); }
    if (host_->view) { layout.label(host_->view->state().message); }
    layout.label("The native child is hidden while an overlapping STK menu is open.");
    layout.label("Linux: no document backend selected. No model or bridge is started.");
  }

 private:
  std::shared_ptr<Host> host_;
};

struct Options {
  gfx::Backend backend = gfx::Backend::OpenGL;
  bool smoke = false;
  bool require_native = false;
  int cycles = 2;
  std::filesystem::path evidence_dir;
  std::string_view memory_gate_selftest;
};

void check(bool condition, const char *message)
{
  std::printf("%s: %s\n", condition ? "ok" : "FAIL", message);
  std::fflush(stdout);
  if (!condition) { throw std::runtime_error(message); }
}

class Evidence {
 public:
  explicit Evidence(const std::filesystem::path &directory) : directory_(directory)
  {
    std::filesystem::create_directories(directory_);
    run_id_ = "run-" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count());
    if (!std::filesystem::create_directory(directory_ / run_id_)) {
      throw std::runtime_error("evidence run directory already exists");
    }
    report_ = {{"format", "stk.native-preview-evidence/1"}, {"status", "running"},
               {"required_cycles", 20}, {"completed_cycles", 0}, {"require_native", true},
               {"images", nlohmann::json::array()}, {"closed_sessions", nlohmann::json::array()},
               {"parent_closed", false}, {"guarded_stk_leaks", nullptr},
               {"claim", "OS-composited STK client captures and native lifecycle; not physical scanout, PDF/IME acceptance or browser memory stability"}};
    save();
  }
  bool pixels(wm::Window &window, const Host &host, const NativeViewState &state,
              int cycle, int phase, int page)
  {
    const auto key = std::to_string(cycle) + "-" + std::to_string(phase);
    if (key_ != key) { key_ = key; capture_.reset(); consecutive_ = 0; }
    if (!capture_) {
      capture_ = capture_window_evidence(window.native_window_handle());
      return false;
    }
    auto result = capture_->poll();
    if (!result) { return false; }
    capture_.reset();
    if (!result->error.empty()) { throw std::runtime_error(result->error); }
    const auto &image = result->image;
    const auto b = host.last_bounds;
    if (image.channels != 4 || image.width != uint32_t(window.width()) ||
        image.height != uint32_t(window.height()) || b.x < 0 || b.y < 0 ||
        b.width <= 0 || b.height <= 0 || b.x + b.width > window.width() ||
        b.y + b.height > window.height()) {
      throw std::runtime_error("OS client screenshot does not match STK framebuffer geometry");
    }
    io::Image document(uint32_t(b.width), uint32_t(b.height));
    const int top = window.height() - b.y - b.height;
    for (int y = 0; y < b.height; ++y) {
      std::copy_n(image.pixel(uint32_t(b.x), uint32_t(top + y)), size_t(b.width) * 4,
                  document.row(uint32_t(y)));
    }
    // Require chromatic host pixels outside the document rectangle as a blank-frame check.
    // This count alone is not a proof that a particular Viewer object was rendered.
    size_t host_pixels = 0;
    for (uint32_t y = 0; y < image.height; y += 2) for (uint32_t x = 0; x < image.width; x += 2) {
      if (int(x) >= b.x && int(x) < b.x + b.width && int(y) >= top && int(y) < top + b.height) { continue; }
      const auto *p = image.pixel(x, y);
      if (int(std::max({p[0], p[1], p[2]})) - int(std::min({p[0], p[1], p[2]})) > 45) { ++host_pixels; }
    }
    const bool first = evidence_marker(document, 1), second = evidence_marker(document, 2);
    const bool matched = host_pixels >= 256 &&
        (page == 0 ? !evidence_marker(image, 1) && !evidence_marker(image, 2) :
                     (page == 1 ? first && !second : second && !first));
    if (!matched) { consecutive_ = 0; }
    else { ++consecutive_; }
    const auto bytes = io::encode_png(image);
    const auto name = run_id_ + "/cycle-" + std::to_string(cycle) + "-phase-" +
                      std::to_string(phase) + (consecutive_ >= 2 ? ".png" : "-waiting.png");
    core::write_file_atomic(directory_ / name, bytes);
    nlohmann::json observation = {{"file", name}, {"sha256", core::Sha256::hex(bytes)},
        {"width", image.width}, {"height", image.height}, {"capture_backend", result->backend},
        {"cycle", cycle}, {"phase", phase}, {"expected_page", page},
        {"consecutive_matches", consecutive_}, {"host_colored_samples", host_pixels},
        {"page_one_marker", first}, {"page_two_marker", second},
        {"parent_attached", state.parent_attached}, {"visible", state.visible},
        {"native_status", int(state.status)}, {"navigation_generation", state.navigation_generation},
        {"runtime_version", state.runtime_version},
        {"session_id", host.resources->identity().session_id},
        {"native_bounds_bottom_left", {b.x, b.y, b.width, b.height}}};
    report_["last_observation"] = observation;
    if (consecutive_ >= 2) { report_["images"].push_back(std::move(observation)); }
    save();
    return consecutive_ >= 2;
  }
  void closed(int cycle, const Host &host, const std::string &old_url)
  {
    const auto s = host.view->state();
    report_["closed_sessions"].push_back({{"cycle", cycle},
        {"session_id", host.resources->identity().session_id},
        {"closed", s.status == NativeViewStatus::Closed}, {"parent_attached", s.parent_attached},
        {"visible", s.visible}, {"old_url_status", host.resources->read(old_url).status}});
    report_["completed_cycles"] = cycle;
    save();
  }
  void parent_closed(const Host &host, const std::string &old_url)
  {
    const auto state = host.view->state();
    report_["parent_close"] = {{"session_id", host.resources->identity().session_id},
        {"closed", state.status == NativeViewStatus::Closed},
        {"parent_attached", state.parent_attached}, {"visible", state.visible},
        {"session_active", host.resources->active()},
        {"old_url_status", host.resources->read(old_url).status}};
    report_["parent_closed"] = true;
    save();
  }
  void stop_capture() { capture_.reset(); }
  void runtime_shutdown(unsigned int blocks)
  {
    // Live first-use engine statics are not leaks yet; preserve the pre-exit diagnostic.
    report_["guarded_stk_blocks_after_runtime"] = blocks;
    save();
  }
  void final_memory(unsigned int blocks, size_t bytes)
  {
    report_["guarded_stk_leaks"] = blocks;
    report_["guarded_stk_bytes"] = bytes;
    report_["guarded_stk_check_boundary"] = "after_engine_static_destructors";
    save();
  }
  void finish()
  {
    if (report_["guarded_stk_leaks"] != 0 || report_["guarded_stk_bytes"] != 0 ||
        report_["guarded_stk_check_boundary"] != "after_engine_static_destructors" ||
        report_["completed_cycles"] != 20 || report_["images"].size() != 161 ||
        report_["closed_sessions"].size() != 20 || report_["parent_closed"] != true) {
      throw std::runtime_error("Native evidence is incomplete");
    }
    report_["status"] = "passed";
    save();
  }
  void failed(const char *message)
  {
    capture_.reset(); report_["status"] = "failed"; report_["error"] = message; save();
  }
 private:
  void save()
  {
    const auto text = report_.dump(2) + "\n";
    core::write_file_atomic(directory_ / "result.json",
        {reinterpret_cast<const uint8_t *>(text.data()), text.size()});
  }
  std::filesystem::path directory_;
  std::string run_id_, key_;
  nlohmann::json report_;
  std::unique_ptr<WindowEvidenceCapture> capture_;
  int consecutive_ = 0;
};

struct FinalGate {
  std::unique_ptr<Evidence> evidence;
  bool completed = false;
};

FinalGate &final_gate()
{
  // Construct this std-only owner before Runtime: it must outlive the at-exit gate and
  // allocator counters. Evidence retains no engine/GPU objects; capture is stopped first.
  static FinalGate gate;
  return gate;
}

struct LateGuardedStatic {
  void *allocation = MEM_new_uninitialized(64, "stk-document-preview-spike late-static self-test");
  LateGuardedStatic()
  {
    if (!allocation) { throw std::runtime_error("Cannot allocate late guarded static self-test"); }
    static_cast<unsigned char *>(allocation)[0] = 0x5a;
    std::printf("self-test: late guarded static constructed after gate registration\n");
  }
  ~LateGuardedStatic()
  {
    MEM_delete_void(allocation);
    std::printf("self-test: late guarded static destroyed before final gate\n");
  }
};

LateGuardedStatic &late_guarded_static()
{
  static LateGuardedStatic allocation;
  return allocation;
}

int run_memory_gate_selftest(std::string_view mode)
{
  // Exercise the same Runtime/at-exit path without creating a WM, GPU or native view.
  (void)late_guarded_static();
  if (mode == "leak") {
    void *leaked = MEM_new_uninitialized(64, "stk-document-preview-spike deliberate self-test leak");
    if (!leaked) { throw std::runtime_error("Cannot allocate deliberate guarded self-test leak"); }
    static_cast<unsigned char *>(leaked)[0] = 0x6b;
    std::printf("self-test: deliberate 64-byte guarded leak allocated\n");
  }
  else if (mode == "early-failure") {
    throw std::runtime_error("controlled early memory-gate self-test failure");
  }
  return 0;
}

void record_failure(Evidence *evidence, const char *message) noexcept
{
  if (evidence) {
    try { evidence->failed(message); }
    catch (const std::exception &error) {
      std::fprintf(stderr, "FAIL: writing native evidence result: %s\n", error.what());
    }
    catch (...) { std::fprintf(stderr, "FAIL: writing native evidence result raised an unknown error\n"); }
  }
  std::fprintf(stderr, "FAIL: %s\n", message);
}

void final_memory_gate() noexcept
{
  auto &gate = final_gate();
  try {
    // Registered after Runtime initializes guardedalloc, but before run() can construct
    // Metal's first-use statics. Reverse exit order is engine statics -> this gate ->
    // guardedalloc's MemLeakPrinter -> allocator counters. Never subtract a baseline.
    const auto blocks = gfx::Runtime::memory_blocks_in_use();
    const auto bytes = MEM_get_memory_in_use();
    std::printf("guardedalloc: final blocks=%u bytes=%zu after engine static destruction\n", blocks, bytes);
    if (blocks != 0) { MEM_printmemlist(); }
    if (gate.evidence) { gate.evidence->final_memory(blocks, bytes); }
    if (blocks != 0 || bytes != 0) { throw std::runtime_error("guarded STK allocations remain after engine static destruction"); }
    if (!gate.completed) {
      // main already recorded an earlier run failure. Zero final blocks must not turn
      // a failed lifecycle/capture into passed evidence, even if a caller exits with 0.
      std::printf("guardedalloc: final zero does not override earlier run failure\n");
      std::fflush(stdout); std::fflush(stderr);
      std::_Exit(EXIT_FAILURE);
    }
    if (gate.evidence) {
      gate.evidence->finish();
      std::printf("PASS: native document evidence; cycles=20; OS client images=161; guarded STK leaks=0\n");
    }
    std::printf("ok: no guarded STK allocation leaks after engine static destruction\n");
    std::fflush(stdout); std::fflush(stderr);
    // The existing fail-on-leak MemLeakPrinter still runs after this successful gate.
    return;
  }
  catch (const std::exception &error) { record_failure(gate.evidence.get(), error.what()); }
  catch (...) { record_failure(gate.evidence.get(), "Final guarded STK memory validation raised an unknown error"); }
  std::fflush(stdout); std::fflush(stderr);
  // at-exit callbacks cannot return an exit status. A failed final gate must override
  // main's otherwise-successful return and must never emit successful evidence.
  std::_Exit(EXIT_FAILURE);
}

int run(const Options &options, Evidence *evidence)
{
  std::vector<std::weak_ptr<Host>> hosts;
  app::AppShell shell({.language = "en", .interactive = true});
  shell.registry().add({kEditor, "Document preview (spike)", [&](const app::EditorType &type) {
    auto host = std::make_shared<Host>();
    hosts.push_back(host);
    return std::make_unique<DocumentEditor>(type, std::move(host));
  }});
  wm::WmOptions wm_options;
  wm_options.gpu.backend = options.backend;
  wm_options.window = {"STK document preview experiment", 1440, 1000, false};
  std::string error;
  auto manager = wm::WindowManager::create(wm_options, error);
  if (!manager) { throw std::runtime_error(error); }
  auto *window = manager->main_window();
  shell.install(window->screen(), window);
  shell.build_default_layout(window->screen());
  auto *area = dynamic_cast<app::EditorArea *>(window->screen().find_area("a3"));
  check(area && area->set_tabs({kEditor, app::kEditorPython}, 0), "fixture document and Python tabs created");
  auto &viewer = shell.store().viewer();
  auto fixture_payload = core::path_from_utf8(gfx::executable_dir()) / "document-preview-payload";
  if (!std::filesystem::is_directory(fixture_payload)) { fixture_payload = STK_DOCUMENT_PREVIEW_PAYLOAD_DIR; }
  check(viewer.open_path(core::path_to_utf8(fixture_payload)), "public fixture opened beside document in Viewer");
  const auto viewer_source = viewer.source_label();
  // Status refresh also gives the async browser startup a running native message loop.
  manager->add_timer(100, 100, [&] {
    for (const auto &w : manager->windows()) { w->request_redraw(); }
  });

  int phase = 0;
  int cycles = 0;
  uint64_t previous_frame = 0;
  uint64_t generation = 0;
  std::shared_ptr<Host> closing_host;
  std::string old_identity, old_url;
  const bool native = window->native_window_handle().kind != wm::NativeWindowKind::Unsupported;
  check(!options.require_native || native, "requested native platform is available");
  auto phase_start = std::chrono::steady_clock::now();
  auto next_phase = [&](int value) {
    phase = value;
    previous_frame = window->frames_drawn();
    phase_start = std::chrono::steady_clock::now();
    window->request_redraw();
  };
  while (manager->process(true)) {
    std::erase_if(hosts, [](const auto &host) { return host.expired(); });
    if (!options.smoke) { continue; }
    if (manager->main_window() != window) { throw std::runtime_error("fixture window closed before smoke completed"); }
    if (std::chrono::steady_clock::now() - phase_start > std::chrono::seconds(45)) {
      throw std::runtime_error("native preview cycle " + std::to_string(cycles + 1) +
                               " phase " + std::to_string(phase) + " timed out");
    }
    if (hosts.empty()) { throw std::runtime_error("document host missing"); }
    auto host = hosts.back().lock();
    if (!host || !host->view || window->frames_drawn() <= previous_frame) { continue; }
    const auto state = host->view->state();
    if (state.status == NativeViewStatus::Failed) { throw std::runtime_error(state.message); }
    int document_tab = -1, python_tab = -1;
    for (int i = 0; i < area->tab_count(); ++i) {
      if (area->tab(i).type().id == kEditor) { document_tab = i; }
      if (area->tab(i).type().id == app::kEditorPython) { python_tab = i; }
    }
    const auto ready = [&] {
      return native ? state.status == NativeViewStatus::Ready && state.parent_attached && state.visible :
                      state.status == NativeViewStatus::Unsupported && !state.parent_attached && !state.visible;
    };
    const auto pixels = [&](int page) {
      return !evidence || evidence->pixels(*window, *host, state, cycles + 1, phase, page);
    };
    switch (phase) {
      case 0:
        if (!ready() || !pixels(1)) { break; }
        std::printf("runtime: %s; native=%d; cycle=%d\n", state.runtime_version.c_str(), int(native), cycles + 1);
        check(host->desired_visible, "active document occupies a visible STK region");
        area->set_active_tab(python_tab);
        check(!host->desired_visible && !host->view->state().visible,
              "tab change immediately withdraws native visibility before the next layout");
        next_phase(1);
        break;
      case 1:
        check(!host->desired_visible && !state.visible, "switching to Python hides the native document");
        if (!pixels(0)) { break; }
        area->set_active_tab(document_tab);
        next_phase(2);
        break;
      case 2:
        if (!ready() || !pixels(1)) { break; }
        window->screen().set_maximized(window->screen().find_area("a2"));
        check(!host->desired_visible && !host->view->state().visible,
              "maximization immediately withdraws native visibility before the next layout");
        next_phase(3);
        break;
      case 3:
        check(!host->desired_visible && !state.visible, "maximizing Viewer hides the other area's document");
        if (!pixels(0)) { break; }
        window->screen().set_maximized(nullptr);
        next_phase(4);
        break;
      case 4:
        if (!ready() || !pixels(1)) { break; }
        generation = state.navigation_generation;
        host->load("next.html");
        next_phase(5);
        break;
      case 5:
        if (!ready()) { break; }
        check(!native || state.navigation_generation > generation, "admitted navigation has a new generation");
        if (!pixels(2)) { break; }
        window->set_client_size(1280, 900);
        next_phase(6);
        break;
      case 6: {
        if (!ready() || !pixels(2)) { break; }
        check(viewer.source_label() == viewer_source && viewer.evaluations_started() == 0 &&
                  shell.store().scripts().history().empty(), "Viewer source preserved; no evaluation or Python run");
        old_url = host->resources->url("index.html");
        old_identity = host->resources->identity().session_id;
        closing_host = host;
        area->close_tab(document_tab);
        check(!host->layout_observer && host->observed_screen == nullptr &&
                  host->view->state().status == NativeViewStatus::Closed &&
                  !host->view->state().parent_attached && !host->view->state().visible &&
                  host->resources->read(old_url).status == 410,
              "closing tab removes native child and invalidates the old resource session");
        next_phase(7);
        break;
      }
      case 7: {
        check(state.status == NativeViewStatus::Closed && !state.parent_attached && !state.visible,
              "closed native view stays detached while Python remains visible");
        if (!pixels(0)) { break; }
        if (evidence) { evidence->closed(cycles + 1, *host, old_url); }
        closing_host.reset();
        if (++cycles < options.cycles) {
          window->set_client_size(1440, 1000);
          check(area->add_tab(kEditor, true), "reopen document in the existing area");
          auto fresh = hosts.back().lock();
          check(fresh && fresh->resources->identity().session_id != old_identity,
                "reopened document has an independent resource session");
          next_phase(0);
        }
        else {
          check(area->add_tab(kEditor, true), "create final document for parent-close validation");
          next_phase(8);
        }
        break;
      }
      case 8:
        if (!ready() || !pixels(1)) { break; }
        old_url = host->resources->url("index.html");
        host->load("next.html");
        manager->close_window(window);
        check(!host->layout_observer && host->observed_screen == nullptr &&
                  host->view->state().status == NativeViewStatus::Closed &&
                  !host->view->state().parent_attached && !host->view->state().visible &&
                  !host->resources->active(),
              "parent close invalidates view before native window destruction");
        if (evidence) { evidence->parent_closed(*host, old_url); }
        std::printf("PASS: document preview; cycles=%d; backend=%s; native=%d\n",
                    cycles, native ? "platform" : "unsupported", int(native));
        return 0;
    }
  }
  if (options.smoke) { throw std::runtime_error("smoke did not finish"); }
  return 0;
}
}  // namespace

int main(int argc, char **argv)
{
  Options options;
#ifdef __APPLE__
  options.backend = gfx::Backend::Metal;
#endif
  for (int i = 1; i < argc; ++i) {
    const std::string_view arg = argv[i];
    if (arg == "--smoke") { options.smoke = true; }
    else if (arg == "--require-native") { options.require_native = true; }
    else if (arg == "--memory-gate-selftest" && i + 1 < argc) {
      options.memory_gate_selftest = argv[++i];
      if (argc != 3 || (options.memory_gate_selftest != "late-static" &&
                        options.memory_gate_selftest != "leak" &&
                        options.memory_gate_selftest != "early-failure")) {
        std::fprintf(stderr, "memory-gate self-test requires exactly one mode: late-static, leak or early-failure\n");
        return 2;
      }
    }
    else if (arg == "--gpu-backend" && i + 1 < argc) {
      if (!gfx::parse_backend(argv[++i], options.backend)) { std::fprintf(stderr, "unknown GPU backend\n"); return 2; }
    }
    else if (arg == "--evidence-dir" && i + 1 < argc) {
      options.evidence_dir = core::path_from_utf8(argv[++i]);
    }
    else if (arg == "--cycles" && i + 1 < argc) {
      const std::string_view count = argv[++i];
      const auto result = std::from_chars(count.data(), count.data() + count.size(), options.cycles);
      if (result.ec != std::errc{} || result.ptr != count.data() + count.size() ||
          options.cycles < 1 || options.cycles > 100) { std::fprintf(stderr, "cycles must be 1..100\n"); return 2; }
    }
    else {
      std::fprintf(stderr, "usage: stk-document-preview-spike [--smoke] [--require-native] [--cycles 1..100] [--gpu-backend BACKEND] [--evidence-dir DIR] | --memory-gate-selftest {late-static|leak|early-failure}\n");
      return arg == "--help" ? 0 : 2;
    }
  }
  if (((options.smoke && options.require_native) || !options.evidence_dir.empty()) &&
      (!options.smoke || !options.require_native || options.cycles != 20 || options.evidence_dir.empty())) {
    std::fprintf(stderr, "native acceptance requires --smoke --require-native --cycles 20 --evidence-dir DIR\n");
    return 2;
  }
  auto &gate = final_gate();
  try {
    if (!options.evidence_dir.empty()) { gate.evidence = std::make_unique<Evidence>(options.evidence_dir); }
    if (gate.evidence) {
      const auto environment_error = native_evidence_environment_error();
      if (!environment_error.empty()) { throw std::runtime_error(environment_error); }
    }
    int result;
    {
      gfx::Runtime runtime;
      if (std::atexit(final_memory_gate) != 0) {
        throw std::runtime_error("Cannot register final guarded STK memory validation");
      }
      try {
        result = options.memory_gate_selftest.empty() ? run(options, gate.evidence.get()) :
                                                       run_memory_gate_selftest(options.memory_gate_selftest);
      }
      catch (...) {
        if (gate.evidence) { gate.evidence->stop_capture(); }
        throw;
      }
      if (gate.evidence) { gate.evidence->stop_capture(); }
    }
    const auto blocks = gfx::Runtime::memory_blocks_in_use();
    std::printf("guardedalloc: %u live block(s) before engine static destruction; final gate pending\n", blocks);
    if (blocks != 0) { MEM_printmemlist(); } // Allocation labels, not user document bytes.
    if (gate.evidence) { gate.evidence->runtime_shutdown(blocks); }
    if (!options.memory_gate_selftest.empty()) {
      check(blocks >= 1 && MEM_get_memory_in_use() >= 64 &&
                static_cast<unsigned char *>(late_guarded_static().allocation)[0] == 0x5a,
            "guarded self-test static remains live after Runtime");
    }
    if (result != 0) { throw std::runtime_error("Native document lifecycle did not complete successfully"); }
    gate.completed = true;
    return result;
  }
  catch (const std::exception &error) {
    record_failure(gate.evidence.get(), error.what()); return EXIT_FAILURE;
  }
  catch (...) {
    record_failure(gate.evidence.get(), "Native document validation raised an unknown error"); return EXIT_FAILURE;
  }
}
