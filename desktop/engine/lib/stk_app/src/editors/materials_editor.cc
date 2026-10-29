/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/materials_state.hh"
#include "stk/app/shell.hh"
#include "stk/core/paths.hh"
#include "stk/ui/gpu_painter.hh"
#include "path_picker.hh"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <type_traits>

namespace stk::app {
namespace {
using io::Json;
std::string number(double value)
{
  std::ostringstream out; out << std::setprecision(5) << value; return out.str();
}
class MaterialsEditor final : public Editor {
 public:
  explicit MaterialsEditor(const EditorType &type) : Editor(type)
  {
    static uint64_t identity = 0; scope_ = "materials-instance-" + std::to_string(++identity);
  }
  bool has_sidebar() const override { return true; }
  bool draws_gpu() const override { return true; }
  ui::Color main_background(const ui::Theme &) const override { return {0, 0, 0, 0}; }
  bool has_unsaved_changes() const override
  {
    return dirty_ || (ui_ && ui_->edit_state() && fields_.contains(ui_->editing()));
  }
  void on_area_removed() override
  {
    const auto saved = save_state();
    directory_ = saved.value("directory", directory_); job_id_ = saved.value("job_id", job_id_);
    hidden_ = saved.value("hidden", hidden_);
    number_drafts_ = saved.value("number_drafts", std::map<std::string, std::string>());
    if (state_ && view_) { state_->detach(view_); }
    ui_ = nullptr; fields_.clear(); numeric_props_.clear(); ++generation_;
  }
  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    attach(ctx); const auto current = guard();
    row.button("materials_refresh", ctx.tr("materials.refresh"), [this, current] {
      if (current()) { state_->refresh(view_); }
    }).width(4).disable(!state_->supported() || view_->busy());
  }
  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx); plot_top_ = 0;
    if (!state_->supported()) { layout.paragraph(ctx.tr("materials.unsupported")); return; }
    if (view_->job.is_null()) {
      layout.paragraph(ctx.tr("materials.intro")); layout.paragraph(ctx.tr("materials.no_curve")); return;
    }
    const auto &job = view_->job;
    layout.label(io::get_string(job, "id") + " · " + std::string(ctx.tr("materials.state." + io::get_string(job, "state"))));
    const auto epoch = io::get_int(job, "epoch", 0), epochs = std::max<int64_t>(1, io::get_int(job, "epochs", 1));
    layout.progress(float(double(epoch) / double(epochs)), std::to_string(epoch) + " / " + std::to_string(epochs));
    layout.tabs("materials_plot_kind", {std::string(ctx.tr("materials.loss")), std::string(ctx.tr("materials.evaluation"))},
        { [this] { return plot_; }, [this, current = guard()](int value) { if (current() && value >= 0 && value <= 1) { plot_ = value; } } });
    plot_top_ = 4 * (ctx.ui ? ctx.ui->style().unit : 20);
    if (plot_ == 1) {
      const auto preview = job.value("evaluation_preview", Json());
      if (preview.is_object() && preview.contains("samples") && preview.at("samples").is_array()) {
        std::vector<std::string> names;
        for (const auto &sample : preview.at("samples")) { names.push_back(io::get_string(sample, "id")); }
        if (!names.empty()) {
          sample_ = std::clamp(sample_, 0, int(names.size()) - 1);
          layout.prop(ctx.tr("materials.sample")).dropdown("materials_sample", names,
              {[this] { return sample_; }, [this, current = guard()](int value) { if (current() && value >= 0 && value < 3) { sample_ = value; } }});
        }
      }
      layout.paragraph(ctx.tr("materials.plot_hint"));
      plot_top_ = 7 * (ctx.ui ? ctx.ui->style().unit : 20);
    }
  }
  void draw_sidebar(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx); ui_ = ctx.ui; fields_.clear(); numeric_props_.clear();
    auto &body = layout.scope(scope_);
    body.tabs("materials_sections", {std::string(ctx.tr("materials.inputs")), std::string(ctx.tr("materials.tasks")),
        std::string(ctx.tr("materials.models"))}, {[this] { return section_; }, [this, current = guard()](int value) {
          if (current() && value >= 0 && value <= 2) { section_ = value; }
        }});
    if (!state_->supported()) { body.paragraph(ctx.tr("materials.unsupported")); }
    if (!error_.empty()) { body.paragraph(ctx.tr(error_)); }
    if (!view_->error.empty()) { body.paragraph(view_->error); }
    if (view_->busy()) { body.label(ctx.tr("materials.loading")); }
    if (section_ == 0) { inputs(body, ctx); }
    else if (section_ == 1) { tasks(body, ctx); }
    else { models(body, ctx); }
  }
  void draw_gpu(EditorContext &ctx) override
  {
    if (!ctx.draw || !ctx.draw->fonts) { return; }
    const float scale = ctx.draw->ui_scale, width = float(ctx.draw->rect.width()), height = float(ctx.draw->rect.height());
    const float line_height = 18 * scale;
    const ui::FontStyle font{ui::FontKind::Regular, 11 * scale};
    ui::DrawList list;
    list.rect({0, 0, width, height}, ui::Color::rgb(0x202328));
    const auto paint = [&] {
      ui::gpu::GpuPainter painter(*ctx.draw->fonts); painter.set_pixel_size(scale); painter.paint(list, {width, height});
    };
    if (!view_ || view_->job.is_null() || plot_top_ <= 0) { paint(); return; }
    const auto plot = plot_ == 0 ? materials_loss_plot(view_->epochs) : materials_evaluation_plot(view_->job, size_t(sample_));
    const ui::Rect area{55 * scale, plot_top_ + 20 * scale, std::max(0.f, width - 75 * scale),
                        std::max(0.f, height - plot_top_ - (65 + 18 * plot.lines.size()) * scale)};
    if (area.w < 20 * scale || area.h < 20 * scale) { paint(); return; }
    const auto foreground = ui::Color::rgb(0xc5cbd1), grid = ui::Color::rgb(0x454b53);
    if (plot.lines.empty()) {
      list.text(std::string(ctx.tr("materials.no_curve")), {area.x, area.y + line_height}, font, foreground);
    }
    else {
      for (int tick = 0; tick <= 4; ++tick) {
        const float part = float(tick) / 4;
        list.rect({area.x + part * area.w, area.y, scale, area.h}, grid);
        list.rect({area.x, area.y + part * area.h, area.w, scale}, grid);
        list.text(number(double((1 - static_cast<long double>(part)) * plot.y_max +
                                static_cast<long double>(part) * plot.y_min)),
                  {2 * scale, area.y + part * area.h + 4 * scale}, font, foreground);
      }
      list.text(number(plot.x_min), {area.x, area.y1() + line_height}, font, foreground);
      list.text(number(plot.x_max), {std::max(area.x, area.x1() - 42 * scale), area.y1() + line_height}, font, foreground);
      const bool pe = io::get_string(view_->job, "kind") == "pe_loop";
      list.text(std::string(ctx.tr(plot_ == 0 ? "materials.epoch" : pe ? "materials.x_field" : "materials.x_cycle")),
                {area.x + .35f * area.w, area.y1() + line_height}, font, foreground);
      list.text(std::string(ctx.tr(plot_ == 0 ? "materials.loss_axis" : pe ? "materials.y_polarization" : "materials.y_soh")),
                {area.x, area.y - 6 * scale}, font, foreground);
      const ui::Color colors[] = {ui::Color::rgb(0x71b7f2), ui::Color::rgb(0xffbd69), ui::Color::rgb(0x99d180), ui::Color::rgb(0xd89fe5)};
      for (size_t index = 0; index < plot.lines.size(); ++index) {
        const auto &line = plot.lines[index]; const auto color = colors[index % 4];
        const std::string key = line.role == "base" ? "base_curve" : line.role;
        const float legend_y = area.y1() + (2 + float(index)) * line_height;
        list.rect({area.x, legend_y - 6 * scale, 16 * scale, 2 * scale}, color);
        list.text(std::string(ctx.tr("materials." + key)), {area.x + 22 * scale, legend_y}, font, foreground);
        list.clip_push(area);
        for (const auto &segment : line.segments) {
          auto position = [&](const MaterialsPlotPoint point) {
            // Scale before subtraction: MSVC long double has double's range, so
            // opposite finite extrema must not overflow their display span.
            const auto normalize = [](double value, double low, double high) {
              const double scale = std::max(std::abs(low), std::abs(high));
              return ((value / scale) - (low / scale)) / ((high / scale) - (low / scale));
            };
            return ui::Vec2{area.x + float(normalize(point.x, plot.x_min, plot.x_max)) * area.w,
                            area.y1() - float(normalize(point.y, plot.y_min, plot.y_max)) * area.h};
          };
          for (size_t point = 0; point < segment.size(); ++point) {
            const auto a = position(segment[point]);
            list.rect({a.x - scale, a.y - scale, 2 * scale, 2 * scale}, color);
            if (!point) { continue; }
            const auto b = position(segment[point - 1]); const float length = std::hypot(a.x - b.x, a.y - b.y);
            if (length <= 0) { continue; }
            const ui::Vec2 offset{-(a.y - b.y) * scale / length, (a.x - b.x) * scale / length};
            list.triangle({a.x + offset.x, a.y + offset.y}, {a.x - offset.x, a.y - offset.y},
                          {b.x + offset.x, b.y + offset.y}, color);
            list.triangle({b.x + offset.x, b.y + offset.y}, {a.x - offset.x, a.y - offset.y},
                          {b.x - offset.x, b.y - offset.y}, color);
          }
        }
        list.clip_pop();
      }
    }
    paint();
  }
  nlohmann::json save_state() const override
  {
    Json result = {{"version", 1}, {"directory", directory_}, {"job_id", job_id_}, {"base_version", base_},
        {"hidden", hidden_}, {"epochs", epochs_}, {"batch_size", batch_}, {"learning_rate", rate_},
        {"patience", patience_}, {"seed", seed_}, {"split", {split_[0], split_[1], split_[2]}},
        {"section", section_}, {"plot", plot_}, {"sample", sample_}, {"kind", kind_}};
    auto number_drafts = number_drafts_;
    // Only this instance's focused string draft can supplement committed bindings.
    if (ui_ && ui_->edit_state()) {
      const auto found = fields_.find(ui_->editing());
      if (found != fields_.end() && (found->second == "directory" || found->second == "job_id" || found->second == "hidden")) {
        result[found->second] = ui_->edit_state()->text();
      }
      else if (found != fields_.end() && numeric_props_.contains(ui_->editing())) {
        number_drafts[found->second] = ui_->edit_state()->text();
      }
    }
    if (!number_drafts.empty()) { result["number_drafts"] = number_drafts; }
    return result;
  }
  bool load_state(const nlohmann::json &state) override
  {
    const Json value = state;
    if (!value.is_object()) { return false; }
    const std::set<std::string> keys = {"version", "directory", "job_id", "base_version", "hidden", "epochs", "batch_size",
        "learning_rate", "patience", "seed", "split", "section", "plot", "sample", "kind", "number_drafts"};
    for (auto item = value.begin(); item != value.end(); ++item) { if (!keys.contains(item.key())) { return false; } }
    if (value.contains("version") && (!value.at("version").is_number_integer() || value.at("version") != 1)) { return false; }
    auto text = [&](const char *key, size_t maximum) { return !value.contains(key) || (value.at(key).is_string() &&
        value.at(key).get_ref<const std::string &>().size() <= maximum && value.at(key).get_ref<const std::string &>().find('\0') == std::string::npos); };
    auto integer = [&](const char *key, int maximum) { return !value.contains(key) || (value.at(key).is_number_integer() &&
        value.at(key).get<int64_t>() >= 0 && value.at(key).get<int64_t>() <= maximum); };
    if (!text("directory", 32768) || !text("job_id", 64) || !text("base_version", 32) || !text("hidden", 128) ||
        !integer("epochs", 5000) || !integer("batch_size", 4096) || !integer("patience", 5000) ||
        !integer("seed", 2147483647) || !integer("section", 2) || !integer("plot", 1) || !integer("sample", 2) || !integer("kind", 1)) { return false; }
    if (value.contains("learning_rate") && (!value.at("learning_rate").is_number() ||
        !std::isfinite(value.at("learning_rate").get<double>()) || value.at("learning_rate").get<double>() <= 0 || value.at("learning_rate").get<double>() > 1)) { return false; }
    if (value.contains("split")) {
      if (!value.at("split").is_array() || value.at("split").size() != 3) { return false; }
      for (const auto &part : value.at("split")) { if (!part.is_number() || !std::isfinite(part.get<double>()) || part.get<double>() <= 0 || part.get<double>() > 1) { return false; } }
    }
    if (value.contains("number_drafts")) {
      const std::set<std::string> fields = {"materials_epochs", "materials_batch", "materials_rate", "materials_patience", "materials_seed",
          "materials_split_train", "materials_split_validation", "materials_split_test"};
      if (!value.at("number_drafts").is_object() || value.at("number_drafts").size() > fields.size()) { return false; }
      for (auto item = value.at("number_drafts").begin(); item != value.at("number_drafts").end(); ++item) {
        if (!fields.contains(item.key()) || !item.value().is_string() || item.value().get_ref<const std::string &>().size() > 128 ||
            item.value().get_ref<const std::string &>().find('\0') != std::string::npos) { return false; }
      }
    }
    if (state_ && view_) {
      state_->detach(view_); state_->invalidate_draft(view_, true); view_->selected_job.clear();
      view_->job = nullptr; view_->epochs = Json::array();
    }
    ++generation_; ui_ = nullptr; fields_.clear(); numeric_props_.clear();
    directory_ = value.value("directory", std::string()); job_id_ = value.value("job_id", std::string("training-job"));
    base_ = value.value("base_version", std::string()); hidden_ = value.value("hidden", std::string("128,128"));
    epochs_ = value.value("epochs", 400); batch_ = value.value("batch_size", 64); patience_ = value.value("patience", 40);
    seed_ = value.value("seed", 0); rate_ = value.value("learning_rate", .001);
    const auto fractions = value.value("split", Json::array({.7, .15, .15}));
    for (size_t index = 0; index < 3; ++index) { split_[index] = fractions[index].get<double>(); }
    section_ = value.value("section", 0); plot_ = value.value("plot", 0); sample_ = value.value("sample", 0); kind_ = value.value("kind", 0);
    number_drafts_ = value.value("number_drafts", std::map<std::string, std::string>());
    dirty_ = !directory_.empty() || hidden_ != "128,128" || epochs_ != 400 || batch_ != 64 || patience_ != 40 || seed_ != 0 || rate_ != .001 ||
        !number_drafts_.empty() || job_id_ != "training-job" || !base_.empty() || split_[0] != .7 || split_[1] != .15 || split_[2] != .15;
    draft_key_.clear(); prepared_switch_.clear(); return true;
  }
 private:
  MaterialsState *state_ = nullptr;
  MaterialsState::ViewPtr view_;
  AppStore *store_ = nullptr;
  EditorArea *area_ = nullptr;
  std::weak_ptr<void> shell_lifetime_;
  ui::Context *ui_ = nullptr;
  std::map<ui::WidgetId, std::string> fields_;
  std::map<ui::WidgetId, ui::NumberProps> numeric_props_;
  std::map<std::string, std::string> number_drafts_;
  std::string scope_, directory_, job_id_ = "training-job", hidden_ = "128,128", base_, version_, error_, draft_key_, draft_directory_, prepared_switch_;
  int epochs_ = 400, batch_ = 64, patience_ = 40, seed_ = 0, section_ = 0, plot_ = 0, sample_ = 0, kind_ = 0;
  double rate_ = .001, split_[3] = {.7, .15, .15};
  uint64_t generation_ = 0;
  bool dirty_ = false;
  float plot_top_ = 0;
  PathPicker picker_;
  std::string draft_key() const
  {
    return Json{{"directory", directory_}, {"id", job_id_}, {"base", base_}, {"hidden", hidden_}, {"epochs", epochs_},
      {"batch", batch_}, {"rate", rate_}, {"patience", patience_}, {"seed", seed_}, {"split", {split_[0], split_[1], split_[2]}},
      {"number_drafts", number_drafts_}}.dump();
  }
  std::function<bool()> guard() const
  {
    const auto weak = lifetime(); const auto generation = generation_, lifetime_epoch = view_ ? view_->lifetime_epoch : 0;
    const auto area = area_; const auto shell = shell_lifetime_;
    const auto bridge_origin = store_ ? store_->bridge_epoch() : 0;
    auto *client = store_ ? store_->bridge() : nullptr;
    const auto pid = client ? client->bridge_pid() : 0;
    const auto spawned = client ? client->stats().spawned : 0;
    return [this, weak, generation, lifetime_epoch, client, pid, spawned, area, shell, bridge_origin] {
      return !weak.expired() && generation == generation_ && view_ && lifetime_epoch == view_->lifetime_epoch && store_ &&
          !shell.expired() && area_ == area && area && &area->editor() == this &&
          store_->bridge_epoch() == bridge_origin && store_->bridge() == client &&
          (!client || (client->bridge_pid() == pid && client->stats().spawned == spawned));
    };
  }
  void attach(EditorContext &ctx)
  {
    store_ = &ctx.store;
    area_ = &ctx.area; shell_lifetime_ = ctx.area.shell().lifetime();
    if (!state_) { state_ = &ctx.store.materials(); view_ = state_->new_view(); }
    state_->sync(view_);
    const auto key = draft_key();
    if (key != draft_key_) {
      if (!draft_key_.empty()) { dirty_ = true; }
      const bool dataset_changed = directory_ != draft_directory_;
      if (dataset_changed && !draft_key_.empty()) { base_.clear(); }
      draft_key_ = draft_key(); draft_directory_ = directory_; state_->invalidate_draft(view_, dataset_changed); ++generation_;
    }
    if (!prepared_switch_.empty() && io::get_string(view_->job, "id") == prepared_switch_) {
      section_ = 1; dirty_ = false; prepared_switch_.clear();
    }
  }
  ui::Binding<std::string> bind_text(std::string &target, const std::string &field)
  {
    return {[&target] { return target; }, [this, current = guard(), &target, field](std::string value) {
      if (current() && !view_->busy() && value != target) {
        target = std::move(value); dirty_ = true; ++generation_; state_->invalidate_draft(view_, field == "directory");
        if (field == "directory") { base_.clear(); }
        draft_key_ = draft_key(); draft_directory_ = directory_;
      }
    }};
  }
  void string_field(ui::Layout &layout, EditorContext &ctx, const char *key, const char *field, std::string &target, const char *label)
  {
    const size_t maximum = field == std::string("directory") ? 32768 : field == std::string("job_id") ? 64 : 128;
    auto &widget = layout.prop(ctx.tr(label)).text_field(key, bind_text(target, field), {.max_length = maximum});
    widget.disable(view_->busy()); fields_[widget.id] = field;
  }
  template<class T> void numeric(ui::Layout &layout, EditorContext &ctx, const char *key, const char *label, T &value, double min, double max, double step)
  {
    const auto current = guard(); ui::NumberProps props;
    props.min = min; props.max = max; props.step = step; props.integer = std::is_integral_v<T>; props.precision = props.integer ? 0 : 6;
    if (number_drafts_.contains(key)) {
      auto &draft = layout.prop(ctx.tr(label)).text_field(key,
          {[this, key] { return number_drafts_.at(key); }, [this, current, key, props, &value](std::string text) {
            if (!current() || view_->busy()) { return; }
            if (const auto parsed = ui::parse_number(text, props)) { value = T(*parsed); number_drafts_.erase(key); }
            else { number_drafts_[key] = std::move(text); }
            dirty_ = true; ++generation_; state_->invalidate_draft(view_); draft_key_ = draft_key();
          }}, {.max_length = 128});
      draft.disable(view_->busy()); fields_[draft.id] = key; numeric_props_[draft.id] = props;
      return;
    }
    auto &widget = layout.prop(ctx.tr(label)).number(key, "", {[&value] { return double(value); }, [this, current, &value](double next) {
      if (current() && !view_->busy() && std::isfinite(next) && double(value) != next) {
        value = T(next); dirty_ = true; ++generation_; state_->invalidate_draft(view_); draft_key_ = draft_key();
      }
    }}, props);
    widget.disable(view_->busy()); fields_[widget.id] = key; numeric_props_[widget.id] = props;
  }
  bool options(Json &result) const
  {
    Json widths = Json::array(); std::istringstream stream(hidden_); std::string token;
    while (std::getline(stream, token, ',')) {
      const auto start = token.find_first_not_of(" \t"); const auto end = token.find_last_not_of(" \t");
      if (start == std::string::npos) { return false; } token = token.substr(start, end - start + 1);
      int width = 0; const auto parsed = std::from_chars(token.data(), token.data() + token.size(), width);
      if (parsed.ec != std::errc() || parsed.ptr != token.data() + token.size() || width < 4 || width > 1024 || widths.size() == 4) { return false; }
      widths.push_back(width);
    }
    if (!number_drafts_.empty() || widths.empty() || hidden_.empty() || hidden_.back() == ',' || epochs_ < 1 || patience_ < 1 || batch_ < 1 ||
        !std::isfinite(rate_) || rate_ <= 0 || rate_ > 1 || std::abs(split_[0] + split_[1] + split_[2] - 1) > 1e-9) { return false; }
    result = {{"hidden", widths}, {"epochs", epochs_}, {"batch_size", batch_}, {"learning_rate", rate_},
              {"patience", patience_}, {"seed", seed_}, {"split", {split_[0], split_[1], split_[2]}}}; return true;
  }
  void inputs(ui::Layout &body, EditorContext &ctx)
  {
    body.paragraph(ctx.tr("materials.draft_hint"));
    string_field(body, ctx, "materials_directory", "directory", directory_, "materials.directory");
    auto &choose = body.row(); const auto current = guard();
    picker_.button(choose, ctx, "materials_browse", &directory_, {.mode = platform::FileDialogMode::OpenFolder,
      .title_key = "materials.directory", .still_current = [this, current, key = draft_key()] { return current() && key == draft_key() && !view_->busy(); }});
    choose.button("materials_validate", ctx.tr("materials.validate"), [this, current, directory = directory_] {
      if (current() && directory_ == directory && !view_->busy()) {
        if (directory.find('\0') != std::string::npos || !core::path_from_utf8(directory).is_absolute()) { error_ = "materials.error_directory"; }
        else { error_.clear(); state_->validate(view_, directory); }
      }
    }).disable(!state_->supported() || view_->busy() || directory_.empty());
    picker_.draw_error(body);
    const auto &card = view_->card;
    if (card.is_object()) {
      body.label(ctx.tr("materials.card"));
      if (!io::get_bool(card, "ok", false)) {
        if (card.contains("problems") && card.at("problems").is_array()) { for (const auto &problem : card.at("problems")) { if (problem.is_string()) { body.paragraph(problem.get<std::string>()); } } }
      }
      else {
        body.paragraph(io::get_string(card, "name") + " · " + std::string(ctx.tr("materials." + io::get_string(card, "kind"))));
        body.prop(ctx.tr("materials.samples")).label(std::to_string(io::get_int(card, "samples", 0)));
        body.paragraph(ctx.tr(io::get_bool(card, "synthetic", false) ? "materials.synthetic" : "materials.measured"));
        body.prop(ctx.tr("materials.sensitivity")).label(io::get_string(card, "sensitivity"));
        body.prop(ctx.tr("materials.license")).label(io::get_string(card, "license"));
      }
    }
    string_field(body, ctx, "materials_job_id", "job_id", job_id_, "materials.job_id");
    const auto kind = io::get_string(card, "kind");
    std::vector<std::string> bases{std::string(ctx.tr("materials.from_scratch"))}, versions{std::string()};
    const auto entry = model_entry(kind);
    if (entry.contains("versions") && entry.at("versions").is_array()) { for (const auto &record : entry.at("versions")) {
      versions.push_back(io::get_string(record, "version")); bases.push_back(versions.back());
    } }
    // A restored choice remains visible until validation/listing confirms it; never display
    // "from scratch" while a nonempty base version would be sent with the explicit request.
    if (!base_.empty() && std::find(versions.begin(), versions.end(), base_) == versions.end()) {
      versions.push_back(base_); bases.push_back(base_);
    }
    int selected = 0; for (size_t index = 0; index < versions.size(); ++index) { if (versions[index] == base_) { selected = int(index); } }
    body.prop(ctx.tr("materials.base")).dropdown("materials_base", bases, {[selected] { return selected; },
      [this, current, versions](int index) { if (current() && !view_->busy() && index >= 0 && size_t(index) < versions.size()) {
        base_ = versions[size_t(index)]; dirty_ = true; ++generation_; state_->invalidate_draft(view_); draft_key_ = draft_key();
      } }}).disable(view_->busy());
    if (auto *panel = body.panel("materials_options", ctx.tr("materials.options"), false)) {
      string_field(*panel, ctx, "materials_hidden", "hidden", hidden_, "materials.hidden");
      numeric(*panel, ctx, "materials_epochs", "materials.epochs", epochs_, 1, 5000, 1);
      numeric(*panel, ctx, "materials_batch", "materials.batch", batch_, 1, 4096, 1);
      numeric(*panel, ctx, "materials_rate", "materials.rate", rate_, .000000001, 1, .0001);
      numeric(*panel, ctx, "materials_patience", "materials.patience", patience_, 1, 5000, 1);
      numeric(*panel, ctx, "materials_seed", "materials.seed", seed_, 0, 2147483647, 1);
      numeric(*panel, ctx, "materials_split_train", "materials.split_train", split_[0], .000000001, 1, .01);
      numeric(*panel, ctx, "materials_split_validation", "materials.split_validation", split_[1], .000000001, 1, .01);
      numeric(*panel, ctx, "materials_split_test", "materials.split_test", split_[2], .000000001, 1, .01);
    }
    body.paragraph(ctx.tr("materials.prepare_hint"));
    Json checked; const bool valid = options(checked);
    body.button("materials_prepare", ctx.tr("materials.prepare"), [this, current, key = draft_key()] {
      if (!current() || key != draft_key() || view_->busy()) { return; }
      Json settings;
      if (!options(settings)) { error_ = "materials.error_options"; return; }
      if (directory_.find('\0') != std::string::npos || !core::path_from_utf8(directory_).is_absolute()) { error_ = "materials.error_directory"; return; }
      Json params = {{"directory", directory_}, {"job_id", job_id_}, {"options", std::move(settings)}};
      if (!base_.empty()) { params["base_version"] = base_; }
      error_.clear(); if (state_->prepare(view_, std::move(params))) { prepared_switch_ = job_id_; }
    }).disable(!state_->supported() || view_->busy() || directory_.empty() || job_id_.empty() || !valid);
    body.button("materials_discard_draft", ctx.tr("materials.discard_draft"), [this, current] {
      if (!current() || view_->busy()) { return; }
      load_state(Json::object()); dirty_ = false;
    }).disable(!has_unsaved_changes() || view_->busy());
  }
  Json model_entry(const std::string &kind) const
  {
    if (!view_->models.is_object() || !view_->models.contains("kinds") || !view_->models.at("kinds").contains(kind)) { return Json::object(); }
    return view_->models.at("kinds").at(kind);
  }
  void tasks(ui::Layout &body, EditorContext &ctx)
  {
    std::vector<std::string> names, ids; int selected = -1;
    for (const auto &job : view_->jobs) {
      ids.push_back(io::get_string(job, "id"));
      names.push_back(ids.back() + " · " + std::string(ctx.tr("materials.state." + io::get_string(job, "state"))));
      if (ids.back() == view_->selected_job) { selected = int(ids.size()) - 1; }
    }
    const auto current = guard();
    body.prop(ctx.tr("materials.choose_job")).dropdown("materials_jobs", names, {[selected] { return selected; },
      [this, current, ids](int index) { if (current() && !view_->busy() && index >= 0 && size_t(index) < ids.size()) {
        state_->select_job(view_, ids[size_t(index)]); ++generation_;
      } }}).disable(names.empty() || view_->busy());
    if (names.empty()) { body.paragraph(ctx.tr("materials.no_jobs")); }
    body.button("materials_jobs_more", ctx.tr("materials.jobs_more"), [this, current] { if (current()) { state_->more_jobs(view_); } })
        .disable(view_->next_offset < 0 || view_->busy());
    const auto &job = view_->job; if (!job.is_object()) { return; }
    const auto id = io::get_string(job, "id"), state = io::get_string(job, "state");
    body.label(id); body.label(ctx.tr("materials.state." + state));
    body.button("materials_start", ctx.tr("materials.start"), [this, current, id] {
      if (current() && view_->selected_job == id && io::get_string(view_->job, "state") == "prepared") { state_->start(view_); }
    }).disable(!state_->supported() || view_->busy() || state != "prepared");
    body.button("materials_cancel", ctx.tr("materials.cancel"), [this, current, id] {
      if (current() && view_->selected_job == id) { state_->cancel(view_); }
    }).disable(view_->busy() || (state != "running" && state != "prepared"));
    body.button("materials_recover", ctx.tr("materials.recover"), [this, current, id] {
      if (current() && view_->selected_job == id) { state_->recover(view_); }
    }).disable(view_->busy() || (state != "running" && state != "uncertain"));
    if (state == "running" || state == "uncertain") { body.paragraph(ctx.tr("materials.recover_hint")); }
    const auto reason = io::get_string(job, "reason"); if (!reason.empty()) { body.prop(ctx.tr("materials.reason")).paragraph(reason); }
    if (!io::get_string(job, "error").empty()) { body.paragraph(io::get_string(job, "error")); }
    if (const auto found = job.find("comparison"); found != job.end() && found->is_object()) {
      body.label(ctx.tr("materials.heldout"));
      body.prop(ctx.tr("materials.samples")).label(std::to_string(io::get_int(*found, "test_samples", 0)));
      for (const auto role : {"candidate", "base", "baseline"}) {
        const auto metric = found->value(role, Json());
        if (metric.is_object() && metric.contains("normalized_rmse") && metric.at("normalized_rmse").is_number()) {
          body.prop(ctx.tr(std::string("materials.") + (std::string(role) == "base" ? "base_curve" : role)))
              .label("NRMSE " + number(metric.at("normalized_rmse").get<double>()));
        }
      }
    }
    if (auto *panel = body.panel("materials_receipt", ctx.tr("materials.input_sha"), false)) {
      panel->paragraph(io::get_string(job, "input_sha256"));
      const auto counts = job.value("split_counts", Json());
      if (counts.is_object()) {
        for (const auto part : {"train", "validation", "test"}) {
          panel->prop(ctx.tr(std::string("materials.split_") + part)).label(std::to_string(io::get_int(counts, part, 0)));
        }
      }
      panel->prop(ctx.tr("materials.base")).label(io::get_string(job, "base_version", "—"));
      panel->prop(ctx.tr("materials.baseline")).label(io::get_string(job, "baseline_version", "—"));
    }
  }
  void models(ui::Layout &body, EditorContext &ctx)
  {
    const auto current = guard();
    body.prop(ctx.tr("materials.kind")).dropdown("materials_kind", {std::string(ctx.tr("materials.pe_loop")), std::string(ctx.tr("materials.capacity_fade"))},
      {[this] { return kind_; }, [this, current](int index) { if (current() && index >= 0 && index <= 1) { kind_ = index; version_.clear(); ++generation_; } }});
    const std::string kind = kind_ == 0 ? "pe_loop" : "capacity_fade"; const auto entry = model_entry(kind);
    body.prop(ctx.tr("materials.active")).label(io::get_string(entry, "active", "—"));
    std::vector<std::string> names;
    if (entry.contains("versions") && entry.at("versions").is_array()) { for (const auto &record : entry.at("versions")) { names.push_back(io::get_string(record, "version")); } }
    int selected = -1;
    for (size_t index = 0; index < names.size(); ++index) { if (names[index] == version_) { selected = int(index); } }
    body.prop(ctx.tr("materials.choose_version")).dropdown("materials_versions", names, {[selected] { return selected; },
      [this, current, names](int index) { if (current() && !view_->busy() && index >= 0 && size_t(index) < names.size()) { version_ = names[size_t(index)]; ++generation_; } }})
      .disable(names.empty() || view_->busy());
    if (names.empty()) { body.paragraph(ctx.tr("materials.no_versions")); }
    body.paragraph(ctx.tr("materials.activation_hint"));
    body.button("materials_activate", ctx.tr("materials.activate"), [this, current, kind, version = version_] {
      if (current() && version_ == version && (kind_ == 0 ? "pe_loop" : "capacity_fade") == kind) { state_->activate(view_, kind, version); }
    }).disable(view_->busy() || version_.empty() || version_ == io::get_string(entry, "active"));
  }
};
}  // namespace
std::unique_ptr<Editor> make_materials_editor(const EditorType &type) { return std::make_unique<MaterialsEditor>(type); }
}  // namespace stk::app
