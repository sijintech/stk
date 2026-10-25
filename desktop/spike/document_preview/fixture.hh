/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "document_resources.hh"

namespace stk::document_preview {

/** Synthetic, memory-only native-preview acceptance assets. Each call has its own session.
 * This is neither a Markdown renderer nor a product report/PDF reader.
 */
std::shared_ptr<ResourceSession> make_fixture(std::string &error);

}  // namespace stk::document_preview
