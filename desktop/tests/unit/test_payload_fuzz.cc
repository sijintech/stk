/* SPDX-License-Identifier: GPL-2.0-or-later */
/* A short randomized mutation run of the payload decoder inside the unit tests (the long run is the
 * stk_payload_fuzz target). Every mutated input must either decode or raise PayloadError. */
#include "fuzz/payload_fuzz.hh"
#include "support.hh"

#include "stk/core/clock.hh"
#include "stk/core/paths.hh"

#include <gtest/gtest.h>

TEST(PayloadFuzz, RandomizedMutationsNeverCrash)
{
  const auto corpus = stk::fuzz::load_corpus(stk::core::path_to_utf8(stk::test::fixtures_dir() / "fuzz_corpus"));
  ASSERT_FALSE(corpus.empty());
  std::mt19937_64 rng(1);
  stk::fuzz::Stats stats;
  stk::core::Stopwatch watch;
  while (stats.runs < 3000 && watch.seconds() < 20) {
    const auto &base = corpus[stats.runs % corpus.size()];
    const std::vector<uint8_t> input = stk::fuzz::mutate(base, corpus, rng);
    ASSERT_NO_THROW(stk::fuzz::run_one(input.data(), input.size(), stats));
  }
  EXPECT_GT(stats.accepted, 0u);
  EXPECT_GT(stats.rejected, 0u);
  std::printf("[fuzz] %llu mutated inputs: %llu decoded, %llu rejected\n", (unsigned long long)stats.runs,
              (unsigned long long)stats.accepted, (unsigned long long)stats.rejected);
}
