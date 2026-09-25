/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/number.hh"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <cstdio>
#include <locale>
#include <sstream>

#include "stk/ui/utf8.hh"

namespace stk::ui {

double NumberProps::soft_lo() const
{
  return std::isnan(soft_min) ? min : soft_min;
}

double NumberProps::soft_hi() const
{
  return std::isnan(soft_max) ? max : soft_max;
}

static double quantum(const NumberProps &p)
{
  return p.integer ? 1.0 : std::pow(10.0, -std::max(0, p.precision));
}

double clamp_number(double v, const NumberProps &p)
{
  if (std::isnan(v)) {
    return v;
  }
  if (p.integer) {
    v = std::round(v);
  }
  if (v < p.min || (p.exclusive_min && v <= p.min)) {
    v = p.exclusive_min ? p.min + quantum(p) : p.min;
  }
  if (v > p.max || (p.exclusive_max && v >= p.max)) {
    v = p.exclusive_max ? p.max - quantum(p) : p.max;
  }
  return v;
}

static std::string trim_exponent(std::string s)
{
  /* "1.000e-04" keeps the mantissa precision; C prints at least two exponent digits already. */
  return s;
}

std::string format_number(double v, const NumberProps &p)
{
  char buf[64];
  if (std::isnan(v)) {
    return "nan";
  }
  if (std::isinf(v)) {
    return v > 0 ? "inf" : "-inf";
  }
  if (p.integer) {
    std::snprintf(buf, sizeof(buf), "%.0f", v);
    return buf;
  }
  const int prec = std::clamp(p.precision, 0, 12);
  const double a = std::fabs(v);
  if (a != 0.0 && (a < 0.5 * std::pow(10.0, -prec) || a >= 1e7)) {
    std::snprintf(buf, sizeof(buf), "%.*e", std::max(prec, 1), v);
    return trim_exponent(buf);
  }
  std::snprintf(buf, sizeof(buf), "%.*f", prec, v);
  if (std::string_view(buf) == "-0" || (buf[0] == '-' && std::strtod(buf, nullptr) == 0.0)) {
    return std::string(buf + 1);
  }
  return buf;
}

std::string format_number_edit(double v, const NumberProps &p)
{
  char buf[64];
  if (p.integer) {
    std::snprintf(buf, sizeof(buf), "%.0f", v);
    return buf;
  }
  for (int digits = 6; digits <= 17; digits++) {
    std::snprintf(buf, sizeof(buf), "%.*g", digits, v);
    std::istringstream is(buf);
    is.imbue(std::locale::classic());
    double back = 0.0;
    is >> back;
    if (back == v) {
      break;
    }
  }
  return buf;
}

/* -------------------------------------------------------------------- */
/* Tiny expression parser: + - * / ^ ( ) unary minus, pi, e-notation numbers. */

namespace {

struct ExprParser {
  std::string_view s;
  size_t i = 0;
  std::string err;

  void ws()
  {
    while (i < s.size() && (s[i] == ' ' || s[i] == '\t')) {
      i++;
    }
  }

  bool number(double &out)
  {
    const size_t start = i;
    bool digits = false;
    while (i < s.size() && std::isdigit((unsigned char)s[i])) {
      i++;
      digits = true;
    }
    if (i < s.size() && s[i] == '.') {
      i++;
      while (i < s.size() && std::isdigit((unsigned char)s[i])) {
        i++;
        digits = true;
      }
    }
    if (!digits) {
      i = start;
      return false;
    }
    if (i < s.size() && (s[i] == 'e' || s[i] == 'E')) {
      size_t j = i + 1;
      if (j < s.size() && (s[j] == '+' || s[j] == '-')) {
        j++;
      }
      if (j < s.size() && std::isdigit((unsigned char)s[j])) {
        while (j < s.size() && std::isdigit((unsigned char)s[j])) {
          j++;
        }
        i = j;
      }
    }
    std::istringstream is(std::string(s.substr(start, i - start)));
    is.imbue(std::locale::classic());
    is >> out;
    return !is.fail();
  }

