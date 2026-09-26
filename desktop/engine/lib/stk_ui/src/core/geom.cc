/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/geom.hh"

#include <cstdio>

namespace stk::ui {

static uint8_t to_byte(float v)
{
  return uint8_t(std::clamp(v, 0.0f, 1.0f) * 255.0f + 0.5f);
}

Color Color::from_float(float r, float g, float b, float a)
{
  return {to_byte(r), to_byte(g), to_byte(b), to_byte(a)};
}

static void rgb_to_hsl(float r, float g, float b, float &h, float &s, float &l)
{
  const float mx = std::max({r, g, b}), mn = std::min({r, g, b});
  l = 0.5f * (mx + mn);
  if (mx == mn) {
    h = s = 0.0f;
    return;
  }
  const float d = mx - mn;
  s = l > 0.5f ? d / (2.0f - mx - mn) : d / (mx + mn);
  if (mx == r) {
    h = (g - b) / d + (g < b ? 6.0f : 0.0f);
  }
  else if (mx == g) {
    h = (b - r) / d + 2.0f;
  }
  else {
    h = (r - g) / d + 4.0f;
  }
  h /= 6.0f;
}

static float hue_to_rgb(float p, float q, float t)
{
  if (t < 0.0f) {
    t += 1.0f;
  }
  if (t > 1.0f) {
    t -= 1.0f;
  }
  if (t < 1.0f / 6.0f) {
    return p + (q - p) * 6.0f * t;
  }
  if (t < 0.5f) {
    return q;
  }
  if (t < 2.0f / 3.0f) {
    return p + (q - p) * (2.0f / 3.0f - t) * 6.0f;
  }
  return p;
}

static void hsl_to_rgb(float h, float s, float l, float &r, float &g, float &b)
{
  if (s == 0.0f) {
    r = g = b = l;
    return;
  }
  const float q = l < 0.5f ? l * (1.0f + s) : l + s - l * s;
  const float p = 2.0f * l - q;
  r = hue_to_rgb(p, q, h + 1.0f / 3.0f);
  g = hue_to_rgb(p, q, h);
  b = hue_to_rgb(p, q, h - 1.0f / 3.0f);
}

Color Color::mul_hsl(float hf, float sf, float lf) const
{
  float h, s, l;
  rgb_to_hsl(r / 255.0f, g / 255.0f, b / 255.0f, h, s, l);
  h = std::clamp(h * hf, 0.0f, 1.0f);
  s = std::clamp(s * sf, 0.0f, 1.0f);
  l = std::clamp(l * lf, 0.0f, 1.0f);
  float rr, gg, bb;
  hsl_to_rgb(h, s, l, rr, gg, bb);
  return {to_byte(rr), to_byte(gg), to_byte(bb), a};
}

Color Color::blend(const Color &o, float fac) const
{
  auto mix = [fac](uint8_t x, uint8_t y) { return uint8_t(std::lround(x + (float(y) - float(x)) * fac)); };
  return {mix(r, o.r), mix(g, o.g), mix(b, o.b), mix(a, o.a)};
}

std::string Color::to_hex() const
{
  char buf[16];
  std::snprintf(buf, sizeof(buf), "#%02x%02x%02x%02x", r, g, b, a);
  return buf;
}

}  // namespace stk::ui
