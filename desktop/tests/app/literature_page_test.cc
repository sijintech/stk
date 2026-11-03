/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/literature_page.hh"
#include "stk/app/literature_state.hh"
#include "stk/core/sha256.hh"
#include "stk/io/png.hh"
#include <algorithm>
#include <array>

namespace stk::app {
namespace {
using io::Json;
Json fixture() { return io::read_json_file(STK_LITERATURE_PAGE_FIXTURE); }
std::vector<uint8_t> hex(std::string_view s)
{
  const auto digit = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
  std::vector<uint8_t> v; for (size_t i = 0; i < s.size(); i += 2) { v.push_back(uint8_t(digit(s[i]) * 16 + digit(s[i + 1]))); } return v;
}
void word(std::vector<uint8_t> &out, uint32_t n) { for (int i = 3; i >= 0; --i) { out.push_back(uint8_t(n >> (i * 8))); } }
uint32_t crc(std::span<const uint8_t> bytes)
{
  uint32_t c = ~0u;
  for (uint8_t b : bytes) { c ^= b; for (int bit = 0; bit < 8; ++bit) { c = c & 1 ? (c >> 1) ^ 0xedb88320u : c >> 1; } }
  return ~c;
}
void chunk(std::vector<uint8_t> &out, const std::string &name, const std::vector<uint8_t> &bytes)
{
  word(out, uint32_t(bytes.size())); const size_t start = out.size(); out.insert(out.end(), name.begin(), name.end());
  out.insert(out.end(), bytes.begin(), bytes.end()); word(out, crc(std::span(out).subspan(start)));
}
std::vector<uint8_t> fixed_png(const std::vector<uint8_t> &compressed, uint32_t width = 1, uint32_t height = 1)
{
  std::vector<uint8_t> data = {137,80,78,71,13,10,26,10}, ihdr; word(ihdr, width); word(ihdr, height);
  ihdr.insert(ihdr.end(), {8,6,0,0,0}); chunk(data, "IHDR", ihdr); chunk(data, "IDAT", compressed); chunk(data, "IEND", {}); return data;
}
const io::PngLimits limits{2048,2048,4 * 1024 * 1024};

TEST(LiteraturePage, ActualCachedResolveAndRenderKeepOriginalPngAndImmutableQuads)
{
  const auto f = fixture(); LiteraturePage page;
  ASSERT_TRUE(page.adopt(f.at("resolved"), f.at("rendered"))) << page.error();
  ASSERT_TRUE(page.ready()); ASSERT_NE(page.image(), nullptr); ASSERT_TRUE(page.highlights());
  EXPECT_EQ(page.image()->width, io::get_int(f.at("rendered").at("image"), "width", 0));
  EXPECT_EQ(core::Sha256::hex(page.png()), io::get_string(f.at("rendered").at("image"), "sha256"));
  EXPECT_EQ(page.highlights()->size(), f.at("rendered").at("highlights").size());
  auto borrowed = page.highlights(); page.clear();
  EXPECT_FALSE(page.ready()); EXPECT_TRUE(page.png().empty()); EXPECT_FALSE(page.highlights());
  EXPECT_FALSE(borrowed->empty()); // A caller's immutable CPU observation cannot restore display authority.
}
TEST(LiteraturePage, FailedReplacementCannotKeepThePreviousPage)
{
  const auto f = fixture(); LiteraturePage page; ASSERT_TRUE(page.adopt(f.at("resolved"), f.at("rendered")));
  auto changed = f.at("rendered"); changed["image"]["sha256"] = std::string(64, 'b');
  EXPECT_FALSE(page.adopt(f.at("resolved"), changed)); EXPECT_FALSE(page.ready()); EXPECT_TRUE(page.png().empty());
  EXPECT_TRUE(page.citation().is_null()); EXPECT_FALSE(page.highlights()); EXPECT_EQ(page.error(), "literature.invalid_page");
}
TEST(LiteraturePage, CitationDatabaseSourceAndParserIdentityCannotBeRelabelled)
{
  const auto f = fixture();
  for (int which = 0; which < 6; ++which) {
    auto changed = f.at("rendered"); auto selected = f.at("resolved");
    if (which == 0) { changed["citation"]["database_id"] = "00000000-0000-4000-8000-000000000099"; }
    if (which == 1) { changed["source_sha256"] = std::string(64, 'b'); }
    if (which == 2) { changed["renderer"]["binary_sha256"] = std::string(64, 'b'); }
    if (which == 3) { selected["database_id"] = "00000000-0000-4000-8000-000000000099"; }
    if (which == 4) { changed["page"]["rotation"] = 90; }
    if (which == 5) { selected["parser"]["python"] = "/arbitrary"; }
    LiteraturePage page; EXPECT_FALSE(page.adopt(selected, changed)) << which;
  }
}
TEST(LiteraturePage, GeometryDigestIsNotAnImageDigestAndCannotHideWrongCharacterBoxes)
{
  const auto f = fixture();
  for (int which = 0; which < 4; ++which) {
    auto selected = f.at("resolved"), changed = f.at("rendered");
    if (which == 0) { changed["geometry_sha256"] = changed["image"]["sha256"]; }
    if (which == 1) { changed["highlights"][0]["quad"][0][0] = 9.0; changed["geometry_sha256"] = LiteratureState::checksum(changed["highlights"]); }
    if (which == 2) { selected["characters"][0]["box"][0] = 9.0; }
    if (which == 3) { changed["pdf_to_pixel"][2] = changed["pdf_to_pixel"][2].get<double>() + .021; }
    LiteraturePage page; EXPECT_FALSE(page.adopt(selected, changed)) << which;
  }
}
TEST(LiteraturePage, BoolFloatAndUnknownFieldsDoNotBorrowIntegerOrClosedShapes)
{
  const auto f = fixture();
  for (int which = 0; which < 5; ++which) {
    auto selected = f.at("resolved"), changed = f.at("rendered");
    if (which == 0) { changed["image"]["width"] = true; }
    if (which == 1) { changed["image"]["bytes"] = double(changed["image"]["bytes"].get<int>()); }
    if (which == 2) { changed["image"]["width"] = 2049; }
    if (which == 3) { selected["characters"][0]["index"] = 0.0; }
    if (which == 4) { changed["renderer"]["extra"] = true; }
    LiteraturePage page; EXPECT_FALSE(page.adopt(selected, changed)) << which;
  }
}
TEST(LiteraturePage, Base64PaddingWhitespaceAndEmbeddedNulAreRejectedBeforeDecode)
{
  const auto f = fixture();
  for (const auto &encoded : {std::string("AAAA\n"), std::string("AA=A"), std::string("AB=="), std::string("AAA=AAAA"), std::string("AA\0=", 4)}) {
    auto changed = f.at("rendered"); changed["image"]["data_base64"] = encoded;
    LiteraturePage page; EXPECT_FALSE(page.adopt(f.at("resolved"), changed));
  }
}
TEST(LiteraturePage, AffineMathMapsAllRotatedCropCornersAndUsesPixelToleranceAtLargeOrigins)
{
  // Analytic geometry fixtures, separate from the actual cached PDF DTO above.
  Json page = {{"page_index",0},{"width",10.0},{"height",20.0},{"page_box",Json::array({100.0,200.0,110.0,220.0})},{"rotation",0},{"status","mapped"}};
  const std::array<std::array<double,6>,4> transforms = {{{10,0,-1000,0,-10,2200}, {0,5,-1000,20,0,-2000}, {-10,0,1100,0,10,-2000}, {0,-5,1100,-20,0,2200}}};
  for (size_t index=0;index<4;++index) {
    page["rotation"]=int(index*90); EXPECT_TRUE(LiteraturePage::affine_matches(page,100,200,transforms[index]));
    auto wrong=transforms[index];wrong[2]+=.021; EXPECT_FALSE(LiteraturePage::affine_matches(page,100,200,wrong));
  }
  page["page_box"]=Json::array({90000.0,-90000.0,90010.0,-89980.0});page["rotation"]=90;
  std::array<double,6> m={0,5,450000,20,0,-1800000}; EXPECT_TRUE(LiteraturePage::affine_matches(page,100,200,m));
  auto tiny_coefficient_change=m;tiny_coefficient_change[0]=3e-7;
  EXPECT_FALSE(LiteraturePage::affine_matches(page,100,200,tiny_coefficient_change)); // 0.027 px, despite a tiny coefficient delta.
  auto tolerated=m;tolerated[2]+=.019; EXPECT_TRUE(LiteraturePage::affine_matches(page,100,200,tolerated));
}
TEST(LiteraturePng, GeneralPngDecodeStillAcceptsNonzeroFilterWhileFixedWireRejectsIt)
{
  const auto zero = fixed_png(hex("789c636000020000050001"));
  EXPECT_NO_THROW(io::check_rgba8_filter_zero_png(zero, limits)); EXPECT_EQ(io::decode_png(zero).pixels.size(), 4u);
  const auto one = fixed_png(hex("789c6364000200000a0002"));
  EXPECT_NO_THROW(io::decode_png(one)); EXPECT_THROW(io::check_rgba8_filter_zero_png(one, limits), io::PngError);
}
TEST(LiteraturePng, CrcChunkOrderTruncationAndTrailingBytesAreRejected)
{
  const auto good = fixed_png(hex("789c636000020000050001"));
  std::vector<std::vector<uint8_t>> cases;
  auto crc_bad = good; crc_bad[crc_bad.size()-1] ^= 1; cases.push_back(crc_bad);
  auto short_header = good; short_header.resize(19); cases.push_back(short_header);
  auto short_chunk = good; short_chunk.pop_back(); cases.push_back(short_chunk);
  auto trailing = good; trailing.push_back(0); cases.push_back(trailing);
  std::vector<uint8_t> order(good.begin(),good.begin()+8); chunk(order,"IEND",{});
  order.insert(order.end(),good.begin()+8,good.end()-12); cases.push_back(order); // Every CRC is valid; order is not.
  auto extra = good; std::vector<uint8_t> text; chunk(text,"tEXt",{'a',0,'b'}); extra.insert(extra.begin()+33,text.begin(),text.end()); cases.push_back(extra);
  auto overflow = good; std::fill_n(overflow.begin()+33, 4, 255); cases.push_back(overflow);
  for (const auto &bad : cases) { EXPECT_THROW(io::check_rgba8_filter_zero_png(bad, limits), io::PngError); }
}
TEST(LiteraturePng, CompleteZlibConsumptionAndOutputBudgetAreEnforced)
{
  auto compressed = hex("789c636000020000050001"); compressed.push_back(0);
  EXPECT_THROW(io::check_rgba8_filter_zero_png(fixed_png(compressed), limits), io::PngError);
  compressed.pop_back(); compressed.pop_back();
  EXPECT_THROW(io::check_rgba8_filter_zero_png(fixed_png(compressed), limits), io::PngError);
  const auto bomb = hex("789cedc101010000008090feafee080a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006a000f0001");
  EXPECT_THROW(io::check_rgba8_filter_zero_png(fixed_png(bomb), limits), io::PngError);
  EXPECT_THROW(io::check_rgba8_filter_zero_png(fixed_png(hex("789c636000020000050001"), 2049, 1), limits), io::PngError);
}
}  // namespace
}  // namespace stk::app
