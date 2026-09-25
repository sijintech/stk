/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* SHA-256 (FIPS 180-4), incremental. Used for payload buffers and the blob cache. */

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <string_view>

namespace stk::core {

class Sha256 {
 public:
  using Digest = std::array<uint8_t, 32>;

  Sha256();
  void update(const void *data, size_t size);
  void update(std::span<const uint8_t> data)
  {
    update(data.data(), data.size());
  }
  void update(std::string_view data)
  {
    update(data.data(), data.size());
  }
  /** Finish and return the digest; the object is reset afterwards. */
  Digest finish();

  static Digest digest(const void *data, size_t size);
  /** Lower-case hex of the digest of `data`. */
  static std::string hex(const void *data, size_t size);
  static std::string hex(std::span<const uint8_t> data)
  {
    return hex(data.data(), data.size());
  }
  static std::string hex(std::string_view data)
  {
    return hex(data.data(), data.size());
  }

 private:
  void reset();
  void block(const uint8_t *p);

  std::array<uint32_t, 8> h_;
  std::array<uint8_t, 64> buffer_;
  uint64_t length_ = 0;
  size_t fill_ = 0;
};

std::string to_hex(std::span<const uint8_t> bytes);

/** True for 64 lower-case hex digits (the payload/blob-store sha256 form). */
bool is_sha256_hex(std::string_view text);

}  // namespace stk::core
