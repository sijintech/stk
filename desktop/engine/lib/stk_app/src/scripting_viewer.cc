/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Python controls the same ViewerState as native widgets, on the UI thread. */
#include "stk/app/shell.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/io/graph.hh"
#include "stk/io/schema.hh"
#include "stk/ui/form_json.hh"

#include <algorithm>
#include <filesystem>
#include <map>
#include <set>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
using bridge::Error;
using bridge::ErrorCode;

const std::map<std::string, std::set<std::string>> operations = {
    {"viewer.status", {}}, {"viewer.presets", {}},
    {"viewer.open", {"path", "preset", "parameters", "focus"}},
    {"viewer.close", {"expected_source"}},
    {"viewer.configure", {"parameters", "auto_evaluate", "overlays", "prefetch", "fps", "loop", "expected_source"}},
    {"viewer.preset", {"id", "expected_source"}}, {"viewer.evaluate", {"expected_source"}},
    {"viewer.cancel", {"expected_source"}},
    {"viewer.layer", {"id", "visible", "opacity", "expected_source"}},
    {"viewer.step", {"index", "expected_source"}}, {"viewer.play", {"playing", "expected_source"}},
    {"viewer.reset_camera", {"expected_source"}},
};

void require(const bool condition, const std::string &message)
{
  if (!condition) { throw std::invalid_argument(message); }
}

std::string required_string(const Json &params, const char *key)
{
  require(params.contains(key) && params[key].is_string() && !params[key].get_ref<const std::string &>().empty(),
          std::string(key) + " must be a nonempty string");
  return params[key].get<std::string>();
}

void check_parameters(const PresetInfo *preset, const Json &values)
{
  require(values.is_object(), "parameters must be an object");
  if (values.empty()) { return; }
  require(preset && preset->raw.contains("graph"), "Choose a loaded Viewer preset before setting parameters");
  const Json declarations = preset->raw.at("graph").value("parameters", Json::array());
  for (auto it = values.begin(); it != values.end(); ++it) {
    const auto decl = std::find_if(declarations.begin(), declarations.end(), [&](const Json &item) {
      return io::get_string(item, "name") == it.key();
    });
    require(decl != declarations.end(), "Unknown Viewer parameter: " + it.key());
    const auto issues = io::check_value(it.value(), io::parameter_schema(*decl));
    require(issues.empty(), "Invalid Viewer parameter: " + it.key() + (issues.empty() ? "" : " (" + issues.front().message + ")"));
  }
}

Json viewer_status(ViewerState &viewer)
{
  const auto &source = viewer.source();
  Json layers = Json::array();
  for (const auto &layer : viewer.layers()) {
    layers.push_back({{"id", layer.id}, {"name", layer.name}, {"type", layer.type}, {"kind", layer.kind},
                      {"visible", layer.visible}, {"has_opacity", layer.has_opacity}, {"opacity", layer.opacity},
                      {"pickable", layer.pickable}});
  }
  Json result = {
      {"source", {{"key", source.key()}, {"kind", source_kind_name(source.kind)}, {"path", source.path},
                  {"connection", source.connection}, {"node", source.node}, {"task_id", source.task_id}}},
      {"preset", viewer.preset_id()}, {"parameters", viewer.parameters()}, {"presets_ready", viewer.presets_loaded()},
      {"evaluating", viewer.evaluating()}, {"pending_edit", viewer.pending_edit()},
      {"error", viewer.open_error().empty() ? viewer.eval_error() : viewer.open_error()},
      {"metadata_error", viewer.metadata_error()}, {"has_payload", bool(viewer.payload())},
      {"layers", layers}, {"overlays", viewer.overlays()}, {"auto_evaluate", viewer.auto_evaluate},
      {"prefetch", viewer.prefetch_neighbours}, {"fps", viewer.fps}, {"loop", viewer.loop},
      {"playing", viewer.playing()}, {"step_index", viewer.step_index()}, {"steps", viewer.step_choices()},
      {"shown_step", viewer.shown_step()}, {"camera_serial", viewer.camera_serial()}, {"warnings", viewer.warnings()},
      {"evaluation", nullptr},
  };
  if (const auto &last = viewer.last_eval()) {
    result["evaluation"] = {{"id", last->eval_id}, {"reason", last->reason}, {"cache_hits", last->cache_hits},
                            {"cache_misses", last->cache_misses}, {"from_cache", last->from_cache}};
  }
  return result;
}

