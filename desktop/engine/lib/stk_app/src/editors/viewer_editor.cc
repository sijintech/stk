/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The Viewer editor (WP10): stk_viewer_gpu under a transparent main block.
 *
 *  - Navigation: Blender style by default (middle drag orbits, Shift+middle pans, Ctrl+middle and
 *    the wheel zoom; the left button uses the toolbar tool: orbit, pan, zoom or pick), ParaView
 *    style optional (left orbit, middle pan, right zoom). A click (press and release within 4 px)
 *    picks in every tool, as the web viewer does; the pick goes to the Probe editor.
 *  - Keys: numpad 1 / 3 / 7 (Ctrl: opposite) and 0 / 9 camera presets, Home view all, Space
 *    play / pause, Left / Right previous / next step.
 *  - Sidebar: layers (visibility, opacity), camera (7 presets, numeric camera, view all, reset),
 *    time steps (scrubber, playback, fps, loop, prefetch), display (overlays, lighting,
 *    navigation style).
 *  - Picking and exports run outside the frame (WindowManager::post) with the window's GPU
 *    context current; the GPU viewer lives in the editor (one camera per Viewer area).
 */

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <filesystem>

#include "viewer_common.hh"

#include "../app_theme.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_export.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "stk/ui/ui.hh"
#include "stk/viewer/camera.hh"
#include "stk/viewer_gpu/viewer.hh"
#include "stk/wm/window.hh"

namespace stk::app {

namespace {

using namespace viewer_ui;

enum class Tool : uint8_t { Orbit, Pan, Zoom, Pick };

const char *tool_key(const Tool t)
{
  switch (t) {
    case Tool::Orbit: return "orbit";
    case Tool::Pan: return "pan";
    case Tool::Zoom: return "zoom";
    case Tool::Pick: return "pick";
  }
  return "orbit";
}

const char *preset_key(const viewer::CameraPreset p)
{
  switch (p) {
    case viewer::CameraPreset::Iso: return "viewer.camera.iso";
    case viewer::CameraPreset::PosX: return "viewer.camera.px";
    case viewer::CameraPreset::NegX: return "viewer.camera.nx";
    case viewer::CameraPreset::PosY: return "viewer.camera.py";
    case viewer::CameraPreset::NegY: return "viewer.camera.ny";
    case viewer::CameraPreset::PosZ: return "viewer.camera.pz";
    case viewer::CameraPreset::NegZ: return "viewer.camera.nz";
  }
  return "viewer.camera.iso";
}

/** The narrow tool column's icon-like glyph (until an icon set exists), the same in every language;
 * the tooltip names the tool. Orbit U+21BB, pan U+271A (move cross), zoom U+00B1 (in / out), pick
 * U+2299 (target). Inter or Noto Sans CJK has each (BLF finds DejaVu Sans Mono's symbols, e.g.
 * U+2725 or the magnifier U+2315, through no fallback). */
const char *tool_glyph(const Tool t)
{
  switch (t) {
    case Tool::Orbit: return "\xe2\x86\xbb";
    case Tool::Pan: return "\xe2\x9c\x9a";
    case Tool::Zoom: return "\xc2\xb1";
    case Tool::Pick: return "\xe2\x8a\x99";
  }
  return "?";
}

class ViewerEditor final : public Editor {
 public:
  explicit ViewerEditor(const EditorType &type) : Editor(type) {}

  ~ViewerEditor() override
  {
    *alive_ = false;
    if (vs_) {
      vs_->viewer_editors--;
      if (vs_->dialog_host == this) {
        vs_->dialog_host = nullptr;
      }
    }
    /* GPU resources are released with the viewer; the GPU context is still alive here (the
     * window manager outlives the screens' editors). */
    gpu_.reset();
  }

  ui::Color main_background(const ui::Theme & /*theme*/) const override
  {
    /* Transparent over the GPU view; the flat viewer grey while there is nothing to show. */
    return has_payload_ ? ui::Color{0, 0, 0, 0} : theme::kViewerBack;
  }

  bool has_toolbar() const override
  {
    return true;
  }
  bool has_sidebar() const override
  {
    return true;
  }
  bool draws_gpu() const override
  {
    return true;
  }

  /* ---- UI ---- */

