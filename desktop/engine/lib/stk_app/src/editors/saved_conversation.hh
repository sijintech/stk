/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <cstdint>
#include <string>

#include "stk/io/json.hh"

namespace stk::app {
class Editor;
class ProjectState;

/** Check a live AI editor before revealing it for an exact saved exchange. */
bool can_reveal_saved_conversation(const Editor &editor, const ProjectState &project);
enum class DeferredAgentStartCheck { Skip, Split, Focused };
/** Check for automatic discussion actions. Literature routes also check the Agent pane in the resulting layout. */
bool saved_conversation_dispatch_safe(const Editor &editor, ProjectState &project, const std::string &request_id,
                                      DeferredAgentStartCheck agent_start = DeferredAgentStartCheck::Skip);
/** Select the saved exchange for display, preserving the editor's compose draft. */
bool reveal_saved_conversation(Editor &editor, ProjectState &project, const std::string &request_id);
/** Show the existing paged question list in this AI editor. */
bool reveal_saved_question_history(Editor &editor, const ProjectState &project);
/** Bring the current project's unsent question into focus without changing its selected exchange. */
bool reveal_question_composer(Editor &editor, const ProjectState &project, uint64_t visibility);
/** Select a saved agent session for display without starting a turn. */
bool reveal_saved_agent_session(Editor &editor, ProjectState &project, const std::string &session_id);
/** One readable line from the saved session summary. */
std::string agent_session_label(const io::Json &session);
}  // namespace stk::app
