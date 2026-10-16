/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/workspace_transfer.hh"
#include "stk/app/shell.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/project_state.hh"
#include "stk/platform/file_dialog.hh"
#include "stk/ui/ui.hh"

#include <algorithm>

namespace stk::app {
using io::Json;
namespace {
std::string single_path(const std::string &value)
{
  const auto paths = platform::split_path_list(value);
  return paths.size() == 1 && platform::is_absolute_path(paths.front()) ? paths.front() : std::string();
}
bool valid_sha(const std::string &value)
{
  return value.size() == 64 && value.find_first_not_of("0123456789abcdef") == std::string::npos;
}
std::string bridge_session(const bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}
bool valid_preview(const Json &value)
{
  if (!value.is_object() || io::get_string(value, "format") != "stk.workspace/1" ||
      !valid_sha(io::get_string(value, "sha256")) || !value.contains("project") ||
      !(value.at("project").is_null() || value.at("project").is_object()) ||
      !value.contains("file_count") || !value.at("file_count").is_number_integer() || io::get_int(value, "file_count", -1) < 0 ||
      !value.contains("total_bytes") || !value.at("total_bytes").is_number_integer() || io::get_int(value, "total_bytes", -1) < 0 ||
      !value.contains("diagnostics") || !value.at("diagnostics").is_array() ||
      !value.contains("complete") || !value.at("complete").is_boolean()) { return false; }
  for (const auto &item : value.at("diagnostics")) {
    if (!item.is_object() || io::get_string(item, "code").empty()) { return false; }
  }
  return true;
}
}  // namespace

struct WorkspaceTransfer::Impl {
  enum class Mode { Export, Import, Open };
  AppShell &shell;
  std::weak_ptr<void> shell_alive;
  std::shared_ptr<void> alive = std::make_shared<int>(0);
  wm::Screen *screen = nullptr;
  Mode mode = Mode::Export;
  bool shown = false, writing = false, allow_incomplete = false;
  uint64_t generation = 0;
  bridge::Client *client = nullptr;
  std::string session, project_handle;
  int64_t revision = -1;
  std::string source, destination, archive, directory, error, notice, preview_source;
  Json preview;
  int diagnostic_page = 0;
  std::optional<bridge::Future<Json>> reading;

