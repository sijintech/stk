/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Opt-in native child-view experiment. It never opens a user project or starts a bridge. */
#include "fixture.hh"
#include "native_document_view.hh"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstdio>
#include <exception>
#include <stdexcept>

#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/gfx/gpu.hh"
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

  Host()
  {
    resources = make_fixture(error);
    if (!resources) { throw std::runtime_error(error); }
  }
  ~Host() { close(); }

  void close()
  {
    if (view) { view->close(); }
    resources->close();
    window = nullptr;
    desired_visible = false;
  }

  void load(std::string_view path)
  {
    if (view) { view->navigate(path, error); }
    if (window) { window->request_redraw(); }
  }

  void sync(wm::WindowManager &manager)
  {
    wm::Window *shown_window = nullptr;
    wm::Region *main = nullptr;
    // Re-resolve after every event/draw, including hidden tabs and maximized OTHER areas.
    // A stored Region pointer or on_layout alone misses these cases and can outlive a layout.
    for (const auto &candidate : manager.windows()) {
      auto &screen = candidate->screen();
      for (auto *region : screen.visible_regions()) {
        auto *area = dynamic_cast<app::EditorArea *>(region->area());
        if (owner && area && &area->editor() == owner &&
            region->name() == app::EditorArea::kMain && !region->rect().empty()) {
          shown_window = candidate.get();
          main = region;
          break;
        }
      }
      if (main) { break; }
    }
    if (main && !attempted) {
      attempted = true;
      window = shown_window;
      const std::weak_ptr<Host> weak = shared_from_this();
      window->add_close_listener([weak](wm::Window &) {
        if (auto host = weak.lock()) { host->close(); }
      });
      view = create_native_document_view(window->native_window_handle(), resources, error);
      if (view) { load("index.html"); }
    }
    if (!view || !window) { return; }
    bool show = main && shown_window == window;
    if (show) {
      const auto rect = main->rect();
      view->set_bounds({rect.xmin, rect.ymin, rect.width(), rect.height()});
      const auto &screen = window->screen();
      const auto capture = screen.capture();
      if (capture == wm::Screen::Capture::Splitter || capture == wm::Screen::Capture::RegionEdge) {
        show = false;
      }
      if (auto *ui = screen.ui()) {
        for (const auto &block : ui->blocks()) {
          if (block->kind() != ui::Block::Kind::Region &&
              !block->frame().intersect(screen.to_ui(rect)).empty()) {
            // Windowed children cannot be painted over by our GPU menus. This temporary hide
            // is an explicit prototype tradeoff, not evidence of seamless overlay composition.
            show = false;
            break;
          }
        }
      }
    }
    desired_visible = show;
    view->set_visible(show);
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
  void draw_main(ui::Layout &layout, app::EditorContext &) override
  {
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
};

void check(bool condition, const char *message)
{
  std::printf("%s: %s\n", condition ? "ok" : "FAIL", message);
  std::fflush(stdout);
  if (!condition) { throw std::runtime_error(message); }
}

int run(const Options &options)
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
  check(viewer.open_path(STK_DOCUMENT_PREVIEW_PAYLOAD_DIR), "public fixture opened beside document in Viewer");
  const auto viewer_source = viewer.source_label();
  // Status refresh also gives the async browser startup a running native message loop.
  manager->add_timer(100, 100, [&] {
    for (const auto &w : manager->windows()) { w->request_redraw(); }
  });

  int phase = 0;
  int cycles = 0;
  uint64_t previous_frame = 0;
  uint64_t generation = 0;
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
    for (const auto &weak : hosts) { if (auto host = weak.lock()) { host->sync(*manager); } }
    if (!options.smoke) { continue; }
    if (manager->main_window() != window) { throw std::runtime_error("fixture window closed before smoke completed"); }
    if (std::chrono::steady_clock::now() - phase_start > std::chrono::seconds(45)) {
      throw std::runtime_error("native preview smoke phase timed out");
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
    switch (phase) {
      case 0:
        if (!ready()) { break; }
        std::printf("runtime: %s; native=%d; cycle=%d\n", state.runtime_version.c_str(), int(native), cycles + 1);
        check(host->desired_visible, "active document occupies a visible STK region");
        area->set_active_tab(python_tab);
        next_phase(1);
        break;
      case 1:
        check(!host->desired_visible && !state.visible, "switching to Python hides the native document");
        area->set_active_tab(document_tab);
        next_phase(2);
        break;
      case 2:
        if (!ready()) { break; }
        window->screen().set_maximized(window->screen().find_area("a2"));
        next_phase(3);
        break;
      case 3:
        check(!host->desired_visible && !state.visible, "maximizing Viewer hides the other area's document");
        window->screen().set_maximized(nullptr);
        next_phase(4);
        break;
      case 4:
        if (!ready()) { break; }
        generation = state.navigation_generation;
        host->load("next.html");
        next_phase(5);
        break;
      case 5:
        if (!ready()) { break; }
        check(!native || state.navigation_generation > generation, "admitted navigation has a new generation");
        window->set_client_size(1280, 900);
        next_phase(6);
        break;
      case 6: {
        if (!ready()) { break; }
        check(viewer.source_label() == viewer_source && viewer.evaluations_started() == 0 &&
                  shell.store().scripts().history().empty(), "Viewer source preserved; no evaluation or Python run");
        const auto old_url = host->resources->url("index.html");
        const auto old_identity = host->resources->identity().session_id;
        area->close_tab(document_tab);
        check(host->view->state().status == NativeViewStatus::Closed &&
                  !host->view->state().parent_attached && !host->view->state().visible &&
                  host->resources->read(old_url).status == 410,
              "closing tab removes native child and invalidates the old resource session");
        if (++cycles < options.cycles) {
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
        if (!ready()) { break; }
        host->load("next.html");
        manager->close_window(window);
        check(host->view->state().status == NativeViewStatus::Closed && !host->resources->active(),
              "parent close invalidates view before native window destruction");
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
    else if (arg == "--gpu-backend" && i + 1 < argc) {
      if (!gfx::parse_backend(argv[++i], options.backend)) { std::fprintf(stderr, "unknown GPU backend\n"); return 2; }
    }
    else if (arg == "--cycles" && i + 1 < argc) {
      const std::string_view count = argv[++i];
      const auto result = std::from_chars(count.data(), count.data() + count.size(), options.cycles);
      if (result.ec != std::errc{} || result.ptr != count.data() + count.size() ||
          options.cycles < 1 || options.cycles > 100) { std::fprintf(stderr, "cycles must be 1..100\n"); return 2; }
    }
    else {
      std::fprintf(stderr, "usage: stk-document-preview-spike [--smoke] [--require-native] [--cycles 1..100] [--gpu-backend BACKEND]\n");
      return arg == "--help" ? 0 : 2;
    }
  }
  try {
    int result;
    { gfx::Runtime runtime; result = run(options); }
    check(gfx::Runtime::memory_blocks_in_use() == 0, "no guarded STK allocation leaks");
    return result;
  }
  catch (const std::exception &e) { std::fprintf(stderr, "FAIL: %s\n", e.what()); return 1; }
}
