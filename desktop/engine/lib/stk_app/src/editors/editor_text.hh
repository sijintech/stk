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
  size_t cut = text.find("。");
  if (cut != std::string::npos) { cut += std::string_view("。").size(); }
  // An English sentence ends at ". " before a capital letter, not inside "e.g. launcher" or "1. 2".
  for (size_t at = text.find(". "); at != std::string::npos && (cut == std::string::npos || at < cut); at = text.find(". ", at + 1)) {
    if (at + 2 < text.size() && text[at + 2] >= 'A' && text[at + 2] <= 'Z') { cut = at + 1; break; }
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