  void attach(EditorContext &ctx)
  {
    area_ = &ctx.area;
    if (!vs_) {
      vs_ = &ctx.store.viewer();
      vs_->viewer_editors++;
    }
    if (!vs_->dialog_host) {
      vs_->dialog_host = this;
    }
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    attach(ctx);
    ViewerState &vs = *vs_;
    const std::string_view open = ctx.tr("viewer.action.open");
    row.button("open", open, [&vs]() { vs.open_dialog = true; }).width(fit_units(ctx, open)).tip(ctx.tr("viewer.action.open.tip"));
    const std::string_view overlays = ctx.tr("viewer.overlays");
    row.checkbox("overlays", overlays, {[&vs]() { return vs.overlays(); }, [&vs](bool on) { vs.set_overlays(on); }})
        .width(fit_units(ctx, overlays) + 1.0f)
        .tip(ctx.tr("viewer.overlays.tip"));
    const std::string_view all = ctx.tr("viewer.camera.view_all");
    row.button("view_all", all, [this]() { view_all(); }).width(fit_units(ctx, all)).tip(ctx.tr("viewer.camera.view_all.tip"));
    const std::string_view exp = ctx.tr("viewer.action.export");
    ui::Widget &e = row.button("export", exp, [this, &vs]() { open_export(vs); });
    e.width(fit_units(ctx, exp));
    if (!vs.payload()) {
      e.disable();
    }
  }

  void draw_toolbar(ui::Layout &l, EditorContext &ctx) override
  {
    attach(ctx);
    for (const Tool t : {Tool::Orbit, Tool::Pan, Tool::Zoom, Tool::Pick}) {
      const std::string key = std::string("editor.viewer.tool.") + tool_key(t);
      const std::string_view label = ctx.tr(key);
      /* A one-tab strip per tool: the selected look marks the active tool. */
      l.tabs(std::string("tool.") + tool_key(t), {tool_glyph(t)},
             {[this, t]() { return tool_ == t ? 0 : -1; }, [this, t](int) { tool_ = t; }})
          .tip(std::string(label) + "\n" + std::string(ctx.tr(std::string("viewer.tool.") + tool_key(t) + ".tip")));
    }
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    attach(ctx);
    pump(ctx);
    ViewerState &vs = *vs_;
    has_payload_ = vs.payload() != nullptr;
    if (vs.dialog_host == this) {
      draw_dialogs(ctx);
    }
    maybe_run_export(ctx);

    /* Top-left: source and evaluation status (non-expanding rows: the rest of the region orbits). */
    if (!vs.source_label().empty()) {
      std::string src = ctx.store.catalog().format(
          "viewer.source", {{"name", vs.source_label()}, {"kind", std::string(ctx.tr(std::string("viewer.source.") +
                                                                                     source_kind_name(vs.source().kind)))}});
      if (!vs.preset_id().empty()) {
        if (const PresetInfo *p = vs.preset(vs.preset_id())) {
          src += "  \xc2\xb7  " + preset_label(ctx, *p);
        }
      }
      if (!vs.step_param().empty() && !vs.shown_step().is_null()) {
        src += "  \xc2\xb7  " + ctx.store.catalog().format("viewer.step_short", {{"step", step_text(vs.shown_step())}});
      }
      ui::Layout &row = l.row(false);
      row.alignment(ui::LayoutAlign::Left);
      row.label(src).width(fit_units(ctx, src)).tip(vs.source().path.empty() ? vs.source_label() : vs.source().path);
    }
    if (vs.progress().running || !vs.eval_error().empty()) {
      draw_eval_status(l, ctx, true);
    }
    if (!has_payload_) {
      if (!vs.progress().running) {
        l.separator(1.0f);
        ui::Layout &box = l.column(false);
        box.label(ctx.tr("viewer.empty.title"), ui::Align::Center);
        box.paragraph(ctx.tr("viewer.empty.body"));
        if (!vs.open_error().empty()) {
          box.label(vs.open_error()).tip(vs.open_error());
        }
      }
      return;
    }
    /* Push the bottom rows down to the bottom edge of the view. */
    const std::vector<std::string> warnings = vs.warnings();
    const float used = 1.0f + (vs.source_label().empty() ? 0.0f : 1.1f) +
                       ((vs.progress().running || !vs.eval_error().empty()) ? 1.1f : 0.0f) +
                       (warnings.empty() ? 0.0f : 1.1f);
    l.separator(std::max(0.0f, fill_units(ctx, used + 1.4f)));
    /* Bottom centre (the overlay anchors use the corners: axes bottom left, orientation sphere
     * bottom right): payload warnings (one line, details in the tooltip) and stats. */
    if (!warnings.empty()) {
      std::string tip;
      for (const std::string &w : warnings) {
        tip += (tip.empty() ? "" : "\n") + w;
      }
      const std::string text =
          "\xe2\x9a\xa0 " + ctx.store.catalog().format("viewer.warnings", {{"count", std::to_string(warnings.size())}});
      ui::Layout &row = l.row(false);
      row.alignment(ui::LayoutAlign::Center);
      row.label(text).width(fit_units(ctx, text)).tip(tip);
    }
    const std::string stats = vs.stats_text();
    if (!stats.empty()) {
      ui::Layout &row = l.row(false);
      row.alignment(ui::LayoutAlign::Center);
      row.label(stats, ui::Align::Center).width(fit_units(ctx, stats));
    }
  }

