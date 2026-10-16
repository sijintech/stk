/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_file_tree.hh"
#include <algorithm>
#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"

namespace stk::app {
using io::Json;
ProjectFileTree::ProjectFileTree(AppStore &store, std::function<bool()> owner_valid)
    : store_(store), project_(store.project()), owner_valid_(std::move(owner_valid)) {}
ProjectFileTree::~ProjectFileTree() { *alive_ = false; if (future_) { future_->cancel(); } }
void ProjectFileTree::changed() { ++version_; if (!owner_valid_ || owner_valid_()) { store_.changed(); } }
void ProjectFileTree::clear()
{
  ++epoch_;
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
  pages_.clear(); expanded_ = {""}; selected_ = nullptr; workspace_selection_ = nullptr; error_.clear(); changed();
}
io::Json ProjectFileTree::save_workspace_state() const
{
  if (!workspace_pending_.is_null()) { return workspace_pending_; }
  return {{"version", 1}, {"project", workspace_project_},
    {"expanded", expanded_}, {"selection", {{"path", io::get_string(selected_, "path")},
      {"record_id", io::get_bool(selected_, "index_only", false) ? io::get_string(selected_, "id") : std::string()}}}};
}
bool ProjectFileTree::check_workspace_state(const Json &value)
{
  const auto relative = [](const Json &item) {
    if (!item.is_string()) { return false; }
    const auto path = item.get<std::string>();
    if (path.size() > 4096 || path.find('\\') != std::string::npos || path.find('\0') != std::string::npos ||
        (!path.empty() && (path.front() == '/' || path.back() == '/'))) { return false; }
    size_t offset = 0;
    while (offset < path.size()) {
      const auto end = path.find('/', offset); const auto part = path.substr(offset, end - offset);
      if (std::any_of(part.begin(), part.end(), [](const unsigned char ch) { return ch < 32 || ch == 127; }) || part.empty() || part == "." || part == ".." || part.front() == '.' || part.find(':') != std::string::npos) { return false; }
      if (end == std::string::npos) { break; } offset = end + 1;
    }
    return true;
  };
  if (!value.is_object() || value.size() != 4 || value.value("version", Json()) != 1 ||
      !value.contains("project") || !value.at("project").is_string() || value.at("project").get_ref<const std::string &>().size() > 64 ||
      !value.contains("expanded") || !value.at("expanded").is_array() || value.at("expanded").size() > 64 ||
      !value.contains("selection") || !value.at("selection").is_object()) { return false; }
  if (!std::all_of(value.at("expanded").begin(), value.at("expanded").end(), relative)) { return false; }
  const auto &selection = value.at("selection");
  return selection.size() == 2 && selection.contains("path") && relative(selection.at("path")) &&
      selection.contains("record_id") && selection.at("record_id").is_string() &&
      selection.at("record_id").get_ref<const std::string &>().size() <= 64;
}
bool ProjectFileTree::load_workspace_state(const Json &value)
{
  if (!check_workspace_state(value)) { return false; }
  workspace_pending_ = value; return true;
}
void ProjectFileTree::sync()
{
  if (owner_valid_ && !owner_valid_()) { return; }
  auto *client = store_.bridge();
  const auto handle = project_.project() ? project_.project()->handle : std::string();
  const auto revision = project_.project() ? project_.project()->revision : -1;
  const auto session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_ || handle != handle_ || revision != revision_) {
    client_ = client; session_ = session; handle_ = handle; revision_ = revision;
    workspace_project_ = project_.project() ? project_.project()->id : std::string();
    clear();
  }
  if (!workspace_pending_.is_null() && supported() && project_.project() &&
      io::get_string(workspace_pending_, "project") == project_.project()->id) {
    expanded_ = workspace_pending_.at("expanded").get<std::set<std::string>>(); expanded_.insert("");
    workspace_selection_ = workspace_pending_.at("selection"); workspace_pending_ = nullptr;
  }
  if (supported() && !busy() && !workspace_selection_.is_null()) {
    for (const auto &path : expanded_) {
      if (!pages_.count(path)) { load(path, 0); return; }
    }
    const auto selection = std::move(workspace_selection_); workspace_selection_ = nullptr;
    const auto record = io::get_string(selection, "record_id"), path = io::get_string(selection, "path");
    if (!record.empty()) { select_record(record); }
    else {
      for (const auto &[parent, page] : pages_) {
        (void)parent;
        for (const auto &entry : page.at("entries")) {
          if (io::get_string(entry, "path") == path) { select(entry); return; }
        }
      }
    }
  }
}
bool ProjectFileTree::supported() const
{
  if (owner_valid_ && !owner_valid_()) { return false; }
  if (!client_) { return false; }
  const auto hello = client_->hello_info();
  return !handle_.empty() && project_.loaded() && project_.ready() && hello &&
      hello->has_method("project.files.children") && hello->has_method("project.files.resolve_path");
}
bool ProjectFileTree::refresh()
{
  sync();
  if (!supported() || busy()) { return false; }
  clear(); return load("", 0);
}
bool ProjectFileTree::load(const std::string &path, const int offset)
{
  if (!supported() || busy() || offset < 0 || offset > 4096) { return false; }
  if (!pages_.count(path) && pages_.size() >= 64) {
    error_ = "Directory browser limit reached (64); refresh to release retained directories";
    changed(); return false;
  }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  error_.clear();
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  future_ = client_->call("project.files.children", {{"handle", handle_}, {"expected_revision", revision_},
      {"path", path}, {"offset", offset}, {"limit", 200}}, options);
  future_->then([this, weak, epoch, path, offset](bridge::Result<Json> result) {
    const auto live = weak.lock(); if (!live || !*live || (owner_valid_ && !owner_valid_())) { return; }
    sync(); if (epoch != epoch_) { return; }
    future_.reset();
    if (!result) { error_ = result.error().describe(); workspace_selection_ = nullptr; }
    else if (io::get_int(result.value(), "revision", -1) != revision_ ||
             io::get_string(result.value(), "directory") != path || !result.value().contains("entries") ||
             !result.value().at("entries").is_array()) { error_ = "Invalid directory response"; }
    else {
      auto page = result.value();
      size_t retained = 0;
      for (const auto &[name, existing] : pages_) {
        if (name != path || offset) { retained += existing.at("entries").size(); }
      }
      if (retained + page.at("entries").size() > 8192) {
        error_ = "Directory browser entry budget exceeded (8192); refresh to close other directories";
        changed(); return;
      }
      if (offset && pages_.count(path)) {
        auto entries = pages_.at(path).at("entries");
        for (const auto &entry : page.at("entries")) { entries.push_back(entry); }
        page["entries"] = std::move(entries);
      }
      pages_[path] = std::move(page);
    }
    changed();
  });
  changed(); return true;
}
bool ProjectFileTree::toggle(const std::string &path)
{
  sync(); if (!supported() || busy()) { return false; }
  if (expanded_.erase(path)) { changed(); return true; }
  if (expanded_.size() >= 64) { error_ = "Directory expansion limit reached (64)"; changed(); return false; }
  expanded_.insert(path);
  changed(); return pages_.count(path) || load(path, 0);
}
bool ProjectFileTree::more(const std::string &path)
{
  sync(); const auto found = pages_.find(path);
  if (found == pages_.end() || !found->second.contains("next_offset") || !found->second.at("next_offset").is_number_integer()) { return false; }
  return load(path, int(io::get_int(found->second, "next_offset", -1)));
}
void ProjectFileTree::select(Json item) { selected_ = std::move(item); changed(); }
bool ProjectFileTree::select_record(const std::string &id)
{
  sync();
  if (!supported()) { return false; }
  const auto &index = project_.file_index();
  if (!index.is_object() || !index.contains("fields")) { return false; }
  for (const auto &table : project_.tables()) {
    if (table.id != io::get_string(index, "table_id")) { continue; }
    for (size_t row = 0; row < table.records.size(); ++row) {
      if (table.records[row].id != id) { continue; }
      Json item = {{"id", id}, {"index_only", true}};
      for (const auto *name : {"name", "path", "location", "kind", "state"}) {
        const auto field = io::get_string(index.at("fields"), name);
        item[name] = nullptr;
        for (size_t column = 0; column < table.fields.size(); ++column) {
          if (table.fields[column].id == field) {
            if (const auto *value = table.cell(int(row), int(column))) { item[name] = *value; }
          }
        }
      }
      select(std::move(item)); return true;
    }
  }
  return false;
}
bool ProjectFileTree::resolve(std::function<void(const std::string &)> complete)
{
  sync(); if (!supported() || busy() || !selected_.is_object()) { return false; }
  const bool registered = io::get_bool(selected_, "index_only", false);
  const auto id = io::get_string(selected_, "id"), path = io::get_string(selected_, "path");
  Json params = {{"handle", handle_}, {"expected_revision", revision_}};
  params[registered ? "record_id" : "path"] = registered ? id : path;
  const auto epoch = epoch_;
  const auto selection = selected_;
  const std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  future_ = client_->call(registered ? "project.files.resolve" : "project.files.resolve_path", params, options);
  future_->then([this, weak, epoch, selection, complete = std::move(complete)](bridge::Result<Json> result) {
    const auto live = weak.lock(); if (!live || !*live || (owner_valid_ && !owner_valid_())) { return; }
    sync(); if (epoch != epoch_) { return; }
    future_.reset();
    if (!result) { error_ = result.error().describe(); }
    else if (!project_.busy() && selection == selected_ && io::get_int(result.value(), "revision", -1) == revision_) {
      complete(io::get_string(result.value(), "path"));
    }
    changed();
  });
  changed(); return true;
}
}  // namespace stk::app
