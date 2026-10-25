/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_state.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/table_workbench.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "stk/io/png.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iterator>

namespace stk::app {
namespace {
using io::Json;
const std::string samples = "c1111111-1111-4111-8111-111111111111";
const std::string temperature = "c2222222-2222-4222-8222-222222222222";
const std::string counter = "c3333333-3333-4333-8333-333333333333";
const std::string accepted = "c4444444-4444-4444-8444-444444444444";
const std::string phase = "c5555555-5555-4555-8555-555555555555";
const std::string evidence = "c6666666-6666-4666-8666-666666666666";
const std::string row_a = "c7777777-7777-4777-8777-777777777777";
const std::string row_b = "c8888888-8888-4888-8888-888888888888";
const std::string row_c = "c9999999-9999-4999-8999-999999999999";
const std::string dry = "caaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const std::string batches = "cbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const std::string batch_label = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const std::string batch_row = "cddddddd-dddd-4ddd-8ddd-dddddddddddd";
const std::string wet = "d1111111-1111-4111-8111-111111111111";
const std::string board_view = "d2222222-2222-4222-8222-222222222222";
const std::string observed_date = "d3333333-3333-4333-8333-333333333333";
const std::string observed_url = "d4444444-4444-4444-8444-444444444444";
const std::string tags_field = "d5555555-5555-4555-8555-555555555555";

std::vector<Json> json_roundtrip_values()
{
  return {Json("123"), Json("true"), Json("false"), Json("null"), Json("ordinary scientific text"),
          Json("中文、\"引号\"、\\路径\n第二行\t制表符"), Json(""), Json("[1,true]"), Json("{\"id\":7}"),
          Json(nullptr), Json(true), Json(INT64_MAX), Json(INT64_MIN), Json(1.25),
          Json::object({{"count", INT64_MAX}, {"label", "true"}, {"nested", Json::array({nullptr, "null", false})}}),
          Json::array({1, "123", true, nullptr, Json::object({{"label", "科学数据"}})}),
          Json(std::string(5000, 'x') + "\nfull JSON string")};
}

class TableWorkbenchEditorPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"table-workbench-editor"};
  wmtest::AppFixture f{"en", 1, 1440, 1200};
  ui::MemoryClipboard clipboard;
  std::unique_ptr<bridge::Client> client;
  std::shared_ptr<const io::Payload> existing_payload;
  uint64_t payload_serial = 0, camera_serial = 0;
  double event_time = 500;
  int clicks = 0;
  ProjectState &project() { return f.shell->store().project(); }
  ViewerState &viewer() { return f.shell->store().viewer(); }
  EditorArea &area() { return f.area("a4"); }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }
  std::string card_key(const char *key) const { return "card" + row_a + "/" + key; }
  const ui::Widget *card_widget(const char *key) { return widget(card_key(key).c_str()); }
  bool has_text_prefix(const std::string &prefix)
  {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) {
        if (item.text.starts_with(prefix)) { return true; }
      }
    }
    return false;
  }
  void frame() { f.screen.run_deferred(); f.drv->frame(); }
  bool pump(const std::function<bool()> &predicate)
  {
    return loop.pump_until([&] { frame(); return predicate(); }, 30);
  }
  void settled(int expected_rows = 3)
  {
    ASSERT_TRUE(pump([&] {
      const auto *grid = widget("records");
      return !project().busy() && grid && grid->table && grid->table->rows == expected_rows;
    }));
    ASSERT_TRUE(project().error().empty()) << project().error();
  }
  void send(ui::Event event)
  {
    event.time = event_time += 1;
    f.screen.ui()->handle_event(event);
    frame();
  }
  void point(ui::Vec2 point)
  {
    send(ui::Event::mouse_down(point));
    send(ui::Event::mouse_up(point));
    ++clicks;
  }
  void click(const char *key)
  {
    for (int attempt = 0; attempt < 32; ++attempt) {
      const auto *candidate = widget(key);
      ASSERT_NE(candidate, nullptr) << key;
      if (candidate->clip.contains({candidate->rect.cx(), candidate->rect.cy()})) { break; }
      ASSERT_FALSE(candidate->clip.empty()) << key;
      const auto clip = candidate->clip;
      const auto unit = f.screen.ui()->style().unit;
      const float padding = std::min(.25f * unit, .25f * clip.w);
      const float x = std::clamp(candidate->rect.cx(), clip.x + padding, clip.x1() - padding);
      send(ui::Event::wheel({x, clip.cy()}, candidate->rect.cy() < clip.y ? 3 : -3));
    }
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    ASSERT_TRUE(w->enabled) << key;
    ASSERT_TRUE(w->clip.contains({w->rect.cx(), w->rect.cy()})) << key;
    point({w->rect.cx(), w->rect.cy()});
  }
  void action(const char *key)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    ASSERT_TRUE(w->enabled) << key;
    ASSERT_TRUE(w->on_click) << key;
    w->on_click(); frame();
  }
  void cell(int row, int column)
  {
    const auto *w = widget("records");
    ASSERT_NE(w, nullptr);
    ASSERT_TRUE(w->table && w->table->grid);
    const auto &style = f.screen.ui()->style();
    const auto width = [&](int c) {
      const auto &field = w->table->columns[size_t(c)];
      float value = field.width;
      if (w->table->column_width) {
        const auto configured = w->table->column_width(field.key);
        if (configured && std::isfinite(*configured) && *configured >= 1.5f && *configured <= 10000) {
          value = *configured;
        }
      }
      return std::round(value * style.unit);
    };
    float x = w->rect.x + style.pixel;
    for (int c = 0; c < column; ++c) { x += width(c); }
    x += .5f * width(column);
    point({x, w->rect.y + style.pixel + (row + 1.5f) * style.unit * w->table->row_height});
  }
  void select(int row, int column)
  {
    const auto *w = widget("records");
    ASSERT_NE(w, nullptr);
    ASSERT_TRUE(w->table && w->table->grid);
    w->table->grid->selection.assign({{row, column}, {row, column}});
    frame();
  }
  void assign(const char *key, const std::string &value)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    w->string.assign(value); frame();
  }
  void index(const char *key, int value)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    w->index.assign(value); frame();
  }
  void choose(const char *key, int value)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
    const auto option = "popup/" + std::to_string(value);
    ASSERT_NO_FATAL_FAILURE(click(option.c_str()));
  }
  void type(const char *key, const std::string &text)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
    send(ui::Event::key_down(ui::Key::A, ui::MOD_CTRL));
    send(ui::Event::text_input(text));
    send(ui::Event::key_down(ui::Key::Enter));
  }
  Json choice_options() const
  {
    return {{"version", 1}, {"choices", Json::array({
        {{"id", dry}, {"label", "Dry"}, {"color", "#123456"}},
        {{"id", wet}, {"label", "Wet"}, {"color", "#234567"}}})}};
  }
  void add_record_fields()
  {
    ASSERT_TRUE(project().apply(Json::array({
      {{"op", "set_field_schema"}, {"id", phase}, {"type", "single_select"}, {"unit", nullptr}, {"options", choice_options()}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", observed_date}, {"name", "Observed date"}, {"type", "date"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", observed_url}, {"name", "Evidence URL"}, {"type", "url"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", tags_field}, {"name", "Tags"}, {"type", "multi_select"}, {"options", choice_options()}},
    })));
    ASSERT_NO_FATAL_FAILURE(settled());
  }
  void show_board(bool hide_fields = false)
  {
    Json columns = Json::array();
    for (const auto &f : project().table()->fields) {
      columns.push_back({{"field_id", f.id}, {"width", 160}, {"hidden", hide_fields && f.id != temperature}});
    }
    ASSERT_TRUE(project().apply(Json::array({
      {{"op", "put_table_view"}, {"id", board_view}, {"table_id", samples}, {"name", "Sample status"},
       {"definition", {{"version", 1}, {"kind", "board"}, {"group_field_id", phase}, {"columns", columns}}}}
    })));
    ASSERT_NO_FATAL_FAILURE(settled());
    ASSERT_TRUE(pump([&] { const auto *tabs = widget("table_views"); return tabs && tabs->items.size() == 2; }));
    const auto *tabs = widget("table_views");
    point({tabs->rect.x + tabs->rect.w * .75f, tabs->rect.cy()});
    ASSERT_TRUE(pump([&] { return !project().busy() && !widget("records") && card_widget("table_board_state"); }));
  }
  void edit_field(int column)
  {
    const auto *grid = widget("records");
    ASSERT_NE(grid, nullptr);
    ASSERT_TRUE(grid->table && grid->table->column_menu);
    const auto menu = grid->table->column_menu(column);
    const auto label = std::string(f.shell->store().tr("table.edit_field"));
    const auto edit = std::find_if(menu.begin(), menu.end(), [&](const auto &entry) { return entry.text == label; });
    ASSERT_NE(edit, menu.end());
    ASSERT_TRUE(edit->enabled && edit->action);
    edit->action(); frame();
    ASSERT_NE(widget("field_name"), nullptr);
  }
  void expect_viewer()
  {
    EXPECT_EQ(f.area("a2").editor().type().id, kEditorViewer);
    EXPECT_EQ(f.screen.maximized(), nullptr);
    EXPECT_EQ(viewer().base_payload(), existing_payload);
    EXPECT_EQ(viewer().payload_serial(), payload_serial);
    EXPECT_EQ(viewer().camera_serial(), camera_serial);
    EXPECT_EQ(viewer().evaluations_started(), 0);
  }
  void link_attachment(const std::filesystem::path &path)
  {
    ASSERT_TRUE(project().index_files({core::path_to_utf8(path)}));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    ASSERT_TRUE(project().selected_file());
    const Json reference = {{"version", 1}, {"project_id", project().project()->id},
                            {"kind", "file"}, {"id", project().record_id()}};
    ASSERT_TRUE(project().apply(Json::array({
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", evidence}, {"value", reference}}
    })));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    project().select_table(samples); project().select_record(row_a);
    ASSERT_NO_FATAL_FAILURE(settled());
    select(0, 5);
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    ui::ContextConfig ui_config;
    ui_config.measurer = &f.measurer;
    ui_config.catalog = &f.shell->store().catalog();
    ui_config.clipboard = &clipboard;
    f.screen.set_ui_config(ui_config);
    frame();
    bridge::ClientOptions options;
    options.python.configured = python;
    options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge";
    options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready();
    f.shell->store().set_bridge(client.get());
    project().sync();
    ASSERT_TRUE(project().create(dir.str() + "/project", "Synthetic research table"));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", samples}, {"name", "Synthetic PET samples"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", temperature}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", counter}, {"name", "Counter"}, {"type", "integer"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", accepted}, {"name", "Accepted"}, {"type", "boolean"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", phase}, {"name", "State"}, {"type", "single_select"},
       {"options", {{"version", 1}, {"choices", Json::array({{{"id", dry}, {"label", "Dry"}, {"color", "#123456"}}})}}}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", evidence}, {"name", "Evidence"}, {"type", "object"},
       {"options", {{"version", 1}, {"kinds", Json::array({"record", "file"})}}}},
      {{"op", "add_record"}, {"table_id", samples}, {"id", row_a}},
      {{"op", "add_record"}, {"table_id", samples}, {"id", row_b}},
      {{"op", "add_record"}, {"table_id", samples}, {"id", row_c}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", temperature}, {"value", 300}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_b}, {"field_id", temperature}, {"value", nullptr}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_c}, {"field_id", temperature}, {"value", 350}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", counter}, {"value", INT64_MAX}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", accepted}, {"value", false}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", phase}, {"value", dry}},
      {{"op", "create_table"}, {"id", batches}, {"name", "Synthetic batches"}},
      {{"op", "add_field"}, {"table_id", batches}, {"id", batch_label}, {"name", "Label"}, {"type", "text"}},
      {{"op", "add_record"}, {"table_id", batches}, {"id", batch_row}},
      {{"op", "set_cell"}, {"table_id", batches}, {"record_id", batch_row}, {"field_id", batch_label}, {"value", "Synthetic B"}},
    })));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    project().select_table(samples);
    project().select_record(row_a);
    ASSERT_NO_FATAL_FAILURE(settled());
    existing_payload = std::make_shared<io::Payload>(io::read_stkp(
        std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    viewer().open_payload(existing_payload, "Existing public synthetic result");
    frame();
    payload_serial = viewer().payload_serial();
    camera_serial = viewer().camera_serial();
  }
  void TearDown() override
  {
    if (existing_payload) { expect_viewer(); }
    project().attach(nullptr);
    f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(TableWorkbenchEditorPython, QueryRecordsRenderAndSortWithoutLookingUpSharedSnapshotRows)
{
  std::optional<bridge::Result<Json>> snapshot;
  client->project_snapshot(project().project()->handle).then([&](auto value) { snapshot = std::move(value); });
  ASSERT_TRUE(pump([&] { return snapshot.has_value(); }));
  ASSERT_TRUE(snapshot->ok());
  auto partial = snapshot->value();
  partial["tables"][0]["records"] = Json::array({partial["tables"][0]["records"][0]});
  const auto info = project().project();
  ASSERT_TRUE(project().adopt_workspace_project(info, partial, samples, row_a));
  ASSERT_EQ(project().table()->records.size(), 1u);
  // A fresh editor must read its own page, not inherit the previous editor's cached query.
  ASSERT_TRUE(area().add_tab(kEditorTable));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_NE(widget("records"), nullptr);
  EXPECT_EQ(widget("records")->table->cell(2, 1), "350");
  EXPECT_EQ(widget("records")->table->cell(0, 2), "9223372036854775807");
  const auto old_cell = widget("records")->table->cell;
  widget("records")->table->on_sort(1, false);
  frame();
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_TRUE(old_cell(0, 1).empty());
  EXPECT_EQ(widget("records")->table->cell(0, 1), "350");
  EXPECT_EQ(widget("records")->table->cell(1, 1), "300");
  select(1, 1);
  action("table_details");
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "300");
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().project()->revision, info->revision);
  EXPECT_EQ(project().table()->records.size(), 1u);
  // The first displayed row is absent from the shared cache. Selecting it supplies only
  // that verified record to the shared detail editor, without hydrating the whole table.
  const int before = clicks;  // Sorted grid and record details already visible.
  cell(0, 1);
  EXPECT_EQ(clicks - before, 1);
  ASSERT_EQ(project().record_id(), row_c);
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "350");
  EXPECT_EQ(project().table()->records.size(), 2u);
  select(2, 1);
  EXPECT_EQ(project().record_id(), row_b);
  EXPECT_EQ(project().table()->records.size(), 2u);
  EXPECT_TRUE(std::none_of(project().table()->records.begin(), project().table()->records.end(),
      [](const auto &record) { return record.id == row_c; }));
  select(1, 1);
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().table()->records.size(), 1u);
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, AttachmentTextNeedsTwoClicksFromSelectedCellAndNeverRunsMarkup)
{
  const auto path = dir.path() / "project" / "public-note.md";
  const std::string text = "# Public synthetic note\n<script>never executed</script>\n";
  { std::ofstream out(path, std::ios::binary); out << text; }
  ASSERT_NO_FATAL_FAILURE(link_attachment(path));
  const auto revision = project().project()->revision;
  const int before = clicks;
  click("table_details");
  click("table_attachment_preview");
  ASSERT_TRUE(pump([&] { return has_text_prefix(text); }));
  EXPECT_EQ(clicks - before, 2);
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table_id(), samples); EXPECT_EQ(project().record_id(), row_a);
  expect_viewer();
  click("table_detail_close");
  EXPECT_FALSE(has_text_prefix(text));
  click("table_details");
  EXPECT_FALSE(has_text_prefix(text)) << "reopening details must not read attachment bytes implicitly";
}

