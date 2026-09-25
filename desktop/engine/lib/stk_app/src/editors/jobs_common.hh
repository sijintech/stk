/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Shared helpers of the Jobs, Transfers, Logs and Bridge-log editors (WP9). */
#pragma once

#include <algorithm>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/jobs_state.hh"
#include "stk/ui/ui.hh"

namespace stk::app {


namespace jobs_ui {

/** Height in UI units that fills what is left of the main region below `used_units`. */
inline float fill_units(const EditorContext &ctx, const float used_units, const float min_units = 4.0f)
{
  if (!ctx.draw || !ctx.ui) {
    return min_units;
  }
  const float unit = std::max(1.0f, ctx.ui->style().unit);
  return std::max(min_units, float(ctx.draw->rect.height()) / unit - used_units);
}

/** Fixed width (UI units) fitting a button text. */
inline float fit_units(const EditorContext &ctx, std::string_view text)
{
  if (!ctx.ui) {
    return 4.0f;
  }
  const ui::Style &st = ctx.ui->style();
  return std::max(2.0f, (ctx.ui->measurer().width(text, st.font) + 2.0f * st.text_margin) / std::max(1.0f, st.unit));
}

inline std::string file_name(const std::string &path)
{
  std::string p = path;
  while (p.size() > 1 && (p.back() == '/' || p.back() == '\\')) {
    p.pop_back();
  }
  const size_t s = p.find_last_of("/\\");
  return s == std::string::npos ? p : p.substr(s + 1);
}

/** A form issue in the current language. */
std::string issue_text(const AppStore &store, const FormIssue &issue);

/** "2026-09-25T10:11:12.345+00:00" -> "09-25 10:11:12" (table columns). */
std::string short_time(const std::string &iso);

/** Catalog key of a transfer state ("transfers.state.running"). */
std::string transfer_state_text(const AppStore &store, const bridge::Transfer &t);

/** Keeps editor callbacks from running after the editor was destroyed (file dialogs). */
using AliveToken = std::shared_ptr<bool>;

}  // namespace jobs_ui

std::unique_ptr<Editor> make_jobs_editor(const EditorType &type);
std::unique_ptr<Editor> make_transfers_editor(const EditorType &type);
std::unique_ptr<Editor> make_logs_editor(const EditorType &type);
std::unique_ptr<Editor> make_bridge_log_editor(const EditorType &type);

}  // namespace stk::app
