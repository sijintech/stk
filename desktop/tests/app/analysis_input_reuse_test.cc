/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_input_reuse.hh"

#include <limits>
#include <stdexcept>
#include <utility>

namespace stk::app {
namespace {
using io::Json;
constexpr uint64_t max_bytes = 256 * 1024 * 1024;
constexpr uint64_t max_snapshot_bytes = uint64_t(1) << 40;

std::string identity(const unsigned int value)
{
  const auto suffix = std::to_string(value);
  return "00000000-0000-4000-8000-" + std::string(12 - suffix.size(), '0') + suffix;
}
Json frozen_file(unsigned int record = 5, uint64_t size = 7, char digest = 'c')
{
  return {{"record_id", identity(record)}, {"sha256", std::string(64, digest)}, {"size", size}};
}
Json manifest_file(unsigned int record = 5, uint64_t size = 7, char digest = 'c')
{
  auto file = frozen_file(record, size, digest);
  file["name"] = record == 5 ? "first.dat" : "场 α.dat";
  file["path"] = "/original/mutable/source.dat";
  file["location"] = "external:posix";
  return file;
}
Json run()
{
  return {{"id", identity(2)}, {"project_id", identity(1)}, {"analysis_id", identity(3)},
      {"source_revision", 8}, {"snapshot_id", identity(4)}, {"snapshot_sha256", std::string(64, 'b')},
      {"plan_sha256", std::string(64, 'a')}, {"status", "prepared"}, {"result", nullptr}, {"error", nullptr},
      {"document", {{"format", "stk.analysis-document/1"}, {"graph", {{"schema", "stk.graph/1"},
          {"nodes", Json::array({{{"id", "src"}, {"type", "fixture.source.scalar@1"}}})},
          {"outputs", {{"value", "src.value"}}}}}, {"parameters", {{"never_copy", "old value"}}},
          {"outputs", Json::array({"value"})}}},
      {"bindings", {{"data", {{"nested/first.dat", frozen_file()}, {"second.dat", frozen_file(6, 11, 'd')}}}}}};
}
Json snapshot()
{
  return {{"id", identity(4)}, {"kind", "files"}, {"sha256", std::string(64, 'b')},
      {"created_at", "2026-09-30T10:00:00+00:00"}, {"revision", 4},
      {"manifest", {{"format", 1}, {"kind", "files"}, {"project_id", identity(1)}, {"source_revision", 3},
          {"files", Json::array({manifest_file(), manifest_file(6, 11, 'd')})}}}};
}
AnalysisInputReusePlan plan() { return analysis_input_reuse_plan(run(), identity(1)); }

TEST(AnalysisInputReuse, ExtractsOnlyDetachedImmutableRunReferences)
{
  auto source = run(); const auto original = source;
  const auto selected = analysis_input_reuse_plan(source, identity(1));
  EXPECT_EQ(selected.project_id, identity(1)); EXPECT_EQ(selected.run_id, identity(2));
  EXPECT_EQ(selected.analysis_id, identity(3)); EXPECT_EQ(selected.snapshot_id, identity(4));
  EXPECT_EQ(selected.plan_sha256, std::string(64, 'a')); EXPECT_EQ(selected.snapshot_sha256, std::string(64, 'b'));
  EXPECT_EQ(selected.source_revision, 8); EXPECT_EQ(selected.bindings, source.at("bindings"));
  EXPECT_EQ(source, original);
  source["bindings"]["data"]["nested/first.dat"]["size"] = 100;
  source["snapshot_id"] = identity(9); source["document"]["parameters"].clear();
  EXPECT_EQ(selected.bindings.at("data").at("nested/first.dat").at("size"), 7);
  EXPECT_EQ(selected.snapshot_id, identity(4));
}

TEST(AnalysisInputReuse, VerifiedMenuAndEditableMappingsAreIndependentCopies)
{
  auto selected = plan(); auto metadata = snapshot(); const auto original = metadata;
  auto reused = analysis_reused_inputs(selected, metadata);
  EXPECT_EQ(reused.project_id, identity(1)); EXPECT_EQ(reused.run_id, identity(2));
  EXPECT_EQ(reused.analysis_id, identity(3)); EXPECT_EQ(reused.plan_sha256, std::string(64, 'a'));
  EXPECT_EQ(reused.snapshot_id, identity(4)); EXPECT_EQ(reused.snapshot_sha256, std::string(64, 'b'));
  EXPECT_EQ(reused.snapshot_revision, 4);
  const Json expected = {{"data", {{"nested/first.dat", identity(5)}, {"second.dat", identity(6)}}}};
  EXPECT_EQ(reused.bindings, expected); ASSERT_EQ(reused.files.size(), 2u);
  EXPECT_EQ(reused.files[0].at("record_id"), identity(5)); EXPECT_EQ(reused.files[1].at("name"), "场 α.dat");
  for (const auto &file : reused.files) {
    EXPECT_EQ(file.size(), 4u); EXPECT_TRUE(file.contains("record_id")); EXPECT_TRUE(file.contains("name"));
    EXPECT_TRUE(file.contains("sha256")); EXPECT_TRUE(file.contains("size"));
    EXPECT_FALSE(file.contains("path")); EXPECT_FALSE(file.contains("location"));
  }
  EXPECT_EQ(metadata, original);
  metadata["manifest"]["files"][0]["name"] = "changed"; selected.bindings.clear();
  EXPECT_EQ(reused.files[0].at("name"), "first.dat"); EXPECT_EQ(reused.bindings, expected);
  reused.files[1]["size"] = 0;
  EXPECT_EQ(metadata.at("manifest").at("files")[1].at("size"), 11);
}

TEST(AnalysisInputReuse, AllowsMultipleAliasesAndBindingsOfOneRecordWithoutRewritingPaths)
{
  auto source = run();
  source["bindings"] = {{"data", {{"目录/α.dat", frozen_file()}, {"second_alias.dat", frozen_file()}}},
                        {"reference", {{"first.dat", frozen_file()}}}};
  const auto reused = analysis_reused_inputs(analysis_input_reuse_plan(source, identity(1)), snapshot());
  EXPECT_EQ(reused.bindings.at("data").at("目录/α.dat"), identity(5));
  EXPECT_EQ(reused.bindings.at("data").at("second_alias.dat"), identity(5));
  EXPECT_EQ(reused.bindings.at("reference").at("first.dat"), identity(5));
  EXPECT_EQ(reused.files.size(), 2u); // Unmapped snapshot records remain available in the menu.
}

TEST(AnalysisInputReuse, RejectsInvalidOrForeignRunIdentityAndHashes)
{
  EXPECT_THROW(analysis_input_reuse_plan(run(), identity(9)), std::invalid_argument);
  EXPECT_THROW(analysis_input_reuse_plan(run(), "project"), std::invalid_argument);
  EXPECT_THROW(analysis_input_reuse_plan(nullptr, identity(1)), std::invalid_argument);
  for (const char *key : {"id", "project_id", "analysis_id", "snapshot_id", "plan_sha256", "snapshot_sha256"}) {
    auto source = run(); source.erase(key);
    EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument) << key;
    source = run(); source[key] = true;
    EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument) << key;
    source = run(); source[key] = std::string(1024 * 1024, 'a');
    EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument) << key;
  }
  auto source = run(); source["id"] = "ABCDEF12-0000-4000-8000-000000000001";
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  source = run(); source["plan_sha256"] = std::string(64, 'A');
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  source = run(); source["snapshot_sha256"] = std::string(64, 'g');
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
}

