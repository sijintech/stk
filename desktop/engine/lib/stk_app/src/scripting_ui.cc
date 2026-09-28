/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Explicit Python → local UI operations, always dispatched on the client's main-loop executor. */
#include "stk/app/shell.hh"

#include <algorithm>
#include <chrono>

#include "stk/app/project_state.hh"

namespace stk::app {
namespace {
using io::Json;
using bridge::Error;
using bridge::ErrorCode;

bool expired(const int64_t expires_at)
{
  const auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::system_clock::now().time_since_epoch()).count();
  return expires_at <= now;
}

Json project_json(const bridge::ProjectInfo &p)
{
  return {{"handle", p.handle}, {"id", p.id}, {"name", p.name}, {"directory", p.directory},
          {"revision", p.revision}, {"format_version", p.format_version}};
}

}  // namespace

void AppShell::handle_ui_request(const std::string &operation, const Json &params, const int64_t expires_at,
                                 std::function<bool()> valid, ScriptState::Completion complete)
{
  if (screens_.empty()) {
    complete(Error::make(ErrorCode::Unavailable, "No desktop screen is open"));
    return;
  }
  wm::Screen *screen = screens_.front(); /* First installed window is the explicit local target. */
  std::weak_ptr<bool> weak = alive_;
  screen->defer([this, weak, screen, operation, params, expires_at, valid = std::move(valid),
                 complete = std::move(complete)]() mutable {
    if (!weak.lock() || !valid()) {
      return;
    }
    if (std::find(screens_.begin(), screens_.end(), screen) == screens_.end()) {
      complete(Error::make(ErrorCode::Unavailable, "The target desktop screen was closed"));
      return;
    }
    if (expired(expires_at)) {
      complete(Error::make(ErrorCode::Timeout, "The desktop request expired before execution"));
      return;
    }
    try {
      perform_ui_request(*screen, operation, params, complete);
    }
    catch (const std::exception &error) {
      complete(Error::make(ErrorCode::InvalidParams, error.what()));
    }
  });
}

void AppShell::perform_ui_request(wm::Screen &screen, const std::string &operation, const Json &params,
                                  ScriptState::Completion complete)
{
  if (operation.rfind("viewer.", 0) == 0) {
    perform_viewer_request(screen, operation, params, std::move(complete));
    return;
  }
  const bool layout = operation == "layout.apply", open = operation == "project.open";
  if (!params.is_object() || (!layout && !open && !params.empty()) ||
      (layout && (params.size() != 1 || !params.contains("layout") || !params["layout"].is_object())) ||
      (open && (params.size() != 1 || !params.contains("directory") || !params["directory"].is_string())))
  {
    complete(Error::make(ErrorCode::InvalidParams, "Invalid parameters for " + operation));
    return;
  }
  if (operation == "layout.get") {
    complete(Json{{"layout", wm::layout_to_json(capture_layout(screen, window_))}});
  }
  else if (layout) {
    wm::LayoutFile file;
    std::string error;
    if (params["layout"].dump().size() > wm::kLayoutMaxBytes ||
        !wm::layout_from_json(params["layout"], file, &error)) {
      complete(Error::make(ErrorCode::InvalidParams, error.empty() ? "Layout exceeds 1 MiB" : error));
      return;
    }
    const auto languages = store_.catalog().languages();
    if (!file.language.empty() && std::find(languages.begin(), languages.end(), file.language) == languages.end()) {
      complete(Error::make(ErrorCode::InvalidParams, "Layout requests an unavailable language"));
      return;
    }
    if (!apply_layout(screen, file, &error)) {
      complete(Error::make(ErrorCode::InvalidParams, error));
      return;
    }
    complete(Json{{"applied", true}});
  }
  else if (operation == "editors.list") {
    Json editors = Json::array();
    for (const auto &type : registry_.types()) {
      editors.push_back({{"id", type->id}, {"label", std::string(store_.tr(type->title_key))}});
    }
    complete(Json{{"editors", editors}});
  }
  else if (operation == "project.current") {
    auto &project = store_.project();
    project.sync();
    complete(Json{{"project", project.project() && !project.project()->handle.empty() ?
                                  project_json(*project.project()) : Json(nullptr)}});
  }
  else if (open) {
    auto &project = store_.project();
    project.sync();
    if (!project.open(params["directory"].get<std::string>(), [complete](const auto &result) {
      if (result.ok()) { complete(Json{{"project", project_json(result.value())}}); }
      else { complete(result.error()); }
    })) {
      complete(Error::make(project.ready() ? ErrorCode::Busy : ErrorCode::Unavailable,
                           "The project controller cannot open a project right now"));
    }
  }
  else if (operation == "project.close") {
    auto &project = store_.project();
    project.sync();
    if (project.busy()) {
      complete(Error::make(ErrorCode::Busy, "The project controller is busy"));
    }
    else if (!project.project()) {
      complete(Json{{"closed", false}});
    }
    else if (!project.close([complete](const auto &result) {
      if (result.ok()) { complete(Json{{"closed", result.value()}}); }
      else { complete(result.error()); }
    })) {
      complete(Error::make(ErrorCode::Unavailable, "The project controller cannot close right now"));
    }
  }
  else {
    complete(Error::make(ErrorCode::Unsupported, "Unknown desktop operation " + operation));
  }
}

}  // namespace stk::app
