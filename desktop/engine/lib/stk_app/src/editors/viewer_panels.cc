/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The Properties editor (preset picker, parameter forms generated from JSON Schema with data and
 * client stages marked, evaluation status and export) and the Probe editor (the last pick with
 * its original data value from the bridge `probe`) of WP10.
 */

#include <algorithm>
#include <cmath>

#include "viewer_common.hh"

#include "../app_theme.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/io/payload.hh"
#include "stk/ui/form.hh"
#include "stk/ui/ui.hh"

namespace stk::app {

namespace {

using namespace viewer_ui;

bool is_colormap_member(const ui::SchemaNode &n)
{
  return n.widget == "colormap" || (n.name == "colormap" && (n.type == ui::SchemaType::Enum || n.type == ui::SchemaType::String));
}

/** The members of `schema` of one stage; colormap members are split off into `colormaps`. */
ui::SchemaNode stage_schema(const ui::SchemaNode &schema, const bool data, std::vector<const ui::SchemaNode *> *colormaps,
                            const bool have_colormaps)
{
  ui::SchemaNode out;
  out.type = ui::SchemaType::Object;
  for (const ui::SchemaNode &m : schema.properties) {
    const bool is_data = m.stage == "data";
    if (is_data != data) {
      continue;
    }
    if (colormaps && have_colormaps && is_colormap_member(m)) {
      colormaps->push_back(&m);
      continue;
    }
    out.properties.push_back(m);
  }
  return out;
}

class PropertiesEditor final : public Editor {
 public:
  explicit PropertiesEditor(const EditorType &type) : Editor(type) {}

  ui::Color main_background(const ui::Theme & /*theme*/) const override
  {
    return theme::kPropertiesBack;
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    pump(ctx);
    ViewerState &vs = ctx.store.viewer();
    if (vs.viewer_editors == 0) {
      draw_dialogs(ctx);
    }
    draw_source(l, ctx, vs);
    draw_preset(l, ctx, vs);
    draw_parameters(l, ctx, vs);
    if (ui::Layout *p = l.panel("export", ctx.tr("props.panel.export"), false)) {
      ui::Widget &b = p->button("export", ctx.tr("props.export.open"), [&vs]() {
        if (vs.export_settings.path.empty()) {
          vs.export_settings.path = "stk-view.png";
        }
        vs.export_dialog = true;
      });
      if (!vs.payload()) {
        b.disable();
      }
      if (!vs.export_status().empty()) {
        p->label(vs.export_status()).tip(vs.export_status());
      }
    }
  }

  void draw_source(ui::Layout &l, EditorContext &ctx, ViewerState &vs)
  {
    ui::Layout *p = l.panel("source", ctx.tr("props.panel.source"));
    if (!p) {
      return;
    }
    const ViewerSource &src = vs.source();
    if (src.kind == SourceKind::None) {
      p->paragraph(ctx.tr("props.source.none"));
    }
    else {
      p->prop(ctx.tr("props.source.kind")).label(ctx.tr(std::string("viewer.source.") + source_kind_name(src.kind)));
      p->prop(ctx.tr("props.source.name")).label(vs.source_label()).tip(src.path.empty() ? vs.source_label() : src.path);
    }
    ui::Layout &row = p->row(false);
    row.button("open", ctx.tr("viewer.action.open"), [&vs]() { vs.open_dialog = true; });
    ui::Widget &close = row.button("close", ctx.tr("viewer.action.close"), [&vs]() { vs.close(); });
    if (src.kind == SourceKind::None) {
      close.disable();
    }
  }

  void draw_preset(ui::Layout &l, EditorContext &ctx, ViewerState &vs)
  {
    ui::Layout *p = l.panel("preset", ctx.tr("props.panel.preset"));
    if (!p) {
      return;
    }
    if (!vs.presets_loaded()) {
      const bool bridge = ctx.store.bridge() != nullptr;
      p->label(ctx.tr(bridge ? "props.preset.loading" : "props.preset.no_bridge")).disable();
      if (!vs.metadata_error().empty()) {
        p->label(vs.metadata_error()).tip(vs.metadata_error());
      }
      return;
    }
    std::vector<std::string> items;
    std::vector<std::string> ids;
    for (const PresetInfo &pi : vs.presets()) {
      items.push_back(preset_label(ctx, pi));
      ids.push_back(pi.id);
    }
    p->prop(ctx.tr("props.preset.label"))
        .dropdown("preset", items,
                  {[&vs, ids]() {
                     const auto it = std::find(ids.begin(), ids.end(), vs.preset_id());
                     return it == ids.end() ? -1 : int(it - ids.begin());
                   },
                   [&vs, ids](int i) { vs.select_preset(ids[size_t(i)]); }})
        .tip(ctx.tr("props.preset.tip"));
    if (const PresetInfo *pi = vs.preset(vs.preset_id())) {
      const std::string key = "props.preset." + pi->id + ".description";
      p->paragraph(ctx.store.catalog().tr_or(key, pi->description));
      if (!pi->bindings.empty()) {
        std::string b;
        for (const std::string &n : pi->bindings) {
          b += (b.empty() ? "" : ", ") + n;
        }
        p->prop(ctx.tr("props.preset.bindings")).label(b);
      }
    }
  }

