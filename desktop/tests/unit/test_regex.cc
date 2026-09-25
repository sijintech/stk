/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Python `re` parity of the schema pattern engine (fixtures/regex_cases.json). */
#include "support.hh"

#include "stk/core/clock.hh"
#include "stk/io/pyregex.hh"

#include <gtest/gtest.h>

using namespace stk;
using io::Json;

TEST(RegexParity, SearchMatchFullmatchLikePython)
{
  const Json fixture = test::fixture_json("regex_cases.json");
  int count = 0;
  const Json &texts = fixture["texts"];
  for (size_t p = 0; p < fixture["patterns"].size(); p++) {
    const std::string pattern = fixture["patterns"][p].get<std::string>();
    const io::PyRegex regex(pattern);
    const std::string results = fixture["results"][p].get<std::string>();
    for (size_t t = 0; t < texts.size(); t++) {
      const std::string text = texts[t].get<std::string>();
      const int bits = results[t] - '0';
      EXPECT_EQ(regex.search(text), (bits & 1) != 0) << "search " << pattern << " on " << Json(text).dump();
      EXPECT_EQ(regex.match(text), (bits & 2) != 0) << "match " << pattern << " on " << Json(text).dump();
      EXPECT_EQ(regex.fullmatch(text), (bits & 4) != 0) << "fullmatch " << pattern << " on " << Json(text).dump();
      count++;
    }
  }
  std::printf("[regex parity] %d pattern/text cases identical to Python re\n", count);
  for (const Json &c : fixture["invalid"]) {
    const std::string pattern = c["pattern"].get<std::string>();
    if (c["python_valid"].get<bool>()) {
      continue; /* e.g. possessive quantifiers: valid in Python 3.11+, rejected here as unsupported */
    }
    EXPECT_THROW(io::PyRegex{pattern}, io::RegexError) << pattern;
  }
}

TEST(Regex, UnsupportedSyntaxIsRejected)
{
  for (const char *pattern : {R"((a)\1)", "(?<=a)b", "(?i)a", "a++", R"(\N{DIGIT ONE})", "(?(1)a|b)"}) {
    EXPECT_THROW(io::PyRegex{pattern}, io::RegexError) << pattern;
  }
}

TEST(Regex, LongInputsAreLinearAndNeverOverflowTheStack)
{
  const io::PyRegex path(R"(^(?![/\\])(?![A-Za-z]:)(?!.*(^|/)\.\.(/|$))[^\\\u0000]+$)");
  std::string text(1 << 20, 'a');
  core::Stopwatch watch;
  EXPECT_TRUE(path.search(text));
  text += "/../x";
  EXPECT_FALSE(path.search(text));
  const io::PyRegex nested("(a*)*b");
  EXPECT_FALSE(nested.search(std::string(20000, 'a'))); /* catastrophic for backtracking engines */
  EXPECT_LT(watch.seconds(), 20.0);
}
