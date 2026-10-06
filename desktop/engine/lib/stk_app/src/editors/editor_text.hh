/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Panel notes on one line (docs/design/user-review-2026-10-06.md, item 4): the first sentence says
 * what the panel does; the whole note, with its limits and what never happens, is the tooltip.
 */
#pragma once

#include "stk/app/editor.hh"

#include <string>
#include <string_view>

namespace stk::app {

inline void hint(ui::Layout &layout, EditorContext &ctx, std::string_view key)
{
  const std::string text(ctx.tr(key));
  size_t cut = std::string::npos;
  for (const std::string_view stop : {std::string_view("。"), std::string_view(". ")}) {
    const auto at = text.find(stop);
    if (at != std::string::npos && (cut == std::string::npos || at + stop.size() < cut)) { cut = at + stop.size(); }
  }
  if (cut == std::string::npos || text.find_first_not_of(" ", cut) == std::string::npos) {
    layout.paragraph(text);
    return;
  }
  auto first = text.substr(0, cut);
  while (!first.empty() && first.back() == ' ') { first.pop_back(); }
  layout.paragraph(first + " …").tip(text);
}

}  // namespace stk::app
