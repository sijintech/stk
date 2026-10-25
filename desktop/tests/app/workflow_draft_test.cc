/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/workflow_draft.hh"

#include <cmath>
#include <stdexcept>
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

TEST(WorkflowDraft, ReusableInterfaceKeepsExactValuesAndLocalUndo)
{
  auto draft = pinned();
  const auto generation = draft.generation();
  const Json boundary = {{"inputs", {{"data", {{"type", "files"}}}}},
      {"outputs", {{"result", {{"type", "result"}, {"from", "view.view"}}}}},
      {"parameters", Json::array({{{"name", "count"}, {"type", "integer"}, {"default", int64_t(9007199254740993LL)}}})}};
  ASSERT_TRUE(draft.set_interface(boundary, generation).accepted);
  EXPECT_EQ(draft.document().at("format"), "stk.workflow/2");
  EXPECT_EQ(exact(draft.document().at("interface")), exact(boundary));
  ASSERT_TRUE(draft.set_link("view", "data", std::string("$input.data"), generation).accepted);
  EXPECT_EQ(draft.step("view")->at("inputs").at("data").at("from"), "$input.data");
  EXPECT_FALSE(draft.set_link("view", "data", std::string("$input.absent"), generation).accepted);
  ASSERT_TRUE(draft.undo(generation).accepted);
  ASSERT_TRUE(draft.undo(generation).accepted);
  EXPECT_EQ(exact(draft.document()), exact(saved()));
  ASSERT_TRUE(draft.redo(generation).accepted);
  EXPECT_EQ(exact(draft.document().at("interface")), exact(boundary));
  auto invalid = boundary;
  invalid["parameters"][0]["default"] = true;
  const auto before = exact(draft.document());
  EXPECT_FALSE(draft.set_interface(invalid, generation).accepted);
  EXPECT_EQ(exact(draft.document()), before);
  invalid = boundary;
  invalid["parameters"].push_back(invalid["parameters"][0]);
  EXPECT_FALSE(draft.set_interface(invalid, generation).accepted);
}