  void draw_parameters(ui::Layout &l, EditorContext &ctx, ViewerState &vs)
  {
    ui::Layout *p = l.panel("parameters", ctx.tr("props.panel.parameters"));
    if (!p) {
      return;
    }
    const ui::SchemaNode &schema = vs.schema();
    if (schema.properties.empty()) {
      p->label(ctx.tr("props.parameters.none")).disable();
      return;
    }
    const bool evaluates = vs.source().evaluates();
    ui::Layout &eval = p->row(false);
    eval.checkbox("auto", ctx.tr("props.auto_evaluate"), ui::bind(vs.auto_evaluate)).tip(ctx.tr("props.auto_evaluate.tip"));
    ui::Widget &go = eval.button("evaluate", ctx.tr("props.evaluate"), [&vs]() { vs.evaluate_now("manual"); });
    go.width(fit_units(ctx, ctx.tr("props.evaluate")));
    if (!evaluates) {
      go.disable().tip(ctx.tr("props.evaluate.no_source"));
    }
    draw_eval_status(*p, ctx, false);

    const auto cms = vs.colormaps();
    const bool have_cms = cms && !cms->empty();
    ui::FormOptions opts;
    opts.stages = ui::StageFilter::All;
    opts.group_panels = true;
    opts.lang = ctx.store.language();
    opts.colormaps = cms;
    /* Data stage: changing it re-runs the data nodes. */
    const ui::SchemaNode data = stage_schema(schema, true, nullptr, false);
    if (!data.properties.empty()) {
      ui::Layout &box = p->box();
      box.label("\xe2\x97\x8f " + std::string(ctx.tr("props.stage.data"))).tip(ctx.tr("form.stage.data"));
      ui::build_form(box.scope("data"), data, vs.form(), opts);
    }
    /* Client stage: appearance only; the data nodes are not re-run. */
    std::vector<const ui::SchemaNode *> colormap_members;
    const ui::SchemaNode client = stage_schema(schema, false, &colormap_members, have_cms);
    if (!client.properties.empty() || !colormap_members.empty()) {
      ui::Layout &box = p->box();
      box.label("\xe2\x97\x8b " + std::string(ctx.tr("props.stage.client"))).tip(ctx.tr("form.stage.client"));
      ui::Layout &body = box.scope("client");
      for (const ui::SchemaNode *m : colormap_members) {
        colormap_field(body, ctx, vs, *m, cms);
      }
      if (!client.properties.empty()) {
        ui::build_form(body, client, vs.form(), opts);
      }
    }
  }

  /** A colormap parameter as a colormap dropdown (gradient swatches from colormaps.list). */
  void colormap_field(ui::Layout &l, EditorContext &ctx, ViewerState &vs, const ui::SchemaNode &m,
                      const std::shared_ptr<const std::vector<ui::ColormapItem>> &all)
  {
    auto items = std::make_shared<std::vector<ui::ColormapItem>>();
    if (m.enum_values.empty()) {
      *items = *all;
    }
    else {
      for (const ui::FormValue &v : m.enum_values) {
        if (v.kind != ui::FormValue::Kind::String) {
          continue;
        }
        const auto it = std::find_if(all->begin(), all->end(), [&](const ui::ColormapItem &c) { return c.name == v.str; });
        items->push_back(it != all->end() ? *it : ui::ColormapItem{v.str, {}});
      }
    }
    const std::string name = m.name;
    ui::FormModel *form = &vs.form();
    std::shared_ptr<const std::vector<ui::ColormapItem>> list = items;
    l.prop(ui::schema_label(m, ctx.store.language()))
        .colormap_dropdown(name, list,
                           {[form, name, list]() {
                              const std::string cur = form->get(name).str;
                              for (size_t i = 0; i < list->size(); i++) {
                                if ((*list)[i].name == cur) {
                                  return int(i);
                                }
                              }
                              return -1;
                            },
                            [form, name, list](int i) { form->set(name, ui::FormValue::string((*list)[size_t(i)].name)); }})
        .tip(std::string(ctx.tr("form.stage.client")));
  }
};

/* -------------------------------------------------------------------- */

class ProbeEditor final : public Editor {
 public:
  explicit ProbeEditor(const EditorType &type) : Editor(type) {}

