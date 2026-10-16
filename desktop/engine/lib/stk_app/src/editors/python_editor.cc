/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <algorithm>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <utility>

#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/platform/file_dialog.hh"
#include "path_picker.hh"

namespace stk::app {
namespace {

class PythonEditor final : public Editor {
 public:
  explicit PythonEditor(const EditorType &type) : Editor(type) {}

  bool has_unsaved_changes() const override { return source_ != baseline_ || pending_io_; }

  bool navigate(const nlohmann::json &target, const std::weak_ptr<void> &, std::string &reason) override
  {
    if (!target.is_object() || target.size() != 1 || !target.contains("path") || !target["path"].is_string()) {
      return false;
    }
    const auto path = target["path"].get<std::string>();
    if (!valid_path(path)) { reason = "script.file_invalid"; return false; }
    if (path == source_path_) { return true; }
    if (has_unsaved_changes()) { reason = "script.navigate_unsaved"; return false; }
    ++generation_;
    pending_open_ = path;
    return true; // The next draw reads this document; navigation never runs it.
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    auto &state = ctx.store.scripts();
    state.sync();
    const auto current = guard();
    row.button("python_run", ctx.tr("script.run_buffer"), [this, &state, current] {
      if (current() && !pending_io_) { state.execute(source_); }
    }).disable(!state.ready() || state.busy() || pending_io_);
    const auto run_id = state.status().contains("run") && state.status()["run"].is_object() ?
        io::get_string(state.status()["run"], "id") : std::string();
    row.button("python_interrupt", ctx.tr(state.busy() ? "script.interrupt" : "script.reset"),
               [&state, current, session = state.session(), run_id, was_busy = state.busy()] {
      if (!current() || state.session() != session || state.busy() != was_busy) { return; }
      const auto live_run = state.status().contains("run") && state.status()["run"].is_object() ?
          io::get_string(state.status()["run"], "id") : std::string();
      if (live_run == run_id) { state.interrupt(); }
    }).disable(!state.ready());
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &state = ctx.store.scripts();
    state.sync();
    if (pending_io_ && pending_session_ != state.session()) {
      ++generation_; pending_io_ = false; notice_ = "script.file_session_changed";
    }
    if (!pending_open_.empty() && !pending_io_ && state.files_supported()) {
      const auto path = std::exchange(pending_open_, {});
      open_file(path, ctx.store);
    }
    if (!state.ready()) { layout.paragraph(ctx.tr("script.bridge_required")); }
    if (!state.error().empty()) { layout.paragraph(state.error()); }
    if (!file_error_.empty()) { layout.paragraph(file_error_); }
    if (!notice_.empty()) { layout.paragraph(ctx.tr(notice_)); }
    auto &status = layout.row();
    status.label(ctx.tr("script.state." + io::get_string(state.status(), "state", "ready"))).width(6);
    status.label(source_path_.empty() ? ctx.tr("script.untitled") : std::string_view(source_path_));
    status.label(ctx.tr(source_ != baseline_ ? "script.modified" : "script.saved")).width(6);
    const auto &project = ctx.store.project().project();
    status.label(project ? project->name : std::string(ctx.tr("script.no_project")));

    const auto current = guard();
    auto *store = &ctx.store;
    const bool unavailable = !state.files_supported() || pending_io_;
    auto &choose = layout.row(true);
    choose.text_field("python_path", ui::bind(path_), {.placeholder = std::string(ctx.tr("script.path_hint"))}).disable(pending_io_);
    path_picker_.button(choose, ctx, "python_browse", &path_, {
        .title_key = "script.file_dialog",
        .still_current = [this, current, path = path_] { return current() && path_ == path && !pending_io_; }});
    choose.button("python_open", ctx.tr("script.open_file"), [this, store, current] {
      if (current()) { open_file(path_, *store); }
    }).disable(unavailable || path_.empty());
    auto &files = layout.row(true);
    files.button("python_new", ctx.tr("script.new"), [this, current] {
      if (!current() || has_unsaved_changes()) { return; }
      ++generation_; source_.clear(); baseline_.clear(); source_path_.clear(); version_.clear();
      path_.clear(); notice_.clear(); file_error_.clear(); history_ = -1;
    }).disable(has_unsaved_changes());
    files.button("python_save", ctx.tr("script.save"), [this, store, current] {
      if (current()) { save_file(source_path_.empty() ? path_ : source_path_, *store); }
    }).disable(unavailable || (source_path_.empty() && path_.empty()));
    files.button("python_save_as", ctx.tr("script.save_as"), [this, store, current] {
      if (!current()) { return; }
      auto *dialog = store->jobs().file_dialog;
      if (!dialog) { save_file(path_, *store); return; }
      platform::FileDialogRequest request;
      request.mode = platform::FileDialogMode::SaveFile;
      request.title = std::string(store->tr("script.save_as"));
      request.file_name = "program.py";
      const auto text = source_;
      dialog->open(request, [this, current, store, text](platform::FileDialogResult result) {
        if (!current() || source_ != text || pending_io_) { return; }
        if (!result.error.empty()) { file_error_ = result.error; }
        else if (!result.paths.empty()) { save_file(result.paths.front(), *store); }
        store->changed();
      });
    }).disable(unavailable || (!PathPicker::available(ctx.store) && path_.empty()));
    auto &disk = layout.row(true);
    disk.button("python_discard", ctx.tr("script.discard"), [this, current] {
      if (!current() || pending_io_) { return; }
      ++generation_; source_ = baseline_; notice_.clear(); file_error_.clear();
    }).disable(source_ == baseline_ || pending_io_);
    disk.button("python_reload", ctx.tr("script.reload"), [this, store, current] {
      if (current()) { open_file(source_path_, *store); }
    }).disable(unavailable || source_path_.empty() || source_ != baseline_);
    disk.button("python_run_file", ctx.tr("script.run_file"), [this, &state, current] {
      if (current() && source_ == baseline_ && !version_.empty()) { state.execute_file(source_path_, version_); }
    }).disable(!state.ready() || state.busy() || pending_io_ || source_path_.empty() || version_.empty() || source_ != baseline_);
    path_picker_.draw_error(layout);
    layout.label(ctx.tr("script.buffer_hint"));

    const float unit = ctx.ui ? ctx.ui->style().unit : 20.0f;
    const float line_height = ctx.ui ? ctx.ui->style().line_height : 16.0f;
    const float available = ctx.draw ? float(ctx.draw->rect.height()) : 500.0f;
    const float usable = std::max(6.0f * line_height, available - 10.0f * unit);
    const float output_units = output_open_ ? std::max(3.0f, usable * float(output_share_) / unit) : 0.0f;
    ui::TextFieldOptions options;
    options.mono = true;
    options.max_length = 262144;
    options.visible_lines = std::max(6, int((usable - output_units * unit) / line_height));
    options.on_submit = [this, &state, current] { if (current() && !pending_io_) { state.execute(source_); } };
    layout.text_area("python_source", ui::bind(source_), std::move(options)).disable(pending_io_);

    auto &output = layout.row(true);
    output.checkbox("python_output_open", ctx.tr("script.output"), ui::bind(output_open_)).width(6);
    if (output_open_) {
      output.slider("python_output_height", ctx.tr("script.output_height"), ui::bind(output_share_),
                    {.min = 0.15, .max = 0.6, .step = 0.05, .precision = 2});
    }
    output.button("python_clear", ctx.tr("script.clear"), [&state, current] {
      if (current()) { state.clear_output(); }
    }).width(6);
    if (output_open_) { layout.log_view("python_output", state.output(), output_units); }
    if (auto *history = layout.panel("python_history", ctx.tr("script.history"), false)) {
      auto &row = history->row();
      const auto count = int(state.history().size());
      row.button("python_previous", ctx.tr("script.previous"), [this, &state, current] {
        if (!current() || pending_io_ || state.history().empty()) { return; }
        const auto &items = state.history();
        history_ = history_ < 0 ? int(items.size()) - 1 : std::max(0, history_ - 1);
        source_ = items[size_t(history_)];
      }).disable(count == 0 || history_ == 0 || pending_io_);
      row.button("python_next", ctx.tr("script.next"), [this, &state, current] {
        if (!current() || pending_io_ || history_ < 0 || history_ + 1 >= int(state.history().size())) { return; }
        history_ = std::min(int(state.history().size()) - 1, history_ + 1);
        source_ = state.history()[size_t(history_)];
      }).disable(history_ < 0 || history_ + 1 >= count || pending_io_);
      row.button("python_help", ctx.tr("script.api_help"), [&state, current] {
        if (current()) { state.execute("stk.help()"); }
      })
          .disable(!state.ready() || state.busy());
    }
  }

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    if (paths.size() != 1 || !valid_path(paths.front()) || pending_io_) { return false; }
    path_ = paths.front();
    ctx.store.changed();
    // A drop selects a path. Only Open reads it; only Run executes it.
    return true;
  }

