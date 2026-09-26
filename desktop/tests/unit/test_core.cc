/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include "stk/core/clock.hh"
#include "stk/core/log.hh"
#include "stk/core/mmap.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/core/thread_pool.hh"
#include "stk/core/utf8.hh"

#include <gtest/gtest.h>

#include <atomic>
#include <fstream>
#include <numeric>

using namespace stk;
namespace utf8 = stk::core::utf8;

TEST(Utf8, ValidatesRfc3629)
{
  EXPECT_TRUE(utf8::is_valid("ascii"));
  EXPECT_TRUE(utf8::is_valid("中文 English 畴"));
  EXPECT_TRUE(utf8::is_valid("\xF0\x9F\x98\x80"));
  EXPECT_FALSE(utf8::is_valid("\xC0\xAF"));         /* overlong '/' */
  EXPECT_FALSE(utf8::is_valid("\xE0\x80\xAF"));     /* overlong */
  EXPECT_FALSE(utf8::is_valid("\xED\xA0\x80"));     /* surrogate */
  EXPECT_FALSE(utf8::is_valid("\xF4\x90\x80\x80")); /* > U+10FFFF */
  EXPECT_FALSE(utf8::is_valid("\xE4\xB8"));         /* truncated */
  EXPECT_FALSE(utf8::is_valid("\xFF"));
  EXPECT_EQ(utf8::first_invalid("ab\xE4\xB8"), 2u);
}

TEST(Utf8, SanitizeUsesMaximalSubparts)
{
  /* Python: b"a\xe4\xb8b\xff\xf0\x9f\x98".decode("utf-8", "replace") == "a\ufffdb\ufffd\ufffd" */
  EXPECT_EQ(utf8::sanitize("a\xE4\xB8" "b\xFF\xF0\x9F\x98"), "a\xEF\xBF\xBD" "b\xEF\xBF\xBD\xEF\xBF\xBD");
  /* b"\xed\xa0\x80".decode(errors="replace") == "\ufffd\ufffd\ufffd" (0xA0 is not a valid second byte after ED) */
  EXPECT_EQ(utf8::sanitize("\xED\xA0\x80"), "\xEF\xBF\xBD\xEF\xBF\xBD\xEF\xBF\xBD");
  EXPECT_EQ(utf8::count_code_points("中文ab"), 4u);
  EXPECT_EQ(utf8::from_utf32(utf8::to_utf32("畴界面 é 😀")), "畴界面 é 😀");
  EXPECT_EQ(utf8::from_utf16(utf8::to_utf16("畴 😀")), "畴 😀");
}

TEST(Utf8, StreamDecoderMatchesWholeBufferAtEverySplit)
{
  const std::string text = "log: 中文 ok \xF0\x9F\x98\x80 bad \xE4\xB8 end \xFF 畴";
  const std::string whole = utf8::sanitize(text);
  for (size_t a = 0; a <= text.size(); a++) {
    for (size_t b = a; b <= text.size(); b += 3) {
      utf8::StreamDecoder decoder;
      std::string out = decoder.feed(std::string_view(text).substr(0, a));
      out += decoder.feed(std::string_view(text).substr(a, b - a));
      out += decoder.feed(std::string_view(text).substr(b));
      out += decoder.finish();
      ASSERT_EQ(out, whole) << a << " " << b;
    }
  }
  utf8::StreamDecoder decoder;
  EXPECT_EQ(decoder.feed("\xE4"), "");
  EXPECT_EQ(decoder.pending(), 1u);
  EXPECT_EQ(decoder.feed("\xB8\xAD"), "中");
}

TEST(Utf8, CjkSafeTruncation)
{
  EXPECT_EQ(utf8::truncate_bytes("中文", 4), "中");
  EXPECT_EQ(utf8::truncate_bytes("中文", 6), "中文");
  EXPECT_EQ(utf8::truncate_bytes("a中", 2), "a");
  EXPECT_EQ(utf8::display_width("中文ab"), 6);
  EXPECT_EQ(utf8::display_width("e\u0301"), 1);
  EXPECT_EQ(utf8::truncate_display("中文字段名称", 7), "中文字\u2026");
  EXPECT_EQ(utf8::truncate_display("abcdef", 4), "abc\u2026");
  EXPECT_EQ(utf8::truncate_display("abc", 4), "abc");
  EXPECT_EQ(utf8::truncate_display("ae\u0301bc", 3, "."), "ae\u0301.");
}