  void draw_sidebar(ui::Layout &l, EditorContext &ctx) override
  {
    attach(ctx);
    ViewerState &vs = *vs_;
    draw_layers(l, ctx, vs);
    draw_camera(l, ctx);
    draw_steps(l, ctx, vs);
    draw_display(l, ctx, vs);
  }

  /* ---- Sidebar panels ---- */

  void draw_layers(ui::Layout &l, EditorContext &ctx, ViewerState &vs)
  {
    ui::Layout *p = l.panel("layers", ctx.tr("viewer.panel.layers"));
    if (!p) {
      return;
    }
    const std::vector<ViewerState::LayerRow> rows = vs.layers();
    if (rows.empty()) {
      p->label(ctx.tr("viewer.layers.none")).disable();
      return;
    }
    for (const ViewerState::LayerRow &r : rows) {
      ui::Layout &s = p->scope(r.id);
      const std::string id = r.id;
      std::string name = r.name.empty() ? r.id : r.name;
      s.checkbox("visible", name, {[&vs, id]() {
                                     for (const auto &row : vs.layers()) {
                                       if (row.id == id) {
                                         return row.visible;
                                       }
                                     }
                                     return true;
                                   },
                                   [&vs, id](bool on) { vs.set_layer_visible(id, on); }})
          .tip(r.id + " \xc2\xb7 " + r.type + (r.kind.empty() ? "" : " (" + r.kind + ")"));
      if (r.has_opacity) {
        ui::NumberProps op;
        op.min = 0.0;
        op.max = 1.0;
        op.step = 0.05;
        op.precision = 2;
        s.slider("opacity", ctx.tr("viewer.layer.opacity"),
                 {[&vs, id]() {
                    for (const auto &row : vs.layers()) {
                      if (row.id == id) {
                        return row.opacity;
                      }
                    }
                    return 1.0;
                  },
                  [&vs, id](double v) { vs.set_layer_opacity(id, v); }},
                 op);
      }
    }
  }

  void draw_camera(ui::Layout &l, EditorContext &ctx)
  {
    ui::Layout *p = l.panel("camera", ctx.tr("viewer.panel.camera"));
    if (!p) {
      return;
    }
    ui::Layout &g = p->grid(4, true);
    for (const viewer::CameraPreset preset : viewer::kCameraPresets) {
      g.button(std::string("preset.") + std::string(viewer::camera_preset_name(preset)), ctx.tr(preset_key(preset)),
               [this, preset]() { set_preset(preset); })
          .tip(std::string(ctx.tr(std::string(preset_key(preset)) + ".tip")));
    }
    g.button("reset", ctx.tr("viewer.camera.reset"), [this]() { reset_camera(); }).tip(ctx.tr("viewer.camera.reset.tip"));
    const bool live = gpu_ && has_payload_;
    if (!live) {
      return;
    }
    ui::Layout *nump = p->panel("numeric", ctx.tr("viewer.camera.numeric"), false);
    if (!nump) {
      return;
    }
    ui::Layout &num = *nump;
    auto vec = [&](const char *key, const char *label_key, viewer::dvec3 viewer::CameraPose::*member, bool physical) {
      ui::Layout &col = num.prop(ctx.tr(label_key)).column(true);
      static const char *xyz[] = {"X", "Y", "Z"};
      for (int i = 0; i < 3; i++) {
        ui::NumberProps np;
        np.step = physical ? 0.1 : 0.01;
        np.precision = 4;
        col.number(std::string(key) + "/" + std::to_string(i), xyz[i],
                   {[this, member, i, physical]() {
                      const viewer::dvec3 v = cam_.*member;
                      return (i == 0 ? v.x : i == 1 ? v.y : v.z) + (physical ? origin_[size_t(i)] : 0.0);
                    },
                    [this, member, i, physical](double d) {
                      viewer::dvec3 &v = cam_.*member;
                      const double local = d - (physical ? origin_[size_t(i)] : 0.0);
                      (i == 0 ? v.x : i == 1 ? v.y : v.z) = local;
                      if (member == &viewer::CameraPose::view_up) {
                        viewer::orthogonalize_view_up(cam_);
                      }
                      apply_camera();
                    }},
                   np);
      }
    };
    vec("position", "viewer.camera.position", &viewer::CameraPose::position, true);
    vec("focal", "viewer.camera.focal_point", &viewer::CameraPose::focal_point, true);
    vec("up", "viewer.camera.view_up", &viewer::CameraPose::view_up, false);
    ui::NumberProps angle;
    angle.min = 1.0;
    angle.max = 170.0;
    angle.step = 1.0;
    angle.precision = 1;
    angle.unit = "\xc2\xb0";
    num.prop(ctx.tr("viewer.camera.angle"))
        .number("angle", "", {[this]() { return cam_.view_angle_deg; }, [this](double d) {
                                cam_.view_angle_deg = d;
                                apply_camera();
                              }},
                angle);
    num.prop("").checkbox("parallel", ctx.tr("viewer.camera.parallel"),
                          {[this]() { return cam_.parallel; }, [this](bool b) {
                             cam_.parallel = b;
                             if (b && cam_.parallel_scale <= 0) {
                               cam_.parallel_scale = 1.0;
                             }
                             apply_camera();
                           }});
    if (cam_.parallel) {
      ui::NumberProps ps;
      ps.min = 1e-12;
      ps.step = 0.1;
      ps.precision = 4;
      num.prop(ctx.tr("viewer.camera.parallel_scale"))
          .number("parallel_scale", "", {[this]() { return cam_.parallel_scale; }, [this](double d) {
                                           cam_.parallel_scale = d;
                                           apply_camera();
                                         }},
                  ps);
    }
  }