TEST_F(TableWorkbenchEditorPython, AttachmentPngDecodesPixelsAndReleasesItsOwnTexture)
{
  const auto path = dir.path() / "project" / "public-image.png";
  io::Image expected(2, 2);
  expected.pixels = {255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 0, 128};
  io::write_png(path, expected);
  ASSERT_NO_FATAL_FAILURE(link_attachment(path));
  struct TextureAudit { int created = 0, freed = 0; io::Image image; };
  const auto audit = std::make_shared<TextureAudit>();
  auto &jobs = f.shell->store().jobs();
  jobs.create_texture = [audit](const io::Image &image) {
    ++audit->created; audit->image = image; return uint64_t(123);
  };
  jobs.free_texture = [audit](uint64_t texture) { EXPECT_EQ(texture, 123u); ++audit->freed; };
  const auto revision = project().project()->revision;
  click("table_details"); click("table_attachment_preview");
  ASSERT_TRUE(pump([&] { return widget("table_attachment_image") != nullptr; }));
  EXPECT_EQ(audit->created, 1); EXPECT_EQ(audit->freed, 0);
  EXPECT_EQ(audit->image.width, 2u); EXPECT_EQ(audit->image.height, 2u);
  EXPECT_EQ(audit->image.pixels, expected.pixels);
  frame(); EXPECT_EQ(audit->created, 1);
  EXPECT_EQ(project().project()->revision, revision);
  expect_viewer();
  click("table_detail_close");
  EXPECT_EQ(audit->freed, 1);
  EXPECT_EQ(widget("table_attachment_image"), nullptr);
}

TEST_F(TableWorkbenchEditorPython, CardThumbnailLoadsInOneClickWithoutSelectionAndReleasesOnViewChange)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  const auto path = dir.path() / "project" / "public-thumbnail.png";
  io::Image image(512, 256);
  for (size_t p = 0; p < image.pixels.size(); p += 4) {
    image.pixels[p] = 20; image.pixels[p + 1] = 40; image.pixels[p + 2] = 60; image.pixels[p + 3] = 255;
  }
  io::write_png(path, image);
  ASSERT_NO_FATAL_FAILURE(link_attachment(path));
  ASSERT_NO_FATAL_FAILURE(show_board());
  struct Audit { int created = 0, freed = 0; io::Image image; };
  const auto audit = std::make_shared<Audit>();
  f.shell->store().jobs().create_texture = [audit](const io::Image &value) { ++audit->created; audit->image = value; return uint64_t(456); };
  f.shell->store().jobs().free_texture = [audit](uint64_t value) { EXPECT_EQ(value, 456u); ++audit->freed; };
  const auto load = card_key(("attachment_" + evidence + "/table_card_thumbnail_load").c_str());
  const auto picture = card_key(("attachment_" + evidence + "/table_card_thumbnail_image").c_str());
  ASSERT_NE(widget(load.c_str()), nullptr);
  EXPECT_EQ(widget(picture.c_str()), nullptr); EXPECT_EQ(audit->created, 0);
  const auto revision = project().project()->revision;
  const int before = clicks;
  click(load.c_str());
  ASSERT_TRUE(pump([&] { return widget(picture.c_str()) != nullptr; }));
  EXPECT_EQ(clicks - before, 1);
  EXPECT_EQ(audit->created, 1); EXPECT_EQ(audit->image.width, 256u); EXPECT_EQ(audit->image.height, 128u);
  EXPECT_EQ(audit->image.pixels[0], 20); EXPECT_EQ(audit->image.pixels[1], 40); EXPECT_EQ(audit->image.pixels[2], 60);
  frame(); EXPECT_EQ(audit->created, 1);
  EXPECT_EQ(project().project()->revision, revision); EXPECT_EQ(project().record_id(), row_a);
  expect_viewer();
  index("table_views", 0); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(audit->freed, 1);
  index("table_views", 1);
  ASSERT_TRUE(pump([&] { return widget(load.c_str()) != nullptr; }));
  EXPECT_EQ(widget(picture.c_str()), nullptr); EXPECT_EQ(audit->created, 1);
}

TEST_F(TableWorkbenchEditorPython, CardThumbnailRejectsLateResponseAndRetainedActionAfterRevisionChanges)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  const auto path = dir.path() / "project" / "public-thumbnail.png";
  io::write_png(path, io::Image(2, 2));
  ASSERT_NO_FATAL_FAILURE(link_attachment(path));
  ASSERT_NO_FATAL_FAILURE(show_board());
  const auto load = card_key(("attachment_" + evidence + "/table_card_thumbnail_load").c_str());
  const auto picture = card_key(("attachment_" + evidence + "/table_card_thumbnail_image").c_str());
  ASSERT_NE(widget(load.c_str()), nullptr);
  const auto retained = widget(load.c_str())->on_click;
  retained();
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a},
                                          {"field_id", counter}, {"value", 42}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && widget(load.c_str()); }));
  retained(); frame();
  EXPECT_EQ(widget(picture.c_str()), nullptr);
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, ConvertedBmpUsesVerifiedPngPixelsAndPreservesTheViewer)
{
  const auto path = dir.path() / "project" / "public-image.bmp";
  // Synthetic 2x2 RGB(20,40,60) BMP; no user asset or external image.
  const auto bytes = bridge::decode_base64("Qk1GAAAAAAAAADYAAAAoAAAAAgAAAAIAAAABABgAAAAAABAAAADEDgAAxA4AAAAAAAAAAAAAPCgUPCgUAAA8KBQ8KBQAAA==");
  ASSERT_TRUE(bytes);
  { std::ofstream out(path, std::ios::binary); out.write(reinterpret_cast<const char *>(bytes->data()), std::streamsize(bytes->size())); }
  ASSERT_NO_FATAL_FAILURE(link_attachment(path));
  const auto image = std::make_shared<io::Image>();
  f.shell->store().jobs().create_texture = [image](const io::Image &value) { *image = value; return uint64_t(789); };
  f.shell->store().jobs().free_texture = [](uint64_t) {};
  click("table_details"); click("table_attachment_preview");
  ASSERT_TRUE(pump([&] { return widget("table_attachment_image") != nullptr; }));
  EXPECT_EQ(image->width, 2u); EXPECT_EQ(image->height, 2u);
  ASSERT_GE(image->pixels.size(), 4u);
  EXPECT_EQ(image->pixels[0], 20); EXPECT_EQ(image->pixels[1], 40); EXPECT_EQ(image->pixels[2], 60); EXPECT_EQ(image->pixels[3], 255);
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, AttachmentOldCallbacksAndLateReadCannotFollowChangedRecord)
{
  const auto path = dir.path() / "project" / "public-note.txt";
  const std::string text = "Public stale attachment must not appear";
  { std::ofstream out(path, std::ios::binary); out << text; }
  ASSERT_NO_FATAL_FAILURE(link_attachment(path));
  click("table_details");
  const auto *button = widget("table_attachment_preview");
  ASSERT_NE(button, nullptr);
  auto retained = button->on_click;
  retained();  // Do not pump the UI executor until the source has changed.
  project().select_record(row_b); frame();
  retained();
  EXPECT_FALSE(has_text_prefix(text));
  EXPECT_EQ(widget("table_attachment_preview"), nullptr);
  EXPECT_EQ(project().record_id(), row_b);
  project().select_record(row_a); frame();
  ASSERT_TRUE(pump([&] {
    const auto *current = widget("table_attachment_preview");
    return current && current->enabled;
  }));  // The original read has completed, even though its content is no longer applicable.
  retained(); frame();
  EXPECT_FALSE(has_text_prefix(text));
  EXPECT_FALSE(has_text_prefix("Loading attachment"));
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, CorruptAttachmentPngIsRejectedByTheNativeDecoder)
{
  const auto path = dir.path() / "project" / "corrupt.png";
  io::Image image(2, 2);
  auto bytes = io::encode_png(image);
  ASSERT_GT(bytes.size(), 32u);
  bytes[29] ^= 1;  // IHDR CRC: dimensions still pass the bridge's lightweight header check.
  { std::ofstream out(path, std::ios::binary); out.write(reinterpret_cast<const char *>(bytes.data()), std::streamsize(bytes.size())); }
  ASSERT_NO_FATAL_FAILURE(link_attachment(path));
  click("table_details"); click("table_attachment_preview");
  // libspng may verify the header CRC when the following chunk is consumed.
  ASSERT_TRUE(pump([&] { return has_text_prefix("PNG "); }));
  EXPECT_EQ(widget("table_attachment_image"), nullptr);
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, DefaultGridUsesMostOfTheTablePaneAndBooleanChangesInOnePointerClick)
{
  ASSERT_EQ(area().editor().type().id, kEditorTable);
  const auto *grid = widget("records");
  ASSERT_NE(grid, nullptr);
  ASSERT_NE(area().find_region("main"), nullptr);
  EXPECT_GE(grid->rect.h, .55f * area().find_region("main")->rect().height());
  EXPECT_EQ(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("manage_objects"), nullptr);
  EXPECT_EQ(grid->table->grid->cell_style(0, 3), ui::TableCellStyle::Checkbox);
  EXPECT_EQ(grid->table->grid->cell_style(1, 3), ui::TableCellStyle::Text);
  EXPECT_TRUE(grid->table->cell(1, 3).empty()) << "an unset scientific observation is not displayed as false";
  const auto revision = project().project()->revision;
  cell(0, 3);  // The actual checkbox body receives one pointer down/up, with no form or Save.
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_TRUE(project().table()->cell(0, 2)->get<bool>());
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST_F(TableWorkbenchEditorPython, FillHandlePreservesInt64WithOneRevisionAndUndo)
{
  cell(0, 2);
  const auto *grid = widget("records");
  ASSERT_NE(grid, nullptr);
  ASSERT_TRUE(grid->table->grid->on_fill);
  const auto &style = f.screen.ui()->style();
  float right = grid->rect.x + style.pixel;
  float last_width = 0;
  for (int c = 0; c <= 2; ++c) {
    const auto &col = grid->table->columns[size_t(c)];
    const auto width = grid->table->column_width(col.key);
    last_width = std::round(width.value_or(col.width) * style.unit);
    right += last_width;
  }
  const float row_height = style.unit * grid->table->row_height;
  const ui::Vec2 handle{right - style.pixel - .175f * style.unit,
                       grid->rect.y + style.pixel + 2 * row_height - style.pixel - .175f * style.unit};
  const ui::Vec2 destination{right - .5f * last_width, grid->rect.y + style.pixel + 3.5f * row_height};
  const auto revision = project().project()->revision;
  send(ui::Event::mouse_down(handle));
  send(ui::Event::mouse_move(destination));
  EXPECT_EQ(project().project()->revision, revision);
  send(ui::Event::mouse_up(destination));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(clicks, 1); // Select once, then one fill drag without a dialog.
  EXPECT_EQ(project().project()->revision, revision + 1);
  for (int row : {1, 2}) {
    ASSERT_NE(project().table()->cell(row, 1), nullptr);
    EXPECT_EQ(project().table()->cell(row, 1)->get<int64_t>(), INT64_MAX);
  }
  EXPECT_EQ(project().record_id(), row_a);
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().table()->cell(1, 1), nullptr);
  EXPECT_EQ(project().table()->cell(2, 1), nullptr);
}