  ui::Color main_background(const ui::Theme & /*theme*/) const override
  {
    return theme::kPropertiesBack;
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    pump(ctx);
    ViewerState &vs = ctx.store.viewer();
    const ProbeState &pr = vs.probe();
    if (pr.status == ProbeState::Status::Empty) {
      l.label(ctx.tr("probe.empty"));
      l.paragraph(ctx.tr("probe.hint"));
      return;
    }
    const PickInfo &pick = pr.pick;
    const std::string unit = vs.base_payload() ? vs.base_payload()->length_unit : std::string();
    ui::Layout &cols = l.split(0.5f, false);
    ui::Layout &left = cols.column(false);
    ui::Layout &right = cols.column(false);
    /* Where: layer, element and the float64 physical position (editable: query elsewhere). */
    const std::string layer = (pick.layer_name.empty() ? pick.layer_id : pick.layer_name) +
                              (pick.layer_type.empty() ? "" : " (" + pick.layer_type + ")");
    left.prop(ctx.tr("probe.layer")).label(layer).tip(pick.layer_id);
    left.prop(ctx.tr("probe.element")).label(std::to_string(pick.element));
    const std::string pos = vec3(pick.physical) + (unit.empty() || unit == "unspecified" ? "" : " " + unit);
    left.prop(ctx.tr("probe.position")).label(pos).tip(ctx.tr("probe.position.tip"));
    ui::Layout &edit = left.prop(ctx.tr("probe.query_at")).row(true);
    static const char *xyz[] = {"X", "Y", "Z"};
    for (int i = 0; i < 3; i++) {
      ui::NumberProps np;
      np.step = 0.1;
      np.precision = 4;
      edit.number(std::string("pos/") + std::to_string(i), xyz[i],
                  {[this, i, &pick]() { return typed_ ? position_[size_t(i)] : pick.physical[size_t(i)]; },
                   [this, i, &pick](double d) {
                     if (!typed_) {
                       position_ = pick.physical;
                       typed_ = true;
                     }
                     position_[size_t(i)] = d;
                   }},
                  np);
    }
    ui::Layout &buttons = left.row(false);
    ui::Widget &q = buttons.button("query", ctx.tr("probe.query"), [this, &vs, &pick]() {
      vs.probe_position(typed_ ? position_ : pick.physical);
      typed_ = false;
    });
    if (!vs.source().evaluates()) {
      q.disable();
    }
    buttons.button("clear", ctx.tr("probe.clear"), [this, &vs]() {
      typed_ = false;
      vs.clear_pick();
    });

    /* What: the original data value (trilinear sample of the source field). */
    switch (pr.status) {
      case ProbeState::Status::Pending:
        right.progress(0.5f, ctx.tr("probe.pending"));
        break;
      case ProbeState::Status::Failed:
        right.label(ctx.store.catalog().format("probe.failed", {{"error", pr.error}})).tip(pr.error);
        break;
      case ProbeState::Status::Unavailable:
        right.paragraph(pr.error);
        break;
      case ProbeState::Status::Done:
        draw_sample(right, ctx, pr);
        break;
      default:
        break;
    }
  }

  void draw_sample(ui::Layout &l, EditorContext &ctx, const ProbeState &pr)
  {
    const io::Json &sample = pr.sample;
    const io::Json &target = pr.target;
    const std::string path = io::get_string(target, "path");
    if (!path.empty()) {
      l.prop(ctx.tr("probe.source")).label(path).tip(io::get_string(target, "binding") + ": " + path);
    }
    const io::Json values = sample.is_object() ? sample.value("values", io::Json()) : io::Json();
    std::string units;
    if (sample.is_object() && sample.contains("units")) {
      const io::Json &u = sample["units"];
      units = u.is_string() ? u.get<std::string>() : u.is_null() ? std::string() : u.dump();
    }
    if (units == "unspecified") {
      units.clear();
    }
    std::vector<double> comps;
    if (values.is_array()) {
      for (const io::Json &v : values) {
        comps.push_back(v.is_number() ? v.get<double>() : std::nan(""));
      }
    }
    else if (values.is_number()) {
      comps.push_back(values.get<double>());
    }
    static const char *xyz[] = {"X", "Y", "Z"};
    for (size_t i = 0; i < comps.size() && i < 16; i++) {
      const std::string label = comps.size() == 3 ? std::string(ctx.tr("probe.component")) + " " + xyz[i] :
                                comps.size() == 1 ? std::string(ctx.tr("probe.value")) :
                                                    std::string(ctx.tr("probe.component")) + " " + std::to_string(i);
      l.prop(label).label(num(comps[i], ".6g") + (units.empty() ? "" : " " + units));
    }
    if (comps.size() == 3) {
      const double mag = std::sqrt(comps[0] * comps[0] + comps[1] * comps[1] + comps[2] * comps[2]);
      l.prop(ctx.tr("probe.magnitude")).label(num(mag, ".6g") + (units.empty() ? "" : " " + units));
    }
    if (comps.empty()) {
      l.label(ctx.tr("probe.no_value"));
    }
    const std::string interp = io::get_string(sample, "interpolation");
    if (!interp.empty()) {
      const std::string method(ctx.store.catalog().tr_or("probe.method." + interp, interp));
      l.label(ctx.store.catalog().format("probe.interpolation", {{"method", method}})).disable();
    }
  }

 private:
  bool typed_ = false;
  std::array<double, 3> position_{};
};

}  // namespace

EditorType properties_editor_type()
{
  return {kEditorProperties, "editor.properties.title",
          [](const EditorType &type) { return std::make_unique<PropertiesEditor>(type); }};
}

EditorType probe_editor_type()
{
  return {kEditorProbe, "editor.probe.title", [](const EditorType &type) { return std::make_unique<ProbeEditor>(type); }};
}

}  // namespace stk::app