  explicit Impl(AppShell &value) : shell(value), shell_alive(value.lifetime()) {}
  ~Impl() { alive.reset(); if (reading) { reading->cancel(); } }
  bool owner() const { return !shell_alive.expired(); }
  void changed() { if (owner()) { shell.store().changed(); } }
  void cancel_read()
  {
    auto previous = std::move(reading); reading.reset();
    if (previous) { previous->cancel(); }
  }
  void scope()
  {
    client = shell.store().bridge(); session = bridge_session(client);
    const auto &project = shell.store().project().project();
    project_handle = project ? project->handle : std::string(); revision = project ? project->revision : -1;
  }
  bool current(uint64_t epoch) const
  {
    if (!owner() || !shown || generation != epoch || !screen || !shell.has_screen(screen) || shell.store().bridge() != client || bridge_session(client) != session) { return false; }
    const auto &project = shell.store().project().project();
    return project_handle == (project ? project->handle : std::string()) && revision == (project ? project->revision : -1);
  }
  void sync()
  {
    if (!shown || !owner() || writing) { return; }
    if (!screen || !shell.has_screen(screen)) { ++generation; cancel_read(); shown = false; return; }
    if (!current(generation)) {
      ++generation; cancel_read(); preview = nullptr; preview_source.clear(); scope();
      allow_incomplete = false; error = "workspace.transfer.changed"; notice.clear(); changed();
    }
  }
  void show(wm::Screen *target, Mode next)
  {
    if (!owner() || writing || !target || !shell.has_screen(target)) { return; }
    ++generation; cancel_read(); screen = target; mode = next; shown = true;
    preview = nullptr; preview_source.clear(); error.clear(); notice.clear(); diagnostic_page = 0; allow_incomplete = false; scope(); changed();
  }
  bool close()
  {
    if (writing && mode != Mode::Export) { return false; }
    ++generation; cancel_read(); shown = false; preview = nullptr; changed(); return true;
  }
  ui::Binding<std::string> bind(std::string &value)
  {
    auto *target = &value; const auto weak = std::weak_ptr<void>(alive);
    return {[weak, target] { return weak.expired() ? std::string() : *target; },
            [this, weak, target](std::string next) {
              if (weak.expired() || !shown || writing) { return; }
              const bool changed_path = *target != next;
              *target = std::move(next);
              if (target == &directory && changed_path) { allow_incomplete = false; }
              if (target == &source && single_path(source) != preview_source) { preview = nullptr; allow_incomplete = false; }
            }};
  }
  void browse(ui::Layout &row, std::string &value, platform::FileDialogMode dialog_mode, const char *title)
  {
    auto *dialog = shell.store().jobs().file_dialog;
    if (!dialog) { return; }
    auto *target = &value;
    row.button("browse", shell.store().tr("path.browse"), [this, weak = std::weak_ptr<void>(alive), epoch = generation, target, dialog_mode, title] {
      if (weak.expired() || !current(epoch) || writing) { return; }
      auto *dialog = shell.store().jobs().file_dialog; if (!dialog) { return; }
      platform::FileDialogRequest request; request.mode = dialog_mode;
      request.title = std::string(shell.store().tr(title));
      request.file_name = std::string_view(title) == "workspace.transfer.destination" ? "restored-workspace" : "workspace.stkworkspace";
      const auto previous = *target;
      dialog->open(request, [this, weak, epoch, target, previous](platform::FileDialogResult result) {
        if (weak.expired() || !current(epoch) || writing || *target != previous) { return; }
        if (!result.error.empty()) { error = result.error; }
        else if (!result.paths.empty()) {
          *target = result.paths.front();
          if (target == &source) { preview = nullptr; allow_incomplete = false; }
          if (target == &directory) { allow_incomplete = false; }
        }
        changed();
      });
    }).width(5).disable(writing);
  }
  void read_preview()
  {
    sync();
    if (!current(generation) || writing || reading) { return; }
    const auto path = single_path(source);
    if (path.empty()) { error = "workspace.transfer.path"; changed(); return; }
    if (!client || session.empty() || !client->hello_info() || !client->hello_info()->has_method("workspace.preview")) {
      error = "workspace.transfer.unavailable"; changed(); return;
    }
    error.clear(); notice.clear(); preview = nullptr; preview_source.clear(); allow_incomplete = false;
    const auto epoch = generation; const auto weak = std::weak_ptr<void>(alive);
    bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
    reading = client->call("workspace.preview", {{"path", path}}, options);
    reading->then([this, weak, epoch, path](bridge::Result<Json> result) {
      if (weak.expired() || !current(epoch)) { return; }
      reading.reset();
      if (path != single_path(source)) { error = "workspace.transfer.changed"; changed(); return; }
      if (!result) { error = result.error().describe(); }
      else if (!valid_preview(result.value())) { error = "workspace.transfer.invalid_response"; }
      else { preview = std::move(result.value()); preview_source = path; diagnostic_page = 0; }
      changed();
    });
    changed();
  }
  bool ready_preview() const
  {
    return preview.is_object() && preview_source == single_path(source) && (preview.value("complete", false) || allow_incomplete) && valid_sha(io::get_string(preview, "sha256"));
  }
  void transfer()
  {
    sync();
    if (!current(generation) || writing || reading) { return; }
    if (shell.text_input_active()) { error = "workspace.transfer.finish_input"; changed(); return; }
    if (mode != Mode::Export && shell.has_unsaved_changes()) { error = "app.unsaved"; changed(); return; }
    if (shell.store().project().busy() || shell.store().scripts().busy() || shell.store().has_open_result()) {
      error = "workspace.transfer.busy"; changed(); return;
    }
    const auto path = single_path(mode == Mode::Export ? archive : mode == Mode::Open ? directory : destination);
    if (path.empty()) { error = "workspace.transfer.path"; changed(); return; }
    if (mode == Mode::Import && !ready_preview()) { error = "workspace.transfer.changed"; changed(); return; }
    error.clear(); notice.clear(); writing = true;
    const auto weak = std::weak_ptr<void>(alive); const auto epoch = generation;
    const auto complete = [this, weak, epoch](bridge::Result<Json> result) {
      if (weak.expired()) { return; }
      writing = false;
      if (!shown || epoch != generation || !owner()) { return; }
      if (!result) { error = result.error().describe(); }
      else { notice = "workspace.transfer.done"; }
      scope(); changed();
    };
    bool accepted = false;
    if (mode == Mode::Export) { accepted = shell.export_workspace(path, complete); }
    else if (mode == Mode::Open) { accepted = shell.open_workspace(path, complete, allow_incomplete); }
    else { accepted = shell.import_workspace(preview_source, path, io::get_string(preview, "sha256"), complete, allow_incomplete); }
    if (!accepted) { writing = false; if (error.empty()) { error = "workspace.transfer.unavailable"; } }
    changed();
  }
  void draw(ui::Context &ui, wm::Screen *target)
  {
    sync();
    if (!shown || target != screen || !owner()) { return; }
    auto &store = shell.store();
    const char *title = mode == Mode::Export ? "workspace.transfer.export" : mode == Mode::Import ? "workspace.transfer.import" : "workspace.transfer.open";
    const auto epoch = generation; const auto weak = std::weak_ptr<void>(alive);
    const auto live = [this, weak, epoch] { return !weak.expired() && current(epoch); };
    auto &box = ui.modal("workspace_transfer", store.tr(title), [this, weak] { if (!weak.expired()) { close(); } },
        {.width_units = std::min(34.0f, std::max(16.0f, ui.window_size().x / ui.style().unit - 1))});
    if (!error.empty()) { box.paragraph(store.tr(error)); }
    if (!notice.empty()) { box.paragraph(store.tr(notice)); }
    if (writing || reading) { box.label(store.tr("workspace.transfer.working")); }
    if (mode == Mode::Export) {
      box.paragraph(store.tr("workspace.transfer.export_hint"));
      auto &row = box.prop(store.tr("workspace.transfer.archive")).row(true);
      row.text_field("workspace_export_path", bind(archive)).disable(writing);
      browse(row, archive, platform::FileDialogMode::SaveFile, title);
      box.button("workspace_export", store.tr(title), [this, live] { if (live()) { transfer(); } }).disable(writing || reading.has_value());
    }
    else if (mode == Mode::Open) {
      box.paragraph(store.tr("workspace.transfer.open_hint"));
      auto &row = box.prop(store.tr("workspace.transfer.directory")).row(true);
      row.text_field("workspace_open_directory", bind(directory)).disable(writing);
      browse(row, directory, platform::FileDialogMode::OpenFolder, title);
      box.checkbox("workspace_allow_incomplete", store.tr("workspace.transfer.allow_incomplete"),
        {[this, weak] { return !weak.expired() && allow_incomplete; },
         [this, live](bool value) { if (live() && !writing) { allow_incomplete = value; } }}).disable(writing);
      box.button("workspace_open", store.tr(title), [this, live] { if (live()) { transfer(); } }).disable(writing || reading.has_value());
    }
    else {
      auto &from = box.prop(store.tr("workspace.transfer.source")).row(true);
      from.text_field("workspace_import_source", bind(source)).disable(writing);
      browse(from, source, platform::FileDialogMode::OpenFiles, title);
      box.button("workspace_preview", store.tr("workspace.transfer.preview"), [this, live] { if (live()) { read_preview(); } }).disable(writing || reading.has_value());
      if (preview.is_object() && preview_source == single_path(source)) {
        box.label(io::get_string(preview, "format") + " · SHA256 " + io::get_string(preview, "sha256").substr(0, 12));
        if (preview.at("project").is_object()) {
          box.label(io::get_string(preview.at("project"), "name") + " · r" + std::to_string(io::get_int(preview.at("project"), "revision", -1)));
        }
        box.label(store.catalog().format("workspace.transfer.contents", {{"files", std::to_string(io::get_int(preview, "file_count", 0))}, {"bytes", std::to_string(io::get_int(preview, "total_bytes", 0))}}));
        if (!preview.value("complete", false)) {
          box.paragraph(store.tr("workspace.transfer.incomplete"));
          box.checkbox("workspace_allow_incomplete", store.tr("workspace.transfer.allow_incomplete"),
            {[this, weak] { return !weak.expired() && allow_incomplete; },
             [this, live](bool value) { if (live() && !writing) { allow_incomplete = value; } }}).disable(writing);
        }
        const auto issues = preview.at("diagnostics");
        if (!issues.empty()) {
          box.label(store.tr("workspace.transfer.diagnostics"));
          const int pages = (int(issues.size()) + 3) / 4; diagnostic_page = std::clamp(diagnostic_page, 0, std::max(0, pages - 1));
          for (int i = diagnostic_page * 4; i < std::min(int(issues.size()), diagnostic_page * 4 + 4); ++i) {
            const auto &item = issues[size_t(i)]; box.paragraph(io::get_string(item, "code") + " · " + io::get_string(item, "path"));
          }
          if (pages > 1) {
            auto &page = box.row(true);
            page.button("workspace_diagnostics_prev", "‹", [this, live] { if (live() && diagnostic_page > 0) { --diagnostic_page; } }).width(2).disable(diagnostic_page == 0);
            page.label(std::to_string(diagnostic_page + 1) + " / " + std::to_string(pages));
            page.button("workspace_diagnostics_next", "›", [this, live, pages] { if (live() && diagnostic_page + 1 < pages) { ++diagnostic_page; } }).width(2).disable(diagnostic_page + 1 == pages);
          }
        }
      }
      box.paragraph(store.tr("workspace.transfer.new_directory"));
      auto &to = box.prop(store.tr("workspace.transfer.destination")).row(true);
      to.text_field("workspace_import_destination", bind(destination)).disable(writing);
      browse(to, destination, platform::FileDialogMode::SaveFile, "workspace.transfer.destination");
      box.button("workspace_import", store.tr(title), [this, live] { if (live()) { transfer(); } }).disable(writing || reading.has_value() || !ready_preview());
    }
    box.button("workspace_transfer_close", store.tr("workspace.transfer.cancel"), [this, weak] { if (!weak.expired()) { close(); } })
        .disable(writing && mode != Mode::Export);
  }
};

WorkspaceTransfer::WorkspaceTransfer(AppShell &shell) : impl_(std::make_unique<Impl>(shell)) {}
WorkspaceTransfer::~WorkspaceTransfer() = default;
void WorkspaceTransfer::show(wm::Screen *screen, bool importing) { impl_->show(screen, importing ? Impl::Mode::Import : Impl::Mode::Export); }
void WorkspaceTransfer::show_open(wm::Screen *screen) { impl_->show(screen, Impl::Mode::Open); }
void WorkspaceTransfer::draw(ui::Context &ui, wm::Screen *screen) { impl_->draw(ui, screen); }
bool WorkspaceTransfer::close() { return impl_->close(); }
bool WorkspaceTransfer::visible() const { return impl_->shown; }
bool WorkspaceTransfer::busy() const { return impl_->writing || impl_->reading.has_value(); }
const std::string &WorkspaceTransfer::error() const { return impl_->error; }
const Json &WorkspaceTransfer::preview() const { return impl_->preview; }
}  // namespace stk::app
