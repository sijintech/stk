/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "viewer_common.hh"

#include <algorithm>
#include <cmath>
#include <filesystem>

#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "stk/ui/ui.hh"
#include "stk/viewer/format.hh"
#include "stk/wm/window.hh"

namespace stk::app::viewer_ui {

float fit_units(const EditorContext &ctx, std::string_view text, const float min_units)
{
  if (!ctx.ui) {
    return std::max(min_units, 4.0f);
  }
  const ui::Style &st = ctx.ui->style();
  return std::max(min_units,
                  (ctx.ui->measurer().width(text, st.font) + 2.0f * st.text_margin) / std::max(1.0f, st.unit));
}

float fill_units(const EditorContext &ctx, const float used_units, const float min_units)
{
  if (!ctx.draw || !ctx.ui) {
    return min_units;
  }
  const float unit = std::max(1.0f, ctx.ui->style().unit);
  return std::max(min_units, float(ctx.draw->rect.height()) / unit - used_units);
}

std::string num(const double value, std::string_view spec)
{
  return viewer::format_label(value, spec);
}

std::string vec3(const std::array<double, 3> &v, std::string_view spec)
{
  return num(v[0], spec) + ", " + num(v[1], spec) + ", " + num(v[2], spec);
}

std::string step_text(const io::Json &step)
{
  if (step.is_null()) {
    return "\xe2\x80\x94"; /* — */
  }
  if (step.is_string()) {
    return step.get<std::string>();
  }
  if (step.is_number_integer()) {
    return std::to_string(step.get<int64_t>());
  }
  if (step.is_number()) {
    return num(step.get<double>(), "g");
  }
  return step.dump();
}

std::string preset_label(const EditorContext &ctx, const PresetInfo &preset)
{
  return std::string(ctx.store.catalog().tr_or("props.preset." + preset.id, preset.name.empty() ? preset.id : preset.name));
}

wm::WindowManager *window_manager(const EditorContext &ctx)
{
  return ctx.area.shell().window_manager();
}

void pump(EditorContext &ctx)
{
  ViewerState &vs = ctx.store.viewer();
  if (std::optional<OpenResultRequest> req = ctx.store.take_open_result()) {
    vs.open(*req);
  }
  const double wake = vs.pump();
  if (!std::isfinite(wake)) {
    return;
  }
  wm::WindowManager *wm = window_manager(ctx);
  if (!wm) {
    return;
  }
  const double now = vs.now();
  if (vs.wake_scheduled > now && vs.wake_scheduled <= wake + 1e-4) {
    return; /* an earlier (or the same) wake-up is already scheduled */
  }
  vs.wake_scheduled = wake;
  const uint64_t delay = uint64_t(std::clamp((wake - now) * 1000.0 + 1.0, 1.0, 60000.0));
  AppStore *store = &ctx.store;
  wm->add_timer(delay, 0, [store]() { store->changed(); });
}

void draw_eval_status(ui::Layout &l, EditorContext &ctx, const bool compact)
{
  ViewerState &vs = ctx.store.viewer();
  const EvalProgress &p = vs.progress();
  if (p.running) {
    ui::Layout &row = l.row(false);
    std::string text = ctx.store.catalog().format(
        "viewer.status.evaluating",
        {{"node", p.node.empty() ? std::string("\xe2\x80\xa6") : p.node},
         {"done", std::to_string(p.finished + p.cached)},
         {"total", p.expected > 0 ? std::to_string(p.expected) : std::string("?")}});
    row.progress(p.fraction(), text).tip(p.message.empty() ? text : p.message);
    const std::string_view cancel = ctx.tr("viewer.action.cancel");
    row.button("eval_cancel", cancel, [&vs]() { vs.cancel_evaluation(); }).width(fit_units(ctx, cancel));
    return;
  }
  if (!vs.pending_edit().empty() && vs.source().evaluates()) {
    l.label(ctx.tr(vs.auto_evaluate ? "viewer.status.pending" : "viewer.status.pending_manual"));
    return;
  }
  if (!vs.eval_error().empty()) {
    l.label(ctx.store.catalog().format("viewer.status.error", {{"error", vs.eval_error()}})).tip(vs.eval_error());
    return;
  }
  const std::optional<EvalRecord> &rec = vs.last_eval();
  if (!rec) {
    return;
  }
  std::string text;
  if (rec->from_cache) {
    text = std::string(ctx.tr(vs.source().evaluates() ? "viewer.status.from_cache" : "viewer.status.loaded"));
  }
  else {
    text = ctx.store.catalog().format(
        "viewer.status.evaluated",
        {{"count", std::to_string(rec->evaluated.size())},
         {"data", std::to_string(rec->data_nodes.size())},
         {"seconds", num(rec->seconds, ".2f")}});
  }
  std::string tip;
  if (!rec->evaluated.empty()) {
    tip = std::string(ctx.tr("viewer.status.nodes")) + " ";
    for (size_t i = 0; i < rec->evaluated.size(); i++) {
      tip += (i ? ", " : "") + rec->evaluated[i];
    }
    tip += "\n" + ctx.store.catalog().format("viewer.status.cache",
                                             {{"hits", std::to_string(rec->cache_hits)},
                                              {"misses", std::to_string(rec->cache_misses)}});
  }
  ui::Widget &w = l.label(text);
  if (!tip.empty()) {
    w.tip(tip);
  }
  (void)compact;
}

namespace {

void open_dialog(EditorContext &ctx, ViewerState &vs)
{
  ui::ModalOptions mo;
  mo.width_units = 24.0f;
  ui::Layout &m = ctx.ui->modal("viewer_open", ctx.tr("viewer.open.title"), [&vs]() { vs.open_dialog = false; }, mo);
  m.paragraph(ctx.tr("viewer.open.body"));
  /* TODO(WP9): a native file dialog (stk_platform) next to the path field. */
  ui::TextFieldOptions to;
  to.placeholder = std::string(ctx.tr("viewer.open.placeholder"));
  m.prop(ctx.tr("viewer.open.path")).text_field("path", ui::bind(vs.open_dialog_path), to);
  if (!vs.open_error().empty()) {
    m.label(vs.open_error()).tip(vs.open_error());
  }
  ui::Layout &row = m.row(false);
  row.button("open", ctx.tr("viewer.open.ok"), [&vs]() {
    std::string path = vs.open_dialog_path;
    while (!path.empty() && (path.back() == ' ' || path.back() == '\n')) {
      path.pop_back();
    }
    if (vs.open_path(path)) {
      vs.open_dialog = false;
    }
  });
  row.button("cancel", ctx.tr("viewer.action.cancel"), [&vs]() { vs.open_dialog = false; });
}

void export_dialog(EditorContext &ctx, ViewerState &vs)
{
  ExportSettings &s = vs.export_settings;
  ui::ModalOptions mo;
  mo.width_units = 22.0f;
  ui::Layout &m = ctx.ui->modal("viewer_export", ctx.tr("export.title"), [&vs]() { vs.export_dialog = false; }, mo);
  ui::NumberProps size;
  size.integer = true;
  size.min = 16;
  size.max = 8192;
  size.step = 1;
  size.precision = 0;
  size.unit = "px";
  ui::Layout &dims = m.prop(ctx.tr("export.size")).row(true);
  dims.number("width", "", ui::bind_int(s.width), size);
  dims.number("height", "", ui::bind_int(s.height), size);
  std::vector<std::string> mags;
  for (int i = 1; i <= 8; i++) {
    mags.push_back("\xc3\x97" + std::to_string(i)); /* ×i */
  }
  m.prop(ctx.tr("export.magnification"))
      .dropdown("magnification", std::move(mags),
                {[&s]() { return std::clamp(s.magnification, 1, 8) - 1; }, [&s](int i) { s.magnification = i + 1; }})
      .tip(ctx.tr("export.magnification.tip"));
  m.prop("").checkbox("transparent", ctx.tr("export.transparent"), ui::bind(s.transparent));
  m.prop("").checkbox("overlays", ctx.tr("export.overlays"), ui::bind(s.overlays));
  const bool steps = vs.step_choices().size() > 1;
  ui::Widget &seq = m.prop("").checkbox("sequence", ctx.tr("export.sequence"), ui::bind(s.sequence));
  seq.tip(ctx.tr("export.sequence.tip"));
  if (!steps) {
    seq.disable();
  }
  /* TODO(WP9): a native save dialog (stk_platform); the path field stays as the fallback. */
  ui::TextFieldOptions to;
  to.placeholder = "/path/to/view.png";
  m.prop(ctx.tr("export.path")).text_field("path", ui::bind(s.path), to);
  const int mag = std::clamp(s.magnification, 1, 8);
  std::string out = ctx.store.catalog().format(
      "export.output", {{"width", std::to_string(s.width * mag)}, {"height", std::to_string(s.height * mag)}});
  if (s.sequence && steps) {
    out += "  \xc2\xb7  " + ctx.store.catalog().format("export.frames",
                                                       {{"count", std::to_string(vs.step_choices().size())}});
  }
  m.label(out);
  if (!vs.export_status().empty()) {
    m.label(vs.export_status()).tip(vs.export_status());
  }
  ui::Layout &row = m.row(false);
  ui::Widget &go = row.button("export", ctx.tr("export.save"), [&vs]() { vs.request_export(); });
  if (!vs.payload() || vs.export_job()) {
    go.disable();
  }
  row.button("close", ctx.tr("export.close"), [&vs]() { vs.export_dialog = false; });
}

}  // namespace

void draw_dialogs(EditorContext &ctx)
{
  if (!ctx.ui) {
    return;
  }
  ViewerState &vs = ctx.store.viewer();
  if (vs.open_dialog) {
    open_dialog(ctx, vs);
  }
  if (vs.export_dialog) {
    export_dialog(ctx, vs);
  }
}

}  // namespace stk::app::viewer_ui