void focus_viewer(wm::Screen &screen)
{
  EditorArea *target = nullptr;
  for (auto *area : screen.areas()) {
    auto *editor = dynamic_cast<EditorArea *>(area);
    if (!editor) { continue; }
    for (int i = 0; i < editor->tab_count(); ++i) {
      if (editor->tab(i).type().id == kEditorViewer) {
        editor->set_active_tab(i);
        if (screen.maximized()) { screen.set_maximized(editor); }
        return;
      }
    }
    if (!target || target->editor().type().id == kEditorPython) { target = editor; }
  }
  if (target) {
    target->add_tab(kEditorViewer);
    if (screen.maximized()) { screen.set_maximized(target); }
  }
}
}  // namespace

void AppShell::perform_viewer_request(wm::Screen &screen, const std::string &operation, const Json &params,
                                     ScriptState::Completion complete)
{
  const auto found = operations.find(operation);
  if (found == operations.end()) { complete(Error::make(ErrorCode::Unsupported, "Unknown Viewer operation")); return; }
  require(params.is_object() && params.dump().size() <= 1024 * 1024, "Viewer parameters must be an object up to 1 MiB");
  for (auto it = params.begin(); it != params.end(); ++it) {
    require(found->second.count(it.key()) != 0, "Unknown parameter: " + it.key());
  }
  auto &viewer = store_.viewer();
  if (params.contains("expected_source")) {
    const auto expected = required_string(params, "expected_source");
    if (expected != viewer.source().key()) {
      complete(Error::make(ErrorCode::Conflict, "The Viewer source changed; inspect its current state"));
      return;
    }
  }
  if (operation == "viewer.presets") {
    viewer.refresh_metadata();
    Json presets = Json::array();
    for (const auto &preset : viewer.presets()) {
      presets.push_back({{"id", preset.id}, {"name", preset.name}, {"description", preset.description},
                         {"parameters", preset.raw.at("graph").value("parameters", Json::array())}});
    }
    complete(Json{{"ready", viewer.presets_loaded()}, {"presets", presets}, {"error", viewer.metadata_error()}});
    return;
  }
  if (operation == "viewer.open") {
    const std::string path = required_string(params, "path");
    require(std::filesystem::path(core::path_from_utf8(path)).is_absolute(), "path must be absolute");
    if (params.contains("focus")) { require(params["focus"].is_boolean(), "focus must be boolean"); }
    const std::string preset_id = params.contains("preset") ? required_string(params, "preset") : std::string();
    if (!preset_id.empty() && !viewer.presets_loaded()) {
      complete(Error::make(ErrorCode::Busy, "Viewer presets are still loading; inspect viewer.presets()")); return;
    }
    require(preset_id.empty() || viewer.preset(preset_id), "Unknown Viewer preset: " + preset_id);
    const Json parameters = params.value("parameters", Json::object());
    check_parameters(preset_id.empty() ? nullptr : viewer.preset(preset_id), parameters);
    std::string why;
    const auto source = classify_path(path, &why);
    require(source.kind != SourceKind::None, why);
    require(source.evaluates() || (preset_id.empty() && parameters.empty()), "Payload/result sources do not accept a graph preset or parameters");
    if (!viewer.open_path(path, preset_id, parameters)) {
      complete(Error::make(ErrorCode::InvalidParams, viewer.open_error())); return;
    }
    if (params.value("focus", true)) { focus_viewer(screen); }
  }
  else if (operation == "viewer.close") { viewer.close(); }
  else if (operation == "viewer.configure") {
    // Validate the whole update before changing any display setting or scheduling evaluation.
    const Json parameters = params.value("parameters", Json::object());
    check_parameters(viewer.preset(viewer.preset_id()), parameters);
    require(parameters.empty() || viewer.source().evaluates(), "The current Viewer source has no graph parameters");
    for (const auto *key : {"auto_evaluate", "overlays", "prefetch", "loop"}) {
      if (params.contains(key)) { require(params[key].is_boolean(), std::string(key) + " must be boolean"); }
    }
    if (params.contains("fps")) {
      require(io::is_finite_number(params["fps"]) && params["fps"] >= 0.1 && params["fps"] <= 60, "fps must be between 0.1 and 60");
    }
    if (params.contains("auto_evaluate")) { viewer.set_auto_evaluate(params["auto_evaluate"].get<bool>()); }
    if (params.contains("overlays")) { viewer.set_overlays(params["overlays"].get<bool>()); }
    if (params.contains("prefetch")) { viewer.prefetch_neighbours = params["prefetch"].get<bool>(); }
    if (params.contains("fps")) { viewer.fps = params["fps"].get<double>(); }
    if (params.contains("loop")) { viewer.loop = params["loop"].get<bool>(); }
    for (auto it = parameters.begin(); it != parameters.end(); ++it) { viewer.set_parameter(it.key(), ui::form_value_from_json(it.value())); }
  }
  else if (operation == "viewer.preset") {
    const auto id = required_string(params, "id");
    require(viewer.preset(id), "Unknown Viewer preset: " + id);
    require(viewer.source().evaluates(), "Choose a run directory or task before changing the preset");
    viewer.select_preset(id);
  }
  else if (operation == "viewer.layer") {
    const auto id = required_string(params, "id");
    const auto layers = viewer.layers();
    const auto layer = std::find_if(layers.begin(), layers.end(), [&](const auto &row) { return row.id == id; });
    require(layer != layers.end(), "Unknown Viewer layer: " + id);
    require(params.contains("visible") || params.contains("opacity"), "Supply visible or opacity");
    if (params.contains("visible")) { require(params["visible"].is_boolean(), "visible must be boolean"); }
    if (params.contains("opacity")) {
      require(layer->has_opacity && io::is_finite_number(params["opacity"]) && params["opacity"] >= 0 && params["opacity"] <= 1,
              "This layer needs an opacity between 0 and 1");
    }
    if (params.contains("visible")) { viewer.set_layer_visible(id, params["visible"].get<bool>()); }
    if (params.contains("opacity")) { viewer.set_layer_opacity(id, params["opacity"].get<double>()); }
  }
  else if (operation == "viewer.step") {
    require(params.contains("index") && params["index"].is_number_integer() && params["index"] >= 0 &&
            params["index"] < viewer.step_choices().size(), "index must identify an available time step");
    viewer.set_step_index(params["index"].get<int>());
  }
  else if (operation == "viewer.play") {
    require(params.contains("playing") && params["playing"].is_boolean(), "playing must be boolean");
    require(!params["playing"].get<bool>() || !viewer.step_choices().empty(), "No time steps are available");
    viewer.set_playing(params["playing"].get<bool>());
  }
  else if (operation == "viewer.evaluate") {
    require(viewer.source().evaluates(), "The Viewer source does not use graph evaluation");
    viewer.evaluate_now("python");
  }
  else if (operation == "viewer.cancel") { viewer.cancel_evaluation(); }
  else if (operation == "viewer.reset_camera") { viewer.request_camera_reset(); }
  // Status polling also services debounce/playback when no Viewer editor is currently visible.
  viewer.pump();
  store_.changed();
  complete(viewer_status(viewer));
}
}  // namespace stk::app
