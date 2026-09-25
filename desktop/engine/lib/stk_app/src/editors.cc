/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * WP3 placeholder editors. Each one draws with stk_ui and says (zh / en) what it will contain;
 * the structure they show (tables, log views, panels, toolbar and sidebar) is what WP9 / WP10
 * fill in. Jobs and Transfers accept file drops (listed as pending uploads, not persisted);
 * the Viewer reports dropped .stkp files.
 */

#include <algorithm>
#include <cmath>

#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/ui/ui.hh"

#include "app_theme.hh"

namespace stk::app {

namespace {

/** Height in UI units that fills what is left of the main region below `used_units`. */
float fill_units(const EditorContext &ctx, const float used_units, const float min_units = 4.0f)
{
  if (!ctx.draw || !ctx.ui) {
    return min_units;
  }
  const float unit = std::max(1.0f, ctx.ui->style().unit);
  return std::max(min_units, float(ctx.draw->rect.height()) / unit - used_units);
}

/** Fixed width (UI units) fitting a button text. */
float fit_units(const EditorContext &ctx, std::string_view text)
{
  if (!ctx.ui) {
    return 4.0f;
  }
  const ui::Style &st = ctx.ui->style();
  return std::max(2.0f, (ctx.ui->measurer().width(text, st.font) + 2.0f * st.text_margin) / std::max(1.0f, st.unit));
}

std::string file_name(const std::string &path)
{
  const size_t p = path.find_last_of("/\\");
  return p == std::string::npos ? path : path.substr(p + 1);
}

class PlaceholderEditor : public Editor {
 public:
  PlaceholderEditor(const EditorType &type, const char *placeholder_key, ui::Color background)
      : Editor(type), placeholder_key_(placeholder_key), background_(background)
  {
  }

  ui::Color main_background(const ui::Theme & /*theme*/) const override
  {
    return background_;
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    intro(l, ctx);
    draw_body(l, ctx);
  }

 protected:
  void intro(ui::Layout &l, EditorContext &ctx)
  {
    l.label(ctx.tr(type().title_key));
    l.paragraph(ctx.tr(placeholder_key_));
    l.label(ctx.tr("editor.placeholder.note")).disable();
    l.separator();
  }
  virtual void draw_body(ui::Layout & /*l*/, EditorContext & /*ctx*/) {}

  const char *placeholder_key_;
  ui::Color background_;
};

/* -------------------------------------------------------------------- */

/** Dropped files shown as pending uploads (per area, in memory only). */
class DropListEditor : public PlaceholderEditor {
 public:
  using PlaceholderEditor::PlaceholderEditor;

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    for (const std::string &p : paths) {
      if (dropped_.size() >= 200) {
        break;
      }
      dropped_.push_back(p);
    }
    version_++;
    ctx.store.log(ctx.store.catalog().format(
        "app.drop.queued",
        {{"count", std::to_string(paths.size())}, {"editor", std::string(ctx.tr(type().title_key))}}));
    return true;
  }

 protected:
  std::vector<std::string> dropped_;
  uint64_t version_ = 0;
};

class JobsEditor final : public DropListEditor {
 public:
  explicit JobsEditor(const EditorType &type)
      : DropListEditor(type, "editor.jobs.placeholder", theme::kListBack)
  {
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    const std::string_view label = ctx.tr("editor.jobs.submit");
    row.button("submit", label, []() {}).width(fit_units(ctx, label)).disable().tip(ctx.tr("editor.placeholder.note"));
  }

  void draw_body(ui::Layout &l, EditorContext &ctx) override
  {
    ui::TableSpec t;
    t.columns = {{std::string(ctx.tr("editor.jobs.col.name")), 9.0f},
                 {std::string(ctx.tr("editor.jobs.col.state")), 4.5f},
                 {std::string(ctx.tr("editor.jobs.col.submitted")), 5.0f},
                 {std::string(ctx.tr("editor.jobs.col.duration")), 4.0f, true, true}};
    t.rows = 0;
    t.visible_rows = 5.0f;
    l.table("tasks", std::move(t));
    if (!dropped_.empty()) {
      l.label(ctx.store.catalog().format("editor.jobs.pending_uploads", {{"count", std::to_string(dropped_.size())}}));
      ui::ListSpec spec;
      spec.count = int(dropped_.size());
      spec.text = [this](int i) { return file_name(dropped_[size_t(i)]); };
      spec.rows = std::min(6.0f, float(dropped_.size()));
      l.virtual_list("pending", std::move(spec));
    }
  }
};

class ViewerEditor final : public PlaceholderEditor {
 public:
  explicit ViewerEditor(const EditorType &type)
      : PlaceholderEditor(type, "editor.viewer.placeholder", theme::kViewerBack)
  {
  }

  bool has_toolbar() const override
  {
    return true;
  }
  bool has_sidebar() const override
  {
    return true;
  }

  void draw_toolbar(ui::Layout &l, EditorContext &ctx) override
  {
    for (const char *key : {"editor.viewer.tool.orbit", "editor.viewer.tool.pan", "editor.viewer.tool.zoom",
                            "editor.viewer.tool.pick"})
    {
      const std::string_view label = ctx.tr(key);
      /* First character only: a narrow tool column until the icon set exists. */
      size_t n = 1;
      while (n < label.size() && (uint8_t(label[n]) & 0xc0) == 0x80) {
        n++;
      }
      l.button(key, label.substr(0, n), []() {}).disable().tip(label);
    }
  }

