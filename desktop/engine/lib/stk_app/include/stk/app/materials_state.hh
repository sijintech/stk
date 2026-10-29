/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"
#include "stk/ui/draw_list.hh"
#include <chrono>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace stk::app {
class AppStore;

/** Local material training RPCs. Each editor owns a View; no observer starts or recovers work. */
class MaterialsState {
 public:
  struct Pending;
  struct View {
    ~View();
    io::Json card, job, models, jobs = io::Json::array(), epochs = io::Json::array();
    std::string selected_job, error;
    int next_offset = -1;
    uint64_t version = 0, draft_epoch = 0, selection_epoch = 0, lifetime_epoch = 0, bridge_epoch = 0;
    bool loaded_jobs = false, loaded_models = false;
    bool busy() const { return pending.contains("write"); }
    bool reading() const { return !pending.empty(); }
   private:
    friend class MaterialsState;
    std::map<std::string, std::shared_ptr<Pending>> pending;
    std::chrono::steady_clock::time_point poll{};
  };
  using ViewPtr = std::shared_ptr<View>;

  explicit MaterialsState(AppStore &store);
  ~MaterialsState();
  ViewPtr new_view();
  void sync(const ViewPtr &view);
  bool supported() const;
  /** Cancel only this view's requests; never send training cancellation. Keeps its data and draft. */
  void detach(const ViewPtr &view);
  void invalidate_draft(const ViewPtr &view, bool dataset_changed = false);
  bool validate(const ViewPtr &view, const std::string &directory);
  bool prepare(const ViewPtr &view, io::Json params);
  bool select_job(const ViewPtr &view, const std::string &job_id);
  bool refresh(const ViewPtr &view);
  bool more_jobs(const ViewPtr &view);
  bool start(const ViewPtr &view);
  bool cancel(const ViewPtr &view);
  bool recover(const ViewPtr &view);
  bool activate(const ViewPtr &view, const std::string &kind, const std::string &version);

 private:
  using Apply = std::function<void(View &, const io::Json &)>;
  bool call(const ViewPtr &, const std::string &slot, const std::string &method, io::Json,
            Apply, bool draft = false, bool selection = false);
  bool read_job(const ViewPtr &);
  bool read_curves(const ViewPtr &);
  bool read_jobs(const ViewPtr &, int offset);
  bool read_models(const ViewPtr &);
  bool job_action(const ViewPtr &, const std::string &action);
  void follow_bridge();
  AppStore &store_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string session_;
  uint64_t epoch_ = 1, store_bridge_epoch_ = 0;
  std::vector<std::weak_ptr<View>> views_;
};

/** Data coordinates retain missing observations and both P-E branches; drawing never invents samples. */
struct MaterialsPlotPoint { double x = 0, y = 0; };
struct MaterialsPlotLine {
  std::string role;
  std::vector<std::vector<MaterialsPlotPoint>> segments;
};
struct MaterialsPlot {
  std::vector<MaterialsPlotLine> lines;
  double x_min = 0, x_max = 1, y_min = 0, y_max = 1;
};
MaterialsPlot materials_loss_plot(const io::Json &epochs);
MaterialsPlot materials_evaluation_plot(const io::Json &job, size_t sample);
}  // namespace stk::app
