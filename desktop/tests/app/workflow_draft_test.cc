/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/workflow_draft.hh"

#include <string>

namespace stk::app {
namespace {
using io::Json;
constexpr const char *id = "8d2a7e50-4f3c-4e1a-9b9d-5cae7f6e4d32";

std::string exact(const Json &value) { return io::python_json_dumps(value, true, true); }

Json saved()
{
  return {{"format", "stk.workflow/1"}, {"steps", {
      {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", "11111111-1111-4111-8111-111111111111"}}}, {"x-note", {1, 2.5, nullptr}}},
      {{"id", "fields"}, {"kind", "files"}, {"ref", {{"snapshot", "22222222-2222-4222-8222-222222222222"}}}, {"after", {"cases"}}},
      {{"id", "view"}, {"kind", "analysis"}, {"ref", {{"analysis", "33333333-3333-4333-8333-333333333333"}}},
       {"inputs", {{"data", {{"from", "fields.files"}}}}}, {"parameters", {{"path", "field.vtk"}}}}}},
      {"ui", {{"positions", {{"cases", {0, 0}}}}, {"zoom", 1.25}}}};
}

WorkflowDraft pinned()
{
  WorkflowDraft draft;
  draft.pin("handle", id, 4, "Temperature scan", saved());
  return draft;
}

TEST(WorkflowDraft, StartsAsTheSavedDocumentAndDropsEditsThatReturnToIt)
{
  auto draft = pinned();
  EXPECT_FALSE(draft.dirty()); EXPECT_EQ(exact(draft.document()), exact(saved()));
  const auto generation = draft.generation(), version = draft.version();
  ASSERT_TRUE(draft.set_label("view", std::string("Field view"), generation).accepted);
  EXPECT_TRUE(draft.dirty()); EXPECT_GT(draft.version(), version);
  EXPECT_EQ(draft.edited_steps(), std::set<std::string>{"view"});
  ASSERT_TRUE(draft.set_label("view", std::nullopt, generation).accepted);
  EXPECT_FALSE(draft.dirty());  // back to the saved document byte for byte
  EXPECT_EQ(exact(draft.document()), exact(saved()));
  ASSERT_TRUE(draft.set_name("Renamed", generation).accepted);
  EXPECT_TRUE(draft.dirty()); EXPECT_EQ(draft.name(), "Renamed"); EXPECT_EQ(exact(draft.document()), exact(saved()));
  EXPECT_FALSE(draft.set_name("  ", generation).accepted);
  ASSERT_TRUE(draft.set_name("Temperature scan", generation).accepted);
  EXPECT_FALSE(draft.dirty());
  EXPECT_TRUE(draft.matches(id, "Temperature scan", saved()));
}

TEST(WorkflowDraft, AddedStepsGetFreeIdsAndRemovalCascades)
{
  auto draft = pinned();
  const auto generation = draft.generation();
  auto added = draft.add_step("analysis", "analysis", "44444444-4444-4444-8444-444444444444", std::pair{520.4, -10.6}, generation);
  ASSERT_TRUE(added.accepted) << added.error; EXPECT_EQ(added.id, "analysis");
  added = draft.add_step("analysis", "analysis", "55555555-5555-4555-8555-555555555555", std::nullopt, generation);
  ASSERT_TRUE(added.accepted); EXPECT_EQ(added.id, "analysis_2");
  EXPECT_EQ(draft.document().at("ui").at("positions").at("analysis"), Json::array({520, -11}));
  ASSERT_TRUE(draft.set_link("analysis", "data", std::string("fields.files"), generation).accepted);
  ASSERT_TRUE(draft.set_after("analysis_2", {"fields", "view"}, generation).accepted);
  ASSERT_TRUE(draft.move_steps({{"fields", {260, 0}}}, generation).accepted);
  // Removing "fields" drops links from it, after entries naming it and its position; others stay.
  ASSERT_TRUE(draft.remove_step("fields", generation).accepted);
  const auto &document = draft.document();
  for (const auto &step : document.at("steps")) { EXPECT_NE(step.at("id"), "fields"); }
  EXPECT_EQ(draft.step("view")->at("inputs"), Json::object());  // emptied, kept: the saved view had inputs
  EXPECT_FALSE(draft.step("analysis")->contains("inputs"));     // emptied, dropped: a new step
  EXPECT_EQ(draft.step("analysis_2")->at("after"), Json::array({"view"}));
  EXPECT_FALSE(document.at("ui").at("positions").contains("fields"));
  EXPECT_EQ(draft.step("cases")->at("x-note"), saved().at("steps")[0].at("x-note"));  // untouched keys keep their JSON
  EXPECT_EQ(document.at("ui").at("zoom"), 1.25);
  EXPECT_FALSE(draft.remove_step("fields", generation).accepted);
}

TEST(WorkflowDraft, EmptiedKeysTheSavedStepHadStayAndOthersGo)
{
  auto draft = pinned();
  const auto generation = draft.generation();
  ASSERT_TRUE(draft.set_link("view", "data", std::nullopt, generation).accepted);
  EXPECT_EQ(draft.step("view")->at("inputs"), Json::object());  // the saved step had inputs
  ASSERT_TRUE(draft.set_after("fields", {}, generation).accepted);
  EXPECT_EQ(draft.step("fields")->at("after"), Json::array());
  ASSERT_TRUE(draft.set_parameter("cases", "x", Json(1), generation).accepted);
  ASSERT_TRUE(draft.set_parameter("cases", "x", std::nullopt, generation).accepted);
  EXPECT_FALSE(draft.step("cases")->contains("parameters"));  // it had none
  ASSERT_TRUE(draft.set_parameter("view", "colormap", Json{{"$field", "66666666-6666-4666-8666-666666666666"}}, generation).accepted);
  EXPECT_EQ(draft.step("view")->at("parameters").at("colormap").at("$field"), "66666666-6666-4666-8666-666666666666");
  EXPECT_TRUE(draft.revert(generation)); EXPECT_FALSE(draft.dirty());
  EXPECT_EQ(exact(draft.document()), exact(saved()));
}

TEST(WorkflowDraft, RefusesWhatStorageWouldRejectAndKeepsState)
{
  auto draft = pinned();
  const auto generation = draft.generation();
  const auto before = exact(draft.document());
  EXPECT_FALSE(draft.add_step("Analysis", "analysis", "x", std::nullopt, generation).accepted);
  EXPECT_FALSE(draft.add_step("analysis", "analysis", std::string(129, 'a'), std::nullopt, generation).accepted);
  EXPECT_FALSE(draft.add_step("analysis", "analysis", "x", std::pair{2e6, 0.0}, generation).accepted);
  EXPECT_FALSE(draft.set_link("view", "data", std::string("fields"), generation).accepted);
  EXPECT_FALSE(draft.set_link("view", "data", std::string("view.view"), generation).accepted);  // its own output
  EXPECT_FALSE(draft.set_link("view", "data", std::string("missing.files"), generation).accepted);
  EXPECT_FALSE(draft.set_link("view", "Data", std::string("fields.files"), generation).accepted);
  EXPECT_FALSE(draft.set_after("view", {"view"}, generation).accepted);
  EXPECT_FALSE(draft.set_after("view", {"cases", "cases"}, generation).accepted);
  EXPECT_FALSE(draft.set_parameter("view", "path", Json(std::string(64 * 1024, 'x')), generation).accepted);
  EXPECT_FALSE(draft.set_label("view", std::string(257, 'x'), generation).accepted);
  EXPECT_FALSE(draft.move_steps({{"view", {0, std::nan("")}}}, generation).accepted);
  EXPECT_EQ(exact(draft.document()), before); EXPECT_FALSE(draft.dirty());
  // A stale generation is refused; re-pinning fences it.
  draft.pin("handle", id, 5, "Temperature scan", saved());
  EXPECT_FALSE(draft.set_label("view", std::string("Late"), generation).accepted);
  // Duplicate ids are never edited.
  auto duplicated = saved();
  duplicated["steps"].push_back(duplicated["steps"][2]);
  WorkflowDraft twice; twice.pin("handle", id, 1, "Twice", duplicated);
  EXPECT_FALSE(twice.set_label("view", std::string("x"), twice.generation()).accepted);
  EXPECT_FALSE(twice.remove_step("view", twice.generation()).accepted);
  // A step limit of 200.
  auto full = saved();
  full["steps"] = Json::array();
  for (int i = 0; i < 200; ++i) { full["steps"].push_back({{"id", "s" + std::to_string(i)}, {"kind", "table"}, {"ref", {{"table", "t"}}}}); }
  WorkflowDraft many; many.pin("handle", id, 1, "Many", full);
  EXPECT_FALSE(many.add_step("table", "table", "t", std::nullopt, many.generation()).accepted);
}

TEST(WorkflowDraft, PositionsAndTheNameDoNotInvalidateACheck)
{
  auto draft = pinned();
  const auto generation = draft.generation();
  const auto check = draft.check_version();
  ASSERT_TRUE(draft.move_steps({{"view", {600.2, 40}}}, generation).accepted);
  ASSERT_TRUE(draft.set_name("Moved", generation).accepted);
  EXPECT_EQ(draft.check_version(), check); EXPECT_TRUE(draft.dirty());
  EXPECT_EQ(draft.document().at("ui").at("positions").at("view"), Json::array({600, 40}));
  ASSERT_TRUE(draft.set_link("view", "data", std::nullopt, generation).accepted);
  EXPECT_GT(draft.check_version(), check);
  // A newer read of the unchanged workflow keeps the edits; a changed one does not.
  const auto edited = io::python_json_dumps(draft.document(), true, true);
  EXPECT_FALSE(draft.rebase(5, "Other name", saved()));
  auto changed = saved(); changed["steps"].erase(0);
  EXPECT_FALSE(draft.rebase(5, "Temperature scan", changed));
  const auto before = draft.check_version();
  ASSERT_TRUE(draft.rebase(5, "Temperature scan", saved()));
  EXPECT_EQ(draft.revision(), 5); EXPECT_GT(draft.check_version(), before);
  EXPECT_EQ(io::python_json_dumps(draft.document(), true, true), edited);
  EXPECT_FALSE(draft.rebase(3, "Temperature scan", saved()));  // never backwards
  EXPECT_THROW(draft.pin("handle", "not-a-uuid", 1, "x", saved()), std::invalid_argument);
  auto bad = saved(); bad["extra"] = 1;
  EXPECT_THROW(draft.pin("handle", id, 1, "x", bad), std::invalid_argument);
  EXPECT_THROW(check_workflow_document(Json{{"format", "stk.workflow/1"}, {"steps", {{{"id", "a"}, {"kind", "t"}, {"ref", {{"t", "x"}}},
      {"inputs", {{"in", {{"from", "b.out"}, {"as", "x"}}}}}}}}, {"ui", Json::object()}}), std::invalid_argument);
}

}  // namespace
}  // namespace stk::app
