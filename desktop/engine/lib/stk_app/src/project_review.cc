/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_review.hh"
#include "stk/app/project_state.hh"

#include <map>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
using Objects = std::map<std::string, ProjectDifference>;

Objects objects(const std::vector<ProjectTable> &tables)
{
  Objects result;
  for (const auto &table : tables) {
    const std::string root = table.id + "/";
    result[root] = {"table", table.id, {}, {}, table.name, 0, {}, Json{{"name", table.name}}};
    std::map<std::string, std::string> names;
    for (const auto &field : table.fields) {
      names[field.id] = field.name;
      result[root + "f/" + field.id] = {"field", table.id, {}, field.id, table.name + " / " + field.name,
          0, {}, Json{{"name", field.name}, {"type", field.type}, {"unit", field.unit}}};
    }
    int64_t row = 0;
    for (const auto &record : table.records) {
      ++row;
      result[root + "r/" + record.id] = {"record", table.id, record.id, {}, table.name, row, {}, Json{{"id", record.id}}};
      // Visit populated cells only, including failed expressions with no effective value.
      std::map<std::string, Json> cells;
      for (const auto &[id, value] : record.values.items()) { cells[id]["value"] = value; }
      for (const auto &[id, value] : record.definitions.items()) { cells[id]["definition"] = value; }
      for (const auto &[id, value] : record.evaluations.items()) {
        auto semantic = value;
        semantic.erase("evaluated_revision"); // Recalculation alone is not a value/definition change.
        cells[id]["evaluation"] = std::move(semantic);
      }
      for (auto &[id, cell] : cells) {
        result[root + "c/" + record.id + "/" + id] = {
            "cell", table.id, record.id, id, table.name + " / " + names[id], row, {}, std::move(cell)};
      }
    }
  }
  return result;
}
}  // namespace

ProjectReview ProjectReview::from_preview(const std::string &project_id, const int64_t base_revision,
                                         const std::vector<ProjectTable> &before, const io::Json &result)
{
  const auto &snapshot = result.at("snapshot");
  if (result.at("persisted") != false || result.at("base_revision") != base_revision ||
      result.at("proposed_revision") != base_revision + 1 ||
      snapshot.at("project").at("id") != project_id ||
      snapshot.at("project").at("revision") != base_revision + 1 ||
      !result.at("commands").is_array() || result.at("commands").empty() || result.at("commands").size() > 1000) {
    throw std::invalid_argument("Preview identity or revision does not match its base");
  }
  ProjectReview review;
  review.project_id = project_id;
  review.base_revision = base_revision;
  review.proposed_revision = base_revision + 1;
  review.commands = result.at("commands");
  std::vector<ProjectTable> candidate;
  for (const auto &table : snapshot.at("tables")) { candidate.push_back(ProjectTable::from_json(table)); }
  auto old = objects(before);
  auto next = objects(candidate);
  for (auto &[key, entry] : next) {
    if (const auto it = old.find(key); it != old.end()) {
      entry.before = it->second.after;
      old.erase(it);
    }
    if (entry.kind == "cell" && entry.after->contains("evaluation") &&
        io::get_string(entry.after->at("evaluation"), "state") == "error") {
      review.errors.push_back(entry); // Include unchanged errors, not just those caused by the draft.
    }
    if (entry.before != entry.after) { review.differences.push_back(std::move(entry)); }
  }
  for (auto &[key, entry] : old) {
    entry.before = std::move(entry.after);
    entry.after.reset();
    review.differences.push_back(std::move(entry));
  }
  return review;
}
}  // namespace stk::app
