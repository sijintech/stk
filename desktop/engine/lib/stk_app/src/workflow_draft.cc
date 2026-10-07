/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/workflow_draft.hh"

#include "stk/app/analysis_document.hh"
#include "stk/core/utf8.hh"

#include <cmath>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
using Limits = WorkflowDocumentLimits;

const std::set<std::string> kStepKeys = {"id", "kind", "ref", "label", "inputs", "parameters", "after"};

void require(const bool condition, const std::string &message)
{
  if (!condition) { throw std::invalid_argument(message); }
}

bool same_json(const Json &a, const Json &b)
{
  return io::python_json_dumps(a, true, true) == io::python_json_dumps(b, true, true);
}

size_t code_points(std::string_view text) { return core::utf8::count_code_points(text); }

/** Python's _text: a non-empty str without NUL of at most `limit` characters. */
bool text(const Json &value, const size_t limit)
{
  if (!value.is_string()) { return false; }
  const auto &string = value.get_ref<const std::string &>();
  return !string.empty() && core::utf8::is_valid(string) && string.find('\0') == std::string::npos &&
      code_points(string) <= limit;
}

/** "step.port" split into its identifiers, else nullopt. */
std::optional<std::pair<std::string, std::string>> port_ref(std::string_view value)
{
  const auto dot = value.find('.');
  if (dot == std::string_view::npos) { return std::nullopt; }
  const auto step = value.substr(0, dot), port = value.substr(dot + 1);
  if (!workflow_identifier(step) || !workflow_identifier(port)) { return std::nullopt; }
  return std::pair{std::string(step), std::string(port)};
}

void check_step(const Json &step)
{
  require(step.is_object(), "Workflow steps must be objects");
  for (const auto &[key, value] : step.items()) {
    (void)value;
    require(kStepKeys.count(key) || (key.rfind("x-", 0) == 0 && code_points(key) <= 64),
            "Workflow steps allow id, kind, ref, label, inputs, parameters, after and x- keys");
  }
  require(step.contains("id") && step.at("id").is_string() && workflow_identifier(step.at("id").get_ref<const std::string &>()),
          "Workflow step id must be a lowercase identifier such as field_2");
  require(step.contains("kind") && step.at("kind").is_string() && workflow_identifier(step.at("kind").get_ref<const std::string &>()),
          "Workflow step kind must be a lowercase identifier such as field_2");
  require(step.contains("ref") && step.at("ref").is_object() && !step.at("ref").empty() &&
          step.at("ref").size() <= Limits::max_ref_entries, "Workflow step ref must be an object with 1 to 8 entries");
  for (const auto &[key, value] : step.at("ref").items()) {
    require(workflow_identifier(key) && text(value, 128), "Workflow ref entries are identifiers naming 1 to 128 characters");
  }
  if (step.contains("label")) { require(text(step.at("label"), 256), "Workflow step label must be 1 to 256 characters without NUL"); }
  if (step.contains("inputs")) {
    const auto &inputs = step.at("inputs");
    require(inputs.is_object() && inputs.size() <= Limits::max_inputs, "Workflow step inputs must be an object with at most 32 ports");
    for (const auto &[port, link] : inputs.items()) {
      require(workflow_identifier(port) && link.is_object() && link.size() == 1 && link.contains("from") &&
              link.at("from").is_string() && port_ref(link.at("from").get_ref<const std::string &>()),
              "Workflow inputs must be exactly {\"from\": \"step.port\"}");
    }
  }
  if (step.contains("parameters")) {
    const auto &parameters = step.at("parameters");
    require(parameters.is_object() && parameters.size() <= Limits::max_parameters &&
            io::python_json_dumps(parameters, true, true).size() <= Limits::max_parameters_bytes,
            "Workflow step parameters must be an object of at most 64 entries and 64 KiB");
    for (const auto &[name, value] : parameters.items()) {
      (void)value;
      require(workflow_identifier(name), "Workflow parameter names must be lowercase identifiers");
    }
  }
  if (step.contains("after")) {
    const auto &after = step.at("after");
    require(after.is_array() && after.size() <= Limits::max_after, "Workflow step after must list at most 64 distinct step ids");
    std::set<std::string> seen;
    for (const auto &id : after) {
      require(id.is_string() && workflow_identifier(id.get_ref<const std::string &>()) && seen.insert(id.get<std::string>()).second,
              "Workflow step after must list at most 64 distinct step ids");
    }
  }
}

