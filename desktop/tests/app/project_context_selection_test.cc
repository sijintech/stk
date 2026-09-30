/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_context_selection.hh"

#include <cstdint>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;

std::string object_id(char kind, size_t index)
{
  const std::string suffix = std::to_string(index);
  return std::string(1, kind) + "0000000-0000-4000-8000-" + std::string(12 - suffix.size(), '0') + suffix;
}
std::string row_id(size_t index) { return object_id('a', index); }
std::string field_id(size_t index) { return object_id('b', index); }

ProjectTable table(size_t rows = 3, size_t fields = 3)
{
  ProjectTable result;
  result.id = "c0000000-0000-4000-8000-000000000001";
  result.name = "Parameters";
  for (size_t i = 0; i < fields; ++i) {
    result.fields.push_back({field_id(i), "Parameter " + std::to_string(i), "number", "K"});
  }
  for (size_t i = 0; i < rows; ++i) {
    result.records.push_back({row_id(i), Json::object()});
  }
  return result;
}

TEST(ProjectContextSelection, EmptyScopeCannotBeEditedOrCaptured)
{
  ProjectContextSelection selection;
  EXPECT_FALSE(selection.current("", -1));
  EXPECT_FALSE(selection.current("opening", 0));
  EXPECT_FALSE(selection.valid());
  EXPECT_TRUE(selection.handle().empty());
  EXPECT_EQ(selection.revision(), -1);
  EXPECT_TRUE(selection.table().id.empty());
  EXPECT_TRUE(selection.rows().empty());
  EXPECT_TRUE(selection.fields().empty());
  EXPECT_EQ(selection.cell_count(), 0u);
  const auto generation = selection.generation();
  EXPECT_FALSE(selection.set_row(row_id(0), true, generation));
  EXPECT_FALSE(selection.set_field(field_id(0), true, generation));
  EXPECT_FALSE(selection.all_rows(generation));
  EXPECT_FALSE(selection.all_fields(generation));
  EXPECT_FALSE(selection.clear_rows(generation));
  EXPECT_FALSE(selection.clear_fields(generation));
  EXPECT_EQ(selection.generation(), generation);
}

TEST(ProjectContextSelection, SnapshotPreservesValuesDefinitionsAndIdsWhenLiveObjectsChange)
{
  auto live = table();
  live.records[1].values = {{field_id(0), INT64_MAX}, {field_id(1), nullptr}};
  live.records[1].definitions = {{field_id(2), {{"kind", "expression"}, {"source", "1 + 2"}}}};
  live.records[1].evaluations = {{field_id(2), {{"state", "ok"}, {"value", 3}}}};
  ProjectContextSelection selection;
  selection.pin("opening", 7, live, row_id(1));
  EXPECT_EQ(selection.rows(), (std::vector<std::string>{row_id(1)}));
  EXPECT_EQ(selection.fields(), (std::vector<std::string>{field_id(0), field_id(1), field_id(2)}));
  EXPECT_TRUE(selection.valid());
  EXPECT_EQ(selection.cell_count(), 3u);
  const auto generation = selection.generation();

  live.name = "Renamed";
  live.fields[0].name = "New parameter name";
  live.records[1].values[field_id(0)] = 42;
  live.records[1].definitions = Json::object();
  live.records.erase(live.records.begin() + 1);
  live.fields.erase(live.fields.begin());

  EXPECT_FALSE(selection.current("opening", 8));
  EXPECT_FALSE(selection.current("reopened-same-project", 7));
  EXPECT_TRUE(selection.current("opening", 7));
  EXPECT_EQ(selection.generation(), generation);
  EXPECT_EQ(selection.table().name, "Parameters");
  EXPECT_EQ(selection.table().fields[0].name, "Parameter 0");
  const auto &saved = selection.table().records[1];
  EXPECT_EQ(saved.id, row_id(1));
  EXPECT_EQ(saved.values.at(field_id(0)).get<int64_t>(), INT64_MAX);
  EXPECT_TRUE(saved.values.at(field_id(1)).is_null());
  EXPECT_FALSE(saved.values.contains(field_id(2)));
  EXPECT_EQ(saved.definitions.at(field_id(2)).at("source"), "1 + 2");
  EXPECT_EQ(saved.evaluations.at(field_id(2)).at("value"), 3);
  EXPECT_TRUE(selection.row_checked(row_id(1)));
  EXPECT_TRUE(selection.field_checked(field_id(0)));
  EXPECT_TRUE(selection.valid()) << "Bounds remain valid; current() separately rejects a stale draft";
}

