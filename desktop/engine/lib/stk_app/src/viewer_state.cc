/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/viewer_state.hh"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <set>

#include "stk/bridge/client.hh"
#include "stk/core/paths.hh"
#include "stk/io/blob_cache.hh"
#include "stk/io/catalog.hh"
#include "stk/io/payload.hh"
#include "stk/ui/form_json.hh"

namespace stk::app {

namespace fs = std::filesystem;
using io::Json;

namespace {

constexpr double kInf = std::numeric_limits<double>::infinity();
/** Results kept per source (payloads share buffers, so neighbouring steps are cheap). */
constexpr size_t kMaxCachedResults = 32;

std::string dumps(const Json &j)
{
  return io::python_json_dumps(j, true, true);
}

bool ends_with(const std::string &s, const std::string &suffix)
{
  return s.size() >= suffix.size() && s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

std::string file_name(const std::string &path)
{
  const size_t p = path.find_last_of("/\\");
  return p == std::string::npos ? path : path.substr(p + 1);
}

bool read_json(const fs::path &path, Json &out)
{
  try {
    out = io::read_json_file(path);
    return true;
  }
  catch (const std::exception &) {
    return false;
  }
}

/** A step value as a number when it is one ("12" stays a string only if it is not numeric). */
bool json_equal_step(const Json &a, const Json &b)
{
  if (a.is_number() && b.is_number()) {
    return a.get<double>() == b.get<double>();
  }
  return a == b;
}

std::string error_text(const bridge::Error &e)
{
  std::string s = e.message.empty() ? e.name : e.message;
  if (e.data.is_object()) {
    if (const auto it = e.data.find("errors"); it != e.data.end() && it->is_array() && !it->empty()) {
      const Json &first = (*it)[0];
      const std::string node = io::get_string(first, "node"), msg = io::get_string(first, "message");
      if (!msg.empty()) {
        s += node.empty() ? ": " + msg : " (" + node + ": " + msg + ")";
      }
    }
    if (const auto it = e.data.find("issues"); it != e.data.end() && it->is_array() && !it->empty()) {
      const std::string msg = io::get_string((*it)[0], "message");
      if (!msg.empty()) {
        s += ": " + msg;
      }
    }
  }
  return s;
}

}  // namespace

/* -------------------------------------------------------------------- */
/** \name Sources
 * \{ */

const char *source_kind_name(const SourceKind kind)
{
  switch (kind) {
    case SourceKind::None: return "none";
    case SourceKind::Payload: return "payload";
    case SourceKind::ResultDir: return "result";
    case SourceKind::RunDir: return "run";
    case SourceKind::Task: return "task";
  }
  return "none";
}

std::string ViewerSource::label() const
{
  switch (kind) {
    case SourceKind::None: return {};
    case SourceKind::Task: return task_id.empty() ? connection : task_id + (connection.empty() ? "" : " @ " + connection);
    default: {
      std::string p = path;
      while (p.size() > 1 && (p.back() == '/' || p.back() == '\\')) {
        p.pop_back();
      }
      return file_name(p);
    }
  }
}

std::string ViewerSource::key() const
{
  return std::string(source_kind_name(kind)) + "|" + path + "|" + connection + "|" + node + "|" + task_id;
}

ViewerSource classify_path(const std::string &path, std::string *r_error)
{
  ViewerSource s;
  auto fail = [&](const std::string &why) {
    if (r_error) {
      *r_error = why;
    }
    return ViewerSource{};
  };
  if (path.empty()) {
    return fail("empty path");
  }
  std::error_code ec;
  fs::path p = core::path_from_utf8(path);
  if (!p.is_absolute()) {
    p = fs::absolute(p, ec);
  }
  p = p.lexically_normal();
  if (!fs::exists(p, ec)) {
    return fail("not found: " + path);
  }
  const std::string abs = core::path_to_utf8(p);
  if (fs::is_regular_file(p, ec)) {
    if (ends_with(abs, ".stkp")) {
      s.kind = SourceKind::Payload;
      s.path = abs;
      return s;
    }
    const std::string name = file_name(abs);
    Json doc;
    if (name == "manifest.json" && read_json(p, doc) && io::get_string(doc, "schema") == io::kPayloadSchema) {
      s.kind = SourceKind::Payload;
      s.path = core::path_to_utf8(p.parent_path());
      return s;
    }
    if ((name == "series.json" || (name.rfind("result", 0) == 0 && ends_with(name, ".json"))) && read_json(p, doc)) {
      const std::string schema = io::get_string(doc, "schema");
      if (schema == io::kSeriesSchema || schema == io::kResultSchema) {
        s.kind = SourceKind::ResultDir;
        s.path = core::path_to_utf8(p.parent_path());
        s.series = schema == io::kSeriesSchema;
        return s;
      }
    }
    return fail("not a payload (.stkp, manifest.json) or a result (result.json, series.json): " + path);
  }
  if (!fs::is_directory(p, ec)) {
    return fail("not a file or directory: " + path);
  }
  Json doc;
  if (fs::is_regular_file(p / "manifest.json", ec) && read_json(p / "manifest.json", doc) &&
      io::get_string(doc, "schema") == io::kPayloadSchema)
  {
    s.kind = SourceKind::Payload;
    s.path = abs;
    return s;
  }
  if (fs::is_regular_file(p / "series.json", ec) && read_json(p / "series.json", doc) &&
      io::get_string(doc, "schema") == io::kSeriesSchema)
  {
    s.kind = SourceKind::ResultDir;
    s.path = abs;
    s.series = true;
    return s;
  }
  if (fs::is_regular_file(p / "result.json", ec) && read_json(p / "result.json", doc) &&
      io::get_string(doc, "schema") == io::kResultSchema)
  {
    s.kind = SourceKind::ResultDir;
    s.path = abs;
    return s;
  }
  s.kind = SourceKind::RunDir;
  s.path = abs;
  return s;
}

std::string guess_preset(const std::string &run_dir)
{
  std::error_code ec;
  const fs::path root = core::path_from_utf8(run_dir);
  auto has_polar = [&](const fs::path &dir) {
    for (fs::directory_iterator it(dir, ec), end; !ec && it != end; it.increment(ec)) {
      const std::string n = core::path_to_utf8(it->path().filename());
      if (n.rfind("Polar.", 0) == 0) {
        return true;
      }
    }
    return false;
  };
  if (has_polar(root)) {
    return "muferro-domains";
  }
  /* One level down (Runtime task directories keep outputs in a subdirectory). */
  for (fs::directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec)) {
    if (it->is_directory(ec) && has_polar(it->path())) {
      return "muferro-domains";
    }
  }
  return {};
}

std::string sequence_frame_path(const std::string &png_path, const Json &step)
{
  fs::path p = core::path_from_utf8(png_path);
  std::string stem = core::path_to_utf8(p.stem());
  std::string suffix;
  if (step.is_number_integer() && step.get<int64_t>() >= 0) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), ".%08lld", (long long)step.get<int64_t>());
    suffix = buf;
  }
  else if (step.is_number()) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), ".%08lld", (long long)std::llround(step.get<double>()));
    suffix = buf;
  }
  else {
    std::string t = step.is_string() ? step.get<std::string>() : step.dump();
    suffix = ".";
    for (const char c : t) {
      suffix += (std::isalnum(uint8_t(c)) || c == '_' || c == '-') ? c : '_';
    }
  }
  return core::path_to_utf8(p.parent_path() / core::path_from_utf8(stem + suffix + ".png"));
}

std::string sequence_manifest_path(const std::string &png_path)
{
  fs::path p = core::path_from_utf8(png_path);
  return core::path_to_utf8(p.parent_path() / core::path_from_utf8(core::path_to_utf8(p.stem()) + ".series.json"));
}