TEST_F(TableWorkbenchEditorPython, FillKeepsNullUnsetChoicesObjectsAndFormulaDefinitions)
{
  const std::string derived = "d6666666-6666-4666-8666-666666666666";
  const Json object = {{"version", 1}, {"project_id", project().project()->id}, {"kind", "record"}, {"table_id", batches}, {"id", batch_row}};
  ASSERT_TRUE(project().apply(Json::array({
    {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", evidence}, {"value", object}},
    {{"op", "add_field"}, {"table_id", samples}, {"id", derived}, {"name", "Derived"}, {"type", "number"}, {"unit", "K"}},
    {{"op", "set_expression"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", derived}, {"expression", "base + fixed"},
     {"bindings", {{"base", {{"record_id", row_a}, {"field_id", temperature}}}, {"fixed", {{"record_id", row_c}, {"field_id", temperature}}}}}},
    {{"op", "set_reference"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", accepted},
     {"source", {{"record_id", row_b}, {"field_id", accepted}}}}
  })));
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto revision = project().project()->revision;
  auto fill = widget("records")->table->grid->on_fill;
  ASSERT_TRUE(fill({{{1, 1}, {0, 1}}, {{1, 2}, {0, 2}}, {{0, 4}, {2, 4}}, {{0, 5}, {2, 5}},
                    {{0, 6}, {2, 6}}, {{0, 3}, {2, 3}}}));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  ASSERT_NE(project().table()->cell(0, 0), nullptr);
  EXPECT_TRUE(project().table()->cell(0, 0)->is_null());
  EXPECT_EQ(project().table()->cell(0, 1), nullptr);
  EXPECT_EQ(*project().table()->cell(2, 3), dry);
  EXPECT_EQ(io::canonical_json(*project().table()->cell(2, 4)), io::canonical_json(object));
  const auto *definition = project().table()->definition(2, 5);
  ASSERT_NE(definition, nullptr);
  EXPECT_EQ(definition->at("kind"), "expression");
  EXPECT_EQ(definition->at("expression"), "base + fixed");
  EXPECT_EQ(definition->at("bindings").at("base").at("record_id"), row_c);
  EXPECT_EQ(definition->at("bindings").at("fixed").at("record_id"), row_c);
  EXPECT_EQ(*project().table()->cell(2, 5), 700);
  ASSERT_NE(project().table()->definition(2, 2), nullptr);
  EXPECT_EQ(project().table()->definition(2, 2)->at("source").at("record_id"), row_b);
  EXPECT_FALSE(fill({{{0, 4}, {1, 4}}})) << "a captured callback cannot be replayed after a revision";
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  EXPECT_EQ(project().table()->definition(2, 5), nullptr);
}

TEST_F(TableWorkbenchEditorPython, FillRejectsEntireMixedBatchAndProtectsDrafts)
{
  const auto revision = project().project()->revision;
  const auto fill = widget("records")->table->grid->on_fill;
  ASSERT_TRUE(fill);
  EXPECT_FALSE(fill({{{0, 2}, {1, 2}}, {{0, 1}, {1, 2}}})); // K number into a unitless integer.
  frame();
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(1, 1), nullptr);
  cell(0, 1);
  send(ui::Event::text_input("317"));
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_FALSE(widget("records")->table->grid->on_fill);
  EXPECT_FALSE(fill({{{0, 2}, {1, 2}}}));
  EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(TableWorkbenchEditorPython, InlineTypingSuspendsOnBlurAndOnlyEnterWritesTheRetainedDraft)
{
  const auto revision = project().project()->revision;
  cell(0, 1);
  send(ui::Event::text_input("315"));
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  click("table_search");
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  cell(0, 1);
  send(ui::Event::key_down(ui::Key::F2));
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "315");
  send(ui::Event::key_down(ui::Key::Enter));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_EQ(*project().table()->cell(0, 0), 315);
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().record_id(), row_b);
  EXPECT_EQ(widget("records")->table->grid->selection.value().active, (ui::TableCell{1, 1}));
}

TEST_F(TableWorkbenchEditorPython, JsonF2EnterPreservesEveryScalarStringAndCompoundValueExactly)
{
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_field_schema"}, {"id", temperature},
      {"type", "json"}, {"unit", nullptr}, {"options", {{"version", 1}}}}})));
  ASSERT_NO_FATAL_FAILURE(settled());
  for (const auto &value : json_roundtrip_values()) {
    SCOPED_TRACE(value.dump().substr(0, 180));
    const Json previous = *project().table()->cell(0, 0);
    ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", samples},
        {"record_id", row_a}, {"field_id", temperature}, {"value", value}}})));
    ASSERT_NO_FATAL_FAILURE(settled());
    const Json expected = *project().table()->cell(0, 0);
    const auto revision = project().project()->revision;
    cell(0, 1);
    send(ui::Event::key_down(ui::Key::F2));
    ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
    EXPECT_EQ(f.screen.ui()->edit_state()->text(), expected.dump());
    EXPECT_EQ(project().project()->revision, revision);
    send(ui::Event::key_down(ui::Key::Enter));
    ASSERT_NO_FATAL_FAILURE(settled());
    ASSERT_NE(project().table()->cell(0, 0), nullptr);
    EXPECT_EQ(project().table()->cell(0, 0)->type(), expected.type());
    EXPECT_EQ(project().table()->cell(0, 0)->dump(), expected.dump());
    EXPECT_EQ(project().project()->revision, revision + 1);
    EXPECT_FALSE(area().editor().has_unsaved_changes());
    ASSERT_TRUE(project().undo());
    ASSERT_NO_FATAL_FAILURE(settled());
    // Reapplying an identical value advances the revision without adding a history delta.
    EXPECT_EQ(project().table()->cell(0, 0)->dump(), previous.dump());
    ASSERT_TRUE(project().redo());
    ASSERT_NO_FATAL_FAILURE(settled());
    EXPECT_EQ(project().table()->cell(0, 0)->dump(), expected.dump());
  }
}

TEST_F(TableWorkbenchEditorPython, JsonClipboardRectanglePreservesTypesAndInt64WithOneApplyAndUndo)
{
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_field_schema"}, {"id", temperature},
      {"type", "json"}, {"unit", nullptr}, {"options", {{"version", 1}}}}})));
  ASSERT_NO_FATAL_FAILURE(settled());
  for (const auto &value : json_roundtrip_values()) {
    SCOPED_TRACE(value.dump().substr(0, 180));
    ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", samples},
        {"record_id", row_a}, {"field_id", temperature}, {"value", value}}})));
    ASSERT_NO_FATAL_FAILURE(settled());
    const Json expected = *project().table()->cell(0, 0);
    const auto revision = project().project()->revision;
    ASSERT_TRUE(project().table()->cell(1, 0)->is_null());
    ASSERT_EQ(project().table()->cell(1, 1), nullptr);
    cell(0, 1);
    send(ui::Event::key_down(ui::Key::Right, ui::MOD_SHIFT));
    send(ui::Event::key_down(ui::Key::C, ui::MOD_CTRL));
    ASSERT_FALSE(clipboard.text.empty());
    cell(1, 1);
    send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
    ASSERT_TRUE(pump([&] { const auto *apply = widget("table_paste_apply"); return apply && apply->enabled; }));
    EXPECT_EQ(project().project()->revision, revision);
    EXPECT_EQ(widget("table_paste_cells")->table->rows, 2);
    click("table_paste_apply");
    ASSERT_NO_FATAL_FAILURE(settled());
    EXPECT_EQ(project().project()->revision, revision + 1);
    ASSERT_NE(project().table()->cell(1, 0), nullptr);
    EXPECT_EQ(project().table()->cell(1, 0)->type(), expected.type());
    EXPECT_EQ(project().table()->cell(1, 0)->dump(), expected.dump());
    ASSERT_NE(project().table()->cell(1, 1), nullptr);
    EXPECT_EQ(project().table()->cell(1, 1)->get<int64_t>(), INT64_MAX);
    EXPECT_EQ(project().table()->cell(0, 0)->dump(), expected.dump());
    ASSERT_TRUE(project().undo());
    ASSERT_NO_FATAL_FAILURE(settled());
    ASSERT_NE(project().table()->cell(1, 0), nullptr);
    EXPECT_TRUE(project().table()->cell(1, 0)->is_null());
    EXPECT_EQ(project().table()->cell(1, 1), nullptr);
    EXPECT_EQ(project().table()->cell(0, 0)->dump(), expected.dump());
  }
}

TEST_F(TableWorkbenchEditorPython, InvalidJsonInlineEditKeepsItsDraftAndNeverChangesTheTypedValue)
{
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_field_schema"}, {"id", temperature},
      {"type", "json"}, {"unit", nullptr}, {"options", {{"version", 1}}}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", temperature}, {"value", "null"}}})));
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto revision = project().project()->revision;
  cell(0, 1);
  send(ui::Event::key_down(ui::Key::F2));
  send(ui::Event::key_down(ui::Key::A, ui::MOD_CTRL));
  send(ui::Event::text_input("{"));
  send(ui::Event::key_down(ui::Key::Enter));
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "{");
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), "null");
  send(ui::Event::key_down(ui::Key::Escape));
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), "null");
}

