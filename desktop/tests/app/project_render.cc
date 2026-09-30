/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real local project bridge -> shared model -> native editor -> offscreen PNG. */
#include "stk/app/project_state.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/app/bridge_status.hh"
#include "stk/app/shell.hh"
#include "stk/app/editor_area.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "../bridge/support.hh"

#include <cstdio>
#include <filesystem>
#include <fstream>

using namespace stk;

int main(int argc, char **argv)
{
  std::string backend_name, lang = "en", output, editor = "project";
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string arg = argv[i];
    if (arg == "--gpu-backend") { backend_name = argv[i + 1]; }
    else if (arg == "--lang") { lang = argv[i + 1]; }
    else if (arg == "--export") { output = argv[i + 1]; }
    else if (arg == "--editor") { editor = argv[i + 1]; }
    else { return 2; }
  }
  if (output.empty()) { return 2; }
  const bool ai_stream = editor == "ai_stream";
  const bool ai_proposal = editor == "ai_proposal" || editor == "ai_proposal_narrow";
  const bool ai = editor == "ai" || editor == "ai_narrow" || ai_stream || ai_proposal;
  const int canvas_width = editor == "ai_narrow" || editor == "ai_proposal_narrow" ? 760 : 1280;
  bridge::test::TempDir dir{"project-render"};
  bridge::test::ManualLoop loop;
  bridge::ClientOptions bo;
  bo.python.configured = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  bo.state_dir = dir.str() + "/bridge";
  bo.cache_dir = dir.str() + "/cache";
  bo.env["PYTHONPATH"] = STK_REPO_ROOT;
  bo.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
  bo.env["STK_STATE_DIR"] = dir.str() + "/runtime";
  bo.env["STK_TOKEN_PLAN_API_KEY"] = "";
  bo.env["STK_TOKEN_PLAN_MODEL"] = "fixture-model";
  bo.executor = loop.executor();
  bo.strict = bo.validate = true;
  std::string error;
  const std::string stream_prefix = lang == "zh" ?
      "已收到保存的上下文，正在生成回复。\n\n"
      "第一组案例的温度是 300 K，第二组案例是 325 K，相差 25 K。"
      "以下内容仍在生成，只是临时显示；完整回答尚未保存。\n\n"
      "这份上下文没有包含模拟输出，因此不能据此判断结果差异。正在检查参数单位与来源……" :
      "Reading the saved context and generating a reply.\n\n"
      "The first case is 300 K and the second is 325 K, a difference of 25 K. "
      "This text is still being generated and is shown temporarily; the complete answer has not been saved.\n\n"
      "No simulation outputs were included, so result differences cannot be assessed. Checking units and sources...";
  if (ai_stream) {
    const auto python = bridge::find_python(bo.python, error);
    if (!python) { fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1; }
    // The test wrapper installs a file-controlled adapter, never the network transport.
    bo.command = {*python, std::string(STK_REPO_ROOT) + "/desktop/tests/bridge/stream_bridge.py",
        dir.str(), "progress", "--stdio", "--state-dir", bo.state_dir, "--cache-dir", bo.cache_dir, "--strict"};
    std::ofstream prefix(core::path_from_utf8(dir.str() + "/prefix.txt"), std::ios::binary);
    prefix << stream_prefix;
    if (!prefix) { fprintf(stderr, "FAIL: cannot write stream fixture\n"); return 1; }
  }
  auto client = bridge::Client::create(bo);
  if (!client->start(&error)) { fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1; }
  gfx::Backend backend;
  if (!gfx::resolve_backend(backend_name, backend, error)) { return 2; }
  gfx::Runtime runtime;
  auto *system = gfx::create_background_system(error);
  if (!system) { return 1; }
  int rc = 0;
  {
    gfx::GpuOptions go;
    go.backend = backend;
    auto gpu = gfx::Gpu::create(*system, go, error);
    if (!gpu) { fprintf(stderr, "FAIL: %s\n", error.c_str()); gfx::dispose_system(); return 1; }
    gfx::set_ui_scale(1);
    app::ShellOptions so;
    so.language = lang == "zh" ? "zh_CN" : "en";
    so.interactive = false;
    app::AppShell shell(so);
    wm::Screen screen;
    shell.install(screen, nullptr);
    shell.build_default_layout(screen);
    shell.store().set_bridge(client.get());
    app::BridgeStatus bridge_status(shell.store(), *client, nullptr);
    auto &state = shell.store().project();
    state.sync();
    bool ok = loop.pump_until([&] { return state.ready(); }, 60);
    ok = ok && state.create(dir.str() + "/project", "Temperature scan / 温度扫描");
    ok = ok && loop.pump_until([&] { return !state.busy(); }, 30) && state.loaded();
    const std::string table = "11111111-1111-4111-8111-111111111111";
    const std::string temperature = "22222222-2222-4222-8222-222222222222";
    const std::string label = "33333333-3333-4333-8333-333333333333";
    const std::string derived = "55555555-5555-4555-8555-555555555555";
    io::Json commands = io::Json::array({
      {{"op", "create_table"}, {"id", table}, {"name", "Cases / 参数表"}},
      {{"op", "add_field"}, {"id", temperature}, {"table_id", table}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_field"}, {"id", label}, {"table_id", table}, {"name", "Notes / 记录"}, {"type", "text"}},
      {{"op", "add_field"}, {"id", derived}, {"table_id", table}, {"name", "Derived / 派生值"}, {"type", "number"}, {"unit", "K"}}
    });
    for (int i = 0; i < 5; ++i) {
      const std::string id = std::to_string(40000000 + i) + "-4444-4444-8444-444444444444";
      commands.push_back({{"op", "add_record"}, {"id", id}, {"table_id", table}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", temperature}, {"value", 300 + i * 25}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", label}, {"value", "Prepared / 待运行"}});
      commands.push_back({{"op", "set_expression"}, {"table_id", table}, {"record_id", id}, {"field_id", derived},
                          {"expression", i == 4 ? "base / 0" : "base + quantity(10, \"K\")"},
                          {"bindings", {{"base", {{"record_id", id}, {"field_id", temperature}}}}}});
    }
    ok = ok && state.apply(commands) && loop.pump_until([&] { return !state.busy(); }, 30);
    ok = ok && state.loaded() && state.project()->revision == 1;
    if (ok) {
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
      area->set_tab_type(0, editor == "python" ? app::kEditorPython : ai ? app::kEditorAI : app::kEditorProject);
      if (editor == "python") {
        auto &scripts = shell.store().scripts();
        const std::string source =
            "project = stk.project.snapshot()\n"
            "temperatures = [300, 325, 350, 375, 400]\n"
            "for value in temperatures:\n"
            "    print(f'{value} K -> {value - 273.15:.2f} C')\n"
            "print('Project / 项目:', project['project']['name'])\n"
            "print('Editors:', len(stk.ui.editors()))";
        area->editor().load_state({{"source", source}});
        ok = loop.pump_until([&] { return scripts.ready() && scripts.desktop_ready() && !scripts.busy(); }, 30);
        ok = ok && scripts.execute(source) && loop.pump_until([&] {
          screen.run_deferred();
          return !scripts.busy();
        }, 30);
        ok = ok && scripts.status().at("run").at("state") == "succeeded";
      }
      if (editor == "offline") {
        auto &scripts = shell.store().scripts();
        ok = loop.pump_until([&] { return scripts.ready() && scripts.desktop_ready() && !scripts.busy(); }, 30);
        const std::string source = "from examples.project_scan.offline import create_demo\n"
            "offline_demo = create_demo(stk, " + io::Json(dir.str() + "/offline").dump() + ")";
        ok = ok && scripts.execute(source) && loop.pump_until([&] {
          screen.run_deferred();
          return !scripts.busy();
        }, 60);
        ok = ok && scripts.status().at("run").at("state") == "succeeded" && bool(shell.store().viewer().payload());
        if (!ok) {
          for (size_t line = 0; line < scripts.output().line_count(); ++line) {
            fprintf(stderr, "%s\n", std::string(scripts.output().line(line)).c_str());
          }
        }
      }
      if (editor == "files" || editor == "snapshots") {
        auto &viewer = shell.store().viewer();
        ok = ok && loop.pump_until([&] { viewer.pump(); return viewer.presets_loaded(); }, 30);
        const std::string path = dir.str() + "/project/Notes 中文.md";
        { std::ofstream file(core::path_from_utf8(path)); file << "# Simulation notes\n"; }
        ok = ok && state.index_files({path, dir.str() + "/project/results/temperature.vti"}) &&
             loop.pump_until([&] { return !state.busy(); }, 30) && state.selected_file();
        if (editor == "snapshots") {
          state.select_record(state.table()->records.front().id);
          ok = ok && state.capture_file() && loop.pump_until([&] { return !state.busy(); }, 30);
          if (!state.input_snapshots().empty()) {
            ok = ok && state.verify_input_snapshot(io::get_string(state.input_snapshots().front(), "id")) &&
                 loop.pump_until([&] { return !state.busy(); }, 30);
          }
          else { ok = false; }
        }
      }
      if (editor == "runs") {
        std::optional<bridge::Result<io::Json>> result;
        client->call("connections.add_runtime", {{"name", "demo"}, {"url", "http://127.0.0.1:1"},
          {"token", "render-test-only"}, {"check", false}}).then([&](auto r) { result = r; });
        ok = ok && loop.pump_until([&] { return result.has_value(); }, 30) && result->ok();
        io::Json entries = io::Json::array();
        for (int i = 0; i < 4; ++i) {
          entries.push_back({{"table_id", table}, {"record_id", std::to_string(40000000 + i) + "-4444-4444-8444-444444444444"},
            {"label", std::to_string(300 + i * 25) + " K"}, {"spec", {{"workspace_id", std::string(32, 'a')},
              {"argv", io::Json::array({"solver", "--temperature", std::to_string(300 + i * 25)})}}}});
        }
        result.reset();
        client->call("project.runs.prepare", {{"handle", state.project()->handle}, {"connection", "runtime:demo"},
          {"expected_revision", state.project()->revision}, {"entries", entries}}).then([&](auto r) { result = r; });
        ok = ok && loop.pump_until([&] { return result.has_value() && !state.busy(); }, 30) && result->ok();
        ok = ok && state.load_runs() && loop.pump_until([&] { return !state.busy(); }, 30);
        ok = ok && state.runs().size() == 4 && !state.run().empty();
      }
      if (editor == "review" || editor == "review_errors") {
        state.set_review_source(io::Json::array({
          {{"op", "set_cell"}, {"table_id", table}, {"record_id", "40000000-4444-4444-8444-444444444444"},
            {"field_id", temperature}, {"value", 350}},
          {{"op", "set_expression"}, {"table_id", table}, {"record_id", "40000001-4444-4444-8444-444444444444"},
            {"field_id", derived}, {"expression", "base / 0"},
            {"bindings", {{"base", {{"record_id", "40000001-4444-4444-8444-444444444444"}, {"field_id", temperature}}}}}}
        }).dump(2));
        ok = ok && state.preview() && loop.pump_until([&] { return !state.busy(); }, 30);
        ok = ok && state.review() && state.review()->differences.size() == 3 && state.review()->errors.size() == 2;
        ok = ok && state.project()->revision == 1 && state.table()->text(0, 0) == "300";
      }
      if (editor == "drafts") {
        // Persist both lifecycle states through the real project service. The saved
        // proposal is then cleared and explicitly restored before its fresh preview.
        state.set_review_source(io::Json::array({
          {{"op", "set_cell"}, {"table_id", table}, {"record_id", "40000000-4444-4444-8444-444444444444"},
            {"field_id", temperature}, {"value", 325}}
        }).dump());
        ok = ok && state.preview() && loop.pump_until([&] { return !state.busy(); }, 30);
        ok = ok && state.save_review(lang == "zh" ? "较早的温度草案" : "Earlier temperature proposal") &&
             loop.pump_until([&] { return !state.busy(); }, 30) && !state.saved_review().empty();
        const auto discarded_id = io::get_string(state.saved_review(), "id");
        ok = ok && state.discard_saved_draft(discarded_id) && loop.pump_until([&] { return !state.busy(); }, 30);
        ok = ok && io::get_string(state.saved_review(), "status") == "discarded";
        state.discard_review();
        state.set_review_source(io::Json::array({
          {{"op", "set_cell"}, {"table_id", table}, {"record_id", "40000000-4444-4444-8444-444444444444"},
            {"field_id", temperature}, {"value", 350}}
        }).dump());
        ok = ok && state.preview() && loop.pump_until([&] { return !state.busy(); }, 30);
        ok = ok && state.save_review(lang == "zh" ? "首个案例升至 350 K" : "Raise first case to 350 K") &&
             loop.pump_until([&] { return !state.busy(); }, 30) && !state.saved_review().empty();
        const auto pending_id = io::get_string(state.saved_review(), "id");
        state.discard_review();
        ok = ok && state.load_draft(pending_id) && loop.pump_until([&] { return !state.busy(); }, 30);
        ok = ok && !state.review() && io::get_string(state.saved_review(), "status") == "pending";
        ok = ok && state.preview() && loop.pump_until([&] { return !state.busy(); }, 30);
        ok = ok && state.review() && state.review()->differences.size() == 2 && state.review()->errors.size() == 1;
        ok = ok && state.project()->revision == 1 && state.table()->text(0, 0) == "300";
      }
      if (editor == "discussion" || editor == "requests" || ai) {
        auto &discussion = state.discussion();
        const std::string record = "40000000-4444-4444-8444-444444444444";
        const auto wait = [&] { return loop.pump_until([&] { return !state.busy() && !discussion.busy(); }, 30); };
        ok = ok && discussion.capture(table, {record, "40000001-4444-4444-8444-444444444444"}, {temperature, derived},
            lang == "zh" ? "前两个温度案例" : "First two temperature cases") && wait() && !discussion.context().empty();
        const auto context_id = io::get_string(discussion.context(), "id");
        const std::string question = ai_proposal ?
            (lang == "zh" ? "请建议将第一个案例的温度改为 350 K，保留单位。\n先保存为草案供检查，不要应用或启动计算。" :
             "Suggest raising the first case to 350 K, keeping its units.\nSave a draft for review; do not apply it or run a simulation.") :
            (lang == "zh" ? "请比较这两个温度案例。\n先检查参数变化，再决定是否启动计算。" :
             "Compare these two temperature cases.\nReview the parameter change before deciding whether to run.");
        ok = ok && discussion.add_message(question) && wait();
        if (!ai_proposal) {
          // Existing discussion fixtures intentionally show a historical context.
          // A new parameter proposal instead retains the captured current revision.
          state.set_review_source(io::Json::array({{{"op", "set_cell"}, {"table_id", table}, {"record_id", record},
              {"field_id", temperature}, {"value", 350}}}).dump());
          ok = ok && state.preview() && wait() && state.save_review("350 K") && wait();
          ok = ok && discussion.link_review() && wait();
          state.discard_review();
          ok = ok && state.apply(io::Json::array({{{"op", "set_cell"}, {"table_id", table}, {"record_id", record},
              {"field_id", temperature}, {"value", 310}}})) && wait();
          ok = ok && discussion.capture(table, {record}, {temperature},
              lang == "zh" ? "编辑后的新上下文" : "New context after editing") && wait();
          ok = ok && discussion.load_context(context_id) && wait();
        }
        ok = ok && discussion.load_page("contexts") && wait();
        ok = ok && (ai || area->editor().show_view("discussion")) && discussion.error().empty();
      }
      if (editor == "requests" || ai) {
        auto &discussion = state.discussion();
        const std::string pending = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
        const std::string cancelled = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
        for (const auto &id : {pending, cancelled}) {
          std::optional<bridge::Result<io::Json>> result;
          io::Json params = {{"handle", state.project()->handle}, {"request_id", id},
              {"message_id", discussion.message().at("id")},
              {"configuration", {{"adapter", ai_stream ? "aliyun-token-plan/1" : "test-controlled"},
                                 {"model", "fixture-v1"}}}};
          if (ai_proposal) { params["prompt_version"] = "stk.parameter-edits/1"; }
          client->call("project.requests.create", std::move(params)).then([&](auto value) { result = value; });
          ok = ok && loop.pump_until([&] { return result.has_value(); }, 30) && result->ok();
        }
        const auto wait = [&] { return loop.pump_until([&] { return !discussion.busy(); }, 30); };
        ok = ok && discussion.cancel_request(cancelled) && wait() && discussion.load_request(pending) && wait();
        ok = ok && discussion.load_page("requests") && wait() && discussion.page("requests").items.size() == 2;
        ok = ok && discussion.load_provider() && wait();
        if (ai_stream) {
          // Use the registered executor and progress API. Leave the adapter at its
          // first marker so the capture shows unsaved text, never a fabricated completion.
          ok = ok && discussion.start_request(pending) && wait();
          ok = ok && loop.pump_until([&] {
            return std::filesystem::exists(core::path_from_utf8(dir.str() + "/first"));
          }, 30);
          ok = ok && discussion.load_exchange(pending) && loop.pump_until([&] {
            discussion.pump(std::chrono::duration<double>(
                std::chrono::steady_clock::now().time_since_epoch()).count());
            return !discussion.exchange_busy();
          }, 30);
          ok = ok && discussion.progress_supported() && discussion.exchange_reply().empty() &&
               !discussion.exchange_progress().empty() &&
               io::get_string(discussion.exchange_progress(), "text") == stream_prefix &&
               io::get_string(discussion.exchange_request(), "status") == "running";
          ok = ok && discussion.load_page("messages") && wait() && discussion.page("messages").items.size() == 1;
          ok = ok && discussion.load_page("requests") && wait();
        }
        else if (ai) {
          // Controlled completion for rendering only; fixture credentials are empty.
          auto &scripts = shell.store().scripts();
          ok = ok && loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30);
          std::string answer = lang == "zh" ?
              "受控显示样例\n\n两个案例的保存温度分别是 300 K 和 325 K，相差 25 K。\n"
              "派生温度分别是 310 K 和 335 K。\n\n这份上下文不包含模拟输出，无法判断结果差异。"
              "可以先检查参数的单位和来源，再选择需要运行的案例。保存的回答与捕获时的输入版本关联，"
              "后续修改表格不会改写这份记录；准备问题也不会自动修改参数或提交模拟。" :
              "Controlled display fixture\n\nThe saved temperatures are 300 K and 325 K, a difference of 25 K.\n"
              "Derived temperatures are 310 K and 335 K.\n\nNo simulation outputs were included; result differences cannot be assessed. "
              "Review units and sources before choosing which cases to run. This saved answer is linked to the captured input version; "
              "later table edits do not rewrite that record. Preparing a question does not change parameters or submit simulations.";
          if (ai_proposal) {
            answer = io::Json{{"format", "stk.parameter-edits/1"},
                {"context_id", discussion.context().at("id")}, {"base_revision", state.project()->revision},
                {"summary", lang == "zh" ?
                    "建议把第一个案例的温度从 300 K 提高到 350 K，以便与第二个案例比较。"
                    "保留 K 单位和派生温度公式。该建议尚未应用，也没有启动模拟。" :
                    "Raise the first case from 300 K to 350 K for comparison with the second case. "
                    "Keep the K unit and the derived-temperature formula. This suggestion has not been applied and no simulation was started."},
                {"edits", io::Json::array({{{"record_id", "40000000-4444-4444-8444-444444444444"},
                                          {"field_id", temperature}, {"value", 350}}})}}.dump();
          }
          ok = ok && scripts.execute("from suan.project import ProjectStore\nfrom uuid import uuid4\n"
              "s=ProjectStore(" + io::Json(dir.str() + "/project").dump() + ")\nowner=str(uuid4())\n"
              "s.requests._claim('" + pending + "', executor_id=owner)\n"
              "s.requests._complete('" + pending + "', executor_id=owner, text=" + io::Json(answer).dump() + ")");
          ok = ok && loop.pump_until([&] { return !scripts.busy(); }, 30) &&
              scripts.status().at("run").at("state") == "succeeded";
          ok = ok && discussion.load_exchange(pending) &&
              loop.pump_until([&] { return !discussion.exchange_busy(); }, 30) && !discussion.exchange_reply().empty();
          if (ai_proposal) {
            // Completion itself creates no draft. Conversion is a separate explicit
            // bridge operation, and the AI editor displays the saved pending candidate.
            ok = ok && discussion.exchange_edit_proposal().at("draft").is_null();
            ok = ok && discussion.propose_exchange_edits() && wait();
            const auto candidate = discussion.exchange_edit_proposal().at("draft");
            ok = ok && io::get_string(candidate, "status") == "pending" && candidate.at("base_revision") == 1 &&
                 candidate.at("commands").size() == 1 && candidate.at("commands").front().at("value") == 350;
            state.refresh();
            ok = ok && loop.pump_until([&] { return !state.busy(); }, 30) && state.project()->revision == 1 &&
                 state.table()->text(0, 0) == "300" && state.saved_review().empty() && !state.review();
          }
          ok = ok && discussion.load_page("requests") && wait();
        }
      }
      if (editor == "csv") {
        const auto source = dir.str() + "/project/parameters.csv";
        { std::ofstream file(core::path_from_utf8(source)); file << "Temperature,Note\n300,Prepared / 待运行\n350,Comparison / 对比\n"; }
        ok = ok && state.import_csv(source, "Imported parameters / 导入参数", {{"Temperature", "number"}},
                                   {{"Temperature", "K"}}, ",") && loop.pump_until([&] { return !state.busy(); }, 30);
      }
      if (editor == "simulation" || editor == "batches") {
        const auto source = core::path_from_utf8(dir.str() + "/case");
        std::filesystem::create_directories(source);
        { std::ofstream file(source / "input.toml");
          file << "material = 'material.toml'\n[system]\nsimulation_grid = [16,16,16]\n"
                  "temperature = 298\ntimestep_total = 101\ndt = 0.01\n[output]\ninterval = 100\n"; }
        { std::ofstream file(source / "material.toml"); file << "[landau]\na1 = '3.8e5*(TEM-479)'\n"; }
      }
      if (editor == "recent") {
        ok = ok && state.close() && loop.pump_until([&] { return !state.busy() && !state.recent_loading(); }, 30);
        ok = ok && state.create(dir.str() + "/comparison", "Comparison / 对比分析") &&
             loop.pump_until([&] { return !state.busy() && !state.recent_loading(); }, 30);
        ok = ok && state.close() && loop.pump_until([&] { return !state.busy(); }, 30);
      }
      if (editor != "offline") { screen.set_maximized(area); }
      wm::DrawContext ctx;
      ctx.ui_scale = 1;
      ctx.fonts = &gpu->fonts();
      ctx.rect = {0, 0, canvas_width, 900};
      ctx.now = 100;
      gfx::Image image;
      if (editor == "review" || editor == "review_errors" || editor == "drafts") {
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *widget = screen.ui()->find("a2/main/project_view")) { widget->index.assign(1); }
        else { ok = false; }
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        const auto *apply = screen.ui()->find("a2/main/review_apply");
        ok = ok && apply && apply->enabled;
        if (editor == "review_errors") {
          if (const auto *widget = screen.ui()->find("a2/main/review_category")) { widget->index.assign(1); }
          else { ok = false; }
        }
        if (editor == "drafts") {
          // Use normal panel hit targets so the capture includes the real saved
          // list and controls, while keeping the candidate table on the same page.
          for (const auto *key : {"a2/main/review_details", "a2/main/saved_reviews"}) {
            if (const auto *widget = screen.ui()->find(key)) {
              const ui::Vec2 center{widget->rect.x + widget->rect.w / 2, widget->rect.y + widget->rect.h / 2};
              screen.ui()->handle_event(ui::Event::mouse_down(center));
              screen.ui()->handle_event(ui::Event::mouse_up(center));
            }
            else { ok = false; }
            ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
            ok = ok && loop.pump_until([&] { return !state.busy(); }, 30);
          }
          ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
          ok = ok && state.drafts_loaded() && state.drafts().size() == 2 && state.drafts_error().empty();
          if (const auto *widget = screen.ui()->find("a2/main/saved_reviews/draft_rows"); widget && widget->table) {
            widget->table->selected.assign(1);
          }
          else { ok = false; }
          if (const auto *widget = screen.ui()->find("a2/main/saved_reviews/draft_title")) {
            widget->string.assign(lang == "zh" ? "首个案例升至 350 K" : "Raise first case to 350 K");
          }
          else { ok = false; }
          const auto *restored_apply = screen.ui()->find("a2/main/review_apply");
          ok = ok && restored_apply && restored_apply->enabled;
        }
      }
      if (editor == "recent") {
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        ok = ok && loop.pump_until([&] { return !state.recent_loading(); }, 30);
        if (const auto *widget = screen.ui()->find("a2/main/project_recent/projects"); widget && widget->table) {
          widget->table->selected.assign(0);
        }
        else { ok = false; }
      }
      if (editor == "requests") {
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *tabs = screen.ui()->find("a2/main/discussion_category")) { tabs->index.assign(3); }
        else { ok = false; }
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        const auto *cancel = screen.ui()->find("a2/main/request_cancel");
        ok = ok && cancel && cancel->enabled && state.project()->revision == 2;
      }
      if (editor == "discussion") {
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *panel = screen.ui()->find("a2/main/message_composer")) {
          const ui::Vec2 point{panel->rect.cx(), panel->rect.cy()};
          screen.ui()->handle_event(ui::Event::mouse_down(point));
          screen.ui()->handle_event(ui::Event::mouse_up(point));
        }
        else { ok = false; }
      }
      if (editor == "filter") {
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *search = screen.ui()->find("a2/main/table_search")) { search->string.assign("prepared"); }
        else { ok = false; }
        if (const auto *errors = screen.ui()->find("a2/main/table_errors_only")) { errors->boolean.assign(true); }
        else { ok = false; }
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *rows = screen.ui()->find("a2/main/" + table + "/records"); rows && rows->table) {
          ok = ok && rows->table->rows == 1;
          rows->table->selected.assign(0);
        }
        else { ok = false; }
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        ok = ok && state.record_id() == "40000004-4444-4444-8444-444444444444" && state.project()->revision == 1;
      }
      if (editor == "expression") {
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *widget = screen.ui()->find("a2/main/cell_field")) {
          widget->index.assign(2);
        }
        else { ok = false; }
      }
      if (editor == "manage" || editor == "files" || editor == "snapshots" || editor == "runs" || editor == "csv" || editor == "simulation" || editor == "batches") {
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *widget = screen.ui()->find((editor == "simulation" || editor == "batches") ? "a2/main/project_simulation" : editor == "manage" ? "a2/main/manage_objects" :
                                                  editor == "files" ? "a2/main/project_files" : editor == "csv" ? "a2/main/project_csv" : editor == "runs" ? "a2/main/project_runs" : "a2/main/input_snapshots")) {
          const ui::Vec2 center{widget->rect.x + widget->rect.w / 2, widget->rect.y + widget->rect.h / 2};
          screen.ui()->handle_event(ui::Event::mouse_down(center));
          screen.ui()->handle_event(ui::Event::mouse_up(center));
        }
        else { ok = false; }
      }
      if (editor == "simulation" || editor == "batches") {
        auto &scripts = shell.store().scripts();
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        ok = ok && loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30);
        if (const auto *widget = screen.ui()->find("a2/main/project_simulation/simulation_source")) {
          widget->string.assign(dir.str() + "/case");
        }
        else { ok = false; }
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *widget = screen.ui()->find("a2/main/project_simulation/simulation_import"); widget && widget->enabled) {
          widget->on_click();
        }
        else { ok = false; }
        ok = ok && loop.pump_until([&] { screen.run_deferred(); return !scripts.busy() && !state.busy(); }, 30);
        ok = ok && scripts.status().at("run").at("state") == "succeeded";
        state.select_table("27e50c45-2d61-523c-a56b-f505bbd595c5");
        ok = ok && state.table() && state.table()->records.size() == 1;
        if (editor == "batches") {
          const auto id = state.record_id();
          ok = ok && scripts.execute("p = stk.project\nrow = stk.muferro.clone_case(" + io::Json(id).dump() +
              ", expected_revision=p.snapshot()['project']['revision'])['record_id']\n"
              "stk.batches.create('muferro/1', [" + io::Json(id).dump() +
              ", row], 'runtime:lab', expected_revision=p.snapshot()['project']['revision']); None");
          ok = ok && loop.pump_until([&] { screen.run_deferred(); return !scripts.busy() && !state.busy(); }, 30);
          ok = ok && scripts.status().at("run").at("state") == "succeeded";
          ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
          for (const auto *key : {"a2/main/project_simulation", "a2/main/project_batches"}) {
            if (const auto *widget = screen.ui()->find(key)) {
              const ui::Vec2 center{widget->rect.x + widget->rect.w / 2, widget->rect.y + widget->rect.h / 2};
              screen.ui()->handle_event(ui::Event::mouse_down(center));
              screen.ui()->handle_event(ui::Event::mouse_up(center));
            }
            else { ok = false; }
            ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
          }
        }
      }
      if (editor == "csv") {
        ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *widget = screen.ui()->find("a2/main/project_csv/source")) {
          widget->string.assign(dir.str() + "/project/parameters.csv");
          screen.ui()->find("a2/main/project_csv/name")->string.assign("Imported parameters / 导入参数");
          screen.ui()->find("a2/main/project_csv/destination")->string.assign(dir.str() + "/project/results.csv");
        }
        else { ok = false; }
      }
      if (editor == "runs") {
        // Drawing services queued model notifications; wait for resulting list/detail reads
        // before capturing enabled controls rather than the transient loading frame.
        for (int i = 0; i < 3; ++i) {
          ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
          ok = ok && loop.pump_until([&] { return !state.busy(); }, 30);
        }
      }
      if (editor == "offline") {
        // A new editor attaches during its first UI draw; subsequent frames draw its GPU region.
        for (int frame = 0; frame < 2; ++frame) {
          ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
        }
      }
      if (editor == "offline") {
        const auto *table = screen.ui()->find("demo-project/main/" + state.table_id() + "/records");
        if (table) {
          screen.ui()->handle_event(ui::Event::wheel({table->rect.cx(), table->rect.cy()}, -1000, 0, ui::MOD_SHIFT));
        }
        else { ok = false; }
      }
      ok = ok && gfx::render_offscreen(canvas_width, 900, [&] { screen.draw(ctx); }, image, error);
      if (ai_stream) {
        const auto *cancel = screen.ui()->find("a2/main/ai_cancel");
        const auto *send = screen.ui()->find("a2/main/ai_send_saved");
        const auto *transcript = screen.ui()->find("a2/main/ai_transcript");
        bool temporary_label = false;
        if (transcript && transcript->log) {
          for (size_t line = 0; line < transcript->log->line_count(); ++line) {
            temporary_label |= transcript->log->line(line).find(shell.store().tr("ai.temporary_reply")) != std::string_view::npos;
          }
        }
        ok = ok && cancel && cancel->enabled && send && !send->enabled && temporary_label &&
             state.discussion().exchange_reply().empty() && client->stats().schema_violations == 0;
      }
      if (ai_proposal) {
        const auto *save = screen.ui()->find("a2/main/ai_save_edits");
        const auto *open = screen.ui()->find("a2/main/ai_open_edits");
        const auto *transcript = screen.ui()->find("a2/main/ai_transcript");
        bool suggested_cell = false;
        if (transcript && transcript->log) {
          for (size_t line = 0; line < transcript->log->line_count(); ++line) {
            const auto text = transcript->log->line(line);
            suggested_cell |= text.find("Temperature") != std::string_view::npos && text.find("350") != std::string_view::npos;
          }
        }
        ok = ok && save && !save->enabled && open && open->enabled && suggested_cell &&
             state.project()->revision == 1 && state.table()->text(0, 0) == "300" &&
             state.saved_review().empty() && !state.review() &&
             io::get_string(state.discussion().exchange_edit_proposal().at("draft"), "status") == "pending" &&
             client->stats().schema_violations == 0;
      }
      ok = ok && gfx::png_write(output, image);
    }
    if (!ok) { fprintf(stderr, "FAIL: %s %s\n%s", state.error().c_str(), error.c_str(), client->bridge_log().text().c_str()); rc = 1; }
    else { printf("wrote %s\n", output.c_str()); }
    state.attach(nullptr);
    shell.store().set_bridge(nullptr);
    client->close();
    loop.run_ready();
  }
  gfx::dispose_system();
  return rc;
}
