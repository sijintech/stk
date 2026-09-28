/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>

namespace stk::app {
namespace {
using io::Json;

class ScriptPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"scripts"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en"};
  std::unique_ptr<bridge::Client> client;

  ScriptState &state() { return f.shell->store().scripts(); }
  bool pump(const std::function<bool()> &until, const double timeout = 30)
  {
    return loop.pump_until([&] { f.screen.run_deferred(); return until(); }, timeout);
  }
  std::string output()
  {
    std::string text;
    const auto &log = state().output();
    for (size_t i = 0; i < log.line_count(); ++i) {
      text += log.line(i);
      text += '\n';
    }
    return text;
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON to run Python desktop tests"; }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge";
    options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.executor = loop.executor();
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    f.shell->store().set_bridge(client.get());
    ASSERT_TRUE(pump([&] { return state().ready() && state().desktop_ready() && !state().busy(); }, 60))
        << client->bridge_log().text();
  }
  void TearDown() override
  {
    f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); }
    loop.run_ready();
    EXPECT_EQ(client ? client->stats().schema_violations : 0, 0u);
  }
  void execute(const std::string &code, const std::string &expected = "succeeded")
  {
    ASSERT_TRUE(state().execute(code)) << state().error();
    ASSERT_TRUE(pump([&] { return !state().busy(); })) << client->bridge_log().text();
    ASSERT_TRUE(state().error().empty()) << state().error();
    EXPECT_EQ(state().status().at("run").at("state"), expected) << output();
  }
};

TEST_F(ScriptPython, LayoutRoundTripAndInvalidLayoutKeepTheCurrentScreen)
{
  const auto original = f.screen.to_json();
  execute("import copy\nsaved = stk.ui.layout()\nprint([e['id'] for e in stk.ui.editors()])\n"
          "changed = copy.deepcopy(saved)\n"
          "changed['screen'] = {'maximized': None, 'root': {'factor': 1, 'split': 'horizontal', 'children': ["
          "{'factor': 0.65, 'area': {'id': 'left', 'type': 'viewer'}},"
          "{'factor': 0.35, 'area': {'id': 'right', 'type': 'project'}}]}}\n"
          "stk.ui.apply_layout(changed)");
  EXPECT_EQ(f.screen.areas().size(), 2u);
  EXPECT_NE(output().find("viewer"), std::string::npos);
  const auto valid = f.screen.to_json();
  execute("bad = copy.deepcopy(changed)\nbad['screen']['root']['children'][1]['area']['id'] = 'left'\nstk.ui.apply_layout(bad)", "failed");
  EXPECT_EQ(f.screen.to_json(), valid);
  EXPECT_NE(output().find("invalid_params"), std::string::npos);
  execute("stk.ui.apply_layout(saved)");
  EXPECT_EQ(f.screen.to_json(), original);
  EXPECT_EQ(state().history().size(), 3u);
}

TEST_F(ScriptPython, ScriptsAndVisibleProjectUseTheSameRevisionedState)
{
  const auto directory = dir.str() + "/project";
  execute("p = stk.projects.create(" + Json(directory).dump() + ", 'Python project')\n"
          "stk.ui.open_project(" + Json(directory).dump() + ")\n"
          "p.apply([{'op': 'create_table', 'name': 'Cases'}], expected_revision=0)");
  auto &project = f.shell->store().project();
  ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy() && project.project()->revision == 1; }));
  ASSERT_EQ(project.tables().size(), 1u);
  EXPECT_EQ(project.tables()[0].name, "Cases");
  execute("print(stk.ui.current_project()['revision'])\nstk.project.apply([{'op': 'rename_table', 'id': p.snapshot()['tables'][0]['id'], 'name': 'Renamed'}], expected_revision=1)");
  ASSERT_TRUE(pump([&] { return !project.busy() && project.project()->revision == 2; }));
  EXPECT_EQ(project.tables()[0].name, "Renamed");
  execute("stk.project.apply([{'op': 'create_table', 'name': 'stale'}], expected_revision=0)", "failed");
  EXPECT_EQ(project.project()->revision, 2);
  execute("stk.ui.close_project()");
  EXPECT_FALSE(project.project());
  execute("stk.ui.open_project(" + Json(directory + "/missing").dump() + ")", "failed");
  EXPECT_FALSE(project.project());
}

