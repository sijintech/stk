/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
/** Why a saved AI question cannot be sent now (docs/design/model-gateway.md): its endpoint is gone, the network
 * setting does not allow it, the Token Plan has no key, or the endpoint is external and the question's data is not
 * labelled public. The service checks the same before sending; the views explain it beforehand. */

#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/model_settings.hh"
#include "stk/app/project_data_labels.hh"
#include "stk/app/project_discussion.hh"

#include <string>

namespace stk::app {

/** A catalog key, or empty when the question may be sent. ``context`` is the question's saved context when
 * known (its table's label is checked for external endpoints), or nullptr to leave that check to the service. */
inline std::string send_blocked(EditorContext &ctx, ProjectDiscussion &discussion, const std::string &adapter,
                                const io::Json *context)
{
  auto &models = ctx.store.models();
  models.sync();
  if (!models.supported() || !models.loaded()) {
    // Older services know only the Token Plan provider.
    return discussion.provider().value("configured", false) && adapter == io::get_string(discussion.provider(), "adapter") ?
        std::string() : std::string("ai.missing_key");
  }
  const auto *target = models.by_adapter(adapter);
  if (!target) { return "ai.send.unknown_endpoint"; }
  if (!io::get_bool(*target, "allowed", true)) { return "ai.send.network"; }
  if (io::get_bool(*target, "builtin", false) && !discussion.provider().value("configured", false)) { return "ai.missing_key"; }
  if (context && io::get_string(*target, "location") == "external") {
    auto &labels = ctx.store.data_labels();
    labels.sync();
    const auto table = io::get_string(context->value("selection", io::Json::object()), "table_id");
    if (!labels.is_public("table", table)) { return "ai.send.private"; }
  }
  return {};
}

}  // namespace stk::app
