/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/app/editor.hh"
#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"
#include <algorithm>

namespace stk::app {
/** Record consumers must show the loaded range separately from the whole-table count. */
inline bool project_record_pages(ui::Layout &layout, EditorContext &ctx, ProjectState &state,
                                  const ProjectTable &table, std::function<bool()> current, int64_t span = 200,
                                  const std::string &initial_record = {})
{
  const auto total = table.total_records();
  const auto shown = std::min<int64_t>(span, int64_t(table.loaded_records()));
  if (!table.records_complete && !shown && total && !state.busy() && !state.table_page_failed(table.id)) {
    state.load_table_page(table.id, 0, initial_record);
  }
  if (!table.records_complete || total > span) {
    auto &row = layout.scope(table.id).row(true);
    row.label(ctx.store.catalog().format("project.records_page", {
        {"first", std::to_string(shown ? table.record_offset + 1 : 0)},
        {"last", std::to_string(shown ? table.record_offset + shown : 0)}, {"total", std::to_string(total)}}));
    const auto change = [current, &state, id = table.id, offset = table.record_offset,
                         revision = state.project()->revision](const int64_t next) {
      if (!current() || state.busy() || !state.project() || state.project()->revision != revision) { return; }
      for (const auto &live : state.tables()) {
        if (live.id == id && live.record_offset == offset) { state.load_table_page(id, next); return; }
      }
    };
    row.button("records_previous", "‹", [change, offset = table.record_offset, span] { change(std::max<int64_t>(0, offset - span)); })
        .width(1.5f).disable(state.busy() || table.record_offset == 0);
    row.button("records_next", "›", [change, offset = table.record_offset, shown] { change(offset + shown); })
        .width(1.5f).disable(state.busy() || !shown || table.record_offset + shown >= total);
  }
  if (!shown && total) {
    if (state.table_page_failed(table.id)) {
      layout.paragraph(state.error());
      layout.scope(table.id).button("records_retry", ctx.tr("files.refresh"), [current, &state, id = table.id] {
        if (current() && !state.busy()) { state.load_table_page(id); }
      }).disable(state.busy());
    }
    else { layout.paragraph(ctx.tr("project.records_loading")); }
    return false;
  }
  return true;
}
}  // namespace stk::app