TEST(ProjectContextSelection, CheckedIdsStayInFrozenTableOrderRegardlessOfClickOrder)
{
  auto source = table();
  std::swap(source.records[0], source.records[2]);
  std::swap(source.fields[0], source.fields[2]);
  ProjectContextSelection selection;
  selection.pin("opening", 0, source);
  for (size_t i = 0; i < 3; ++i) {
    ASSERT_TRUE(selection.set_row(row_id(i), true, selection.generation()));
    ASSERT_TRUE(selection.set_field(field_id(i), true, selection.generation()));
  }
  EXPECT_EQ(selection.rows(), (std::vector<std::string>{row_id(2), row_id(1), row_id(0)}));
  EXPECT_EQ(selection.fields(), (std::vector<std::string>{field_id(2), field_id(1), field_id(0)}));
  ASSERT_TRUE(selection.set_row(row_id(1), false, selection.generation()));
  ASSERT_TRUE(selection.set_field(field_id(1), false, selection.generation()));
  ASSERT_TRUE(selection.set_row(row_id(1), true, selection.generation()));
  ASSERT_TRUE(selection.set_field(field_id(1), true, selection.generation()));
  EXPECT_EQ(selection.rows(), (std::vector<std::string>{row_id(2), row_id(1), row_id(0)}));
  EXPECT_EQ(selection.fields(), (std::vector<std::string>{field_id(2), field_id(1), field_id(0)}));
  EXPECT_EQ(selection.cell_count(), 9u);
  EXPECT_EQ(source.records[0].id, row_id(2));
  EXPECT_TRUE(source.records[0].values.empty());
}

TEST(ProjectContextSelection, ChangedChoicesAndExplicitResetsInvalidateRenderedCallbacks)
{
  ProjectContextSelection selection;
  const auto source = table();
  selection.pin("opening", 3, source, row_id(0));
  const auto rendered = selection.generation();
  ASSERT_TRUE(selection.set_row(row_id(1), true, rendered));
  const auto changed = selection.generation();
  EXPECT_GT(changed, rendered);
  EXPECT_FALSE(selection.set_row(row_id(2), true, rendered));
  EXPECT_FALSE(selection.set_field(field_id(0), false, rendered));
  EXPECT_FALSE(selection.all_rows(rendered));
  EXPECT_FALSE(selection.all_fields(rendered));
  EXPECT_FALSE(selection.clear_rows(rendered));
  EXPECT_FALSE(selection.clear_fields(rendered));
  EXPECT_EQ(selection.generation(), changed);
  EXPECT_EQ(selection.rows(), (std::vector<std::string>{row_id(0), row_id(1)}));

  selection.pin("opening", 3, source);
  EXPECT_GT(selection.generation(), changed);
  EXPECT_FALSE(selection.set_row(row_id(2), true, changed));
  EXPECT_TRUE(selection.rows().empty());
  const auto repinned = selection.generation();
  selection.reset();
  EXPECT_GT(selection.generation(), repinned);
  EXPECT_FALSE(selection.set_row(row_id(2), true, repinned));
  EXPECT_FALSE(selection.current("opening", 3));
  selection.pin("opening", 3, source);
  EXPECT_FALSE(selection.all_rows(repinned));
}

