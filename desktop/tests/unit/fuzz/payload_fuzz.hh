/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Payload decoder fuzzing shared by the libFuzzer target, the standalone time-limited driver and the
 * short randomized gtest: a structure-aware mutator for .stkp bytes (raw byte edits, JSON-level edits
 * of the manifest re-packed with valid framing, and blob edits with the sha256 fixed up so the
 * data-level checks are reached) and the checked operation (decode, then exercise every accessor and
 * the viewer-model consumers of a payload that decoded). */

#include <cstddef>
#include <cstdint>
#include <random>
#include <string>
#include <vector>

namespace stk::fuzz {

struct Stats {
  uint64_t runs = 0, accepted = 0, rejected = 0;
};

/** Decode `data` as .stkp and, when valid, use it like the viewer does. Throws std::logic_error when
 * an exception other than PayloadError escapes (a bug). */
void run_one(const uint8_t *data, size_t size, Stats &stats);

/** One mutation of `input` (the result is always a byte string; it may or may not be a valid .stkp). */
std::vector<uint8_t> mutate(const std::vector<uint8_t> &input, const std::vector<std::vector<uint8_t>> &corpus,
                            std::mt19937_64 &rng);

/** Load every file of a corpus directory. */
std::vector<std::vector<uint8_t>> load_corpus(const std::string &directory);

}  // namespace stk::fuzz
