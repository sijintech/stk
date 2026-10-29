/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real MaterialsEditor GPU drawing with a strict local bridge and controlled completed tasks.
 * The trainer fixture proves rendering/provenance wiring, not Torch accuracy or material physics.
 * Usage: stk-materials-render --gpu-backend opengl --lang en --mode wide --export /path/materials
 * Writes <prefix>-loss.png, <prefix>-evaluation.png and a pixel/provenance evidence JSON.
 */
#include "stk/app/editor_area.hh"
#include "stk/app/materials_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "../bridge/support.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <stdexcept>

using namespace stk;
using io::Json;
namespace fs = std::filesystem;

namespace {
constexpr const char *kBridge = R"PY(
from pathlib import Path
import hashlib
import json
import sys
from suan.materials import curves, datasets, inputs, training
from suan.desktop_bridge.__main__ import main
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                   ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
def controlled_train(directory, output, *, frozen=False, progress=None, cancel=None, **kwargs):
    assert frozen, 'Renderer fixture must use frozen inputs'
    manifest, description, samples = inputs.load(directory)
    identity = Path(directory).parent.name
    candidate_offset, candidate_score = {'render-base': (.12, .06),
        'render-baseline': (.07, .035), 'render-candidate': (-.04, .02)}[identity]
    for epoch in range(1, 9):
        if cancel.is_set():
            raise training.Cancelled('Renderer fixture cancelled')
        progress(epoch, .8 / epoch + .012, 1.0 / epoch + .035)
    split = manifest['split']
    selected = {sample['id']: sample for sample in samples}
    shifted = lambda sample, offset: [value + offset if value is not None else .8 + offset
                                     for value in sample['curve']]
    role_offsets = {'base': .12, 'baseline': .12 if identity == 'render-baseline' else .07}
    role_scores = {'base': .06, 'baseline': .06 if identity == 'render-baseline' else .035}
    metric = lambda score: {'samples': len(split['test']), 'rmse': score / 10, 'normalized_rmse': score}
    preview = {'grid': curves.grid(manifest['kind']), 'samples': [
        {'id': sid, 'inputs': selected[sid]['inputs'], 'observed': selected[sid]['curve'],
         'candidate': shifted(selected[sid], candidate_offset),
         **{role: shifted(selected[sid], role_offsets[role]) if manifest[role + '_model'] else None
            for role in ('base', 'baseline')}} for sid in split['test'][:3]]}
    weights = ('Controlled renderer weights: ' + identity + '; not a Torch model').encode('utf-8')
    meta = {'format': training.MODEL_FORMAT, 'kind': manifest['kind'],
        'inputs': description['inputs'], 'grid': curves.grid(manifest['kind']),
        'created_at': '2026-10-29T00:00:00+00:00', 'dataset': {
            'name': description['name'], 'sha256': datasets.digest(description, samples),
            'samples': len(samples), 'synthetic': description['synthetic'],
            'license': description['license'], 'sensitivity': description['sensitivity']},
        'metrics': {'test': metric(candidate_score),
            'train': {**metric(candidate_score), 'samples': len(split['train'])},
            'epochs': 8, 'best_epoch': 8, 'seconds': 0},
        'comparison': {'format': 'stk.materials-training-comparison/1',
            'test_sha256': digest(split['test']), 'test_samples': len(split['test']),
            'candidate': metric(candidate_score),
            **{role: metric(role_scores[role]) if manifest[role + '_model'] else None
               for role in ('base', 'baseline')}},
        'evaluation_preview': preview, 'weights_sha256': hashlib.sha256(weights).hexdigest(),
        'training_input': {'capsule_sha256': manifest['sha256'], 'split_sha256': digest(split),
            'split_counts': {key: len(ids) for key, ids in split.items()},
            'base_model': manifest['base_model'], 'baseline_model': manifest['baseline_model']}}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'model.pt').write_bytes(weights)
    (output / 'model.json').write_text(json.dumps(meta, allow_nan=False), encoding='utf-8')
    return meta
training.torch_module = lambda: object()
training.train = controlled_train
main()
)PY";

void require(bool condition, const std::string &message)
{
  if (!condition) { throw std::runtime_error(message); }
}

