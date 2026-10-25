/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/project_reports.hh"
#include "stk/app/project_state.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/io/png.hh"
#include "path_picker.hh"
#include "project_navigation.hh"

#include <algorithm>
#include <cmath>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
std::string short_text(const std::string &text, size_t bytes = 256)
{
  return text.size() <= bytes ? text : std::string(core::utf8::truncate_bytes(text, bytes)) + "…";
}
class ReportsEditor final : public Editor {
 public:
  explicit ReportsEditor(const EditorType &type) : Editor(type) {}
  ~ReportsEditor() override { release_image(); }
  bool has_unsaved_changes() const override { return reports_ && reports_->exporting(); }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    attach(ctx); workspace_link(row, ctx);
    const auto current = guard();
    row.button("reports_refresh", ctx.tr("project.refresh"), [this, current] {
      if (!current() || reports_->busy()) { return; }
      reports_->clear(); // Revalidate metadata; never implicitly reread an asset.
    }).width(5).disable(!reports_->supported() || reports_->busy());
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx);
    auto &reports = *reports_;
    const auto &project = ctx.store.project().project();
    if (!project) {
      layout.paragraph(ctx.tr("reports.no_project"));
      layout.button("reports_project", ctx.tr("project.location"), project_navigation_action(ctx, "project"));
      return;
    }
    if (!reports.supported()) { layout.paragraph(ctx.tr("reports.unsupported")); return; }
    if (!reports.busy() && reports.error().empty()) {
      if (reports.page().is_null()) { reports.load_page(); }
      else if (pending_load_ && project_id_ == reports.project_id()) {
        if (reports.load(report_id_, source_sha_)) { pending_load_ = false; }
      }
    }
    accept_selection();
    layout.label(short_text(project->name));
    layout.paragraph(ctx.tr("reports.intro"));
    if (reports.busy()) { layout.label(ctx.tr("project.busy")); }
    if (!reports.error().empty()) { layout.paragraph(reports.error()); }
    if (!reports.notice().empty()) { layout.paragraph(ctx.tr(reports.notice())); }
    if (!project_id_.empty() && project_id_ != reports.project_id()) { layout.paragraph(ctx.tr("reports.other_project")); }
    const auto current = guard();
    draw_list(layout, ctx, current);
    if (!reports.selected().is_object()) { return; }
    const auto &item = reports.selected();
    layout.label(short_text(io::get_string(item, "name")));
    if (io::get_string(item, "state") != "readable") { layout.paragraph(io::get_string(item, "error")); return; }
    const auto &manifest = item.at("manifest");
    layout.label(std::string(ctx.tr("reports.version")) + source_sha_);
    layout.label(std::string(ctx.tr("reports.snapshot")) + io::get_string(manifest, "snapshot_id") +
        " · " + std::string(ctx.tr("reports.revision")) + std::to_string(io::get_int(manifest, "source_revision", 0)));
    draw_sources(layout, ctx, manifest);
    draw_assets(layout, ctx, manifest, current);
    draw_export(layout, ctx, current);
    draw_content(layout, ctx, current);
  }

  nlohmann::json save_state() const override
  {
    // Stable identities and reading preferences only: no handle, URL, document bytes or destination.
    return {{"version", 1}, {"project_id", project_id_}, {"report_id", core::is_sha256_hex(source_sha_) ? report_id_ : ""},
            {"source_sha256", source_sha_}, {"asset_path", asset_path_}, {"text_page", text_page_}};
  }
  bool load_state(const nlohmann::json &state) override
  {
    if (state.is_object() && state.empty()) {
      return load_state({{"version", 1}, {"project_id", ""}, {"report_id", ""},
          {"source_sha256", ""}, {"asset_path", ""}, {"text_page", 0}});
    }
    if (!state.is_object() || state.size() != 6 || io::get_int(state, "version", -1) != 1 ||
        !state.contains("text_page") || !state.at("text_page").is_number_integer()) { return false; }
    for (const char *key : {"project_id", "report_id", "source_sha256", "asset_path"}) {
      if (!state.contains(key) || !state.at(key).is_string()) { return false; }
    }
    const auto project = io::get_string(state, "project_id"), report = io::get_string(state, "report_id");
    const auto digest = io::get_string(state, "source_sha256"), path = io::get_string(state, "asset_path");
    const auto page = io::get_int(state, "text_page", 0);
    if ((!project.empty() && !canonical_uuid(project)) || (!report.empty() && !canonical_uuid(report)) ||
        (!digest.empty() && !core::is_sha256_hex(digest)) || (!report.empty() && (project.empty() || digest.empty())) ||
        path.size() > 1024 || !core::utf8::is_valid(path) || path.find('\0') != std::string::npos || page < 0 || page > 4096) { return false; }
    ++generation_; release_image(); text_offsets_.clear(); destination_.clear(); navigation_handle_.clear();
    if (reports_) { reports_->clear(); }
    project_id_ = project; report_id_ = report; source_sha_ = digest; asset_path_ = path; text_page_ = size_t(page);
    pending_load_ = !report.empty(); restore_asset_ = true; restored_ = true;
    return true;
  }
  bool shows_navigation_target(const nlohmann::json &target) const override
  {
    if (reports_) { reports_->sync(); }
    return reports_ && io::get_string(target, "project_handle") == reports_->handle() &&
        project_id_ == reports_->project_id() && io::get_string(target, "project_id") == project_id_ &&
        io::get_string(target, "report_id") == report_id_ &&
        io::get_string(target, "source_sha256") == source_sha_;
  }
  bool navigate(const nlohmann::json &target, const std::weak_ptr<void> &, std::string &) override
  {
    if (has_unsaved_changes() || !target.is_object() || !canonical_uuid(io::get_string(target, "project_id")) ||
        !canonical_uuid(io::get_string(target, "report_id")) ||
        !core::is_sha256_hex(io::get_string(target, "source_sha256")) ||
        io::get_string(target, "project_handle").empty()) { return false; }
    if (reports_ && (reports_->handle() != io::get_string(target, "project_handle") ||
                    reports_->project_id() != io::get_string(target, "project_id"))) { return false; }
    const bool accepted = load_state({{"version", 1}, {"project_id", io::get_string(target, "project_id")},
        {"report_id", io::get_string(target, "report_id")}, {"source_sha256", io::get_string(target, "source_sha256")},
        {"asset_path", ""}, {"text_page", 0}});
    if (accepted) { navigation_handle_ = io::get_string(target, "project_handle"); }
    return accepted;
  }

 private:
  void attach(EditorContext &ctx)
  {
    if (!reports_) { reports_ = std::make_unique<ProjectReports>(ctx.store); }
    reports_->sync();
    if (epoch_ != reports_->epoch()) {
      epoch_ = reports_->epoch(); ++generation_; release_image(); text_offsets_.clear();
      asset_version_ = std::numeric_limits<uint64_t>::max(); destination_.clear();
      if (!restored_ && !project_id_.empty() && !reports_->project_id().empty() && project_id_ != reports_->project_id()) {
        report_id_.clear(); source_sha_.clear(); asset_path_.clear(); text_page_ = 0;
      }
      if (!restored_ || project_id_.empty()) { project_id_ = reports_->project_id(); }
      pending_load_ = !report_id_.empty(); restore_asset_ = true;
    }
    if (!navigation_handle_.empty() && reports_->supported()) {
      if (navigation_handle_ != reports_->handle()) { pending_load_ = false; }
      navigation_handle_.clear();
    }
  }
  std::function<bool()> guard() const
  {
    const auto weak = lifetime();
    const auto generation = generation_, epoch = reports_->epoch(), version = reports_->version();
    const auto selected = io::get_string(reports_->selected(), "id"), digest = io::get_string(reports_->selected(), "source_sha256");
    return [this, weak, generation, epoch, version, selected, digest] {
      if (weak.expired() || generation != generation_ || !reports_) { return false; }
      reports_->sync();
      return reports_->epoch() == epoch && reports_->version() == version &&
          io::get_string(reports_->selected(), "id") == selected &&
          io::get_string(reports_->selected(), "source_sha256") == digest;
    };
  }
  void accept_selection()
  {
    if (!reports_->selected().is_object()) { return; }
    project_id_ = reports_->project_id(); report_id_ = io::get_string(reports_->selected(), "id");
    source_sha_ = io::get_string(reports_->selected(), "source_sha256");
    if (restore_asset_) {
      restore_asset_ = false;
      if (!asset_path_.empty()) { reports_->select_asset(asset_path_); }
    }
    asset_path_ = reports_->asset_path();
  }
  void draw_list(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &current)
  {
    const auto &page = reports_->page();
    if (!page.is_object()) { return; }
    const auto &items = page.at("reports");
    if (items.empty()) { layout.paragraph(ctx.tr("reports.empty")); return; }
    // Only bounded summaries are copied into retained UI callbacks, never full manifests.
    ui::ListSpec list; list.count = int(items.size()); list.rows = std::min(4.0f, float(items.size()));
    list.text = [items](int i) { const auto &item = items.at(size_t(i));
      return short_text(io::get_string(item, "name")) + (io::get_string(item, "state") == "readable" ? "" : " ⚠"); };
    int selected = -1;
    for (size_t i = 0; i < items.size(); ++i) { if (io::get_string(items[i], "id") == report_id_) { selected = int(i); } }
    list.selected = {[selected] { return selected; }, [this, current, items](int i) {
      if (!current() || reports_->busy() || i < 0 || size_t(i) >= items.size()) { return; }
      ++generation_; restored_ = pending_load_ = restore_asset_ = false;
      asset_path_.clear(); text_page_ = 0; destination_.clear();
      report_id_ = io::get_string(items[size_t(i)], "id"); project_id_ = reports_->project_id();
      source_sha_ = io::get_string(items[size_t(i)], "source_sha256");
      reports_->load(report_id_, source_sha_); // Accept exactly the version explicitly selected in this list.
    }};
    layout.virtual_list("reports_list", std::move(list)).disable(reports_->busy());
    const auto offset = io::get_int(page, "offset", 0), total = io::get_int(page, "total", 0);
    if (offset || total > int64_t(items.size())) {
      auto &pages = layout.row();
      pages.button("reports_previous", ctx.tr("reports.previous"), [this, current, offset] {
        if (current()) { reports_->load_page(std::max(int64_t(0), offset - 64)); }
      }).disable(reports_->busy() || !offset);
      pages.button("reports_next", ctx.tr("reports.next"), [this, current, offset] {
        if (current()) { reports_->load_page(offset + 64); }
      }).disable(reports_->busy() || offset + int64_t(items.size()) >= total);
    }
  }
  void draw_sources(ui::Layout &layout, EditorContext &ctx, const Json &manifest)
  {
    auto *panel = layout.panel("reports_sources", ctx.tr("reports.sources"), false);
    if (!panel) { return; }
    const auto &sources = manifest.at("sources");
    if (sources.empty()) { panel->label(ctx.tr("reports.no_sources")); return; }
    ui::ListSpec list; list.count = int(sources.size()); list.rows = std::min(3.0f, float(sources.size()));
    // Construct small display rows, not retained copies of frozen contexts (up to 384 KiB).
    std::vector<std::string> rows;
    for (const auto &source : sources) {
      rows.push_back(std::string(ctx.tr("reports.source." + io::get_string(source, "kind"))) + " · " +
          io::get_string(source, "id") + " · r" + std::to_string(io::get_int(source, "source_revision", 0)));
    }
    list.text = [rows](int i) { return rows.at(size_t(i)); };
    list.selected = {[] { return -1; }, [](int) {}};
    panel->virtual_list("reports_source_list", std::move(list));
    panel->paragraph(ctx.tr("reports.sources_export"));
  }
  void draw_assets(ui::Layout &layout, EditorContext &ctx, const Json &manifest, const std::function<bool()> &current)
  {
    layout.label(ctx.tr("reports.assets"));
    const auto &assets = manifest.at("assets");
    ui::ListSpec list; list.count = int(assets.size()); list.rows = std::min(4.0f, float(assets.size()));
    const auto entry = io::get_string(manifest, "entry_path");
    list.text = [assets, entry](int i) { const auto &asset = assets.at(size_t(i));
      const auto path = io::get_string(asset, "path");
      return (path == entry ? "▶ " : "  ") + short_text(path) + " · " + io::get_string(asset, "mime") +
          " · " + std::to_string(io::get_int(asset, "size", 0)) + " B"; };
    int selected = -1;
    for (size_t i = 0; i < assets.size(); ++i) { if (io::get_string(assets[i], "path") == reports_->asset_path()) { selected = int(i); } }
    list.selected = {[selected] { return selected; }, [this, current, assets](int i) {
      if (current() && !reports_->busy() && i >= 0 && size_t(i) < assets.size() &&
          reports_->select_asset(io::get_string(assets[size_t(i)], "path"))) {
        ++generation_; asset_path_ = reports_->asset_path(); text_page_ = 0;
      }
    }};
    layout.virtual_list("reports_assets", std::move(list)).disable(reports_->busy());
    layout.button("reports_read_asset", ctx.tr("reports.read_asset"), [this, current] {
      if (current()) { reports_->read_asset(); }
    }).disable(reports_->busy() || reports_->asset_path().empty() || !reports_->supports("project.reports.asset"));
  }
  void draw_export(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &current)
  {
    auto &row = layout.row(true);
    row.text_field("reports_destination", {
        [this, current] { return current() ? destination_ : std::string(); },
        [this, current](const std::string &value) { if (current() && !reports_->busy() && value.size() <= 4096) { destination_ = value; } }},
        {.placeholder = std::string(ctx.tr("reports.destination")), .max_length = 4096}).disable(reports_->busy());
    picker_.button(row, ctx, "reports_browse", &destination_, {.mode = platform::FileDialogMode::SaveFile,
        .title_key = "reports.export", .file_name = "report.zip",
        .still_current = [this, current, path = destination_] { return current() && !reports_->busy() && destination_ == path; }});
    const auto destination = destination_;
    row.button("reports_export", ctx.tr("reports.export"), [this, current, destination] {
      if (current() && destination_ == destination) { reports_->export_file(destination); }
    }).disable(reports_->busy() || destination.empty() || !reports_->supports("project.reports.export_file"));
    picker_.draw_error(layout);
    if (reports_->export_receipt().is_object()) { layout.paragraph(io::get_string(reports_->export_receipt(), "path")); }
  }
  void release_image()
  {
    if (texture_ && free_texture_) { free_texture_(texture_); }
    texture_ = 0; free_texture_ = {}; image_.reset(); image_error_.clear();
  }
  void cache_content()
  {
    if (asset_version_ == reports_->asset_version()) { return; }
    asset_version_ = reports_->asset_version(); release_image(); text_offsets_.clear();
    if (!reports_->asset_loaded()) { return; }
    const auto &bytes = reports_->asset_bytes();
    if (reports_->asset_mime() == "image/png") {
      try { image_ = io::decode_png(bytes, {4096, 4096, 4 * 1024 * 1024}); }
      catch (const std::exception &error) { image_error_ = error.what(); }
    }
    else if (reports_->asset_mime().starts_with("text/")) {
      const std::string_view text(bytes.empty() ? "" : reinterpret_cast<const char *>(bytes.data()), bytes.size());
      text_offsets_.push_back(0);
      for (size_t offset = 0; offset < text.size();) {
        offset += core::utf8::truncate_bytes(text.substr(offset), 4096).size();
        text_offsets_.push_back(offset);
      }
      if (text_offsets_.size() == 1) { text_offsets_.push_back(0); }
      text_page_ = std::min(text_page_, text_offsets_.size() - 2);
    }
  }
  void draw_content(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &current)
  {
    cache_content();
    if (!reports_->asset_loaded()) { return; }
    layout.label(short_text(reports_->asset_path()));
    if (!image_error_.empty()) { layout.paragraph(image_error_); }
    if (image_) {
      auto &jobs = ctx.store.jobs();
      if (!texture_ && jobs.create_texture && jobs.free_texture) {
        free_texture_ = jobs.free_texture; texture_ = jobs.create_texture(*image_);
      }
      layout.image("reports_image", {texture_, int(image_->width), int(image_->height), 12});
      return;
    }
    if (!text_offsets_.empty()) {
      layout.paragraph(ctx.tr("reports.raw_text"));
      const auto pages = text_offsets_.size() - 1;
      auto &row = layout.row(true);
      row.button("reports_text_previous", ctx.tr("reports.previous"), [this, current] {
        if (current() && text_page_) { --text_page_; }
      }).disable(text_page_ == 0);
      row.number("reports_text_page", ctx.tr("reports.page"), {
          [this, current] { return current() ? double(text_page_ + 1) : 1.0; },
          [this, current, pages](double value) { if (current() && std::isfinite(value)) { text_page_ = size_t(std::clamp(value, 1.0, double(pages))) - 1; } }},
          {.min = 1, .max = double(pages), .step = 1, .precision = 0});
      row.label("/ " + std::to_string(pages));
      row.button("reports_text_next", ctx.tr("reports.next"), [this, current, pages] {
        if (current() && text_page_ + 1 < pages) { ++text_page_; }
      }).disable(text_page_ + 1 >= pages);
      const auto &bytes = reports_->asset_bytes();
      const auto start = text_offsets_[text_page_], end = text_offsets_[text_page_ + 1];
      layout.paragraph(std::string_view(bytes.empty() ? "" : reinterpret_cast<const char *>(bytes.data()) + start, end - start));
    }
    else { layout.paragraph(ctx.tr("reports.binary_asset")); }
  }

  std::unique_ptr<ProjectReports> reports_;
  uint64_t epoch_ = std::numeric_limits<uint64_t>::max(), generation_ = 0;
  uint64_t asset_version_ = std::numeric_limits<uint64_t>::max();
  std::string project_id_, report_id_, source_sha_, asset_path_, navigation_handle_, destination_;
  bool pending_load_ = false, restore_asset_ = false, restored_ = false;
  size_t text_page_ = 0;
  std::vector<size_t> text_offsets_;
  std::optional<io::Image> image_;
  std::string image_error_;
  uint64_t texture_ = 0;
  std::function<void(uint64_t)> free_texture_;
  PathPicker picker_;
};
}  // namespace
std::unique_ptr<Editor> make_reports_editor(const EditorType &type) { return std::make_unique<ReportsEditor>(type); }
}  // namespace stk::app