  void draw_steps(ui::Layout &l, EditorContext &ctx, ViewerState &vs)
  {
    ui::Layout *p = l.panel("steps", ctx.tr("viewer.panel.steps"));
    if (!p) {
      return;
    }
    const std::vector<io::Json> &choices = vs.step_choices();
    if (vs.step_param().empty() || choices.empty()) {
      p->label(ctx.tr("viewer.steps.none")).disable();
      return;
    }
    const int n = int(choices.size());
    const int i = vs.step_index();
    p->label(ctx.store.catalog().format(
        "viewer.steps.current",
        {{"step", step_text(vs.shown_step())}, {"index", std::to_string(i + 1)}, {"count", std::to_string(n)}}));
    ui::NumberProps sp;
    sp.integer = true;
    sp.min = 0;
    sp.max = std::max(0, n - 1);
    sp.step = 1;
    sp.precision = 0;
    p->slider("scrub", "", {[&vs]() { return double(std::max(0, vs.step_index())); }, [&vs](double d) {
                              vs.set_step_index(int(std::lround(d)));
                            }},
              sp)
        .tip(ctx.tr("viewer.steps.scrub.tip"));
    ui::Layout &row = p->row(true);
    row.button("first", "|\xe2\x97\x80", [&vs]() { vs.set_step_index(0); }).tip(ctx.tr("viewer.steps.first"));
    row.button("prev", "\xe2\x97\x80", [&vs]() { vs.step_by(-1); }).tip(ctx.tr("viewer.steps.prev"));
    row.button("play", vs.playing() ? "\xe2\x8f\xb8" : "\xe2\x96\xb6", [&vs]() { vs.set_playing(!vs.playing()); })
        .tip(ctx.tr(vs.playing() ? "viewer.steps.pause" : "viewer.steps.play"));
    row.button("next", "\xe2\x96\xb6|", [&vs]() { vs.step_by(1); }).tip(ctx.tr("viewer.steps.next"));
    row.button("last", "\xe2\x96\xb6\xe2\x96\xb6", [&vs]() { vs.set_step_index(int(vs.step_choices().size()) - 1); })
        .tip(ctx.tr("viewer.steps.last"));
    ui::NumberProps fps;
    fps.min = 0.2;
    fps.max = 60.0;
    fps.step = 1.0;
    fps.precision = 1;
    p->prop(ctx.tr("viewer.steps.fps")).number("fps", "", ui::bind(vs.fps), fps);
    p->prop("").checkbox("loop", ctx.tr("viewer.steps.loop"), ui::bind(vs.loop));
    p->prop("").checkbox("prefetch", ctx.tr("viewer.steps.prefetch"), ui::bind(vs.prefetch_neighbours))
        .tip(ctx.tr("viewer.steps.prefetch.tip"));
    if (vs.source().evaluates()) {
      p->button("latest", ctx.tr("viewer.steps.latest"), [&vs]() { vs.step_latest(); }).tip(ctx.tr("viewer.steps.latest.tip"));
    }
    std::string info = ctx.store.catalog().format("viewer.steps.cached", {{"count", std::to_string(vs.cached_results())}});
    if (vs.last_step_switch_ms() >= 0) {
      info += "  \xc2\xb7  " + ctx.store.catalog().format("viewer.steps.switch", {{"ms", num(vs.last_step_switch_ms(), ".0f")}});
    }
    p->label(info).disable();
  }

