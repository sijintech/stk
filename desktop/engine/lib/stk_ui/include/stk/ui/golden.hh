/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Deterministic serialization of a built frame (resolved widget rects per block and the draw list)
 * for layout goldens. One widget / draw command per line so diffs stay readable.
 */
#pragma once

#include <string>

#include <nlohmann/json.hpp>

#include "stk/ui/draw_list.hh"
#include "stk/ui/ui.hh"

namespace stk::ui {

nlohmann::ordered_json draw_cmd_to_json(const DrawCmd &cmd);
/** {"window", "scale", "unit", "blocks": [{name, kind, rect, frame, widgets: [{key, type, rect}]}], "draw": [...]} */
std::string dump_frame(const Context &ctx);

}  // namespace stk::ui
