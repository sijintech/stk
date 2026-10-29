/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/document/test_media_probe.hh"

#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES

#include <gtest/gtest.h>

#include <string>
#include <string_view>
#include <tuple>

namespace stk::document_preview::test {
namespace {

// Literal browser reply: deliberately independent of the parser's field table
// and the platform scripts. Rectangle origins may lie outside the viewport.
constexpr std::string_view kSnapshot = R"JSON({
  "paused": true, "ended": false, "seeking": false, "duration_known": true,
  "current_time": 1.25, "duration": 6.0,
  "rect_x": -4.5, "rect_y": -7.25, "rect_width": 320.0, "rect_height": 180.0,
  "viewport_width": 640.0, "viewport_height": 480.0,
  "ready_state": 4, "network_state": 1, "error_code": 0,
  "video_width": 320, "video_height": 180
})JSON";

auto values(const MediaSnapshot &media)
{
  return std::tie(media.paused, media.ended, media.seeking, media.duration_known,
      media.current_time, media.duration, media.rect_x, media.rect_y, media.rect_width,
      media.rect_height, media.viewport_width, media.viewport_height, media.ready_state,
      media.network_state, media.error_code, media.video_width, media.video_height,
      media.navigation_generation);
}

std::string changed(std::string_view before, std::string_view after)
{
  std::string result(kSnapshot);
  // A typo in a test's literal replacement must fail the test, not quietly
  // produce an unrelated invalid document that happens to be rejected.
  result.replace(result.find(before), before.size(), after);
  return result;
}

void rejects_without_mutation(std::string_view json)
{
  const MediaSnapshot before{false, true, true, false, 9.5, 13.0, -11.5, -13.25,
      17.0, 19.0, 101.0, 103.0, 1, 2, 3, 23, 29, 47};
  auto media = before;
  std::string error = "previous error";
  EXPECT_FALSE(parse_media_snapshot(json, media, error));
  EXPECT_FALSE(error.empty());
  EXPECT_NE(error, "previous error");
  EXPECT_EQ(error.find("synthetic-sensitive-marker"), std::string::npos);
  EXPECT_EQ(values(media), values(before));
}

TEST(NativeMediaProbe, ValidSnapshotPreservesNativeNavigationGeneration)
{
  MediaSnapshot media;
  media.navigation_generation = 47;
  std::string error = "previous error";
  ASSERT_TRUE(parse_media_snapshot(kSnapshot, media, error)) << error;
  EXPECT_TRUE(error.empty());
  EXPECT_TRUE(media.paused); EXPECT_FALSE(media.ended); EXPECT_FALSE(media.seeking);
  EXPECT_TRUE(media.duration_known);
  EXPECT_DOUBLE_EQ(media.current_time, 1.25); EXPECT_DOUBLE_EQ(media.duration, 6.0);
  EXPECT_DOUBLE_EQ(media.rect_x, -4.5); EXPECT_DOUBLE_EQ(media.rect_y, -7.25);
  EXPECT_DOUBLE_EQ(media.rect_width, 320.0); EXPECT_DOUBLE_EQ(media.rect_height, 180.0);
  EXPECT_DOUBLE_EQ(media.viewport_width, 640.0); EXPECT_DOUBLE_EQ(media.viewport_height, 480.0);
  EXPECT_EQ(media.ready_state, 4); EXPECT_EQ(media.network_state, 1); EXPECT_EQ(media.error_code, 0);
  EXPECT_EQ(media.video_width, 320); EXPECT_EQ(media.video_height, 180);
  EXPECT_EQ(media.navigation_generation, 47u);
}

TEST(NativeMediaProbe, UnknownMetadataRequiresAnExplicitFlagAndCanonicalZeroDuration)
{
  auto json = changed("\"duration_known\": true", "\"duration_known\": false");
  json.replace(json.find("\"duration\": 6.0"), std::string_view("\"duration\": 6.0").size(), "\"duration\": 0");
  json.replace(json.find("\"video_width\": 320"), std::string_view("\"video_width\": 320").size(), "\"video_width\": 0");
  json.replace(json.find("\"video_height\": 180"), std::string_view("\"video_height\": 180").size(), "\"video_height\": 0");
  MediaSnapshot media;
  media.navigation_generation = 19;
  std::string error;
  ASSERT_TRUE(parse_media_snapshot(json, media, error)) << error;
  EXPECT_FALSE(media.duration_known); EXPECT_DOUBLE_EQ(media.duration, 0);
  EXPECT_EQ(media.video_width, 0); EXPECT_EQ(media.video_height, 0);
  EXPECT_EQ(media.navigation_generation, 19u);
  rejects_without_mutation(changed("\"duration_known\": true", "\"duration_known\": false"));
  rejects_without_mutation(changed("\"duration_known\": true,", ""));
}