TEST(AnalysisInputReuse, RevisionsRequireNonnegativeSigned64Integers)
{
  for (const Json &invalid : {Json(-1), Json(true), Json(8.0), Json("8"), Json(), Json(std::numeric_limits<uint64_t>::max())}) {
    auto source = run(); source["source_revision"] = invalid;
    EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
    auto metadata = snapshot(); metadata["revision"] = invalid;
    EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
    metadata = snapshot(); metadata["manifest"]["source_revision"] = invalid;
    EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  }
  auto source = run(); source["source_revision"] = std::numeric_limits<int64_t>::max();
  EXPECT_EQ(analysis_input_reuse_plan(source, identity(1)).source_revision, std::numeric_limits<int64_t>::max());
  auto metadata = snapshot(); metadata["revision"] = 9;
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["manifest"]["source_revision"] = 5;
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
}

TEST(AnalysisInputReuse, BindingShapeAndMetadataMustBeBoundedBeforeCopying)
{
  for (const Json &invalid : {Json(), Json::array(), Json::object(), Json{{"data", Json::array()}},
       Json{{"data", Json::object()}}, Json{{"_private", {{"x.dat", frozen_file()}}}},
       Json{{"Data", {{"x.dat", frozen_file()}}}}, Json{{"a-b", {{"x.dat", frozen_file()}}}}}) {
    auto source = run(); source["bindings"] = invalid;
    EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  }
  for (const char *key : {"record_id", "sha256", "size"}) {
    auto source = run(); source["bindings"]["data"]["nested/first.dat"].erase(key);
    EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  }
  auto source = run(); source["bindings"]["data"]["nested/first.dat"]["extra"] = std::string(1024 * 1024, 'x');
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  source = run(); source["bindings"]["data"]["nested/first.dat"]["record_id"] = "broken";
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
}

