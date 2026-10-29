/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/app_store.hh"
#include "stk/app/materials_state.hh"
#include "stk/app/editor.hh"
#include <cmath>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
Json preview(const std::string &kind, const Json &observed, const Json &candidate)
{
  return {{"kind", kind}, {"evaluation_preview", {{"samples", Json::array({{
    {"id", "synthetic-heldout"}, {"observed", observed}, {"candidate", candidate}, {"base", nullptr}, {"baseline", nullptr}}})}}}};
}
Json values(const size_t count, const double value)
{
  Json result = Json::array(); for (size_t i = 0; i < count; ++i) { result.push_back(value); } return result;
}

TEST(MaterialsState, OfflineObservationAndExplicitActionsNeverInventATrainer)
{
  AppStore store;
  auto &state = store.materials(); auto view = state.new_view(); state.sync(view);
  EXPECT_FALSE(state.supported());
  view->selected_job = "synthetic-job"; view->job = {{"id", "synthetic-job"}, {"state", "prepared"}};
  EXPECT_FALSE(state.validate(view, "/synthetic"));
  EXPECT_FALSE(state.prepare(view, {{"directory", "/synthetic"}, {"job_id", "synthetic-job"}}));
  EXPECT_FALSE(state.start(view)); EXPECT_FALSE(state.cancel(view)); EXPECT_FALSE(state.recover(view));
  EXPECT_FALSE(state.activate(view, "capacity_fade", "v1"));
  EXPECT_EQ(io::get_string(view->job, "state"), "prepared"); EXPECT_FALSE(view->busy());
}

TEST(MaterialsState, ViewsRetainSeparateDataAndSourceEpochs)
{
  AppStore store; auto &state = store.materials();
  auto first = state.new_view(), second = state.new_view(); state.sync(first); state.sync(second);
  first->card = {{"name", "first"}}; second->card = {{"name", "second"}};
  const auto second_epoch = second->draft_epoch;
  const auto first_epoch = first->draft_epoch;
  state.invalidate_draft(first);  // Parameter edits keep the data card for the same directory.
  EXPECT_GT(first->draft_epoch, first_epoch); EXPECT_EQ(io::get_string(first->card, "name"), "first");
  state.invalidate_draft(first, true);
  EXPECT_TRUE(first->card.is_null()); EXPECT_EQ(io::get_string(second->card, "name"), "second");
  EXPECT_EQ(second->draft_epoch, second_epoch);
}

TEST(MaterialsState, DetachingAnOwnerNeverCancelsItsBackendTask)
{
  AppStore store; auto &state = store.materials(); auto view = state.new_view(); state.sync(view);
  view->job = {{"id", "synthetic-job"}, {"state", "running"}, {"cancel_requested", false}};
  const auto before = view->lifetime_epoch;
  state.detach(view);
  EXPECT_GT(view->lifetime_epoch, before); EXPECT_FALSE(view->reading());
  EXPECT_EQ(io::get_string(view->job, "state"), "running"); EXPECT_FALSE(view->job.at("cancel_requested").get<bool>());
}

TEST(MaterialsState, WorkspaceRestoresOnlyLocalDraftsIncludingUncommittedNumericText)
{
  EditorRegistry registry; register_builtin_editors(registry);
  auto original = registry.create(kEditorMaterials), reopened = registry.create(kEditorMaterials);
  ASSERT_TRUE(original); ASSERT_TRUE(reopened);
  auto draft = original->save_workspace_state();
  draft["directory"] = "/synthetic local dataset"; draft["job_id"] = "synthetic-job";
  draft["hidden"] = "64,32"; draft["epochs"] = 20;
  draft["number_drafts"] = {{"materials_rate", "1e-"}};
  ASSERT_TRUE(original->load_workspace_state(draft));
  ASSERT_TRUE(reopened->load_workspace_state(original->save_workspace_state()));
  EXPECT_EQ(reopened->save_workspace_state(), draft); EXPECT_TRUE(reopened->has_unsaved_changes());
  EXPECT_FALSE(draft.contains("selected_job")); EXPECT_FALSE(draft.contains("inputs"));
}