TEST_F(ScriptPython, InterruptAndBridgeRestartNeverReplayUserCode)
{
  ASSERT_TRUE(state().execute("answer = 42\nprint('loop started', flush=True)\nwhile True:\n    pass"));
  ASSERT_TRUE(pump([&] { return output().find("loop started") != std::string::npos; }));
  EXPECT_FALSE(state().execute("print('must not run')"));
  ASSERT_TRUE(state().interrupt());
  ASSERT_TRUE(pump([&] { return !state().busy(); }));
  EXPECT_EQ(state().status().at("run").at("state"), "cancelled");
  execute("answer", "failed");
  execute("print('one execution')");
  const auto old_session = state().session();
  client->shutdown_bridge();
  ASSERT_TRUE(pump([&] { return state().ready() && state().desktop_ready() && state().session() != old_session; }, 60))
      << client->bridge_log().text();
  ASSERT_TRUE(pump([&] { return !state().busy(); }));
  const auto text = output();
  const auto first = text.find("one execution");
  ASSERT_NE(first, std::string::npos);
  EXPECT_EQ(text.find("one execution", first + 1), std::string::npos);
  execute("print('new session')");
}

TEST_F(ScriptPython, DetachedBridgeDoesNotRunQueuedLayoutMutations)
{
  auto layout = wm::layout_to_json(f.shell->capture_layout(f.screen, nullptr));
  layout["screen"] = {{"maximized", nullptr}, {"root", {{"factor", 1},
      {"area", {{"id", "replacement"}, {"type", "viewer"}}}}}};
  // Pump only bridge callbacks until the UI request has been queued on Screen::defer.
  bool requested = false;
  auto listener = client->on_event("ui.request", [&](const auto &, const auto &) { requested = true; });
  ASSERT_TRUE(state().execute("import json\nstk.ui.apply_layout(json.loads(" + Json(layout.dump()).dump() + "))"));
  ASSERT_TRUE(loop.pump_until([&] { return requested; }, 30));
  f.shell->store().set_bridge(nullptr);
  const auto before = f.screen.to_json();
  f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), before);
  // The old request cannot send a reply through a replacement/detached client.
  EXPECT_FALSE(state().ready());
}

TEST_F(ScriptPython, ConsoleEditorRunsMultilineDraftAndRestoresWithoutExecuting)
{
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorPython));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto *source = f.screen.ui()->find("a2/main/python_source");
  ASSERT_NE(source, nullptr);
  EXPECT_TRUE(source->text_opts.multiline);
  source->string.assign("print('console 中文')\n40 + 2");
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/python_source");
  f.drv->click(x, y);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  f.drv->key(wm::Key::End, primary);
  f.drv->key(wm::Key::Enter, primary);
  ASSERT_TRUE(pump([&] { return !state().busy() && state().status().contains("run") && state().status()["run"].is_object(); }));
  EXPECT_EQ(state().status()["run"]["state"], "succeeded") << output();
  EXPECT_NE(output().find("console 中文"), std::string::npos);
  EXPECT_NE(output().find("42"), std::string::npos);
  const auto run = state().status()["run"]["id"];
  const auto saved = f.shell->capture_layout(f.screen, nullptr);
  f.drv->click(x, y);
  ASSERT_NE(f.screen.ui()->editing(), 0u);
  f.shell->build_default_layout(f.screen);
  EXPECT_EQ(f.screen.ui(), nullptr); // old text bindings must not outlive their editor owner
  ASSERT_TRUE(f.shell->apply_layout(f.screen, saved));
  f.drv->frame();
  const auto *restored = f.screen.ui()->find("a2/main/python_source");
  ASSERT_NE(restored, nullptr);
  EXPECT_EQ(restored->string.value(), "print('console 中文')\n40 + 2");
  auto &restored_area = f.area("a2");
  auto context = restored_area.context(nullptr, nullptr);
  ASSERT_TRUE(restored_area.editor().on_drop({dir.str() + "/selected-only.py"}, context));
  f.drv->frame();
  loop.run_ready();
  EXPECT_EQ(state().status()["run"]["id"], run);
  EXPECT_EQ(restored_area.editor().save_state()["path"], dir.str() + "/selected-only.py");
}

