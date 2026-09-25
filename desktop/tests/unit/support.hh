/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Shared helpers of the unit tests: fixture paths, JSON patches and base64. */

#include "stk/core/mmap.hh"
#include "stk/io/json.hh"

#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace stk::test {

std::filesystem::path repo_root();
std::filesystem::path fixtures_dir();
std::filesystem::path example_dir(); /* docs/specs/examples/payload-v2 */
io::Json fixture_json(const std::string &name);
std::vector<uint8_t> base64_decode(const std::string &text);

/** make_fixtures.py patches: ["set" | "delete" | "append", path, value?]. */
io::Json apply_patches(io::Json manifest, const io::Json &patches);

/** The example payload's blobs keyed by sha256 (read from the directory form). */
std::map<std::string, core::SharedBytes> example_blobs();

/** JSON number from a fixture value that may be "nan"/"inf"/"-inf" strings. */
double fixture_number(const io::Json &value);

/** A scratch directory under the build tree, emptied on construction. */
std::filesystem::path scratch_dir(const std::string &name);

}  // namespace stk::test