TEST(MaterialsState, InvalidWorkspaceFieldsAreRejectedWithoutChangingTheDraft)
{
  EditorRegistry registry; register_builtin_editors(registry); auto editor = registry.create(kEditorMaterials);
  ASSERT_TRUE(editor); const auto saved = editor->save_workspace_state();
  std::vector<Json> invalid = {
    {{"version", "1"}}, {{"version", true}}, {{"epochs", 5001}}, {{"seed", -1}},
    {{"learning_rate", nullptr}}, {{"split", {0, .5, .5}}}, {{"selected_job", "synthetic-job"}},
    {{"number_drafts", {{"materials_directory", "must not be numeric"}}}},
    {{"number_drafts", {{"materials_epochs", false}}}}
  };
  for (const auto &value : invalid) {
    EXPECT_FALSE(editor->load_workspace_state(value)) << value.dump(); EXPECT_EQ(editor->save_workspace_state(), saved);
  }
}

TEST(MaterialsState, SplitBaseAndJobIdentityOnlyDraftsRemainProtectedAfterReopening)
{
  EditorRegistry registry; register_builtin_editors(registry);
  for (const auto &change : std::vector<Json>{{{"split", {.6, .2, .2}}}, {{"base_version", "v2"}}, {{"job_id", "another-job"}}}) {
    auto first = registry.create(kEditorMaterials), reopened = registry.create(kEditorMaterials);
    ASSERT_TRUE(first); ASSERT_TRUE(reopened);
    ASSERT_TRUE(first->load_workspace_state(change));
    const auto saved = first->save_workspace_state(); ASSERT_TRUE(reopened->load_workspace_state(saved));
    EXPECT_TRUE(reopened->has_unsaved_changes()) << change.dump(); EXPECT_EQ(reopened->save_workspace_state(), saved);
  }
}

TEST(MaterialsPlot, LossCurvesUseRecordedEpochsAndIndependentActualLosses)
{
  const auto plot = materials_loss_plot(Json::array({
      {{"epoch", 1}, {"train_loss", 1.5}, {"validation_loss", 2.5}},
      {{"epoch", 2}, {"train_loss", .5}, {"validation_loss", .75}}}));
  ASSERT_EQ(plot.lines.size(), 2u);
  EXPECT_EQ(plot.lines[0].role, "train_loss"); EXPECT_EQ(plot.lines[1].role, "validation_loss");
  ASSERT_EQ(plot.lines[0].segments.at(0).size(), 2u);
  EXPECT_EQ(plot.lines[0].segments[0][1].x, 2); EXPECT_EQ(plot.lines[0].segments[0][1].y, .5);
  EXPECT_EQ(plot.lines[1].segments[0][0].y, 2.5);
  EXPECT_EQ(plot.x_min, 1); EXPECT_EQ(plot.x_max, 2); EXPECT_EQ(plot.y_min, .5); EXPECT_EQ(plot.y_max, 2.5);
}

TEST(MaterialsPlot, MissingObservationsAreSeparateSegmentsWithoutEndpointExtension)
{
  auto observed = values(64, 1), candidate = values(64, .95);
  observed[0] = nullptr; observed[3] = nullptr; observed[63] = nullptr;
  const auto plot = materials_evaluation_plot(preview("capacity_fade", observed, candidate), 0);
  ASSERT_EQ(plot.lines.size(), 2u); EXPECT_EQ(plot.lines[0].role, "observed");
  const auto &segments = plot.lines[0].segments; ASSERT_EQ(segments.size(), 2u);
  EXPECT_EQ(segments[0].size(), 2u); EXPECT_GT(segments[0].front().x, 0); EXPECT_LT(segments.back().back().x, 2000);
  EXPECT_GT(segments[1].front().x, segments[0].back().x);
  EXPECT_EQ(plot.lines[1].segments[0].size(), 64u); EXPECT_EQ(plot.x_min, 0); EXPECT_EQ(plot.x_max, 2000);
}

