/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Label formatting parity: offscreen.py _label (Python format, 'd' = round half to even) for the
 * whole spec subset, and web/src/colormaps.ts formatNumber (the web legend). */
#include "support.hh"

#include "stk/viewer/format.hh"

#include <gtest/gtest.h>

#include <cmath>

using namespace stk;
using namespace stk::viewer;
using io::Json;

TEST(FormatParity, OffscreenLabelsMatchPython)
{
  int count = 0;
  for (const Json &c : test::fixture_json("format_cases.json")) {
    if (c["text"].is_null()) {
      continue; /* Python raises (round(nan)); the C++ labels print nan/inf instead */
    }
    const double value = test::fixture_number(c["value"]);
    EXPECT_EQ(format_label(value, c["format"].get<std::string>()), c["text"].get<std::string>())
        << "format(" << c["value"].dump() << ", " << c["format"] << ")";
    count++;
  }
  std::printf("[format parity] %d labels identical to the offscreen renderer (Python format)\n", count);
}

TEST(FormatParity, WebLegendMatchesFormatNumber)
{
  int count = 0;
  const Json fixture_1 = test::fixture_json("web_vectors.json");
  for (const Json &c : fixture_1["format"]) {
    double value = test::fixture_number(c["value"]);
    if (c["negative_zero"].get<bool>()) {
      value = -0.0;
    }
    EXPECT_EQ(format_number_web(value, c["format"].get<std::string>()), c["text"].get<std::string>())
        << "formatNumber(" << c["value"].dump() << ", " << c["format"] << ")";
    count++;
  }
  std::printf("[format parity] %d labels identical to web formatNumber\n", count);
}

TEST(Format, TicksAndParsing)
{
  const auto ticks = scalar_bar_ticks(0.0, 1.0, 5, ".2f");
  ASSERT_EQ(ticks.size(), 5u);
  EXPECT_EQ(ticks[1].label, "0.25");
  EXPECT_DOUBLE_EQ(ticks[4].fraction, 1.0);
  EXPECT_EQ(scalar_bar_ticks(0, 1, 1).size(), 2u);
  EXPECT_EQ(scalar_bar_ticks(0, 1, 99).size(), 20u);
  EXPECT_FALSE(parse_label_format("{}").has_value());
  EXPECT_THROW(format_python(1.0, ".3d"), std::invalid_argument);
  const auto f = parse_label_format("+08,.2f");
  ASSERT_TRUE(f.has_value());
  EXPECT_EQ(f->sign, '+');
  EXPECT_TRUE(f->zero_pad);
  EXPECT_EQ(f->width, 8);
  EXPECT_TRUE(f->grouping);
  EXPECT_EQ(f->precision, 2);
  EXPECT_EQ(f->type, 'f');
  EXPECT_EQ(format_label(2.5, "d"), "2");      /* Python round(): half to even */
  EXPECT_EQ(format_number_web(2.5, "d"), "3"); /* Math.round */
}