  void draw_display(ui::Layout &l, EditorContext &ctx, ViewerState &vs)
  {
    ui::Layout *p = l.panel("display", ctx.tr("viewer.panel.display"), false);
    if (!p) {
      return;
    }
    p->prop("").checkbox("overlays", ctx.tr("viewer.overlays"), {[&vs]() { return vs.overlays(); }, [&vs](bool on) {
                                                                    vs.set_overlays(on);
                                                                  }});
    const std::vector<std::string> lights = {"", "three_point", "headlight", "none"};
    p->prop(ctx.tr("viewer.lighting"))
        .dropdown("lighting",
                  {std::string(ctx.tr("viewer.lighting.payload")), std::string(ctx.tr("viewer.lighting.three_point")),
                   std::string(ctx.tr("viewer.lighting.headlight")), std::string(ctx.tr("viewer.lighting.none"))},
                  {[this, lights]() {
                     const auto it = std::find(lights.begin(), lights.end(), lighting_);
                     return it == lights.end() ? 0 : int(it - lights.begin());
                   },
                   [this, lights](int i) { lighting_ = lights[size_t(std::clamp(i, 0, 3))]; }});
    p->prop(ctx.tr("viewer.navigation"))
        .dropdown("navigation",
                  {std::string(ctx.tr("viewer.navigation.blender")), std::string(ctx.tr("viewer.navigation.paraview"))},
                  {[this]() { return nav_ == viewer::NavigationStyle::ParaView ? 1 : 0; },
                   [this](int i) { nav_ = i == 1 ? viewer::NavigationStyle::ParaView : viewer::NavigationStyle::Blender; }})
        .tip(ctx.tr("viewer.navigation.tip"));
  }

  /* ---- Camera operations (CPU only; the GPU viewer applies them at the next draw) ---- */

  void set_preset(const viewer::CameraPreset preset)
  {
    if (gpu_ && has_payload_) {
      gpu_->set_camera_preset(preset);
      cam_ = gpu_->camera();
    }
    else {
      pending_preset_ = preset;
    }
    redraw();
  }

  void view_all()
  {
    if (gpu_ && has_payload_) {
      viewer::CameraPose pose = gpu_->camera();
      viewer::view_all(pose, gpu_->bounds());
      gpu_->set_camera(pose);
      cam_ = pose;
    }
    redraw();
  }

  void reset_camera()
  {
    if (gpu_ && has_payload_) {
      gpu_->reset_camera();
      cam_ = gpu_->camera();
    }
    redraw();
  }

  void apply_camera()
  {
    if (gpu_ && has_payload_) {
      gpu_->set_camera(cam_);
    }
    redraw();
  }

  void redraw()
  {
    if (area_) {
      area_->tag_redraw();
    }
  }

  void open_export(ViewerState &vs)
  {
    ExportSettings &s = vs.export_settings;
    if (const auto p = vs.payload()) {
      const io::Json &vp = p->manifest.contains("view") ? p->manifest["view"].value("viewport", io::Json()) : io::Json();
      if (!export_sized_) {
        s.width = int(io::get_number(vp, "width", s.width));
        s.height = int(io::get_number(vp, "height", s.height));
        export_sized_ = true;
      }
    }
    if (s.path.empty()) {
      std::error_code ec;
      std::string stem = vs.source_label().empty() ? "stk-view" : vs.source_label();
      for (char &c : stem) {
        if (c == '/' || c == '\\' || c == ':' || c == ' ') {
          c = '_';
        }
      }
      const std::filesystem::path home = core::home_dir();
      s.path = core::path_to_utf8((home.empty() ? std::filesystem::current_path(ec) : home) /
                                  core::path_from_utf8(stem + (vs.preset_id().empty() ? "" : "-" + vs.preset_id()) + ".png"));
    }
    vs.export_dialog = true;
  }

  /* ---- GPU ---- */