/** Index of the only step with this id, else -1. */
int unique_step(const Json &document, const std::string &id)
{
  int found = -1;
  const auto &steps = document.at("steps");
  for (size_t i = 0; i < steps.size(); ++i) {
    if (steps[i].is_object() && io::get_string(steps[i], "id") == id) {
      if (found >= 0) { return -1; }
      found = int(i);
    }
  }
  return found;
}

bool valid_name(const std::string &name)
{
  return !name.empty() && name.size() <= 1024 && core::utf8::is_valid(name) && name.find('\0') == std::string::npos &&
      code_points(name) <= 256 && visible_text(name);
}
}  // namespace

bool workflow_identifier(std::string_view value)
{
  if (value.empty() || value.size() > 64 || value[0] < 'a' || value[0] > 'z') { return false; }
  for (const char c : value) {
    if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) { return false; }
  }
  return true;
}

void check_workflow_document(const Json &document)
{
  check_analysis_json_bounds(document);
  require(document.is_object() && document.size() == 3 && document.contains("format") && document.contains("steps") &&
          document.contains("ui"), "Workflow document requires exactly format, steps and ui");
  require(document.at("format") == "stk.workflow/1", "Unsupported workflow document format");
  const auto &steps = document.at("steps");
  require(steps.is_array() && steps.size() <= Limits::max_steps, "Workflow steps must be a list of at most 200 steps");
  for (const auto &step : steps) { check_step(step); }
  const auto &ui = document.at("ui");
  require(ui.is_object(), "Workflow ui must be an object");
  if (ui.contains("positions")) {
    const auto &positions = ui.at("positions");
    require(positions.is_object(), "Workflow ui.positions maps step ids to finite [x, y] within 1e6");
    for (const auto &[id, point] : positions.items()) {
      bool ok = workflow_identifier(id) && point.is_array() && point.size() == 2;
      for (size_t i = 0; ok && i < 2; ++i) {
        ok = point[i].is_number() && std::isfinite(point[i].get<double>()) && std::abs(point[i].get<double>()) <= 1e6;
      }
      require(ok, "Workflow ui.positions maps step ids to finite [x, y] within 1e6");
    }
  }
  require(io::python_json_dumps(document, true, true).size() <= Limits::max_document_bytes, "Workflow document exceeds 256 KiB");
}

void WorkflowDraft::pin(std::string handle, std::string workflow_id, const int64_t revision, std::string name,
                        const Json &document)
{
  require(!handle.empty() && handle.size() <= 1024 && core::utf8::is_valid(handle) && canonical_uuid(workflow_id) &&
          revision >= 0, "Workflow draft requires an opening handle, UUID and revision");
  require(valid_name(name), "Invalid workflow name");
  check_workflow_document(document);
  Json detached = document;
  handle_ = std::move(handle); workflow_id_ = std::move(workflow_id); revision_ = revision;
  baseline_name_ = std::move(name); baseline_ = std::move(detached);
  document_.reset(); name_.reset();
  ++generation_; ++version_; ++check_version_;
}

void WorkflowDraft::reset()
{
  handle_.clear(); workflow_id_.clear(); baseline_name_.clear(); revision_ = -1;
  baseline_ = nullptr; document_.reset(); name_.reset();
  ++generation_; ++version_; ++check_version_;
}

bool WorkflowDraft::current(const std::string &handle, const int64_t revision) const
{
  return pinned() && handle == handle_ && revision == revision_;
}

const Json &WorkflowDraft::document() const { return document_ ? *document_ : baseline_; }
const std::string &WorkflowDraft::name() const { return name_ ? *name_ : baseline_name_; }

const Json *WorkflowDraft::step(const std::string &id) const
{
  if (!pinned()) { return nullptr; }
  const int index = unique_step(document(), id);
  return index < 0 ? nullptr : &document().at("steps")[size_t(index)];
}

std::set<std::string> WorkflowDraft::edited_steps() const
{
  std::set<std::string> edited;
  if (!document_) { return edited; }
  for (const auto &candidate : document_->at("steps")) {
    const auto id = io::get_string(candidate, "id");
    const int index = unique_step(baseline_, id);
    if (index < 0 || !same_json(candidate, baseline_.at("steps")[size_t(index)])) { edited.insert(id); }
  }
  return edited;
}