TEST(AnalysisInputReuse, FileSizesAndAliasesConsumeTheLogical256MiBBudgetExactly)
{
  for (const Json &invalid : {Json(-1), Json(true), Json(7.0), Json(), Json(std::numeric_limits<uint64_t>::max()), Json(max_bytes + 1)}) {
    auto source = run(); source["bindings"]["data"]["nested/first.dat"]["size"] = invalid;
    EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  }
  auto source = run(); auto metadata = snapshot();
  source["bindings"] = {{"data", {{"one.dat", frozen_file(5, max_bytes / 2)}, {"two.dat", frozen_file(5, max_bytes / 2)}}}};
  metadata["manifest"]["files"][0]["size"] = max_bytes / 2;
  EXPECT_NO_THROW(analysis_reused_inputs(analysis_input_reuse_plan(source, identity(1)), metadata));
  source["bindings"]["data"]["three.dat"] = frozen_file(5, 1);
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  source["bindings"]["data"].erase("three.dat");
  source["bindings"]["data"]["zero.dat"] = frozen_file(7, 0, 'e');
  metadata["manifest"]["files"].push_back(manifest_file(7, 0, 'e'));
  EXPECT_NO_THROW(analysis_reused_inputs(analysis_input_reuse_plan(source, identity(1)), metadata));
}

TEST(AnalysisInputReuse, AtMost32GroupsAnd100MappingsAreAccepted)
{
  auto source = run(); source["bindings"] = Json::object();
  for (size_t i = 0; i < 32; ++i) { source["bindings"]["data" + std::to_string(i)] = {{"alias.dat", frozen_file()}}; }
  EXPECT_NO_THROW(analysis_input_reuse_plan(source, identity(1)));
  source["bindings"]["data32"] = {{"alias.dat", frozen_file()}};
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  source["bindings"] = {{"data", Json::object()}};
  for (size_t i = 0; i < 100; ++i) { source["bindings"]["data"]["alias" + std::to_string(i) + ".dat"] = frozen_file(); }
  const auto reused = analysis_reused_inputs(analysis_input_reuse_plan(source, identity(1)), snapshot());
  EXPECT_EQ(reused.bindings.at("data").size(), 100u);
  source["bindings"]["data"]["overflow.dat"] = frozen_file();
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
}