// Inspect actual GPU pixels inside the plot, excluding its legend, labels and controls.
// This is deliberately a geometric/color check, not a screenshot template or CPU-point verdict.
Json check_pixels(const gfx::Image &image, const ui::Rect main, const ui::Rect plot, int roles, float scale)
{
  constexpr std::array<uint32_t, 4> colors{0x71b7f2, 0xffbd69, 0x99d180, 0xd89fe5};
  Json result = Json::array();
  const auto matches = [&](int x, int y, uint32_t color) {
    const auto *pixel = image.px(x, y);
    return pixel[3] >= 250 && std::abs(int(pixel[0]) - int((color >> 16) & 255)) <= 8 &&
        std::abs(int(pixel[1]) - int((color >> 8) & 255)) <= 8 && std::abs(int(pixel[2]) - int(color & 255)) <= 8;
  };
  const int left = std::max(0, int(std::ceil(plot.x + 3 * scale)));
  const int right = std::min(image.width, int(std::floor(plot.x1() - 3 * scale)));
  const int top = std::max(0, int(std::ceil(plot.y + 3 * scale)));
  const int bottom = std::min(image.height, int(std::floor(plot.y1() - 3 * scale)));
  require(right - left > 80 * scale && bottom - top > 80 * scale, "Plot is too small for actual pixel evidence");
  for (int role = 0; role < roles; ++role) {
    int count = 0, min_x = right, max_x = left, outside = 0;
    for (int y = top; y < bottom; ++y) {
      for (int x = std::max(0, int(main.x)); x < std::min(image.width, int(main.x1())); ++x) {
        if (!matches(x, y, colors[size_t(role)])) { continue; }
        if (x >= left && x < right) { ++count; min_x = std::min(min_x, x); max_x = std::max(max_x, x); }
        else if (x < plot.x - 4 * scale || x >= plot.x1() + 4 * scale) { ++outside; }
      }
    }
    require(count >= std::max(30, int(plot.w * .1f)), "Missing actual curve palette pixels for role " + std::to_string(role));
    require(max_x - min_x >= plot.w * .4f, "Curve palette only occupies a small marker instead of the plot");
    require(outside == 0, "Curve palette escaped the horizontal plot clip");
    result.push_back({{"role_index", role}, {"rgb", colors[size_t(role)]}, {"interior_pixels", count},
                      {"horizontal_span", max_x - min_x}, {"outside_clip_pixels", outside}});
  }
  return result;
}
}  // namespace

