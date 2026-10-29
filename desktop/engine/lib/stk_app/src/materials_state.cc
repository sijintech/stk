/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/materials_state.hh"
#include "stk/app/app_store.hh"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace stk::app {
using io::Json;
namespace {
std::string session(bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}
bool finite(const Json &value) { return value.is_number() && std::isfinite(value.get<double>()); }
void ranges(MaterialsPlot &plot)
{
  bool first = true;
  for (const auto &line : plot.lines) { for (const auto &segment : line.segments) { for (const auto point : segment) {
    if (first) { plot.x_min = plot.x_max = point.x; plot.y_min = plot.y_max = point.y; first = false; }
    else {
      plot.x_min = std::min(plot.x_min, double(point.x)); plot.x_max = std::max(plot.x_max, double(point.x));
      plot.y_min = std::min(plot.y_min, double(point.y)); plot.y_max = std::max(plot.y_max, double(point.y));
    }
  } } }
  if (plot.x_max == plot.x_min) { plot.x_max += 1; }
  if (plot.y_max == plot.y_min) {
    const double padding = std::max(1.0, std::abs(plot.y_min) * .05);
    const double low = plot.y_min - padding, high = plot.y_max + padding;
    if (std::isfinite(low)) { plot.y_min = low; }
    if (std::isfinite(high)) { plot.y_max = high; }
  }
}
}

