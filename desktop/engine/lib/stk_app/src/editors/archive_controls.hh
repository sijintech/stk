/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
/** Shared archive controls (docs/design/project-archive.md): a "show archived (N)" switch for a list, an
 * archive/restore button for one object and the read-only notice of an archived object. */

#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_archive.hh"

#include <optional>
#include <string>

namespace stk::app {

/** The list filter to send: true lists only archived objects, false the others; nullopt when the service or
 * project cannot archive (lists stay unfiltered, as before). */
inline std::optional<bool> archive_filter(EditorContext &ctx, const bool show)
{
  auto &archive = ctx.store.archive();
  archive.sync();
  return archive.supported() ? std::optional<bool>(show) : std::nullopt;
}

/** "Show archived (N)" switching a list to only its archived objects, drawn once something of `kind` is
 * archived (or while switched on). `counted` false leaves N out, for lists showing part of a kind. */
inline void archive_switch(ui::Layout &layout, EditorContext &ctx, const std::string &kind, ui::Binding<bool> show,
                           const std::string &key, const bool counted = true)
{
  auto &archive = ctx.store.archive();
  archive.sync();
  if (!archive.supported() || (!show.value() && archive.count(kind) == 0)) { return; }
  layout.checkbox(key, counted ? ctx.store.catalog().format("archive.show", {{"count", std::to_string(archive.count(kind))}}) :
                                 std::string(ctx.tr("archive.show_plain")), std::move(show));
}
inline void archive_switch(ui::Layout &layout, EditorContext &ctx, const std::string &kind, bool &show,
                           const std::string &key, const bool counted = true)
{
  archive_switch(layout, ctx, kind, ui::bind(show), key, counted);
}

/** "Archive" or "Restore" for one object; ``include_runs`` also covers a workflow's runs that are not running.
 * Returns the button (nullptr when nothing can be archived here). */
inline ui::Widget *archive_button(ui::Layout &layout, EditorContext &ctx, const std::string &kind, const std::string &id,
                                  const std::string &key, const bool include_runs = false, const bool enabled = true)
{
  auto &archive = ctx.store.archive();
  archive.sync();
  if (!archive.supported() || id.empty()) { return nullptr; }
  const bool archived = archive.archived(kind, id);
  auto *state = &archive;
  const std::string tip = std::string(archived ? "archive.restore" : "archive.archive") + (include_runs ? ".runs_tip" : ".tip");
  return &layout.button(key, ctx.tr(archived ? "archive.restore" : "archive.archive"), [state, kind, id, archived, include_runs] {
    state->set(kind, {id}, !archived, include_runs);
  }).disable(archive.busy() || !enabled).tip(ctx.tr(tip));
}

/** Whether the object is archived; if so, says what that means for this kind. Archived objects are frozen: they
 * cannot be changed (nor retried, sent, applied or discarded in place) but can be used as they are; changes go
 * through restoring or a copy (owner decision 2026-10-08). */
inline bool archived_notice(ui::Layout &layout, EditorContext &ctx, const std::string &kind, const std::string &id)
{
  auto &archive = ctx.store.archive();
  archive.sync();
  if (!archive.supported() || id.empty() || !archive.archived(kind, id)) { return false; }
  const bool record = kind == "workflow_run" || kind == "analysis_run" || kind == "simulation_run";
  layout.paragraph(ctx.tr("archive.notice." + std::string(record ? "run" : kind)));
  return true;
}

}  // namespace stk::app