TEST(AnalysisInputReuse, PathsRemainExactBoundedRelativeAliases)
{
  for (const auto &path : {std::string(), std::string("/absolute.dat"), std::string("../up.dat"), std::string("./same.dat"),
       std::string("folder//x.dat"), std::string("C:\\absolute.dat"), std::string("folder/back\\slash.dat"),
       std::string("trailing."), std::string("trailing "), std::string("bad\0name", 8), std::string("bad\nname"),
       std::string("bad\x7fname"), std::string("\xff", 1), std::string(256, 'x'), std::string(1025, 'x')}) {
    auto source = run(); source["bindings"] = {{"data", {{path, frozen_file()}}}};
    EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
  }
  const auto part = std::string(204, 'a');
  const auto path = part + "/" + part + "/" + part + "/" + part + "/" + part;
  ASSERT_EQ(path.size(), 1024u);
  auto source = run(); source["bindings"] = {{"data", {{path, frozen_file()}}}};
  const auto reused = analysis_reused_inputs(analysis_input_reuse_plan(source, identity(1)), snapshot());
  EXPECT_EQ(reused.bindings.at("data").at(path), identity(5));
}

TEST(AnalysisInputReuse, SnapshotIdentityHashProjectAndFormatMustMatch)
{
  auto metadata = snapshot(); metadata["id"] = identity(8);
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["sha256"] = std::string(64, 'f');
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["manifest"]["project_id"] = identity(8);
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["kind"] = "other";
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["manifest"]["kind"] = "other";
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  for (const Json &format : {Json(true), Json(1.0), Json(0), Json(2), Json("1")}) {
    metadata = snapshot(); metadata["manifest"]["format"] = format;
    EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  }
  EXPECT_THROW(analysis_reused_inputs(plan(), nullptr), std::invalid_argument);
  metadata = snapshot(); metadata.erase("manifest");
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
}

TEST(AnalysisInputReuse, EveryMappedRecordMustHaveExactlyOneMatchingManifestEntry)
{
  auto metadata = snapshot(); metadata["manifest"]["files"].erase(0);
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["manifest"]["files"].push_back(manifest_file());
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["manifest"]["files"][0]["sha256"] = std::string(64, 'e');
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["manifest"]["files"][1]["size"] = 12;
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["manifest"]["files"][0]["record_id"] = identity(8);
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  metadata = snapshot(); metadata["manifest"]["files"][0].erase("name");
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
}

TEST(AnalysisInputReuse, UnmappedSnapshotFilesCanBeLargeAndRemainInTheMenu)
{
  auto metadata = snapshot(); metadata["manifest"]["files"].push_back(manifest_file(7, max_snapshot_bytes, 'e'));
  const auto reused = analysis_reused_inputs(plan(), metadata);
  ASSERT_EQ(reused.files.size(), 3u); EXPECT_EQ(reused.files[2].at("size"), max_snapshot_bytes);
  EXPECT_EQ(reused.files[2].at("record_id"), identity(7));
  EXPECT_EQ(reused.bindings.at("data").size(), 2u);
  metadata["manifest"]["files"][2]["size"] = max_snapshot_bytes + 1;
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  auto source = run(); source["bindings"]["data"]["huge.dat"] = frozen_file(7, max_snapshot_bytes, 'e');
  EXPECT_THROW(analysis_input_reuse_plan(source, identity(1)), std::invalid_argument);
}

TEST(AnalysisInputReuse, SnapshotMenuNamesAndFileListAreBoundedBeforeAnyResultCopy)
{
  for (const Json &name : {Json(), Json(true), Json(""), Json(std::string("\xff", 1)), Json(std::string("a\0b", 3)),
       Json(std::string(1025, 'x'))}) {
    auto metadata = snapshot(); metadata["manifest"]["files"][0]["name"] = name;
    EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  }
  auto metadata = snapshot(); metadata["manifest"]["files"][0]["name"] = std::string(1024, 'x');
  EXPECT_NO_THROW(analysis_reused_inputs(plan(), metadata));
  for (const Json &invalid : {Json(), Json::object(), Json::array()}) {
    metadata = snapshot(); metadata["manifest"]["files"] = invalid;
    EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  }
  metadata = snapshot();
  for (unsigned int i = 7; i < 105; ++i) { metadata["manifest"]["files"].push_back(manifest_file(i)); }
  ASSERT_EQ(metadata.at("manifest").at("files").size(), 100u);
  EXPECT_EQ(analysis_reused_inputs(plan(), metadata).files.size(), 100u);
  metadata["manifest"]["files"].push_back(manifest_file(105));
  EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  for (const Json &size : {Json(true), Json(7.0), Json(-1), Json(std::numeric_limits<uint64_t>::max())}) {
    metadata = snapshot(); metadata["manifest"]["files"][0]["size"] = size;
    EXPECT_THROW(analysis_reused_inputs(plan(), metadata), std::invalid_argument);
  }
}

