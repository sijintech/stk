/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Number parsing (scientific notation, full-width digits, units, arithmetic), formatting and
 * limits. */
#include <cmath>

#include <gtest/gtest.h>

#include "stk/ui/number.hh"

using namespace stk::ui;

TEST(Number, ParsesScientificNotation)
{
  NumberProps p;
  EXPECT_DOUBLE_EQ(*parse_number("1e-3", p), 1e-3);
  EXPECT_DOUBLE_EQ(*parse_number("2.5E+4", p), 25000.0);
  EXPECT_DOUBLE_EQ(*parse_number("-1e-3", p), -1e-3);
  EXPECT_DOUBLE_EQ(*parse_number(" .5 ", p), 0.5);
  EXPECT_DOUBLE_EQ(*parse_number("1e3*2", p), 2000.0);
  EXPECT_DOUBLE_EQ(*parse_number("6.02214076e23", p), 6.02214076e23);
}

TEST(Number, ParsesArithmeticUnitsAndFullWidth)
{
  NumberProps p;
  p.unit = "nm";
  EXPECT_DOUBLE_EQ(*parse_number("0.1 nm", p), 0.1);
  EXPECT_DOUBLE_EQ(*parse_number("0.1nm", p), 0.1);
  EXPECT_NEAR(*parse_number("1/3", p), 1.0 / 3.0, 1e-15);
  EXPECT_NEAR(*parse_number("2*pi", p), 6.283185307179586, 1e-12);
  EXPECT_DOUBLE_EQ(*parse_number("(1+2)*2^2", p), 12.0);
  /* Full-width digits, ideographic full stop and the Unicode minus from CJK input methods. */
  EXPECT_DOUBLE_EQ(*parse_number("\xef\xbc\x91\xef\xbc\x8e\xef\xbc\x95", p), 1.5);   /* １．５ */
  EXPECT_DOUBLE_EQ(*parse_number("\xef\xbc\x92\xe3\x80\x82\xef\xbc\x95", p), 2.5);   /* ２。５ */
  EXPECT_DOUBLE_EQ(*parse_number("\xe2\x88\x92" "3", p), -3.0);                    /* −3 */
}

TEST(Number, RejectsGarbage)
{
  NumberProps p;
  std::string err;
  EXPECT_FALSE(parse_number("abc", p, &err));
  EXPECT_FALSE(err.empty());
  EXPECT_FALSE(parse_number("", p));
  EXPECT_FALSE(parse_number("1e", p));
  EXPECT_FALSE(parse_number("1..2", p));
  EXPECT_FALSE(parse_number("1/0", p));
  EXPECT_FALSE(parse_number("(1", p));
}

TEST(Number, IntegersRound)
{
  NumberProps p;
  p.integer = true;
  EXPECT_DOUBLE_EQ(*parse_number("2.6", p), 3.0);
  EXPECT_EQ(format_number(42, p), "42");
  EXPECT_EQ(format_number_edit(7, p), "7");
}

TEST(Number, Formats)
{
  NumberProps p;
  p.precision = 3;
  EXPECT_EQ(format_number(0.1, p), "0.100");
  EXPECT_EQ(format_number(1e-4, p), "1.000e-04");
  EXPECT_EQ(format_number(-2.5e8, p), "-2.500e+08");
  EXPECT_EQ(format_number(-0.0001, p), "-1.000e-04");
  EXPECT_EQ(format_number(0.0, p), "0.000");
  EXPECT_EQ(format_number_edit(0.001, p), "0.001");
  EXPECT_EQ(format_number_edit(1e-5, p), "1e-05");
  EXPECT_EQ(format_number_edit(0.1 + 0.2, p), "0.30000000000000004");
}

TEST(Number, ClampHardAndExclusive)
{
  NumberProps p;
  p.min = 0;
  p.max = 180;
  EXPECT_DOUBLE_EQ(clamp_number(-5, p), 0.0);
  EXPECT_DOUBLE_EQ(clamp_number(200, p), 180.0);
  p.exclusive_min = true;
  p.precision = 3;
  EXPECT_DOUBLE_EQ(clamp_number(0, p), 0.001);
  EXPECT_DOUBLE_EQ(clamp_number(0.5, p), 0.5);
  EXPECT_DOUBLE_EQ(p.soft_lo(), 0.0);
  p.soft_max = 90;
  EXPECT_DOUBLE_EQ(p.soft_hi(), 90.0);
}
