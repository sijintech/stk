/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include "stk/core/sha256.hh"
#include "stk/core/thread_pool.hh"
#include "stk/io/blob_cache.hh"
#include "stk/io/payload.hh"

#include <gtest/gtest.h>

#include <cmath>

using namespace stk;
using io::Json;

TEST(Payload, ExampleDirectoryAndStkpDecodeToTheSamePayload)
{
  const io::Payload dir = io::read_directory(test::example_dir());
  const io::Payload stkp = io::read_stkp(test::example_dir() / "example.stkp");
  EXPECT_EQ(dir.manifest, stkp.manifest); /* .stkp URIs are rewritten to sha256:<hex> */
  EXPECT_EQ(dir.render_origin, (std::array<double, 3>{100.0, 50.0, 25.0}));
  EXPECT_EQ(dir.length_unit, stkp.length_unit);
  ASSERT_EQ(dir.accessors.size(), stkp.accessors.size());
  for (const io::PayloadAccessor &a : dir.accessors) {
    const auto x = dir.accessor_bytes(a.id);
    const auto y = stkp.accessor_bytes(a.id);
    ASSERT_EQ(x.size(), y.size());
    EXPECT_TRUE(std::equal(x.begin(), x.end(), y.begin())) << a.id;
  }
  EXPECT_TRUE(stkp.buffers[0].bytes.mapped());
  EXPECT_EQ(dir.layers().size(), 9u);
  const Json *domains = dir.layer("domains");
  ASSERT_NE(domains, nullptr);
  const auto positions = dir.view<float>((*domains)["positions"].get<std::string>());
  EXPECT_EQ(positions.size(), 72u * 3);
  EXPECT_THROW(dir.view<double>((*domains)["positions"].get<std::string>()), io::PayloadError);
  EXPECT_EQ(dir.colormap("pal0")->at("categorical"), true);
  EXPECT_EQ(dir.layer_origin(*domains), dir.render_origin);
}

TEST(Payload, PackStkpIsByteIdenticalToPython)
{
  const io::Payload payload = io::read_directory(test::example_dir());
  std::map<std::string, core::SharedBytes> blobs;
  for (const io::PayloadBuffer &b : payload.buffers) {
    blobs[b.sha256] = b.bytes;
  }
  const std::vector<uint8_t> packed = io::pack_stkp(payload.manifest, blobs);
  const std::vector<uint8_t> python = core::read_file(test::example_dir() / "example.stkp");
  EXPECT_EQ(packed, python);
}

TEST(Payload, ScenesMatchThePythonEncoderChecksums)
{
  const Json summary = test::fixture_json("payload/scenes/scenes.json");
  core::ThreadPool pool(3);
  for (auto it = summary.begin(); it != summary.end(); ++it) {
    io::DecodeOptions options;
    options.pool = &pool;
    const io::Payload p = io::read_stkp(test::fixtures_dir() / "payload" / "scenes" / (it.key() + ".stkp"), options);
    const Json &expect = it.value();
    for (int i = 0; i < 3; i++) {
      EXPECT_EQ(p.render_origin[size_t(i)], expect["render_origin"][size_t(i)].get<double>());
    }
    ASSERT_EQ(p.layers().size(), expect["layers"].size()) << it.key();
    for (size_t i = 0; i < p.layers().size(); i++) {
      EXPECT_EQ(p.layers()[i]["id"], expect["layers"][i][0]);
    }
    EXPECT_EQ(p.total_bytes(), expect["bytes"].get<uint64_t>());
    for (auto a = expect["accessors"].begin(); a != expect["accessors"].end(); ++a) {
      const io::PayloadAccessor &accessor = p.accessor(a.key());
      EXPECT_EQ(accessor.count, a.value()["count"].get<uint64_t>());
      const std::vector<double> values = p.doubles(a.key());
      double sum = 0;
      for (double v : values) {
        sum += v;
      }
      const double expected = a.value()["sum"].get<double>();
      EXPECT_NEAR(sum, expected, 1e-9 * std::max(1.0, std::abs(expected))) << it.key() << " " << a.key();
      for (size_t k = 0; k < a.value()["first"].size(); k++) {
        EXPECT_EQ(values[k], a.value()["first"][k].get<double>()) << a.key();
      }
    }
  }
}

