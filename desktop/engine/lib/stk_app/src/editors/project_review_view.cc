/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "project_review_view.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_state.hh"
#include <algorithm>
#include <limits>

namespace stk::app {
namespace {
std::string summary(const std::optional<io::Json> &value)
{
  if (!value) { return "—"; }
  if (value->contains("evaluation") && io::get_string(value->at("evaluation"), "state") == "error") {
    return "#" + io::get_string(value->at("evaluation").at("error"), "code");
  }
  if (value->contains("value")) {
    return (value->contains("definition") ? "= " : "") + value->at("value").dump();
  }
  return value->dump();
}
}  // namespace

void ProjectReviewView::draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  layout.paragraph(ctx.tr("project.review.hint"));
  if (!state.preview_supported()) { layout.paragraph(ctx.tr("project.review.unsupported")); }
  layout.text_area("review_source", {
    [&state] { return state.review_source(); },
    [&state, handle = state.project()->handle](std::string source) {
      if (state.project() && state.project()->handle == handle) { state.set_review_source(std::move(source)); }
    }
  }, {.max_length = 256 * 1024, .mono = true, .visible_lines = 3});
  auto &input = layout.row();
  input.button("review_preview", ctx.tr("project.review.preview"), [&state] { state.preview(); })
      .disable(!state.preview_supported() || state.busy());
  input.button("review_example", ctx.tr("project.review.example"), [&state] {
    state.set_review_source(io::Json::array({{{"op", "create_table"}, {"name", "Proposed table"}}}).dump(2));
  }).disable(state.busy());
  input.button("review_discard", ctx.tr("project.review.discard"), [&state] { state.discard_review(); });
  if (!state.review_error().empty()) { layout.paragraph(state.review_error()); }
  const auto review = state.review();
  if (shown_ != review) {
    shown_ = review;
    selected_ = 0;
    category_ = 0;
    details_row_ = details_category_ = -1;
    // The full review is inspectable. Do not silently drop lines from long definitions/commands.
    commands_ = ui::LogBuffer(std::numeric_limits<size_t>::max());
    details_ = ui::LogBuffer(std::numeric_limits<size_t>::max());
    if (review) { commands_.append(review->commands.dump(2)); }
  }
  if (!review) { return; }
  layout.label(ctx.store.catalog().format("project.review.summary", {
    {"base", std::to_string(review->base_revision)}, {"next", std::to_string(review->proposed_revision)},
    {"changes", std::to_string(review->differences.size())}, {"errors", std::to_string(review->errors.size())}}));
  const bool stale = state.project()->id != review->project_id || state.project()->revision != review->base_revision;
  if (stale) { layout.paragraph(ctx.tr("project.review.stale")); }
  if (!review->errors.empty()) { layout.paragraph(ctx.tr("project.review.errors_hint")); }
  layout.button("review_apply", ctx.tr("project.review.apply"), [&state, review] {
    if (state.review() == review) { state.apply_review(); }
  })
      .disable(!state.can_apply_review());
  layout.tabs("review_category", {std::string(ctx.tr("project.review.changes")),
                                   std::string(ctx.tr("project.review.errors"))}, {
    [this] { return category_; }, [this](int category) { category_ = category; selected_ = 0; }
  });
  const auto &entries = category_ == 1 ? review->errors : review->differences;
  if (entries.empty()) { layout.label(ctx.tr("project.review.empty")); }
  else {
    selected_ = std::clamp(selected_, 0, int(entries.size()) - 1);
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("project.review.object")), 5},
                    {std::string(ctx.tr("project.review.location")), 21},
                    {std::string(ctx.tr("project.review.before")), 12},
                    {std::string(ctx.tr("project.review.after")), 12}};
    spec.rows = int(entries.size());
    spec.visible_rows = float(std::clamp(spec.rows, 1, 5));
    spec.data_version = state.version() * 2 + uint64_t(category_);
    spec.selected = ui::bind(selected_);
    spec.cell = [review, category = category_, store = &ctx.store](int row, int col) {
      const auto &entry = (category == 1 ? review->errors : review->differences)[size_t(row)];
      if (col == 0) { return std::string(store->tr("project.review." + entry.kind)); }
      if (col == 1) { return entry.label; }
      return summary(col == 2 ? entry.before : entry.after);
    };
    layout.table("review_rows", std::move(spec));
    if (details_row_ != selected_ || details_category_ != category_) {
      details_row_ = selected_;
      details_category_ = category_;
      const auto &entry = entries[size_t(selected_)];
      const io::Json detail = {{"table_id", entry.table_id}, {"record_id", entry.record_id}, {"field_id", entry.field_id},
          {"before", entry.before ? *entry.before : io::Json(nullptr)}, {"after", entry.after ? *entry.after : io::Json(nullptr)}};
      details_.clear();
      details_.append(detail.dump(2));
    }
    if (auto *panel = layout.panel("review_details", ctx.tr("project.review.details"), true)) {
      panel->log_view("value", details_, 8);
    }
  }
  if (auto *panel = layout.panel("review_commands", ctx.tr("project.review.commands"), false)) {
    panel->log_view("value", commands_, 8);
  }
}
}  // namespace stk::app
