/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Decoder parity with suan/render/payload.py (spec §10): every case of fixtures/payload/cases.json
 * (the test_render_payload.py cases, data-level cases, .stkp corruptions and a seeded mutation corpus)
 * gets the Python verdict, with the same JSON-pointer path when Python reports one. The C++ decoder is
 * deliberately stricter in the cases listed in kStricter (spec checks the web decoder applies and
 * payload.py does not). The web decoder's verdicts are compared for information only. */
#include "support.hh"

#include "stk/io/payload.hh"

#include <gtest/gtest.h>

#include <cstring>

using namespace stk;
using io::Json;

namespace {

struct Outcome {
  bool ok;
  std::string path, message;
};

Outcome run_case(const Json &c, const Json &example_manifest, const std::map<std::string, core::SharedBytes> &blobs,
                 const std::vector<uint8_t> &example_stkp)
{
  try {
    const std::string kind = c["kind"].get<std::string>();
    if (kind == "example") {
      io::decode(test::apply_patches(example_manifest, c["patches"]), blobs);
    }
    else if (kind == "blobs") {
      std::map<std::string, core::SharedBytes> own;
      for (auto it = c["blobs"].begin(); it != c["blobs"].end(); ++it) {
        own[it.key()] = core::SharedBytes::from_vector(test::base64_decode(it.value().get<std::string>()));
      }
      io::decode(c["manifest"], own);
    }
    else {
      std::vector<uint8_t> bytes = example_stkp;
      for (const Json &edit : c["edits"]) {
        const size_t at = edit[0].get<size_t>();
        const std::string hex = edit[1].get<std::string>();
        for (size_t k = 0; k * 2 < hex.size(); k++) {
          bytes[at + k] = uint8_t(std::stoul(hex.substr(2 * k, 2), nullptr, 16));
        }
      }
      if (!c["truncate"].is_null()) {
        bytes.resize(c["truncate"].get<size_t>());
      }
      const std::string append = c.value("append", std::string());
      for (size_t k = 0; k * 2 < append.size(); k++) {
        bytes.push_back(uint8_t(std::stoul(append.substr(2 * k, 2), nullptr, 16)));
      }
      io::decode_stkp(core::SharedBytes::from_vector(std::move(bytes)));
    }
  }
  catch (const io::PayloadError &error) {
    return {false, error.path(), error.what()};
  }
  return {true, {}, {}};
}

/* Paths of checks that C++ applies and payload.py does not (see payload.cc "Stricter than payload.py"). */
bool stricter(const Outcome &cpp)
{
  const auto ends_with = [&](const char *suffix) {
    const size_t n = std::strlen(suffix);
    return cpp.path.size() >= n && cpp.path.compare(cpp.path.size() - n, n, suffix) == 0;
  };
  return ends_with("/value_range") || ends_with("/grid/direction") || ends_with("/byteLength");
}

}  // namespace

TEST(PayloadParity, EveryCaseMatchesPython)
{
  const Json cases = test::fixture_json("payload/cases.json");
  const Json example = io::read_json_file(test::example_dir() / "manifest.json");
  const auto blobs = test::example_blobs();
  const std::vector<uint8_t> stkp = core::read_file(test::example_dir() / "example.stkp");
  int accepted = 0, rejected = 0, same_path = 0, python_paths = 0, stricter_count = 0;
  for (const Json &c : cases) {
    const std::string name = c["name"].get<std::string>();
    const Json &python = c["python"];
    const Outcome cpp = run_case(c, example, blobs, stkp);
    if (python["ok"].get<bool>()) {
      if (!cpp.ok && stricter(cpp)) {
        stricter_count++;
        continue;
      }
      EXPECT_TRUE(cpp.ok) << name << ": C++ rejected what Python accepts: " << cpp.message;
      accepted++;
      continue;
    }
    rejected++;
    EXPECT_FALSE(cpp.ok) << name << ": C++ accepted what Python rejects: " << python["message"];
    const std::string path = python.value("path", std::string());
    if (!path.empty() && !cpp.ok) {
      python_paths++;
      same_path += cpp.path == path;
      EXPECT_EQ(cpp.path, path) << name << "\n  python: " << python["message"] << "\n  c++:    " << cpp.message;
    }
  }
  std::printf("[payload parity] %zu cases: %d accepted, %d rejected (%d/%d same JSON-pointer path), %d stricter\n",
              cases.size(), accepted, rejected, same_path, python_paths, stricter_count);
  EXPECT_GT(accepted, 100);
  EXPECT_GT(rejected, 300);
}

TEST(PayloadParity, WebDecoderAgreementIsReported)
{
  const Json cases = test::fixture_json("payload/cases.json");
  const Json web = test::fixture_json("web_vectors.json")["verdicts"];
  ASSERT_EQ(cases.size(), web.size());
  int differ = 0;
  for (size_t i = 0; i < cases.size(); i++) {
    ASSERT_EQ(cases[i]["name"], web[i]["name"]);
    if (cases[i]["python"]["ok"].get<bool>() != web[i]["ok"].get<bool>()) {
      differ++;
    }
  }
  /* Python (and C++) and the web decoder disagree on some cases; the list is part of the WP4 report. */
  std::printf("[payload parity] python vs web decoder verdicts differ on %d of %zu cases\n", differ, cases.size());
  SUCCEED();
}
