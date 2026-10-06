/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <algorithm>

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

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    auto &state = ctx.store.scripts();
    state.sync();
    row.button("python_run", ctx.tr("script.run"), [this, &state] { state.execute(source_); })
        .width(4).disable(!state.ready() || state.busy());
    row.button("python_interrupt", ctx.tr(state.busy() ? "script.interrupt" : "script.reset"),
               [&state] { state.interrupt(); }).width(4).disable(!state.ready());
    row.button("python_clear", ctx.tr("script.clear"), [&state] { state.clear_output(); }).width(6);
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &state = ctx.store.scripts();
    state.sync();
    if (!state.ready()) { layout.paragraph(ctx.tr("script.bridge_required")); }
    if (!state.error().empty()) { layout.paragraph(state.error()); }
    auto &status = layout.row();
    const auto phase = io::get_string(state.status(), "state", "ready");
    status.label(ctx.tr("script.state." + phase)).width(6);
    const auto &project = ctx.store.project().project();
    status.label(project ? project->name : std::string(ctx.tr("script.no_project")));
    if (state.status().contains("run") && state.status()["run"].is_object()) {
      status.label(ctx.tr("script.run_state." + io::get_string(state.status()["run"], "state"))).width(8);
    }
    const float unit = ctx.ui ? ctx.ui->style().unit : 20.0f;
    const float line_height = ctx.ui ? ctx.ui->style().line_height : 16.0f;
    const float available = ctx.draw ? float(ctx.draw->rect.height()) : 500.0f;
    const int input_lines = std::clamp(int(available * 0.35f / line_height), 6, 20);
    const float output_units = std::max(6.0f, (available - input_lines * line_height) / unit - 8.0f);
    layout.log_view("python_output", state.output(), output_units);
    layout.label(ctx.tr("script.input_hint"));
    ui::TextFieldOptions options;
    options.mono = true;
    options.max_length = 262144;
    options.visible_lines = input_lines;
    options.on_submit = [this, &state] { state.execute(source_); };
    layout.text_area("python_source", ui::bind(source_), std::move(options));
    auto &history = layout.row();
    const auto count = int(state.history().size());
    history.button("python_previous", ctx.tr("script.previous"), [this, &state] {
      const auto &items = state.history();
      history_ = history_ < 0 ? int(items.size()) - 1 : std::max(0, history_ - 1);
      source_ = items[size_t(history_)];
    }).disable(count == 0 || history_ == 0);
    history.button("python_next", ctx.tr("script.next"), [this, &state] {
      history_ = std::min(int(state.history().size()) - 1, history_ + 1);
      source_ = state.history()[size_t(history_)];
    }).disable(history_ < 0 || history_ + 1 >= count);
    history.button("python_help", ctx.tr("script.api_help"), [&state] { state.execute("stk.help()"); })
        .disable(!state.ready() || state.busy());
    if (auto *file = layout.panel("python_file", ctx.tr("script.file"), !path_.empty())) {
      auto &choose = file->row(true);
      choose.text_field("python_path", ui::bind(path_), {.placeholder = std::string(ctx.tr("script.path_hint"))});
      path_picker_.button(choose, ctx, "python_browse", &path_, {.title_key = "script.file_dialog"});
      path_picker_.draw_error(*file);
      file->button("python_run_file", ctx.tr("script.run_file"), [this, &state] {
        const auto paths = platform::split_path_list(path_);
        if (paths.size() == 1) { state.execute_file(paths.front()); }
      }).disable(!state.ready() || state.busy() || path_.empty());
      file->paragraph(ctx.tr("script.file_hint"));
    }
  }

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    if (paths.size() != 1) { return false; }
    path_ = paths.front();
    ctx.store.changed();
    // A drop selects a path only. Running arbitrary code always needs a separate explicit action.
    return true;
  }

  nlohmann::json save_state() const override { return {{"source", source_}, {"path", path_}}; }
  bool load_state(const nlohmann::json &state) override
  {
    if (!state.is_object()) { return false; }
    for (const char *key : {"source", "path"}) {
      if (state.contains(key) && (!state[key].is_string() || state[key].get_ref<const std::string &>().size() > (1 << 20))) {
        return false;
      }
    }
    source_ = state.value("source", source_);
    path_ = state.value("path", path_);
    return true;
  }

 private:
  std::string source_ = "print('Hello, STK')\n2 + 2";
  std::string path_;
  PathPicker path_picker_;
  int history_ = -1;
};

}  // namespace

std::unique_ptr<Editor> make_python_editor(const EditorType &type)
{
  return std::make_unique<PythonEditor>(type);
}

}  // namespace stk::app
