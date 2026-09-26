/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Label formatting parity (spec §6.7): format_label against suan.render.payload.format_label (the reference,
 * drawn by the offscreen renderer) and web/src/colormaps.ts formatNumber (the web legend), for every format of
 * the subset, a few invalid ones (".3g" fallback) and ties, negative zero and non-finite values. */
#include "support.hh"

#include "stk/viewer/format.hh"

#include <gtest/gtest.h>

#include <cmath>

using namespace stk;
using namespace stk::viewer;
using io::Json;

namespace {

double case_value(const Json &c)
{
  return c["negative_zero"].get<bool>() ? -0.0 : test::fixture_number(c["value"]);
}

}  // namespace

TEST(FormatParity, LabelsMatchPython)
{
  int count = 0;
  for (const Json &c : test::fixture_json("format_cases.json")) {
    EXPECT_EQ(format_label(case_value(c), c["format"].get<std::string>()), c["text"].get<std::string>())
        << "format_label(" << c["value"].dump() << ", " << c["format"] << ")";
    count++;
  }
  std::printf("[format parity] %d labels identical to Python format_label\n", count);
  EXPECT_GT(count, 3000);
}

TEST(FormatParity, WebLegendMatchesPython)
{
  int count = 0;
  const Json web = test::fixture_json("web_vectors.json");
  for (const Json &c : web["format"]) {
    const std::string what = "formatNumber(" + c["value"].dump() + ", " + c["format"].dump() + ")";
    EXPECT_EQ(c["text"], c["python"]) << what;
    EXPECT_EQ(format_label(case_value(c), c["format"].get<std::string>()), c["text"].get<std::string>()) << what;
    count++;
  }
  std::printf("[format parity] %d web labels identical to Python and C++\n", count);
  EXPECT_GT(count, 3000);
}

TEST(Format, TicksParsingAndRounding)
{
  const auto ticks = scalar_bar_ticks(0.0, 1.0, 5, ".2f");
  ASSERT_EQ(ticks.size(), 5u);
  EXPECT_EQ(ticks[1].label, "0.25");
  EXPECT_DOUBLE_EQ(ticks[4].fraction, 1.0);
  EXPECT_EQ(scalar_bar_ticks(0, 1, 1).size(), 2u);
  EXPECT_EQ(scalar_bar_ticks(0, 1, 99).size(), 20u);
  EXPECT_FALSE(parse_label_format("{}").has_value());
  EXPECT_FALSE(parse_label_format(".3g\n").has_value());
  const auto f = parse_label_format("+08,.2f");
  ASSERT_TRUE(f.has_value());
  EXPECT_EQ(f->sign, '+');
  EXPECT_TRUE(f->zero_pad);
  EXPECT_EQ(f->width, 8);
  EXPECT_TRUE(f->grouping);
  EXPECT_EQ(f->precision, 2);
  EXPECT_EQ(f->type, 'f');
  EXPECT_EQ(format_label(2.5, "d"), "2");       /* round half to even */
  EXPECT_EQ(format_label(3.5, "d"), "4");
  EXPECT_EQ(format_label(0.125, ".2f"), "0.12"); /* an exact binary tie: half to even */
  EXPECT_EQ(format_label(0.375, ".2f"), "0.38");
  EXPECT_EQ(format_label(-0.0, ".3g"), "0");     /* never "-0" */
  EXPECT_EQ(format_label(-0.0001, "+.2f"), "+0.00");
  EXPECT_EQ(format_label(-0.4, "d"), "0");
  EXPECT_EQ(format_label(-1e-300, ".3g"), "-1e-300");
  EXPECT_EQ(format_label(1.0, "{}"), "1");       /* outside the subset: ".3g" */
  EXPECT_EQ(format_label(-INFINITY, "+05d"), "-0inf");
}
