/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "png_min.hh"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>

#include <zlib.h>

namespace stk::spike {

static void put_u32(std::vector<uint8_t> &out, uint32_t v)
{
  out.push_back(uint8_t(v >> 24));
  out.push_back(uint8_t(v >> 16));
  out.push_back(uint8_t(v >> 8));
  out.push_back(uint8_t(v));
}

static uint32_t get_u32(const uint8_t *p)
{
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
}

static void put_chunk(std::vector<uint8_t> &out, const char type[4], const std::vector<uint8_t> &data)
{
  put_u32(out, uint32_t(data.size()));
  const size_t start = out.size();
  out.insert(out.end(), type, type + 4);
  out.insert(out.end(), data.begin(), data.end());
  put_u32(out, uint32_t(crc32(0, out.data() + start, uInt(out.size() - start))));
}

static const uint8_t png_sig[8] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'};

bool png_write(const std::string &path, const Image &img)
{
  std::vector<uint8_t> raw;
  raw.reserve(size_t(img.height) * (img.width * 4 + 1));
  for (int y = 0; y < img.height; y++) {
    raw.push_back(0); /* Filter: none. */
    const uint8_t *row = img.px(0, y);
    raw.insert(raw.end(), row, row + size_t(img.width) * 4);
  }
  uLongf zlen = compressBound(uLong(raw.size()));
  std::vector<uint8_t> z(zlen);
  if (compress2(z.data(), &zlen, raw.data(), uLong(raw.size()), 6) != Z_OK) {
    return false;
  }
  z.resize(zlen);

  std::vector<uint8_t> out(png_sig, png_sig + 8);
  std::vector<uint8_t> ihdr;
  put_u32(ihdr, uint32_t(img.width));
  put_u32(ihdr, uint32_t(img.height));
  ihdr.insert(ihdr.end(), {8, 6, 0, 0, 0}); /* 8-bit, RGBA, deflate, adaptive, no interlace. */
  put_chunk(out, "IHDR", ihdr);
  put_chunk(out, "IDAT", z);
  put_chunk(out, "IEND", {});

  FILE *f = fopen(path.c_str(), "wb");
  if (!f) {
    return false;
  }
  const bool ok = fwrite(out.data(), 1, out.size(), f) == out.size();
  return (fclose(f) == 0) && ok;
}

static uint8_t paeth(int a, int b, int c)
{
  const int p = a + b - c, pa = std::abs(p - a), pb = std::abs(p - b), pc = std::abs(p - c);
  return uint8_t((pa <= pb && pa <= pc) ? a : (pb <= pc ? b : c));
}

bool png_read(const std::string &path, Image &img, std::string &err)
{
  std::ifstream in(path, std::ios::binary);
  std::vector<uint8_t> buf((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  if (buf.size() < 8 || memcmp(buf.data(), png_sig, 8) != 0) {
    err = "not a PNG: " + path;
    return false;
  }
  int bpp = 0;
  std::vector<uint8_t> z;
  for (size_t pos = 8; pos + 12 <= buf.size();) {
    const uint32_t len = get_u32(&buf[pos]);
    const char *type = reinterpret_cast<const char *>(&buf[pos + 4]);
    const uint8_t *data = &buf[pos + 8];
    if (pos + 12 + len > buf.size()) {
      err = "truncated chunk";
      return false;
    }
    if (memcmp(type, "IHDR", 4) == 0) {
      img.width = int(get_u32(data));
      img.height = int(get_u32(data + 4));
      if (data[8] != 8 || (data[9] != 6 && data[9] != 2) || data[12] != 0) {
        err = "unsupported PNG format (need 8-bit RGB/RGBA, non-interlaced)";
        return false;
      }
      bpp = data[9] == 6 ? 4 : 3;
    }
    else if (memcmp(type, "IDAT", 4) == 0) {
      z.insert(z.end(), data, data + len);
    }
    pos += 12 + len;
  }
  if (!bpp) {
    err = "missing IHDR";
    return false;
  }
  const size_t stride = size_t(img.width) * bpp;
  std::vector<uint8_t> raw((stride + 1) * img.height);
  uLongf rawlen = uLongf(raw.size());
  if (uncompress(raw.data(), &rawlen, z.data(), uLong(z.size())) != Z_OK || rawlen != raw.size()) {
    err = "inflate failed";
    return false;
  }
  std::vector<uint8_t> prev(stride, 0), cur(stride);
  img.rgba.assign(size_t(img.width) * img.height * 4, 255);
  for (int y = 0; y < img.height; y++) {
    const uint8_t filter = raw[y * (stride + 1)];
    const uint8_t *src = &raw[y * (stride + 1) + 1];
    for (size_t i = 0; i < stride; i++) {
      const int a = i >= size_t(bpp) ? cur[i - bpp] : 0, b = prev[i],
                c = i >= size_t(bpp) ? prev[i - bpp] : 0;
      int v = src[i];
      switch (filter) {
        case 1: v += a; break;
        case 2: v += b; break;
        case 3: v += (a + b) / 2; break;
        case 4: v += paeth(a, b, c); break;
        default: break;
      }
      cur[i] = uint8_t(v);
    }
    for (int x = 0; x < img.width; x++) {
      memcpy(&img.rgba[(size_t(y) * img.width + x) * 4], &cur[size_t(x) * bpp], bpp);
    }
    std::swap(prev, cur);
  }
  return true;
}

}  // namespace stk::spike
