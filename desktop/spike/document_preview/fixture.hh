/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/document/resources.hh"

namespace stk::document_preview {

/** Synthetic, memory-only native-preview acceptance assets. Each call has its own session.
 * This is neither a Markdown renderer nor a product report/PDF reader.
 */
std::shared_ptr<ResourceSession> make_fixture(std::string &error);
/** Complete two-page synthetic PDF bytes; page-embedded RGB stripes identify both pages.
 * Shared by the standalone spike and the frozen production ReportsEditor acceptance.
 */
std::string make_pdf_fixture();

}  // namespace stk::document_preview