TEST_F(TableWorkbenchEditorPython, BoardRecordEditsHiddenTypedFieldsWithoutSwitchingViews)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board(true));
  const auto revision = project().project()->revision;
  const int navigation_start = clicks;
  ASSERT_NO_FATAL_FAILURE(click(card_key("open").c_str()));
  ASSERT_NE(widget("table_detail_field"), nullptr);
  EXPECT_EQ(widget("table_detail_field")->items.size(), 8u);
  EXPECT_EQ(widget("cell_field"), nullptr) << "the record form owns one stable field selector";
  choose("table_detail_field", 5);
  EXPECT_EQ(clicks - navigation_start, 3) << "open record, open field list, choose hidden field";
  EXPECT_EQ(project().record_id(), row_a);
  ASSERT_NE(widget("cell_value"), nullptr);
  type("cell_value", "2026-10-21");
  EXPECT_EQ(project().project()->revision, revision);
  click("save_cell");
  ASSERT_TRUE(pump([&] { return widget("table_detail_field") && !project().busy() && !area().editor().has_unsaved_changes() && project().project()->revision == revision + 1; }));
  EXPECT_EQ(*project().table()->cell(0, 5), "2026-10-21");
  EXPECT_EQ(project().table()->cell(1, 5), nullptr);
  EXPECT_EQ(widget("table_detail_field")->index.value(), 5);
  EXPECT_EQ(widget("records"), nullptr);

  choose("table_detail_field", 6);
  type("cell_value", "not-a-url");
  click("save_cell");
  ASSERT_TRUE(pump([&] { return !project().busy() && !project().error().empty(); }));
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_EQ(project().table()->cell(0, 6), nullptr);
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(widget("cell_value")->string.value(), "not-a-url");
  type("cell_value", "https://example.org/measurements/1");
  click("save_cell");
  ASSERT_TRUE(pump([&] { return widget("table_detail_field") && !project().busy() && !area().editor().has_unsaved_changes() && project().project()->revision == revision + 2; }));
  EXPECT_EQ(*project().table()->cell(0, 6), "https://example.org/measurements/1");

  choose("table_detail_field", 7);
  const auto choice = "choice" + wet;
  click(choice.c_str());
  ASSERT_TRUE(pump([&] { return !project().busy() && project().project()->revision == revision + 3; }));
  EXPECT_EQ(*project().table()->cell(0, 7), Json::array({wet}));
  ASSERT_TRUE(project().undo());
  ASSERT_TRUE(pump([&] { return widget("table_detail_field") && !project().busy() && project().table()->cell(0, 7) == nullptr; }));
  EXPECT_EQ(*project().table()->cell(0, 5), "2026-10-21");
  EXPECT_EQ(widget("table_detail_field")->index.value(), 7);
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, TypedReferencesAndExpressionsKeepTheirDefinitionsInRecordDetails)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_TRUE(project().apply(Json::array({
    {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", tags_field}, {"value", Json::array({dry})}},
    {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", evidence},
     {"value", {{"version", 1}, {"project_id", project().project()->id}, {"kind", "record"}, {"table_id", batches}, {"id", batch_row}}}},
    {{"op", "set_reference"}, {"table_id", samples}, {"record_id", row_b}, {"field_id", phase}, {"source", {{"record_id", row_a}, {"field_id", phase}}}},
    {{"op", "set_reference"}, {"table_id", samples}, {"record_id", row_b}, {"field_id", evidence}, {"source", {{"record_id", row_a}, {"field_id", evidence}}}},
    {{"op", "set_reference"}, {"table_id", samples}, {"record_id", row_b}, {"field_id", tags_field}, {"source", {{"record_id", row_a}, {"field_id", tags_field}}}},
    {{"op", "set_expression"}, {"table_id", samples}, {"record_id", row_c}, {"field_id", phase}, {"expression", Json(dry).dump()}, {"bindings", Json::object()}}
  })));
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto revision = project().project()->revision;
  cell(1, 4);
  click("table_details");
  ASSERT_NE(widget("cell_mode"), nullptr);
  EXPECT_EQ(widget("cell_mode")->index.value(), 1);
  EXPECT_EQ(widget("table_choice"), nullptr);
  const auto old_source_table = widget("source_table")->index;
  const auto old_source_record = widget("source_record")->index;
  const auto old_source_field = widget("source_field")->index;
  const auto source_state = area().editor().save_workspace_state();
  ASSERT_TRUE(area().editor().load_workspace_state(source_state));
  ASSERT_TRUE(pump([&] { return widget("source_field") && widget("table_detail_field"); }));
  EXPECT_EQ(old_source_table.value(), 0);
  EXPECT_EQ(old_source_record.value(), 0);
  EXPECT_EQ(old_source_field.value(), 0);
  old_source_table.assign(1); old_source_record.assign(1); old_source_field.assign(1); frame();
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  const auto phase_definition = *project().table()->definition(1, 3);
  choose("table_detail_field", 7);
  EXPECT_EQ(widget("cell_mode")->index.value(), 1);
  EXPECT_EQ(widget(("choice" + dry).c_str()), nullptr);
  choose("table_detail_field", 4);
  EXPECT_EQ(widget("cell_mode")->index.value(), 1);
  EXPECT_EQ(widget("table_pick_object"), nullptr);
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->definition(1, 3), phase_definition);
  click("save_cell");  // Explicitly saving a reference remains a reference, including object fields.
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(io::get_string(*project().table()->definition(1, 4), "kind"), "reference");
  EXPECT_EQ(*project().table()->cell(1, 4), *project().table()->cell(0, 4));
  cell(2, 4);
  send(ui::Event::key_down(ui::Key::F2));
  ASSERT_NE(widget("cell_mode"), nullptr);
  EXPECT_EQ(widget("cell_mode")->index.value(), 2);
  EXPECT_EQ(widget("table_choice"), nullptr);
  EXPECT_EQ(io::get_string(*project().table()->definition(2, 3), "kind"), "expression");
  EXPECT_EQ(project().project()->revision, revision + 1);
  ASSERT_NE(widget("binding_rows"), nullptr);
  const auto old_binding = widget("binding_rows")->table->selected;
  const auto expression_state = area().editor().save_workspace_state();
  ASSERT_TRUE(area().editor().load_workspace_state(expression_state));
  ASSERT_TRUE(pump([&] { return widget("binding_rows") != nullptr; }));
  EXPECT_EQ(old_binding.value(), -1);
  old_binding.assign(0); frame();
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision + 1);
}

TEST_F(TableWorkbenchEditorPython, BoardDragMovesToEmptyLaneInOneGestureAndOneUndoWithViewerPreserved)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board());
  const auto source = [&] {
    const auto *card = card_widget("table_board_drag");
    return ui::Vec2{card->rect.cx(), card->rect.y + f.screen.ui()->style().box_space + .5f * f.screen.ui()->style().unit};
  };
  const auto target = [&](const std::string &choice) {
    const auto *lane = widget(("table_board_lane_value:" + Json(choice).dump()).c_str());
    return ui::Vec2{lane->rect.cx(), lane->rect.y + .5f * f.screen.ui()->style().unit};
  };
  ASSERT_NE(card_widget("table_board_drag"), nullptr);
  ASSERT_TRUE(card_widget("table_board_drag")->clip.contains(source()));
  const auto wet_target = target(wet);
  ASSERT_TRUE(card_widget("table_board_drag")->clip.contains(wet_target));
  const auto revision = project().project()->revision;
  const auto selected = project().record_id();
  const int clicks_before = clicks;
  send(ui::Event::mouse_down(source()));
  send(ui::Event::mouse_move(wet_target));
  EXPECT_EQ(project().project()->revision, revision);
  send(ui::Event::mouse_up(wet_target));
  ASSERT_TRUE(pump([&] { return !project().busy() && project().project()->revision == revision + 1 && card_widget("table_board_drag"); }));
  EXPECT_EQ(clicks, clicks_before) << "one drag, no navigation or status-picker clicks";
  EXPECT_EQ(*project().table()->cell(0, 3), wet);
  EXPECT_EQ(project().table()->cell(1, 3), nullptr);
  EXPECT_EQ(project().record_id(), selected);
  expect_viewer();
  ASSERT_TRUE(project().undo());
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_drag") && *project().table()->cell(0, 3) == dry; }));
  const auto after_undo = project().project()->revision;
  send(ui::Event::mouse_down(source()));
  send(ui::Event::mouse_move(target(dry)));
  send(ui::Event::mouse_up(target(dry)));
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, after_undo);
  send(ui::Event::mouse_down(source()));
  send(ui::Event::mouse_move(target(wet)));
  send(ui::Event::key_down(ui::Key::Escape));
  send(ui::Event::mouse_up(target(wet)));
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, after_undo);
}

TEST_F(TableWorkbenchEditorPython, BoardDragRejectsRevisionsViewChangesDerivedStatusAndOtherEditorsDraft)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board());
  const auto original = card_widget("table_board_drag")->drag_source->on_drop;
  const auto box = card_widget("table_board_drag")->rect;
  send(ui::Event::mouse_down({box.cx(), box.y + 10}));
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", counter}, {"value", 7}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_drag"); }));
  const auto revision = project().project()->revision;
  EXPECT_EQ(f.screen.ui()->active(), 0u);
  original("value:" + Json(wet).dump()); frame();
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, revision);
  const auto before_view = card_widget("table_board_drag")->drag_source->on_drop;
  index("table_views", 0);
  ASSERT_NO_FATAL_FAILURE(settled());
  before_view("value:" + Json(wet).dump()); frame();
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, revision);
  index("table_views", 1);
  ASSERT_TRUE(pump([&] { return card_widget("table_board_drag") != nullptr; }));
  auto &other = f.area("a3");
  ASSERT_TRUE(other.add_tab(kEditorTable)); frame();
  ASSERT_TRUE(pump([&] { return widget("records") && widget("records")->table->rows == 3; }));
  cell(0, 1); send(ui::Event::text_input("321"));
  ASSERT_TRUE(other.editor().has_unsaved_changes());
  card_widget("table_board_drag")->drag_source->on_drop("value:" + Json(wet).dump()); frame();
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, revision);
  EXPECT_TRUE(other.editor().has_unsaved_changes());
  send(ui::Event::key_down(ui::Key::Escape));
  ASSERT_FALSE(other.editor().has_unsaved_changes());
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_expression"}, {"table_id", samples}, {"record_id", row_a},
      {"field_id", phase}, {"expression", Json(dry).dump()}, {"bindings", Json::object()}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_drag") && !card_widget("table_board_drag")->enabled; }));
  const auto derived_revision = project().project()->revision;
  card_widget("table_board_drag")->drag_source->on_drop("value:" + Json(wet).dump()); frame();
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, derived_revision);
  EXPECT_EQ(io::get_string(*project().table()->definition(0, 3), "kind"), "expression");
}

TEST_F(TableWorkbenchEditorPython, BoardDragPreservesUnsetAndNullAndRejectsUnknownTargets)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board());
  const auto revision = project().project()->revision;
  card_widget("table_board_drag")->drag_source->on_drop("value:\"unknown\""); frame();
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, revision);
  card_widget("table_board_drag")->drag_source->on_drop("null"); frame();
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_drag") && project().table()->cell(0, 3) && project().table()->cell(0, 3)->is_null(); }));
  EXPECT_EQ(project().table()->cell(1, 3), nullptr);
  card_widget("table_board_drag")->drag_source->on_drop("unset"); frame();
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_drag") && !project().table()->cell(0, 3); }));
  EXPECT_EQ(project().project()->revision, revision + 2);
  ASSERT_TRUE(project().undo());
  ASSERT_TRUE(pump([&] { return !project().busy() && project().table()->cell(0, 3) && project().table()->cell(0, 3)->is_null(); }));
}

