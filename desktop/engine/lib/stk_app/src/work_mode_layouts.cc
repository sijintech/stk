/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/shell.hh"
#include "stk/app/editor_area.hh"

#include <algorithm>
#include <set>
#include <stdexcept>

namespace stk::app {
namespace {
using Json = nlohmann::json;
using WorkMode = AppShell::WorkMode;

const char *mode_name(WorkMode mode)
{
  switch (mode) {
    case WorkMode::Preparation: return "preparation";
    case WorkMode::Analysis: return "analysis";
    case WorkMode::Report: return "report";
  }
  throw std::runtime_error("Unknown work mode");
}

WorkMode parse_mode(const Json &value)
{
  if (value == "preparation") { return WorkMode::Preparation; }
  if (value == "analysis") { return WorkMode::Analysis; }
  if (value == "report") { return WorkMode::Report; }
  throw std::runtime_error("Unknown work mode");
}

void keys(const Json &value, std::initializer_list<const char *> required)
{
  if (!value.is_object() || value.size() != required.size()) {
    throw std::runtime_error("Invalid work mode preferences");
  }
  for (const auto *key : required) {
    if (!value.contains(key)) { throw std::runtime_error("Missing work mode preference"); }
  }
}
}  // namespace

AppShell::WorkMode AppShell::work_mode(const wm::Screen &screen) const
{
  const auto found = work_modes_.find(&screen);
  return found == work_modes_.end() ? WorkMode::Analysis : found->second.active;
}

AppShell::WorkModeLayout AppShell::capture_work_mode(const wm::Screen &screen) const
{
  WorkModeLayout result{screen.arrangement(), {}};
  for (auto *base : screen.areas()) {
    if (const auto *area = dynamic_cast<EditorArea *>(base)) {
      result.panes.push_back({area->id(), area->editor().lifetime(), area->toolbar_open(), area->sidebar_open()});
    }
  }
  return result;
}

AppShell::WorkModeLayout AppShell::adapt_work_mode(const wm::Screen &screen, const WorkModeLayout &saved) const
{
  // Areas and tabs belong to the window, not to a mode. Adding/removing an area rebases an old
  // arrangement on the current split tree; never recreate a closed area or discard a new draft.
  auto result = capture_work_mode(screen);
  if (screen.check_arrangement(saved.geometry)) { result.geometry = saved.geometry; }
  for (auto &pane : result.panes) {
    const auto old = std::find_if(saved.panes.begin(), saved.panes.end(),
        [&](const auto &item) { return item.area == pane.area; });
    if (old != saved.panes.end()) {
      pane.toolbar = old->toolbar;
      pane.sidebar = old->sidebar;
    }
  }
  // Match live instances rather than indices/types: tabs can move, close, or have duplicate types.
  for (const auto &old : saved.panes) {
    const auto identity = old.editor.lock();
    if (!identity) { continue; }
    for (auto &pane : result.panes) {
      const auto *area = dynamic_cast<EditorArea *>(screen.find_area(pane.area));
      for (int index = 0; index < area->tab_count(); ++index) {
        if (area->tab(index).lifetime().lock() == identity) { pane.editor = old.editor; break; }
      }
    }
  }
  return result;
}

bridge::Result<io::Json> AppShell::switch_work_mode(wm::Screen *screen, WorkMode mode)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (!has_screen(screen)) {
    return Error::make(ErrorCode::Unavailable, std::string(store_.tr("app.focus.closed")));
  }
  if (screen->capture() != wm::Screen::Capture::None || (screen->ui() && screen->ui()->text_input_active())) {
    return Error::make(ErrorCode::Busy, std::string(store_.tr("app.focus.busy")));
  }
  const auto previous = work_mode(*screen);
  if (previous == mode) { return io::Json{{"mode", mode_name(mode)}, {"changed", false}}; }
  auto leaving = capture_work_mode(*screen);
  auto &modes = work_modes_[screen];
  const auto found = modes.layouts.find(mode);
  if (found != modes.layouts.end()) {
    auto target = adapt_work_mode(*screen, found->second);
    std::string error;
    if (!screen->rearrange(target.geometry, &error)) {
      return Error::make(ErrorCode::InvalidParams, error);
    }
    for (const auto &pane : target.panes) {
      auto *area = dynamic_cast<EditorArea *>(screen->find_area(pane.area));
      for (int index = 0; index < area->tab_count(); ++index) {
        if (area->tab(index).lifetime().lock() == pane.editor.lock()) { area->set_active_tab(index); break; }
      }
      area->set_toolbar_open(pane.toolbar);
      area->set_sidebar_open(pane.sidebar);
    }
  }
  else {
    const char *editor = mode == WorkMode::Preparation ? kEditorAI :
        mode == WorkMode::Report ? kEditorReports : kEditorViewer;
    const auto activated = activate_editor(screen, editor, false);
    if (!activated) { return activated.error(); }
    auto *area = screen->find_area(activated.value().at("area_id").get<std::string>());
    // The initial mode keeps the other panes visible and gives the main editor most of its row.
    if (auto *parent = area->node()->parent; parent && parent->children.size() > 1) {
      for (const auto &child : parent->children) {
        child->factor = child.get() == area->node() ? 0.65f : 0.35f / float(parent->children.size() - 1);
      }
    }
  }
  modes.layouts[previous] = std::move(leaving);
  modes.active = mode;
  screen->tag_redraw();
  return io::Json{{"mode", mode_name(mode)}, {"changed", true}};
}

