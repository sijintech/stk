/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/ui/form.hh"

namespace stk::ui {
/** Editor for the normalized opacity pairs of x-stk-widget: transfer_function. */
void build_transfer_function(Layout &layout, const SchemaNode &node, FormModel &model,
                             std::string_view label, std::string_view tooltip);
}