TEST_F(TableWorkbenchEditorPython, BoardStateHasEmptyChoiceLanesAndChangesOneRecordInOneUndoableEdit)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board());
  const auto has_empty_wet = [&] { return has_text_prefix("Wet · 0 "); };
  EXPECT_TRUE(has_empty_wet());
  const auto revision = project().project()->revision;
  const auto selected = project().record_id();
  const int start = clicks;
  choose(card_key("table_board_state").c_str(), 3);
  EXPECT_EQ(clicks - start, 2) << "visible card status picker and target status";
  ASSERT_TRUE(pump([&] { return !project().busy() && project().project()->revision == revision + 1 && card_widget("table_board_state"); }));
  EXPECT_EQ(*project().table()->cell(0, 3), wet);
  EXPECT_EQ(project().table()->cell(1, 3), nullptr);
  EXPECT_EQ(project().record_id(), selected);
  ASSERT_TRUE(project().undo());
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_state") && *project().table()->cell(0, 3) == dry; }));
  EXPECT_EQ(project().table()->cell(1, 3), nullptr);
  EXPECT_TRUE(has_empty_wet());
  choose(card_key("table_board_state").c_str(), 0);
  ASSERT_TRUE(pump([&] { return !project().busy() && project().table()->cell(0, 3) == nullptr; }));
  ASSERT_TRUE(project().undo());
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_state") && project().table()->cell(0, 3) && *project().table()->cell(0, 3) == dry; }));
  choose(card_key("table_board_state").c_str(), 1);
  ASSERT_TRUE(pump([&] { return !project().busy() && project().table()->cell(0, 3) && project().table()->cell(0, 3)->is_null(); }));
  ASSERT_TRUE(project().undo());
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_state") && project().table()->cell(0, 3) && *project().table()->cell(0, 3) == dry; }));
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, RetainedDetailSettersAndSaveCannotWriteAfterClosingOrChangingFields)
{
  cell(0, 1);
  click("table_details");
  ASSERT_NE(widget("cell_value"), nullptr);
  const auto stale_text = widget("cell_value")->string;
  const auto stale_save = widget("save_cell")->on_click;
  const auto stale_field = widget("table_detail_field")->index;
  const auto revision = project().project()->revision;
  click("table_detail_close");
  stale_text.assign("999"); stale_save(); stale_field.assign(3); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  click("table_details");
  EXPECT_EQ(widget("cell_value")->string.value(), "300");
  stale_text.assign("999"); stale_save(); stale_field.assign(3); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(widget("table_detail_field")->index.value(), 0);
  EXPECT_EQ(widget("cell_value")->string.value(), "300");
  choose("table_detail_field", 3);
  stale_text.assign("999"); stale_save(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(widget("table_detail_field")->index.value(), 3);
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
}

TEST_F(TableWorkbenchEditorPython, BoardStatusCallbacksRejectNewRevisionsDerivedCellsAndAnotherEditorsDraft)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board());
  const auto stale_status = card_widget("table_board_state")->index;
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", counter}, {"value", 7}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_state"); }));
  const auto revision = project().project()->revision;
  stale_status.assign(3); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 3), dry);

  auto &other = f.area("a3");
  ASSERT_TRUE(other.add_tab(kEditorTable)); frame();
  ASSERT_TRUE(pump([&] { return widget("records") && widget("records")->table->rows == 3; }));
  cell(0, 1);
  send(ui::Event::text_input("321"));
  ASSERT_TRUE(other.editor().has_unsaved_changes());
  const auto guarded_status = card_widget("table_board_state")->index;
  guarded_status.assign(3); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
  EXPECT_TRUE(other.editor().has_unsaved_changes());
  send(ui::Event::key_down(ui::Key::Escape));
  ASSERT_FALSE(other.editor().has_unsaved_changes());
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_expression"}, {"table_id", samples}, {"record_id", row_a},
      {"field_id", phase}, {"expression", Json(dry).dump()}, {"bindings", Json::object()}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("table_board_state") && !card_widget("table_board_state")->enabled; }));
  const auto derived_revision = project().project()->revision;
  card_widget("table_board_state")->index.assign(3); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, derived_revision);
  EXPECT_EQ(io::get_string(*project().table()->definition(0, 3), "kind"), "expression");
}

TEST_F(TableWorkbenchEditorPython, HiddenRecordFieldAndDraftSurviveWorkspaceRestoreWithoutAnyWrite)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board(true));
  ASSERT_NO_FATAL_FAILURE(click(card_key("open").c_str()));
  choose("table_detail_field", 5);
  type("cell_value", "2026-11-02");
  const auto revision = project().project()->revision;
  const auto old_save = widget("save_cell")->on_click;
  const auto saved = area().editor().save_workspace_state();
  EXPECT_EQ(saved.at("layout").at("detail_field_id"), observed_date);
  EXPECT_EQ(saved.at("advanced").at("cell_field"), observed_date);
  EXPECT_EQ(saved.at("advanced").at("cell_text"), "2026-11-02");
  ASSERT_TRUE(area().editor().load_workspace_state(saved));
  ASSERT_TRUE(pump([&] { return widget("cell_value") && widget("table_detail_field"); }));
  EXPECT_EQ(widget("table_detail_field")->index.value(), 5);
  EXPECT_EQ(widget("cell_value")->string.value(), "2026-11-02");
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(0, 5), nullptr);
  old_save(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  click("save_cell");
  ASSERT_TRUE(pump([&] { return widget("table_detail_field") && !project().busy() && !area().editor().has_unsaved_changes() && project().project()->revision == revision + 1; }));
  EXPECT_EQ(*project().table()->cell(0, 5), "2026-11-02");
  EXPECT_EQ(widget("table_detail_field")->index.value(), 5);
  const auto before_invalid = area().editor().save_workspace_state();
  auto invalid = before_invalid;
  invalid["layout"]["detail_field_id"] = 17;
  EXPECT_FALSE(area().editor().load_workspace_state(invalid));
  EXPECT_EQ(area().editor().save_workspace_state(), before_invalid);
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, HiddenObjectPickerBindsTheOriginalRecordFieldAndAllowedKinds)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board(true));
  ASSERT_NO_FATAL_FAILURE(click(card_key("open").c_str()));
  choose("table_detail_field", 4);
  const auto old_field = widget("table_detail_field")->index;
  click("table_pick_object");
  ASSERT_NE(widget("table_object_kind"), nullptr);
  EXPECT_EQ(widget("table_object_kind")->items.size(), 2u) << "only the field's record/file kinds are offered";
  choose("table_object_table", 1);
  ASSERT_TRUE(pump([&] { const auto *w = widget("table_object_candidates"); return w && w->list && w->list->count == 1; }));
  const auto old_selection = widget("table_object_candidates")->list->selected;
  old_selection.assign(0); frame();
  const auto old_use = widget("table_object_set")->on_click;
  const auto revision = project().project()->revision;
  old_field.assign(5); frame();  // Simulate an external field-navigation callback while the picker exists.
  EXPECT_EQ(widget("table_object_set"), nullptr);
  old_use(); old_selection.assign(0); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(0, 4), nullptr);
  choose("table_detail_field", 4);
  click("table_pick_object");
  ASSERT_TRUE(pump([&] { const auto *w = widget("table_object_candidates"); return w && w->list && w->list->count == 1; }));
  old_selection.assign(0); old_use(); frame();
  EXPECT_EQ(widget("table_object_candidates")->list->selected.value(), -1);
  widget("table_object_candidates")->list->selected.assign(0); frame();
  const auto wrong_record_use = widget("table_object_set")->on_click;
  ASSERT_TRUE(project().request_select(project().project()->handle, revision, samples, row_b)); frame();
  wrong_record_use(); frame();
  EXPECT_EQ(widget("table_object_set"), nullptr);
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(0, 4), nullptr);
  EXPECT_EQ(project().table()->cell(1, 4), nullptr);
}

TEST_F(TableWorkbenchEditorPython, BoardWithoutVisibleColumnsStillOpensAndEditsTheStableRecord)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board(true));
  auto definition = area().editor().save_state().at("view");
  for (auto &column : definition["columns"]) { column["hidden"] = true; }
  ASSERT_TRUE(project().apply(Json::array({{{"op", "put_table_view"}, {"id", board_view}, {"table_id", samples},
      {"name", "Sample status"}, {"definition", definition}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && card_widget("open") && area().editor().save_state().at("view") == definition; }));
  const auto revision = project().project()->revision;
  ASSERT_NO_FATAL_FAILURE(click(card_key("open").c_str()));
  ASSERT_NE(widget("table_detail_field"), nullptr);
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(widget("table_detail_field")->index.value(), 0);
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "300");
  type("cell_value", "305");
  click("save_cell");
  ASSERT_TRUE(pump([&] { return !project().busy() && !area().editor().has_unsaved_changes() && project().project()->revision == revision + 1; }));
  EXPECT_EQ(*project().table()->cell(0, 0), 305);
  EXPECT_TRUE(project().table()->cell(1, 0)->is_null());
}

TEST_F(TableWorkbenchEditorPython, BoardGroupingKeepsJsonStringsAndNumbersInDifferentLanes)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board());
  auto definition = area().editor().save_state().at("view");
  definition["group_field_id"] = temperature;
  ASSERT_TRUE(project().apply(Json::array({
      {{"op", "set_field_schema"}, {"id", temperature}, {"type", "json"}, {"unit", nullptr}, {"options", {{"version", 1}}}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", temperature}, {"value", 1}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_b}, {"field_id", temperature}, {"value", "1"}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_c}, {"field_id", temperature}, {"value", nullptr}},
      {{"op", "put_table_view"}, {"id", board_view}, {"table_id", samples}, {"name", "Typed JSON groups"}, {"definition", definition}}
  })));
  const auto has_lane = [&](const std::string &prefix) { return has_text_prefix(prefix); };
  ASSERT_TRUE(pump([&] { return !project().busy() && has_lane("1 · 1 ") && has_lane("\"1\" · 1 "); }));
  EXPECT_EQ(card_widget("table_board_state"), nullptr);
  EXPECT_TRUE(has_lane(std::string(f.shell->store().tr("table.value_null")) + " · 1 "));
  EXPECT_EQ(*project().table()->cell(0, 0), 1);
  EXPECT_EQ(*project().table()->cell(1, 0), "1");
}

TEST_F(TableWorkbenchEditorPython, InlineTabKeepsGridRecordFormAndSaveTargetOnTheNextField)
{
  cell(0, 1);
  click("table_details");
  cell(0, 1);
  send(ui::Event::key_down(ui::Key::F2));
  send(ui::Event::key_down(ui::Key::A, ui::MOD_CTRL));
  send(ui::Event::text_input("315"));
  send(ui::Event::key_down(ui::Key::Tab));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(widget("records")->table->grid->selection.value().active, (ui::TableCell{0, 2}));
  ASSERT_NE(widget("table_detail_field"), nullptr);
  EXPECT_EQ(widget("table_detail_field")->index.value(), 1);
  EXPECT_EQ(area().editor().save_state().at("detail_field_id"), counter);
  EXPECT_EQ(area().editor().save_workspace_state().at("advanced").at("cell_field"), counter);
  EXPECT_EQ(widget("cell_value")->string.value(), std::to_string(INT64_MAX));
  type("cell_value", "9223372036854775806");
  click("save_cell");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 315);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_C(9223372036854775806));
}