  std::vector<std::string> workspace_resource_paths() const override
  {
    return valid_path(source_path_) ? std::vector<std::string>{source_path_} : std::vector<std::string>{};
  }

  nlohmann::json save_state() const override
  {
    return {{"source", source_}, {"baseline", baseline_}, {"path", path_}, {"source_path", source_path_},
            {"version", version_}, {"output_open", output_open_}, {"output_share", output_share_}};
  }

  bool load_state(const nlohmann::json &state) override
  {
    if (!state.is_object()) { return false; }
    for (const char *key : {"source", "baseline", "path", "source_path", "version"}) {
      if (state.contains(key) && (!state[key].is_string() || state[key].get_ref<const std::string &>().size() > 262144)) { return false; }
    }
    if (state.contains("output_open") && !state["output_open"].is_boolean()) { return false; }
    if (state.contains("output_share") && (!state["output_share"].is_number() || !std::isfinite(state["output_share"].get<double>()))) { return false; }
    ++generation_; pending_io_ = false; pending_open_.clear();
    source_ = state.value("source", source_);
    // Old layouts did not preserve a disk baseline. Keep their draft unsaved.
    baseline_ = state.value("baseline", state.contains("source") ? std::string() : source_);
    path_ = state.value("path", path_);
    source_path_ = state.value("source_path", std::string());
    version_ = state.value("version", std::string());
    output_open_ = state.value("output_open", true);
    output_share_ = std::clamp(state.value("output_share", 0.25), 0.15, 0.6);
    notice_ = source_path_.empty() ? std::string() : "script.restored_file";
    return true;
  }