Json AppShell::capture_work_modes(const wm::Screen &screen) const
{
  WorkModes modes;
  if (const auto found = work_modes_.find(&screen); found != work_modes_.end()) { modes = found->second; }
  modes.layouts[modes.active] = capture_work_mode(screen);
  Json layouts = Json::object();
  for (const auto &[mode, saved] : modes.layouts) {
    auto layout = adapt_work_mode(screen, saved);
    Json panes = Json::array();
    for (const auto &pane : layout.panes) {
      const auto *area = dynamic_cast<EditorArea *>(screen.find_area(pane.area));
      for (int index = 0; index < area->tab_count(); ++index) {
        if (area->tab(index).lifetime().lock() != pane.editor.lock()) { continue; }
        panes.push_back({{"area", pane.area}, {"tab", index}, {"type", area->tab(index).type().id},
                         {"toolbar", pane.toolbar}, {"sidebar", pane.sidebar}});
        break;
      }
    }
    layouts[mode_name(mode)] = {{"geometry", std::move(layout.geometry)}, {"panes", std::move(panes)}};
  }
  return {{"version", 1}, {"active", mode_name(modes.active)}, {"layouts", std::move(layouts)}};
}

bool AppShell::read_work_modes(const wm::Screen &screen, const Json &layout, WorkModes &modes, std::string *error) const
{
  try {
    WorkModes candidate;
    if (!layout.contains("work_modes")) { modes = std::move(candidate); return true; }
    const auto &raw = layout.at("work_modes");
    keys(raw, {"version", "active", "layouts"});
    if (!raw.at("version").is_number_integer() || raw.at("version") != 1 || raw.dump().size() > 256 * 1024) {
      throw std::runtime_error("Unsupported or oversized work mode preferences");
    }
    candidate.active = parse_mode(raw.at("active"));
    const auto &layouts = raw.at("layouts");
    if (!layouts.is_object() || layouts.empty() || layouts.size() > 3 || !layouts.contains(mode_name(candidate.active))) {
      throw std::runtime_error("Invalid work mode layouts");
    }
    for (auto item = layouts.begin(); item != layouts.end(); ++item) {
      const auto mode = parse_mode(item.key());
      const auto &value = item.value();
      keys(value, {"geometry", "panes"});
      std::string reason;
      if (!screen.check_arrangement(value.at("geometry"), &reason)) { throw std::runtime_error(reason); }
      const auto &panes = value.at("panes");
      if (!panes.is_array() || panes.size() > 64) { throw std::runtime_error("Invalid work mode panes"); }
      WorkModeLayout parsed{value.at("geometry"), {}};
      std::set<std::string> seen;
      for (const auto &pane : panes) {
        keys(pane, {"area", "tab", "type", "toolbar", "sidebar"});
        const auto id = pane.at("area").get<std::string>();
        const auto *area = dynamic_cast<EditorArea *>(screen.find_area(id));
        const auto &tab = pane.at("tab");
        if (!area || !seen.insert(id).second || !tab.is_number_integer() || tab < 0 || tab >= area->tab_count() ||
            !pane.at("toolbar").is_boolean() || !pane.at("sidebar").is_boolean()) {
          throw std::runtime_error("Invalid work mode pane target");
        }
        const auto &editor = area->tab(tab.get<int>());
        if (pane.at("type") != editor.type().id) { throw std::runtime_error("Work mode tab type mismatch"); }
        parsed.panes.push_back({id, editor.lifetime(), pane.at("toolbar").get<bool>(), pane.at("sidebar").get<bool>()});
      }
      candidate.layouts.emplace(mode, std::move(parsed));
    }
    modes = std::move(candidate);
    return true;
  }
  catch (const std::exception &e) {
    if (error) { *error = e.what(); }
    return false;
  }
}
}  // namespace stk::app