TEST_F(TableWorkbenchEditorPython, AllHiddenGridColumnsUseSafeRecordSelectionAndOpenTheWholeRecord)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board(true));
  auto definition = area().editor().save_state().at("view");
  definition["kind"] = "grid";
  for (auto &column : definition["columns"]) { column["hidden"] = true; }
  ASSERT_TRUE(project().apply(Json::array({{{"op", "put_table_view"}, {"id", board_view}, {"table_id", samples},
      {"name", "Record identities"}, {"definition", definition}}})));
  ASSERT_TRUE(pump([&] { return !project().busy() && widget("records") && !widget("records")->table->grid && widget("records")->table->rows == 3; }));
  const auto *grid = widget("records");
  const auto &style = f.screen.ui()->style();
  point({grid->rect.x + style.unit, grid->rect.y + style.pixel + 2.5f * style.unit * grid->table->row_height});
  EXPECT_EQ(project().record_id(), row_b);
  ASSERT_NE(widget("table_detail_field"), nullptr);
  EXPECT_EQ(widget("table_detail_field")->items.size(), 8u);
  choose("table_detail_field", 5);
  type("cell_value", "2026-10-22");
  click("save_cell");
  ASSERT_TRUE(pump([&] { return !project().busy() && project().table()->cell(1, 5); }));
  EXPECT_EQ(*project().table()->cell(1, 5), "2026-10-22");
  EXPECT_EQ(project().table()->cell(0, 5), nullptr);
}

TEST_F(TableWorkbenchEditorPython, ManagementBindingsCannotRenameAnotherFieldOrSurviveWorkspaceReplacement)
{
  cell(0, 1);
  click("table_details");
  click("manage_objects");
  ASSERT_NE(widget("rename_field"), nullptr);
  EXPECT_EQ(widget("manage_field"), nullptr);
  const auto old_name = widget("rename_field")->string;
  const auto old_save = widget("save_field_name")->on_click;
  choose("table_detail_field", 3);
  ASSERT_NE(widget("rename_field"), nullptr);
  EXPECT_EQ(widget("rename_field")->string.value(), "State");
  const auto revision = project().project()->revision;
  old_name.assign("Wrong field name"); old_save(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(widget("rename_field")->string.value(), "State");
  assign("rename_field", "Condition");  // Binding safety test; no pointer-click metric is claimed here.
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  const auto saved = area().editor().save_workspace_state();
  const auto replaced_name = widget("rename_field")->string;
  ASSERT_TRUE(area().editor().load_workspace_state(saved));
  ASSERT_TRUE(pump([&] { return widget("rename_field") != nullptr; }));
  EXPECT_TRUE(replaced_name.value().empty());
  replaced_name.assign("Dangling rename"); old_name.assign("Another dangling rename"); old_save(); frame();
  EXPECT_EQ(widget("rename_field")->string.value(), "Condition");
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_TRUE(pump([&] { return widget("save_field_name") && widget("save_field_name")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(action("save_field_name"));
  ASSERT_TRUE(pump([&] { return !project().busy() && !area().editor().has_unsaved_changes() && project().project()->revision == revision + 1; }));
  EXPECT_EQ(project().table()->fields[0].name, "Temperature");
  EXPECT_EQ(project().table()->fields[3].name, "Condition");
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
}

TEST_F(TableWorkbenchEditorPython, SweepReadsLiveInputsAndOldBindingsCannotRetargetOrSurviveRestore)
{
  cell(0, 1);
  click("table_details");
  click("project_sweep");
  ASSERT_NE(widget("start"), nullptr);
  assign("start", "300"); assign("stop", "310"); assign("count", "2");
  ASSERT_NE(widget("apply_sweep"), nullptr);
  ASSERT_TRUE(widget("apply_sweep")->enabled);
  const auto old_start = widget("start")->string;
  const auto old_copy = widget("copy_selected")->boolean;
  const auto old_apply = widget("apply_sweep")->on_click;
  const auto revision = project().project()->revision;
  choose("table_detail_field", 1);
  ASSERT_NE(widget("start"), nullptr);
  old_start.assign("999"); old_copy.assign(false); old_apply(); frame();
  EXPECT_EQ(widget("start")->string.value(), "300");
  EXPECT_TRUE(widget("copy_selected")->boolean.value());
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  const auto old_axis_apply = widget("apply_sweep")->on_click;
  choose("field", 1);
  old_axis_apply(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->records.size(), 3);
  const auto saved = area().editor().save_workspace_state();
  const auto replaced_start = widget("start")->string;
  const auto replaced_field = widget("field")->index;
  ASSERT_TRUE(area().editor().load_workspace_state(saved));
  ASSERT_TRUE(pump([&] { return widget("start") && widget("apply_sweep"); }));
  EXPECT_TRUE(replaced_start.value().empty());
  EXPECT_EQ(replaced_field.value(), -1);
  replaced_start.assign("777"); old_apply(); frame();
  EXPECT_EQ(widget("start")->string.value(), "300");
  EXPECT_EQ(project().project()->revision, revision);
  // Keep a valid previous count, edit without Enter, then click Apply once. The click
  // commits the active text first and must plan three rows, never the old count of two.
  click("count");
  send(ui::Event::key_down(ui::Key::A, ui::MOD_CTRL));
  send(ui::Event::text_input("3"));
  const auto *button = widget("apply_sweep"); ASSERT_NE(button, nullptr);
  ASSERT_TRUE(button->enabled);
  click("apply_sweep");
  ASSERT_TRUE(pump([&] { return !project().busy() && project().table()->records.size() == 6; }));
  EXPECT_EQ(project().project()->revision, revision + 1);
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
}

TEST_F(TableWorkbenchEditorPython, LegacyWorkspaceRestoresItsAdvancedDraftFieldInsteadOfTheOldGridCursor)
{
  ASSERT_NO_FATAL_FAILURE(add_record_fields());
  ASSERT_NO_FATAL_FAILURE(show_board(true));
  ASSERT_NO_FATAL_FAILURE(click(card_key("open").c_str()));
  choose("table_detail_field", 5);
  type("cell_value", "2026-12-03");
  auto legacy = area().editor().save_workspace_state();
  legacy["layout"].erase("detail_field_id");
  legacy["parameters"]["active_field_id"] = temperature;
  legacy["parameters"]["anchor_row"] = 0; legacy["parameters"]["active_row"] = 0;
  legacy["parameters"]["anchor_column"] = 1; legacy["parameters"]["active_column"] = 1;
  const auto revision = project().project()->revision;
  ASSERT_TRUE(area().editor().load_workspace_state(legacy));
  ASSERT_TRUE(pump([&] { return widget("cell_value") && widget("table_detail_field"); }));
  EXPECT_EQ(widget("table_detail_field")->index.value(), 5);
  EXPECT_EQ(area().editor().save_state().at("detail_field_id"), observed_date);
  EXPECT_EQ(widget("cell_value")->string.value(), "2026-12-03");
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  click("save_cell");
  ASSERT_TRUE(pump([&] { return !project().busy() && !area().editor().has_unsaved_changes() && project().project()->revision == revision + 1; }));
  EXPECT_EQ(*project().table()->cell(0, 5), "2026-12-03");
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
}

TEST_F(TableWorkbenchEditorPython, RemovedFieldsOrRecordsKeepTheOriginalDraftVisibleUntilExplicitDiscard)
{
  cell(0, 1);
  click("table_details");
  type("cell_value", "321");
  const auto old_save = widget("save_cell")->on_click;
  Json commands = Json::array();
  for (const auto &field : project().table()->fields) { commands.push_back({{"op", "delete_field"}, {"id", field.id}}); }
  ASSERT_TRUE(project().apply(commands));
  ASSERT_TRUE(pump([&] { return !project().busy() && widget("table_advanced_discard"); }));
  EXPECT_TRUE(project().table()->fields.empty());
  EXPECT_EQ(area().editor().save_workspace_state().at("advanced").at("cell_text"), "321");
  EXPECT_EQ(area().editor().save_workspace_state().at("advanced").at("cell_field"), temperature);
  const auto field_revision = project().project()->revision;
  old_save(); frame();
  EXPECT_EQ(project().project()->revision, field_revision);
  click("table_advanced_discard");
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());

  cell(0, 1);
  type("cell_value", "322");
  commands = Json::array();
  for (const auto &record : project().table()->records) { commands.push_back({{"op", "delete_record"}, {"id", record.id}}); }
  ASSERT_TRUE(project().apply(commands));
  ASSERT_TRUE(pump([&] { return !project().busy() && widget("table_advanced_discard"); }));
  EXPECT_TRUE(project().table()->records.empty());
  EXPECT_EQ(area().editor().save_workspace_state().at("advanced").at("cell_text"), "322");
  EXPECT_EQ(area().editor().save_workspace_state().at("advanced").at("cell_field"), temperature);
  const auto record_revision = project().project()->revision;
  click("table_advanced_discard");
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, record_revision);
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
}

TEST_F(TableWorkbenchEditorPython, RemovedTablesKeepTheirDraftAndIdentityRecoverableWithoutATablePane)
{
  cell(0, 1);
  click("table_details");
  type("cell_value", "323");
  const auto old_save = widget("save_cell")->on_click;
  Json commands = Json::array();
  for (const auto &table : project().tables()) { commands.push_back({{"op", "delete_table"}, {"id", table.id}}); }
  ASSERT_TRUE(project().apply(commands));
  ASSERT_TRUE(pump([&] { return !project().busy() && widget("table_advanced_discard"); }));
  ASSERT_EQ(project().table(), nullptr);
  EXPECT_EQ(area().editor().save_workspace_state().at("advanced").at("cell_text"), "323");
  EXPECT_EQ(area().editor().save_workspace_state().at("advanced").at("cell_field"), temperature);
  const auto revision = project().project()->revision;
  old_save(); frame();
  EXPECT_EQ(project().project()->revision, revision);
  click("table_advanced_discard");
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(TableWorkbenchEditorPython, PasteFitsTheActualRectanglePreviewsAndUndoesAsOneEdit)
{
  const auto initial = project().project()->revision;
  cell(0, 1);
  clipboard.text = "310";
  send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
  ASSERT_TRUE(pump([&] { const auto *apply = widget("table_paste_apply"); return apply && apply->enabled; }));
  EXPECT_EQ(project().project()->revision, initial);
  ASSERT_NE(widget("table_paste_cells"), nullptr);
  EXPECT_EQ(widget("table_paste_cells")->table->rows, 1);
  click("table_paste_apply");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, initial + 1);
  EXPECT_EQ(*project().table()->cell(0, 0), 310);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);

  cell(0, 1);
  clipboard.text = "320\t9223372036854775806\n330\t-9223372036854775807";
  const auto before = project().project()->revision;
  send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
  ASSERT_TRUE(pump([&] { const auto *apply = widget("table_paste_apply"); return apply && apply->enabled; }));
  EXPECT_EQ(widget("table_paste_cells")->table->rows, 4);
  EXPECT_EQ(project().project()->revision, before);
  click("table_paste_apply");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, before + 1);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_C(9223372036854775806));
  EXPECT_EQ(*project().table()->cell(1, 0), 330);
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_TRUE(project().table()->cell(1, 0)->is_null());
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  EXPECT_EQ(project().table()->cell(1, 1), nullptr);
}

