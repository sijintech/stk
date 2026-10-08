/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "project_review_view.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_discussion.hh"
#include "archive_controls.hh"
#include "project_labels.hh"
#include "editor_text.hh"
#include <algorithm>
#include <limits>

namespace stk::app {
namespace {
std::string summary(const AppStore &store, const std::optional<io::Json> &value)
{
  if (!value) { return "—"; }
  if (value->contains("evaluation") && io::get_string(value->at("evaluation"), "state") == "error") {
    return formula_error_label(store, io::get_string(value->at("evaluation").at("error"), "code"));
  }
  if (value->contains("value")) {
    return (value->contains("definition") ? "= " : "") + value->at("value").dump();
  }
  return value->dump();
}
}  // namespace

void ProjectReviewView::saved_drafts(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  if (draft_project_ != state.project()->id) {
    draft_project_ = state.project()->id;
    draft_title_.clear();
    selected_draft_.clear();
  }
  const auto &saved = state.saved_review();
  if (!saved.empty()) {
    auto &discussion = state.discussion();
    const auto saved_id = io::get_string(saved, "id");
    if (discussion.supported() && discussion.origin_draft() != saved_id && !discussion.busy() && !state.busy()) {
      discussion.load_origin(saved_id, true);
    }
    if (discussion.origin_draft() == saved_id && !discussion.origin().empty()) {
      layout.paragraph(ctx.store.catalog().format("discussion.review_origin", {
        {"message", io::get_string(discussion.origin(), "message_id")},
        {"context", io::get_string(discussion.origin(), "context_id")}}));
    }
    if (discussion.supported()) {
      if (!discussion.error().empty()) { layout.paragraph(discussion.error()); }
      layout.button("refresh_review_origin", ctx.tr("discussion.refresh_origin"), [&discussion, &state, saved_id] {
        if (io::get_string(state.saved_review(), "id") == saved_id) { discussion.load_origin(saved_id); }
      }).disable(discussion.busy() || state.busy());
    }
    const auto status = io::get_string(saved, "status");
    layout.paragraph(ctx.store.catalog().format("project.drafts.loaded", {
      {"title", io::get_string(saved, "title")}, {"base", std::to_string(io::get_int(saved, "base_revision", -1))},
      {"status", std::string(ctx.tr("project.drafts." + status))}}));
    if (status == "applied") {
      layout.label(ctx.store.catalog().format("project.drafts.applied_at", {
        {"revision", std::to_string(io::get_int(saved, "applied_revision", -1))}}));
    }
    if (status != "pending" || io::get_int(saved, "base_revision", -1) != state.project()->revision) {
      layout.paragraph(ctx.tr("project.drafts.stale"));
      layout.button("review_copy_saved", ctx.tr("project.drafts.copy"), [&state, id = saved.at("id")] {
        if (!state.saved_review().empty() && state.saved_review().at("id") == id) { state.copy_saved_review(); }
      }).disable(state.busy());
    }
  }
  auto *panel = layout.panel("saved_reviews", ctx.tr("project.drafts.title"), false);
  if (!panel) { return; }
  if (!state.drafts_supported()) { panel->paragraph(ctx.tr("project.drafts.unsupported")); return; }
  // Archived drafts leave the list unless switched to them (format 11).
  state.sync_archive();
  if (!state.drafts_loaded() && !state.busy()) { state.load_drafts(0, true); }
  hint(*panel, ctx, "project.drafts.hint");
  archive_switch(*panel, ctx, "draft", {[&state] { return state.show_archived_drafts(); },
      [&state](const bool show) { state.set_show_archived_drafts(show); }}, "drafts_show_archived");
  panel->prop(ctx.tr("project.drafts.name")).text_field("draft_title", ui::bind(draft_title_), {.max_length = 1024});
  auto &save = panel->row();
  save.button("save_review", ctx.tr("project.drafts.save"), [this, &state, review = state.review()] {
    if (state.review() == review) { state.save_review(draft_title_); }
  }).disable(!state.can_apply_review() || !state.saved_review().empty() || draft_title_.empty());
  save.button("refresh_drafts", ctx.tr("project.drafts.refresh"), [&state] { state.load_drafts(); }).disable(state.busy());
  if (!state.drafts_error().empty()) { panel->paragraph(state.drafts_error()); }
  const auto drafts = state.drafts();
  if (drafts.empty()) { panel->label(ctx.tr("project.drafts.empty")); }
  else {
    if (std::none_of(drafts.begin(), drafts.end(), [&](const auto &draft) { return draft.at("id") == selected_draft_; })) {
      selected_draft_ = io::get_string(drafts.front(), "id");
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("project.drafts.name")), 16}, {std::string(ctx.tr("project.drafts.base")), 5},
                    {std::string(ctx.tr("project.drafts.status")), 8}, {std::string(ctx.tr("project.drafts.applied_revision")), 7}};
    spec.rows = int(drafts.size());
    spec.visible_rows = float(std::min(spec.rows, 4));
    spec.data_version = state.version();
    spec.selected = {[this, drafts] {
      for (size_t i = 0; i < drafts.size(); ++i) { if (drafts[i].at("id") == selected_draft_) { return int(i); } }
      return -1;
    }, [this, drafts](int row) {
      if (row >= 0 && size_t(row) < drafts.size()) { selected_draft_ = io::get_string(drafts[size_t(row)], "id"); }
    }};
    spec.cell = [drafts, store = &ctx.store, revision = state.project()->revision](int row, int col) {
      const auto &draft = drafts[size_t(row)];
      if (col == 0) { return io::get_string(draft, "title") + " / " + io::get_string(draft, "id").substr(0, 8); }
      if (col == 1) { return std::to_string(io::get_int(draft, "base_revision", -1)); }
      if (col == 2) {
        const auto status = io::get_string(draft, "status");
        return std::string(store->tr("project.drafts." +
            (status == "pending" && io::get_int(draft, "base_revision", -1) != revision ? "outdated" : status)));
      }
      return draft.at("applied_revision").is_null() ? std::string("—") : draft.at("applied_revision").dump();
    };
    panel->table("draft_rows", std::move(spec));
    const auto chosen = std::find_if(drafts.begin(), drafts.end(), [&](const auto &draft) { return draft.at("id") == selected_draft_; });
    const bool archived = ctx.store.archive().archived("draft", selected_draft_);
    const bool pending = chosen != drafts.end() && io::get_string(*chosen, "status") == "pending" && !archived;
    archived_notice(*panel, ctx, "draft", selected_draft_);
    auto &actions = panel->row();
    const auto handle = state.project()->handle;
    actions.button("load_draft", ctx.tr("project.drafts.load"), [&state, handle, id = selected_draft_] {
      if (state.project() && state.project()->handle == handle) { state.load_draft(id); }
    }).disable(state.busy() || !pending);
    actions.button("discard_saved_draft", ctx.tr("project.drafts.discard"), [&state, handle, id = selected_draft_] {
      if (state.project() && state.project()->handle == handle) { state.discard_saved_draft(id); }
    }).disable(state.busy() || !pending);
    if (chosen != drafts.end()) { archive_button(actions, ctx, "draft", selected_draft_, "draft_archive", false, !state.busy()); }
  }
  auto &pages = panel->row();
  pages.button("drafts_previous", ctx.tr("project.drafts.previous"), [&state] {
    state.load_drafts(std::max(int64_t(0), state.drafts_offset() - 100));
  }).disable(state.busy() || state.drafts_offset() == 0);
  pages.button("drafts_next", ctx.tr("project.drafts.next"), [&state] {
    state.load_drafts(state.drafts_next_offset());
  }).disable(state.busy() || state.drafts_next_offset() < 0);
}