TEST_F(ScriptPython, ViewerPayloadControlsKeepInvalidUpdatesAndStaleSourcesOut)
{
  const std::string path = std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp";
  execute("opened = stk.viewer.open(" + Json(path).dump() + ", focus=False)\n"
          "assert stk.viewer.wait(timeout=0)['has_payload']\n"
          "key = opened['source']['key']\n"
          "assert opened['source']['kind'] == 'payload'\n"
          "layer = next(layer for layer in opened['layers'] if layer['has_opacity'])\n"
          "stk.viewer.configure(overlays=False, auto_evaluate=False, prefetch=False, fps=2.5, loop=False)\n"
          "stk.viewer.layer(layer['id'], visible=False, opacity=0.25, expected_source=key)\n"
          "saved = stk.viewer.status()\n"
          "assert not saved['overlays'] and not saved['auto_evaluate'] and saved['fps'] == 2.5\n"
          "changed = next(item for item in saved['layers'] if item['id'] == layer['id'])\n"
          "assert not changed['visible'] and changed['opacity'] == 0.25");
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(viewer.payload());
  const auto source = viewer.source().key();
  execute("stk.viewer.configure(overlays=True, fps=0)", "failed");
  EXPECT_FALSE(viewer.overlays());
  execute("stk.viewer.layer(layer['id'], visible=True, opacity=2)", "failed");
  execute("assert not next(item for item in stk.viewer.status()['layers'] if item['id'] == layer['id'])['visible']");
  execute("stk.viewer.close(expected_source='different')", "failed");
  EXPECT_EQ(viewer.source().key(), source);
  execute("stk.viewer.open('missing.stkp')", "failed");
  EXPECT_EQ(viewer.source().key(), source);
  execute("stk.viewer.configure(parameters={'unknown': 3}, overlays=True)", "failed");
  EXPECT_FALSE(viewer.overlays());
  execute("stk.viewer.step(True)", "failed");
  execute("stk.viewer.play(True)", "failed");
  const auto camera = viewer.camera_serial();
  execute("stk.viewer.reset_camera(expected_source=key)\nstk.viewer.cancel(expected_source=key)");
  EXPECT_GT(viewer.camera_serial(), camera);
  execute("stk.viewer.close(expected_source=key)\nassert stk.viewer.status()['source']['kind'] == 'none'");
  EXPECT_FALSE(viewer.payload());
}

TEST_F(ScriptPython, ViewerSeriesStepAndPlaybackUseTheSameSharedTimeline)
{
  execute("import json, shutil\nfrom pathlib import Path\n"
          "folder = Path(" + Json(dir.str() + "/series").dump() + ")\n"
          "payload = Path(" + Json(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains").dump() + ")\n"
          "manifest = json.loads((payload / 'manifest.json').read_text())\nframes = []\n"
          "for step in [1, 5]:\n"
          "    name = f'view.{step}'\n"
          "    shutil.copytree(payload, folder / name)\n"
          "    result = {'schema': 'stk.graph-result/1', 'graph_sha256': '0'*64, 'graph_hash': 'sha256:' + '0'*64,\n"
          "              'profile': 'desktop', 'outputs': {'view': {'type': 'payload', 'manifest': manifest}},\n"
          "              'parameters': {'step': {'value': step, 'choices': []}}, 'keys': {}, 'evaluated': [],\n"
          "              'timings': {}, 'cache': {'hits': 0, 'misses': 0}, 'warnings': [], 'files': {'view': name + '/manifest.json'}}\n"
          "    result_name = f'result.{step}.json'\n"
          "    (folder / result_name).write_text(json.dumps(result))\n"
          "    frames.append({'step': step, 'outputs': {'view': name + '/manifest.json'}, 'result': result_name})\n"
          "(folder / 'series.json').write_text(json.dumps({'schema': 'stk.series/1', 'parameter': 'step', 'frames': frames}))\n"
          "opened = stk.viewer.open(folder, focus=False)\n"
          "assert opened['source']['kind'] == 'result' and opened['steps'] == [1, 5]\n"
          "assert stk.viewer.step(0)['shown_step'] == 1\n"
          "stk.viewer.configure(fps=4, loop=True)\n"
          "assert stk.viewer.play()['playing']\n"
          "assert not stk.viewer.play(False)['playing']\n"
          "assert stk.viewer.step(1)['shown_step'] == 5");
  auto &viewer = f.shell->store().viewer();
  EXPECT_EQ(viewer.step_index(), 1);
  EXPECT_EQ(viewer.shown_step(), Json(5));
  execute("stk.viewer.step(2)", "failed");
  EXPECT_EQ(viewer.step_index(), 1);
  execute("stk.viewer.step(0.5)", "failed");
  EXPECT_EQ(viewer.step_index(), 1);
}

