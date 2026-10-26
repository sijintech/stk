/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "../wm/support.hh"
#include "stk/app/app_store.hh"
#include "stk/app/report_document_host.hh"

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
}  // namespace
}  // namespace stk::app