WorkflowDraft::EditResult WorkflowDraft::edit(const uint64_t generation, const bool affects_check,
                                              const std::function<std::string(Json &)> &change)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  try {
    Json next = document();
    if (auto error = change(next); !error.empty()) { return {false, std::move(error)}; }
    // Keys emptied by an edit go when the saved step lacked them, so undoing restores it exactly.
    for (auto &step : next["steps"]) {
      const int index = unique_step(baseline_, io::get_string(step, "id"));
      const Json *saved = index < 0 ? nullptr : &baseline_.at("steps")[size_t(index)];
      for (const auto *key : {"inputs", "parameters", "after"}) {
        const auto found = step.find(key);
        if (found != step.end() && found->empty() && !(saved && saved->contains(key))) { step.erase(key); }
      }
    }
    auto &ui = next["ui"];
    if (ui.contains("positions") && ui.at("positions").empty() && !baseline_.at("ui").contains("positions")) { ui.erase("positions"); }
    check_workflow_document(next);
    if (same_json(next, document())) { return {true, {}}; }
    if (same_json(next, baseline_)) { document_.reset(); }
    else { document_ = std::move(next); }
    ++version_;
    if (affects_check) { ++check_version_; }
    return {true, {}};
  }
  catch (const std::exception &error) { return {false, error.what()}; }
}

WorkflowDraft::EditResult WorkflowDraft::set_name(const std::string &name, const uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  if (!valid_name(name)) { return {false, "A workflow name has 1 to 256 characters without NUL"}; }
  if (name == this->name()) { return {true, {}}; }
  if (name == baseline_name_) { name_.reset(); }
  else { name_ = name; }
  ++version_;
  return {true, {}};
}

WorkflowDraft::EditResult WorkflowDraft::add_step(const std::string &kind, const std::string &ref_key,
                                                  const std::string &ref_value,
                                                  std::optional<std::pair<double, double>> position,
                                                  const uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  if (!workflow_identifier(kind) || !workflow_identifier(ref_key)) { return {false, "A step kind and its reference key are identifiers"}; }
  if (document().at("steps").size() >= Limits::max_steps) { return {false, "A workflow holds at most 200 steps"}; }
  std::set<std::string> taken;
  for (const auto &step : document().at("steps")) { taken.insert(io::get_string(step, "id")); }
  std::string id = kind;
  for (int suffix = 2; taken.count(id); ++suffix) { id = kind + "_" + std::to_string(suffix); }
  if (id.size() > 64) { return {false, "No free step id is left for this kind"}; }
  auto result = edit(generation, true, [&](Json &next) -> std::string {
    next["steps"].push_back(Json{{"id", id}, {"kind", kind}, {"ref", {{ref_key, ref_value}}}});
    if (position) {
      const auto [x, y] = *position;
      if (!std::isfinite(x) || !std::isfinite(y) || std::abs(x) > 1e6 || std::abs(y) > 1e6) {
        return "Step positions are finite and at most 1e6 in size";
      }
      next["ui"]["positions"][id] = Json::array({int64_t(std::llround(x)), int64_t(std::llround(y))});
    }
    return {};
  });
  if (result.accepted) { result.id = id; }
  return result;
}

WorkflowDraft::EditResult WorkflowDraft::remove_step(const std::string &step, const uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  if (unique_step(document(), step) < 0) { return {false, "Only a uniquely named step can be removed"}; }
  return edit(generation, true, [&](Json &next) -> std::string {
    auto &steps = next["steps"];
    steps.erase(steps.begin() + unique_step(next, step));
    for (auto &other : steps) {
      if (auto inputs = other.find("inputs"); inputs != other.end() && inputs->is_object()) {
        for (auto it = inputs->begin(); it != inputs->end();) {
          const auto source = port_ref(io::get_string(*it, "from"));
          if (source && source->first == step) { it = inputs->erase(it); }
          else { ++it; }
        }
      }
      if (auto after = other.find("after"); after != other.end() && after->is_array()) {
        for (auto it = after->begin(); it != after->end();) {
          if (it->is_string() && it->get<std::string>() == step) { it = after->erase(it); }
          else { ++it; }
        }
      }
    }
    if (auto &ui = next["ui"]; ui.contains("positions") && ui.at("positions").is_object()) { ui["positions"].erase(step); }
    return {};
  });
}