TEST(ProjectContextSelection, NoOpChecksDoNotInvalidateCallbacksAndUnknownIdsNeverEnterScope)
{
  ProjectContextSelection selection;
  selection.pin("opening", 0, table(), row_id(0));
  const auto generation = selection.generation();
  EXPECT_TRUE(selection.set_row(row_id(0), true, generation));
  EXPECT_TRUE(selection.set_row(row_id(1), false, generation));
  EXPECT_TRUE(selection.set_field(field_id(0), true, generation));
  EXPECT_TRUE(selection.all_fields(generation));
  EXPECT_FALSE(selection.set_row(row_id(99), true, generation));
  EXPECT_FALSE(selection.set_row(row_id(99), false, generation));
  EXPECT_FALSE(selection.set_field(field_id(99), true, generation));
  EXPECT_FALSE(selection.set_field(field_id(99), false, generation));
  EXPECT_EQ(selection.generation(), generation);
  EXPECT_EQ(selection.rows().size(), 1u);
  EXPECT_EQ(selection.fields().size(), 3u);
}

TEST(ProjectContextSelection, LimitsRejectAllWithoutSilentlyTruncatingOrReplacingCheckedIds)
{
  ProjectContextSelection selection;
  selection.pin("opening", 0, table(101, 65));
  ASSERT_TRUE(selection.set_row(row_id(100), true, selection.generation()));
  ASSERT_TRUE(selection.set_field(field_id(64), true, selection.generation()));
  const auto before_all = selection.generation();
  EXPECT_FALSE(selection.all_rows(before_all));
  EXPECT_FALSE(selection.all_fields(before_all));
  EXPECT_EQ(selection.generation(), before_all);
  EXPECT_EQ(selection.rows(), (std::vector<std::string>{row_id(100)}));
  EXPECT_EQ(selection.fields(), (std::vector<std::string>{field_id(64)}));
  for (size_t i = 0; i < 99; ++i) {
    ASSERT_TRUE(selection.set_row(row_id(i), true, selection.generation()));
  }
  for (size_t i = 0; i < 63; ++i) {
    ASSERT_TRUE(selection.set_field(field_id(i), true, selection.generation()));
  }
  const auto full = selection.generation();
  EXPECT_FALSE(selection.set_row(row_id(99), true, full));
  EXPECT_FALSE(selection.set_field(field_id(63), true, full));
  EXPECT_EQ(selection.generation(), full);
  EXPECT_EQ(selection.rows().size(), 100u);
  EXPECT_EQ(selection.fields().size(), 64u);
  EXPECT_TRUE(selection.row_checked(row_id(100)));
  EXPECT_TRUE(selection.field_checked(field_id(64)));
  EXPECT_FALSE(selection.valid());
  ASSERT_TRUE(selection.set_row(row_id(0), false, selection.generation()));
  ASSERT_TRUE(selection.set_row(row_id(99), true, selection.generation()));
  ASSERT_TRUE(selection.set_field(field_id(0), false, selection.generation()));
  ASSERT_TRUE(selection.set_field(field_id(63), true, selection.generation()));
}

TEST(ProjectContextSelection, CellLimitKeepsExplicitSelectionForDeselectingBeforeCapture)
{
  ProjectContextSelection selection;
  selection.pin("opening", 0, table(100, 11));
  ASSERT_TRUE(selection.all_rows(selection.generation()));
  ASSERT_TRUE(selection.all_fields(selection.generation()));
  EXPECT_EQ(selection.cell_count(), 1100u);
  EXPECT_FALSE(selection.valid());
  EXPECT_EQ(selection.rows().size(), 100u);
  EXPECT_EQ(selection.fields().size(), 11u);
  ASSERT_TRUE(selection.set_field(field_id(10), false, selection.generation()));
  EXPECT_EQ(selection.cell_count(), 1000u);
  EXPECT_TRUE(selection.valid());
  ASSERT_TRUE(selection.clear_rows(selection.generation()));
  EXPECT_EQ(selection.cell_count(), 0u);
  EXPECT_FALSE(selection.valid());
  ASSERT_TRUE(selection.all_rows(selection.generation()));
  ASSERT_TRUE(selection.clear_fields(selection.generation()));
  EXPECT_EQ(selection.cell_count(), 0u);
  EXPECT_FALSE(selection.valid());
}

