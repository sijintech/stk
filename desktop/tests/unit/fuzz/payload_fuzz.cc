/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Payload decoder fuzzer.
 *
 *  - libFuzzer (Clang, STK_LIBFUZZER):  stk_payload_fuzz -max_total_time=600 <corpus dir>
 *  - standalone (any compiler; build with STK_UNIT_SANITIZE=ON for ASan/UBSan):
 *      stk_payload_fuzz --seconds 600 --corpus desktop/tests/unit/fixtures/fuzz_corpus [--seed N]
 *    mutates the corpus with the structure-aware mutator of payload_fuzz_lib.cc until the time is up;
 *    exits 1 (after writing crash-<n>.stkp) when anything but PayloadError escapes the decoder. */
#include "payload_fuzz.hh"

#include "stk/core/clock.hh"
#include "stk/core/mmap.hh"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>

#ifdef STK_LIBFUZZER

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
  static stk::fuzz::Stats stats;
  stk::fuzz::run_one(data, size, stats); /* a logic_error aborts the run: libFuzzer reports the input */
  return 0;
}

#else

int main(int argc, char **argv)
{
  double seconds = 10;
  uint64_t seed = 20260925;
  std::string corpus_dir = STK_FIXTURES_DIR "/fuzz_corpus";
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string key = argv[i];
    if (key == "--seconds") {
      seconds = std::atof(argv[i + 1]);
    }
    else if (key == "--seed") {
      seed = std::strtoull(argv[i + 1], nullptr, 10);
    }
    else if (key == "--corpus") {
      corpus_dir = argv[i + 1];
    }
  }
  std::vector<std::vector<uint8_t>> corpus = stk::fuzz::load_corpus(corpus_dir);
  if (corpus.empty()) {
    std::fprintf(stderr, "empty corpus %s\n", corpus_dir.c_str());
    return 2;
  }
  std::mt19937_64 rng(seed);
  stk::fuzz::Stats stats;
  stk::core::Stopwatch watch;
  double next_report = 30;
  uint64_t crashes = 0;
  /* Inputs that decoded are added to the working set (bounded) so later mutations start from them. */
  std::vector<std::vector<uint8_t>> pool = corpus;
  while (watch.seconds() < seconds) {
    const std::vector<uint8_t> &base = pool[std::uniform_int_distribution<size_t>(0, pool.size() - 1)(rng)];
    std::vector<uint8_t> input = stk::fuzz::mutate(base, corpus, rng);
    if (std::uniform_int_distribution<int>(0, 3)(rng) == 0) {
      input = stk::fuzz::mutate(input, corpus, rng);
    }
    const uint64_t accepted = stats.accepted;
    try {
      stk::fuzz::run_one(input.data(), input.size(), stats);
    }
    catch (const std::logic_error &error) {
      const std::string name = "crash-" + std::to_string(crashes++) + ".stkp";
      stk::core::write_file_atomic(name, input);
      std::fprintf(stderr, "FAILURE %s (input saved to %s)\n", error.what(), name.c_str());
      if (crashes >= 5) {
        break;
      }
    }
    if (stats.accepted != accepted && pool.size() < 4096) {
      pool.push_back(std::move(input));
    }
    if (watch.seconds() > next_report) {
      std::printf("[fuzz] %.0fs: %llu runs, %llu decoded, %llu rejected, pool %zu\n", watch.seconds(),
                  (unsigned long long)stats.runs, (unsigned long long)stats.accepted,
                  (unsigned long long)stats.rejected, pool.size());
      std::fflush(stdout);
      next_report += 30;
    }
  }
  std::printf("[fuzz] done: %.1fs, %llu runs (%.0f/s), %llu decoded, %llu rejected, %llu failures, seed %llu\n",
              watch.seconds(), (unsigned long long)stats.runs, stats.runs / std::max(1e-9, watch.seconds()),
              (unsigned long long)stats.accepted, (unsigned long long)stats.rejected, (unsigned long long)crashes,
              (unsigned long long)seed);
  return crashes ? 1 : 0;
}

#endif