struct MaterialsState::Pending { std::optional<bridge::Future<Json>> future; };
MaterialsState::View::~View()
{
  auto old = std::move(pending);
  for (auto &[key, request] : old) { if (request->future) { request->future->cancel(); } }
}
MaterialsState::MaterialsState(AppStore &store) : store_(store) {}
MaterialsState::~MaterialsState()
{
  *alive_ = false;
  for (const auto &weak : views_) { if (auto view = weak.lock()) { detach(view); } }
}
MaterialsState::ViewPtr MaterialsState::new_view()
{
  auto view = std::make_shared<View>(); views_.push_back(view); return view;
}
void MaterialsState::detach(const ViewPtr &view)
{
  ++view->lifetime_epoch;
  auto old = std::move(view->pending); view->pending.clear();
  for (auto &[key, request] : old) { if (request->future) { request->future->cancel(); } }
}
void MaterialsState::follow_bridge()
{
  auto *current = store_.bridge(); const auto identity = session(current);
  if (current == client_ && identity == session_ && store_.bridge_epoch() == store_bridge_epoch_) { return; }
  client_ = current; session_ = identity; store_bridge_epoch_ = store_.bridge_epoch(); ++epoch_;
  std::erase_if(views_, [](const auto &weak) { return weak.expired(); });
  for (const auto &weak : views_) { if (auto view = weak.lock()) {
    detach(view); ++view->version; ++view->draft_epoch; ++view->selection_epoch;
    view->bridge_epoch = epoch_; view->card = view->job = view->models = nullptr;
    view->jobs = view->epochs = Json::array(); view->error.clear(); view->next_offset = -1;
    view->loaded_jobs = view->loaded_models = false;
  } }
}
bool MaterialsState::supported() const
{
  const auto hello = client_ && !session_.empty() ? client_->hello_info() : std::nullopt;
  return hello && hello->has_method("materials.prepare") && hello->has_method("materials.start") &&
      hello->has_method("materials.jobs.list") && hello->has_method("materials.jobs.curves") &&
      hello->has_method("materials.models.list");
}
void MaterialsState::sync(const ViewPtr &view)
{
  follow_bridge();
  if (!supported() || view->busy()) { return; }
  if (!view->loaded_jobs && !view->pending.contains("jobs")) { read_jobs(view, 0); }
  if (!view->loaded_models && !view->pending.contains("models")) { read_models(view); }
  const auto now = std::chrono::steady_clock::now();
  if (!view->selected_job.empty() && !view->pending.contains("job") &&
      ((view->job.is_null() || io::get_string(view->job, "state") == "running") && now >= view->poll)) {
    read_job(view);
  }
}
bool MaterialsState::call(const ViewPtr &view, const std::string &slot, const std::string &method,
                          Json params, Apply apply, bool draft, bool selection)
{
  follow_bridge();
  if (!supported() || view->pending.contains(slot) || !client_->hello_info()->has_method(method) ||
      (slot != "write" && view->busy())) { return false; }
  if (slot == "write") {
    // A reply observed before this explicit mutation cannot overwrite its ACK.
    // In particular an old prepared job must not stop polling after Start says running.
    ++view->selection_epoch;
    auto old = std::move(view->pending); view->pending.clear();
    for (auto &[key, request] : old) { if (request->future) { request->future->cancel(); } }
    view->loaded_jobs = view->loaded_models = false;
  }
  const auto epoch = epoch_, lifetime = view->lifetime_epoch, source = view->draft_epoch,
             selected = view->selection_epoch, bridge_origin = store_.bridge_epoch();
  const auto request = std::make_shared<Pending>(); view->pending[slot] = request;
  const std::weak_ptr<View> weak = view;
  const std::weak_ptr<bool> alive = alive_;
  const std::weak_ptr<Pending> pending = request;
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  request->future = client_->call(method, std::move(params), options);
  request->future->then([this, alive, weak, pending, epoch, lifetime, source, selected, bridge_origin, slot,
                          apply = std::move(apply), draft, selection](bridge::Result<Json> result) {
    const auto live = alive.lock(); if (!live || !*live) { return; }
    const auto view = weak.lock(); const auto request = pending.lock();
    if (!view || !request || store_.bridge() != client_ || store_.bridge_epoch() != bridge_origin || session(store_.bridge()) != session_ ||
        epoch != epoch_ || lifetime != view->lifetime_epoch || !view->pending.contains(slot) ||
        view->pending.at(slot) != request) { return; }
    view->pending.erase(slot);
    if ((draft && source != view->draft_epoch) || (selection && selected != view->selection_epoch)) {
      ++view->version; store_.changed(); return;
    }
    if (!result) { view->error = result.error().message; }
    else {
      try { apply(*view, result.value()); view->error.clear(); }
      catch (const std::exception &) { view->error = "Invalid materials response"; }
    }
    ++view->version; store_.changed();
  });
  store_.changed(); return true;
}
void MaterialsState::invalidate_draft(const ViewPtr &view, const bool dataset_changed)
{
  ++view->draft_epoch; ++view->version;
  if (dataset_changed) { view->card = nullptr; }
}
bool MaterialsState::validate(const ViewPtr &view, const std::string &directory)
{
  return call(view, "validate", "materials.datasets.validate", {{"directory", directory}},
      [](View &v, const Json &reply) { v.card = reply.at("card"); }, true);
}
bool MaterialsState::prepare(const ViewPtr &view, Json params)
{
  const auto source = view->draft_epoch; follow_bridge();
  if (source != view->draft_epoch) { return false; }
  if (view->busy()) { return false; }
  return call(view, "write", "materials.prepare", std::move(params), [](View &v, const Json &reply) {
    v.job = reply.at("job"); v.selected_job = io::get_string(v.job, "id"); ++v.selection_epoch;
    v.epochs = Json::array(); v.loaded_jobs = false; v.card = v.job.value("card", Json());
  }, true);
}
bool MaterialsState::read_jobs(const ViewPtr &view, const int offset)
{
  view->loaded_jobs = true;
  return call(view, "jobs", "materials.jobs.list", {{"offset", offset}, {"limit", 50}},
      [offset](View &v, const Json &reply) {
        const auto &rows = reply.at("jobs"); if (!rows.is_array()) { throw std::invalid_argument("jobs"); }
        if (offset == 0) { v.jobs = Json::array(); }
        for (const auto &row : rows) {
          const auto id = io::get_string(row, "id");
          auto found = std::find_if(v.jobs.begin(), v.jobs.end(), [&](const auto &entry) { return io::get_string(entry, "id") == id; });
          if (found == v.jobs.end()) { v.jobs.push_back(row); } else { *found = row; }
        }
        const auto next = reply.value("next_offset", Json()); v.next_offset = next.is_number_integer() ? next.get<int>() : -1;
      });
}
bool MaterialsState::read_models(const ViewPtr &view)
{
  view->loaded_models = true;
  return call(view, "models", "materials.models.list", Json::object(),
      [](View &v, const Json &reply) { if (!reply.at("kinds").is_object()) { throw std::invalid_argument("models"); } v.models = reply; });
}
bool MaterialsState::refresh(const ViewPtr &view)
{
  follow_bridge(); if (view->busy()) { return false; }
  bool started = read_jobs(view, 0); started = read_models(view) || started;
  if (!view->selected_job.empty()) { started = read_job(view) || started; }
  return started;
}
bool MaterialsState::more_jobs(const ViewPtr &view)
{
  follow_bridge(); return view->next_offset >= 0 && read_jobs(view, view->next_offset);
}
bool MaterialsState::select_job(const ViewPtr &view, const std::string &job_id)
{
  if (view->busy()) { return false; }
  ++view->selection_epoch; view->selected_job = job_id; view->job = nullptr; view->epochs = Json::array();
  for (const auto slot : {"job", "curves"}) {
    auto found = view->pending.find(slot);
    if (found != view->pending.end()) { auto old = found->second; view->pending.erase(found); if (old->future) { old->future->cancel(); } }
  }
  return read_job(view);
}
bool MaterialsState::read_job(const ViewPtr &view)
{
  if (view->selected_job.empty()) { return false; }
  view->poll = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
  const std::weak_ptr<View> weak = view;
  return call(view, "job", "materials.jobs.get", {{"job_id", view->selected_job}},
      [this, weak](View &v, const Json &reply) {
        const auto job = reply.at("job"); if (io::get_string(job, "id") != v.selected_job) { throw std::invalid_argument("identity"); }
        const auto previous = io::get_string(v.job, "state");
        v.job = job;
        if (auto current = weak.lock()) { read_curves(current); }
        const auto state = io::get_string(job, "state");
        if (state != previous) { v.loaded_jobs = false; }
        if (state == "done") { v.loaded_models = false; }
      }, false, true);
}
bool MaterialsState::read_curves(const ViewPtr &view)
{
  if (view->selected_job.empty()) { return false; }
  const int64_t after = view->epochs.empty() ? 0 : io::get_int(view->epochs.back(), "epoch", 0);
  const std::weak_ptr<View> weak = view;
  return call(view, "curves", "materials.jobs.curves", {{"job_id", view->selected_job}, {"after", after}, {"limit", 1000}},
      [this, weak](View &v, const Json &reply) {
        if (io::get_string(reply, "id") != v.selected_job || !reply.at("curves").is_array()) { throw std::invalid_argument("curves"); }
        for (const auto &row : reply.at("curves")) {
          if (v.epochs.size() >= 5000) { break; }
          if (v.epochs.empty() || io::get_int(row, "epoch", 0) > io::get_int(v.epochs.back(), "epoch", 0)) { v.epochs.push_back(row); }
        }
        if (reply.value("next_after", Json()).is_number_integer()) { if (auto current = weak.lock()) { read_curves(current); } }
      }, false, true);
}
bool MaterialsState::job_action(const ViewPtr &view, const std::string &action)
{
  follow_bridge();
  if (view->busy() || view->selected_job.empty()) { return false; }
  const auto state = io::get_string(view->job, "state");
  if ((action == "start" && state != "prepared") || (action == "cancel" && state != "prepared" && state != "running") ||
      (action == "recover" && state != "running" && state != "uncertain")) { return false; }
  const std::weak_ptr<View> weak = view;
  const auto method = action == "start" ? "materials.start" : "materials.jobs." + action;
  return call(view, "write", method, {{"job_id", view->selected_job}}, [this, weak](View &v, const Json &reply) {
    if (io::get_string(reply.at("job"), "id") != v.selected_job) { throw std::invalid_argument("job"); }
    v.job = reply.at("job"); v.loaded_jobs = v.loaded_models = false; v.poll = {};
    if (auto current = weak.lock()) { read_curves(current); }
  }, false, true);
}
bool MaterialsState::start(const ViewPtr &view) { return job_action(view, "start"); }
bool MaterialsState::cancel(const ViewPtr &view) { return job_action(view, "cancel"); }
bool MaterialsState::recover(const ViewPtr &view) { return job_action(view, "recover"); }
bool MaterialsState::activate(const ViewPtr &view, const std::string &kind, const std::string &version)
{
  follow_bridge();
  if (view->busy() || !view->models.is_object() || !view->models.contains("kinds") ||
      !view->models.at("kinds").contains(kind)) { return false; }
  const auto &entry = view->models.at("kinds").at(kind);
  if (!entry.contains("versions") || !entry.at("versions").is_array() ||
      std::none_of(entry.at("versions").begin(), entry.at("versions").end(),
          [&](const auto &record) { return io::get_string(record, "version") == version; })) { return false; }
  return call(view, "write", "materials.models.activate", {{"kind", kind}, {"version", version}},
      [kind](View &v, const Json &reply) { v.models["kinds"][kind] = reply.at("entry"); v.loaded_models = false; });
}

