/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * ViewerState: the result being viewed, shared by the Viewer, Properties and Probe editors (WP10).
 * CPU only (no GPU / GHOST headers), so the logic is unit-testable against the fake bridge.
 *
 * Sources (#open / #open_path, drag and drop, File > Open, Jobs "Open in viewer"):
 *   - a payload: a .stkp file, a payload directory or its manifest.json (shown as is);
 *   - a result directory written by `suan graph run` (result.json, or series.json with one
 *     result per step: the steps become the time-step scrubber);
 *   - a run directory: evaluated in the bridge with `graph.evaluate` (local mode,
 *     local_bindings {binding: dir});
 *   - a task: `graph.evaluate` in local mode with a Runtime task binding, or in hub mode.
 *
 * Evaluating sources carry a preset (stk.graph/1) and a parameter form generated from JSON Schema
 * (stk_ui preset_schema + build_form). Edits are debounced; a new evaluation cancels the one it
 * supersedes (the bridge future's cancel sends graph.cancel); graph.progress drives the progress
 * bar. A client-stage edit re-runs no data node (asserted from result.evaluated by the tests).
 *
 * Time steps: the result's step choices drive a scrubber with playback. Results are cached per
 * (source, preset, parameters with the resolved step); the neighbours of the shown step are
 * evaluated in the background (prefetch), so a cached step switches without a bridge round trip.
 * The camera is kept across steps (the view's camera signature is unchanged); #camera_serial bumps
 * when the view must reset (a new source or preset).
 *
 * Main thread only. Bridge callbacks arrive through the client's executor (the main loop).
 */
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "stk/app/app_store.hh"
#include "stk/io/json.hh"
#include "stk/io/result.hh"
#include "stk/ui/form.hh"

namespace stk::io {
class Payload;
}

namespace stk::app {

enum class SourceKind : uint8_t { None, Payload, ResultDir, RunDir, Task };
const char *source_kind_name(SourceKind kind);

struct ViewerSource {
  SourceKind kind = SourceKind::None;
  /** Payload file or directory, result directory, or run directory (absolute). */
  std::string path;
  /** Tasks: bridge connection ("runtime:<name>", "hub:<name>"), hub node, workspace, task. */
  std::string connection, node, workspace_id, task_id;
  /** Result directories: series.json (steps) instead of result.json. */
  bool series = false;

  bool evaluates() const
  {
    return kind == SourceKind::RunDir || kind == SourceKind::Task;
  }
  bool hub() const
  {
    return connection.rfind("hub:", 0) == 0;
  }
  /** Short text for the UI (file name or task id). */
  std::string label() const;
  /** Stable identity (cache keys). */
  std::string key() const;
};

/**
 * What a local path is: a .stkp file, a payload directory (manifest.json with schema
 * stk.payload/2) or that manifest, a result directory (result.json / series.json) or a run
 * directory (any other directory). Kind None with `r_error` when it cannot be opened.
 */
ViewerSource classify_path(const std::string &path, std::string *r_error = nullptr);
/** A preset for a run directory: muFerro frames (Polar.*) -> "muferro-domains"; else "". */
std::string guess_preset(const std::string &run_dir);

struct PresetInfo {
  std::string id, name, description;
  std::vector<std::string> bindings;
  io::Json raw; /**< {id, name, description, graph, bindings, parameters} */
};

struct EvalProgress {
  bool running = false;
  std::string eval_id;
  std::string reason;
  int started = 0, finished = 0, cached = 0, failed = 0;
  /** Nodes the graph evaluates for the requested outputs (0 = unknown). */
  int expected = 0;
  std::string node;    /**< last started node */
  std::string message; /**< last warning or progress message */
  /** A hub evaluation waits for review. */
  bool review = false;
  double started_at = 0.0;

  float fraction() const;
};

/** The evaluation behind the payload on screen. */
struct EvalRecord {
  std::string eval_id;
  /** open, preset, data, client, step, prefetch, manual. */
  std::string reason;
  std::vector<std::string> evaluated;
  /** evaluated nodes of stage source / data / analysis (none after a client-stage change). */
  std::vector<std::string> data_nodes;
  int64_t cache_hits = 0, cache_misses = 0;
  double seconds = 0.0;
  /** Served from the viewer's own result cache (no bridge call). */
  bool from_cache = false;
};

/** A pick of the Viewer (GPU id pass refined in float64). */
struct PickInfo {
  std::string layer_id, layer_name, layer_type;
  uint32_t element = 0;
  std::array<double, 3> physical{};
  /** Where view.probe reads (payload layer pick.probe, else the layer node). */
  std::string probe_node, probe_dataset;
};

struct ProbeState {
  enum class Status : uint8_t { Empty, Pending, Done, Failed, Unavailable };
  Status status = Status::Empty;
  PickInfo pick;
  /** bridge `probe` result: target {binding, task_id?, path, node, metadata?} and sample
   * {position, values, units, interpolation, source}. */
  io::Json target, sample;
  std::string error;
  uint64_t serial = 0;
};

struct ExportSettings {
  int width = 1600, height = 1200;
  int magnification = 1; /**< 1..8 (tiled) */
  bool transparent = false;
  bool overlays = true;
  /** PNG path; a sequence writes <stem>.%08d.png per step and <stem>.series.json. */
  std::string path;
  bool sequence = false;
};

/** Work for the GPU side (the Viewer editor, or the headless exporter). */
struct ExportJob {
  ExportSettings settings;
  /** One frame (PNG) or every step (sequence), in order: (step value, payload). */
  std::vector<std::pair<io::Json, std::shared_ptr<const io::Payload>>> frames;
  std::string parameter; /**< the step parameter (sequence) */
  bool ready = false;    /**< every frame is available */
  size_t pending = 0;    /**< frames still being evaluated */
};

/** stk.series/1 file names of a sequence export: "<dir>/<stem>.%08d.png" and "<dir>/<stem>.series.json". */
std::string sequence_frame_path(const std::string &png_path, const io::Json &step);
std::string sequence_manifest_path(const std::string &png_path);

class ViewerState {
 public:
  explicit ViewerState(AppStore &store);
  ~ViewerState();
  ViewerState(const ViewerState &) = delete;
  ViewerState &operator=(const ViewerState &) = delete;

  AppStore &store() const
  {
    return store_;
  }
  /** Seconds (steady clock by default; tests replace it). */
  std::function<double()> clock;
  double now() const;

  /* ---- Metadata from the bridge (graph.presets, graph.catalog, colormaps.list) ---- */

  /** Requests what is missing (or everything with `force`) once the bridge is ready. */
  void refresh_metadata(bool force = false);
  bool presets_loaded() const;
  const std::vector<PresetInfo> &presets() const;
  const PresetInfo *preset(const std::string &id) const;
  /** stk.catalog/1 document (null until loaded). */
  const io::Json &catalog() const;
  /** colormaps.list as gradient items (null until loaded). */
  std::shared_ptr<const std::vector<ui::ColormapItem>> colormaps() const;
  const std::string &metadata_error() const;
  /** Uses a graph.presets result ({presets: [...]}) and a stk.catalog/1 document directly (offline
   * use and tests); colormaps stay as they are. */
  void set_metadata(const io::Json &presets_result, const io::Json &catalog);
  void set_colormaps(std::shared_ptr<const std::vector<ui::ColormapItem>> colormaps);

  /* ---- Sources ---- */

  /** Jobs "Open in viewer" and File > Open. False (with #open_error) when nothing can be opened. */
  bool open(const OpenResultRequest &request);
  /** `parameters` ({name: value}) override the preset defaults of an evaluated source. */
  bool open_path(const std::string &path, const std::string &preset = {}, const io::Json &parameters = io::Json());
  /** Shows an in-memory payload (tests, tools). */
  void open_payload(std::shared_ptr<const io::Payload> payload, std::string label);
  void close();
  const ViewerSource &source() const;
  const std::string &source_label() const;
  const std::string &open_error() const;

  /* ---- Preset and parameters ---- */

  const std::string &preset_id() const;
  /** Selects a preset (form reset to its defaults) and evaluates when the source evaluates. */
  void select_preset(const std::string &id);
  /** Form schema of the current preset (stk_ui preset_schema); empty object without one. */
  const ui::SchemaNode &schema() const;
  ui::FormModel &form();
  /** The form's values as graph parameters (nulls dropped). */
  io::Json parameters() const;
  /** "data" / "client" ("" for unknown names). */
  std::string param_stage(const std::string &name) const;
  /** Same as form().set(name, value). */
  void set_parameter(const std::string &name, ui::FormValue value);
  /** Evaluate automatically after edits (else only with #evaluate_now). */
  bool auto_evaluate = true;
  /** Debounce of data-stage and client-stage edits (seconds). */
  double data_debounce_s = 0.35;
  double client_debounce_s = 0.06;
  /** Output names the evaluation requests (the preset's payload outputs). */
  std::vector<std::string> payload_outputs() const;

  /* ---- Evaluation ---- */

  void evaluate_now(const std::string &reason = "manual");
  /** Cancels the running evaluation and pending edits. */
  void cancel_evaluation();
  bool evaluating() const;
  const EvalProgress &progress() const;
  /** The evaluation behind the payload on screen. */
  const std::optional<EvalRecord> &last_eval() const;
  /** The graph result on screen (nullopt for plain payloads). */
  const std::optional<io::GraphResult> &result() const;
  const std::string &eval_error() const;
  /** Node ids of the preset graph whose stage is source / data / analysis (from the catalog). */
  std::vector<std::string> data_nodes() const;
  /** Bridge evaluations started (main + prefetch) and superseded ones cancelled. */
  int evaluations_started() const;
  int evaluations_cancelled() const;
  /** Pending debounced edit (the reason it will evaluate with), empty when none. */
  const std::string &pending_edit() const;

  /* ---- Time steps ---- */

  /** The preset's step parameter ("" when it has none). */
  const std::string &step_param() const;
  /** Choices of the step (result parameters, else series frames). */
  const std::vector<io::Json> &step_choices() const;
  /** Index of the shown step in #step_choices, -1 when unknown. */
  int step_index() const;
  io::Json shown_step() const;
  void set_step_index(int index);
  void step_by(int delta);
  /** Follows the latest frame again ("latest"). */
  void step_latest();
  bool playing() const;
  void set_playing(bool playing);
  double fps = 4.0;
  bool loop = true;
  bool prefetch_neighbours = true;
  /** Milliseconds from the last step request to its payload being current. */
  double last_step_switch_ms() const;
  size_t cached_results() const;
  /** Prefetch evaluations completed (neighbour steps). */
  int prefetched_count() const;

  /* ---- Payload on screen ---- */

  /** The payload with the display overrides (layer opacity) applied; null when none. */
  std::shared_ptr<const io::Payload> payload() const;
  /** The payload as delivered. */
  std::shared_ptr<const io::Payload> base_payload() const;
  /** Bumps whenever #payload changes. */
  uint64_t payload_serial() const;
  /** Bumps when views must reset their camera (new source or preset, explicit reset). */
  uint64_t camera_serial() const;
  void request_camera_reset();
  /** Payloads to upload ahead (prefetched neighbour steps); cleared by the call. */
  std::vector<std::shared_ptr<const io::Payload>> take_prefetched();
  /** Payload warnings (skipped layers) and result warnings, for display. */
  std::vector<std::string> warnings() const;
  /** "12,345 triangles · 1 volume · 312 KiB" style summary parts from manifest stats. */
  std::string stats_text() const;

  /* ---- Layers (display state, kept by layer id across steps) ---- */

  struct LayerRow {
    std::string id, name, type, kind;
    bool visible = true;
    bool has_opacity = false; /**< layers with appearance.opacity */
    double opacity = 1.0;
    bool pickable = false;
  };
  std::vector<LayerRow> layers() const;
  void set_layer_visible(const std::string &id, bool visible);
  void set_layer_opacity(const std::string &id, double opacity);
  /** Explicit visibility toggles (applied by the views on top of the payload's own). */
  const std::map<std::string, bool> &visibility() const;
  bool overlays() const;
  void set_overlays(bool on);

  /* ---- Picking and probing ---- */

  /** A pick from a view: queries the bridge probe for evaluated sources. */
  void set_pick(PickInfo pick);
  /** Re-queries at a typed physical position (same layer). */
  void probe_position(const std::array<double, 3> &position);
  void clear_pick();
  const ProbeState &probe() const;

  /* ---- Dialogs and export ---- */

  bool open_dialog = false;
  std::string open_dialog_path;
  bool export_dialog = false;
  ExportSettings export_settings;
  /** Starts an export with #export_settings (a sequence evaluates or loads every step first). */
  void request_export();
  /** The export waiting for the GPU side (null when none). */
  ExportJob *export_job();
  void finish_export(bool ok, const std::string &message);
  const std::string &export_status() const;
  /** Writes the stk.series/1 manifest of a finished sequence (called by the exporter). */
  static bool write_series(const ExportJob &job, std::string *r_error = nullptr);

  /* ---- Main loop ---- */

  /** Runs due work (debounced edits, playback, prefetch, metadata); returns the absolute time
   * (#now) of the next wake-up, +inf when idle. Cheap; editors call it while building. */
  double pump();
  /** Bumps on every change (views re-read). */
  uint64_t version() const;

  /** Live Viewer editors and the one hosting the dialogs (see the Viewer editor). */
  int viewer_editors = 0;
  const void *dialog_host = nullptr;
  /** The wake-up (#now time) a window-manager timer is already scheduled for. */
  double wake_scheduled = -1.0;

  struct Impl;

 private:
  AppStore &store_;
  std::unique_ptr<Impl> impl_;
};

}  // namespace stk::app
