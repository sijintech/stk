/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/format.hh"

#include "stk/io/json.hh"
#include "stk/io/payload.hh"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>

namespace stk::viewer {

namespace {

/* |value| = 0.d1 d2 d3 ... x 10^point (digits without leading zeros; "0" for zero). */
struct Decimal {
  std::string digits;
  int point = 1;
  bool negative = false;
};

/* The exact decimal expansion of a finite double (%.767e prints every significant digit). */
Decimal exact_decimal(double value)
{
  Decimal d;
  d.negative = std::signbit(value);
  value = std::fabs(value);
  if (value == 0.0 || !std::isfinite(value)) {
    d.digits = "0"; /* callers handle non-finite values before */
    d.point = 1;
    return d;
  }
  static thread_local char buffer[1100];
  std::snprintf(buffer, sizeof(buffer), "%.767e", value);
  const char *e = std::strchr(buffer, 'e');
  for (const char *c = buffer; c < e; c++) {
    if (*c >= '0' && *c <= '9') {
      d.digits.push_back(*c);
    }
  }
  while (d.digits.size() > 1 && d.digits.back() == '0') {
    d.digits.pop_back();
  }
  d.point = std::atoi(e + 1) + 1;
  return d;
}

enum class Tie { Even };

/* Keep the first `keep` digits (keep may be <= 0), rounding the rest; returns the new digits (exactly
 * `max(keep, 0)` of them, or keep + 1 on carry, adjusting point). */
Decimal round_digits(const Decimal &in, int keep, Tie tie)
{
  Decimal out = in;
  if (in.digits == "0") {
    out.digits.assign(size_t(std::max(keep, 0)), '0');
    return out;
  }
  if (keep >= int(in.digits.size())) {
    out.digits.append(size_t(keep) - in.digits.size(), '0');
    return out;
  }
  bool up = false;
  if (keep >= 0) {
    const char first = in.digits[size_t(keep)];
    bool rest = false;
    for (size_t i = size_t(keep) + 1; i < in.digits.size(); i++) {
      rest |= in.digits[i] != '0';
    }
    if (first > '5' || (first == '5' && rest)) {
      up = true;
    }
    else if (first == '5') {
      (void)tie; /* ties to even (Python format) */
      const int last = keep > 0 ? in.digits[size_t(keep) - 1] - '0' : 0;
      up = last % 2 == 1;
    }
  }
  out.digits = keep > 0 ? in.digits.substr(0, size_t(keep)) : std::string();
  if (up) {
    int i = int(out.digits.size()) - 1;
    while (i >= 0 && out.digits[size_t(i)] == '9') {
      out.digits[size_t(i)] = '0';
      i--;
    }
    if (i >= 0) {
      out.digits[size_t(i)]++;
    }
    else {
      out.digits.insert(out.digits.begin(), '1');
      out.point++;
    }
  }
  return out;
}

/* Fixed notation with `frac` fraction digits (no sign). */
std::string fixed(const Decimal &value, int frac, Tie tie)
{
  const Decimal r = round_digits(value, value.point + frac, tie);
  std::string digits = r.digits;
  int point = r.point;
  if (value.digits == "0") {
    point = 1;
    digits = std::string(size_t(frac) + 1, '0');
  }
  /* Integer part: digits[0 .. point), zero-extended; leading zeros when point <= 0. */
  std::string integer, fraction;
  if (point <= 0) {
    integer = "0";
    fraction = std::string(size_t(-point), '0') + digits;
  }
  else {
    if (int(digits.size()) < point) {
      digits.append(size_t(point) - digits.size(), '0');
    }
    integer = digits.substr(0, size_t(point));
    fraction = digits.substr(size_t(point));
  }
  if (int(fraction.size()) < frac) {
    fraction.append(size_t(frac) - fraction.size(), '0');
  }
  fraction.resize(size_t(frac));
  const size_t nonzero = integer.find_first_not_of('0');
  integer = nonzero == std::string::npos ? "0" : integer.substr(nonzero);
  return frac > 0 ? integer + "." + fraction : integer;
}

/* Scientific notation with `frac` mantissa fraction digits: mantissa digits and the exponent. */
void scientific(const Decimal &value, int frac, Tie tie, std::string &mantissa, int &exponent)
{
  if (value.digits == "0") {
    mantissa = frac > 0 ? "0." + std::string(size_t(frac), '0') : "0";
    exponent = 0;
    return;
  }
  const Decimal r = round_digits(value, frac + 1, tie);
  mantissa = r.digits.substr(0, 1);
  if (frac > 0) {
    mantissa += "." + r.digits.substr(1, size_t(frac));
  }
  exponent = r.point - 1;
}

std::string exponent_text(int exponent, int min_digits)
{
  char buffer[16];
  std::snprintf(buffer, sizeof(buffer), "%c%0*d", exponent < 0 ? '-' : '+', min_digits, std::abs(exponent));
  return buffer;
}

std::string strip_zeros(const std::string &text)
{
  if (text.find('.') == std::string::npos) {
    return text;
  }
  size_t end = text.find_last_not_of('0');
  if (text[end] == '.') {
    end--;
  }
  return text.substr(0, end + 1);
}

std::string group_thousands(const std::string &integer, int min_width)
{
  std::string out;
  int count = 0;
  for (int i = int(integer.size()) - 1; i >= 0; i--) {
    if (count && count % 3 == 0) {
      out.push_back(',');
    }
    out.push_back(integer[size_t(i)]);
    count++;
  }
  /* Zero padding is grouped too (Python): never start with a separator. */
  while (int(out.size()) < min_width) {
    if (count % 3 == 0) {
      out.push_back(',');
    }
    out.push_back('0');
    count++;
  }
  std::reverse(out.begin(), out.end());
  return out;
}

/* Sign, alignment, zero padding and grouping of a formatted magnitude (`body` = integer part digits,
 * `rest` = fraction/exponent/suffix). */
std::string finish(const LabelFormat &f, bool negative, const std::string &integer, const std::string &rest, bool numeric)
{
  std::string sign;
  if (negative) {
    sign = "-";
  }
  else if (f.sign == '+') {
    sign = "+";
  }
  else if (f.sign == ' ') {
    sign = " ";
  }
  std::string body;
  if (f.zero_pad && numeric) {
    const int min_width = std::max(0, f.width - int(sign.size()) - int(rest.size()));
    if (f.grouping) {
      body = group_thousands(integer, min_width);
    }
    else {
      body = integer;
      if (int(body.size()) < min_width) {
        body.insert(0, size_t(min_width) - body.size(), '0');
      }
    }
    return sign + body + rest;
  }
  body = f.grouping && numeric ? group_thousands(integer, 0) : integer;
  std::string text = sign + body + rest;
  if (f.zero_pad && !numeric) {
    /* inf/nan with '0': Python pads with zeros after the sign as well. */
    const std::string payload = body + rest;
    const int pad = f.width - int(sign.size()) - int(payload.size());
    return sign + std::string(size_t(std::max(pad, 0)), '0') + payload;
  }
  const int pad = f.width - int(text.size());
  return pad > 0 ? std::string(size_t(pad), ' ') + text : text;
}

bool is_upper(char type)
{
  return type == 'E' || type == 'F' || type == 'G';
}

std::string format_python(double value, const LabelFormat &f);

}  // namespace

std::optional<LabelFormat> parse_label_format(std::string_view s)
{
  if (!io::is_label_format(s)) {
    return std::nullopt;
  }
  LabelFormat f;
  size_t i = 0;
  if (i < s.size() && (s[i] == '+' || s[i] == '-' || s[i] == ' ')) {
    f.sign = s[i++];
  }
  if (i < s.size() && s[i] == '#') {
    f.alternate = true;
    i++;
  }
  if (i < s.size() && s[i] == '0') {
    f.zero_pad = true;
    i++;
  }
  while (i < s.size() && s[i] >= '0' && s[i] <= '9') {
    f.width = f.width * 10 + (s[i++] - '0');
  }
  if (i < s.size() && s[i] == ',') {
    f.grouping = true;
    i++;
  }
  if (i < s.size() && s[i] == '.') {
    i++;
    f.precision = 0;
    while (i < s.size() && s[i] >= '0' && s[i] <= '9') {
      f.precision = f.precision * 10 + (s[i++] - '0');
    }
  }
  if (i < s.size()) {
    f.type = s[i];
  }
  return f;
}

namespace {

/* Python format(value, spec) of a spec of the subset (an integral value for `d`). */
std::string format_python(double value, const LabelFormat &f)
{
  const bool negative = std::signbit(value) && !std::isnan(value);
  if (!std::isfinite(value)) {
    std::string text = std::isnan(value) ? "nan" : "inf";
    if (is_upper(f.type)) {
      text = std::isnan(value) ? "NAN" : "INF";
    }
    return finish(f, negative, text, f.type == '%' ? "%" : "", false);
  }
  char type = f.type;
  if (type == 'd') {
    /* An integer (the caller rounded it): exact digits of the integral double. */
    const Decimal d = exact_decimal(value);
    return finish(f, negative && d.digits != "0", fixed(d, 0, Tie::Even), "", true);
  }
  double v = value;
  if (type == '%') {
    v = value * 100.0;
    if (!std::isfinite(v)) {
      return finish(f, negative, "inf", "%", false); /* format(1e308, '%') == 'inf%' */
    }
  }
  const Decimal d = exact_decimal(v);
  std::string text;
  if (type == 'f' || type == 'F' || type == '%') {
    const int p = f.precision < 0 ? 6 : f.precision;
    text = fixed(d, p, Tie::Even);
    if (f.alternate && p == 0) {
      text += ".";
    }
    if (type == '%') {
      text += "%";
    }
  }
  else if (type == 'e' || type == 'E') {
    const int p = f.precision < 0 ? 6 : f.precision;
    std::string mantissa;
    int exponent;
    scientific(d, p, Tie::Even, mantissa, exponent);
    if (f.alternate && p == 0) {
      mantissa += ".";
    }
    text = mantissa + (type == 'E' ? "E" : "e") + exponent_text(exponent, 2);
  }
  else if (type == 'g' || type == 'G' || (type == 0 && f.precision >= 0)) {
    /* Python: round to p significant digits, then fixed if -4 <= exp < p (no type: exp < p - 1 ...
     * and at least one fraction digit), else scientific; trailing zeros removed unless '#'. */
    int p = f.precision < 0 ? 6 : f.precision;
    if (p == 0) {
      p = 1;
    }
    std::string mantissa;
    int exponent;
    scientific(d, p - 1, Tie::Even, mantissa, exponent);
    if (d.digits == "0") {
      exponent = 0;
    }
    const bool none = type == 0;
    const bool use_fixed = exponent >= -4 && exponent < (none ? p - 1 : p);
    if (use_fixed) {
      text = fixed(d, std::max(0, p - 1 - exponent), Tie::Even);
      if (!f.alternate) {
        text = strip_zeros(text);
      }
      else if (text.find('.') == std::string::npos) {
        text += ".";
      }
      if (none && text.find('.') == std::string::npos) {
        text += ".0";
      }
    }
    else {
      if (!f.alternate) {
        mantissa = strip_zeros(mantissa);
      }
      else if (mantissa.find('.') == std::string::npos) {
        mantissa += ".";
      }
      text = mantissa + (type == 'G' ? "E" : "e") + exponent_text(exponent, 2);
    }
  }
  else {
    /* No type, no precision: repr (shortest round trip). */
    text = io::python_float_repr(std::fabs(v));
    if (f.alternate && text.find('.') == std::string::npos && text.find('e') != std::string::npos) {
      const size_t e = text.find('e');
      text.insert(e, ".");
    }
  }
  /* Split into integer digits and the rest for sign/padding/grouping. */
  size_t end = 0;
  while (end < text.size() && text[end] >= '0' && text[end] <= '9') {
    end++;
  }
  return finish(f, negative, text.substr(0, end), text.substr(end), true);
}

std::string format_rounded(double value, const LabelFormat &f)
{
  if (f.type == 'd' && std::isfinite(value)) {
    /* Python round(): half to even, exact. */
    const double r = std::nearbyint(value); /* default rounding mode: to nearest, ties to even */
    return format_python(r == 0.0 ? 0.0 : r, f);
  }
  return format_python(value, f);
}

}  // namespace

std::string format_label(double value, std::string_view spec)
{
  auto parsed = parse_label_format(spec);
  if (!parsed) {
    parsed = parse_label_format(".3g");
  }
  const std::string text = format_rounded(value, *parsed);
  /* A label that shows zero never carries a minus sign (Python's `z` option). */
  if (std::isfinite(value) && std::signbit(value) && text.find_first_of("123456789") == std::string::npos) {
    return format_rounded(-value, *parsed);
  }
  return text;
}

std::vector<ScalarBarTick> scalar_bar_ticks(double lo, double hi, int count, std::string_view spec)
{
  count = std::max(2, std::min(20, count));
  std::vector<ScalarBarTick> ticks;
  for (int k = 0; k < count; k++) {
    const double value = lo + ((hi - lo) * k) / (count - 1);
    ticks.push_back({double(k) / (count - 1), value, format_label(value, spec)});
  }
  return ticks;
}

}  // namespace stk::viewer