MaterialsPlot materials_loss_plot(const Json &epochs)
{
  MaterialsPlot plot;
  if (!epochs.is_array()) { return plot; }
  for (const auto role : {"train_loss", "validation_loss"}) {
    MaterialsPlotLine line{role, {{}}};
    for (const auto &row : epochs) {
      if (row.is_object() && row.contains("epoch") && row.contains(role) && finite(row.at("epoch")) && finite(row.at(role))) {
        line.segments.back().push_back({row.at("epoch").get<double>(), row.at(role).get<double>()});
      }
    }
    if (!line.segments.back().empty()) { plot.lines.push_back(std::move(line)); }
  }
  ranges(plot); return plot;
}
MaterialsPlot materials_evaluation_plot(const Json &job, const size_t sample)
{
  MaterialsPlot plot;
  if (!job.is_object() || !job.contains("evaluation_preview") || !job.at("evaluation_preview").is_object()) { return plot; }
  const auto &preview = job.at("evaluation_preview");
  if (!preview.contains("samples") || !preview.at("samples").is_array() || sample >= preview.at("samples").size()) { return plot; }
  const auto &selected = preview.at("samples")[sample];
  const bool pe = io::get_string(job, "kind") == "pe_loop";
  const size_t count = pe ? 128 : 64, points = 64;
  for (const auto role : {"observed", "candidate", "base", "baseline"}) {
    if (!selected.contains(role) || !selected.at(role).is_array() || selected.at(role).size() != count) { continue; }
    const auto &values = selected.at(role);
    MaterialsPlotLine line{role, {{}}};
    for (size_t index = 0; index < count; ++index) {
      if (pe && index == points) { line.segments.emplace_back(); }
      if (!finite(values[index])) { if (!line.segments.back().empty()) { line.segments.emplace_back(); } continue; }
      const double unit = double(index % points) / double(points - 1);
      // stk.dataset/1 stores both up and down branches in increasing E/E_max.
      const double x = pe ? -1 + 2 * unit : 2000 * unit;
      line.segments.back().push_back({x, values[index].get<double>()});
    }
    std::erase_if(line.segments, [](const auto &segment) { return segment.empty(); });
    plot.lines.push_back(std::move(line));
  }
  ranges(plot); return plot;
}
}  // namespace stk::app
