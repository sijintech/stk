/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "../wm/support.hh"
#include "stk/app/app_store.hh"
#include "stk/app/report_document_host.hh"
#include "stk/gfx/gpu.hh"
#include "stk/wm/window.hh"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>

namespace stk::app {
namespace {
using document_preview::NativeViewStatus;
using document_preview::ResourceSession;

PreparedReportPreview prepared(const AppStore &store)
{
  PreparedReportPreview result;
  result.identity = {"11111111-1111-4111-8111-111111111111",
                     "22222222-2222-4222-8222-222222222222", std::string(64, 'a'),
                     "33333333-3333-4333-8333-333333333333"};
  result.entry_path = "render/report.html";
  const std::string html = "<!doctype html><meta charset=utf-8><h1>报告</h1>";
  result.assets = {{result.entry_path, "text/html; charset=utf-8", {html.begin(), html.end()}},
                   {"source/图片 #100%.png", "image/png", {0x89, 'P', 'N', 'G', 0, 0xff}}};
  result.project_scope_epoch = store.project_scope_epoch();
  return result;
}

TEST(ReportDocumentHost, AdmitsTheCompleteCollectionWithoutCreatingANativeWindow)
{
  AppStore store; int creates = 0;
  ReportDocumentHost host(store, [&](auto, auto, auto &) {
    ++creates; return std::unique_ptr<document_preview::NativeDocumentView>{};
  });
  auto source = prepared(store);
  const auto identity = source.identity;
  const auto expected = source.assets;
  ASSERT_TRUE(host.adopt(std::move(source)));
  ASSERT_TRUE(host.has_content()); EXPECT_EQ(creates, 0);
  EXPECT_EQ(host.state().status, NativeViewStatus::Loading);
  auto resources = host.session(); ASSERT_TRUE(resources);
  EXPECT_EQ(resources->identity().project_id, identity.project_id);
  EXPECT_EQ(resources->identity().resource_id, identity.report_id);
  EXPECT_EQ(resources->identity().source_version, identity.source_sha256);
  EXPECT_EQ(resources->identity().session_id, identity.session_id);
  for (const bool https : {false, true}) {
    for (const auto &asset : expected) {
      const auto url = resources->url(asset.path, https);
      ASSERT_FALSE(url.empty());
      const auto response = resources->read(url);
      EXPECT_EQ(response.status, 200); EXPECT_EQ(response.mime, asset.mime);
      EXPECT_EQ(response.bytes, asset.bytes);
    }
  }
  EXPECT_FALSE(host.state().parent_attached); EXPECT_FALSE(host.state().visible);
}

TEST(ReportDocumentHost, ScopeInvalidationRevokesBorrowedUrlsBeforeReturning)
{
  AppStore store; ReportDocumentHost host(store);
  ASSERT_TRUE(host.adopt(prepared(store)));
  const auto resources = host.session(); const auto url = resources->url("render/report.html");
  store.invalidate_project_scope();
  EXPECT_FALSE(host.has_content()); EXPECT_FALSE(resources->active());
  EXPECT_EQ(resources->read(url).status, 410); EXPECT_EQ(host.state().status, NativeViewStatus::Closed);
  EXPECT_FALSE(host.state().parent_attached); EXPECT_FALSE(host.state().visible);
}

TEST(ReportDocumentHost, ReaderClearSynchronouslyRevokesTheMovedCollection)
{
  AppStore store; ProjectReports reader(store); ReportDocumentHost host(store);
  reader.on_preview_invalidated = host.invalidator();
  ASSERT_TRUE(host.adopt(prepared(store)));
  auto resources = host.session(); const auto url = resources->url("render/report.html");
  reader.clear_preview();
  EXPECT_FALSE(host.has_content()); EXPECT_EQ(resources->read(url).status, 410);
  // Retained callbacks must remain harmless after the owning host disappears.
  std::function<void()> retained;
  { ReportDocumentHost another(store); retained = another.invalidator(); }
  EXPECT_NO_THROW(retained());
}

TEST(ReportDocumentHost, ReplacingTheSessionCannotReuseTheOldIdentityUrls)
{
  AppStore store; ReportDocumentHost host(store);
  ASSERT_TRUE(host.adopt(prepared(store)));
  const auto before = host.session(); const auto url = before->url("render/report.html");
  auto next = prepared(store); next.identity.session_id[0] = '4';
  ASSERT_TRUE(host.adopt(std::move(next)));
  EXPECT_EQ(before->read(url).status, 410);
  ASSERT_TRUE(host.session()); EXPECT_EQ(host.session()->read(url).status, 403);
}

TEST(ReportDocumentHost, ACollectionPreparedBeforeScopeChangeCannotBeReattached)
{
  AppStore store; ReportDocumentHost host(store);
  auto stale = prepared(store); store.invalidate_project_scope();
  EXPECT_FALSE(host.adopt(std::move(stale))); EXPECT_FALSE(host.has_content());
  EXPECT_EQ(host.state().status, NativeViewStatus::Failed);
  EXPECT_FALSE(host.state().message.empty());
  ASSERT_TRUE(host.adopt(prepared(store)));
  EXPECT_TRUE(host.has_content());
}

TEST(ReportDocumentHost, InvalidCollectionsFailClosedWithoutPublishingPartialResources)
{
  AppStore store; ReportDocumentHost host(store);
  for (int problem = 0; problem < 9; ++problem) {
    SCOPED_TRACE(problem);
    ASSERT_TRUE(host.adopt(prepared(store)));
    const auto old = host.session(); const auto url = old->url("render/report.html");
    auto invalid = prepared(store);
    if (problem == 0) { invalid.assets.clear(); }
    if (problem == 1) { invalid.entry_path = "missing.html"; }
    if (problem == 2) { invalid.assets[0].mime = "text/markdown"; }
    if (problem == 3) { invalid.assets[1].mime = "image/svg+xml"; }
    if (problem == 4) { invalid.assets[1].path = "../outside.png"; }
    if (problem == 5) { invalid.assets[1].path = invalid.entry_path; }
    if (problem == 6) { invalid.identity.source_sha256 = "not-a-sha"; }
    if (problem == 7) { invalid.identity.project_id = "../../other"; }
    if (problem == 8) { invalid.assets[1].bytes.resize(4 * 1024 * 1024 + 1); }
    EXPECT_FALSE(host.adopt(std::move(invalid)));
    EXPECT_FALSE(host.has_content()); EXPECT_FALSE(host.session());
    EXPECT_EQ(old->read(url).status, 410); EXPECT_EQ(host.state().status, NativeViewStatus::Failed);
  }
}

TEST(ReportDocumentHost, HiddenReadingRetainsBytesButClearAndDestructionRevokeThem)
{
  AppStore store; std::shared_ptr<const ResourceSession> borrowed; std::string url;
  {
    ReportDocumentHost host(store);
    ASSERT_TRUE(host.adopt(prepared(store)));
    borrowed = host.session(); url = borrowed->url("render/report.html");
    host.set_visible(false);
    EXPECT_EQ(borrowed->read(url).status, 200); EXPECT_FALSE(host.state().visible);
    host.clear(); EXPECT_EQ(borrowed->read(url).status, 410);
    ASSERT_TRUE(host.adopt(prepared(store)));
    borrowed = host.session(); url = borrowed->url("render/report.html");
  }
  EXPECT_EQ(borrowed->read(url).status, 410);
}

TEST(ReportDocumentHost, FrozenVideoIsAConfinedSubresourceAndPreparationCannotStartPlayback)
{
  AppStore store; int creates = 0;
  ReportDocumentHost host(store, [&](auto, auto, auto &) {
    ++creates; return std::unique_ptr<document_preview::NativeDocumentView>{};
  });
  auto video = prepared(store);
  video.assets.push_back({"media/视频 #100%.mp4", "video/mp4", {0, 0, 0, 16, 'f', 't', 'y', 'p'}});
  const auto expected = video.assets.back().bytes;
  ASSERT_TRUE(host.adopt(std::move(video))); ASSERT_TRUE(host.has_media());
  EXPECT_EQ(creates, 0); EXPECT_FALSE(host.pause_media()); // No native Window or player exists.
  const auto resources = host.session(); ASSERT_TRUE(resources);
  const auto url = resources->url("media/视频 #100%.mp4"); ASSERT_FALSE(url.empty());
  EXPECT_FALSE(resources->allows_navigation(url)); EXPECT_EQ(resources->read(url).bytes, expected);
  const auto part = resources->read(url, "GET", "bytes=4-7");
  EXPECT_EQ(part.status, 206); EXPECT_EQ(part.bytes, (std::vector<uint8_t>{'f', 't', 'y', 'p'}));
  host.set_visible(false); host.set_visible(true);
  EXPECT_EQ(creates, 0); EXPECT_EQ(resources->read(url).status, 200);
  store.invalidate_project_scope();
  EXPECT_FALSE(host.has_media()); EXPECT_FALSE(host.has_content()); EXPECT_EQ(resources->read(url).status, 410);
}

TEST(ReportDocumentHost, VideoRequiresAnHtmlPlayerAndRejectsUnsupportedMediaAtomically)
{
  AppStore store; ReportDocumentHost host(store);
  for (const auto &mime : {"video/mp4", "video/webm", "audio/mpeg"}) {
    auto invalid = prepared(store);
    if (std::string(mime) == "video/mp4") {
      invalid.entry_path = "movie.mp4"; invalid.assets = {{"movie.mp4", mime, {0, 1, 2}}};
    }
    else { invalid.assets.push_back({"media/movie", mime, {0, 1, 2}}); }
    EXPECT_FALSE(host.adopt(std::move(invalid))); EXPECT_FALSE(host.has_media()); EXPECT_FALSE(host.session());
  }
}

TEST(ReportDocumentHost, HeadlessLayoutNeverClaimsAttachmentAndChangingScreenRevokesSession)
{
  wmtest::AppFixture first, second; int creates = 0;
  auto &store = first.shell->store();
  ReportDocumentHost host(store, [&](auto, auto, auto &) {
    ++creates; return std::unique_ptr<document_preview::NativeDocumentView>{};
  });
  auto &area = first.area("a3");
  EditorContext ctx{store, area, first.screen.ui(), &first.drv->ctx};
  host.bind(area.editor(), ctx);
  ASSERT_TRUE(host.adopt(prepared(store)));
  const auto resources = host.session(); const auto url = resources->url("render/report.html");
  host.set_visible(true); first.drv->frame();
  EXPECT_EQ(creates, 0); EXPECT_TRUE(host.has_content());
  EXPECT_FALSE(host.state().parent_attached); EXPECT_FALSE(host.state().visible);
  auto &other = second.area("a3");
  EditorContext changed{store, other, second.screen.ui(), &second.drv->ctx};
  host.bind(other.editor(), changed);
  EXPECT_EQ(resources->read(url).status, 410); EXPECT_FALSE(host.has_content());
  EXPECT_EQ(creates, 0);
}

TEST(ReportDocumentHost, DestroyingTheScreenBeforeTheHostLeavesNoBorrowedLayoutCallback)
{
  wmtest::AppFixture fixture;
  auto &store = fixture.shell->store();
  ReportDocumentHost host(store);
  {
    wm::Screen temporary;
    fixture.shell->install(temporary, nullptr); fixture.shell->build_default_layout(temporary);
    auto *area = dynamic_cast<EditorArea *>(temporary.find_area("a3")); ASSERT_NE(area, nullptr);
    EditorContext ctx{store, *area}; host.bind(area->editor(), ctx);
    ASSERT_TRUE(host.adopt(prepared(store)));
    fixture.shell->forget(temporary);
  }
  // A subsequent adoption must not dereference the old Screen just to request a redraw.
  EXPECT_TRUE(host.adopt(prepared(store)));
  host.clear(); EXPECT_FALSE(host.has_content());
}

TEST(ReportDocumentHost, SingleBinaryPdfUsesTheSameConfinedIdentityAndImmediateRevocation)
{
  AppStore store; ReportDocumentHost host(store);
  auto pdf = prepared(store); pdf.entry_path = "报告 #100%.pdf";
  const std::vector<uint8_t> bytes = {'%', 'P', 'D', 'F', '-', '1', '.', '4', '\n', 0xff, 0, 0xfe};
  pdf.assets = {{pdf.entry_path, "application/pdf", bytes}};
  ASSERT_TRUE(host.adopt(std::move(pdf))); const auto resources = host.session(); ASSERT_TRUE(resources);
  const auto url = resources->url("报告 #100%.pdf");
  EXPECT_EQ(resources->read(url).status, 200); EXPECT_EQ(resources->read(url).mime, "application/pdf");
  EXPECT_EQ(resources->read(url).bytes, bytes);
  EXPECT_FALSE(host.state().parent_attached); EXPECT_FALSE(host.state().visible);
  store.invalidate_project_scope();
  EXPECT_FALSE(host.has_content()); EXPECT_EQ(resources->read(url).status, 410);
}

TEST(ReportDocumentHost, PdfRejectsSecondaryResourcesAndOversizedBinaryAtomically)
{
  AppStore store; ReportDocumentHost host(store);
  for (int problem = 0; problem < 4; ++problem) {
    SCOPED_TRACE(problem);
    ASSERT_TRUE(host.adopt(prepared(store))); const auto old = host.session();
    const auto old_url = old->url("render/report.html");
    auto pdf = prepared(store); pdf.entry_path = "document.pdf";
    pdf.assets = {{pdf.entry_path, "application/pdf", {'%', 'P', 'D', 'F', 0xff}}};
    if (problem < 3) {
      pdf.assets.push_back({"secondary", problem == 0 ? "image/png" : problem == 1 ? "text/html; charset=utf-8" : "application/pdf", {0}});
    }
    else { pdf.assets.front().bytes.resize(4 * 1024 * 1024 + 1); }
    EXPECT_FALSE(host.adopt(std::move(pdf))); EXPECT_FALSE(host.has_content()); EXPECT_FALSE(host.session());
    EXPECT_EQ(old->read(old_url).status, 410);
  }
}

TEST(ReportDocumentHost, PdfReplacementRevokesItsOldUrlsAndHtmlStillRejectsPdfAttachments)
{
  AppStore store; ReportDocumentHost host(store);
  auto pdf = prepared(store); pdf.entry_path = "document.pdf";
  pdf.assets = {{pdf.entry_path, "application/pdf", {'%', 'P', 'D', 'F', 0xff}}};
  ASSERT_TRUE(host.adopt(std::move(pdf))); const auto old = host.session(); const auto url = old->url("document.pdf");
  auto html = prepared(store); html.identity.session_id[0] = '4';
  ASSERT_TRUE(host.adopt(std::move(html))); EXPECT_EQ(old->read(url).status, 410);
  EXPECT_EQ(host.session()->read(url).status, 403);
  html = prepared(store); html.assets[1].mime = "application/pdf";
  EXPECT_FALSE(host.adopt(std::move(html))); EXPECT_FALSE(host.has_content());
}

// ---------------------------------------------------------------------------------------------
// Live window (Linux Xvfb only, dedicated filtered CTest): a real WindowManager/AppShell, an
// injected mock NativeDocumentView and ordinary Screen mouse input. This pins host sequencing
// only; it says nothing about any platform media backend.

#ifdef __linux__
struct ViewProbe {
  int index = 0;
  bool visible = false, closed = false, fail_pause = false, refuse_show = false;
  NativeViewStatus status = NativeViewStatus::Loading;
  int shows = 0;
  int hide_pauses = 0;
  std::vector<bool> pause_visible; // Child visibility at each native pause dispatch.
};
struct LiveFixture {
  std::unique_ptr<ReportDocumentHost> host;
  std::vector<std::shared_ptr<ViewProbe>> views;
  std::vector<std::string> log; // Ordered native calls across every created view.
  struct Click { bool visible_at_dispatch, accepted; };
  std::vector<Click> clicks;
};

class MockDocumentView final : public document_preview::NativeDocumentView {
 public:
  // The fixture owns the host that owns this view, so a borrowed pointer avoids a cycle.
  MockDocumentView(LiveFixture &fixture, std::shared_ptr<ViewProbe> probe)
      : fixture_(fixture), probe_(std::move(probe)) {}
  bool navigate(std::string_view, std::string &) override
  {
    note("navigate"); if (probe_->status == NativeViewStatus::Loading) { probe_->status = NativeViewStatus::Ready; }
    return true;
  }
  void set_bounds(document_preview::ViewBounds) override {}
  void set_visible(bool visible) override
  {
    if (probe_->closed) { return; }
    if (visible && probe_->refuse_show) { note("show-refused"); return; }
    note(visible ? "show" : "hide");
    if (visible && !probe_->visible) { ++probe_->shows; }
    probe_->visible = visible;
  }
  bool pause_media(std::string &error) override
  {
    note(probe_->visible ? "pause@visible" : "pause@hidden");
    probe_->pause_visible.push_back(probe_->visible);
    if (probe_->fail_pause) { error = "synthetic pause failure"; return false; }
    return true;
  }
  bool pause_media_for_hide(std::string &error) override
  {
    ++probe_->hide_pauses;
    return pause_media(error);
  }
  void focus() override {}
  void set_focus_exit_handler(document_preview::FocusExitHandler) override {}
  bool return_focus() override { return true; }
  void close() override
  {
    if (!probe_->closed) { note("close"); }
    probe_->closed = true; probe_->visible = false;
  }
  document_preview::NativeViewState state() const override
  {
    document_preview::NativeViewState result;
    result.parent_attached = !probe_->closed; result.visible = !probe_->closed && probe_->visible;
    result.status = probe_->closed ? NativeViewStatus::Closed : probe_->status;
    return result;
  }
 private:
  void note(const char *what) { fixture_.log.push_back("v" + std::to_string(probe_->index) + ":" + what); }
  LiveFixture &fixture_;
  std::shared_ptr<ViewProbe> probe_;
};

/** Mirrors the reading toolbar order of reports_editor.cc: anchor, Pause, viewport, anchor. */
class PauseFixtureEditor final : public Editor {
 public:
  PauseFixtureEditor(const EditorType &type, std::shared_ptr<LiveFixture> fixture)
      : Editor(type), fixture_(std::move(fixture)) {}
  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    if (!fixture_->host) { return; }
    auto &host = *fixture_->host;
    host.bind(*this, ctx);
    auto &row = layout.row(true);
    const auto previous = row.button("pause_fixture_before", "Before", [] {}).id;
    row.button("pause_fixture_pause", "Pause", [fixture = fixture_] {
      if (!fixture->host) { return; }
      const bool visible = fixture->host->state().visible;
      fixture->clicks.push_back({visible, fixture->host->pause_media()});
    });
    const auto viewport = layout.native_viewport("pause_fixture_viewport", 6.0f).id;
    const auto next = layout.button("pause_fixture_after", "After", [] {}).id;
    host.set_viewport(viewport, previous, next);
    host.set_visible(viewport != 0);
  }
 private:
  std::shared_ptr<LiveFixture> fixture_;
};

PreparedReportPreview video_preview(const AppStore &store, char session)
{
  auto result = prepared(store);
  result.identity.session_id[0] = session;
  result.assets.push_back({"media/clip.mp4", "video/mp4", {0, 0, 0, 16, 'f', 't', 'y', 'p'}});
  return result;
}

class LiveWindow {
 public:
  LiveWindow(wm::WindowManager &manager, wm::Window &window) : manager_(manager), window_(&window) {}
  bool wait(const std::function<bool()> &done, double seconds = 20)
  {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(seconds);
    while (current()) {
      if (done()) { return true; }
      if (std::chrono::steady_clock::now() >= deadline || !manager_.process(false)) { return false; }
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return false;
  }
  bool frame()
  {
    if (!current()) { return false; }
    const auto previous = window_->frames_drawn();
    window_->request_redraw();
    return wait([&] { return window_->frames_drawn() > previous; });
  }
  bool pointer(wm::EventType type, const std::string &key)
  {
    if (!current()) { return false; }
    auto &screen = window_->screen();
    const auto *widget = screen.ui() ? screen.ui()->find(key) : nullptr;
    if (!widget || !widget->enabled) { return false; }
    wm::Event e; e.type = type; e.window = window_; e.time_ms = manager_.time_ms();
    e.x = int(widget->rect.cx()); e.y = window_->height() - 1 - int(widget->rect.cy());
    if (type != wm::EventType::MouseMove) { e.button = wm::MouseButton::Left; }
    wm::DrawContext ctx; ctx.window = window_; ctx.fonts = &manager_.gpu().fonts();
    ctx.ui_scale = window_->ui_scale(); ctx.rect = {0, 0, window_->width(), window_->height()};
    ctx.ui = screen.ui(); ctx.now = double(e.time_ms) / 1000;
    screen.dispatch(e, ctx);
    if (!current()) { return false; }
    window_->request_redraw();
    return true;
  }
  bool press(const std::string &key)
  {
    return pointer(wm::EventType::MouseMove, key) && pointer(wm::EventType::MouseDown, key);
  }
 private:
  bool current() const { return !manager_.quitting() && manager_.main_window() == window_; }

  wm::WindowManager &manager_;
  wm::Window *const window_;
};

TEST(ReportDocumentHostDisplay, PauseClickCoalescesWithTheHidePauseAndNeverReusesOldAcceptance)
{
  // Same accounting as the window smokes: guarded blocks are counted after the Runtime ends.
  gfx::RuntimeOptions runtime_options; runtime_options.fail_on_leak = false;
  {
    gfx::Runtime runtime(runtime_options);
    AppShell shell({.language = "en", .interactive = false});
    wm::WmOptions options;
    options.window = {"STK report document pause test", 1280, 800, false};
    if (const char *backend = std::getenv("STK_TEST_GPU_BACKEND"); backend && *backend) {
      ASSERT_TRUE(gfx::parse_backend(backend, options.gpu.backend)) << backend;
    }
    std::string error;
    auto manager = wm::WindowManager::create(options, error);
    if (!manager) {
      const char *x11 = std::getenv("DISPLAY"), *wayland = std::getenv("WAYLAND_DISPLAY");
      if ((!x11 || !*x11) && (!wayland || !*wayland)) { GTEST_SKIP() << "no display: " << error; }
      FAIL() << "a display is configured but no window opened: " << error;
    }
    auto *window = manager->main_window(); ASSERT_NE(window, nullptr);
    auto &screen = window->screen();
    auto &store = shell.store();
    const auto fixture = std::make_shared<LiveFixture>();
    shell.registry().add({"report-pause-fixture", "editor.table.title", [fixture](const EditorType &type) {
      return std::make_unique<PauseFixtureEditor>(type, fixture);
    }});
    shell.install(screen, window); shell.build_default_layout(screen);
    auto *area = dynamic_cast<EditorArea *>(screen.find_area("a3")); ASSERT_NE(area, nullptr);
    ASSERT_TRUE(area->add_tab("report-pause-fixture", true));
    fixture->host = std::make_unique<ReportDocumentHost>(store, [raw = fixture.get()](auto, auto, auto &) {
      auto probe = std::make_shared<ViewProbe>(); probe->index = int(raw->views.size()) + 1;
      raw->views.push_back(probe);
      return std::unique_ptr<document_preview::NativeDocumentView>(new MockDocumentView(*raw, probe));
    });
    auto &host = *fixture->host;
    LiveWindow live(*manager, *window);
    const auto count = [&](const std::string &entry) {
      return int(std::count(fixture->log.begin(), fixture->log.end(), entry));
    };
    const auto shown = [&](size_t views) {
      return live.wait([&] {
        return fixture->views.size() == views && host.state().visible && host.state().parent_attached;
      });
    };
    ASSERT_TRUE(live.frame());
    ASSERT_TRUE(host.adopt(video_preview(store, '3'))); ASSERT_TRUE(host.has_media());
    ASSERT_TRUE(shown(1)) << "the mock child was never shown";
    auto v1 = fixture->views[0];
    EXPECT_TRUE(v1->pause_visible.empty()) << "showing must never pause or resume";

    {
      SCOPED_TRACE("hide pause plus explicit Pause in one hidden epoch: one native call");
      const auto log_before = fixture->log.size(); const auto pauses = v1->pause_visible.size();
      ASSERT_TRUE(live.press("pause_fixture_pause"));
      EXPECT_EQ(screen.capture(), wm::Screen::Capture::Ui);
      EXPECT_TRUE(fixture->clicks.empty()) << "mouse-down must not run the click handler";
      EXPECT_FALSE(v1->visible) << "mouse-down must invalidate the native viewport before the click";
      ASSERT_GE(fixture->log.size(), log_before + 2);
      EXPECT_EQ(fixture->log[log_before], "v1:pause@visible") << "a visible surface pauses before hiding";
      EXPECT_EQ(fixture->log[log_before + 1], "v1:hide");
      ASSERT_TRUE(live.frame()); // A real layout between down and up keeps the child hidden.
      EXPECT_FALSE(v1->visible); EXPECT_EQ(v1->pause_visible.size(), pauses + 1);
      EXPECT_EQ(v1->hide_pauses, 1);
      ASSERT_TRUE(live.pointer(wm::EventType::MouseUp, "pause_fixture_pause"));
      ASSERT_EQ(fixture->clicks.size(), 1u);
      EXPECT_FALSE(fixture->clicks[0].visible_at_dispatch);
      EXPECT_TRUE(fixture->clicks[0].accepted);
      EXPECT_EQ(v1->pause_visible.size(), pauses + 1) << "the explicit Pause superseded the hide pause";
      EXPECT_EQ(count("v1:pause@hidden"), 0);
      const int shows = v1->shows;
      ASSERT_TRUE(shown(1)) << "the child must reappear after release";
      EXPECT_EQ(v1->shows, shows + 1); EXPECT_EQ(v1->pause_visible.size(), pauses + 1);
    }
    {
      SCOPED_TRACE("after re-show every Pause reaches the view again");
      const auto pauses = v1->pause_visible.size();
      const auto hide_pauses = v1->hide_pauses;
      EXPECT_TRUE(host.pause_media());
      ASSERT_EQ(v1->pause_visible.size(), pauses + 1); EXPECT_TRUE(v1->pause_visible.back());
      EXPECT_EQ(v1->hide_pauses, hide_pauses);
      ASSERT_TRUE(live.press("pause_fixture_pause"));
      ASSERT_EQ(v1->pause_visible.size(), pauses + 2); EXPECT_TRUE(v1->pause_visible.back());
      EXPECT_EQ(v1->hide_pauses, hide_pauses + 1);
      ASSERT_TRUE(live.pointer(wm::EventType::MouseUp, "pause_fixture_pause"));
      ASSERT_EQ(fixture->clicks.size(), 2u); EXPECT_FALSE(fixture->clicks[1].visible_at_dispatch);
      EXPECT_TRUE(fixture->clicks[1].accepted);
      EXPECT_EQ(v1->pause_visible.size(), pauses + 2);
      ASSERT_TRUE(shown(1));
    }
    {
      SCOPED_TRACE("a show attempt the platform refuses still ends the hidden epoch");
      ASSERT_TRUE(live.press("pause_fixture_pause"));
      const auto pauses = v1->pause_visible.size(); EXPECT_TRUE(v1->pause_visible.back());
      v1->refuse_show = true;
      ASSERT_TRUE(live.pointer(wm::EventType::MouseUp, "pause_fixture_pause"));
      ASSERT_EQ(fixture->clicks.size(), 3u); EXPECT_TRUE(fixture->clicks[2].accepted);
      EXPECT_EQ(v1->pause_visible.size(), pauses);
      const auto refused = count("v1:show-refused");
      ASSERT_TRUE(live.wait([&] { return count("v1:show-refused") > refused; }));
      EXPECT_FALSE(host.state().visible);
      EXPECT_TRUE(host.pause_media());
      ASSERT_EQ(v1->pause_visible.size(), pauses + 1); EXPECT_FALSE(v1->pause_visible.back());
      v1->refuse_show = false;
      ASSERT_TRUE(shown(1));
    }
    {
      SCOPED_TRACE("a view that failed after the hide pause cannot reuse that acceptance");
      ASSERT_TRUE(live.press("pause_fixture_pause"));
      EXPECT_FALSE(v1->visible); EXPECT_TRUE(v1->pause_visible.back());
      v1->status = NativeViewStatus::Failed; v1->fail_pause = true; // Asynchronous platform failure.
      ASSERT_TRUE(live.pointer(wm::EventType::MouseUp, "pause_fixture_pause"));
      ASSERT_EQ(fixture->clicks.size(), 4u);
      EXPECT_FALSE(fixture->clicks[3].accepted);
      EXPECT_TRUE(v1->closed); EXPECT_EQ(host.state().status, NativeViewStatus::Failed);
      EXPECT_FALSE(host.has_content());
      ASSERT_TRUE(live.frame()); EXPECT_EQ(fixture->views.size(), 1u);
    }
    {
      SCOPED_TRACE("replacement while hidden: the old acceptance stays with the closed view");
      ASSERT_TRUE(host.adopt(video_preview(store, '4'))); ASSERT_TRUE(shown(2));
      auto v2 = fixture->views[1];
      ASSERT_TRUE(live.press("pause_fixture_pause"));
      ASSERT_EQ(v2->pause_visible.size(), 1u); EXPECT_TRUE(v2->pause_visible[0]);
      ASSERT_TRUE(host.adopt(video_preview(store, '5'))); // Replaced before the mouse is released.
      EXPECT_TRUE(v2->closed);
      ASSERT_TRUE(live.pointer(wm::EventType::MouseUp, "pause_fixture_pause"));
      ASSERT_EQ(fixture->clicks.size(), 5u); EXPECT_FALSE(fixture->clicks[4].accepted);
      EXPECT_EQ(v2->pause_visible.size(), 1u);
      ASSERT_TRUE(shown(3));
      auto v3 = fixture->views[2];
      EXPECT_TRUE(v3->pause_visible.empty());
      EXPECT_TRUE(host.pause_media());
      ASSERT_EQ(v3->pause_visible.size(), 1u); EXPECT_TRUE(v3->pause_visible[0]);
    }
    {
      SCOPED_TRACE("a failed hide pause closes the view; the click cannot claim acceptance");
      auto v3 = fixture->views[2];
      v3->fail_pause = true;
      ASSERT_TRUE(live.press("pause_fixture_pause"));
      ASSERT_EQ(v3->pause_visible.size(), 2u); EXPECT_TRUE(v3->pause_visible[1]);
      EXPECT_TRUE(v3->closed); EXPECT_EQ(host.state().status, NativeViewStatus::Failed);
      ASSERT_TRUE(live.pointer(wm::EventType::MouseUp, "pause_fixture_pause"));
      ASSERT_EQ(fixture->clicks.size(), 6u); EXPECT_FALSE(fixture->clicks[5].accepted);
      EXPECT_EQ(v3->pause_visible.size(), 2u);
      ASSERT_TRUE(live.frame()); EXPECT_EQ(fixture->views.size(), 3u);
    }
    {
      SCOPED_TRACE("scope invalidation while hidden keeps the original guard");
      ASSERT_TRUE(host.adopt(video_preview(store, '6'))); ASSERT_TRUE(shown(4));
      auto v4 = fixture->views[3];
      ASSERT_TRUE(live.press("pause_fixture_pause"));
      ASSERT_EQ(v4->pause_visible.size(), 1u);
      store.invalidate_project_scope();
      EXPECT_TRUE(v4->closed); EXPECT_FALSE(host.has_content());
      ASSERT_TRUE(live.pointer(wm::EventType::MouseUp, "pause_fixture_pause"));
      ASSERT_EQ(fixture->clicks.size(), 7u); EXPECT_FALSE(fixture->clicks[6].accepted);
      EXPECT_EQ(v4->pause_visible.size(), 1u);
      ASSERT_TRUE(live.frame()); EXPECT_EQ(fixture->views.size(), 4u);
    }
    {
      SCOPED_TRACE("closing the native window ends the wait and revokes the view");
      ASSERT_TRUE(host.adopt(video_preview(store, '7'))); ASSERT_TRUE(shown(5));
      const auto resources = host.session(); ASSERT_TRUE(resources);
      ASSERT_TRUE(manager->post([&] { manager->close_window(window); }));
      int probes = 0;
      EXPECT_FALSE(live.wait([&] { ++probes; return false; }));
      ASSERT_EQ(probes, 1);
      ASSERT_EQ(manager->main_window(), nullptr);
      EXPECT_FALSE(live.frame());
      EXPECT_FALSE(live.pointer(wm::EventType::MouseMove, "pause_fixture_pause"));
      EXPECT_TRUE(fixture->views[4]->closed);
      EXPECT_FALSE(host.has_content());
      EXPECT_FALSE(resources->active());
    }
    for (const auto &entry : fixture->log) { std::printf("native-call %s\n", entry.c_str()); }
    fixture->host.reset();
    manager.reset();
  }
  EXPECT_EQ(gfx::Runtime::memory_blocks_in_use(), 0u);
}
#endif
}  // namespace
}  // namespace stk::app