TEST(MaterialsPlot, BothPEBranchesUseThePublishedIncreasingFieldOrderAndNeverJoin)
{
  auto observed = values(128, -5), candidate = values(128, 5);
  const auto plot = materials_evaluation_plot(preview("pe_loop", observed, candidate), 0);
  ASSERT_EQ(plot.lines.size(), 2u);
  for (const auto &line : plot.lines) {
    ASSERT_EQ(line.segments.size(), 2u);
    for (const auto &branch : line.segments) {
      ASSERT_EQ(branch.size(), 64u); EXPECT_EQ(branch.front().x, -1); EXPECT_EQ(branch.back().x, 1);
      for (size_t i = 1; i < branch.size(); ++i) { EXPECT_GT(branch[i].x, branch[i - 1].x); }
    }
  }
  EXPECT_EQ(plot.y_min, -5); EXPECT_EQ(plot.y_max, 5);
}

TEST(MaterialsPlot, CandidateBaseAndActiveBaselineUseOneHeldoutSampleAndCommonAxes)
{
  auto job = preview("capacity_fade", values(64, 1), values(64, .9));
  job["evaluation_preview"]["samples"][0]["base"] = values(64, .8);
  job["evaluation_preview"]["samples"][0]["baseline"] = values(64, .7);
  auto other = job["evaluation_preview"]["samples"][0]; other["id"] = "other-heldout";
  other["candidate"] = values(64, .4); job["evaluation_preview"]["samples"].push_back(other);
  const auto first = materials_evaluation_plot(job, 0), second = materials_evaluation_plot(job, 1);
  ASSERT_EQ(first.lines.size(), 4u); ASSERT_EQ(second.lines.size(), 4u);
  EXPECT_EQ(first.lines[1].segments[0][0].y, .9); EXPECT_EQ(second.lines[1].segments[0][0].y, .4);
  EXPECT_EQ(first.lines[2].role, "base"); EXPECT_EQ(first.lines[3].role, "baseline");
  EXPECT_EQ(first.y_min, .7); EXPECT_EQ(first.y_max, 1);
}

TEST(MaterialsPlot, MissingOrMalformedPreviewNeverCreatesASyntheticCurve)
{
  EXPECT_TRUE(materials_evaluation_plot(Json(), 0).lines.empty());
  EXPECT_TRUE(materials_evaluation_plot({{"evaluation_preview", nullptr}}, 0).lines.empty());
  auto job = preview("capacity_fade", Json::array({1, 2}), Json::array({1, 2}));
  EXPECT_TRUE(materials_evaluation_plot(job, 0).lines.empty());
  EXPECT_TRUE(materials_evaluation_plot(job, 1).lines.empty());
  EXPECT_TRUE(materials_loss_plot(Json::array()).lines.empty());
}

TEST(MaterialsPlot, LargeFiniteLossesRetainDoublePrecisionAndNonzeroAxes)
{
  const auto plot = materials_loss_plot(Json::array({{{"epoch", 1}, {"train_loss", 1e300}, {"validation_loss", 1e300}}}));
  ASSERT_EQ(plot.lines.size(), 2u);
  EXPECT_TRUE(std::isfinite(plot.lines[0].segments[0][0].y)); EXPECT_EQ(plot.lines[0].segments[0][0].y, 1e300);
  EXPECT_TRUE(std::isfinite(plot.y_min)); EXPECT_TRUE(std::isfinite(plot.y_max)); EXPECT_LT(plot.y_min, plot.y_max);
}

TEST(MaterialsPlot, ConstantFiniteExtremaHaveFiniteNonzeroDisplayRangesWithoutChangingData)
{
  for (const double value : {1e20, std::numeric_limits<double>::max(), -std::numeric_limits<double>::max()}) {
    const auto plot = materials_loss_plot(Json::array({{{"epoch", 1}, {"train_loss", value}, {"validation_loss", value}}}));
    ASSERT_EQ(plot.lines.size(), 2u); EXPECT_EQ(plot.lines[0].segments[0][0].y, value);
    EXPECT_TRUE(std::isfinite(plot.y_min)); EXPECT_TRUE(std::isfinite(plot.y_max)); EXPECT_LT(plot.y_min, plot.y_max);
    EXPECT_LE(plot.y_min, value); EXPECT_GE(plot.y_max, value);
  }
}
}  // namespace
}  // namespace stk::app