TEST(ProjectContextSelection, SeedRequiresExistingRecordAndAnEntireBoundedFieldSet)
{
  ProjectContextSelection selection;
  selection.pin("opening", 0, table(101, 64), row_id(100));
  EXPECT_EQ(selection.rows(), (std::vector<std::string>{row_id(100)}));
  EXPECT_EQ(selection.fields().size(), 64u);
  EXPECT_TRUE(selection.valid());
  selection.pin("opening", 0, table(101, 65), row_id(100));
  EXPECT_TRUE(selection.rows().empty());
  EXPECT_TRUE(selection.fields().empty());
  EXPECT_FALSE(selection.valid());
  selection.pin("opening", 0, table(), row_id(99));
  EXPECT_TRUE(selection.rows().empty());
  EXPECT_TRUE(selection.fields().empty());
  selection.pin("opening", 0, table(1, 0), row_id(0));
  EXPECT_TRUE(selection.rows().empty());
  EXPECT_TRUE(selection.fields().empty());
  EXPECT_TRUE(selection.all_fields(selection.generation()));
  EXPECT_FALSE(selection.valid());
  selection.pin("opening", 0, table(0, 1));
  EXPECT_TRUE(selection.all_rows(selection.generation()));
  EXPECT_TRUE(selection.all_fields(selection.generation()));
  EXPECT_FALSE(selection.valid());
}

TEST(ProjectContextSelection, ExplicitReloadReplacesFrozenDataAndStartsEmpty)
{
  auto live = table();
  ProjectContextSelection selection;
  selection.pin("opening", 4, live, row_id(1));
  const auto old_generation = selection.generation();
  live.records.erase(live.records.begin() + 1);
  live.fields.erase(live.fields.begin());
  live.name = "After deletion";
  EXPECT_FALSE(selection.current("opening", 5));
  EXPECT_TRUE(selection.row_checked(row_id(1)));
  EXPECT_TRUE(selection.field_checked(field_id(0)));
  selection.pin("opening", 5, live);
  EXPECT_TRUE(selection.current("opening", 5));
  EXPECT_TRUE(selection.rows().empty());
  EXPECT_TRUE(selection.fields().empty());
  EXPECT_EQ(selection.table().name, "After deletion");
  EXPECT_EQ(selection.table().records.size(), 2u);
  EXPECT_EQ(selection.table().fields.size(), 2u);
  EXPECT_FALSE(selection.set_row(row_id(0), true, old_generation));
  EXPECT_FALSE(selection.set_row(row_id(1), true, selection.generation()));
  EXPECT_FALSE(selection.set_field(field_id(0), true, selection.generation()));
}

TEST(ProjectContextSelection, MalformedPinIsAtomicAndDoesNotInvalidateExistingScope)
{
  ProjectContextSelection selection;
  const auto original = table();
  selection.pin("opening", 7, original, row_id(0));
  const auto generation = selection.generation();
  EXPECT_THROW(selection.pin("", 7, original), std::invalid_argument);
  EXPECT_THROW(selection.pin("other", -1, original), std::invalid_argument);
  auto malformed = original;
  malformed.id.clear();
  EXPECT_THROW(selection.pin("other", 8, malformed), std::invalid_argument);
  malformed = original;
  malformed.records[1].id = malformed.records[0].id;
  EXPECT_THROW(selection.pin("other", 8, malformed), std::invalid_argument);
  malformed = original;
  malformed.fields[1].id = malformed.fields[0].id;
  EXPECT_THROW(selection.pin("other", 8, malformed), std::invalid_argument);
  malformed = original;
  malformed.records[0].id.clear();
  EXPECT_THROW(selection.pin("other", 8, malformed), std::invalid_argument);
  malformed = original;
  malformed.fields[0].id.clear();
  EXPECT_THROW(selection.pin("other", 8, malformed), std::invalid_argument);
  EXPECT_EQ(selection.generation(), generation);
  EXPECT_TRUE(selection.current("opening", 7));
  EXPECT_EQ(selection.table().id, original.id);
  EXPECT_EQ(selection.rows(), (std::vector<std::string>{row_id(0)}));
  EXPECT_EQ(selection.fields().size(), 3u);
  EXPECT_TRUE(selection.valid());
}
}  // namespace
}  // namespace stk::app
