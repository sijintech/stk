/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Decoder parity (spec §10) of the three implementations on every case of fixtures/payload/cases.json (the
 * test_render_payload.py cases, data-level cases, .stkp corruptions, a seeded mutation corpus and the cases of the
 * reconciled rules): the C++ decoder gives the Python verdict (payload.py, the reference) with the same
 * JSON-pointer path, and the same warnings (skipped layers) when the payload is accepted; the web decoder
 * (web_vectors.json, web/src/payload.ts) gives the same verdicts and warnings too. */
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
  Json warnings = Json::array();
};

Outcome run_case(const Json &c, const Json &example_manifest, const std::map<std::string, core::SharedBytes> &blobs,
                 const std::vector<uint8_t> &example_stkp)
{
  io::Payload payload;
  try {
    const std::string kind = c["kind"].get<std::string>();
    if (kind == "example") {
      payload = io::decode(test::apply_patches(example_manifest, c["patches"]), blobs);
    }
    else if (kind == "blobs") {
      std::map<std::string, core::SharedBytes> own;
      for (auto it = c["blobs"].begin(); it != c["blobs"].end(); ++it) {
        own[it.key()] = core::SharedBytes::from_vector(test::base64_decode(it.value().get<std::string>()));
      }
      payload = io::decode(c["manifest"], own);
    }
    else if (kind == "stkp_bytes") {
      payload = io::decode_stkp(core::SharedBytes::from_vector(test::base64_decode(c["data"].get<std::string>())));
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
      payload = io::decode_stkp(core::SharedBytes::from_vector(std::move(bytes)));
    }
  }
  catch (const io::PayloadError &error) {
    return {false, error.path(), error.what()};
  }
  Outcome outcome{true, {}, {}};
  for (const io::PayloadWarning &warning : payload.warnings) {
    outcome.warnings.push_back(warning.path);
  }
  return outcome;
}

}  // namespace

TEST(PayloadParity, EveryCaseMatchesPython)
{
  const Json cases = test::fixture_json("payload/cases.json");
  const Json example = io::read_json_file(test::example_dir() / "manifest.json");
  const auto blobs = test::example_blobs();
  const std::vector<uint8_t> stkp = core::read_file(test::example_dir() / "example.stkp");
  int accepted = 0, rejected = 0, same_path = 0, python_paths = 0, warned = 0;
  for (const Json &c : cases) {
    const std::string name = c["name"].get<std::string>();
    const Json &python = c["python"];
    ASSERT_FALSE(python.value("crash", false)) << name << ": the Python reference crashed: " << python["message"];
    const Outcome cpp = run_case(c, example, blobs, stkp);
    if (python["ok"].get<bool>()) {
      EXPECT_TRUE(cpp.ok) << name << ": C++ rejected what Python accepts: " << cpp.message;
      EXPECT_EQ(cpp.warnings, python["warnings"]) << name << ": skipped layers differ";
      accepted++;
      warned += !python["warnings"].empty();
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
  std::printf("[payload parity] %zu cases: %d accepted (%d with skipped layers), %d rejected (%d/%d same JSON-pointer "
              "path)\n",
              cases.size(), accepted, warned, rejected, same_path, python_paths);
  EXPECT_GT(accepted, 100);
  EXPECT_GT(rejected, 300);
}

TEST(PayloadParity, WebDecoderGivesTheSameVerdictsAndWarnings)
{
  const Json cases = test::fixture_json("payload/cases.json");
  const Json web = test::fixture_json("web_vectors.json")["verdicts"];
  ASSERT_EQ(cases.size(), web.size());
  int differ = 0, warnings_differ = 0;
  for (size_t i = 0; i < cases.size(); i++) {
    ASSERT_EQ(cases[i]["name"], web[i]["name"]);
    const Json &python = cases[i]["python"];
    if (python["ok"].get<bool>() != web[i]["ok"].get<bool>()) {
      differ++;
      ADD_FAILURE() << cases[i]["name"] << ": python " << (python["ok"].get<bool>() ? "accepts" : "rejects")
                    << ", web " << web[i]["message"];
    }
    else if (python["ok"].get<bool>() && python["warnings"] != web[i]["warnings"]) {
      warnings_differ++;
      ADD_FAILURE() << cases[i]["name"] << ": skipped layers differ: python " << python["warnings"] << ", web "
                    << web[i]["warnings"];
    }
  }
  std::printf("[payload parity] python vs web decoder: %d of %zu verdicts differ, %d warning lists differ\n", differ,
              cases.size(), warnings_differ);
}
