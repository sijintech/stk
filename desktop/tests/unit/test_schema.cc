/* SPDX-License-Identifier: GPL-2.0-or-later */
/* JSON-Schema subset parity with suan.graph.schema.check_value / normalize_value: the exact
 * (JSON pointer, message) list for every case of fixtures/schema_cases.json (test_graph_schema.py
 * cases, hand-written edge cases and every M1 catalog param schema against probe values). */
#include "support.hh"

#include "stk/io/schema.hh"

#include <gtest/gtest.h>

using namespace stk;
using io::Json;

TEST(SchemaParity, CheckValueMatchesPythonExactly)
{
  const Json fixture = test::fixture_json("schema_cases.json");
  const Json &schemas = fixture["schemas"];
  const Json &values = fixture["values"];
  int checked = 0, invalid = 0, raises = 0;
  for (const Json &c : fixture["cases"]) {
    const Json &value = values[c[0].get<size_t>()];
    const Json &schema = schemas[c[1].get<size_t>()];
    const Json &expected = c[2];
    if (expected.is_object()) {
      EXPECT_THROW(io::check_value(value, schema), io::SchemaError) << value.dump() << " / " << schema.dump();
      raises++;
      continue;
    }
    std::vector<io::SchemaIssue> want;
    for (const Json &e : expected) {
      want.push_back({e[0].get<std::string>(), e[1].get<std::string>()});
    }
    std::vector<io::SchemaIssue> got;
    try {
      got = io::check_value(value, schema);
    }
    catch (const std::exception &error) {
      ADD_FAILURE() << "threw " << error.what() << " for " << value.dump() << " / " << schema.dump();
      continue;
    }
    ASSERT_EQ(got.size(), want.size()) << "value " << value.dump() << "\nschema " << schema.dump()
                                       << "\nfirst python: " << (want.empty() ? "" : want[0].path + " " + want[0].message)
                                       << "\nfirst c++:    " << (got.empty() ? "" : got[0].path + " " + got[0].message);
    for (size_t i = 0; i < got.size(); i++) {
      EXPECT_EQ(got[i].path, want[i].path) << value.dump() << " / " << schema.dump();
      EXPECT_EQ(got[i].message, want[i].message) << value.dump() << " / " << schema.dump();
    }
    checked++;
    invalid += !want.empty();
  }
  std::printf("[schema parity] %d cases (%d invalid, %d schema errors) identical to suan.graph.schema\n", checked,
              invalid, raises);
  EXPECT_GT(checked, 5000);
}

TEST(SchemaParity, NormalizeValueMatchesPython)
{
  const Json fixture_1 = test::fixture_json("graph_cases.json");
  for (const Json &c : fixture_1["normalize"]) {
    const Json got = io::normalize_value(c["value"], c["schema"]);
    EXPECT_EQ(io::python_json_dumps(got), io::python_json_dumps(c["normalized"])) << c.dump();
  }
}

TEST(Schema, CloseMatchesLikeDifflib)
{
  /* difflib.get_close_matches */
  EXPECT_EQ(io::close_matches("rnage", {"by", "range"}, 1), std::vector<std::string>{"range"});
  EXPECT_EQ(io::close_matches("appel", {"ape", "apple", "peach", "puppy"}), (std::vector<std::string>{"apple", "ape"}));
  EXPECT_TRUE(io::close_matches("zzzz", {"preset", "position"}).empty());
  EXPECT_EQ(io::pointer_join("/a", "b/c~d"), "/a/b~1c~0d");
}

TEST(Json, PythonFloatReprAndCanonicalJson)
{
  EXPECT_EQ(io::python_float_repr(1.0), "1.0");
  EXPECT_EQ(io::python_float_repr(0.1 + 0.2), "0.30000000000000004");
  EXPECT_EQ(io::python_float_repr(1e16), "1e+16");
  EXPECT_EQ(io::python_float_repr(1e15), "1000000000000000.0");
  EXPECT_EQ(io::python_float_repr(1e-5), "1e-05");
  EXPECT_EQ(io::python_float_repr(0.0001), "0.0001");
  EXPECT_EQ(io::python_float_repr(-0.0), "-0.0");
  EXPECT_EQ(io::python_float_repr(5e-324), "5e-324");
  EXPECT_EQ(io::python_float_repr(1.7976931348623157e308), "1.7976931348623157e+308");
  EXPECT_EQ(io::canonical_json(io::parse_json(R"({"b":[1,2.0,-0.0],"a":"畴\n","c":{"z":null,"y":true}})")),
            R"({"a":"畴\n","b":[1,2.0,0.0],"c":{"y":true,"z":null}})");
  EXPECT_EQ(io::python_json_dumps(io::parse_json(R"({"a":[1,{"b":2.5}]})")), R"({"a": [1, {"b": 2.5}]})");
  EXPECT_THROW(io::parse_json("[NaN]"), io::JsonError);
  EXPECT_THROW(io::parse_json("{"), io::JsonError);
}
