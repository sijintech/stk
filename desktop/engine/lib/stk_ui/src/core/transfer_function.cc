/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "transfer_function.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <optional>

#include <nlohmann/json.hpp>

namespace stk::ui {
namespace {

using Points = std::vector<std::array<double, 2>>;
constexpr size_t kMaxPoints = 64;
const Points kRamp{{0, 0}, {1, 0.8}};

/* Keep JSON as the form's wire value; double precision is retained through every edit. */
std::optional<Points> read_points(const FormValue &value)
{
  if (value.kind != FormValue::Kind::String) {
    return std::nullopt;
  }
  try {
    const auto j = nlohmann::json::parse(value.str);
    if (!j.is_array() || j.size() < 2 || j.size() > kMaxPoints) {
      return std::nullopt;
    }
    Points out;
    for (const auto &pair : j) {
      if (!pair.is_array() || pair.size() != 2 || !pair[0].is_number() || !pair[1].is_number()) {
        return std::nullopt;
      }
      const double x = pair[0].get<double>(), alpha = pair[1].get<double>();
      if (!std::isfinite(x) || !std::isfinite(alpha) || x < 0 || x > 1 || alpha < 0 || alpha > 1) {
        return std::nullopt;
      }
      out.push_back({x, alpha});
    }
    std::stable_sort(out.begin(), out.end(), [](const auto &a, const auto &b) { return a[0] < b[0]; });
    return out;
  }
  catch (const nlohmann::json::exception &) {
    return std::nullopt;
  }
}

bool automatic(const FormValue &v)
{
  return v.is_null() || (v.kind == FormValue::Kind::String &&
                         nlohmann::json::parse(v.str, nullptr, false).is_null());
}

void write_points(FormModel &model, const std::string &name, const Points &points)
{
  model.set(name, FormValue::string(nlohmann::json(points).dump()));
}

/* Split the largest gap, including constant extensions to 0 and 1. */
void add_point(Points &points)
{
  Points extended = points;
  double first_alpha = points.front()[1];
  for (size_t i = 1; i < points.size() && points[i][0] == points.front()[0]; i++) {
    first_alpha = points[i][1];
  }
  extended.insert(extended.begin(), {0, first_alpha});
  extended.push_back({1, points.back()[1]});
  size_t best = 1;
  for (size_t i = 2; i < extended.size(); i++) {
    if (extended[i][0] - extended[i - 1][0] > extended[best][0] - extended[best - 1][0]) {
      best = i;
    }
  }
  const auto a = extended[best - 1];
  auto b = extended[best];
  for (size_t i = best + 1; i < extended.size() && extended[i][0] == b[0]; i++) {
    b = extended[i];
  }
  const std::array<double, 2> point{a[0] + (b[0] - a[0]) * 0.5, a[1] + (b[1] - a[1]) * 0.5};
  points.insert(points.begin() + (best - 1), point);
}

}  // namespace

void build_transfer_function(Layout &layout, const SchemaNode &node, FormModel &model,
                             std::string_view label, std::string_view tooltip)
{
  Layout *body = layout.panel(node.name, label);
  if (!body) {
    return;
  }
  auto tr = [&](const char *key, const char *fallback) {
    return layout.ctx().catalog() ? std::string(layout.ctx().catalog()->tr_or(key, fallback)) : std::string(fallback);
  };
  FormModel *m = &model;
  const std::string name = node.name;
  const auto fallback = node.default_value ? read_points(*node.default_value) : std::nullopt;
  const Points defaults = fallback.value_or(kRamp);
  Layout &controls = body->row();
  controls.checkbox("auto", tr("form.tf.auto", "Automatic"),
                    {[m, name]() { return automatic(m->get(name)); },
                     [m, name, defaults](bool on) {
                       if (on) {
                         m->set(name, FormValue::null());
                       }
                       else {
                         write_points(*m, name, defaults);
                       }
                     }}).tip(tooltip);
  controls.button("reset", tr("form.tf.reset", "Reset ramp"),
                  [m, name, defaults]() { write_points(*m, name, defaults); });
  if (automatic(model.get(name))) {
    body->paragraph(tr("form.tf.auto_hint", "Opacity follows the field type. Turn off Automatic to edit points."));
    return;
  }
  const auto points = read_points(model.get(name));
  if (!points) {
    /* Do not silently overwrite imported values. Keep an escape hatch for repair. */
    body->paragraph(tr("form.tf.invalid", "Use 2–64 [position, opacity] pairs with values from 0 to 1, or reset the ramp."));
    body->text_field("json", {[m, name]() { return m->get(name).to_string(); },
                              [m, name](std::string s) { m->set(name, FormValue::string(std::move(s))); }});
    return;
  }
  std::vector<Vec2> preview;
  for (const auto &point : *points) {
    preview.push_back({float(point[0]), float(point[1])});
  }
  body->curve_preview("preview", std::move(preview)).tip(tooltip);
  body->paragraph(tr("form.tf.axes", "Position: 0 = range minimum, 1 = maximum. Opacity: 0 = transparent, 1 = opaque."));
  for (size_t i = 0; i < points->size(); i++) {
    Layout &row = body->scope(std::to_string(i)).row(true);
    for (size_t axis = 0; axis < 2; axis++) {
      NumberProps props;
      props.min = axis == 0 && i > 0 ? (*points)[i - 1][0] : 0;
      props.max = axis == 0 && i + 1 < points->size() ? (*points)[i + 1][0] : 1;
      props.step = 0.01;
      props.precision = 3;
      row.number(axis == 0 ? "x" : "alpha", axis == 0 ? tr("form.tf.position", "Position") : tr("form.tf.opacity", "Opacity"),
                 {[m, name, i, axis]() {
                    const auto current = read_points(m->get(name));
                    return current && i < current->size() ? (*current)[i][axis] : 0.0;
                  },
                  [m, name, i, axis](double value) {
                    auto current = read_points(m->get(name));
                    if (!current || i >= current->size() || !std::isfinite(value)) {
                      return;
                    }
                    const double lo = axis == 0 && i > 0 ? (*current)[i - 1][0] : 0;
                    const double hi = axis == 0 && i + 1 < current->size() ? (*current)[i + 1][0] : 1;
                    (*current)[i][axis] = std::clamp(value, lo, hi);
                    write_points(*m, name, *current);
                  }}, props);
    }
    row.button("remove", "−", [m, name, i]() {
      auto current = read_points(m->get(name));
      if (current && current->size() > 2 && i < current->size()) {
        current->erase(current->begin() + i);
        write_points(*m, name, *current);
      }
    }).width(1.2f).disable(points->size() <= 2).tip(tr("form.tf.remove", "Remove point"));
  }
  body->button("add", tr("form.tf.add", "Add point"), [m, name]() {
    auto current = read_points(m->get(name));
    if (current && current->size() < kMaxPoints) {
      add_point(*current);
      write_points(*m, name, *current);
    }
  }).disable(points->size() >= kMaxPoints);
}

}  // namespace stk::ui