TEST(Payload, NormalizedFloatsAndDoubles)
{
  io::Json manifest = {{"schema", "stk.payload/2"},
                       {"render_origin", {0, 0, 0}},
                       {"length_unit", "nm"},
                       {"layers", Json::array()}};
  const std::vector<uint8_t> bytes{0, 255, 128, 0, 0, 0, 0, 0, 0x00, 0x80, 0xFF, 0x7F};
  const std::string sha = core::Sha256::hex(bytes);
  manifest["buffers"] = {{{"id", "b"}, {"uri", "sha256:" + sha}, {"sha256", sha}, {"byteLength", bytes.size()}}};
  manifest["accessors"] = {{{"id", "u"}, {"buffer", "b"}, {"byteOffset", 0}, {"count", 3}, {"type", "u8"},
                            {"components", 1}, {"normalized", true}},
                           {{"id", "s"}, {"buffer", "b"}, {"byteOffset", 8}, {"count", 2}, {"type", "i16"},
                            {"components", 1}, {"normalized", true}}};
  const io::Payload p = io::decode(manifest, {{sha, core::SharedBytes::copy_of(bytes)}});
  const std::vector<float> u = p.floats("u");
  EXPECT_FLOAT_EQ(u[0], 0.0f);
  EXPECT_FLOAT_EQ(u[1], 1.0f);
  EXPECT_FLOAT_EQ(u[2], float(128.0 / 255.0));
  const std::vector<float> s = p.floats("s");
  EXPECT_FLOAT_EQ(s[0], -1.0f); /* -32768 / 32767 clamps to -1 */
  EXPECT_FLOAT_EQ(s[1], 1.0f);
  EXPECT_EQ(p.doubles("s")[0], -32768.0);
}

TEST(BlobCache, StoresVerifiesAndProvides)
{
  const auto root = test::scratch_dir("blobs");
  io::BlobCache cache(root / "blobs");
  const std::vector<uint8_t> data{1, 2, 3, 4, 5};
  const std::string sha = cache.put(data);
  EXPECT_EQ(sha, core::Sha256::hex(data));
  EXPECT_EQ(cache.path_for(sha), root / "blobs" / sha.substr(0, 2) / sha);
  EXPECT_TRUE(cache.contains(sha));
  EXPECT_EQ(cache.put(data), sha); /* idempotent */
  const auto bytes = cache.open(sha);
  ASSERT_TRUE(bytes.has_value());
  EXPECT_EQ(bytes->size(), 5u);
  EXPECT_THROW(cache.path_for("../etc/passwd"), io::PayloadError);
  EXPECT_FALSE(cache.contains("zz"));
  /* A corrupt blob is removed and reported as missing. */
  const std::vector<uint8_t> other{9, 9, 9};
  const std::string other_sha = core::Sha256::hex(other);
  std::filesystem::create_directories(cache.path_for(other_sha).parent_path());
  core::write_file_atomic(cache.path_for(other_sha), data);
  EXPECT_FALSE(cache.open(other_sha).has_value());
  EXPECT_FALSE(cache.contains(other_sha));

  /* The example manifest decodes from the cache (the bridge's blob path). */
  for (const auto &[digest, blob] : test::example_blobs()) {
    EXPECT_EQ(cache.put(blob.span()), digest);
  }
  const Json manifest = io::read_json_file(test::example_dir() / "manifest.json");
  const io::Payload p = io::decode_manifest(manifest, cache.provider());
  EXPECT_EQ(p.buffers.size(), manifest["buffers"].size());
  EXPECT_TRUE(p.buffers[0].bytes.mapped());
  io::BlobCache empty(root / "none");
  try {
    io::decode_manifest(manifest, empty.provider());
    FAIL() << "missing blobs must be rejected";
  }
  catch (const io::PayloadError &error) {
    EXPECT_EQ(error.path(), "/buffers/0");
  }
}

TEST(Payload, LabelFormatsAndIds)
{
  for (const char *good : {".3g", ".2f", "+.1e", ".0%", "08.3f", ",.2f", "", "g", "d", ",d", "+05d", "99", "#0,.0%"}) {
    EXPECT_TRUE(io::is_label_format(good)) << good;
  }
  for (const char *bad : {"999999", ".999f", "{}", "abc", ".3d", "~s", "xxx", "999d", ".3g\n", "00"}) {
    EXPECT_FALSE(io::is_label_format(bad)) << bad;
  }
  EXPECT_TRUE(io::is_payload_id("mesh_pos"));
  EXPECT_TRUE(io::is_payload_id("stk:cubic-26.x"));
  EXPECT_FALSE(io::is_payload_id("-x"));
  EXPECT_FALSE(io::is_payload_id(std::string(129, 'a')));
}
