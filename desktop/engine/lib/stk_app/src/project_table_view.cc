/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_table_view.hh"

#include "stk/app/project_state.hh"
#include "stk/core/utf8.hh"

#include <algorithm>
#include <stdexcept>
#include <unordered_map>

namespace stk::app {
namespace {
using io::Json;

unsigned char ascii_fold(const unsigned char character)
{
  return character >= 'A' && character <= 'Z' ? character + ('a' - 'A') : character;
}

bool contains(const std::string_view text, const std::string_view query)
{
  return std::search(text.begin(), text.end(), query.begin(), query.end(), [](const char a, const char b) {
    return ascii_fold(static_cast<unsigned char>(a)) == ascii_fold(static_cast<unsigned char>(b));
  }) != text.end();
}

std::string bounded(const std::string_view text, const size_t maximum)
{
  if (text.size() <= maximum) { return std::string(text); }
  constexpr std::string_view ellipsis = "…";
  if (maximum < ellipsis.size()) { return std::string(core::utf8::truncate_bytes(text, maximum)); }
  return std::string(core::utf8::truncate_bytes(text, maximum - ellipsis.size())) + std::string(ellipsis);
}

/** Produce only the visible JSON prefix. A cell may hold a large array or object; serializing the
 * whole value merely to display its first line would defeat the view's bounded summaries. */
class ValueSummary {
 public:
  explicit ValueSummary(const size_t maximum) : maximum_(maximum) {}

  std::string format(const Json &value)
  {
    if (value.is_string()) { string(value.get_ref<const std::string &>(), false); }
    else { json(value, 0); }
    constexpr std::string_view ellipsis = "…";
    if (truncated_ && maximum_ >= ellipsis.size()) {
      return std::string(core::utf8::truncate_bytes(output_, maximum_ - ellipsis.size())) + std::string(ellipsis);
    }
    return std::move(output_);
  }

 private:
  bool append(const std::string_view text)
  {
    const size_t remaining = maximum_ - output_.size();
    if (text.size() <= remaining) { output_.append(text); return true; }
    output_.append(core::utf8::truncate_bytes(text, remaining));
    truncated_ = true;
    return false;
  }

  bool string(const std::string_view text, const bool quoted)
  {
    if (quoted && !append("\"")) { return false; }
    for (size_t offset = 0; offset < text.size();) {
      if (output_.size() == maximum_) { truncated_ = true; return false; }
      const unsigned char character = static_cast<unsigned char>(text[offset]);
      std::string_view escaped;
      if (character == '\n') { escaped = "\\n"; }
      else if (character == '\r') { escaped = "\\r"; }
      else if (character == '\t') { escaped = "\\t"; }
      else if (quoted && character == '\"') { escaped = "\\\""; }
      else if (quoted && character == '\\') { escaped = "\\\\"; }
      if (!escaped.empty()) {
        if (!append(escaped)) { return false; }
        ++offset;
      }
      else if (character < 0x20) {
        constexpr char hex[] = "0123456789abcdef";
        const char control[] = {'\\', 'u', '0', '0', hex[character >> 4], hex[character & 15]};
        if (!append(std::string_view(control, sizeof(control)))) { return false; }
        ++offset;
      }
      else {
        const auto decoded = core::utf8::decode(text, offset);
        if (!decoded.valid) { throw std::invalid_argument("Cell summary contains invalid UTF-8"); }
        if (!append(text.substr(offset, decoded.length))) { return false; }
        offset += decoded.length;
      }
    }
    return !quoted || append("\"");
  }

  bool json(const Json &value, const int depth)
  {
    if (depth >= 64) { truncated_ = true; return false; }
    if (value.is_string()) { return string(value.get_ref<const std::string &>(), true); }
    if (value.is_array()) {
      if (!append("[")) { return false; }
      bool first = true;
      for (const auto &child : value) {
        if (!first && !append(",")) { return false; }
        first = false;
        if (!json(child, depth + 1)) { return false; }
      }
      return append("]");
    }
    if (value.is_object()) {
      if (!append("{")) { return false; }
      bool first = true;
      for (auto item = value.begin(); item != value.end(); ++item) {
        if (!first && !append(",")) { return false; }
        first = false;
        if (!string(item.key(), true) || !append(":") || !json(item.value(), depth + 1)) { return false; }
      }
      return append("}");
    }
    return append(value.dump()); // Scalar numbers/booleans/null have bounded representations.
  }