#ifndef _WIN32  // The Windows bridge test environment intentionally has no NumPy/VTK.
TEST_F(ScriptPython, OfflineWorkbenchDemoBuildsProjectAndConfiguresThreeEditorsWithoutRuntime)
{
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(pump([&] { viewer.pump(); return viewer.presets_loaded() && !viewer.catalog().is_null(); }, 60));
  execute("from examples.project_scan.offline import create_demo\n"
          "offline_demo = create_demo(stk, " + Json(dir.str() + "/offline").dump() + ")\n"
          "assert stk.ui.current_project()['id'] == offline_demo['project_id']\n"
          "assert stk.viewer.status()['has_payload']\n"
          "assert stk.projects.open(offline_demo['directory']).runs.list()['runs'] == []");
  EXPECT_EQ(f.screen.areas().size(), 3u);
  EXPECT_NE(f.screen.find_area("demo-project"), nullptr);
  EXPECT_NE(f.screen.find_area("demo-view"), nullptr);
  EXPECT_NE(f.screen.find_area("demo-python"), nullptr);
  EXPECT_TRUE(viewer.payload());
  EXPECT_EQ(viewer.source().kind, SourceKind::RunDir);
  auto &project = f.shell->store().project();
  ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy(); }));
  EXPECT_EQ(project.tables().size(), 4u);  // parameters, controls, results and the file index
  EXPECT_EQ(project.project()->revision, 5);
  execute("stk.viewer.open(offline_demo['folders'][0] + '/field.vtk', preset='volume')\n"
          "shown = stk.viewer.wait(timeout=30)\n"
          "assert shown['has_payload'] and not shown['error'], shown\n"
          "assert shown['source']['field_file'] == 'field.vtk'\n"
          "assert shown['parameters']['path'] == 'field.vtk'");
  execute("stk.ui.apply_layout(offline_demo['previous_layout'])");
  EXPECT_EQ(f.screen.areas().size(), 4u);
}

TEST_F(ScriptPython, ViewerOpensSyntheticResultsAndReevaluatesExplicitParameters)
{
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(pump([&] { viewer.pump(); return viewer.presets_loaded() && !viewer.catalog().is_null(); }, 60));
  execute("from pathlib import Path\nfrom examples.project_scan.solver import simulate\n"
          "directory = Path(" + Json(dir.str() + "/field").dump() + ")\n"
          "simulate({'temperature_K': 300, 'size': 5}, directory)\n"
          "assert any(p['id'] == 'volume' for p in stk.viewer.presets()['presets'])\n"
          "from examples.project_scan.show import show_directory\n"
          "shown = show_directory(stk, directory, focus=False)\n"
          "assert shown['has_payload'] and not shown['error'], shown\n"
          "assert shown['preset'] == 'volume' and shown['parameters']['path'] == 'field.vtk'\n"
          "key = shown['source']['key']\n"
          "stk.viewer.configure(auto_evaluate=False, parameters={'colormap': 'cividis'}, expected_source=key)\n"
          "assert stk.viewer.status()['pending_edit'] == 'client'\n"
          "stk.viewer.evaluate(expected_source=key)\n"
          "updated = stk.viewer.wait(timeout=25)\n"
          "assert updated['has_payload'] and not updated['error'], updated\n"
          "assert updated['parameters']['colormap'] == 'cividis'\n"
          "assert updated['evaluation']['id'] != shown['evaluation']['id']");
  EXPECT_TRUE(viewer.payload());
  EXPECT_EQ(viewer.source().kind, SourceKind::RunDir);
  const auto old_parameters = viewer.parameters();
  execute("stk.viewer.configure(parameters={'colormap': 'bad', 'path': 'missing.vtk'}, overlays=False)", "failed");
  EXPECT_EQ(viewer.parameters(), old_parameters);
  EXPECT_TRUE(viewer.overlays());
  execute("stk.viewer.configure(parameters={'path': 'missing.vtk'})\nstk.viewer.evaluate()\n"
          "failed = stk.viewer.wait(timeout=25)\nassert failed['error']");
}
#endif

}  // namespace
}  // namespace stk::app