  void sync(const EditorContext &ctx)
  {
    ViewerState &vs = *vs_;
    if (!gpu_) {
      viewer_gpu::ViewerOptions opts;
      opts.navigation = nav_;
      gpu_ = std::make_unique<viewer_gpu::Viewer>(*ctx.draw->fonts, opts);
    }
    if (vs.camera_serial() != camera_serial_) {
      camera_serial_ = vs.camera_serial();
      camera_reset_pending_ = true;
    }
    if (vs.payload_serial() != payload_serial_) {
      payload_serial_ = vs.payload_serial();
      gpu_->set_payload(vs.payload());
      if (const auto p = vs.payload()) {
        origin_ = p->render_origin;
      }
    }
    if (camera_reset_pending_ && vs.payload()) {
      camera_reset_pending_ = false;
      gpu_->reset_camera();
      if (saved_camera_) {
        gpu_->set_camera(*saved_camera_);
        saved_camera_.reset();
      }
    }
    if (pending_preset_ && vs.payload()) {
      gpu_->set_camera_preset(*pending_preset_);
      pending_preset_.reset();
    }
    for (const auto &p : vs.take_prefetched()) {
      gpu_->prefetch(p);
    }
    for (const auto &[id, on] : vs.visibility()) {
      gpu_->set_layer_visible(id, on);
    }
    gpu_->set_overlays_visible(vs.overlays());
    gpu_->set_lighting(lighting_);
    gpu_->set_interacting(dragging_ && moved_);
  }

  void draw_gpu(EditorContext &ctx) override
  {
    if (!ctx.draw || !ctx.draw->fonts || !vs_) {
      return;
    }
    area_ = &ctx.area;
    sync(ctx);
    if (!vs_->payload()) {
      return;
    }
    const wm::Rect r = ctx.draw->rect;
    gpu_->draw({r.xmin, r.ymin, r.width(), r.height()}, ctx.draw->ui_scale);
    cam_ = gpu_->camera();
    view_w_ = r.width();
    view_h_ = r.height();
  }

  /** Runs `fn` outside the frame with the GPU context current (posted to the main loop). */
  void later(const EditorContext &ctx, std::function<void()> fn)
  {
    wm::WindowManager *wm = window_manager(ctx);
    std::shared_ptr<bool> alive = alive_;
    if (!wm) {
      fn();
      return;
    }
    wm->post([alive, fn = std::move(fn)]() {
      if (*alive) {
        fn();
      }
    });
  }

  void pick_at(const EditorContext &ctx, const double x, const double y)
  {
    if (!gpu_ || !has_payload_) {
      return;
    }
    const int w = view_w_, h = view_h_;
    ViewerState *vs = vs_;
    later(ctx, [this, vs, x, y, w, h]() {
      const viewer_gpu::PickResult hit = gpu_->pick(x, y, w, h);
      if (!hit.hit) {
        last_pick_miss_ = true;
        return;
      }
      last_pick_miss_ = false;
      PickInfo info;
      info.layer_id = hit.layer_id;
      info.layer_type = hit.layer_type;
      info.element = hit.element;
      info.physical = hit.physical;
      for (const ViewerState::LayerRow &row : vs->layers()) {
        if (row.id == hit.layer_id) {
          info.layer_name = row.name;
        }
      }
      if (hit.probe) {
        info.probe_node = hit.probe->node;
        info.probe_dataset = hit.probe->dataset;
      }
      vs->set_pick(std::move(info));
      redraw();
    });
  }

  void maybe_run_export(EditorContext &ctx)
  {
    ViewerState &vs = *vs_;
    ExportJob *job = vs.export_job();
    if (!job || !job->ready || export_posted_ || vs.dialog_host != this) {
      return;
    }
    export_posted_ = true;
    ViewerState *pvs = vs_;
    later(ctx, [this, pvs]() {
      export_posted_ = false;
      ExportJob *j = pvs->export_job();
      if (!j || !gpu_) {
        if (j) {
          pvs->finish_export(false, std::string(pvs->store().tr("export.error.no_view")));
        }
        return;
      }
      std::string message;
      const bool ok = render_export_job(*gpu_, *j, pvs->store(), pvs->payload(), message);
      pvs->finish_export(ok, message);
      redraw();
    });
  }

  /* ---- Events ---- */

