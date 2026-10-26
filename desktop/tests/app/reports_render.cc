/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real frozen report -> ReportsEditor reading or unsaved creation form -> GPU screenshot. No mock controls. */
#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/io/json.hh"
#include "stk/io/payload.hh"
#include "stk/io/png.hh"
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
constexpr const char *kReport = "a1111111-1111-4111-8111-111111111111";
constexpr const char *kContext = "b2222222-2222-4222-8222-222222222222";
constexpr const char *kTable = "c3333333-3333-4333-8333-333333333333";
constexpr const char *kField = "d4444444-4444-4444-8444-444444444444";
constexpr const char *kRow = "e5555555-5555-4555-8555-555555555555";

void require(const bool condition, const std::string &message)
{
  if (!condition) { throw std::runtime_error(message); }
}

void write_text(const fs::path &path, const std::string &value)
{
  std::ofstream output(path, std::ios::binary);
  output.write(value.data(), std::streamsize(value.size()));
  require(output.good(), "write fixture " + core::path_to_utf8(path));
}

io::Image plot_fixture()
{
  io::Image image(480, 200);
  const std::array<int, 4> top = {115, 86, 51, 30};
  const std::array<std::array<uint8_t, 3>, 4> colors = {{{24, 170, 145}, {70, 120, 230},
      {225, 160, 55}, {70, 120, 230}}};
  for (uint32_t y = 0; y < image.height; ++y) {
    for (uint32_t x = 0; x < image.width; ++x) {
      auto *pixel = image.pixel(x, y);
      std::array<uint8_t, 3> color = {248, 250, 252};
      if (x >= 30 && x <= 455 && y >= 20 && y <= 174 && (y % 30 == 24 || x == 30)) {
        color = {206, 216, 225};
      }
      for (int bar = 0; bar < 4; ++bar) {
        if (int(x) >= 55 + 100 * bar && int(x) < 115 + 100 * bar && int(y) >= top[bar] && y < 174) {
          color = colors[bar];
        }
      }
      std::copy(color.begin(), color.end(), pixel); pixel[3] = 255;
    }
  }
  return image;
}
}  // namespace

