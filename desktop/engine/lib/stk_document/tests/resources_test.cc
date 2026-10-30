/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/document/resources.hh"
#include "stk/document/media_pause_verification.hh"

#include <string>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

namespace stk::document_preview {
namespace {

TEST(DocumentResources, PauseWaitsForObservedNonPlayingStateWithinOriginalDeadline)
{
  using Check = detail::MediaPauseVerification;
  using namespace std::chrono_literals;
  const Check::Clock::time_point start{};
  Check check(7, 3, start);
  EXPECT_EQ(check.observe(true, 7, 3, start + 25ms), Check::Result::Waiting);
  EXPECT_EQ(check.observe(true, 7, 3, start + 50ms), Check::Result::Waiting);
  EXPECT_EQ(check.observe(false, 7, 3, start + 75ms), Check::Result::Paused);
  // A late Playing response and the independent watchdog cannot revoke a
  // completed verification or close a view after an explicit later play.
  EXPECT_EQ(check.observe(true, 7, 3, start + 80ms), Check::Result::Ignored);
  EXPECT_EQ(check.expire(7, 3, start + 2s), Check::Result::Ignored);
}

TEST(DocumentResources, PauseDeadlineCoversPlayingAndMissingCallbacksWithoutExtending)
{
  using Check = detail::MediaPauseVerification;
  using namespace std::chrono_literals;
  const Check::Clock::time_point start{};
  Check playing(1, 2, start), no_ack(1, 2, start), no_state_reply(1, 2, start);
  for (const auto offset : {25ms, 250ms, 500ms, 999ms}) {
    EXPECT_EQ(playing.observe(true, 1, 2, start + offset), Check::Result::Waiting);
  }
  EXPECT_EQ(playing.observe(true, 1, 2, start + 1s), Check::Result::Failed);
  EXPECT_EQ(no_ack.expire(1, 2, start + 1s), Check::Result::Failed);
  EXPECT_EQ(no_state_reply.expire(1, 2, start + 1s), Check::Result::Failed);
  // Even an otherwise successful response is too late at the absolute cutoff.
  Check late(1, 2, start);
  EXPECT_EQ(late.observe(false, 1, 2, start + 1s), Check::Result::Failed);
  EXPECT_EQ(late.observe(false, 1, 2, start + 1001ms), Check::Result::Ignored);
}

TEST(DocumentResources, PauseCallbacksCannotAffectAnotherPauseOrNavigation)
{
  using Check = detail::MediaPauseVerification;
  using namespace std::chrono_literals;
  const Check::Clock::time_point start{};
  Check check(11, 9, start);
  EXPECT_EQ(check.observe(false, 12, 9, start + 25ms), Check::Result::Ignored);
  EXPECT_EQ(check.observe(false, 11, 10, start + 25ms), Check::Result::Ignored);
  EXPECT_EQ(check.expire(12, 9, start + 2s), Check::Result::Ignored);
  EXPECT_EQ(check.expire(11, 10, start + 2s), Check::Result::Ignored);
  EXPECT_EQ(check.observe(true, 11, 9, start + 100ms), Check::Result::Waiting);
  EXPECT_EQ(check.observe(false, 11, 9, start + 200ms), Check::Result::Paused);
}

PreviewIdentity identity()
{
  return {"11111111-1111-4111-8111-111111111111",
          "22222222-2222-4222-8222-222222222222",
          "fixture-v1",
          "33333333-3333-4333-8333-333333333333"};
}

ResourceAsset text_asset(std::string path, std::string_view text = "<p>Offline report</p>")
{
  return {std::move(path), "text/html", std::vector<uint8_t>(text.begin(), text.end())};
}

std::shared_ptr<ResourceSession> session(std::vector<ResourceAsset> assets = {text_asset("index.html")},
                                        PreviewIdentity source = identity())
{
  std::string error;
  auto result = ResourceSession::create(std::move(source), std::move(assets), error);
  EXPECT_TRUE(result) << error;
  EXPECT_TRUE(error.empty()) << error;
  return result;
}

std::string asset_base(const ResourceSession &resources, bool https = false)
{
  const std::string url = resources.url("index.html", https);
  return url.substr(0, url.size() - std::string_view("index.html").size());
}

void rejected_identity(PreviewIdentity source)
{
  std::string error;
  EXPECT_FALSE(ResourceSession::create(std::move(source), {text_asset("index.html")}, error));
  EXPECT_FALSE(error.empty());
}

TEST(DocumentResources, BothOriginsReturnExactAdmittedBytesAndBoundIdentity)
{
  const std::string html = "<!doctype html><meta charset=utf-8><h1>报告</h1><p>A &amp; B</p>";
  const std::vector<uint8_t> image = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n', 0, 0xff};
  auto resources = session({text_asset("index.html", html), {"images/plot.png", "image/png", image}});
  ASSERT_TRUE(resources);
  EXPECT_EQ(resources->identity().project_id, identity().project_id);
  EXPECT_EQ(resources->identity().resource_id, identity().resource_id);
  EXPECT_EQ(resources->identity().source_version, "fixture-v1");
  EXPECT_EQ(resources->identity().session_id, identity().session_id);
  for (const bool https : {false, true}) {
    const std::string url = resources->url("index.html", https);
    EXPECT_TRUE(url.starts_with(https ? "https://stk-preview.invalid/" : "stk-preview://local/"));
    EXPECT_NE(url.find("/" + identity().session_id + "/" + identity().project_id + "/" +
                       identity().resource_id + "/fixture-v1/assets/"),
              std::string::npos);
    const auto result = resources->read(url);
    EXPECT_EQ(result.status, 200);
    EXPECT_EQ(result.mime, "text/html; charset=utf-8");
    EXPECT_EQ(result.bytes, (std::vector<uint8_t>(html.begin(), html.end())));
    EXPECT_TRUE(resources->allows_navigation(url));
    const auto binary = resources->read(resources->url("images/plot.png", https));
    EXPECT_EQ(binary.status, 200);
    EXPECT_EQ(binary.mime, "image/png");
    EXPECT_EQ(binary.bytes, image);
  }
}

TEST(DocumentResources, Utf8SpacesHashesAndLiteralPercentsRoundTripExactlyOnce)
{
  const std::string path = "报告/图 #100%.html";
  const std::string literal_escape_path = "%2e%2e/%2F.html";
  auto source = identity();
  source.source_version = "修订 #100%";
  auto resources = session({text_asset(path, "First source"),
                            text_asset(literal_escape_path, "Literal percent source")},
                           source);
  ASSERT_TRUE(resources);
  const std::string url = resources->url(path);
  EXPECT_NE(url.find("%E6%8A%A5%E5%91%8A/%E5%9B%BE%20%23100%25.html"), std::string::npos);
  EXPECT_NE(url.find("/%E4%BF%AE%E8%AE%A2%20%23100%25/assets/"), std::string::npos);
  const auto result = resources->read(url + "#%E7%AB%A0%20one");
  EXPECT_EQ(result.status, 200);
  const std::string first = "First source";
  EXPECT_EQ(result.bytes, (std::vector<uint8_t>(first.begin(), first.end())));
  const std::string escaped_url = resources->url(literal_escape_path);
  EXPECT_NE(escaped_url.find("/%252e%252e/%252F.html"), std::string::npos);
  const auto literal = resources->read(escaped_url);
  EXPECT_EQ(literal.status, 200);
  const std::string expected = "Literal percent source";
  EXPECT_EQ(literal.bytes, (std::vector<uint8_t>(expected.begin(), expected.end())));
  EXPECT_TRUE(resources->allows_navigation(url + "#part?local-anchor"));
}

TEST(DocumentResources, EachIdentityComponentPreventsCrossSourceReadsEvenWithReusedSessionId)
{
  auto original = session();
  ASSERT_TRUE(original);
  const std::string previous = original->url("index.html");
  for (int component = 0; component < 4; ++component) {
    auto changed = identity();
    switch (component) {
      case 0:
        changed.project_id[0] = 'a';
        break;
      case 1:
        changed.resource_id[0] = 'b';
        break;
      case 2:
        changed.source_version = "fixture-v2";
        break;
      case 3:
        changed.session_id[0] = 'c';
        break;
    }
    auto other = session({text_asset("index.html", "Different bytes")}, changed);
    ASSERT_TRUE(other);
    EXPECT_NE(other->url("index.html"), previous);
    EXPECT_EQ(other->read(previous).status, 403) << component;
    EXPECT_FALSE(other->allows_navigation(previous)) << component;
    EXPECT_EQ(original->read(other->url("index.html")).status, 403) << component;
  }
}

TEST(DocumentResources, RejectsForeignAuthoritiesSchemesUserInfoAndQueries)
{
  auto resources = session();
  ASSERT_TRUE(resources);
  const std::string local = resources->url("index.html");
  const std::string suffix = local.substr(std::string_view("stk-preview://local/").size());
  const std::vector<std::string> denied = {
      "https://example.invalid/" + suffix,
      "https://stk-preview.invalid.evil/" + suffix,
      "https://user@stk-preview.invalid/" + suffix,
      "https://stk-preview.invalid:443/" + suffix,
      "https://stk-preview%2einvalid/" + suffix,
      "http://stk-preview.invalid/" + suffix,
      "stk-preview://local.evil/" + suffix,
      "stk-preview://user@local/" + suffix,
      "stk-preview:///local/" + suffix,
      "file:///etc/passwd",
      "data:text/html,content",
      "javascript:alert(1)",
      "//stk-preview.invalid/" + suffix,
      local + "?download=1",
      local + "?",
      local + "?x#anchor",
      " " + local,
      local + "\n",
  };
  for (const auto &url : denied) {
    SCOPED_TRACE(url);
    EXPECT_EQ(resources->read(url).status, 403);
    EXPECT_FALSE(resources->allows_navigation(url));
  }
}

TEST(DocumentResources, RejectsTraversalEncodedSeparatorsAndMalformedEscapes)
{
  auto resources = session();
  ASSERT_TRUE(resources);
  const std::string base = asset_base(*resources);
  const std::vector<std::string> suffixes = {
      "../index.html", "./index.html", "a/../index.html", "%2e%2e/index.html",
      ".%2E/index.html", "%2E./index.html", "a/%2e%2e/index.html", "a%2Findex.html",
      "a%2findex.html", "a%5Cindex.html", "a\\index.html", "/index.html", "a//index.html",
      "a/", "index.html%", "index.html%0", "index.html%xy", "index.html%00", "index.html%0A",
      "%C0%AE%C0%AE/index.html", "%ED%A0%80", "%F4%90%80%80", "%C2%80",
      "index.html%3Fdownload=1", "index.html#%00", "index.html#%QQ", "index.html#%5c",
      std::string("x\0y", 3), std::string("\xc0\xaf", 2), std::string("\xe2\x82", 2),
  };
  for (const auto &suffix : suffixes) {
    SCOPED_TRACE(::testing::PrintToString(suffix));
    EXPECT_EQ(resources->read(base + suffix).status, 403);
    EXPECT_FALSE(resources->allows_navigation(base + suffix));
  }
  EXPECT_EQ(resources->read(base + "%252e%252e/not-listed.html").status, 404);
  EXPECT_EQ(resources->read(base + std::string(8192, 'a')).status, 403);
}

TEST(DocumentResources, MissingManifestEntriesNeverBecomeHostFileReads)
{
  auto resources = session();
  ASSERT_TRUE(resources);
  const std::string missing = asset_base(*resources) + "etc/passwd";
  EXPECT_TRUE(resources->url("etc/passwd").empty());
  EXPECT_EQ(resources->read(missing).status, 404);
  EXPECT_TRUE(resources->read(missing).bytes.empty());
  EXPECT_FALSE(resources->allows_navigation(missing));
  EXPECT_TRUE(resources->url("../index.html").empty());
  EXPECT_TRUE(resources->url("/index.html").empty());
}

TEST(DocumentResources, HeadHasMetadataWithoutBytesAndMethodsAreExplicit)
{
  auto resources = session();
  ASSERT_TRUE(resources);
  const std::string url = resources->url("index.html");
  const auto get = resources->read(url);
  const auto head = resources->read(url, "HEAD");
  EXPECT_EQ(head.status, 200);
  EXPECT_EQ(head.mime, get.mime);
  EXPECT_EQ(head.content_security_policy, get.content_security_policy);
  EXPECT_EQ(head.content_length, get.bytes.size());
  EXPECT_EQ(get.content_length, get.bytes.size());
  EXPECT_TRUE(head.accept_ranges);
  EXPECT_TRUE(head.bytes.empty());
  EXPECT_FALSE(get.bytes.empty());
  for (const auto method : {"POST", "PUT", "DELETE", "OPTIONS", "TRACE", "get", "", "GET "}) {
    EXPECT_EQ(resources->read(url, method).status, 405) << method;
    EXPECT_TRUE(resources->read(url, method).bytes.empty()) << method;
  }
}

TEST(DocumentResources, PolicyAdmitsOnlyExactSessionAssetRootsAndInlineStyle)
{
  auto resources = session();
  ASSERT_TRUE(resources);
  const std::string policy = resources->read(resources->url("index.html")).content_security_policy;
  for (const auto directive : {"default-src 'none';", "script-src 'none';", "connect-src 'none';",
                               "frame-src 'none';", "object-src 'none';", "form-action 'none';",
                               "base-uri 'none';", "frame-ancestors 'none';"}) {
    EXPECT_NE(policy.find(directive), std::string::npos) << directive;
  }
  const std::string sources = asset_base(*resources) + " " + asset_base(*resources, true);
  EXPECT_NE(policy.find("style-src 'unsafe-inline' " + sources + ";"), std::string::npos);
  EXPECT_NE(policy.find("img-src " + sources + ";"), std::string::npos);
  EXPECT_EQ(policy.find("'self'"), std::string::npos);
  EXPECT_EQ(policy.find("*"), std::string::npos);
  EXPECT_EQ(policy.find("data:"), std::string::npos);
}

TEST(DocumentResources, IdentityValidationIsBoundedAndCanonical)
{
  for (const std::string &bad : {std::string{}, std::string(37, 'a'),
                                std::string("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
                                std::string("11111111111141118111111111111111"),
                                std::string("11111111-1111-4111-8111-11111111111/")}) {
    auto source = identity();
    source.project_id = bad;
    rejected_identity(source);
    source = identity();
    source.resource_id = bad;
    rejected_identity(source);
    source = identity();
    source.session_id = bad;
    rejected_identity(source);
  }
  for (const std::string &bad : {std::string{}, std::string(257, 'v'), std::string(".."),
                                std::string("."), std::string(" v1"), std::string("v1 "),
                                std::string("v/1"), std::string("v\\1"), std::string("v?1"),
                                std::string("v\n1"), std::string("\xed\xa0\x80", 3)}) {
    auto source = identity();
    source.source_version = bad;
    rejected_identity(source);
  }
  auto maximum = identity();
  maximum.source_version.assign(256, 'v');
  EXPECT_TRUE(session({text_asset("index.html")}, maximum));
}

TEST(DocumentResources, ManifestRejectsUnsafeDuplicateAndOversizedVirtualPaths)
{
  const std::vector<std::string> bad_paths = {
      "", ".", "..", "/index.html", "../index.html", "a/../index.html", "a/./index.html",
      "a//index.html", "index.html/", "a\\index.html", "index.html?x", "a\nb", "a\x7f",
      "C:/report.html", "https://example.invalid/report.html",
      std::string("a\0b", 3), std::string("\xf0\x80\x80\xaf", 4), std::string(1025, 'x')};
  for (const auto &path : bad_paths) {
    std::string error;
    EXPECT_FALSE(ResourceSession::create(identity(), {text_asset(path)}, error))
        << ::testing::PrintToString(path);
    EXPECT_FALSE(error.empty());
  }
  std::string error;
  EXPECT_FALSE(ResourceSession::create(
      identity(), {text_asset("index.html", "First"), text_asset("index.html", "Second")}, error));
  EXPECT_FALSE(error.empty());
  EXPECT_TRUE(session({text_asset(std::string(1024, 'x'))}));
}

TEST(DocumentResources, OnlySupportedMimeTypesAndUtf8TextAreAdmitted)
{
  for (const auto mime : {"text/html", "text/html; charset=utf-8", "text/plain", "text/css",
                          "image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "video/mp4"}) {
    auto asset = text_asset("asset");
    asset.mime = mime;
    EXPECT_TRUE(session({asset})) << mime;
  }
  for (const auto mime : {"", "text/javascript", "application/javascript", "image/svg+xml",
                          "application/xml", "text/html; charset=utf-16", "TEXT/HTML",
                          "application/octet-stream", "text/html\r\nX-Test: 1", "video/webm",
                          "video/mp4; codecs=avc1.42E01E", "video/MP4"}) {
    auto asset = text_asset("asset");
    asset.mime = mime;
    std::string error;
    EXPECT_FALSE(ResourceSession::create(identity(), {asset}, error)) << mime;
    EXPECT_FALSE(error.empty());
  }
  auto invalid_text = text_asset("asset");
  invalid_text.bytes = {0xff, 0xfe, 0x00};
  std::string error;
  EXPECT_FALSE(ResourceSession::create(identity(), {invalid_text}, error));
  invalid_text.mime = "image/png";
  auto binary = session({invalid_text});
  ASSERT_TRUE(binary);
  EXPECT_EQ(binary->read(binary->url("asset")).bytes, invalid_text.bytes);
}

TEST(DocumentResources, AssetCountBudgetAcceptsItsBoundaryAndRejectsEmptyOrExcess)
{
  std::string error;
  EXPECT_FALSE(ResourceSession::create(identity(), {}, error));
  EXPECT_FALSE(error.empty());
  std::vector<ResourceAsset> assets;
  for (size_t i = 0; i < 64; ++i) {
    assets.push_back(text_asset(std::to_string(i) + ".html"));
  }
  EXPECT_TRUE(session(assets));
  assets.push_back(text_asset("overflow.html"));
  EXPECT_FALSE(ResourceSession::create(identity(), std::move(assets), error));
  EXPECT_FALSE(error.empty());
}

TEST(DocumentResources, ByteBudgetsAcceptExactLimitsAndRejectOneByteOver)
{
  constexpr size_t limit = 4 * 1024 * 1024;
  std::string error;
  ResourceAsset maximum = {"maximum.pdf", "application/pdf", std::vector<uint8_t>(limit, 0xa5)};
  auto resources = session({maximum});
  ASSERT_TRUE(resources);
  EXPECT_EQ(resources->read(resources->url("maximum.pdf")).bytes, maximum.bytes);
  maximum.bytes.push_back(0xa5);
  EXPECT_FALSE(ResourceSession::create(identity(), {std::move(maximum)}, error));
  EXPECT_FALSE(error.empty());

  std::vector<ResourceAsset> assets;
  for (size_t i = 0; i < 8; ++i) {
    assets.push_back({std::to_string(i) + ".pdf", "application/pdf",
                      std::vector<uint8_t>(limit, static_cast<uint8_t>(i))});
  }
  {
    auto exact = session(assets);
    ASSERT_TRUE(exact);
    EXPECT_EQ(exact->read(exact->url("7.pdf")).bytes, assets.back().bytes);
  }
  assets.push_back({"one-byte.pdf", "application/pdf", {0x01}});
  EXPECT_FALSE(ResourceSession::create(identity(), std::move(assets), error));
  EXPECT_FALSE(error.empty());
}

TEST(DocumentResources, ResponsesOwnBytesAndCloseInvalidatesEveryExistingUrl)
{
  auto resources = session();
  ASSERT_TRUE(resources);
  const std::string url = resources->url("index.html");
  const std::string https = resources->url("index.html", true);
  auto before = resources->read(url);
  ASSERT_FALSE(before.bytes.empty());
  const auto original = before.bytes;
  before.bytes[0] ^= 0xff;
  EXPECT_EQ(resources->read(url).bytes, original);
  resources->close();
  resources->close();
  EXPECT_FALSE(resources->active());
  EXPECT_TRUE(resources->url("index.html").empty());
  EXPECT_TRUE(resources->url("index.html", true).empty());
  for (const auto &old_url : {url, https, url + "#anchor"}) {
    EXPECT_FALSE(resources->allows_navigation(old_url));
    for (const auto method : {"GET", "HEAD", "POST"}) {
      const auto result = resources->read(old_url, method);
      EXPECT_EQ(result.status, 410);
      EXPECT_TRUE(result.bytes.empty());
    }
  }
}

TEST(DocumentResources, SingleRangesReturnExactBytesAndEntityMetadataOnBothOrigins)
{
  const std::vector<uint8_t> bytes = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
  auto resources = session({text_asset("index.html"), {"clip.mp4", "video/mp4", bytes}});
  ASSERT_TRUE(resources);
  struct Example {
    const char *range;
    std::vector<uint8_t> body;
    const char *content_range;
  };
  const std::vector<Example> examples = {
      {"bytes=0-0", {0}, "bytes 0-0/10"},
      {"bytes=3-6", {3, 4, 5, 6}, "bytes 3-6/10"},
      {"ByTeS=1-2", {1, 2}, "bytes 1-2/10"},
      {"bytes=7-", {7, 8, 9}, "bytes 7-9/10"},
      {"bytes=-3", {7, 8, 9}, "bytes 7-9/10"},
      {"bytes=-20", bytes, "bytes 0-9/10"},
      {"bytes=8-999", {8, 9}, "bytes 8-9/10"},
  };
  for (const bool https : {false, true}) {
    const auto url = resources->url("clip.mp4", https);
    const auto whole = resources->read(url);
    EXPECT_EQ(whole.status, 200);
    EXPECT_EQ(whole.content_length, bytes.size());
    EXPECT_TRUE(whole.content_range.empty());
    EXPECT_TRUE(whole.accept_ranges);
    EXPECT_EQ(whole.bytes, bytes);
    for (const auto &example : examples) {
      SCOPED_TRACE(example.range);
      const auto result = resources->read(url, "GET", example.range);
      EXPECT_EQ(result.status, 206);
      EXPECT_EQ(result.mime, "video/mp4");
      EXPECT_EQ(result.bytes, example.body);
      EXPECT_EQ(result.content_length, example.body.size());
      EXPECT_EQ(result.content_range, example.content_range);
      EXPECT_TRUE(result.accept_ranges);
    }
  }
}

TEST(DocumentResources, RangeValidationRejectsMultipleMalformedOverflowAndUnsatisfiableRequests)
{
  auto resources = session({{"clip.mp4", "video/mp4", {0, 1, 2}}, {"empty.mp4", "video/mp4", {}}});
  ASSERT_TRUE(resources);
  const std::vector<std::string> rejected = {
      "bytes=3-", "bytes=9-10", "bytes=2-1", "bytes=-0", "bytes=-", "bytes=",
      "bytes=0-1,2-2", "bytes=0-1,", "bytes=0--1", "bytes=+0-1", "bytes=0-+1",
      "items=0-1", "bytes =0-1", "bytes= 0-1", "bytes=0-1 ",
      "bytes=0-184467440737095516160", "bytes=184467440737095516160-",
      "bytes=-184467440737095516160", "bytes=0-1\r\nX-Test: injected", std::string(129, '9')};
  for (const bool https : {false, true}) {
    const auto url = resources->url("clip.mp4", https);
    for (const auto &range : rejected) {
      SCOPED_TRACE(range);
      const auto result = resources->read(url, "GET", range);
      EXPECT_EQ(result.status, 416);
      EXPECT_EQ(result.content_range, "bytes */3");
      EXPECT_EQ(result.content_length, 0);
      EXPECT_TRUE(result.bytes.empty());
      EXPECT_TRUE(result.accept_ranges);
    }
    const auto empty = resources->read(resources->url("empty.mp4", https), "GET", "bytes=0-");
    EXPECT_EQ(empty.status, 416);
    EXPECT_EQ(empty.content_range, "bytes */0");
  }
}

TEST(DocumentResources, HeadIgnoresRangeAndClosureWinsBeforeRangeOrMethodParsing)
{
  auto resources = session({{"clip.mp4", "video/mp4", {0, 1, 2}}});
  ASSERT_TRUE(resources);
  for (const bool https : {false, true}) {
    const auto url = resources->url("clip.mp4", https);
    for (const auto range : {"bytes=1-2", "bytes=9-", "bytes=0-1,2-2"}) {
      const auto head = resources->read(url, "HEAD", range);
      EXPECT_EQ(head.status, 200);
      EXPECT_EQ(head.content_length, 3);
      EXPECT_TRUE(head.content_range.empty());
      EXPECT_TRUE(head.bytes.empty());
      EXPECT_TRUE(head.accept_ranges);
    }
  }
  const auto url = resources->url("clip.mp4");
  resources->close();
  for (const auto method : {"GET", "HEAD", "POST"}) {
    const auto closed = resources->read(url, method, "bytes=0-1,2-2");
    EXPECT_EQ(closed.status, 410);
    EXPECT_EQ(closed.content_length, 0);
    EXPECT_TRUE(closed.content_range.empty());
    EXPECT_TRUE(closed.bytes.empty());
    EXPECT_FALSE(closed.accept_ranges);
  }
}

TEST(DocumentResources, MediaPolicyAdmitsOnlyListedVideoUrlsAndNeverVideoTopLevelNavigation)
{
  auto resources = session({text_asset("index.html"), {"clips/报告 #100%.mp4", "video/mp4", {0, 1}},
                            {"poster.png", "image/png", {0x89, 'P', 'N', 'G'}}});
  ASSERT_TRUE(resources);
  std::string expected = "media-src";
  for (const bool https : {false, true}) {
    const auto url = resources->url("clips/报告 #100%.mp4", https);
    expected += " " + url;
    EXPECT_FALSE(resources->allows_navigation(url));
    EXPECT_FALSE(resources->allows_navigation(url + "#play"));
    EXPECT_EQ(resources->read(url).status, 200);
    auto foreign = identity();
    foreign.session_id[0] = 'a';
    const auto other = session({{"clips/报告 #100%.mp4", "video/mp4", {3}}}, foreign);
    ASSERT_TRUE(other);
    EXPECT_EQ(resources->read(other->url("clips/报告 #100%.mp4", https), "GET", "bytes=0-").status, 403);
  }
  expected += ";";
  const auto policy = resources->read(resources->url("index.html")).content_security_policy;
  EXPECT_NE(policy.find(expected), std::string::npos);
  EXPECT_NE(policy.find("script-src 'none';"), std::string::npos);
  EXPECT_NE(policy.find("connect-src 'none';"), std::string::npos);
  EXPECT_EQ(policy.find("media-src 'none'"), std::string::npos);
  EXPECT_EQ(policy.find("media-src " + asset_base(*resources) + " "), std::string::npos);
  EXPECT_EQ(policy.find("data:"), std::string::npos);
  EXPECT_EQ(policy.find("blob:"), std::string::npos);
  const auto static_only = session();
  ASSERT_TRUE(static_only);
  EXPECT_NE(static_only->read(static_only->url("index.html")).content_security_policy.find("media-src 'none';"),
            std::string::npos);
}

}  // namespace
}  // namespace stk::document_preview