  bool handle_gpu_event(const wm::Event &e, EditorContext &ctx) override
  {
    area_ = &ctx.area;
    if (!ctx.draw) {
      return false;
    }
    const wm::Rect r = ctx.draw->rect;
    const double lx = double(e.x - r.xmin) + 0.5;
    const double ly = double(r.ymax - 1 - e.y) + 0.5;
    const viewer::Viewport vp{double(std::max(1, r.width())), double(std::max(1, r.height()))};
    switch (e.type) {
      case wm::EventType::MouseDown:
        if (e.button == wm::MouseButton::Left || e.button == wm::MouseButton::Middle ||
            e.button == wm::MouseButton::Right)
        {
          dragging_ = true;
          moved_ = false;
          button_ = e.button;
          mods_ = e.modifiers;
          press_x_ = last_x_ = lx;
          press_y_ = last_y_ = ly;
          return true;
        }
        return false;
      case wm::EventType::MouseMove: {
        if (!dragging_) {
          return false;
        }
        const double dx = lx - last_x_, dy = ly - last_y_;
        last_x_ = lx;
        last_y_ = ly;
        if (!moved_ && std::hypot(lx - press_x_, ly - press_y_) > 4.0) {
          moved_ = true;
        }
        if (moved_ && gpu_ && has_payload_) {
          navigate(dx, dy, vp);
        }
        return true;
      }
      case wm::EventType::MouseUp: {
        if (!dragging_) {
          return false;
        }
        const bool click = !moved_ && e.button == wm::MouseButton::Left && button_ == wm::MouseButton::Left;
        dragging_ = false;
        moved_ = false;
        if (gpu_) {
          gpu_->set_interacting(false);
        }
        if (click) {
          pick_at(ctx, lx, ly);
        }
        redraw();
        return true;
      }
      case wm::EventType::Wheel: {
        if (!gpu_ || !has_payload_) {
          return false;
        }
        const double notches = e.precise ? e.wheel_y / 40.0 : e.wheel_y;
        if (notches == 0.0) {
          return false;
        }
        viewer::CameraPose pose = gpu_->camera();
        const double factor = std::pow(1.2, notches);
        if (nav_ == viewer::NavigationStyle::Blender) {
          viewer::dolly(pose, factor);
        }
        else {
          viewer::dolly_to(pose, factor, lx, ly, vp);
        }
        gpu_->set_camera(pose);
        cam_ = pose;
        redraw();
        return true;
      }
      default:
        return false;
    }
  }

  void navigate(const double dx, const double dy, const viewer::Viewport &vp)
  {
    enum class Op { None, Orbit, Pan, Zoom } op = Op::None;
    const bool shift = (mods_ & wm::ModShift) != 0, ctrl = (mods_ & wm::ModCtrl) != 0;
    auto tool_op = [&]() {
      switch (tool_) {
        case Tool::Orbit: return shift ? Op::Pan : ctrl ? Op::Zoom : Op::Orbit;
        case Tool::Pan: return Op::Pan;
        case Tool::Zoom: return Op::Zoom;
        case Tool::Pick: return Op::None;
      }
      return Op::None;
    };
    if (nav_ == viewer::NavigationStyle::Blender) {
      if (button_ == wm::MouseButton::Middle) {
        op = shift ? Op::Pan : ctrl ? Op::Zoom : Op::Orbit;
      }
      else if (button_ == wm::MouseButton::Left) {
        op = tool_op();
      }
    }
    else {
      if (button_ == wm::MouseButton::Left) {
        op = tool_ == Tool::Orbit ? (shift ? Op::Pan : ctrl ? Op::Zoom : Op::Orbit) : tool_op();
      }
      else if (button_ == wm::MouseButton::Middle) {
        op = Op::Pan;
      }
      else if (button_ == wm::MouseButton::Right) {
        op = Op::Zoom;
      }
    }
    viewer::CameraPose pose = gpu_->camera();
    switch (op) {
      case Op::Orbit: viewer::orbit(pose, nav_, dx, dy, vp); break;
      case Op::Pan: viewer::pan(pose, dx, dy, vp); break;
      case Op::Zoom: viewer::dolly(pose, std::exp(-dy * 0.01)); break;
      case Op::None: return;
    }
    gpu_->set_camera(pose);
    gpu_->set_interacting(true);
    cam_ = pose;
    redraw();
  }