 private:
  static bool valid_path(const std::string &path)
  {
    if (path.empty() || path.size() > 32768 || path.find('\0') != std::string::npos) { return false; }
    try {
      const auto file = std::filesystem::u8path(path);
      auto suffix = file.extension().string();
      std::transform(suffix.begin(), suffix.end(), suffix.begin(), [](unsigned char c) { return char(std::tolower(c)); });
      return file.is_absolute() && suffix == ".py";
    }
    catch (const std::exception &) { return false; }
  }

  std::function<bool()> guard() const
  {
    return [this, weak = lifetime(), generation = generation_] { return !weak.expired() && generation == generation_; };
  }

  void open_file(const std::string &path, AppStore &app)
  {
    if (has_unsaved_changes()) { notice_ = "script.navigate_unsaved"; return; }
    if (!valid_path(path)) { notice_ = "script.file_invalid"; return; }
    auto &state = app.scripts();
    const auto current = guard();
    auto *store = &app;
    const auto session = state.session();
    pending_io_ = true; pending_session_ = session; notice_.clear(); file_error_.clear();
    if (!state.read_file(path, [this, current, store, session](const auto &result) {
      if (!current() || store->scripts().session() != session) { return; }
      pending_io_ = false;
      if (!result.ok()) { file_error_ = result.error().describe(); }
      else {
        source_ = io::get_string(result.value(), "source"); baseline_ = source_;
        source_path_ = io::get_string(result.value(), "path"); path_ = source_path_;
        version_ = io::get_string(result.value(), "version"); history_ = -1; ++generation_;
      }
      store->changed();
    })) { pending_io_ = false; notice_ = "script.files_unsupported"; }
  }

  void save_file(const std::string &path, AppStore &app)
  {
    if (pending_io_) { return; }
    if (!valid_path(path)) { notice_ = "script.file_invalid"; return; }
    auto &state = app.scripts();
    const auto current = guard();
    auto *store = &app;
    const auto session = state.session(), text = source_;
    pending_io_ = true; pending_session_ = session; notice_.clear(); file_error_.clear();
    if (!state.write_file(path, text, path == source_path_ ? version_ : std::string(),
        [this, current, store, session, text](const auto &result) {
      if (!current() || store->scripts().session() != session) { return; }
      pending_io_ = false;
      if (!result.ok()) { file_error_ = result.error().describe(); }
      else {
        source_path_ = io::get_string(result.value(), "path"); path_ = source_path_;
        version_ = io::get_string(result.value(), "version"); baseline_ = text; ++generation_;
      }
      store->changed();
    })) { pending_io_ = false; notice_ = "script.files_unsupported"; }
  }

  std::string source_ = "print('Hello, STK')\n2 + 2";
  std::string baseline_ = source_, path_, source_path_, version_, pending_open_, pending_session_, notice_, file_error_;
  PathPicker path_picker_;
  uint64_t generation_ = 0;
  bool pending_io_ = false, output_open_ = true;
  double output_share_ = 0.25;
  int history_ = -1;
};

}  // namespace

std::unique_ptr<Editor> make_python_editor(const EditorType &type)
{
  return std::make_unique<PythonEditor>(type);
}

}  // namespace stk::app