int main(int argc, char **argv)
{
  std::string backend_name, language = "en", output, mode = "wide";
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string arg = argv[i];
    if (arg == "--gpu-backend") { backend_name = argv[i + 1]; }
    else if (arg == "--lang") { language = argv[i + 1]; }
    else if (arg == "--export") { output = argv[i + 1]; }
    else if (arg == "--mode") { mode = argv[i + 1]; }
    else { return 2; }
  }
  if (argc % 2 != 1 || output.empty() || (language != "en" && language != "zh") || (mode != "wide" && mode != "narrow")) { return 2; }
  const bool narrow = mode == "narrow";
  const int width = narrow ? 1000 : 1440, height = 1100;
  constexpr float scale = 1;
  bridge::test::TempDir directory{"materials-render"};
  bridge::test::ManualLoop loop;
  { std::ofstream stream(directory.path() / "bridge.py", std::ios::binary); stream << kBridge; if (!stream.good()) { return 1; } }
  std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  if (const auto selected = core::getenv_utf8("STK_BRIDGE_TEST_PYTHON"); selected && !selected->empty()) { python = *selected; }
  if (python.empty()) { fprintf(stderr, "FAIL: set STK_BRIDGE_TEST_PYTHON\n"); return 1; }
  bridge::ClientOptions options;
  options.python.configured = python; options.executor = loop.executor(); options.strict = options.validate = true;
  options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
  options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
  options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
  options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
  options.command = {python, "-u", directory.str() + "/bridge.py", "--stdio", "--state-dir", options.state_dir,
                     "--cache-dir", options.cache_dir, "--strict"};
  auto client = bridge::Client::create(options);
  std::string error;
  if (!client->start(&error) || !client->wait_ready(60)) { fprintf(stderr, "FAIL: bridge startup: %s\n", error.c_str()); return 1; }
  loop.run_ready();
  gfx::Backend backend;
  if (!gfx::resolve_backend(backend_name, backend, error)) { return 2; }
  gfx::Runtime runtime;
  auto *system = gfx::create_background_system(error);
  if (!system) { fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1; }
  int rc = 0;
  {
    gfx::GpuOptions gpu_options; gpu_options.backend = backend;
    auto gpu = gfx::Gpu::create(*system, gpu_options, error);
    if (!gpu) { fprintf(stderr, "FAIL: %s\n", error.c_str()); gfx::dispose_system(); return 1; }
    gfx::set_ui_scale(scale);
    app::ShellOptions shell_options;
    shell_options.language = language == "zh" ? "zh_CN" : "en"; shell_options.interactive = false;
    app::AppShell shell(shell_options);
    wm::Screen screen; shell.install(screen, nullptr); shell.build_default_layout(screen);
    shell.store().set_bridge(client.get());
    shell.store().viewer().set_auto_evaluate(false); shell.store().viewer().prefetch_neighbours = false;
    Json evidence = {{"format", "stk.materials-gpu-render/1"}, {"status", "failed"},
        {"claim", "Actual MaterialsEditor draw_gpu pixels with controlled training outputs; not Torch accuracy or physical validation"},
        {"language", language}, {"mode", mode}, {"backend", gpu->backend_name()}, {"images", Json::array()}};
    try {
      auto call = [&](const std::string &method, Json params) {
        auto reply = std::make_shared<std::optional<bridge::Result<Json>>>();
        auto future = client->call(method, std::move(params));
        future.then([reply](auto result) { *reply = std::move(result); });
        const bool done = loop.pump_until([&] { return reply->has_value(); }, 30);
        if (!done) { future.cancel(); }
        require(done, method + " timed out");
        require(reply->value().ok(), method + ": " + (reply->value() ? "" : reply->value().error().describe()));
        return reply->value().value();
      };
      const auto dataset = core::path_to_utf8(directory.path() / "data");
      call("materials.datasets.synthetic", {{"directory", dataset}, {"kind", "capacity_fade"}, {"samples", 24}, {"seed", 7},
          {"name", "Public synthetic GPU rendering fixture"}});
      Json job;
      for (const auto *id : {"render-base", "render-baseline", "render-candidate"}) {
        Json params = {{"directory", dataset}, {"job_id", id}, {"options", {{"epochs", 8}, {"patience", 8}, {"hidden", {4}}}}};
        if (std::string_view(id) == "render-candidate") { params["base_version"] = "v1"; }
        require(call("materials.prepare", params).at("job").at("state") == "prepared", "Real input preparation");
        call("materials.start", {{"job_id", id}});
        require(loop.pump_until([&] {
          job = call("materials.jobs.get", {{"job_id", id}}).at("job"); return job.at("state") != "running";
        }, 30), "Controlled completed task");
        require(job.at("state") == "done", job.dump());
      }
      require(job.at("base_version") == "v1" && job.at("baseline_version") == "v2", "Distinct frozen base and active baseline");
      const auto curves_reply = call("materials.jobs.curves", {{"job_id", "render-candidate"}});
      require(curves_reply.at("curves").size() == 8, "Actual eight persisted epoch rows");
      const auto &sample = job.at("evaluation_preview").at("samples").at(0);
      for (const auto *role : {"observed", "candidate", "base", "baseline"}) {
        require(sample.at(role).is_array() && sample.at(role).size() == 64, std::string("Missing role ") + role);
      }
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a4"));
      require(area && area->set_tabs({app::kEditorMaterials}, 0), "Materials editor");
      area->set_sidebar_open(true); area->set_toolbar_open(false);
      require(area->editor().load_state({{"section", 1}, {"plot", 0}}), "Materials task view");
      area->find_region(app::EditorArea::kSidebar)->set_size_1x(narrow ? 380 : 440); screen.set_maximized(area);
      wm::DrawContext context;
      context.ui_scale = scale; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
      gfx::Image image;
      auto frame = [&] { require(gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error), error); };
      auto widget = [&](const char *key) { return screen.ui()->find(key); };
      auto wait = [&](const std::function<bool()> &predicate, const char *description) {
        require(loop.pump_until([&] { frame(); return predicate(); }, 30), description);
      };
      frame();
      wait([&] { return widget("materials_jobs") && widget("materials_jobs")->enabled; }, "Read task list");
      const auto *jobs = widget("materials_jobs"); int selected = -1;
      for (size_t i = 0; i < jobs->items.size(); ++i) { if (jobs->items[i].starts_with("render-candidate")) { selected = int(i); break; } }
      require(selected >= 0, "Completed task appears in real dropdown");
      jobs->index.assign(selected); frame(); // The production Widget binding calls state.select_job.
      wait([&] { return widget("materials_plot_kind") && widget("materials_start") && !widget("materials_start")->enabled; }, "Selected completed task");
      require(call("materials.jobs.get", {{"job_id", "render-candidate"}}).at("job") == job, "Rendering must not mutate task");
      // Drain the real curves response into this editor before inspecting rendered loss pixels.
      wait([&] { return widget("materials_plot_kind") != nullptr; }, "Plot controls");
      wait([&] {
        const auto main = area->find_region(app::EditorArea::kMain)->ui_rect();
        const float top = 4 * screen.ui()->style().unit;
        const ui::Rect plot{main.x + 55 * scale, main.y + top + 20 * scale,
            std::max(0.f, main.w - 75 * scale), std::max(0.f, main.h - top - 101 * scale)};
        try { check_pixels(image, main, plot, 2, scale); return true; }
        catch (const std::runtime_error &) { return false; }
      }, "Persisted epoch curves actually reach GPU pixels");
      for (int plot_kind = 0; plot_kind < 2; ++plot_kind) {
        widget("materials_plot_kind")->index.assign(plot_kind); frame();
        if (plot_kind == 1) {
          wait([&] { return widget("materials_sample") && !widget("materials_sample")->items.empty(); }, "Frozen held-out sample");
          require(widget("materials_sample")->items.at(0) == io::get_string(sample, "id"), "Same frozen held-out identity");
        }
        frame(); const auto main = area->find_region(app::EditorArea::kMain)->ui_rect();
        const int roles = plot_kind == 0 ? 2 : 4;
        const float plot_top = (plot_kind == 0 ? 4 : 7) * screen.ui()->style().unit;
        const ui::Rect plot{main.x + 55 * scale, main.y + plot_top + 20 * scale,
            std::max(0.f, main.w - 75 * scale), std::max(0.f, main.h - plot_top - (65 + 18 * roles) * scale)};
        const auto path = output + (plot_kind == 0 ? "-loss.png" : "-evaluation.png");
        for (size_t i = 3; i < image.rgba.size(); i += 4) { image.rgba[i] = 255; }
        require(gfx::png_write(path, image), "Write actual GPU PNG");
        evidence["images"].push_back({{"path", path}, {"kind", plot_kind == 0 ? "loss" : "evaluation"},
            {"size", {image.width, image.height}}, {"plot_top_left", {plot.x, plot.y, plot.w, plot.h}}});
        evidence["images"].back()["pixels"] = check_pixels(image, main, plot, roles, scale);
        printf("wrote %s (%dx%d, %s, actual MaterialsEditor GPU pixels)\n", path.c_str(), width, height, gpu->backend_name());
      }
      require(client->stats().schema_violations == 0, "Strict bridge schema violations");
      require(shell.store().viewer().evaluations_started() == 0, "Renderer must not evaluate Viewer");
      evidence["task"] = job; evidence["epoch_rows"] = curves_reply.at("curves"); evidence["status"] = "passed";
    }
    catch (const std::exception &exception) { evidence["error"] = exception.what(); fprintf(stderr, "FAIL: %s\n", exception.what()); rc = 1; }
    { std::ofstream stream(core::path_from_utf8(output + "-evidence.json"), std::ios::binary);
      stream << evidence.dump(2) << '\n'; if (!stream.good()) { rc = 1; } }
    shell.store().set_bridge(nullptr); client->close(); loop.run_ready();
  }
  gfx::dispose_system();
  printf("guardedalloc: %u block(s) in use after shutdown\n", gfx::Runtime::memory_blocks_in_use());
  return rc;
}