TEST_F(TableWorkbenchEditorPython, CsvPreviewMappingRejectsChangedBytesThenImportsUndoablyAndExportsTheFilteredView)
{
  const auto source = dir.path() / "synthetic-input.csv";
  const auto output = dir.path() / "synthetic-filtered.csv";
  const auto write_source = [&](const char *hot_temperature) {
    std::ofstream file(source, std::ios::binary | std::ios::trunc);
    ASSERT_TRUE(file.is_open());
    file << "Temperature,Count,Note\n300,9223372036854775807,\"synthetic, cold\"\n"
         << hot_temperature << ",2,\"synthetic, hot\"\n";
    file.close();
    ASSERT_TRUE(file.good());
  };
  const auto open_csv = [&] {
    const auto *more = widget("table_more"); ASSERT_NE(more, nullptr);
    const auto label = std::string(f.shell->store().tr("project.csv.title"));
    const auto found = std::find_if(more->menu.begin(), more->menu.end(),
        [&](const auto &entry) { return entry.text == label; });
    ASSERT_NE(found, more->menu.end()); ASSERT_TRUE(found->enabled && found->action);
    const auto open = found->action;
    open(); frame();
    ASSERT_NE(widget("table_csv_source"), nullptr);
  };
  const auto preview_and_map = [&](const std::string &expected_hot) {
    assign("table_csv_source", core::path_to_utf8(source));
    action("table_csv_preview");
    ASSERT_TRUE(pump([&] {
      const auto *grid = widget("table_csv_preview_grid");
      return grid && grid->table && grid->table->rows == 2 && grid->table->columns.size() == 3 &&
             grid->table->cell(1, 0) == expected_hot;
    }));
    EXPECT_EQ(widget("table_csv_preview_grid")->table->cell(0, 1), "9223372036854775807");
    EXPECT_EQ(widget("table_csv_preview_grid")->table->cell(0, 2), "synthetic, cold");
    // Explicit per-column GUI declarations: previewing does not infer numeric types or units.
    ASSERT_NE(widget("csv_column0/type"), nullptr);
    EXPECT_EQ(widget("csv_column0/type")->index.value(), 0);
    index("csv_column0/type", 2);  // number
    ASSERT_NE(widget("csv_column0/unit"), nullptr); ASSERT_TRUE(widget("csv_column0/unit")->enabled);
    assign("csv_column0/unit", "K");
    index("csv_column1/type", 1);  // integer, retained exactly beyond double precision
    EXPECT_EQ(widget("csv_column2/type")->index.value(), 0);  // text remains text
    assign("table_csv_name", "Synthetic imported measurements");
    ASSERT_NE(widget("table_csv_import"), nullptr); ASSERT_TRUE(widget("table_csv_import")->enabled);
  };

  const auto initial = project().project()->revision;
  const auto initial_tables = project().tables().size();
  ASSERT_NO_FATAL_FAILURE(write_source("350"));
  ASSERT_NO_FATAL_FAILURE(open_csv());
  ASSERT_NO_FATAL_FAILURE(preview_and_map("350"));
  EXPECT_EQ(project().project()->revision, initial);
  EXPECT_EQ(project().tables().size(), initial_tables);
  ASSERT_NO_FATAL_FAILURE(write_source("360.5"));  // A real byte change after the displayed preview.
  action("table_csv_import");
  ASSERT_TRUE(pump([&] { return !project().busy() && !project().error().empty(); }));
  EXPECT_NE(project().error().find("changed since its preview"), std::string::npos);
  EXPECT_EQ(project().project()->revision, initial);
  EXPECT_EQ(project().tables().size(), initial_tables);
  EXPECT_EQ(project().table_id(), samples);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  expect_viewer();

  ASSERT_NO_FATAL_FAILURE(open_csv());
  ASSERT_NO_FATAL_FAILURE(preview_and_map("360.5"));
  action("table_csv_import");
  ASSERT_NO_FATAL_FAILURE(settled(2));
  ASSERT_EQ(project().tables().size(), initial_tables + 1);
  EXPECT_EQ(project().project()->revision, initial + 1);
  ASSERT_NE(project().table_id(), samples);
  const auto imported = project().table_id();
  const auto first_record = project().table()->records[0].id, second_record = project().table()->records[1].id;
  ASSERT_EQ(project().table()->fields.size(), 3u);
  EXPECT_EQ(project().table()->fields[0].type, "number");
  EXPECT_EQ(project().table()->fields[0].unit, "K");
  EXPECT_EQ(project().table()->fields[1].type, "integer");
  EXPECT_EQ(project().table()->fields[2].type, "text");
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  EXPECT_EQ(*project().table()->cell(1, 0), 360.5);
  EXPECT_EQ(*project().table()->cell(1, 2), "synthetic, hot");

  // One Undo removes the entire table/field/record/cell batch; one Redo restores its identities.
  action("project_undo");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, initial + 2);
  EXPECT_EQ(project().tables().size(), initial_tables);
  EXPECT_TRUE(std::none_of(project().tables().begin(), project().tables().end(),
      [&](const auto &table) { return table.id == imported; }));
  action("project_redo");
  ASSERT_TRUE(pump([&] { return !project().busy() && project().tables().size() == initial_tables + 1; }));
  const auto restored = std::find_if(project().tables().begin(), project().tables().end(),
      [&](const auto &table) { return table.id == imported; });
  ASSERT_NE(restored, project().tables().end());
  index("table", int(restored - project().tables().begin()));
  ASSERT_NO_FATAL_FAILURE(settled(2));
  EXPECT_EQ(project().project()->revision, initial + 3);
  ASSERT_EQ(project().table()->records.size(), 2u);
  EXPECT_EQ(project().table()->records[0].id, first_record);
  EXPECT_EQ(project().table()->records[1].id, second_record);
  EXPECT_EQ(project().table()->fields[0].unit, "K");
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);

  action("table_settings");
  index("table_filter_field", 0);
  index("table_filter_op", 3);  // Numeric gt.
  assign("table_filter_value", "300");
  action("table_filter_add");
  action("table_view_done");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "360.5");
  ASSERT_EQ(project().table()->records.size(), 2u) << "filtering changes the view, not stored rows";
  ASSERT_NO_FATAL_FAILURE(open_csv());
  assign("table_csv_destination", core::path_to_utf8(output));
  action("table_csv_export");
  ASSERT_TRUE(pump([&] { return !project().busy() && std::filesystem::is_regular_file(output); }));
  EXPECT_TRUE(project().error().empty()) << project().error();
  EXPECT_EQ(project().project()->revision, initial + 3);
  std::ifstream file(output, std::ios::binary); ASSERT_TRUE(file.is_open());
  const std::string actual((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
  EXPECT_EQ(actual, std::string("\xEF\xBB\xBF") +
      "Temperature,Count,Note\r\n360.5,2,\"synthetic, hot\"\r\n");
  const auto &scripts = f.shell->store().scripts();
  EXPECT_TRUE(scripts.history().empty());
  EXPECT_TRUE(!scripts.status().contains("run") || scripts.status().at("run").is_null());
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, SavedLeafFilterSurvivesAddingAnotherConditionAndResavingTheView)
{
  const std::string saved_view = "e1111111-1111-4111-8111-111111111111";
  const Json positive = {{"field_id", temperature}, {"op", "gt"}, {"value", 0}};
  ASSERT_TRUE(project().apply(Json::array({
    {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_b}, {"field_id", temperature}, {"value", -10}},
    {{"op", "put_table_view"}, {"id", saved_view}, {"table_id", samples}, {"name", "Positive synthetic samples"},
     {"definition", {{"version", 1}, {"kind", "grid"}, {"filters", positive}}}}
  })));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(pump([&] { const auto *tabs = widget("table_views"); return tabs && tabs->items.size() == 2; }));
  index("table_views", 1);
  ASSERT_NO_FATAL_FAILURE(settled(2));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "300");
  EXPECT_EQ(widget("records")->table->cell(1, 1), "350");

  action("table_settings");
  ASSERT_NE(widget("filter0/remove"), nullptr) << "the root leaf is visible in the builder";
  index("table_filter_field", 0);
  index("table_filter_op", 5); // lt
  assign("table_filter_value", "325");
  action("table_filter_add");
  const auto before_save = project().project()->revision;
  action("table_view_save");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(project().project()->revision, before_save + 1);
  EXPECT_EQ(widget("records")->table->cell(0, 1), "300")
      << "the negative record must not reappear when the upper bound is added";
  ASSERT_EQ(project().table()->records.size(), 3u);
  EXPECT_EQ(*project().table()->cell(1, 0), -10);

  Json stored;
  bool done = false;
  bridge::CallOptions never;
  never.retry = bridge::CallOptions::Retry::Never;
  client->call("project.table.views.get", {{"handle", project().project()->handle},
      {"expected_revision", project().project()->revision}, {"id", saved_view}}, never).then([&](auto response) {
    EXPECT_TRUE(response);
    if (response) { stored = response.value().at("view").at("definition").at("filters"); }
    done = true;
  });
  ASSERT_TRUE(pump([&] { return done; }));
  ASSERT_TRUE(stored.is_object());
  EXPECT_EQ(stored.at("op"), "and");
  ASSERT_EQ(stored.at("conditions").size(), 2u);
  EXPECT_EQ(nlohmann::json(stored.at("conditions")[0]), nlohmann::json(positive));
  EXPECT_EQ(nlohmann::json(stored.at("conditions")[1]),
      nlohmann::json({{"field_id", temperature}, {"op", "lt"}, {"value", 325}}));
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, NullDateAndAmbiguousChoiceLabelsNeverTurnIntoAnotherValue)
{
  const std::string date = "d6666666-6666-4666-8666-666666666666";
  const std::string other = "d7777777-7777-4777-8777-777777777777";
  ASSERT_TRUE(project().apply(Json::array({
    {{"op", "add_field"}, {"table_id", samples}, {"id", date}, {"name", "Observed"}, {"type", "date"}},
    {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", date}, {"value", nullptr}},
    {{"op", "set_field_schema"}, {"id", phase}, {"type", "single_select"}, {"unit", nullptr},
      {"options", {{"version", 1}, {"choices", Json::array({
        {{"id", dry}, {"label", "Repeated"}, {"color", "#123456"}},
        {{"id", other}, {"label", "Repeated"}, {"color", "#234567"}}
      })}}}}
  })));
  ASSERT_NO_FATAL_FAILURE(settled());
  cell(0, 6);
  send(ui::Event::key_down(ui::Key::F2));
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_TRUE(f.screen.ui()->edit_state()->text().empty());
  send(ui::Event::key_down(ui::Key::Enter));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(project().table()->cell(0, 5));
  EXPECT_TRUE(project().table()->cell(0, 5)->is_null());
  cell(0, 4);
  send(ui::Event::key_down(ui::Key::F2));
  send(ui::Event::text_input("Repeated"));
  const auto revision = project().project()->revision;
  send(ui::Event::key_down(ui::Key::Enter));
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "Repeated");
  send(ui::Event::key_down(ui::Key::Escape));
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST_F(TableWorkbenchEditorPython, NamedTypedFilterAndSortSurviveProjectCloseAndReopen)
{
  click("table_settings");
  assign("table_view_name", "Hot synthetic samples");
  index("table_filter_field", 0);
  index("table_filter_op", 3);  // Numeric gt, not lexicographic text matching.
  assign("table_filter_value", "300");
  click("table_filter_add");
  index("table_sort_field", 1);
  index("table_sort_direction", 1);
  click("table_sort_add");
  click("table_view_save");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  ASSERT_TRUE(pump([&] { const auto *tabs = widget("table_views"); return tabs && tabs->items.size() == 2; }));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "350");
  ASSERT_TRUE(project().close());
  ASSERT_TRUE(pump([&] { return !project().project() && !project().busy(); }));
  ASSERT_TRUE(area().add_tab(kEditorTable));  // A fresh instance proves the view came from the project DB.
  frame();
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(pump([&] { const auto *tabs = widget("table_views"); return tabs && tabs->items.size() == 2; }));
  // Fixed starting point: freshly reopened project, all-records view visible. One pointer
  // click switches to the saved view; asynchronous reads and typing are not counted as clicks.
  const auto *tabs = widget("table_views"); ASSERT_NE(tabs, nullptr);
  point({tabs->rect.x + tabs->rect.w * .75f, tabs->rect.cy()});
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "350");
  EXPECT_EQ(project().table()->records.size(), 3u);
}

TEST_F(TableWorkbenchEditorPython, ChoiceAndBooleanFiltersUseTypedPickersWithoutEnteringIdentities)
{
  click("table_settings");
  index("table_filter_field", 3);  // State: stored UUID, human option label in the UI.
  index("table_filter_op", 0);
  ASSERT_NE(widget("table_filter_choice"), nullptr);
  EXPECT_EQ(widget("table_filter_choice")->items, (std::vector<std::string>{"Dry"}));
  EXPECT_EQ(widget("table_filter_value"), nullptr);
  index("table_filter_choice", 0);
  click("table_filter_add");
  index("table_filter_field", 2);  // Accepted: a boolean picker, not JSON entry.
  ASSERT_NE(widget("table_filter_boolean"), nullptr);
  index("table_filter_boolean", 1);
  click("table_filter_add");
  assign("table_view_name", "Dry pending samples");
  click("table_view_save");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "300");
  EXPECT_EQ(project().table()->records.size(), 3u);
}

