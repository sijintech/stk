/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/core/sha256.hh"

#include <algorithm>
#include <cstring>

namespace stk::core {

namespace {

constexpr uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

inline uint32_t rotr(uint32_t x, int n)
{
  return (x >> n) | (x << (32 - n));
}

}  // namespace

Sha256::Sha256()
{
  reset();
}

void Sha256::reset()
{
  h_ = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  length_ = 0;
  fill_ = 0;
}

void Sha256::block(const uint8_t *p)
{
  uint32_t w[64];
  for (int i = 0; i < 16; i++) {
    w[i] = uint32_t(p[4 * i]) << 24 | uint32_t(p[4 * i + 1]) << 16 | uint32_t(p[4 * i + 2]) << 8 |
           uint32_t(p[4 * i + 3]);
  }
  for (int i = 16; i < 64; i++) {
    const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
    const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = h_[0], b = h_[1], c = h_[2], d = h_[3], e = h_[4], f = h_[5], g = h_[6], h = h_[7];
  for (int i = 0; i < 64; i++) {
    const uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    const uint32_t ch = (e & f) ^ (~e & g);
    const uint32_t t1 = h + s1 + ch + K[i] + w[i];
    const uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    const uint32_t t2 = s0 + maj;
    h = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + t2;
  }
  h_[0] += a;
  h_[1] += b;
  h_[2] += c;
  h_[3] += d;
  h_[4] += e;
  h_[5] += f;
  h_[6] += g;
  h_[7] += h;
}

void Sha256::update(const void *data, size_t size)
{
  const uint8_t *p = static_cast<const uint8_t *>(data);
  length_ += size;
  if (fill_) {
    const size_t take = std::min(size, 64 - fill_);
    std::memcpy(buffer_.data() + fill_, p, take);
    fill_ += take;
    p += take;
    size -= take;
    if (fill_ < 64) {
      return;
    }
    block(buffer_.data());
    fill_ = 0;
  }
  while (size >= 64) {
    block(p);
    p += 64;
    size -= 64;
  }
  if (size) {
    std::memcpy(buffer_.data(), p, size);
    fill_ = size;
  }
}

Sha256::Digest Sha256::finish()
{
  const uint64_t bits = length_ * 8;
  const uint8_t pad = 0x80;
  update(&pad, 1);
  const uint8_t zero = 0;
  while (fill_ != 56) {
    update(&zero, 1);
  }
  uint8_t len[8];
  for (int i = 0; i < 8; i++) {
    len[i] = uint8_t(bits >> (56 - 8 * i));
  }
  update(len, 8);
  Digest out;
  for (int i = 0; i < 8; i++) {
    out[4 * i] = uint8_t(h_[i] >> 24);
    out[4 * i + 1] = uint8_t(h_[i] >> 16);
    out[4 * i + 2] = uint8_t(h_[i] >> 8);
    out[4 * i + 3] = uint8_t(h_[i]);
  }
  reset();
  return out;
}

Sha256::Digest Sha256::digest(const void *data, size_t size)
{
  Sha256 sha;
  sha.update(data, size);
  return sha.finish();
}

std::string Sha256::hex(const void *data, size_t size)
{
  const Digest d = digest(data, size);
  return to_hex(d);
}

std::string to_hex(std::span<const uint8_t> bytes)
{
  static const char digits[] = "0123456789abcdef";
  std::string out(bytes.size() * 2, '0');
  for (size_t i = 0; i < bytes.size(); i++) {
    out[2 * i] = digits[bytes[i] >> 4];
    out[2 * i + 1] = digits[bytes[i] & 15];
  }
  return out;
}

bool is_sha256_hex(std::string_view text)
{
  if (text.size() != 64) {
    return false;
  }
  for (char c : text) {
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
      return false;
    }
  }
  return true;
}

}  // namespace stk::core