  bool primary(double &out)
  {
    ws();
    if (i >= s.size()) {
      err = "unexpected end";
      return false;
    }
    if (s[i] == '(') {
      i++;
      if (!expr(out)) {
        return false;
      }
      ws();
      if (i >= s.size() || s[i] != ')') {
        err = "missing ')'";
        return false;
      }
      i++;
      return true;
    }
    if (s[i] == '-' || s[i] == '+') {
      const bool neg = s[i] == '-';
      i++;
      if (!power(out)) {
        return false;
      }
      out = neg ? -out : out;
      return true;
    }
    if (s.substr(i, 2) == "pi") {
      i += 2;
      out = 3.14159265358979323846;
      return true;
    }
    if (!number(out)) {
      err = "not a number";
      return false;
    }
    return true;
  }

  bool power(double &out)
  {
    if (!primary(out)) {
      return false;
    }
    ws();
    if (i < s.size() && s[i] == '^') {
      i++;
      double e;
      if (!power(e)) {
        return false;
      }
      out = std::pow(out, e);
    }
    return true;
  }

  bool term(double &out)
  {
    if (!power(out)) {
      return false;
    }
    while (true) {
      ws();
      if (i < s.size() && (s[i] == '*' || s[i] == '/')) {
        const char op = s[i++];
        double r;
        if (!power(r)) {
          return false;
        }
        out = op == '*' ? out * r : out / r;
      }
      else {
        return true;
      }
    }
  }

  bool expr(double &out)
  {
    if (!term(out)) {
      return false;
    }
    while (true) {
      ws();
      if (i < s.size() && (s[i] == '+' || s[i] == '-')) {
        const char op = s[i++];
        double r;
        if (!term(r)) {
          return false;
        }
        out = op == '+' ? out + r : out - r;
      }
      else {
        return true;
      }
    }
  }
};

std::string normalize(std::string_view text)
{
  std::string s = utf8::fold_fullwidth(text);
  /* Ideographic full stop (Chinese punctuation mode) and the Unicode minus sign. */
  std::string out;
  for (size_t p = 0; p < s.size();) {
    size_t len = 1;
    const uint32_t cp = utf8::decode(s, p, &len);
    if (cp == 0x3002) {
      out += '.';
    }
    else if (cp == 0x2212) {
      out += '-';
    }
    else if (cp == 0x00D7) {
      out += '*';
    }
    else if (cp == 0x00F7) {
      out += '/';
    }
    else {
      out.append(s, p, len);
    }
    p += std::max<size_t>(len, 1);
  }
  return out;
}

std::string_view trim(std::string_view s)
{
  while (!s.empty() && (s.front() == ' ' || s.front() == '\t')) {
    s.remove_prefix(1);
  }
  while (!s.empty() && (s.back() == ' ' || s.back() == '\t')) {
    s.remove_suffix(1);
  }
  return s;
}

}  // namespace

std::optional<double> parse_number(std::string_view text, const NumberProps &p, std::string *err)
{
  const std::string norm = normalize(text);
  std::string_view s = trim(norm);
  if (!p.unit.empty() && s.size() > p.unit.size() && s.substr(s.size() - p.unit.size()) == p.unit) {
    s = trim(s.substr(0, s.size() - p.unit.size()));
  }
  if (s.empty()) {
    if (err) {
      *err = "empty";
    }
    return std::nullopt;
  }
  ExprParser ep;
  ep.s = s;
  double v = 0.0;
  bool ok = ep.expr(v);
  ep.ws();
  if (ok && ep.i != s.size()) {
    ok = false;
    ep.err = "unexpected '" + std::string(s.substr(ep.i, 1)) + "'";
  }
  if (!ok || !std::isfinite(v)) {
    if (err) {
      *err = ok ? "not finite" : ep.err;
    }
    return std::nullopt;
  }
  if (p.integer) {
    v = std::round(v);
  }
  return v;
}

}  // namespace stk::ui