TEST(AnalysisInputReuse, PublicPlanMutationCannotBypassSecondPhaseGuards)
{
  auto selected = plan(); selected.source_revision = -1;
  EXPECT_THROW(analysis_reused_inputs(selected, snapshot()), std::invalid_argument);
  selected = plan(); selected.project_id = "foreign";
  EXPECT_THROW(analysis_reused_inputs(selected, snapshot()), std::invalid_argument);
  selected = plan(); selected.run_id = identity(2) + "x";
  EXPECT_THROW(analysis_reused_inputs(selected, snapshot()), std::invalid_argument);
  selected = plan(); selected.plan_sha256 = std::string(64, 'A');
  EXPECT_THROW(analysis_reused_inputs(selected, snapshot()), std::invalid_argument);
  selected = plan(); selected.bindings["data"]["nested/first.dat"]["size"] = max_bytes + 1;
  EXPECT_THROW(analysis_reused_inputs(selected, snapshot()), std::invalid_argument);
  selected = plan(); selected.bindings["data"]["nested/first.dat"]["record_id"] = true;
  EXPECT_THROW(analysis_reused_inputs(selected, snapshot()), std::invalid_argument);
  selected = plan(); selected.bindings = nullptr;
  EXPECT_THROW(analysis_reused_inputs(selected, snapshot()), std::invalid_argument);
}

TEST(AnalysisInputReuse, UnconsumedDefinitionsResultsAndOriginalPathsAreNotTraversed)
{
  Json deep = 0;
  for (int i = 0; i < 10000; ++i) {
    auto next = Json::array(); next.push_back(std::move(deep)); deep = std::move(next);
  }
  auto source = run(); source["document"] = std::move(deep);
  source["result"] = std::string(5 * 1024 * 1024, 'x'); source["status"] = Json::array({1, 2, 3});
  const auto selected = analysis_input_reuse_plan(source, identity(1));
  auto metadata = snapshot();
  metadata["manifest"]["files"][0]["path"] = std::string(5 * 1024 * 1024, 'x');
  metadata["manifest"]["files"][0]["location"] = nullptr;
  metadata["created_at"] = Json::array({1});
  // Synthetic unused values test the pure copy boundary; they are not valid wire snapshots.
  const auto reused = analysis_reused_inputs(selected, metadata);
  EXPECT_EQ(reused.bindings, (Json{{"data", {{"nested/first.dat", identity(5)}, {"second.dat", identity(6)}}}}));
  ASSERT_EQ(reused.files.size(), 2u); EXPECT_EQ(reused.files[0].size(), 4u);
}

TEST(AnalysisInputReuse, ARejectedSnapshotLeavesPreviouslyReturnedPreparationUntouched)
{
  const auto selected = plan(); const auto original_bindings = selected.bindings;
  const auto reused = analysis_reused_inputs(selected, snapshot());
  const auto bindings = reused.bindings, files = reused.files;
  auto wrong = snapshot(); wrong["manifest"]["files"][1]["sha256"] = std::string(64, 'f');
  EXPECT_THROW(analysis_reused_inputs(selected, wrong), std::invalid_argument);
  EXPECT_EQ(reused.bindings, bindings); EXPECT_EQ(reused.files, files);
  EXPECT_EQ(selected.bindings, original_bindings); EXPECT_EQ(reused.snapshot_id, identity(4));
}

}  // namespace
}  // namespace stk::app
