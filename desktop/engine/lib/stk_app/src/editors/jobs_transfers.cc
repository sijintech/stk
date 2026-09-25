/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The Transfers editor (WP9): every upload and download the bridge knows (journaled, resumable),
 * with state, progress, the hub review of an upload's workspace.import, resume and cancel; files
 * waiting for a workspace (dropped or picked before one was chosen) are listed first.
 */

#include "../app_theme.hh"
#include "jobs_common.hh"

namespace stk::app {

namespace {

using namespace jobs_ui;

class TransfersEditor final : public Editor {
 public:
  explicit TransfersEditor(const EditorType &type) : Editor(type) {}

  ui::Color main_background(const ui::Theme & /*theme*/) const override
  {
    return theme::kListBack;
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    JobsState &jobs = ctx.store.jobs();
    jobs.sync();
    const std::string_view refresh = ctx.tr("jobs.refresh");
    row.button("refresh", refresh, [&jobs]() { jobs.refresh_transfers(); })
        .width(fit_units(ctx, refresh))
        .disable(!jobs.ready());
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    JobsState &jobs = ctx.store.jobs();
    jobs.sync();
    AppStore &store = ctx.store;
    const std::vector<std::string> &pending = jobs.pending_uploads();
    const std::vector<bridge::Transfer> &list = jobs.transfers();
    const int np = int(pending.size());

    const bridge::Transfer *sel = nullptr;
    if (!selected_.empty()) {
      sel = jobs.transfer(selected_);
    }
    ui::Layout &row = l.row(false);
    const std::string id = sel ? sel->id : std::string();
    const bool resumable = sel && (sel->state == "interrupted" || sel->state == "failed");
    row.button("resume", ctx.tr("transfers.resume"), [&jobs, id]() { jobs.resume_transfer(id); })
        .disable(!jobs.ready() || !resumable)
        .tip(ctx.tr("transfers.resume.tip"));
    row.button("cancel", ctx.tr("transfers.cancel"), [&jobs, id]() { jobs.cancel_transfer(id); })
        .disable(!jobs.ready() || !sel || sel->finished())
        .tip(ctx.tr("transfers.cancel.tip"));
    if (np > 0) {
      row.button("start_pending", ctx.tr("jobs.pending.start"), [&jobs]() { jobs.start_pending(); })
          .disable(!jobs.ready() || jobs.workspace().empty());
    }

    ui::TableSpec t;
    t.columns = {{std::string(ctx.tr("transfers.col.file")), 9.0f},
                 {std::string(ctx.tr("transfers.col.direction")), 3.5f},
                 {std::string(ctx.tr("transfers.col.progress")), 4.0f, true, true},
                 {std::string(ctx.tr("transfers.col.size")), 5.0f, true, true},
                 {std::string(ctx.tr("transfers.col.state")), 5.0f},
                 {std::string(ctx.tr("transfers.col.updated")), 5.5f}};
    t.rows = np + int(list.size());
    t.cell = [&pending, &list, &store, np](int r, int c) -> std::string {
      if (r < np) {
        switch (c) {
          case 0: return file_name(pending[size_t(r)]);
          case 1: return std::string(store.tr("transfers.upload"));
          case 2: return "0";
          case 3: return "-";
          case 4: return std::string(store.tr("transfers.state.pending"));
          default: return {};
        }
      }
      const bridge::Transfer &x = list[size_t(r - np)];
      switch (c) {
        case 0: {
          const std::string name = file_name(x.kind == "upload" ? x.local : x.remote);
          return x.files_total > 1 ? name + " (" + std::to_string(x.files_done) + "/" + std::to_string(x.files_total) + ")" :
                                     name;
        }
        case 1: return std::string(store.tr(x.kind == "upload" ? "transfers.upload" : "transfers.download"));
        case 2: {
          if (x.bytes_total <= 0) {
            return x.state == "completed" ? "100" : "0";
          }
          return std::to_string(int(100.0 * double(x.bytes_done) / double(x.bytes_total)));
        }
        case 3: return format_bytes(x.bytes_total);
        case 4: return transfer_state_text(store, x);
        default: return short_time(x.updated_at);
      }
    };
    const ui::Theme theme = ctx.ui ? ctx.ui->theme() : ui::Theme::blender_dark();
    t.cell_color = [&list, theme, np](int r, int c) -> ui::Color {
      if (c != 4 || r < np) {
        return {0, 0, 0, 0};
      }
      const bridge::Transfer &x = list[size_t(r - np)];
      if (x.kind == "upload" && x.action && x.action->in_review() && !x.finished()) {
        return theme.state.warning;
      }
      if (x.state == "completed") {
        return theme.state.success;
      }
      if (x.state == "failed") {
        return theme.state.error;
      }
      if (x.state == "interrupted" || x.state == "cancelled") {
        return theme.state.warning;
      }
      return {0, 0, 0, 0};
    };
    t.selected = {[this, &list, np]() {
                    for (size_t i = 0; i < list.size(); i++) {
                      if (list[i].id == selected_) {
                        return int(i) + np;
                      }
                    }
                    return -1;
                  },
                  [this, &list, np](int i) {
                    if (i >= np && i - np < int(list.size())) {
                      selected_ = list[size_t(i - np)].id;
                    }
                  }};
    t.visible_rows = 6.0f;
    t.data_version = jobs.version();
    l.table("transfers", std::move(t));
    if (list.empty() && pending.empty()) {
      l.label(ctx.tr("transfers.none")).disable();
    }

    if (sel) {
      const float f = sel->bytes_total > 0 ? float(double(sel->bytes_done) / double(sel->bytes_total)) :
                                             (sel->state == "completed" ? 1.0f : 0.0f);
      l.progress(f, format_bytes(sel->bytes_done) + " / " + format_bytes(sel->bytes_total));
      l.label(sel->local).tip(sel->local);
      if (!sel->remote.empty()) {
        l.label(store.catalog().format("transfers.remote", {{"path", sel->remote}}));
      }
      if (sel->action) {
        l.label(store.catalog().format("transfers.action",
                                       {{"id", sel->action->id.substr(0, 12)}, {"state", sel->action->state}}));
        if (sel->action->in_review()) {
          l.paragraph(store.tr("transfers.review_body"));
        }
      }
      if (sel->error) {
        l.paragraph(store.catalog().format("transfers.error", {{"error", sel->error->message}}));
      }
    }
  }

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    JobsState &jobs = ctx.store.jobs();
    jobs.sync();
    jobs.upload(paths);
    ctx.store.log(ctx.store.catalog().format(
        "jobs.drop.queued",
        {{"count", std::to_string(paths.size())}, {"editor", std::string(ctx.tr(type().title_key))}}));
    return true;
  }

 private:
  std::string selected_;
};

}  // namespace

std::unique_ptr<Editor> make_transfers_editor(const EditorType &type)
{
  return std::make_unique<TransfersEditor>(type);
}

}  // namespace stk::app