  size_t maximum_;
  bool truncated_ = false;
  std::string output_;
};

const Json *part(const Json *record, const char *category, const std::string &field_id)
{
  if (!record) { return nullptr; }
  const auto &values = record->at(category);
  const auto found = values.find(field_id);
  return found == values.end() ? nullptr : &*found;
}

bool omitted(const Json *value)
{
  return value && io::get_string(*value, "state") != "included";
}

void fill_value(CapturedProjectCell &cell, const Json *literal, const Json *definition, const Json *evaluation)
{
  cell.incomplete = omitted(literal) || omitted(definition) || omitted(evaluation);
  if (definition) {
    if (!evaluation || omitted(evaluation)) {
      cell.status = evaluation && io::get_string(*evaluation, "reason") == "value_limit" ?
                        "omitted" : "evaluation_unavailable";
      cell.incomplete = true;
      return;
    }
    const auto &result = evaluation->at("value");
    const auto state = io::get_string(result, "state");
    if (state == "error") {
      cell.status = "formula_error";
      cell.value_text = bounded("#" + io::get_string(result.at("error"), "code", "error"), 160);
    }
    else if (state == "ok" && result.contains("value")) {
      cell.status = "evaluated";
      cell.value_text = "= " + project_value_summary(result.at("value"), 158);
    }
    else {
      cell.status = "evaluation_unavailable";
      cell.incomplete = true;
    }
  }
  else if (!literal) {
    cell.status = "unset";
  }
  else if (omitted(literal)) {
    cell.status = "omitted";
  }
  else {
    const auto &value = literal->at("value");
    cell.status = value.is_null() ? "null" : "literal";
    cell.value_text = project_value_summary(value);
  }
}
}  // namespace

std::vector<int> project_table_rows(const ProjectTable &table, const ProjectTableQuery &query)
{
  if (query.text.size() > 256 || !core::utf8::is_valid(query.text)) {
    throw std::invalid_argument("Table search must contain valid UTF-8 and at most 256 bytes");
  }
  std::vector<int> rows;
  for (size_t row = 0; row < table.records.size(); ++row) {
    bool matches = query.text.empty() || contains(table.records[row].id, query.text);
    bool has_error = false;
    for (size_t column = 0; column < table.fields.size(); ++column) {
      if (matches && (!query.errors_only || has_error)) { break; }
      const Json *evaluation = table.evaluation(int(row), int(column));
      const bool error = evaluation && io::get_string(*evaluation, "state") == "error";
      has_error |= error;
      if (!matches) {
        matches = contains(table.text(int(row), int(column)), query.text);
        if (!matches && error) {
          matches = contains(io::get_string(evaluation->at("error"), "message"), query.text);
        }
      }
    }
    if (matches && (!query.errors_only || has_error)) { rows.push_back(int(row)); }
  }
  return rows;
}

std::string project_value_summary(const Json &value, const size_t max_bytes)
{
  if (!max_bytes) { return {}; }
  return ValueSummary(max_bytes).format(value);
}

CapturedProjectTable project_context_table(const Json &context)
{
  CapturedProjectTable table;
  const auto &captured = context.at("content");
  if (io::get_string(captured, "state") == "omitted") {
    table.omission_reason = captured.at("reason").get<std::string>();
    return table;
  }
  if (io::get_string(captured, "state") != "included" || !captured.contains("value")) {
    throw std::invalid_argument("A full included or omitted project context is required");
  }
  const auto &selection = context.at("selection"), &content = captured.at("value");
  const auto records = selection.at("record_ids").get<std::vector<std::string>>();
  const auto fields = selection.at("field_ids").get<std::vector<std::string>>();
  if (records.empty() || records.size() > 100 || fields.empty() || fields.size() > 64 ||
      records.size() * fields.size() > 1000) {
    throw std::invalid_argument("Project context selection exceeds its bounds");
  }
  std::unordered_map<std::string, const Json *> record_data, field_data;
  for (const auto &record : content.at("records")) { record_data.emplace(record.at("id").get<std::string>(), &record); }
  for (const auto &field : content.at("fields")) { field_data.emplace(field.at("id").get<std::string>(), &field); }
  const bool missing_table = content.at("table").is_null();
  table.cells.reserve(records.size() * fields.size());
  for (const auto &record_id : records) {
    const auto row = record_data.find(record_id);
    const Json *record = row == record_data.end() ? nullptr : row->second;
    for (const auto &field_id : fields) {
      const auto column = field_data.find(field_id);
      const Json *field = column == field_data.end() ? nullptr : column->second;
      CapturedProjectCell cell;
      cell.record_id = record_id;
      cell.field_id = field_id;
      cell.field_name = field ? io::get_string(*field, "name") : field_id;
      cell.type = field ? io::get_string(*field, "type") : "";
      cell.unit = field ? io::get_string(*field, "unit") : "";
      cell.value_text = "—";
      cell.details = {{"context_id", context.at("id")}, {"source_revision", context.at("source_revision")},
                      {"table_id", selection.at("table_id")}, {"record_id", record_id}, {"field_id", field_id},
                      {"field", field ? *field : Json(nullptr)}};
      const Json *literal = part(record, "literals", field_id), *definition = part(record, "definitions", field_id),
                 *evaluation = part(record, "evaluations", field_id);
      if (literal) { cell.details["literal"] = *literal; }
      if (definition) { cell.details["definition"] = *definition; }
      if (evaluation) { cell.details["evaluation"] = *evaluation; }
      if (missing_table || !record || !field) {
        cell.status = missing_table ? "missing_table" : !record ? "missing_record" : "missing_field";
        cell.incomplete = true;
      }
      else { fill_value(cell, literal, definition, evaluation); }
      table.cells.push_back(std::move(cell));
    }
  }
  return table;
}

}  // namespace stk::app