float EvalProgress::fraction() const
{
  if (!running) {
    return 1.0f;
  }
  const int done = finished + cached + failed;
  if (expected > 0) {
    return std::clamp(float(done) / float(expected), 0.0f, 0.99f);
  }
  return started > 0 ? std::clamp(float(done) / float(std::max(started, 1) + 1), 0.0f, 0.95f) : 0.0f;
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Implementation state
 * \{ */

struct ViewerState::Impl {
  ViewerState &self;
  AppStore &store;
  std::shared_ptr<int> alive = std::make_shared<int>(0);
  uint64_t version = 0;

  /* Metadata. */
  bool presets_requested = false, catalog_requested = false, colormaps_requested = false;
  bool presets_loaded = false;
  std::vector<PresetInfo> presets;
  Json catalog;
  std::optional<io::Catalog> catalog_model;
  std::shared_ptr<const std::vector<ui::ColormapItem>> colormaps;
  std::string metadata_error;

  /* Source. */
  ViewerSource source;
  std::string label, open_error;
  bool waiting_for_metadata = false;
  /* Parameters to apply once the form exists (open_path). */
  Json initial_params;
  /* Result directories. */
  Json series_doc;
  std::string series_param;

  /* Preset and form. */
  std::string preset_id;
  ui::SchemaNode schema;
  ui::FormModel form;
  bool form_quiet = false;
  std::string step_param;
  std::string pending_reason;
  double pending_at = kInf;

  /* Evaluations. */
  struct Running {
    std::string eval_id, key, reason;
    Json params;
    double t0 = 0.0;
    bridge::Future<bridge::HubPolicy> policy_future;
    bridge::Future<bridge::EvaluateResult> future;
  };
  std::optional<Running> main, prefetch;
  uint64_t seq = 0;
  EvalProgress progress;
  std::optional<EvalRecord> last;
  std::optional<io::GraphResult> result;
  Json shown_params;
  std::string eval_error;
  int started = 0, cancelled = 0, prefetched = 0;

  struct Frame {
    io::GraphResult result;
    std::shared_ptr<const io::Payload> payload;
    EvalRecord record;
    Json step;
    Json params;
    uint64_t use = 0;
  };
  std::map<std::string, Frame> cache;
  uint64_t use_clock = 0;

  /* Steps. */
  std::vector<Json> choices;
  Json shown_step;
  bool playing = false;
  double next_frame_at = kInf;
  double step_request_at = -1.0;
  double last_switch_ms = -1.0;

  /* Payload. */
  std::shared_ptr<const io::Payload> base, display;
  uint64_t payload_serial = 0, camera_serial = 0;
  std::vector<std::shared_ptr<const io::Payload>> prefetched_payloads;

  /* Layers. */
  std::map<std::string, bool> visibility;
  std::map<std::string, double> opacity;
  bool overlays = true;

  /* Probe. */
  ProbeState probe;
  bridge::Future<Json> probe_future;

  /* Export. */
  std::optional<ExportJob> job;
  std::string export_status;

  Impl(ViewerState &s, AppStore &st) : self(s), store(st) {}

  double now() const
  {
    return self.now();
  }

  void changed()
  {
    version++;
    store.changed();
  }

  bridge::Client *client() const
  {
    return store.bridge();
  }

  bool bridge_ready() const
  {
    bridge::Client *c = client();
    return c && c->state() == bridge::BridgeState::Ready;
  }

  /* ---- Metadata ---- */

  void request_metadata(const bool force)
  {
    bridge::Client *c = client();
    if (!c || !bridge_ready()) {
      return;
    }
    std::weak_ptr<int> weak = alive;
    if (force || !presets_requested) {
      presets_requested = true;
      c->graph_presets().then([this, weak](bridge::Result<Json> r) {
        if (weak.expired()) {
          return;
        }
        if (!r.ok()) {
          metadata_error = error_text(r.error());
          presets_requested = false;
          changed();
          return;
        }
        parse_presets(r.value());
        presets_loaded = true;
        metadata_arrived();
      });
    }
    if (force || !catalog_requested) {
      catalog_requested = true;
      c->graph_catalog().then([this, weak](bridge::Result<Json> r) {
        if (weak.expired()) {
          return;
        }
        if (!r.ok()) {
          metadata_error = error_text(r.error());
          catalog_requested = false;
          changed();
          return;
        }
        set_catalog(r.value().contains("catalog") ? r.value()["catalog"] : Json());
        metadata_arrived();
      });
    }
    if (force || !colormaps_requested) {
      colormaps_requested = true;
      c->colormaps_list().then([this, weak](bridge::Result<bridge::ColormapList> r) {
        if (weak.expired()) {
          return;
        }
        if (!r.ok()) {
          metadata_error = error_text(r.error());
          colormaps_requested = false;
          changed();
          return;
        }
        auto items = std::make_shared<std::vector<ui::ColormapItem>>();
        for (const bridge::Colormap &cm : r.value().colormaps) {
          ui::ColormapItem item;
          item.name = cm.name;
          item.lut.reserve(256);
          for (size_t i = 0; i < 256; i++) {
            item.lut.push_back(ui::Color{cm.lut_rgba8[i * 4], cm.lut_rgba8[i * 4 + 1], cm.lut_rgba8[i * 4 + 2],
                                         cm.lut_rgba8[i * 4 + 3]});
          }
          items->push_back(std::move(item));
        }
        colormaps = std::move(items);
        changed();
      });
    }
  }

  void parse_presets(const Json &result)
  {
    presets.clear();
    const Json &list = result.contains("presets") ? result["presets"] : Json::array();
    for (const Json &p : list) {
      if (!p.is_object()) {
        continue;
      }
      PresetInfo info;
      info.id = io::get_string(p, "id");
      info.name = io::get_string(p, "name", info.id);
      info.description = io::get_string(p, "description");
      if (const auto it = p.find("bindings"); it != p.end() && it->is_array()) {
        for (const Json &b : *it) {
          info.bindings.push_back(b.is_object() ? io::get_string(b, "name") : b.is_string() ? b.get<std::string>() : "");
        }
      }
      info.raw = p;
      if (!info.id.empty()) {
        presets.push_back(std::move(info));
      }
    }
  }

  void set_catalog(const Json &doc)
  {
    catalog = doc;
    try {
      catalog_model = io::Catalog::from_json(catalog);
    }
    catch (const std::exception &e) {
      metadata_error = e.what();
      catalog_model.reset();
    }
  }

  bool have_metadata() const
  {
    return presets_loaded && !catalog.is_null();
  }

  void metadata_arrived()
  {
    if (have_metadata()) {
      if (!waiting_for_metadata && !preset_id.empty() && schema.properties.empty()) {
        build_form(false);
      }
      if (waiting_for_metadata) {
        waiting_for_metadata = false;
        if (preset_id.empty() && !presets.empty()) {
          preset_id = presets.front().id;
        }
        build_form(false);
        start_eval("open");
      }
    }
    changed();
  }

  const PresetInfo *preset(const std::string &id) const
  {
    for (const PresetInfo &p : presets) {
      if (p.id == id) {
        return &p;
      }
    }
    return nullptr;
  }

  const Json *graph() const
  {
    const PresetInfo *p = preset(preset_id);
    if (!p) {
      return nullptr;
    }
    const auto it = p->raw.find("graph");
    return it != p->raw.end() && it->is_object() ? &*it : nullptr;
  }

  std::string binding_name() const
  {
    const PresetInfo *p = preset(preset_id);
    return p && !p->bindings.empty() && !p->bindings.front().empty() ? p->bindings.front() : "run";
  }

  void build_form(const bool keep_values)
  {
    std::map<std::string, ui::FormValue> old;
    if (keep_values) {
      old = form.values();
    }
    schema = ui::SchemaNode{};
    schema.type = ui::SchemaType::Object;
    step_param.clear();
    const PresetInfo *p = preset(preset_id);
    if (p && !catalog.is_null()) {
      try {
        schema = ui::preset_schema(p->raw, catalog);
      }
      catch (const std::exception &e) {
        eval_error = std::string("form: ") + e.what();
      }
    }
    if (const Json *g = graph()) {
      if (const auto it = g->find("parameters"); it != g->end() && it->is_array()) {
        for (const Json &decl : *it) {
          if (io::get_string(decl, "type") == "step") {
            step_param = io::get_string(decl, "name");
            break;
          }
        }
      }
    }
    form = ui::FormModel{};
    form_quiet = true;
    for (const auto &[k, v] : old) {
      if (schema.property(k)) {
        form.set(k, v);
      }
    }
    form.init_defaults(schema);
    if (initial_params.is_object()) {
      for (auto it = initial_params.begin(); it != initial_params.end(); ++it) {
        if (schema.property(it.key())) {
          form.set(it.key(), ui::form_value_from_json(it.value()));
        }
      }
      initial_params = Json();
    }
    form_quiet = false;
    form.on_change = [this](const std::string &name, const ui::FormValue &) { on_param_changed(name); };
  }

  /* ---- Parameters ---- */

  Json parameters() const
  {
    Json out = Json::object();
    if (schema.properties.empty()) {
      return out;
    }
    const nlohmann::ordered_json values = ui::form_values_to_ordered_json(form, schema);
    for (auto it = values.begin(); it != values.end(); ++it) {
      if (!it.value().is_null()) {
        out[it.key()] = it.value();
      }
    }
    return out;
  }

  std::string param_stage(const std::string &name) const
  {
    const ui::SchemaNode *n = schema.property(name);
    return n ? n->stage : std::string();
  }

  void on_param_changed(const std::string &name)
  {
    if (form_quiet) {
      return;
    }
    const bool is_step = !step_param.empty() && name == step_param;
    const std::string stage = param_stage(name);
    const bool client = stage == "client";
    std::string reason = is_step ? "step" : client ? "client" : "data";
    /* A pending data-stage edit wins over a later client-stage one (it evaluates everything). */
    if (pending_reason == "data" || (pending_reason == "step" && reason == "client")) {
      reason = pending_reason;
    }
    if (!is_step) {
      cancel_prefetch();
    }
    pending_reason = reason;
    if (self.auto_evaluate && source.evaluates()) {
      pending_at = now() + (reason == "client" ? self.client_debounce_s : self.data_debounce_s);
    }
    else {
      pending_at = kInf;
    }
    changed();
  }

  /* ---- Evaluation ---- */

  std::vector<std::string> payload_outputs() const
  {
    std::vector<std::string> out;
    const Json *g = graph();
    if (!g) {
      return out;
    }
    std::map<std::string, std::string> types;
    if (const auto it = g->find("nodes"); it != g->end() && it->is_array()) {
      for (const Json &n : *it) {
        types[io::get_string(n, "id")] = io::get_string(n, "type");
      }
    }
    if (const auto it = g->find("outputs"); it != g->end() && it->is_object()) {
      for (auto o = it->begin(); o != it->end(); ++o) {
        if (!o.value().is_string()) {
          continue;
        }
        const std::string ref = o.value().get<std::string>();
        const std::string node = ref.substr(0, ref.find('.'));
        const std::string type = types[node];
        if (type.rfind("stk.view.scene@", 0) == 0 || type.rfind("stk.output.payload@", 0) == 0) {
          out.push_back(o.key());
        }
      }
    }
    return out;
  }

  std::vector<std::string> data_nodes() const
  {
    std::vector<std::string> out;
    const Json *g = graph();
    if (!g || !catalog_model) {
      return out;
    }
    if (const auto it = g->find("nodes"); it != g->end() && it->is_array()) {
      for (const Json &n : *it) {
        const io::NodeType *t = catalog_model->find(io::get_string(n, "type"));
        const std::string stage = t ? t->stage : std::string();
        if (stage == "source" || stage == "data" || stage == "analysis") {
          out.push_back(io::get_string(n, "id"));
        }
      }
    }
    return out;
  }

  int expected_nodes() const
  {
    const Json *g = graph();
    if (!g) {
      return 0;
    }
    /* Ancestors of the payload outputs. */
    std::map<std::string, std::vector<std::string>> inputs;
    if (const auto it = g->find("nodes"); it != g->end() && it->is_array()) {
      for (const Json &n : *it) {
        std::vector<std::string> up;
        if (const auto in = n.find("inputs"); in != n.end() && in->is_object()) {
          for (auto l = in->begin(); l != in->end(); ++l) {
            auto add = [&](const Json &link) {
              const std::string from = io::get_string(link, "from");
              up.push_back(from.substr(0, from.find('.')));
            };
            if (l.value().is_array()) {
              for (const Json &link : l.value()) {
                add(link);
              }
            }
            else {
              add(l.value());
            }
          }
        }
        inputs[io::get_string(n, "id")] = std::move(up);
      }
    }
    std::set<std::string> seen;
    std::vector<std::string> todo;
    const Json &outs = (*g)["outputs"];
    for (const std::string &name : payload_outputs()) {
      const std::string ref = io::get_string(outs, name);
      todo.push_back(ref.substr(0, ref.find('.')));
    }
    while (!todo.empty()) {
      const std::string n = todo.back();
      todo.pop_back();
      if (!seen.insert(n).second) {
        continue;
      }
      for (const std::string &u : inputs[n]) {
        todo.push_back(u);
      }
    }
    return int(seen.size());
  }

  std::string cache_key(const Json &params) const
  {
    return source.key() + "|" + preset_id + "|" + dumps(params);
  }

  Json params_with_step(const Json &step) const
  {
    Json p = parameters();
    if (!step_param.empty() && !step.is_null()) {
      p[step_param] = step;
    }
    return p;
  }

  void cancel_prefetch()
  {
    if (prefetch) {
      Running run = std::move(*prefetch);
      prefetch.reset();
      run.policy_future.cancel();
      run.future.cancel();
    }
  }

  void cancel_main()
  {
    if (main) {
      Running run = std::move(*main);
      main.reset();
      run.policy_future.cancel();
      run.future.cancel();
      cancelled++;
      progress.running = false;
    }
  }

  /** Shows a cached frame (no bridge call). */
  void show_cached(Frame &f, const std::string &reason)
  {
    f.use = ++use_clock;
    EvalRecord rec = f.record;
    rec.reason = reason;
    rec.from_cache = true;
    rec.evaluated.clear();
    rec.data_nodes.clear();
    rec.cache_hits = rec.cache_misses = 0;
    rec.seconds = 0.0;
    show_frame(f, rec);
  }

  void show_frame(const Frame &f, EvalRecord record)
  {
    result = f.result;
    shown_params = f.params;
    base = f.payload;
    apply_display();
    last = std::move(record);
    shown_step = f.step;
    update_choices(f.result);
    eval_error.clear();
    if (step_request_at >= 0.0) {
      last_switch_ms = (now() - step_request_at) * 1000.0;
      step_request_at = -1.0;
    }
    /* A pick follows the shown frame (the probe reads the same step). */
    if (probe.status == ProbeState::Status::Done || probe.status == ProbeState::Status::Failed) {
      query_probe(probe.pick);
    }
    changed();
  }

  void update_choices(const io::GraphResult &r)
  {
    /* Result folders take their steps from series.json. */
    if (step_param.empty() || source.kind == SourceKind::ResultDir) {
      return;
    }
    const auto it = r.parameters.find(step_param);
    if (it != r.parameters.end() && it->second.choices.is_array() && !it->second.choices.empty()) {
      choices.assign(it->second.choices.begin(), it->second.choices.end());
    }
  }

  void store_frame(const std::string &key, Frame f)
  {
    f.use = ++use_clock;
    cache[key] = std::move(f);
    while (cache.size() > kMaxCachedResults) {
      auto oldest = cache.begin();
      for (auto it = cache.begin(); it != cache.end(); ++it) {
        if (it->second.use < oldest->second.use) {
          oldest = it;
        }
      }
      cache.erase(oldest);
    }
  }

  std::string new_eval_id()
  {
    static const long long session = (long long)(std::chrono::steady_clock::now().time_since_epoch().count() & 0xffffff);
    char buf[64];
    std::snprintf(buf, sizeof(buf), "desktop-%06llx-%llu", session, (unsigned long long)++seq);
    return buf;
  }

  Running *running(const std::string &eval_id)
  {
    if (main && main->eval_id == eval_id) {
      return &*main;
    }
    return prefetch && prefetch->eval_id == eval_id ? &*prefetch : nullptr;
  }

  void submit_eval(const bridge::EvaluateParams &ep)
  {
    Running *run = running(ep.eval_id);
    if (!run) {
      return; /* cancelled or superseded while looking up the source hub's policy */
    }
    bridge::Client *c = client();
    if (!c) {
      on_done(ep.eval_id, bridge::Error::make(bridge::ErrorCode::Unavailable,
                                            std::string(store.tr("viewer.error.no_bridge"))));
      return;
    }
    std::weak_ptr<int> weak = alive;
    const std::string eval_id = ep.eval_id;
    bridge::CallOptions call;
    call.timeout_s = 3600.0;
    run->future = c->graph_evaluate(ep, [this, weak, eval_id](const bridge::GraphProgress &p) {
      if (!weak.expired()) {
        on_graph_progress(eval_id, p);
      }
    }, call);
    run->future.then([this, weak, eval_id](bridge::Result<bridge::EvaluateResult> r) {
      if (!weak.expired()) {
        on_done(eval_id, std::move(r));
      }
    });
  }

  /**
   * Evaluates the current parameters (with `step` replacing the step parameter when given).
   * Main evaluations supersede (cancel) the running one; prefetches run one at a time.
   */
  void start_eval(const std::string &reason, const bool is_prefetch = false, const Json &step = Json())
  {
    if (!source.evaluates()) {
      return;
    }
    if (!have_metadata() || preset_id.empty()) {
      waiting_for_metadata = true;
      return;
    }
    const Json params = params_with_step(step);
    const std::string key = cache_key(params);
    if (!is_prefetch) {
      pending_reason.clear();
      pending_at = kInf;
      if (auto it = cache.find(key); it != cache.end()) {
        cancel_main();
        show_cached(it->second, reason);
        schedule_prefetch();
        return;
      }
      if (main && main->key == key) {
        return; /* already on its way */
      }
      if (prefetch && prefetch->key == key) {
        /* The neighbour being prefetched is what is wanted now: promote it. */
        main = std::move(prefetch);
        prefetch.reset();
        main->reason = reason;
        progress = EvalProgress{};
        progress.running = true;
        progress.eval_id = main->eval_id;
        progress.reason = reason;
        progress.expected = expected_nodes();
        progress.started_at = main->t0;
        changed();
        return;
      }
    }
    else if (cache.count(key) || (main && main->key == key) || (prefetch && prefetch->key == key)) {
      return;
    }
    bridge::Client *c = client();
    if (!c) {
      if (!is_prefetch) {
        eval_error = std::string(store.tr("viewer.error.no_bridge"));
        changed();
      }
      return;
    }
    bridge::EvaluateParams ep;
    ep.eval_id = new_eval_id();
    Json request = Json::object();
    request["preset"] = preset_id;
    request["parameters"] = params;
    const std::vector<std::string> outs = payload_outputs();
    if (!outs.empty()) {
      Json o = Json::array();
      for (const std::string &n : outs) {
        o.push_back(n);
      }
      request["outputs"] = o;
    }
    request["profile"] = "desktop";
    const std::string binding = binding_name();
    if (source.kind == SourceKind::RunDir) {
      ep.local_bindings[binding] = source.path;
    }
    else {
      request["bindings"] = Json::object({{binding, Json::object({{"task_id", source.task_id}})}});
      ep.target.connection = source.connection;
      if (source.hub()) {
        ep.mode = "hub";
        ep.target.node = source.node;
      }
    }
    ep.request = std::move(request);
    Running run;
    run.eval_id = ep.eval_id;
    run.key = key;
    run.reason = reason;
    run.params = params;
    run.t0 = now();
    const std::string eval_id = ep.eval_id;
    started++;
    if (is_prefetch) {
      cancel_prefetch();
      prefetch = std::move(run);
    }
    else {
      cancel_main();
      main = std::move(run);
      progress = EvalProgress{};
      progress.running = true;
      progress.eval_id = eval_id;
      progress.reason = reason;
      progress.expected = expected_nodes();
      progress.started_at = main->t0;
      eval_error.clear();
    }
    if (ep.mode == "hub" && c->hello_info() && c->hello_info()->has_method("hub.policy")) {
      /* Desktop auto-run (bridge spec §7.1) needs the viewed result's hub cap, independently of
       * the Jobs selection. Query before submission, including when that hub was never active. */
      std::weak_ptr<int> weak = alive;
      Running *pending = running(eval_id);
      pending->policy_future = c->hub_policy(ep.target.connection);
      pending->policy_future.then([this, weak, c, ep = std::move(ep)](bridge::Result<bridge::HubPolicy> r) mutable {
        if (weak.expired() || !running(ep.eval_id)) {
          return;
        }
        if (client() != c || (!r && r.error().code == bridge::ErrorCode::Cancelled)) {
          on_done(ep.eval_id, bridge::Error::make(bridge::ErrorCode::Cancelled, "Evaluation cancelled"));
          return;
        }
        if (r && r.value().desktop_auto && r.value().desktop_auto_bytes > 0) {
          ep.request["budget"] = Json::object({{"max_output_bytes", r.value().desktop_auto_bytes}});
        }
        /* An unavailable/unsupported policy keeps the ordinary unbudgeted review path. */
        submit_eval(ep);
      });
    }
    else {
      submit_eval(ep);
    }
    if (!is_prefetch) {
      changed();
    }
  }

  void on_graph_progress(const std::string &eval_id, const bridge::GraphProgress &p)
  {
    if (!main || main->eval_id != eval_id) {
      return;
    }
    const std::string type = io::get_string(p.event, "type");
    const std::string node = io::get_string(p.event, "node");
    if (type == "node.started") {
      progress.started++;
      progress.node = node;
    }
    else if (type == "node.finished") {
      progress.finished++;
    }
    else if (type == "node.cached") {
      progress.cached++;
    }
    else if (type == "node.failed") {
      progress.failed++;
      progress.message = node + ": " + io::get_string(p.event, "message");
    }
    else if (type == "warning" || type == "progress") {
      const std::string m = io::get_string(p.event, "message");
      if (!m.empty()) {
        progress.message = node.empty() ? m : node + ": " + m;
      }
    }
    changed();
  }

  void on_done(const std::string &eval_id, bridge::Result<bridge::EvaluateResult> r)
  {
    const bool is_main = main && main->eval_id == eval_id;
    const bool is_prefetch = prefetch && prefetch->eval_id == eval_id;
    if (!is_main && !is_prefetch) {
      return; /* superseded */
    }
    Running run = is_main ? std::move(*main) : std::move(*prefetch);
    if (is_main) {
      main.reset();
      progress.running = false;
    }
    else {
      prefetch.reset();
    }
    if (!r.ok()) {
      if (r.error().code == bridge::ErrorCode::Cancelled) {
        return;
      }
      if (is_main) {
        eval_error = error_text(r.error());
        store.log(store.catalog().format("viewer.log.eval_failed", {{"error", eval_error}}));
        step_request_at = -1.0;
      }
      changed();
      return;
    }
    const bridge::EvaluateResult &er = r.value();
    if (!er.result.is_object()) {
      if (is_main) {
        progress.review = er.action && er.action->in_review();
        eval_error = progress.review ? std::string(store.tr("viewer.status.review")) :
                                       std::string(store.tr("viewer.error.no_result"));
      }
      changed();
      return;
    }
    Frame f;
    try {
      f.result = er.graph_result();
      for (const std::string &name : payload_outputs()) {
        const io::ResultOutput *out = f.result.output(name);
        if (out && out->manifest()) {
          const io::BlobCache blobs(core::path_from_utf8(er.blob_dir));
          f.payload = std::make_shared<const io::Payload>(io::decode_manifest(*out->manifest(), blobs.provider(false)));
          break;
        }
      }
      if (!f.payload) {
        for (const io::ResultOutput &out : f.result.outputs) {
          if (out.manifest()) {
            const io::BlobCache blobs(core::path_from_utf8(er.blob_dir));
            f.payload = std::make_shared<const io::Payload>(io::decode_manifest(*out.manifest(), blobs.provider(false)));
            break;
          }
        }
      }
    }
    catch (const std::exception &e) {
      if (is_main) {
        eval_error = e.what();
        changed();
      }
      return;
    }
    if (!f.payload) {
      if (is_main) {
        eval_error = std::string(store.tr("viewer.error.no_payload"));
        changed();
      }
      return;
    }
    f.params = run.params;
    if (!step_param.empty()) {
      const auto it = f.result.parameters.find(step_param);
      f.step = it != f.result.parameters.end() ? it->second.value : run.params.value(step_param, Json());
      f.params[step_param] = f.step;
    }
    EvalRecord &rec = f.record;
    rec.eval_id = eval_id;
    rec.reason = run.reason;
    rec.evaluated = f.result.evaluated;
    const std::vector<std::string> dn = data_nodes();
    for (const std::string &n : rec.evaluated) {
      if (std::find(dn.begin(), dn.end(), n) != dn.end()) {
        rec.data_nodes.push_back(n);
      }
    }
    rec.cache_hits = f.result.cache_hits;
    rec.cache_misses = f.result.cache_misses;
    rec.seconds = now() - run.t0;
    const std::string key = cache_key(f.params);
    if (is_main) {
      store_frame(key, f);
      show_frame(f, rec);
      schedule_prefetch();
      return;
    }
    prefetched++;
    prefetched_payloads.push_back(f.payload);
    update_choices(f.result);
    store_frame(key, std::move(f));
    advance_export();
    schedule_prefetch();
    changed();
  }

  /** Neighbours of the shown step (ahead first while playing). */
  void schedule_prefetch()
  {
    if (!self.prefetch_neighbours || step_param.empty() || choices.size() < 2 || prefetch || main ||
        !source.evaluates() || pending_at < kInf)
    {
      advance_export();
      return;
    }
    /* Export frames first. */
    if (job && !job->ready) {
      for (const auto &[step, payload] : job->frames) {
        if (!payload) {
          const Json p = params_with_step(step);
          if (!cache.count(cache_key(p))) {
            start_eval("export", true, step);
            return;
          }
        }
      }
    }
    const int i = self.step_index();
    if (i < 0) {
      return;
    }
    const int n = int(choices.size());
    std::vector<int> cands;
    if (playing) {
      cands = {i + 1, i + 2};
    }
    else {
      cands = {i + 1, i - 1};
    }
    for (int c : cands) {
      if (playing && self.loop) {
        c = ((c % n) + n) % n;
      }
      if (c < 0 || c >= n || c == i) {
        continue;
      }
      if (!cache.count(cache_key(params_with_step(choices[size_t(c)])))) {
        start_eval("prefetch", true, choices[size_t(c)]);
        return;
      }
    }
  }

  /* ---- Display ---- */

  void apply_display()
  {
    payload_serial++;
    if (!base) {
      display.reset();
      return;
    }
    bool any = false;
    const Json &layers = base->layers();
    for (const Json &L : layers) {
      if (opacity.count(io::get_string(L, "id"))) {
        any = true;
      }
    }
    if (!any) {
      display = base;
      return;
    }
    auto copy = std::make_shared<io::Payload>(*base);
    Json &ls = copy->manifest["layers"];
    for (Json &L : ls) {
      const auto it = opacity.find(io::get_string(L, "id"));
      if (it == opacity.end()) {
        continue;
      }
      if (!L.contains("appearance") || !L["appearance"].is_object()) {
        L["appearance"] = Json::object();
      }
      L["appearance"]["opacity"] = it->second;
    }
    display = std::move(copy);
  }

  /* ---- Probe ---- */

  void query_probe(const PickInfo &pick)
  {
    probe.pick = pick;
    probe.serial++;
    probe.target = Json();
    probe.sample = Json();
    probe.error.clear();
    probe_future.cancel();
    bridge::Client *c = client();
    if (!source.evaluates()) {
      probe.status = ProbeState::Status::Unavailable;
      probe.error = std::string(store.tr("probe.unavailable.local"));
      changed();
      return;
    }
    if (pick.probe_node.empty()) {
      probe.status = ProbeState::Status::Unavailable;
      probe.error = std::string(store.tr("probe.unavailable.layer"));
      changed();
      return;
    }
    if (!c) {
      probe.status = ProbeState::Status::Unavailable;
      probe.error = std::string(store.tr("viewer.error.no_bridge"));
      changed();
      return;
    }
    bridge::ProbeParams pp;
    pp.preset = preset_id;
    pp.node = pick.probe_node;
    pp.dataset = pick.probe_dataset;
    Json context = Json::object();
    const std::string binding = binding_name();
    if (source.kind == SourceKind::Task) {
      context["bindings"] = Json::object({{binding, source.task_id}});
      pp.target.connection = source.connection;
      pp.target.node = source.node;
    }
    else {
      pp.local_bindings[binding] = source.path;
    }
    context["values"] = shown_params.is_object() ? shown_params : parameters();
    if (result) {
      context["result"] = result->raw;
    }
    pp.context = std::move(context);
    pp.position = pick.physical;
    probe.status = ProbeState::Status::Pending;
    std::weak_ptr<int> weak = alive;
    const uint64_t serial = probe.serial;
    probe_future = c->probe(pp);
    probe_future.then([this, weak, serial](bridge::Result<Json> r) {
      if (weak.expired() || serial != probe.serial) {
        return;
      }
      if (!r.ok()) {
        if (r.error().code == bridge::ErrorCode::Cancelled) {
          return;
        }
        probe.status = ProbeState::Status::Failed;
        probe.error = error_text(r.error());
      }
      else {
        probe.status = ProbeState::Status::Done;
        probe.target = r.value().value("target", Json());
        probe.sample = r.value().value("sample", Json());
      }
      changed();
    });
    changed();
  }

  /* ---- Result directories ---- */

  bool load_result_frame(const fs::path &result_file, const Json &step, Frame &f, std::string &err)
  {
    Json doc;
    try {
      doc = io::read_json_file(result_file);
      f.result = io::GraphResult::from_json(doc);
    }
    catch (const std::exception &e) {
      err = e.what();
      return false;
    }
    const fs::path dir = result_file.parent_path();
    const Json files = doc.value("files", Json::object());
    for (const io::ResultOutput &out : f.result.outputs) {
      if (out.type != "payload") {
        continue;
      }
      fs::path manifest = dir / core::path_from_utf8(out.name) / "manifest.json";
      if (files.is_object() && files.contains(out.name) && files[out.name].is_string()) {
        const auto joined = core::join_safe(dir, files[out.name].get<std::string>());
        if (joined) {
          manifest = *joined;
        }
      }
      try {
        f.payload = std::make_shared<const io::Payload>(io::read_directory(manifest));
      }
      catch (const std::exception &e) {
        err = e.what();
        return false;
      }
      break;
    }
    if (!f.payload) {
      err = std::string(store.tr("viewer.error.no_payload"));
      return false;
    }
    f.step = step;
    f.record.reason = "open";
    f.record.from_cache = true;
    return true;
  }

  bool show_series_step(const Json &step)
  {
    const std::string key = source.key() + "|series|" + dumps(step);
    if (auto it = cache.find(key); it != cache.end()) {
      show_cached(it->second, "step");
      return true;
    }
    if (!series_doc.is_object()) {
      return false;
    }
    for (const Json &frame : series_doc.value("frames", Json::array())) {
      const Json value = frame.contains(series_param) ? frame[series_param] : frame.value("step", Json());
      if (!json_equal_step(value, step)) {
        continue;
      }
      const std::string rel = io::get_string(frame, "result");
      const fs::path dir = core::path_from_utf8(source.path);
      Frame f;
      std::string err;
      const auto file = core::join_safe(dir, rel.empty() ? "result.json" : rel);
      if (!file || !load_result_frame(*file, value, f, err)) {
        eval_error = err.empty() ? "cannot read " + rel : err;
        changed();
        return false;
      }
      store_frame(key, f);
      show_frame(f, f.record);
      return true;
    }
    return false;
  }

  /* ---- Export ---- */

  void advance_export()
  {
    if (!job || job->ready) {
      return;
    }
    size_t pending = 0;
    for (auto &[step, payload] : job->frames) {
      if (payload) {
        continue;
      }
      if (source.kind == SourceKind::ResultDir) {
        const std::string key = source.key() + "|series|" + dumps(step);
        if (!cache.count(key)) {
          Json saved_step = shown_step;
          show_series_step(step);
          if (!saved_step.is_null() && !json_equal_step(saved_step, step)) {
            /* keep the view where it was */
            show_series_step(saved_step);
          }
        }
        if (auto it = cache.find(key); it != cache.end()) {
          payload = it->second.payload;
        }
      }
      else if (auto it = cache.find(cache_key(params_with_step(step))); it != cache.end()) {
        payload = it->second.payload;
      }
      if (!payload) {
        pending++;
      }
    }
    job->pending = pending;
    if (pending == 0) {
      job->ready = true;
      export_status = std::string(store.tr("export.status.rendering"));
      changed();
    }
  }
};

/** \} */

/* -------------------------------------------------------------------- */
/** \name ViewerState
 * \{ */

ViewerState::ViewerState(AppStore &store) : store_(store), impl_(std::make_unique<Impl>(*this, store))
{
  impl_->schema.type = ui::SchemaType::Object;
}

ViewerState::~ViewerState()
{
  if (impl_) {
    impl_->alive.reset();
    impl_->cancel_prefetch();
    if (impl_->main) {
      impl_->main->policy_future.cancel();
      impl_->main->future.cancel();
    }
    impl_->probe_future.cancel();
  }
}

double ViewerState::now() const
{
  if (clock) {
    return clock();
  }
  return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

void ViewerState::refresh_metadata(const bool force)
{
  impl_->request_metadata(force);
}

bool ViewerState::presets_loaded() const
{
  return impl_->presets_loaded;
}

const std::vector<PresetInfo> &ViewerState::presets() const
{
  return impl_->presets;
}

const PresetInfo *ViewerState::preset(const std::string &id) const
{
  return impl_->preset(id);
}

const Json &ViewerState::catalog() const
{
  return impl_->catalog;
}

std::shared_ptr<const std::vector<ui::ColormapItem>> ViewerState::colormaps() const
{
  return impl_->colormaps;
}

const std::string &ViewerState::metadata_error() const
{
  return impl_->metadata_error;
}

void ViewerState::set_metadata(const Json &presets_result, const Json &catalog)
{
  Impl &m = *impl_;
  m.presets_requested = m.catalog_requested = true;
  m.parse_presets(presets_result);
  m.presets_loaded = true;
  m.set_catalog(catalog);
  m.metadata_arrived();
}

void ViewerState::set_colormaps(std::shared_ptr<const std::vector<ui::ColormapItem>> colormaps)
{
  impl_->colormaps_requested = true;
  impl_->colormaps = std::move(colormaps);
  impl_->changed();
}

bool ViewerState::open(const OpenResultRequest &request)
{
  Impl &m = *impl_;
  if (!request.task_id.empty()) {
    close();
    m.source.kind = SourceKind::Task;
    m.source.connection = request.connection;
    m.source.node = request.node;
    m.source.workspace_id = request.workspace_id;
    m.source.task_id = request.task_id;
    m.label = m.source.label();
    m.camera_serial++;
    m.preset_id = request.preset;
    if (m.preset_id.empty() && m.have_metadata()) {
      m.preset_id = "muferro-domains";
      if (!m.preset(m.preset_id) && !m.presets.empty()) {
        m.preset_id = m.presets.front().id;
      }
    }
    if (!m.have_metadata()) {
      m.waiting_for_metadata = true;
      m.request_metadata(false);
      m.changed();
      return true;
    }
    m.build_form(false);
    m.start_eval("open");
    m.changed();
    return true;
  }
  for (const std::string &p : request.local_paths) {
    if (open_path(p, request.preset)) {
      return true;
    }
  }
  if (request.local_paths.empty()) {
    m.open_error = "nothing to open";
    m.changed();
  }
  return false;
}

bool ViewerState::open_path(const std::string &path, const std::string &preset, const Json &parameters)
{
  Impl &m = *impl_;
  std::string err;
  ViewerSource s = classify_path(path, &err);
  if (s.kind == SourceKind::None) {
    m.open_error = err;
    store_.log(store_.catalog().format("viewer.log.open_failed", {{"path", path}, {"error", err}}));
    m.changed();
    return false;
  }
  close();
  m.source = s;
  m.label = s.label();
  m.camera_serial++;
  store_.log(store_.catalog().format("viewer.log.opened", {{"path", s.path}, {"kind", source_kind_name(s.kind)}}));
  switch (s.kind) {
    case SourceKind::Payload: {
      try {
        const fs::path p = core::path_from_utf8(s.path);
        auto payload = fs::is_directory(p) ? std::make_shared<const io::Payload>(io::read_directory(p)) :
                                             std::make_shared<const io::Payload>(io::read_stkp(p));
        m.base = std::move(payload);
        m.apply_display();
      }
      catch (const std::exception &e) {
        m.open_error = e.what();
        m.source = ViewerSource{};
        m.label.clear();
        store_.log(store_.catalog().format("viewer.log.open_failed", {{"path", path}, {"error", m.open_error}}));
      }
      m.changed();
      return m.base != nullptr;
    }
    case SourceKind::ResultDir: {
      const fs::path dir = core::path_from_utf8(s.path);
      if (s.series) {
        try {
          m.series_doc = io::read_json_file(dir / "series.json");
        }
        catch (const std::exception &e) {
          m.open_error = e.what();
          m.changed();
          return false;
        }
        m.series_param = io::get_string(m.series_doc, "parameter", "step");
        m.step_param = m.series_param;
        m.choices.clear();
        for (const Json &frame : m.series_doc.value("frames", Json::array())) {
          m.choices.push_back(frame.contains(m.series_param) ? frame[m.series_param] : frame.value("step", Json()));
        }
        if (m.choices.empty() || !m.show_series_step(m.choices.back())) {
          m.open_error = m.eval_error.empty() ? "series.json has no frames" : m.eval_error;
          m.changed();
          return false;
        }
        return true;
      }
      Impl::Frame f;
      std::string ferr;
      if (!m.load_result_frame(dir / "result.json", Json(), f, ferr)) {
        m.open_error = ferr;
        m.changed();
        return false;
      }
      m.store_frame(s.key() + "|result", f);
      m.show_frame(f, f.record);
      return true;
    }
    case SourceKind::RunDir: {
      m.initial_params = parameters;
      m.preset_id = !preset.empty() ? preset : guess_preset(s.path);
      if (!m.have_metadata()) {
        m.waiting_for_metadata = true;
        m.request_metadata(false);
        m.changed();
        return true;
      }
      if (m.preset_id.empty() || !m.preset(m.preset_id)) {
        m.preset_id = m.presets.empty() ? std::string() : m.presets.front().id;
      }
      m.build_form(false);
      m.start_eval("open");
      m.changed();
      return true;
    }
    default: break;
  }
  return false;
}

void ViewerState::open_payload(std::shared_ptr<const io::Payload> payload, std::string label)
{
  close();
  Impl &m = *impl_;
  m.source.kind = SourceKind::Payload;
  m.label = std::move(label);
  m.source.path = m.label;
  m.camera_serial++;
  m.base = std::move(payload);
  m.apply_display();
  m.changed();
}

void ViewerState::close()
{
  Impl &m = *impl_;
  m.cancel_main();
  m.cancel_prefetch();
  m.probe_future.cancel();
  m.source = ViewerSource{};
  m.label.clear();
  m.open_error.clear();
  m.eval_error.clear();
  m.series_doc = Json();
  m.series_param.clear();
  m.cache.clear();
  m.choices.clear();
  m.shown_step = Json();
  m.shown_params = Json();
  m.result.reset();
  m.last.reset();
  m.base.reset();
  m.apply_display();
  m.prefetched_payloads.clear();
  m.visibility.clear();
  m.opacity.clear();
  m.probe = ProbeState{};
  m.playing = false;
  m.pending_reason.clear();
  m.pending_at = kInf;
  m.waiting_for_metadata = false;
  m.progress = EvalProgress{};
  m.job.reset();
  m.step_param.clear();
  m.changed();
}

const ViewerSource &ViewerState::source() const
{
  return impl_->source;
}

const std::string &ViewerState::source_label() const
{
  return impl_->label;
}

const std::string &ViewerState::open_error() const
{
  return impl_->open_error;
}

const std::string &ViewerState::preset_id() const
{
  return impl_->preset_id;
}

void ViewerState::select_preset(const std::string &id)
{
  Impl &m = *impl_;
  if (id == m.preset_id && !m.schema.properties.empty()) {
    return;
  }
  m.cancel_main();
  m.cancel_prefetch();
  m.preset_id = id;
  m.cache.clear();
  m.choices.clear();
  m.visibility.clear();
  m.opacity.clear();
  m.camera_serial++;
  m.build_form(false);
  if (m.source.evaluates()) {
    m.start_eval("preset");
  }
  m.changed();
}

const ui::SchemaNode &ViewerState::schema() const
{
  return impl_->schema;
}

ui::FormModel &ViewerState::form()
{
  return impl_->form;
}

Json ViewerState::parameters() const
{
  return impl_->parameters();
}

std::string ViewerState::param_stage(const std::string &name) const
{
  return impl_->param_stage(name);
}

void ViewerState::set_parameter(const std::string &name, ui::FormValue value)
{
  impl_->form.set(name, std::move(value));
}

std::vector<std::string> ViewerState::payload_outputs() const
{
  return impl_->payload_outputs();
}

void ViewerState::evaluate_now(const std::string &reason)
{
  Impl &m = *impl_;
  m.cancel_prefetch();
  if (reason == "manual") {
    /* An explicit evaluation goes to the bridge (a live run may have new frames). */
    m.cache.erase(m.cache_key(m.parameters()));
  }
  m.start_eval(reason.empty() ? "manual" : reason);
}

void ViewerState::cancel_evaluation()
{
  Impl &m = *impl_;
  m.pending_reason.clear();
  m.pending_at = kInf;
  m.cancel_main();
  m.cancel_prefetch();
  m.playing = false;
  m.changed();
}

bool ViewerState::evaluating() const
{
  return impl_->main.has_value();
}

const EvalProgress &ViewerState::progress() const
{
  return impl_->progress;
}

const std::optional<EvalRecord> &ViewerState::last_eval() const
{
  return impl_->last;
}

const std::optional<io::GraphResult> &ViewerState::result() const
{
  return impl_->result;
}

const std::string &ViewerState::eval_error() const
{
  return impl_->eval_error;
}

std::vector<std::string> ViewerState::data_nodes() const
{
  return impl_->data_nodes();
}

int ViewerState::evaluations_started() const
{
  return impl_->started;
}

int ViewerState::evaluations_cancelled() const
{
  return impl_->cancelled;
}

const std::string &ViewerState::pending_edit() const
{
  return impl_->pending_reason;
}

const std::string &ViewerState::step_param() const
{
  return impl_->step_param;
}

const std::vector<Json> &ViewerState::step_choices() const
{
  return impl_->choices;
}

int ViewerState::step_index() const
{
  const Impl &m = *impl_;
  for (size_t i = 0; i < m.choices.size(); i++) {
    if (json_equal_step(m.choices[i], m.shown_step)) {
      return int(i);
    }
  }
  return -1;
}

Json ViewerState::shown_step() const
{
  return impl_->shown_step;
}

void ViewerState::set_step_index(const int index)
{
  Impl &m = *impl_;
  if (index < 0 || size_t(index) >= m.choices.size()) {
    return;
  }
  const Json step = m.choices[size_t(index)];
  m.step_request_at = now();
  if (m.source.kind == SourceKind::ResultDir) {
    m.show_series_step(step);
    return;
  }
  if (!m.source.evaluates() || m.step_param.empty()) {
    return;
  }
  m.form_quiet = true;
  m.form.set(m.step_param, ui::form_value_from_json(step));
  m.form_quiet = false;
  const std::string key = m.cache_key(m.params_with_step(step));
  if (m.cache.count(key) || (m.prefetch && m.prefetch->key == key)) {
    m.start_eval("step");
    return;
  }
  /* Not cached: debounce briefly (dragging the scrubber supersedes quickly). */
  m.pending_reason = "step";
  m.pending_at = now() + 0.1;
  m.changed();
}

void ViewerState::step_by(const int delta)
{
  const int n = int(impl_->choices.size());
  if (n == 0) {
    return;
  }
  int i = step_index();
  if (i < 0) {
    i = n - 1;
  }
  set_step_index(std::clamp(i + delta, 0, n - 1));
}

void ViewerState::step_latest()
{
  Impl &m = *impl_;
  if (m.source.kind == SourceKind::ResultDir) {
    set_step_index(int(m.choices.size()) - 1);
    return;
  }
  if (m.step_param.empty()) {
    return;
  }
  m.playing = false;
  m.form_quiet = true;
  m.form.set(m.step_param, ui::FormValue::string("latest"));
  m.form_quiet = false;
  m.step_request_at = now();
  m.start_eval("step");
}

bool ViewerState::playing() const
{
  return impl_->playing;
}

void ViewerState::set_playing(const bool playing)
{
  Impl &m = *impl_;
  m.playing = playing && m.choices.size() > 1;
  m.next_frame_at = m.playing ? now() + 1.0 / std::max(0.1, fps) : kInf;
  m.changed();
}

double ViewerState::last_step_switch_ms() const
{
  return impl_->last_switch_ms;
}

size_t ViewerState::cached_results() const
{
  return impl_->cache.size();
}

int ViewerState::prefetched_count() const
{
  return impl_->prefetched;
}

std::shared_ptr<const io::Payload> ViewerState::payload() const
{
  return impl_->display;
}

std::shared_ptr<const io::Payload> ViewerState::base_payload() const
{
  return impl_->base;
}

uint64_t ViewerState::payload_serial() const
{
  return impl_->payload_serial;
}

uint64_t ViewerState::camera_serial() const
{
  return impl_->camera_serial;
}

void ViewerState::request_camera_reset()
{
  impl_->camera_serial++;
  impl_->changed();
}

std::vector<std::shared_ptr<const io::Payload>> ViewerState::take_prefetched()
{
  std::vector<std::shared_ptr<const io::Payload>> out;
  out.swap(impl_->prefetched_payloads);
  return out;
}

std::vector<std::string> ViewerState::warnings() const
{
  const Impl &m = *impl_;
  std::vector<std::string> out;
  if (m.base) {
    for (const io::PayloadWarning &w : m.base->warnings) {
      out.push_back((w.layer.empty() ? "" : w.layer + ": ") + w.message);
    }
  }
  if (m.result) {
    for (const io::GraphIssueRecord &w : m.result->warnings) {
      out.push_back((w.node.empty() ? "" : w.node + ": ") + w.message);
    }
    for (const io::GraphIssueRecord &w : m.result->errors) {
      out.push_back((w.node.empty() ? "" : w.node + ": ") + w.message);
    }
  }
  return out;
}

std::string ViewerState::stats_text() const
{
  const Impl &m = *impl_;
  if (!m.base) {
    return {};
  }
  std::vector<std::string> parts;
  auto count = [&](const char *key, const char *label_key) {
    const Json &stats = m.base->manifest.contains("stats") ? m.base->manifest["stats"] : Json();
    const double v = io::get_number(stats, key, 0.0);
    if (v > 0) {
      parts.push_back(store_.catalog().format(label_key, {{"count", std::to_string(int64_t(v))}}));
    }
  };
  count("triangles", "viewer.stats.triangles");
  count("instances", "viewer.stats.instances");
  count("voxels", "viewer.stats.voxels");
  parts.push_back(store_.catalog().format("viewer.stats.kib", {{"count", std::to_string(m.base->total_bytes() / 1024)}}));
  std::string s;
  for (size_t i = 0; i < parts.size(); i++) {
    s += (i ? " \xc2\xb7 " : "") + parts[i];
  }
  return s;
}

std::vector<ViewerState::LayerRow> ViewerState::layers() const
{
  const Impl &m = *impl_;
  std::vector<LayerRow> out;
  if (!m.base) {
    return out;
  }
  const Json &visibility = m.base->manifest.contains("view") ? m.base->manifest["view"].value("visibility", Json())
                                                             : Json();
  for (const Json &L : m.base->layers()) {
    LayerRow row;
    row.id = io::get_string(L, "id");
    if (m.base->skipped(row.id)) {
      continue;
    }
    row.name = io::get_string(L, "name", row.id);
    row.type = io::get_string(L, "type");
    row.kind = io::get_string(L, "kind");
    bool visible = io::get_bool(L, "visible", true);
    if (visibility.is_object() && visibility.contains(row.id) && visibility[row.id].is_boolean()) {
      visible = visible && visibility[row.id].get<bool>();
    }
    if (const auto it = m.visibility.find(row.id); it != m.visibility.end()) {
      visible = it->second;
    }
    row.visible = visible;
    row.has_opacity = row.type != "overlay" && row.type != "volume";
    const Json &app = L.contains("appearance") ? L["appearance"] : Json();
    row.opacity = std::clamp(io::get_number(app, "opacity", 1.0), 0.0, 1.0);
    if (const auto it = m.opacity.find(row.id); it != m.opacity.end()) {
      row.opacity = it->second;
    }
    row.pickable = L.contains("pick") || row.type == "triangles" || row.type == "slice_image";
    out.push_back(std::move(row));
  }
  return out;
}

void ViewerState::set_layer_visible(const std::string &id, const bool visible)
{
  impl_->visibility[id] = visible;
  impl_->changed();
}

void ViewerState::set_layer_opacity(const std::string &id, const double opacity)
{
  Impl &m = *impl_;
  const double o = std::isfinite(opacity) ? std::clamp(opacity, 0.0, 1.0) : 1.0;
  if (const auto it = m.opacity.find(id); it != m.opacity.end() && it->second == o) {
    return;
  }
  m.opacity[id] = o;
  m.apply_display();
  m.changed();
}

const std::map<std::string, bool> &ViewerState::visibility() const
{
  return impl_->visibility;
}

bool ViewerState::overlays() const
{
  return impl_->overlays;
}

void ViewerState::set_overlays(const bool on)
{
  impl_->overlays = on;
  impl_->changed();
}

void ViewerState::set_pick(PickInfo pick)
{
  impl_->query_probe(pick);
}

void ViewerState::probe_position(const std::array<double, 3> &position)
{
  PickInfo p = impl_->probe.pick;
  p.physical = position;
  impl_->query_probe(p);
}

void ViewerState::clear_pick()
{
  impl_->probe_future.cancel();
  impl_->probe = ProbeState{};
  impl_->changed();
}

const ProbeState &ViewerState::probe() const
{
  return impl_->probe;
}

void ViewerState::request_export()
{
  Impl &m = *impl_;
  ExportJob job;
  job.settings = export_settings;
  job.settings.magnification = std::clamp(job.settings.magnification, 1, 8);
  if (job.settings.path.empty()) {
    m.export_status = std::string(store_.tr("export.error.no_path"));
    m.changed();
    return;
  }
  if (!m.display) {
    m.export_status = std::string(store_.tr("export.error.no_payload"));
    m.changed();
    return;
  }
  if (job.settings.sequence && !m.choices.empty()) {
    job.parameter = m.step_param.empty() ? "step" : m.step_param;
    for (const Json &step : m.choices) {
      std::shared_ptr<const io::Payload> p;
      if (json_equal_step(step, m.shown_step)) {
        p = m.display;
      }
      job.frames.emplace_back(step, std::move(p));
    }
  }
  else {
    job.settings.sequence = false;
    job.frames.emplace_back(m.shown_step, m.display);
  }
  m.job = std::move(job);
  m.export_status = std::string(store_.tr("export.status.preparing"));
  m.advance_export();
  m.schedule_prefetch();
  m.changed();
}

ExportJob *ViewerState::export_job()
{
  return impl_->job ? &*impl_->job : nullptr;
}

void ViewerState::finish_export(const bool ok, const std::string &message)
{
  Impl &m = *impl_;
  m.job.reset();
  m.export_status = message;
  store_.log(message);
  if (store_.toast) {
    store_.toast(message, ok ? ui::ToastKind::Success : ui::ToastKind::Error);
  }
  m.changed();
}

const std::string &ViewerState::export_status() const
{
  return impl_->export_status;
}

bool ViewerState::write_series(const ExportJob &job, std::string *r_error)
{
  io::Series series;
  series.parameter = job.parameter.empty() ? "step" : job.parameter;
  for (const auto &[step, payload] : job.frames) {
    io::SeriesFrame f;
    f.step = step;
    f.outputs["image"] = core::path_to_utf8(core::path_from_utf8(sequence_frame_path(job.settings.path, step)).filename());
    series.frames.push_back(std::move(f));
  }
  Json doc = series.to_json();
  /* The CLI's frames also name the parameter (spec §6: {"step", "outputs"}). */
  for (Json &frame : doc["frames"]) {
    if (series.parameter != "step") {
      frame[series.parameter] = frame["step"];
    }
  }
  const std::string path = sequence_manifest_path(job.settings.path);
  std::FILE *f = std::fopen(path.c_str(), "wb");
  if (!f) {
    if (r_error) {
      *r_error = "cannot write " + path;
    }
    return false;
  }
  const std::string text = doc.dump(1) + "\n";
  const bool ok = std::fwrite(text.data(), 1, text.size(), f) == text.size();
  std::fclose(f);
  if (!ok && r_error) {
    *r_error = "cannot write " + path;
  }
  return ok;
}

double ViewerState::pump()
{
  Impl &m = *impl_;
  const double t = now();
  if (m.bridge_ready() && (!m.presets_requested || !m.catalog_requested || !m.colormaps_requested)) {
    m.request_metadata(false);
  }
  if (m.pending_at <= t && !m.pending_reason.empty()) {
    const std::string reason = m.pending_reason;
    m.start_eval(reason);
  }
  if (m.playing) {
    if (m.choices.size() < 2) {
      m.playing = false;
    }
    else if (t >= m.next_frame_at) {
      if (m.main || m.pending_at < kInf) {
        /* Still waiting for the previous frame: check again soon. */
        m.next_frame_at = t + 0.02;
      }
      else {
        const int n = int(m.choices.size());
        int i = step_index();
        int next = i + 1;
        if (next >= n) {
          next = loop ? 0 : n - 1;
          if (!loop) {
            m.playing = false;
          }
        }
        if (m.playing || next != i) {
          set_step_index(next);
        }
        m.next_frame_at = t + 1.0 / std::max(0.1, fps);
        m.changed();
      }
    }
  }
  m.schedule_prefetch();
  double wake = m.pending_at;
  if (m.playing) {
    wake = std::min(wake, m.next_frame_at);
  }
  return wake;
}

uint64_t ViewerState::version() const
{
  return impl_->version;
}

/** \} */

}  // namespace stk::app