TEST_F(TableWorkbenchEditorPython, SameTableExternalSelectionKeepsGridDetailAndSaveOnTheSameRecord)
{
  select(0, 1);
  action("table_details");
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "300");
  const auto selected = project().request_select(project().project()->handle, project().project()->revision, samples, row_c);
  ASSERT_TRUE(selected);
  frame();
  ASSERT_NE(widget("records"), nullptr);
  EXPECT_EQ(widget("records")->table->grid->selection.value().active, (ui::TableCell{2, 1}));
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "350");
  assign("cell_value", "360");
  action("save_cell");  // Exercise the retained advanced editor's stable-ID command, not a mouse KPI.
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_EQ(*project().table()->cell(2, 0), 360);
  EXPECT_EQ(project().record_id(), row_c);
}

TEST_F(TableWorkbenchEditorPython, RecordObjectPickerLinksAnotherTableAndLocatesItsStableRecord)
{
  select(0, 5);
  click("table_details");
  click("table_pick_object");
  ASSERT_NE(widget("table_object_table"), nullptr);
  index("table_object_table", 1);
  ASSERT_TRUE(pump([&] {
    const auto *list = widget("table_object_candidates");
    return list && list->list && list->list->count == 1 &&
        list->list->text(0).find("Synthetic batches") != std::string::npos;
  }));
  widget("table_object_candidates")->list->selected.assign(0);
  frame();
  click("table_object_set");
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto *reference = project().table()->cell(0, 4);
  ASSERT_NE(reference, nullptr);
  ASSERT_TRUE(reference->is_object());
  EXPECT_EQ(reference->at("kind"), "record");
  EXPECT_EQ(reference->at("table_id"), batches);
  EXPECT_EQ(reference->at("id"), batch_row);
  EXPECT_EQ(reference->at("project_id"), project().project()->id);
  EXPECT_EQ(project().table_id(), samples);
  click("table_resolve_object");
  ASSERT_TRUE(pump([&] { return widget("table_object_locate") != nullptr; }));
  action("table_object_locate");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(project().table_id(), batches);
  EXPECT_EQ(project().record_id(), batch_row);
  EXPECT_EQ(*project().table()->cell(0, 0), "Synthetic B");
}

TEST_F(TableWorkbenchEditorPython, CancelledAndSupersededPasteApplyCallbacksCannotWrite)
{
  cell(0, 1);
  clipboard.text = "310";
  send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
  ASSERT_TRUE(pump([&] { return widget("table_paste_apply") != nullptr; }));
  const auto abandoned = widget("table_paste_apply")->on_click;
  ASSERT_TRUE(abandoned);
  click("table_paste_cancel");
  const auto revision = project().project()->revision;
  abandoned(); frame(); loop.run_ready(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);

  cell(0, 1);
  clipboard.text = "320";
  send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
  ASSERT_TRUE(pump([&] { return widget("table_paste_apply") != nullptr; }));
  abandoned(); frame(); loop.run_ready(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  click("table_paste_apply");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_EQ(*project().table()->cell(0, 0), 320);
}

TEST_F(TableWorkbenchEditorPython, CancelledObjectPickerCannotApplyItsRetainedUseCallback)
{
  select(0, 5);
  click("table_details");
  click("table_pick_object");
  index("table_object_table", 1);
  ASSERT_TRUE(pump([&] {
    const auto *list = widget("table_object_candidates");
    return list && list->list && list->list->count == 1 &&
        list->list->text(0).find("Synthetic batches") != std::string::npos;
  }));
  widget("table_object_candidates")->list->selected.assign(0);
  frame();
  const auto *use = widget("table_object_set");
  ASSERT_NE(use, nullptr);
  ASSERT_TRUE(use->enabled);
  const auto abandoned = use->on_click;
  ASSERT_TRUE(abandoned);
  send(ui::Event::key_down(ui::Key::Escape));
  EXPECT_EQ(widget("table_object_set"), nullptr);
  const auto revision = project().project()->revision;
  abandoned(); frame(); loop.run_ready(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(0, 4), nullptr);
}

TEST_F(TableWorkbenchEditorPython, FormulaCellsOpenTheirDefinitionAndRecomputeWithoutBecomingLiterals)
{
  const std::string derived = "ceeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
  ASSERT_TRUE(project().apply(Json::array({
    {{"op", "add_field"}, {"table_id", samples}, {"id", derived}, {"name", "Derived temperature"}, {"type", "number"}, {"unit", "K"}},
    {{"op", "set_expression"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", derived},
     {"expression", "base + quantity(10, \"K\")"},
     {"bindings", {{"base", {{"record_id", row_a}, {"field_id", temperature}}}}}}
  })));
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto revision = project().project()->revision;
  cell(0, 6);
  send(ui::Event::key_down(ui::Key::F2));
  send(ui::Event::text_input("999"));
  EXPECT_EQ(f.screen.ui()->editing(), 0);
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NE(widget("cell_mode"), nullptr);
  EXPECT_EQ(widget("cell_mode")->index.value(), 2);
  EXPECT_NE(widget("expression")->string.value().find("quantity"), std::string::npos);
  ASSERT_TRUE(project().table()->definition(0, 5));
  EXPECT_EQ(*project().table()->cell(0, 5), 310);
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", samples},
      {"record_id", row_a}, {"field_id", temperature}, {"value", 305}}})));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 5), 315);
  ASSERT_TRUE(project().table()->definition(0, 5));
  EXPECT_EQ(project().table()->definition(0, 5)->at("kind"), "expression");
  ASSERT_TRUE(project().close());
  ASSERT_TRUE(pump([&] { return !project().project() && !project().busy(); }));
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 5), 315);
  ASSERT_TRUE(project().table()->definition(0, 5));
  EXPECT_EQ(project().table()->definition(0, 5)->at("kind"), "expression");
}

TEST_F(TableWorkbenchEditorPython, FieldChoiceRenameAndRepeatedReorderPreserveIdsAndStoredSelection)
{
  const std::string wet = "cfffffff-ffff-4fff-8fff-ffffffffffff";
  const std::string desorbed = "d1111111-1111-4111-8111-111111111111";
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_field_schema"}, {"id", phase},
      {"type", "single_select"}, {"unit", nullptr}, {"options", {{"version", 1},
        {"choices", Json::array({
          {{"id", dry}, {"label", "Dry"}, {"color", "#123456"}},
          {{"id", wet}, {"label", "Wet"}, {"color", "#234567"}},
          {{"id", desorbed}, {"label", "Desorbed"}, {"color", "#345678"}}
        })}}}}})));
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto revision = project().project()->revision;
  edit_field(4);
  const auto dry_label = "option" + dry + "/label";
  assign(dry_label.c_str(), "Dried");
  assign("field_name", "Sample state");
  const auto up_key = "option" + desorbed + "/up";
  const auto *up = widget(up_key.c_str());
  ASSERT_NE(up, nullptr);
  ASSERT_TRUE(up->enabled && up->on_click);
  const auto same_choice_up = up->on_click;
  same_choice_up(); frame();
  same_choice_up(); frame();  // The retained event must still mean the same choice UUID.
  action("add_field");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  const auto &field = project().table()->fields[3];
  EXPECT_EQ(field.id, phase);
  EXPECT_EQ(field.name, "Sample state");
  const auto &choices = field.options.at("choices");
  ASSERT_EQ(choices.size(), 3u);
  EXPECT_EQ(choices[0].at("id"), desorbed);
  EXPECT_EQ(choices[1].at("id"), dry);
  EXPECT_EQ(choices[1].at("label"), "Dried");
  EXPECT_EQ(choices[1].at("color"), "#123456");
  EXPECT_EQ(choices[2].at("id"), wet);
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
  EXPECT_EQ(widget("records")->table->cell(0, 4), "Dried");
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().table()->fields[3].name, "State");
  EXPECT_EQ(project().table()->fields[3].options.at("choices").at(0).at("id"), dry);
  EXPECT_EQ(project().table()->fields[3].options.at("choices").at(0).at("label"), "Dry");
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
}

TEST_F(TableWorkbenchEditorPython, SchemaDraftBlocksEditorCloseAndOldBindingsCannotChangeANewFieldForm)
{
  edit_field(4);
  assign("field_name", "Abandoned state name");
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  const auto old_name = widget("field_name")->string;
  const auto old_type = widget("field_type")->index;
  const auto old_save = widget("add_field")->on_click;
  const auto old_tabs = area().tab_count();
  const auto *editor = &area().editor();
  area().close_tab(area().active_tab());
  frame();
  EXPECT_EQ(area().tab_count(), old_tabs);
  EXPECT_EQ(&area().editor(), editor);
  index("table", 1);
  EXPECT_EQ(project().table_id(), samples);
  send(ui::Event::key_down(ui::Key::Escape));  // Explicitly cancel the field form and its draft.
  ASSERT_FALSE(area().editor().has_unsaved_changes());

  edit_field(1);
  assign("field_name", "Current temperature name");
  const auto revision = project().project()->revision;
  old_name.assign("Stale field name");
  old_type.assign(7);
  old_save(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NE(widget("field_name"), nullptr);
  EXPECT_EQ(widget("field_name")->string.value(), "Current temperature name");
  EXPECT_EQ(widget("field_type")->index.value(), 2);
  EXPECT_EQ(project().table()->fields[0].name, "Temperature");
  EXPECT_EQ(project().table()->fields[3].name, "State");
  send(ui::Event::key_down(ui::Key::Escape));
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST_F(TableWorkbenchEditorPython, RenamingAnObjectFieldPreservesItsAllowedReferenceKinds)
{
  edit_field(5);
  assign("field_name", "Renamed evidence");
  action("add_field");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().table()->fields[4].id, evidence);
  EXPECT_EQ(project().table()->fields[4].name, "Renamed evidence");
  EXPECT_EQ(project().table()->fields[4].options.at("kinds"), Json::array({"record", "file"}));
}

TEST_F(TableWorkbenchEditorPython, ClosedViewBuilderCannotSaveOrChangeTheNewBuildersName)
{
  click("table_settings");
  assign("table_view_name", "Abandoned view");
  const auto old_name = widget("table_view_name")->string;
  const auto old_save = widget("table_view_save")->on_click;
  action("table_view_done");
  click("table_settings");
  assign("table_view_name", "Current view");
  const auto revision = project().project()->revision;
  old_name.assign("Stale view name");
  old_save(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NE(widget("table_view_name"), nullptr);
  EXPECT_EQ(widget("table_view_name")->string.value(), "Current view");
  action("table_view_discard");
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST(TableWorkbenchLayout, MalformedSavedViewStateIsRejectedWithoutChangingTheCurrentState)
{
  TableWorkbench workbench;
  const auto initial = workbench.save_state();
  EXPECT_TRUE(workbench.load_state(Json::object()));
  EXPECT_EQ(workbench.save_state(), initial);
  for (const auto &bad_columns : {Json::array({3}), Json::array({{{"field_id", temperature}, {"width", "wide"}, {"hidden", false}}})}) {
    auto invalid = initial;
    invalid["view"]["columns"] = bad_columns;
    EXPECT_FALSE(workbench.load_state(invalid));
    EXPECT_EQ(workbench.save_state(), initial);
  }
  auto invalid = initial;
  invalid["view"]["filters"] = {{"op", "and"}, {"conditions", 3}};
  EXPECT_FALSE(workbench.load_state(invalid));
  EXPECT_EQ(workbench.save_state(), initial);
  EXPECT_TRUE(workbench.load_state(initial));
}
}  // namespace
}  // namespace stk::app
