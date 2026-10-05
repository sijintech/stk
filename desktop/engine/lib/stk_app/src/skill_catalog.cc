/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/skill_catalog.hh"

#include "stk/app/app_store.hh"
#include "stk/bridge/client.hh"

#include <algorithm>
#include <utility>

namespace stk::app {
namespace {

std::string bridge_session(const bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}

}  // namespace

std::string skill_text(const io::Json &text, const std::string &language)
{
  if (text.is_string()) { return text.get<std::string>(); }
  const std::string key = language.rfind("zh", 0) == 0 ? "zh_CN" : "en";
  const auto local = io::get_string(text, key);
  return local.empty() ? io::get_string(text, "en") : local;
}

std::vector<SkillSummary> parse_skill_summaries(const io::Json &result)
{
  std::vector<SkillSummary> rows;
  const auto found = result.is_object() ? result.find("skills") : result.end();
  if (!result.is_object() || found == result.end() || !found->is_array()) { return rows; }
  for (const auto &item : *found) {
    SkillSummary row;
    row.id = io::get_string(item, "id");
    row.version = io::get_int(item, "version", 0);
    row.ref = io::get_string(item, "ref");
    if (row.id.empty() || row.version < 1 || row.ref.empty()) { continue; }
    row.content_sha256 = io::get_string(item, "content_sha256");
    if (item.contains("entry")) {
      row.entry_kind = io::get_string(item.at("entry"), "kind");
      row.preset = io::get_string(item.at("entry"), "preset");
    }
    row.title = item.contains("title") ? item.at("title") : io::Json(row.id);
    row.summary = item.contains("summary") ? item.at("summary") : io::Json::object();
    if (item.contains("availability") && item.at("availability").is_object()) {
      const auto &availability = item.at("availability");
      row.status = io::get_string(availability, "status");
      const auto outputs = availability.find("unavailable_outputs");
      if (outputs != availability.end() && outputs->is_array()) {
        for (const auto &name : *outputs) {
          if (name.is_string()) { row.unavailable_outputs.push_back(name.get<std::string>()); }
        }
      }
      const auto issues = availability.find("issues");
      row.issue_count = issues != availability.end() && issues->is_array() ? issues->size() : 0;
    }
    rows.push_back(std::move(row));
  }
  return rows;
}

SkillCatalogState::SkillCatalogState(AppStore &store) : store_(store) {}

SkillCatalogState::~SkillCatalogState()
{
  *alive_ = false;
  auto list = std::move(list_future_), detail = std::move(detail_future_);
  if (list) { list->cancel(); }
  if (detail) { detail->cancel(); }
}

void SkillCatalogState::clear()
{
  ++list_request_;
  ++detail_request_;
  auto list = std::move(list_future_), detail = std::move(detail_future_);
  list_future_.reset();
  detail_future_.reset();
  if (list) { list->cancel(); }
  if (detail) { detail->cancel(); }
  loaded_ = requested_ = false;
  error_.clear();
  detail_error_.clear();
  selected_.clear();
  selected_id_.clear();
  selected_version_ = 0;
  offset_ = total_ = problem_count_ = 0;
  next_offset_.reset();
  skills_.clear();
  problems_ = io::Json::array();
  detail_ = nullptr;
}

void SkillCatalogState::sync()
{
  auto *client = store_.bridge();
  const auto session = bridge_session(client);
  if (client == client_ && session == session_) { return; }
  // Another bridge (or the same one restarted) may serve another catalog: start again, keeping
  // only the query the user typed.
  client_ = client;
  session_ = session;
  clear();
}

bool SkillCatalogState::bridge_ready() const
{
  return client_ && client_->state() == bridge::BridgeState::Ready && client_->hello_info().has_value();
}

bool SkillCatalogState::supported() const
{
  if (!bridge_ready()) { return false; }
  const auto hello = client_->hello_info();
  return hello->has_method("skills.list") && hello->has_method("skills.get");
}

bool SkillCatalogState::ensure_loaded()
{
  sync();
  if (requested_ || !supported()) { return false; }
  return load(0, query_);
}

bool SkillCatalogState::refresh()
{
  sync();
  if (!supported()) { return false; }
  // Reload the shown definition too: availability follows the bridge's environment.
  if (!selected_.empty()) { load_detail(); }
  return load(offset_, query_);
}

bool SkillCatalogState::search(const std::string &query)
{
  sync();
  if (!supported()) { return false; }
  // At most kMaxQuery bytes (so also characters), never splitting a UTF-8 sequence.
  size_t end = std::min(query.size(), kMaxQuery);
  while (end < query.size() && end > 0 && (static_cast<unsigned char>(query[end]) & 0xC0) == 0x80) { --end; }
  return load(0, query.substr(0, end));
}

bool SkillCatalogState::next_page()
{
  sync();
  if (!supported() || !next_offset_) { return false; }
  return load(*next_offset_, query_);
}

bool SkillCatalogState::previous_page()
{
  sync();
  if (!supported() || offset_ == 0) { return false; }
  return load(std::max<int64_t>(0, offset_ - kPageSize), query_);
}

bool SkillCatalogState::select(const std::string &ref)
{
  sync();
  const auto row = std::find_if(skills_.begin(), skills_.end(), [&](const SkillSummary &item) { return item.ref == ref; });
  if (row == skills_.end() || !supported()) { return false; }
  if (ref == selected_ && (!detail_.is_null() || detail_future_)) { return false; }
  selected_ = ref;
  selected_id_ = row->id;
  selected_version_ = row->version;
  detail_ = nullptr;
  detail_error_.clear();
  return load_detail();
}

bool SkillCatalogState::load(const int64_t offset, std::string query)
{
  requested_ = true;
  const auto request = ++list_request_;
  if (list_future_) { auto old = std::move(list_future_); list_future_.reset(); old->cancel(); }
  io::Json params = {{"offset", offset}, {"limit", kPageSize}};
  if (!query.empty()) { params["query"] = query; }
  auto *client = client_;
  const auto session = session_;
  const std::weak_ptr<bool> weak = alive_;
  list_future_ = client->call("skills.list", params);
  list_future_->then([this, weak, request, client, session, offset, query = std::move(query)](bridge::Result<io::Json> result) {
    const auto live = weak.lock();
    if (!live || !*live || request != list_request_) { return; }
    if (store_.bridge() != client || client_ != client || bridge_session(client) != session || session_ != session) {
      // Answered by another bridge than the current one: never apply it, and do not wait for it.
      clear();
      store_.changed();
      return;
    }
    list_future_.reset();
    if (!result) { error_ = result.error().describe(); }
    else {
      const auto &value = result.value();
      error_.clear();
      loaded_ = true;
      query_ = query;
      offset_ = offset;
      skills_ = parse_skill_summaries(value);
      total_ = io::get_int(value, "total", int64_t(skills_.size()));
      const auto next = value.find("next_offset");
      next_offset_.reset();
      if (next != value.end() && next->is_number_integer()) { next_offset_ = next->get<int64_t>(); }
      const auto problems = value.find("problems");
      problems_ = problems != value.end() && problems->is_array() ? *problems : io::Json::array();
      problem_count_ = io::get_int(value, "problem_count", int64_t(problems_.size()));
    }
    store_.changed();
  });
  store_.changed();
  return true;
}

bool SkillCatalogState::load_detail()
{
  const auto request = ++detail_request_;
  if (detail_future_) { auto old = std::move(detail_future_); detail_future_.reset(); old->cancel(); }
  auto *client = client_;
  const auto session = session_;
  const auto ref = selected_;
  const std::weak_ptr<bool> weak = alive_;
  detail_future_ = client->call("skills.get", {{"id", selected_id_}, {"version", selected_version_}});
  detail_future_->then([this, weak, request, client, session, ref](bridge::Result<io::Json> result) {
    const auto live = weak.lock();
    if (!live || !*live || request != detail_request_ || selected_ != ref) { return; }
    if (store_.bridge() != client || client_ != client || bridge_session(client) != session || session_ != session) {
      clear();
      store_.changed();
      return;
    }
    detail_future_.reset();
    if (!result) {
      detail_error_ = result.error().describe();
    }
    else if (const auto &value = result.value(); !value.is_object() || !value.contains("skill") ||
             !value.at("skill").is_object() || io::get_string(value.at("skill"), "ref") != ref) {
      detail_error_ = "The bridge returned another skill than " + ref;
    }
    else {
      detail_error_.clear();
      detail_ = value.at("skill");
    }
    store_.changed();
  });
  store_.changed();
  return true;
}

}  // namespace stk::app