  bool on_key(const wm::Event &e, EditorContext &ctx) override
  {
    if (e.type != wm::EventType::KeyDown || !vs_) {
      return false;
    }
    area_ = &ctx.area;
    const bool ctrl = (e.modifiers & wm::ModCtrl) != 0;
    const bool plain = (e.modifiers & (wm::ModCtrl | wm::ModAlt | wm::ModOS)) == 0;
    using P = viewer::CameraPreset;
    switch (e.key) {
      case wm::Key::Numpad1: set_preset(ctrl ? P::PosY : P::NegY); return true;
      case wm::Key::Numpad3: set_preset(ctrl ? P::NegX : P::PosX); return true;
      case wm::Key::Numpad7: set_preset(ctrl ? P::NegZ : P::PosZ); return true;
      case wm::Key::Numpad0: set_preset(P::Iso); return true;
      case wm::Key::Numpad9: {
        /* Blender: the opposite side of the current view. */
        if (gpu_ && has_payload_) {
          viewer::CameraPose pose = gpu_->camera();
          pose.position = pose.focal_point * 2.0 - pose.position;
          gpu_->set_camera(pose);
          cam_ = pose;
          redraw();
        }
        return true;
      }
      case wm::Key::Home: view_all(); return true;
      case wm::Key::Space:
        if (plain) {
          vs_->set_playing(!vs_->playing());
          return true;
        }
        return false;
      case wm::Key::LeftArrow:
        if (plain) {
          vs_->step_by(-1);
          return true;
        }
        return false;
      case wm::Key::RightArrow:
        if (plain) {
          vs_->step_by(1);
          return true;
        }
        return false;
      default: return false;
    }
  }

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    ViewerState &vs = ctx.store.viewer();
    for (const std::string &p : paths) {
      if (vs.open_path(p)) {
        return true;
      }
    }
    if (!paths.empty() && ctx.store.toast) {
      ctx.store.toast(vs.open_error(), ui::ToastKind::Warning);
    }
    return !paths.empty();
  }

  void menu_entries(std::vector<ui::MenuEntry> &entries, EditorContext &ctx) override
  {
    ViewerState &vs = ctx.store.viewer();
    entries.push_back({std::string(ctx.tr("viewer.action.open")), [&vs]() { vs.open_dialog = true; }});
    entries.push_back({std::string(ctx.tr("viewer.action.export")), [this, &vs]() { open_export(vs); }, vs.payload() != nullptr});
    entries.push_back({std::string(ctx.tr("viewer.action.close")), [&vs]() { vs.close(); }, vs.payload() != nullptr});
  }

  /* ---- Persistence (per area: tool, navigation, lighting, camera) ---- */

  nlohmann::json save_state() const override
  {
    nlohmann::json s = nlohmann::json::object();
    s["tool"] = tool_key(tool_);
    s["navigation"] = nav_ == viewer::NavigationStyle::ParaView ? "paraview" : "blender";
    if (!lighting_.empty()) {
      s["lighting"] = lighting_;
    }
    return s;
  }

  bool load_state(const nlohmann::json &state) override
  {
    if (!state.is_object()) {
      return true;
    }
    const std::string tool = state.value("tool", std::string("orbit"));
    for (const Tool t : {Tool::Orbit, Tool::Pan, Tool::Zoom, Tool::Pick}) {
      if (tool == tool_key(t)) {
        tool_ = t;
      }
    }
    nav_ = state.value("navigation", std::string()) == "paraview" ? viewer::NavigationStyle::ParaView :
                                                                     viewer::NavigationStyle::Blender;
    const std::string light = state.value("lighting", std::string());
    if (light == "three_point" || light == "headlight" || light == "none") {
      lighting_ = light;
    }
    return true;
  }

 private:
  ViewerState *vs_ = nullptr;
  EditorArea *area_ = nullptr;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::unique_ptr<viewer_gpu::Viewer> gpu_;
  uint64_t payload_serial_ = 0, camera_serial_ = 0;
  bool camera_reset_pending_ = false;
  std::optional<viewer::CameraPose> saved_camera_;
  std::optional<viewer::CameraPreset> pending_preset_;
  viewer::CameraPose cam_;
  std::array<double, 3> origin_{};
  bool has_payload_ = false;
  int view_w_ = 0, view_h_ = 0;
  Tool tool_ = Tool::Orbit;
  viewer::NavigationStyle nav_ = viewer::NavigationStyle::Blender;
  std::string lighting_;
  bool dragging_ = false, moved_ = false;
  wm::MouseButton button_ = wm::MouseButton::None;
  uint32_t mods_ = 0;
  double press_x_ = 0, press_y_ = 0, last_x_ = 0, last_y_ = 0;
  bool export_posted_ = false, export_sized_ = false;
  bool last_pick_miss_ = false;
};

}  // namespace

EditorType viewer_editor_type()
{
  return {kEditorViewer, "editor.viewer.title",
          [](const EditorType &type) { return std::make_unique<ViewerEditor>(type); }};
}

}  // namespace stk::app