TEST(WorkflowDraft, AddingSubworkflowUpgradesInOneReversibleEdit)
{
  auto draft = pinned();
  const auto generation = draft.generation();
  const auto added = draft.add_step("workflow", "workflow", id, std::nullopt, generation);
  ASSERT_TRUE(added.accepted) << added.error;
  EXPECT_EQ(draft.document().at("format"), "stk.workflow/2");
  EXPECT_TRUE(draft.document().at("interface").at("inputs").empty());
  ASSERT_TRUE(draft.undo(generation).accepted);
  EXPECT_EQ(exact(draft.document()), exact(saved()));
  ASSERT_TRUE(draft.redo(generation).accepted);
  EXPECT_EQ(draft.step(added.id)->at("ref").at("workflow"), id);
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

TEST(WorkflowDraft, WorkspaceKeepsUnsavedNameStepsAndPositionsWithANewOpening)
{
  auto model = pinned();
  ASSERT_TRUE(model.set_name("Unsaved name", model.generation()).accepted);
  ASSERT_TRUE(model.set_parameter("view", "path", Json("new.vtk"), model.generation()).accepted);
  ASSERT_TRUE(model.move_steps({{"view", {800, 120}}}, model.generation()).accepted);
  const auto state = model.save_workspace_state(); EXPECT_FALSE(state.contains("handle"));
  auto restored = pinned(); const auto generation = restored.generation();
  ASSERT_TRUE(restored.load_workspace_state(state, "new-opening"));
  EXPECT_GT(restored.generation(), generation); EXPECT_EQ(restored.handle(), "new-opening");
  EXPECT_TRUE(restored.dirty()); EXPECT_EQ(restored.name(), "Unsaved name");
  EXPECT_EQ(exact(restored.baseline()), exact(model.baseline())); EXPECT_EQ(exact(restored.document()), exact(model.document()));
  EXPECT_FALSE(restored.set_name("stale callback", generation).accepted);
}

TEST(WorkflowDraft, InvalidWorkspaceDocumentAndImportedHandleAreAtomicRefusals)
{
  auto model = pinned(); ASSERT_TRUE(model.set_name("Unsaved", model.generation()).accepted);
  const auto before = model.save_workspace_state(); const auto generation = model.generation();
  auto invalid = before; invalid["document"]["steps"] = "invalid";
  EXPECT_FALSE(model.load_workspace_state(invalid, "new-opening"));
  EXPECT_EQ(model.save_workspace_state(), before); EXPECT_EQ(model.generation(), generation);
  invalid = before; invalid["handle"] = "imported-opening";
  EXPECT_FALSE(model.load_workspace_state(invalid, "new-opening")); EXPECT_EQ(model.save_workspace_state(), before);
}

TEST(WorkflowDraft, WorkspaceRelocatesCandidateButKeepsExactOriginalBaselineForRebase)
{
  auto original = saved(); original["steps"][2]["parameters"]["path"] = "/old-machine/project/input.dat";
  WorkflowDraft model; model.pin("old-opening", id, 4, "Temperature scan", original);
  auto state = model.save_workspace_state();
  state["baseline"]["steps"][2]["parameters"]["path"] = "/new-machine/project/input.dat";
  state["document"]["steps"][2]["parameters"]["path"] = "/new-machine/project/input.dat";
  auto restored = pinned(); ASSERT_TRUE(restored.load_workspace_state(state, "new-opening"));
  EXPECT_EQ(exact(restored.baseline()), exact(original));
  EXPECT_EQ(restored.document().at("steps")[2].at("parameters").at("path"), "/new-machine/project/input.dat");
  EXPECT_TRUE(restored.dirty()); EXPECT_TRUE(restored.current("new-opening", 4));
  EXPECT_FALSE(restored.current("old-opening", 4)); EXPECT_FALSE(restored.current("new-opening", 5));
  ASSERT_TRUE(restored.rebase(5, "Temperature scan", original));
  auto changed = original; changed["steps"][0]["label"] = "Another saved document";
  EXPECT_FALSE(restored.rebase(6, "Temperature scan", changed));
  auto legacy = model.save_workspace_state(); legacy.erase("baseline_json");
  ASSERT_TRUE(restored.load_workspace_state(legacy, "legacy-opening"));
  EXPECT_EQ(exact(restored.baseline()), exact(original));
}

TEST(WorkflowDraft, InvalidOpaqueBaselineIsRejectedAtomically)
{
  auto model = pinned(); const auto before = model.save_workspace_state(); const auto generation = model.generation();
  for (const Json bad : {Json(nullptr), Json("{} {}"), Json("{\"a\":1,\"a\":2}"),
                        Json(std::string(100, '[') + std::string(100, ']')),
                        Json(std::string(WorkflowDocumentLimits::max_document_bytes + 1, ' '))}) {
    auto state = before; state["baseline_json"] = bad;
    EXPECT_FALSE(model.load_workspace_state(state, "other-opening"));
    EXPECT_EQ(model.save_workspace_state(), before); EXPECT_EQ(model.generation(), generation);
  }
}

TEST(WorkflowDraft, HistoryRestoresNamesTypedParametersDependenciesAndCascadingDeletion)
{
  auto model = pinned(); const auto generation = model.generation();
  std::vector<std::pair<std::string, std::string>> states{{model.name(), exact(model.document())}};
  ASSERT_TRUE(model.set_parameter("view", "gain", Json::array({1, 1.0, -0.0, nullptr, false}), generation).accepted);
  states.push_back({model.name(), exact(model.document())});
  ASSERT_TRUE(model.set_after("view", {"fields"}, generation).accepted); states.push_back({model.name(), exact(model.document())});
  ASSERT_TRUE(model.set_name("Customer workflow", generation).accepted); states.push_back({model.name(), exact(model.document())});
  ASSERT_TRUE(model.remove_step("fields", generation).accepted); states.push_back({model.name(), exact(model.document())});
  auto version = model.version(), check = model.check_version();
  for (size_t i = states.size() - 1; i > 0; --i) {
    ASSERT_TRUE(model.undo(generation).accepted);
    EXPECT_EQ(model.name(), states[i - 1].first); EXPECT_EQ(exact(model.document()), states[i - 1].second);
    EXPECT_EQ(model.version(), ++version);
    if (i != 3) { ++check; }  // the rename never affects validation
    EXPECT_EQ(model.check_version(), check); EXPECT_EQ(model.generation(), generation);
  }
  EXPECT_FALSE(model.dirty()); EXPECT_FALSE(model.can_undo()); EXPECT_TRUE(model.can_redo());
  for (size_t i = 1; i < states.size(); ++i) {
    ASSERT_TRUE(model.redo(generation).accepted);
    EXPECT_EQ(model.name(), states[i].first); EXPECT_EQ(exact(model.document()), states[i].second);
    EXPECT_EQ(model.version(), ++version);
    if (i != 3) { ++check; }
    EXPECT_EQ(model.check_version(), check);
  }
  EXPECT_FALSE(model.redo(generation).accepted);
}

TEST(WorkflowDraft, HistoryNoOpsRefusalsBranchesAndLayoutKeepTheCheckContract)
{
  auto model = pinned(); const auto generation = model.generation(), check = model.check_version();
  ASSERT_TRUE(model.move_steps({{"view", {600, 40}}}, generation).accepted);
  const auto moved = exact(model.document());
  ASSERT_TRUE(model.undo(generation).accepted); ASSERT_TRUE(model.redo(generation).accepted);
  EXPECT_EQ(model.check_version(), check); EXPECT_EQ(exact(model.document()), moved);
  ASSERT_TRUE(model.set_name("Other", generation).accepted); ASSERT_TRUE(model.undo(generation).accepted);
  const auto bytes = model.history_bytes();
  const auto version = model.version();
  ASSERT_TRUE(model.move_steps({{"view", {600, 40}}}, generation).accepted);
  ASSERT_TRUE(model.set_name("Temperature scan", generation).accepted);
  EXPECT_FALSE(model.set_name(" ", generation).accepted);
  EXPECT_FALSE(model.remove_step("missing", generation).accepted);
  EXPECT_FALSE(model.move_steps({{"view", {std::nan(""), 1}}}, generation).accepted);
  EXPECT_FALSE(model.undo(generation + 1).accepted); EXPECT_FALSE(model.redo(generation + 1).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(model.history_bytes(), bytes);
  EXPECT_EQ(model.undo_depth(), 1u); EXPECT_EQ(model.redo_depth(), 1u);
  ASSERT_TRUE(model.set_label("view", std::string("Selected"), generation).accepted);
  EXPECT_FALSE(model.can_redo()); EXPECT_EQ(model.undo_depth(), 2u);
  ASSERT_TRUE(model.undo(generation).accepted); EXPECT_EQ(exact(model.document()), moved);
  EXPECT_EQ(model.check_version(), check + 2);
}

TEST(WorkflowDraft, HistoryIsBoundedByBothActionCountAndSnapshotCapacity)
{
  auto small = pinned();
  for (size_t i = 0; i < WorkflowDraft::max_history_steps + 12; ++i) {
    ASSERT_TRUE(small.set_name("Workflow " + std::to_string(i), small.generation()).accepted);
    EXPECT_LE(small.history_bytes(), WorkflowDraft::max_history_bytes);
  }
  EXPECT_EQ(small.undo_depth(), WorkflowDraft::max_history_steps);
  while (small.can_undo()) { ASSERT_TRUE(small.undo(small.generation()).accepted); }
  EXPECT_EQ(small.name(), "Workflow 11");
  auto document = saved(); document["ui"]["x-padding"] = std::string(128 * 1024, 'p');
  WorkflowDraft large; large.pin("opening", id, 4, "Large", document);
  for (size_t i = 0; i < 40; ++i) {
    ASSERT_TRUE(large.set_name("Large " + std::to_string(i), large.generation()).accepted);
    EXPECT_LE(large.history_bytes(), WorkflowDraft::max_history_bytes);
  }
  EXPECT_GT(large.undo_depth(), 0u); EXPECT_LT(large.undo_depth(), 40u);
  const auto bytes = large.history_bytes();
  while (large.can_undo()) { ASSERT_TRUE(large.undo(large.generation()).accepted); }
  while (large.can_redo()) { ASSERT_TRUE(large.redo(large.generation()).accepted); }
  EXPECT_EQ(large.history_bytes(), bytes); EXPECT_EQ(large.name(), "Large 39");
}

TEST(WorkflowDraft, HistoryKeepsAnUnchangedRebaseButNotAReplacementOrWorkspaceSession)
{
  auto model = pinned(); ASSERT_TRUE(model.set_name("Draft", model.generation()).accepted);
  const auto generation = model.generation();
  const auto bytes = model.history_bytes();
  EXPECT_FALSE(model.rebase(5, "Another", saved()));
  ASSERT_TRUE(model.rebase(5, "Temperature scan", saved()));
  EXPECT_EQ(model.history_bytes(), bytes); EXPECT_TRUE(model.can_undo());
  ASSERT_TRUE(model.undo(generation).accepted); EXPECT_EQ(model.name(), "Temperature scan"); EXPECT_EQ(model.revision(), 5);
  ASSERT_TRUE(model.redo(generation).accepted); EXPECT_EQ(model.name(), "Draft");
  auto state = model.save_workspace_state(), bad = state; bad["document"]["format"] = "other";
  EXPECT_FALSE(model.load_workspace_state(bad, "new-opening"));
  EXPECT_THROW(model.pin("", id, 5, "Invalid", saved()), std::invalid_argument);
  EXPECT_EQ(model.history_bytes(), bytes); EXPECT_EQ(model.undo_depth(), 1u); EXPECT_EQ(model.generation(), generation);
  ASSERT_TRUE(model.load_workspace_state(state, "new-opening"));
  EXPECT_TRUE(model.dirty()); EXPECT_EQ(model.history_bytes(), 0u); EXPECT_FALSE(model.can_undo()); EXPECT_FALSE(model.can_redo());
  EXPECT_GT(model.generation(), generation); EXPECT_FALSE(model.undo(generation).accepted);
  ASSERT_TRUE(model.set_name("Next", model.generation()).accepted);
  ASSERT_TRUE(model.revert(model.generation())); EXPECT_EQ(model.history_bytes(), 0u);
  ASSERT_TRUE(model.set_name("Next", model.generation()).accepted);
  model.pin("opening", id, 6, "Repinned", saved()); EXPECT_EQ(model.history_bytes(), 0u);
  ASSERT_TRUE(model.set_name("Next", model.generation()).accepted); model.reset();
  EXPECT_EQ(model.history_bytes(), 0u); EXPECT_FALSE(model.can_undo()); EXPECT_FALSE(model.can_redo());
}

TEST(WorkflowDraft, GroupedLayoutAndStepChangesCommitOneActionAndRollbackEveryFailure)
{
  auto model = pinned(); const auto generation = model.generation(), version = model.version(), check = model.check_version();
  const auto original = exact(model.document());
  auto result = model.edit_group(generation, [](WorkflowDraft &candidate) {
    auto moved = candidate.move_steps({{"fields", {260, 0}}}, candidate.generation());
    if (!moved.accepted) { return moved; }
    return candidate.add_step("analysis", "analysis", "44444444-4444-4444-8444-444444444444", std::pair{800.0, 0.0}, candidate.generation());
  });
  ASSERT_TRUE(result.accepted) << result.error; EXPECT_EQ(result.id, "analysis");
  EXPECT_EQ(model.undo_depth(), 1u); EXPECT_EQ(model.version(), version + 1); EXPECT_EQ(model.check_version(), check + 1);
  const auto changed = exact(model.document());
  ASSERT_TRUE(model.undo(generation).accepted); EXPECT_EQ(exact(model.document()), original);
  ASSERT_TRUE(model.redo(generation).accepted); EXPECT_EQ(exact(model.document()), changed);
  const auto before = model.version();
  const auto bytes = model.history_bytes();
  EXPECT_FALSE(model.edit_group(generation, [](WorkflowDraft &candidate) {
    candidate.move_steps({{"fields", {800, 0}}}, candidate.generation());
    return candidate.remove_step("absent", candidate.generation());
  }).accepted);
  EXPECT_FALSE(model.edit_group(generation, [](WorkflowDraft &candidate) -> WorkflowDraft::EditResult {
    candidate.set_name("Temporary", candidate.generation()); throw std::runtime_error("Rejected grouped edit");
  }).accepted);
  EXPECT_FALSE(model.edit_group(generation, [](WorkflowDraft &candidate) -> WorkflowDraft::EditResult {
    candidate.reset(); return {true, {}};
  }).accepted);
  EXPECT_FALSE(model.edit_group(generation, [](WorkflowDraft &candidate) -> WorkflowDraft::EditResult {
    candidate.rebase(5, "Temperature scan", saved()); return {true, {}};
  }).accepted);
  EXPECT_EQ(exact(model.document()), changed); EXPECT_EQ(model.name(), "Temperature scan");
  EXPECT_EQ(model.version(), before); EXPECT_EQ(model.history_bytes(), bytes); EXPECT_EQ(model.undo_depth(), 1u);
  bool called = false;
  EXPECT_FALSE(model.edit_group(generation + 1, [&called](WorkflowDraft &) -> WorkflowDraft::EditResult { called = true; return {true, {}}; }).accepted);
  EXPECT_FALSE(called);
}

TEST(WorkflowDraft, GroupedFinalNoOpKeepsRedoAndLayoutOrNameChangesKeepChecks)
{
  auto model = pinned(); const auto generation = model.generation();
  ASSERT_TRUE(model.set_name("Changed", generation).accepted); ASSERT_TRUE(model.undo(generation).accepted);
  const auto version = model.version(), check = model.check_version();
  const auto bytes = model.history_bytes();
  ASSERT_TRUE(model.edit_group(generation, [](WorkflowDraft &candidate) {
    auto changed = candidate.set_parameter("view", "gain", 5, candidate.generation());
    if (!changed.accepted) { return changed; }
    return candidate.set_parameter("view", "gain", std::nullopt, candidate.generation());
  }).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(model.history_bytes(), bytes); EXPECT_TRUE(model.can_redo());
  ASSERT_TRUE(model.edit_group(generation, [](WorkflowDraft &candidate) {
    auto changed = candidate.set_parameter("view", "gain", 5, candidate.generation());
    if (!changed.accepted) { return changed; }
    changed = candidate.set_parameter("view", "gain", std::nullopt, candidate.generation());
    if (!changed.accepted) { return changed; }
    changed = candidate.move_steps({{"fields", {300, 20}}}, candidate.generation());
    if (!changed.accepted) { return changed; }
    return candidate.set_name("Customer layout", candidate.generation());
  }).accepted);
  EXPECT_EQ(model.version(), version + 1); EXPECT_EQ(model.check_version(), check);
  EXPECT_EQ(model.undo_depth(), 1u); EXPECT_FALSE(model.can_redo());
  ASSERT_TRUE(model.undo(generation).accepted); EXPECT_EQ(model.check_version(), check);
  ASSERT_TRUE(model.redo(generation).accepted); EXPECT_EQ(model.check_version(), check);
  ASSERT_TRUE(model.revert(generation)); EXPECT_EQ(model.check_version(), check);
}

TEST(WorkflowDraft, GroupedFailedAdditionAtCapacityDoesNotLeaveLayoutOrDropRenameHistory)
{
  auto document = saved(); document["steps"] = Json::array(); document["ui"] = Json::object();
  for (size_t i = 0; i < WorkflowDocumentLimits::max_steps; ++i) {
    document["steps"].push_back({{"id", "s" + std::to_string(i)}, {"kind", "table"}, {"ref", {{"table", "t"}}}});
  }
  WorkflowDraft model; model.pin("opening", id, 4, "At capacity", document);
  const auto generation = model.generation();
  ASSERT_TRUE(model.set_name("Renamed", generation).accepted);
  const auto version = model.version(), check = model.check_version();
  const auto bytes = model.history_bytes();
  const auto result = model.edit_group(generation, [](WorkflowDraft &temporary) {
    auto moved = temporary.move_steps({{"s0", {100, 40}}}, temporary.generation());
    if (!moved.accepted) { return moved; }
    return temporary.add_step("table", "table", "other", std::nullopt, temporary.generation());
  });
  EXPECT_FALSE(result.accepted); EXPECT_FALSE(result.error.empty());
  EXPECT_EQ(exact(model.document()), exact(document)); EXPECT_EQ(model.name(), "Renamed");
  EXPECT_EQ(model.version(), version); EXPECT_EQ(model.check_version(), check); EXPECT_EQ(model.history_bytes(), bytes);
  EXPECT_EQ(model.undo_depth(), 1u); ASSERT_TRUE(model.undo(generation).accepted); EXPECT_EQ(model.name(), "At capacity");
}

}  // namespace
}  // namespace stk::app