int main(int argc, char **argv)
{
  std::string backend_name, language = "en", output, width_mode = "wide", view = "text";
  if (argc % 2 != 1) { return 2; }
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string argument = argv[i];
    if (argument == "--gpu-backend") { backend_name = argv[i + 1]; }
    else if (argument == "--lang") { language = argv[i + 1]; }
    else if (argument == "--export") { output = argv[i + 1]; }
    else if (argument == "--width") { width_mode = argv[i + 1]; }
    else if (argument == "--view") { view = argv[i + 1]; }
    else { return 2; }
  }
  if (output.empty() || (language != "en" && language != "zh") ||
      (width_mode != "wide" && width_mode != "narrow") || (view != "text" && view != "png" && view != "create" && view != "sources" && view != "document")) { return 2; }
  const int width = width_mode == "narrow" ? 560 : 1440, height = 1000;
  const bool chinese = language == "zh", png_view = view == "png", sources_view = view == "sources";
  const bool create_view = view == "create" || sources_view;
  const bool document_view = view == "document";
  bridge::test::TempDir directory{"reports-render"};
  bridge::test::ManualLoop loop;
  bridge::ClientOptions options;
  options.python.configured = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
  options.env["PYTHONPATH"] = STK_REPO_ROOT;
  options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
  options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
  options.env["STK_TOKEN_PLAN_API_KEY"] = "";
  options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
  options.executor = loop.executor(); options.strict = options.validate = true;
  std::string error;
  if (create_view) {
    // Keep the real bridge and services. Observe content requests separately so a visually
    // empty widget cannot hide an accidental asset/preview read during form preparation.
    write_text(directory.path() / "observe_content.py", R"PY(
from pathlib import Path
import sys
from suan.desktop_bridge.projects import ProjectSessions
from suan.desktop_bridge.__main__ import main
marker = Path(sys.argv.pop(1))
source_marker = Path(sys.argv.pop(1))
reports = ProjectSessions.reports
contexts = ProjectSessions.contexts
def record_source(action):
    with source_marker.open('a', encoding='utf-8') as output:
        output.write(action + '\n')
def observed_contexts(self, action, params):
    if action == 'list':
        record_source('list')
    return contexts(self, action, params)
ProjectSessions.contexts = observed_contexts
def observed(self, action, params):
    if action in ('asset', 'preview', 'preview_resources', 'export_file'):
        with marker.open('a', encoding='utf-8') as output:
            output.write(action + '\n')
    if action in ('review_sources', 'create'):
        record_source(action)
    return reports(self, action, params)
ProjectSessions.reports = observed
main()
)PY");
    const auto python = bridge::find_python(options.python, error);
    if (!python) { fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1; }
    options.command = {*python, "-u", directory.str() + "/observe_content.py", directory.str() + "/content.calls",
        directory.str() + "/source.calls", "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
  }
  auto client = bridge::Client::create(options);
  if (!client->start(&error) || !client->wait_ready(60)) {
    fprintf(stderr, "FAIL: bridge: %s\n%s", error.c_str(), client->bridge_log().text().c_str()); return 1;
  }
  loop.run_ready();
  gfx::Backend backend;
  if (!gfx::resolve_backend(backend_name, backend, error)) { fprintf(stderr, "FAIL: %s\n", error.c_str()); return 2; }
  gfx::Runtime runtime;
  auto *system = gfx::create_background_system(error);
  if (!system) { fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1; }
  int result = 0;
  {
    gfx::GpuOptions gpu_options; gpu_options.backend = backend;
    auto gpu = gfx::Gpu::create(*system, gpu_options, error);
    if (!gpu) { fprintf(stderr, "FAIL: %s\n", error.c_str()); gfx::dispose_system(); return 1; }
    gfx::set_ui_scale(1);
    app::ShellOptions shell_options;
    shell_options.language = chinese ? "zh_CN" : "en"; shell_options.interactive = false;
    app::AppShell shell(shell_options); shell.layout_path.clear();
    wm::Screen screen; shell.install(screen, nullptr); shell.build_default_layout(screen);
    shell.store().set_bridge(client.get());
    app::BridgeStatus bridge_status(shell.store(), *client, nullptr);
    auto &viewer = shell.store().viewer();
    viewer.prefetch_neighbours = false; viewer.set_auto_evaluate(false);
    auto &jobs = shell.store().jobs(); app::use_gpu_textures(jobs);
    auto &project = shell.store().project();
    try {
      auto call = [&](const std::string &method, Json params) {
        auto reply = std::make_shared<std::optional<bridge::Result<Json>>>();
        auto future = client->call(method, params);
        future.then([reply](auto value) { *reply = std::move(value); });
        const bool done = loop.pump_until([&] { return reply->has_value(); }, 30);
        if (!done) { future.cancel(); }
        require(done, method + " timeout");
        require(reply->value().ok(), method + ": " + (reply->value() ? "" : reply->value().error().describe()));
        return reply->value().value();
      };
      project.sync();
      require(project.create(directory.str() + "/project", chinese ? "冻结报告示例" : "Frozen report example"), "create project");
      require(loop.pump_until([&] { return project.loaded() && !project.busy(); }, 30), "load project");
      const auto handle = project.project()->handle;
      const auto folder = directory.path() / "project";
      const std::string markdown = chinese ?
          "# 冻结报告\n\n这是保存的 Markdown 原文，尚未渲染。\n\n"
          "## 示例数据\n\n| 样本 | 温度 / K |\n| --- | --- |\n| A | 300 |\n| B | 325 |\n\n"
          "![示例图](plot.png)\n\n仅使用合成数据；没有执行模拟或分析。\n" :
          "# Frozen report\n\nSaved Markdown source; rendering has not been applied.\n\n"
          "## Fixture values\n\n| Sample | Temperature / K |\n| --- | --- |\n| A | 300 |\n| B | 325 |\n\n"
          "![Example plot](plot.png)\n\nSynthetic fixture only; no simulation or analysis was run.\n";
      write_text(folder / "report.md", markdown);
      io::write_png(folder / "plot.png", plot_fixture());
      write_text(folder / "paper.pdf", "%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n");
      const auto indexed = call("project.files.index", {{"handle", handle}, {"expected_revision", 0},
          {"paths", Json::array({core::path_to_utf8(folder / "report.md"), core::path_to_utf8(folder / "plot.png"),
                                core::path_to_utf8(folder / "paper.pdf")})}});
      const auto ids = indexed.at("record_ids");
      const auto captured = call("project.snapshots.capture", {{"handle", handle}, {"record_ids", ids}, {"expected_revision", 1}});
      call("project.apply", {{"handle", handle}, {"expected_revision", 2}, {"commands", Json::array({
          {{"op", "create_table"}, {"id", kTable}, {"name", chinese ? "示例参数" : "Fixture parameters"}},
          {{"op", "add_field"}, {"id", kField}, {"table_id", kTable}, {"name", "T"}, {"type", "number"}, {"unit", "K"}},
          {{"op", "add_record"}, {"id", kRow}, {"table_id", kTable}},
          {{"op", "set_cell"}, {"table_id", kTable}, {"record_id", kRow}, {"field_id", kField}, {"value", 300}}
      })}});
      call("project.contexts.capture", {{"handle", handle}, {"context_id", kContext}, {"table_id", kTable},
          {"record_ids", Json::array({kRow})}, {"field_ids", Json::array({kField})}, {"expected_revision", 3},
          {"title", chinese ? "保存的参数" : "Saved parameters"}});
      call("project.reports.create", {{"handle", handle}, {"report_id", kReport},
          {"name", chinese ? "温度比较 · 冻结资产" : "Temperature comparison · frozen assets"},
          {"snapshot_id", captured.at("snapshot").at("id")}, {"entry_record_id", ids.at(0)},
          {"assets", Json::array({{{"record_id", ids.at(0)}, {"path", "report.md"}},
                                 {{"record_id", ids.at(1)}, {"path", "plot.png"}},
                                 {{"record_id", ids.at(2)}, {"path", "paper.pdf"}}})},
          {"sources", Json::array({{{"kind", "context"}, {"id", kContext}}})}, {"expected_revision", 3}});
      const auto saved = call("project.reports.get", {{"handle", handle}, {"report_id", kReport}}).at("report");
      for (const char *name : {"report.md", "plot.png", "paper.pdf"}) {
        require(fs::remove(folder / name), std::string("remove live fixture ") + name);
      }
      project.refresh();
      require(loop.pump_until([&] { return project.loaded() && !project.busy(); }, 30), "refresh report revision");
      require(project.project()->revision == 4, "exact captured revision");
      const auto history = call("project.history", {{"handle", handle}});
      const auto shown = std::make_shared<io::Payload>(io::read_stkp(
          std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
      viewer.open_payload(shown, "Existing synthetic result");
      const auto viewer_state = viewer.save_workspace_state();
      const auto camera_serial = viewer.camera_serial(), payload_serial = viewer.payload_serial();
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a4"));
      require(area && area->set_tabs({app::kEditorReports, app::kEditorPython}, 1), "Reports and hidden Python tabs");
      area->set_sidebar_open(false); area->set_toolbar_open(false); screen.set_maximized(area);
      wm::DrawContext context;
      context.ui_scale = 1; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
      gfx::Image image;
      auto frame = [&] {
        screen.run_deferred(); context.now += 0.01;
        require(gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error), error);
      };
      auto widget = [&](const char *key) { return screen.ui()->find(key); };
      auto wait = [&](const std::function<bool()> &predicate, const char *description) {
        require(loop.pump_until([&] { frame(); return predicate(); }, 45), description);
      };
      int clicks = 0, scroll_steps = 0;
      auto fully_visible = [width, height](const ui::Widget *item) {
        if (!item) { return false; }
        const auto visible = item->rect.intersect(item->clip).intersect(ui::Rect{0, 0, float(width), float(height)});
        return !visible.empty() && visible.h >= item->rect.h - 1 && visible.w >= item->rect.w - 1;
      };
      auto scroll_to = [&](const char *key) {
        frame();
        const auto main = area->find_region(app::EditorArea::kMain)->ui_rect();
        for (int step = 0; step < 80 && !fully_visible(widget(key)); ++step) {
          const auto *item = widget(key);
          require(item, std::string("missing scroll target: ") + key);
          // Use the main region edge, outside inner virtual lists, so its scrollbar receives
          // the real wheel event. Never change production layout or stored scroll offsets.
          screen.ui()->handle_event(ui::Event::wheel({main.x1() - 2, main.cy()},
              item->rect.cy() > main.cy() ? -1.0f : 1.0f, context.now + 0.001));
          ++scroll_steps; frame();
        }
        require(fully_visible(widget(key)), std::string("control cannot fit in viewport: ") + key);
      };
      auto click = [&](const char *key, int row = -1) {
        if (create_view || document_view) { scroll_to(key); }
        frame(); const auto *item = widget(key);
        require(item && item->enabled, std::string("control unavailable: ") + key);
        ui::Vec2 point{item->rect.cx(), item->rect.cy()};
        if (row >= 0) {
          require(item->list && row < item->list->count, std::string("list row unavailable: ") + key);
          point.y = item->rect.y + screen.ui()->style().pixel + screen.ui()->style().unit * (float(row) + 0.5f);
        }
        require(item->rect.intersect(item->clip).contains(point), std::string("control clipped: ") + key);
        screen.ui()->handle_event(ui::Event::mouse_down(point, ui::MouseButton::Left, context.now + 0.001));
        screen.ui()->handle_event(ui::Event::mouse_up(point, ui::MouseButton::Left, context.now + 0.002));
        ++clicks; frame();
      };
      frame(); click("python_source");
#ifdef __APPLE__
      constexpr auto primary = ui::MOD_SUPER;
#else
      constexpr auto primary = ui::MOD_CTRL;
#endif
      const std::string draft = "print('keep this unsaved draft')";
      screen.ui()->handle_event(ui::Event::key_down(ui::Key::A, primary, context.now + 0.001));
      screen.ui()->handle_event(ui::Event::text_input(draft, context.now + 0.002)); frame();
      click("python_output_open"); // Commit the real text edit without executing it.
      require(area->tab(1).has_unsaved_changes(), "Python draft must be unsaved before report interaction");
      const auto draft_state = area->tab(1).save_workspace_state();
      require(draft_state.at("source") == draft && draft_state.at("baseline") != draft, "exact Python draft");
      area->set_active_tab(0); frame(); clicks = scroll_steps = 0;
      wait([&] { const auto *item = widget("reports_list"); return item && item->enabled && item->list && item->list->count == 1; }, "report summary loaded");
      require(!widget("reports_text_page") && !widget("reports_image"), "listing must not read report assets");
      auto source_calls = [&](const std::string &action) {
        std::ifstream input(directory.path() / "source.calls");
        size_t count = 0; std::string line;
        while (std::getline(input, line)) { count += line == action; }
        return count;
      };
      const auto initial_creates = source_calls("create");
      if (create_view) {
        require(source_calls("list") == 0 && source_calls("review_sources") == 0,
            "opening Reports must not list or review creation sources");
        click("reports_create_panel");
        click("reports_create_snapshots");
        wait([&] { const auto *item = widget("reports_create_snapshot_list");
          return item && item->enabled && item->list && item->list->count == 1; }, "snapshot summary page loaded");
        click("reports_create_snapshot_list", 0);
        wait([&] { const auto *item = widget("reports_create_title"); return item && item->enabled; }, "selected snapshot reviewed");
        const std::string title = chinese ? "温度比较 · 新报告草稿" : "Temperature comparison · new report draft";
        click("reports_create_title");
        screen.ui()->handle_event(ui::Event::text_input(title, context.now + 0.001));
        screen.ui()->handle_event(ui::Event::key_down(ui::Key::Enter, 0, context.now + 0.002)); frame();
        click("reports_create_files", 0);
        click("reports_create_include");
        wait([&] { const auto *item = widget("reports_create_entry"); return item && item->enabled; }, "entry selection enabled");
        click("reports_create_entry");
        wait([&] { const auto *item = widget("reports_create_submit"); return item && item->enabled; }, "creation form ready");
        scroll_to("reports_create_submit");
        const auto state = area->editor().save_workspace_state();
        require(state.at("version") == 2 && state.contains("create_draft"), "creation workspace contains its draft");
        const auto &creation = state.at("create_draft");
        require(creation.at("name") == title && creation.at("project_id") == project.project()->id &&
            creation.at("snapshot_id") == captured.at("snapshot").at("id") &&
            creation.at("snapshot_sha256") == captured.at("snapshot").at("sha256") &&
            creation.at("assets").size() == 1 && creation.at("assets")[0].at("record_id") == ids.at(0) &&
            creation.at("assets")[0].at("path") == "report.md" && creation.at("entry_record_id") == ids.at(0) &&
            creation.at("pending").is_null(), "unsaved form matches the exact frozen snapshot, selected file and entry");
        require(area->editor().has_unsaved_changes(), "creation form must remain an unsaved draft");
        for (const char *key : {"reports_create_title", "reports_create_files", "reports_create_include", "reports_create_path",
                               "reports_create_entry", "reports_create_asset_review", "reports_create_submit"}) {
          require(fully_visible(widget(key)), std::string("creation control must be fully visible: ") + key);
        }
        require(widget("reports_create_title")->string.value() == title &&
            widget("reports_create_path")->string.value() == "report.md" &&
            widget("reports_create_include")->boolean.value() && !widget("reports_create_entry")->enabled,
            "visible title, virtual path, checked file and selected entry");
        const auto *files = widget("reports_create_files"), *review = widget("reports_create_asset_review");
        require(files->list && files->list->count == 3 && files->list->selected.value() == 0 &&
            files->list->text(0).starts_with("☑ ") && files->list->text(0).find("report.md") != std::string::npos &&
            review->list && review->list->count == 1 && review->list->text(0).starts_with("▶ report.md"),
            "selected filename and unique entry must be visible");
        for (const auto *list : {files, review}) {
          require(screen.ui()->measurer().width(list->list->text(0), screen.ui()->style().font) +
              2 * screen.ui()->style().text_margin <= list->rect.w, "selected asset text must fit without horizontal clipping");
        }
        require(!widget("reports_image") && !widget("reports_text_page") && !fs::exists(directory.path() / "content.calls"),
                "creation preparation must not read or render asset content");
        require(clicks == 7, "fixed-start creation form preparation requires seven mouse clicks; Create is not clicked");
        if (sources_view) {
          // Five more real clicks: expand, explicitly list, select row, add, explicitly review.
          // No workspace load, setter injection or direct callback is used to prepare this scene.
          click("reports_create_sources_panel");
          require(source_calls("list") == 0 && source_calls("review_sources") == 0,
              "expanding the sources panel must not read metadata");
          click("reports_create_sources_load");
          wait([&] { const auto *item = widget("reports_create_source_candidates");
            return item && item->enabled && item->list && item->list->count == 1; }, "explicit context list loaded");
          click("reports_create_source_candidates", 0);
          click("reports_create_source_add");
          require(widget("reports_create_submit") && !widget("reports_create_submit")->enabled,
              "selecting a source must require explicit review before creation");
          require(source_calls("list") == 1 && source_calls("review_sources") == 0,
              "selection reads exactly one source page and does not review automatically");
          const auto selected = area->editor().save_workspace_state().at("create_draft");
          const auto expected_sources = Json::array({{{"kind", "context"}, {"id", kContext}}});
          require(selected.at("sources") == nlohmann::json(expected_sources) && selected.at("pending").is_null() &&
              !selected.contains("reviewed_sources"), "only exact source selectors belong in the unsaved workspace");
          click("reports_create_sources_review");
          wait([&] { const auto *item = widget("reports_create_submit"); return item && item->enabled; },
              "complete selected provenance reviewed");
          require(source_calls("list") == 1 && source_calls("review_sources") == 1,
              "explicit review must make exactly one request without reloading the list");
          scroll_to("reports_create_source_detail_next");
          for (const char *key : {"reports_create_sources_selected", "reports_create_source_remove",
                                 "reports_create_sources_review", "reports_create_source_detail_previous",
                                 "reports_create_source_detail_next"}) {
            require(fully_visible(widget(key)), std::string("reviewed source control must be visible: ") + key);
          }
          const auto *sources = widget("reports_create_sources_selected");
          require(sources->list && sources->list->count == 1 && sources->list->selected.value() == 0 &&
              sources->list->text(0).find(kContext) != std::string::npos,
              "selected source kind and complete stable UUID remain visible");
          require(screen.ui()->measurer().width(sources->list->text(0), screen.ui()->style().font) +
              2 * screen.ui()->style().text_margin <= sources->rect.w,
              "selected source UUID must fit without horizontal clipping");
          bool reviewed_notice = false, exact_source = false, page_label = false;
          for (const auto &block : screen.ui()->blocks()) {
            for (const auto &item : block->widgets()) {
              if (!fully_visible(&item)) { continue; }
              reviewed_notice |= item.text == shell.store().tr("reports.create.sources.reviewed");
              page_label |= item.text == std::string(shell.store().tr("reports.create.sources.details")) + "1 / 1";
              if (!item.text.starts_with("{")) { continue; }
              const auto detail = Json::parse(item.text, nullptr, false);
              // The production paragraph contains the complete single-page frozen descriptor,
              // including values, omissions, diagnostics and SHA, rather than a mock summary.
              exact_source |= !detail.is_discarded() &&
                  nlohmann::json(detail) == nlohmann::json(saved.at("manifest").at("sources").at(0));
            }
          }
          require(reviewed_notice && page_label && exact_source,
              "the screenshot must show the complete reviewed provenance and its review notice");
          require(!widget("reports_create_source_detail_previous")->enabled &&
              !widget("reports_create_source_detail_next")->enabled,
              "the complete small fixture occupies one source-detail page");
          require(area->editor().save_workspace_state().at("create_draft") == selected,
              "reviewing sources must not persist values or alter the creation draft");
          require(clicks == 12, "fixed-start source preparation requires twelve clicks; Create is not clicked");
        }
      }
      else {
        click("reports_list", 0);
        wait([&] { const auto *item = widget("reports_assets"); return item && item->enabled && item->list && item->list->count == 3; }, "frozen report manifest loaded");
        const auto selected_state = area->editor().save_workspace_state();
        require(selected_state.at("report_id") == kReport && selected_state.at("source_sha256") == saved.at("source_sha256"), "selected manifest identity");
        require(!widget("reports_text_page") && !widget("reports_image"), "selection must not read report assets");
        if (document_view) {
          click("reports_preview");
          wait([&] { return widget("reports_document_viewport") != nullptr; }, "explicit preparation creates the production document viewport");
          const auto *viewport = widget("reports_document_viewport");
          require(viewport->type == ui::WidgetType::NativeViewport && fully_visible(viewport),
              "dedicated native viewport must fit in the actual resolved reading layout");
          for (const char *key : {"reports_document_source", "reports_document_prepare", "reports_document_close",
                                 "reports_document_focus", "reports_document_return_focus", "reports_document_after"}) {
            require(fully_visible(widget(key)), std::string("reading control must fit: ") + key);
          }
          require(!widget("reports_text_page") && !widget("reports_image"), "reading viewport is independent of source/PNG controls");
          require(!widget("reports_document_focus")->enabled,
              "headless layout must not claim a native browser is attached or ready for focus");
          for (const auto &command : screen.ui()->draw_list().cmds) {
            require(command.type != ui::CmdType::Image, "headless document viewport must not fake browser pixels with a GPU image");
          }
          require(area->editor().save_workspace_state() == selected_state,
              "transient native reading state must not enter the saved workspace");
          require(clicks == 2, "fixed report-list start to prepared reading viewport requires two clicks");
        }
        else {
        click("reports_sources");
        const auto *source = widget("reports_source_list");
        require(source && source->list && source->list->count == 1, "frozen provenance visible");
        const auto source_text = source->list->text(0);
        require(source_text.find(kContext) != std::string::npos, "complete provenance UUID");
        require(screen.ui()->measurer().width(source_text, screen.ui()->style().font) + 2 * screen.ui()->style().text_margin <= source->rect.w,
            "provenance UUID must fit without horizontal clipping");
        if (png_view) { click("reports_assets", 1); }
        click("reports_read_asset");
        wait([&] {
          const auto *read = widget("reports_read_asset");
          const auto *content = widget(png_view ? "reports_image" : "reports_text_page");
          return read && read->enabled && content && (!png_view || content->image.texture != 0);
        }, "explicit frozen content read completed");
        const auto expected_path = png_view ? "plot.png" : "report.md";
        require(area->editor().save_workspace_state().at("asset_path") == expected_path, "selected asset identity");
        const auto *assets = widget("reports_assets");
        require(assets && assets->list && assets->list->text(png_view ? 1 : 0).find(expected_path) != std::string::npos,
            "asset name remains visible");
        bool raw_notice = false, exact_source = false;
        for (const auto &block : screen.ui()->blocks()) {
          for (const auto &item : block->widgets()) {
            const auto visible = item.rect.intersect(item.clip);
            if (visible.empty()) { continue; }
            const bool fully_visible = visible.h >= item.rect.h - 1 && visible.w >= item.rect.w - 1;
            raw_notice |= fully_visible && item.text == shell.store().tr("reports.raw_text");
            exact_source |= fully_visible && item.text == markdown;
          }
        }
        if (!png_view) { require(raw_notice && exact_source, "full raw Markdown and explicit unrendered notice"); }
        else {
          const auto *preview = widget("reports_image");
          require(preview && preview->image.texture && preview->image.width == 480 && preview->image.height == 200,
              "verified PNG uploaded as a real GPU texture");
          const auto visible = preview->rect.intersect(preview->clip);
          require(visible.h >= preview->rect.h - 1 && visible.w >= preview->rect.w - 1, "PNG must fit in the viewport");
          size_t blue_pixels = 0;
          for (int y = std::max(0, int(std::ceil(visible.y))); y < std::min(height, int(visible.y1())); ++y) {
            for (int x = std::max(0, int(std::ceil(visible.x))); x < std::min(width, int(visible.x1())); ++x) {
              const auto *pixel = image.px(x, y);
              blue_pixels += pixel[2] > int(pixel[0]) + 35 && pixel[2] > int(pixel[1]) + 35 && pixel[3] > 200;
            }
          }
          require(blue_pixels > 100, "screenshot contains the frozen PNG's blue bars");
        }
        }
      }
      require(viewer.base_payload() == shown && viewer.payload_serial() == payload_serial &&
          viewer.camera_serial() == camera_serial && viewer.save_workspace_state() == viewer_state &&
          viewer.evaluations_started() == 0, "report interaction must preserve Viewer state");
      require(area->tab(1).has_unsaved_changes() && area->tab(1).save_workspace_state() == draft_state &&
          shell.store().scripts().history().empty(), "report interaction must preserve the hidden, unexecuted Python draft");
      require(call("project.history", {{"handle", handle}}) == history, "reading or preparing an unsaved report must not edit project history");
      for (const char *method : {"project.runs.list", "project.analysis_runs.list", "project.workflow_runs.list"}) {
        require(call(method, {{"handle", handle}}).at("runs").empty(), "report interaction must not prepare or execute a run");
      }
      if (create_view) {
        require(!fs::exists(directory.path() / "content.calls"), "no late asset/preview/export content request");
        require(source_calls("create") == initial_creates, "preparing the source scene must not create a report");
        require(source_calls("list") == size_t(sources_view) && source_calls("review_sources") == size_t(sources_view),
            "settling and screenshot preparation must not trigger additional source reads");
      }
      require(client->stats().schema_violations == 0, "bridge schema violations");
      require(gfx::png_write(output, image), "write report screenshot");
      printf("wrote %s (%dx%d, %s, %s, %s; report clicks=%d; wheel steps=%d; frozen sources; unchanged Viewer/Python draft)\n",
          output.c_str(), width, height, language.c_str(), view.c_str(), gpu->backend_name(), clicks, scroll_steps);
    }
    catch (const std::exception &exception) {
      fprintf(stderr, "FAIL: %s\n%s", exception.what(), client->bridge_log().text().c_str()); result = 1;
    }
    // ReportsEditor owns its uploaded texture. Destroy it while a GPU context is current.
    gfx::Image cleanup;
    if (!gfx::render_offscreen(8, 8, [&] { screen.clear(); jobs.clear_preview(); }, cleanup, error)) {
      fprintf(stderr, "FAIL: cleanup: %s\n", error.c_str()); result = 1;
    }
    jobs.create_texture = nullptr; jobs.free_texture = nullptr;
    viewer.close(); shell.store().set_bridge(nullptr); client->close(); loop.run_ready();
  }
  gfx::dispose_system();
  return result;
}
