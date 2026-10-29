/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/project_reports.hh"
#include "stk/app/report_document_host.hh"
#include "stk/app/project_state.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/io/png.hh"
#include "path_picker.hh"
#include "project_navigation.hh"
#include "reports_create_view.hh"
#include "reports_generation_view.hh"

#include <algorithm>
#include <cmath>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
// Workspace hooks receive sorted JSON. Inspect bounded scalar fields directly before
// any conversion to ordered RPC JSON, which would otherwise copy the complete draft.
bool reading_state_shape(const nlohmann::json &state, int version)
{
  if (!state.is_object() || state.size() != size_t(version == 3 ? 8 : version == 2 ? 7 : 6) ||
      !state.contains("version") || !state.at("version").is_number_integer() || state.at("version") != version ||
      !state.contains("text_page") || !state.at("text_page").is_number_integer()) { return false; }
  const auto &page = state.at("text_page");
  if (page < 0 || page > 4096) { return false; }
  for (const char *key : {"project_id", "report_id", "source_sha256", "asset_path"}) {
    if (!state.contains(key) || !state.at(key).is_string() ||
        state.at(key).get_ref<const std::string &>().size() > (std::string_view(key) == "asset_path" ? 1024u : 64u)) { return false; }
  }
  return true;
}
std::string short_text(const std::string &text, size_t bytes = 256)
{
  return text.size() <= bytes ? text : std::string(core::utf8::truncate_bytes(text, bytes)) + "…";
}
class ReportsEditor final : public Editor {
 public:
  explicit ReportsEditor(const EditorType &type) : Editor(type) {}
  ~ReportsEditor() override
  {
    if (reports_) { reports_->on_preview_invalidated = {}; }
    document_.reset();
    release_image();
  }
  bool has_unsaved_changes() const override
  {
    return create_.dirty() || generate_.dirty() || (reports_ && reports_->exporting());
  }
  void on_area_removed() override
  {
    // An in-flight prepared response must not attach to a different owner/window later.
    // Keep the source reader, PNG and creation draft; reopening the native page is explicit.
    ++generation_; // Retained controls from the old area cannot reopen the moved preview.
    if (reports_) { reports_->clear_preview(); }
    if (document_) { document_->clear(); document_->set_visible(false); }
    document_mode_ = false;
  }

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
    if (document_mode_ && reports.selected().is_object() &&
        io::get_string(reports.selected(), "state") == "readable") {
      draw_document(layout, ctx, guard());
      return;
    }
    document_->set_visible(false);
    layout.label(short_text(project->name));
    layout.paragraph(ctx.tr("reports.intro"));
    if (reports.busy()) { layout.label(ctx.tr("project.busy")); }
    if (!reports.error().empty()) { layout.paragraph(reports.error()); }
    if (!reports.notice().empty()) { layout.paragraph(ctx.tr(reports.notice())); }
    if (!project_id_.empty() && project_id_ != reports.project_id()) { layout.paragraph(ctx.tr("reports.other_project")); }
    generate_.draw(layout, ctx, [this, weak = lifetime()] {
      return !weak.expired() && reports_ && !reports_->busy();
    });
    const auto adopt_created = [this, &reports](const auto &created) {
      if (created.project_id != reports.project_id()) { return; }
      ++generation_; release_image(); text_offsets_.clear(); destination_.clear();
      project_id_ = created.project_id; report_id_ = created.report_id; source_sha_ = created.source_sha256;
      asset_path_.clear(); text_page_ = 0; pending_load_ = restore_asset_ = restored_ = true;
      reports.clear(); // Open only verified metadata after the explicit create; no asset read.
    };
    if (const auto created = generate_.take_created()) { adopt_created(*created); }
    create_.draw(layout, ctx, [this, weak = lifetime()] {
      return !weak.expired() && reports_ && !reports_->busy();
    });
    if (const auto created = create_.take_created()) { adopt_created(*created); }
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
    layout.button("reports_preview", ctx.tr("reports.preview"), [this, current] {
      if (!current()) { return; }
      document_mode_ = true;
      document_->set_visible(true);
      if (!document_->has_content() && !reports_->preview_busy()) { reports_->prepare_preview(); }
    }).disable(reports.busy() || reports.preview_busy() || !reports.supports_preview());
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
    if (!reading_state_shape(state, 1)) { return false; }
    const auto &project = state.at("project_id").get_ref<const std::string &>();
    const auto &report = state.at("report_id").get_ref<const std::string &>();
    const auto &digest = state.at("source_sha256").get_ref<const std::string &>();
    const auto &path = state.at("asset_path").get_ref<const std::string &>();
    const auto page = state.at("text_page").get<int64_t>();
    if ((!project.empty() && !canonical_uuid(project)) || (!report.empty() && !canonical_uuid(report)) ||
        (!digest.empty() && !core::is_sha256_hex(digest)) || (!report.empty() && (project.empty() || digest.empty())) ||
        path.size() > 1024 || !core::utf8::is_valid(path) || path.find('\0') != std::string::npos || page < 0 || page > 4096) { return false; }
    if (document_) { document_->clear(); document_->set_visible(false); }
    document_mode_ = false;
    ++generation_; release_image(); text_offsets_.clear(); destination_.clear(); navigation_handle_.clear();
    if (reports_) { reports_->clear(); }
    project_id_ = project; report_id_ = report; source_sha_ = digest; asset_path_ = path; text_page_ = size_t(page);
    pending_load_ = !report.empty(); restore_asset_ = true; restored_ = true;
    return true;
  }
  nlohmann::json save_workspace_state() const override
  {
    auto state = save_state();
    const auto draft = create_.save_workspace_state();
    const auto generated = generate_.save_workspace_state();
    if (!generated.empty()) {
      state["version"] = 3; state["create_draft"] = draft; state["generation_draft"] = generated;
    }
    else if (!draft.empty()) { state["version"] = 2; state["create_draft"] = draft; }
    return state;
  }
  bool load_workspace_state(const nlohmann::json &state) override
  {
    if (state.is_object() && state.contains("version") && state.at("version").is_number_integer() &&
        (state.at("version") == 2 || state.at("version") == 3)) {
      const bool generated = state.at("version") == 3;
      if (!reading_state_shape(state, generated ? 3 : 2) || !state.contains("create_draft") ||
          !ReportsCreateView::valid_workspace_state(state.at("create_draft")) ||
          (generated && (!state.contains("generation_draft") ||
              !ReportsGenerationView::valid_workspace_state(state.at("generation_draft"))))) { return false; }
      nlohmann::json reading = {{"version", 1}};
      for (const char *key : {"project_id", "report_id", "source_sha256", "asset_path", "text_page"}) { reading[key] = state.at(key); }
      // Validate both payloads before mutating this tab. Reader validation is atomic.
      if (!load_state(reading)) { return false; }
      return create_.load_workspace_state(state.at("create_draft")) &&
          generate_.load_workspace_state(generated ? state.at("generation_draft") : nlohmann::json::object());
    }
    if (!load_state(state)) { return false; }
    return create_.load_workspace_state(nlohmann::json::object()) &&
        generate_.load_workspace_state(nlohmann::json::object());
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
    if (!document_) {
      document_ = std::make_unique<ReportDocumentHost>(ctx.store);
      reports_->on_preview_invalidated = document_->invalidator();
    }
    document_->bind(*this, ctx);
    reports_->sync();
    if (reports_->prepared_preview()) {
      if (auto prepared = reports_->take_prepared_preview()) { document_->adopt(std::move(*prepared)); }
    }
    document_->set_visible(document_mode_);
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
  void draw_document(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &current)
  {
    using document_preview::NativeViewStatus;
    layout.label(short_text(io::get_string(reports_->selected(), "name"), 128));
    layout.label(std::string(ctx.tr("reports.version")) + source_sha_);
    auto &actions = layout.row(true);
    actions.button("reports_document_source", ctx.tr("reports.source_view"), [this, current] {
      if (current()) { document_mode_ = false; document_->set_visible(false); }
    });
    actions.button("reports_document_prepare", ctx.tr("reports.preview_prepare"), [this, current] {
      if (current()) { reports_->prepare_preview(); }
    }).disable(reports_->busy() || reports_->preview_busy() || !reports_->supports_preview());
    actions.button("reports_document_close", ctx.tr("reports.preview_close"), [this, current] {
      if (current()) { reports_->clear_preview(); document_mode_ = false; document_->set_visible(false); }
    });
    const auto actual = document_->state();
    auto &focus = layout.row(true);
    const auto previous_anchor = focus.button("reports_document_focus", ctx.tr("reports.preview_focus"), [this, current] {
      if (current()) { document_->focus(); }
    }).disable(actual.status != NativeViewStatus::Ready || !actual.parent_attached).id;
    focus.button("reports_document_return_focus", ctx.tr("reports.preview_return"), [this, current] {
      if (current()) { document_->return_focus(); }
    });
    if (document_->has_media()) {
      focus.button("reports_document_pause", ctx.tr("reports.video_pause"), [this, current] {
        if (current()) { document_->pause_media(); }
      }).disable(actual.status != NativeViewStatus::Ready);
      layout.paragraph(ctx.tr("reports.video_help"));
    }
    if (reports_->preview_busy()) { layout.label(ctx.tr("reports.preview_preparing")); }
    else if (!reports_->preview_error().empty()) { layout.paragraph(reports_->preview_error()); }
    else if (actual.status == NativeViewStatus::Unsupported) { layout.paragraph(ctx.tr("reports.preview_unsupported")); }
    else if (actual.status == NativeViewStatus::Failed) { layout.paragraph(actual.message); }
    else if (actual.status == NativeViewStatus::Ready && actual.parent_attached && actual.visible) {
      layout.label(ctx.tr("reports.preview_ready"));
    }
    else if (document_->has_content()) { layout.label(ctx.tr("reports.preview_loading")); }
    else { layout.label(ctx.tr("reports.preview_prepare_needed")); }
    const float unit = ctx.ui ? ctx.ui->style().unit : 20.0f;
    const float height = ctx.draw ? float(ctx.draw->rect.height()) : 0.0f;
    ui::WidgetId viewport = 0;
    const float reserved_rows = document_->has_media() ? 15.0f : 10.0f;
    if (height >= (reserved_rows + 2.0f) * unit && document_->has_content()) {
      // The reading mode has a fixed compact toolbar; leave an additional row below the
      // dedicated viewport so Tab can leave forwards as well as backwards.
      viewport = layout.native_viewport("reports_document_viewport", std::max(1.0f, height / unit - reserved_rows)).id;
    }
    else if (document_->has_content()) { layout.label(ctx.tr("reports.preview_enlarge")); }
    const auto next_anchor = layout.button("reports_document_after", ctx.tr("reports.source_view"), [this, current] {
      if (current()) { document_mode_ = false; document_->set_visible(false); }
    }).id;
    document_->set_viewport(viewport, previous_anchor, next_anchor);
    document_->set_visible(viewport != 0);
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

  ReportsCreateView create_;
  ReportsGenerationView generate_;
  std::unique_ptr<ProjectReports> reports_;
  std::unique_ptr<ReportDocumentHost> document_;
  bool document_mode_ = false;
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
