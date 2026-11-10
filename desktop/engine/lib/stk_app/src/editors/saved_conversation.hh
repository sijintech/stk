/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <string>

#include "stk/io/json.hh"

namespace stk::app {
class Editor;
class ProjectState;

/** Check a live AI editor before revealing it for an exact saved exchange. */
bool can_reveal_saved_conversation(const Editor &editor, const ProjectState &project);
/** Discussion selection is shared, so another active AI editor may also react to it. */
bool saved_conversation_dispatch_safe(const Editor &editor, ProjectState &project, const std::string &request_id);
/** Select the saved exchange for display, preserving the editor's compose draft. */
bool reveal_saved_conversation(Editor &editor, ProjectState &project, const std::string &request_id);
/** Select a saved agent session for display without starting a turn. */
bool reveal_saved_agent_session(Editor &editor, ProjectState &project, const std::string &session_id);
/** One readable line from the saved session summary. */
std::string agent_session_label(const io::Json &session);
}  // namespace stk::app