void ProjectReviewView::draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  hint(layout, ctx, "project.review.hint");
  saved_drafts(layout, ctx, state);
  if (!state.preview_supported()) { layout.paragraph(ctx.tr("project.review.unsupported")); }
  // Edits normally arrive from the cell editor, a saved draft or the AI Assistant; the JSON is for experts.
  if (auto *json = layout.panel("review_json", ctx.tr("project.review.json"), false)) {
    json->text_area("review_source", {
      [&state] { return state.review_source(); },
      [&state, handle = state.project()->handle](std::string source) {
        if (state.project() && state.project()->handle == handle) { state.set_review_source(std::move(source)); }
      }
    }, {.max_length = 256 * 1024, .mono = true, .visible_lines = 3});
    json->button("review_example", ctx.tr("project.review.example"), [&state] {
      state.set_review_source(io::Json::array({{{"op", "create_table"}, {"name", "Proposed table"}}}).dump(2));
    }).disable(state.busy());
  }
  auto &input = layout.row();
  input.button("review_preview", ctx.tr("project.review.preview"), [&state] { state.preview(); })
      .disable(!state.preview_supported() || state.busy());
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
      if (col == 1) {
        return entry.row > 0 ? entry.label + " / " + store->catalog().format("project.row", {{"n", std::to_string(entry.row)}}) : entry.label;
      }
      return summary(*store, col == 2 ? entry.before : entry.after);
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
    if (auto *panel = layout.panel("review_details", ctx.tr("project.review.details"), false)) {
      panel->log_view("value", details_, 8);
    }
  }
  if (auto *panel = layout.panel("review_commands", ctx.tr("project.review.commands"), false)) {
    panel->log_view("value", commands_, 8);
  }
}
}  // namespace stk::app