TEST(NativeMediaProbe, ExactFieldSetRejectsDuplicatesMissingAndNativeIdentityKeys)
{
  rejects_without_mutation(changed("\"paused\": true", "\"paused\": true, \"paused\": true"));
  rejects_without_mutation(changed("\"paused\": true", "\"paused\": true, \"pa\\u0075sed\": false"));
  rejects_without_mutation(changed("\"ended\": false,", ""));
  rejects_without_mutation(changed("{", "{\"unexpected\": 0,"));
  rejects_without_mutation(changed("{", "{\"navigation_generation\": 999,"));
}

TEST(NativeMediaProbe, RejectsNonfiniteNegativeAndOutOfRangeMeasurementsAtomically)
{
  rejects_without_mutation(changed("\"duration\": 6.0", "\"duration\": NaN"));
  rejects_without_mutation(changed("\"current_time\": 1.25", "\"current_time\": Infinity"));
  rejects_without_mutation(changed("\"rect_x\": -4.5", "\"rect_x\": 1e400"));
  rejects_without_mutation(changed("\"current_time\": 1.25", "\"current_time\": -0.5"));
  rejects_without_mutation(changed("\"rect_width\": 320.0", "\"rect_width\": -1"));
  rejects_without_mutation(changed("\"ready_state\": 4", "\"ready_state\": 5"));
  rejects_without_mutation(changed("\"network_state\": 1", "\"network_state\": 4"));
  rejects_without_mutation(changed("\"error_code\": 0", "\"error_code\": -1"));
  rejects_without_mutation(changed("\"video_width\": 320", "\"video_width\": 2147483648"));
}

TEST(NativeMediaProbe, RejectsWrongTypesContainersAndNonObjectRepliesAtomically)
{
  rejects_without_mutation(changed("\"paused\": true", "\"paused\": 1"));
  rejects_without_mutation(changed("\"current_time\": 1.25", "\"current_time\": false"));
  rejects_without_mutation(changed("\"ready_state\": 4", "\"ready_state\": 4.0"));
  rejects_without_mutation(changed("\"duration\": 6.0", "\"duration\": null"));
  rejects_without_mutation(changed("\"video_height\": 180", "\"video_height\": [180]"));
  rejects_without_mutation(changed("\"rect_x\": -4.5", "\"rect_x\": {\"synthetic-sensitive-marker\": 1}"));
  rejects_without_mutation("null");
  rejects_without_mutation("[]");
  rejects_without_mutation("\"synthetic-sensitive-marker\"");
  rejects_without_mutation("[" + std::string(kSnapshot) + "]");
}

TEST(NativeMediaProbe, RejectsMalformedUtf8BomTrailingDataAndOversizedRepliesAtomically)
{
  std::string boundary(kSnapshot);
  ASSERT_LT(boundary.size(), 4096u);
  boundary.append(4096 - boundary.size(), ' ');
  MediaSnapshot media;
  std::string error;
  ASSERT_TRUE(parse_media_snapshot(boundary, media, error)) << error;
  rejects_without_mutation(boundary + " ");
  rejects_without_mutation("");
  rejects_without_mutation("\xef\xbb\xbf" + std::string(kSnapshot));
  rejects_without_mutation(changed("\"paused\"", "\"p\xffused\""));
  rejects_without_mutation(std::string(kSnapshot) + " null");
  rejects_without_mutation(changed("\"paused\": true", "\"paused\": synthetic-sensitive-marker"));
}

#if !defined(__APPLE__) && !defined(_WIN32)
TEST(NativeMediaProbe, UnsupportedPlatformRejectsWithoutCallbackOrSession)
{
  const wm::NativeWindowHandle parent;
  constexpr std::string_view session = "a1111111-1111-4111-8111-111111111111";
  int callbacks = 0;
  std::string error;
  EXPECT_FALSE(probe_media(parent, session, [&](MediaProbeResult) { ++callbacks; }, error));
  EXPECT_FALSE(error.empty()); EXPECT_EQ(callbacks, 0);
  error.clear();
  EXPECT_FALSE(resource_session(parent, session, error));
  EXPECT_FALSE(error.empty()); EXPECT_EQ(callbacks, 0);
}
#endif

}  // namespace
}  // namespace stk::document_preview::test

#endif  // STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