  void draw_sidebar(ui::Layout &l, EditorContext &ctx) override
  {
    if (ui::Layout *p = l.panel("layers", ctx.tr("editor.viewer.panel.layers"))) {
      p->paragraph(ctx.tr("editor.viewer.panel.layers.body"));
    }
    if (ui::Layout *p = l.panel("camera", ctx.tr("editor.viewer.panel.camera"))) {
      p->paragraph(ctx.tr("editor.viewer.panel.camera.body"));
    }
    if (ui::Layout *p = l.panel("steps", ctx.tr("editor.viewer.panel.steps"), false)) {
      p->paragraph(ctx.tr("editor.viewer.panel.steps.body"));
    }
  }

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    int n = 0;
    for (const std::string &p : paths) {
      if (p.size() > 5 && p.compare(p.size() - 5, 5, ".stkp") == 0) {
        ctx.store.log(ctx.store.catalog().format("editor.viewer.drop_stkp", {{"file", file_name(p)}}));
        n++;
      }
    }
    return n > 0;
  }
};

class PropertiesEditor final : public PlaceholderEditor {
 public:
  explicit PropertiesEditor(const EditorType &type)
      : PlaceholderEditor(type, "editor.properties.placeholder", theme::kPropertiesBack)
  {
  }

  void draw_body(ui::Layout &l, EditorContext &ctx) override
  {
    for (const char *key : {"editor.properties.panel.preset", "editor.properties.panel.parameters",
                            "editor.properties.panel.export"})
    {
      if (ui::Layout *p = l.panel(key, ctx.tr(key), false)) {
        p->label(ctx.tr("editor.placeholder.note")).disable();
      }
    }
  }
};

class LogEditor final : public PlaceholderEditor {
 public:
  LogEditor(const EditorType &type, const char *key, bool bridge)
      : PlaceholderEditor(type, key, theme::kListBack), bridge_(bridge)
  {
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    /* One line of description; the log view fills the rest of the region. */
    l.label(ctx.tr(placeholder_key_)).tip(ctx.tr(placeholder_key_));
    ui::LogBuffer &log = bridge_ ? ctx.store.bridge_log() : ctx.store.app_log();
    l.log_view("log", log, fill_units(ctx, 2.0f));
  }

 private:
  bool bridge_;
};

class ProbeEditor final : public PlaceholderEditor {
 public:
  explicit ProbeEditor(const EditorType &type)
      : PlaceholderEditor(type, "editor.probe.placeholder", theme::kPropertiesBack)
  {
  }

  void draw_body(ui::Layout &l, EditorContext &ctx) override
  {
    l.label(ctx.tr("editor.probe.empty")).disable();
  }
};

class TransfersEditor final : public DropListEditor {
 public:
  explicit TransfersEditor(const EditorType &type)
      : DropListEditor(type, "editor.transfers.placeholder", theme::kListBack)
  {
  }

  void draw_body(ui::Layout &l, EditorContext &ctx) override
  {
    ui::TableSpec t;
    t.columns = {{std::string(ctx.tr("editor.transfers.col.file")), 10.0f},
                 {std::string(ctx.tr("editor.transfers.col.direction")), 4.0f},
                 {std::string(ctx.tr("editor.transfers.col.progress")), 4.0f, true, true},
                 {std::string(ctx.tr("editor.transfers.col.state")), 5.0f}};
    t.rows = int(dropped_.size());
    const std::string up(ctx.tr("editor.transfers.upload"));
    const std::string pending(ctx.tr("editor.transfers.pending"));
    t.cell = [this, up, pending](int row, int col) -> std::string {
      switch (col) {
        case 0: return file_name(dropped_[size_t(row)]);
        case 1: return up;
        case 2: return "0";
        default: return pending;
      }
    };
    t.data_version = version_;
    t.visible_rows = 5.0f;
    l.table("transfers", std::move(t));
  }
};

template<class T> EditorType make_type(const char *id, const char *title_key)
{
  return {id, title_key, [](const EditorType &type) { return std::make_unique<T>(type); }};
}

}  // namespace

void register_builtin_editors(EditorRegistry &registry)
{
  registry.add(make_type<JobsEditor>(kEditorJobs, "editor.jobs.title"));
  registry.add(make_type<ViewerEditor>(kEditorViewer, "editor.viewer.title"));
  registry.add(make_type<PropertiesEditor>(kEditorProperties, "editor.properties.title"));
  registry.add({kEditorLogs, "editor.logs.title", [](const EditorType &type) {
                  return std::make_unique<LogEditor>(type, "editor.logs.placeholder", false);
                }});
  registry.add(make_type<ProbeEditor>(kEditorProbe, "editor.probe.title"));
  registry.add(make_type<TransfersEditor>(kEditorTransfers, "editor.transfers.title"));
  registry.add({kEditorBridgeLog, "editor.bridge_log.title", [](const EditorType &type) {
                  return std::make_unique<LogEditor>(type, "editor.bridge_log.placeholder", true);
                }});
}

}  // namespace stk::app