WorkflowDraft::EditResult WorkflowDraft::set_link(const std::string &step, const std::string &port,
                                                  const std::optional<std::string> &source, const uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  if (unique_step(document(), step) < 0) { return {false, "Only a uniquely named step can be linked"}; }
  if (!workflow_identifier(port)) { return {false, "An input port is a lowercase identifier"}; }
  if (source) {
    const auto parsed = port_ref(*source);
    if (!parsed) { return {false, "A link source is \"step.port\""}; }
    if (parsed->first == step) { return {false, "A step cannot take its own output"}; }
    if (unique_step(document(), parsed->first) < 0) { return {false, "A link source must be a uniquely named step"}; }
  }
  return edit(generation, true, [&](Json &next) -> std::string {
    auto &target = next["steps"][size_t(unique_step(next, step))];
    if (source) { target["inputs"][port] = Json{{"from", *source}}; }
    else if (target.contains("inputs")) { target["inputs"].erase(port); }
    return {};
  });
}

WorkflowDraft::EditResult WorkflowDraft::set_after(const std::string &step, const std::vector<std::string> &steps,
                                                   const uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  if (unique_step(document(), step) < 0) { return {false, "Only a uniquely named step can wait for others"}; }
  std::set<std::string> seen;
  for (const auto &before : steps) {
    if (before == step) { return {false, "A step cannot wait for itself"}; }
    if (unique_step(document(), before) < 0) { return {false, "A step can only wait for uniquely named steps"}; }
    if (!seen.insert(before).second) { return {false, "Each step is listed once"}; }
  }
  return edit(generation, true, [&](Json &next) -> std::string {
    next["steps"][size_t(unique_step(next, step))]["after"] = steps;
    return {};
  });
}

WorkflowDraft::EditResult WorkflowDraft::set_parameter(const std::string &step, const std::string &name,
                                                       const std::optional<Json> &value, const uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  if (unique_step(document(), step) < 0) { return {false, "Only a uniquely named step has parameters"}; }
  if (!workflow_identifier(name)) { return {false, "A parameter name is a lowercase identifier"}; }
  return edit(generation, true, [&](Json &next) -> std::string {
    auto &target = next["steps"][size_t(unique_step(next, step))];
    if (value) { target["parameters"][name] = *value; }
    else if (target.contains("parameters")) { target["parameters"].erase(name); }
    return {};
  });
}

WorkflowDraft::EditResult WorkflowDraft::set_label(const std::string &step, const std::optional<std::string> &label,
                                                   const uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  if (unique_step(document(), step) < 0) { return {false, "Only a uniquely named step has a label"}; }
  return edit(generation, true, [&](Json &next) -> std::string {
    auto &target = next["steps"][size_t(unique_step(next, step))];
    if (label && !label->empty()) { target["label"] = *label; }
    else { target.erase("label"); }
    return {};
  });
}

WorkflowDraft::EditResult WorkflowDraft::move_steps(const std::map<std::string, std::pair<double, double>> &positions,
                                                    const uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The workflow draft has changed or is unavailable"}; }
  for (const auto &[id, point] : positions) {
    if (unique_step(document(), id) < 0) { return {false, "Only uniquely named steps can be placed"}; }
    if (!std::isfinite(point.first) || !std::isfinite(point.second) ||
        std::abs(point.first) > 1e6 || std::abs(point.second) > 1e6) { return {false, "Step positions are finite and at most 1e6 in size"}; }
  }
  return edit(generation, false, [&](Json &next) -> std::string {
    for (const auto &[id, point] : positions) {
      next["ui"]["positions"][id] = Json::array({int64_t(std::llround(point.first)), int64_t(std::llround(point.second))});
    }
    return {};
  });
}

bool WorkflowDraft::rebase(const int64_t revision, const std::string &name, const Json &document)
{
  if (!pinned() || revision < revision_ || name != baseline_name_ || !same_json(document, baseline_)) { return false; }
  if (revision != revision_) { revision_ = revision; ++version_; ++check_version_; }
  return true;
}

bool WorkflowDraft::revert(const uint64_t expected_generation)
{
  if (!accepts(expected_generation)) { return false; }
  if (!dirty()) { return true; }
  const bool checked = document_.has_value();
  document_.reset(); name_.reset();
  ++version_;
  if (checked) { ++check_version_; }
  return true;
}

bool WorkflowDraft::matches(const std::string &workflow_id, const std::string &name, const Json &document) const
{
  return pinned() && workflow_id == workflow_id_ && name == this->name() && same_json(document, this->document());
}

}  // namespace stk::app