TEST(Sha256, NistVectors)
{
  EXPECT_EQ(core::Sha256::hex(std::string_view("")), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  EXPECT_EQ(core::Sha256::hex(std::string_view("abc")), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  EXPECT_EQ(core::Sha256::hex(std::string_view("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq")),
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
  core::Sha256 sha;
  const std::string chunk(1000, 'a');
  for (int i = 0; i < 1000; i++) {
    sha.update(chunk);
  }
  EXPECT_EQ(core::to_hex(sha.finish()), "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
  EXPECT_TRUE(core::is_sha256_hex("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"));
  EXPECT_FALSE(core::is_sha256_hex("CDC76E5C9914FB9281A1C7E284D73E67F1809A48A497200E046D39CCC7112CD0"));
}

TEST(Mmap, MapsFilesSlicesAndEmptyFiles)
{
  const auto dir = test::scratch_dir("mmap");
  const std::string text = "0123456789abcdef";
  core::write_file_atomic(dir / "data.bin", std::span(reinterpret_cast<const uint8_t *>(text.data()), text.size()));
  const core::SharedBytes mapped = core::SharedBytes::from_file(dir / "data.bin");
  EXPECT_TRUE(mapped.mapped());
  ASSERT_EQ(mapped.size(), 16u);
  const core::SharedBytes slice = mapped.slice(8, 4);
  EXPECT_EQ(std::string(reinterpret_cast<const char *>(slice.data()), 4), "89ab");
  EXPECT_THROW(mapped.slice(10, 7), std::out_of_range);
  std::ofstream(dir / "empty.bin").close();
  EXPECT_EQ(core::SharedBytes::from_file(dir / "empty.bin").size(), 0u);
  EXPECT_THROW(core::SharedBytes::from_file(dir / "missing.bin"), core::FileError);
  const core::SharedBytes copied = core::SharedBytes::from_file(dir / "data.bin", false);
  EXPECT_FALSE(copied.mapped());
  EXPECT_EQ(core::read_text_file(dir / "data.bin"), text);
  /* Non-ASCII file names. */
  const auto cjk = dir / core::path_from_utf8("数据.bin");
  core::write_file_atomic(cjk, std::span(reinterpret_cast<const uint8_t *>(text.data()), 4));
  EXPECT_EQ(core::SharedBytes::from_file(cjk).size(), 4u);
  EXPECT_EQ(core::path_to_utf8(cjk.filename()), "数据.bin");
}

TEST(Paths, SafeRelativePathsFollowTheGraphRule)
{
  for (const char *good : {"Polar.00000000.dat", "run/frames/x.dat", "中文/数据.vti", "a..b", ".hidden"}) {
    EXPECT_TRUE(core::is_safe_relative_path(good)) << good;
  }
  for (const char *bad : {"", "/abs", "\\x", "C:x", "c:\\x", "../x", "x/../y", "x/..", "..", "a\\b"}) {
    EXPECT_FALSE(core::is_safe_relative_path(bad)) << bad;
  }
  EXPECT_FALSE(core::is_safe_relative_path(std::string_view("a\0b", 3)));
  EXPECT_TRUE(core::join_safe("/base", "a/b").has_value());
  EXPECT_FALSE(core::join_safe("/base", "../etc").has_value());
  EXPECT_EQ(core::default_blob_cache_dir().filename(), "blobs");
}

TEST(ThreadPool, ParallelForAndFutures)
{
  core::ThreadPool pool(4);
  std::vector<uint64_t> values(100000);
  pool.parallel_for(values.size(), 1000, [&](size_t begin, size_t end) {
    for (size_t i = begin; i < end; i++) {
      values[i] = i;
    }
  });
  EXPECT_EQ(std::accumulate(values.begin(), values.end(), uint64_t(0)), uint64_t(99999) * 100000 / 2);
  auto future = pool.submit([] { return 42; });
  EXPECT_EQ(future.get(), 42);
  EXPECT_THROW(pool.parallel_for(10, 1, [](size_t begin, size_t) {
    if (begin == 5) {
      throw std::runtime_error("boom");
    }
  }),
               std::runtime_error);
  std::atomic<int> count{0};
  for (int i = 0; i < 50; i++) {
    pool.submit([&] { count++; });
  }
  pool.wait_idle();
  EXPECT_EQ(count.load(), 50);
}

TEST(Clock, FormatsAndManualClock)
{
  EXPECT_EQ(core::format_utc_iso8601(0.0), "1970-01-01T00:00:00.000Z");
  EXPECT_EQ(core::format_utc_iso8601(1790318149.5), "2026-09-25T06:35:49.500Z");
  EXPECT_EQ(core::format_utc_iso8601(-1.0), "1969-12-31T23:59:59.000Z");
  core::ManualClock clock(10.0);
  clock.advance(0.25);
  EXPECT_DOUBLE_EQ(clock.now(), 10.25);
  const double a = core::monotonic_seconds();
  EXPECT_GE(core::monotonic_seconds(), a);
}

TEST(Log, SinkAndLevel)
{
  std::vector<std::string> lines;
  auto previous = core::set_log_sink([&](const core::LogRecord &r) {
    lines.push_back(std::string(core::log_level_name(r.level)) + ":" + std::string(r.channel) + ":" + std::string(r.message));
  });
  core::set_log_level(core::LogLevel::Info);
  core::log_debug("t", "hidden {}", 1);
  core::log_info("t", "shown {} {}", 1, "中文");
  core::log_error("io", "bad");
  core::set_log_sink(previous);
  ASSERT_EQ(lines.size(), 2u);
  EXPECT_EQ(lines[0], "info:t:shown 1 中文");
  EXPECT_EQ(lines[1], "error:io:bad");
}
