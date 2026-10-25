/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "support.hh"

#include <map>

using namespace stk::ui;
using stk::ui::test::Harness;

namespace {
struct Grid {
  Harness h;
  TableSelection selected{{0, 0}, {0, 0}};
  std::vector<std::vector<std::string>> values{{"c", "C", "false"}, {"a", "A", "true"}, {"b", "B", "false"}};
  std::map<std::pair<int, int>, std::string> drafts;
  std::map<std::string, float> widths;
  std::vector<TableColumn> columns{{"Name", 6, true, false, "name"}, {"Value", 6, true, false, "value"}, {"Flag", 6, false, false, "flag"}};
  std::vector<int> pasted_rows, cleared_rows;
  std::string pasted_text;
  int pasted_column = -1, cleared_column = -1, cleared_columns = -1;
  int commits = 0, cancels = 0, toggles = 0, menu_calls = 0;
  bool accept = true, commit_ok = true, visible = true, styles = false, menus = false;
  int frozen = 0, first_column = 0;
  float width = 480;
  uint64_t version = 1;
  bool fill_enabled = false, enabled = true, modal = false;
  int fills = 0;
  int fill_limits = 0;
  float visible_rows = 4;
  std::vector<TableFillCell> filled;

  explicit Grid(float scale = 1) : h(scale)
  {
    h.window = {600 * scale, 600 * scale};
    h.ui = [this](Context &ctx) {
      auto &layout = ctx.block("r", {0, 0, width * h.ctx->scale(), h.window.y - 50 * h.ctx->scale()}).layout();
      if (!visible) { return; }
      TableSpec spec;
      spec.columns = columns;
      spec.rows = int(values.size()); spec.visible_rows = visible_rows;
      spec.data_version = version; spec.frozen_columns = frozen;
      spec.cell = [](int, int) { return std::string("short"); };
      spec.compare = [this](int a, int b, int column) { return values[size_t(a)][size_t(column)].compare(values[size_t(b)][size_t(column)]); };
      spec.column_width = [this](std::string_view key) -> std::optional<float> {
        const auto found = widths.find(std::string(key));
        return found == widths.end() ? std::nullopt : std::optional<float>(found->second);
      };
      spec.on_column_width = [this](std::string_view key, float value) { widths[std::string(key)] = value; };
      if (menus) {
        spec.column_menu = [this](int) { return std::vector<MenuEntry>{{"Unavailable", {}, false}, {"Inspect", [this] { ++menu_calls; }}}; };
      }
      TableGridSpec grid;
      grid.first_column = first_column;
      grid.selection = {[this] { return selected; }, [this](TableSelection value) { if (accept) { selected = value; } }};
      grid.editable = [](TableCell cell) { return cell.column != 2; };
      grid.edit_text = [this](TableCell cell) {
        const auto found = drafts.find({cell.row, cell.column});
        return found == drafts.end() ? values[size_t(cell.row)][size_t(cell.column)] : found->second;
      };
      grid.on_change = [this](TableCell cell, std::string text) { drafts[{cell.row, cell.column}] = std::move(text); };
      grid.on_commit = [this](TableCell cell, std::string text) {
        ++commits;
        if (!commit_ok) { return false; }
        values[size_t(cell.row)][size_t(cell.column)] = std::move(text);
        drafts.erase({cell.row, cell.column});
        ++version;
        return true;
      };
      grid.on_cancel = [this](TableCell cell) { ++cancels; drafts.erase({cell.row, cell.column}); };
      grid.export_cell = [this](int row, int column) { return values[size_t(row)][size_t(column)]; };
      grid.on_paste = [this](const std::vector<int> &rows, int column, std::string text) {
        pasted_rows = rows; pasted_column = column; pasted_text = std::move(text); return false;
      };
      grid.on_clear = [this](const std::vector<int> &rows, int column, int count) {
        cleared_rows = rows; cleared_column = column; cleared_columns = count; return false;
      };
      grid.on_toggle = [this](TableCell cell) {
        ++toggles;
        auto &value = values[size_t(cell.row)][size_t(cell.column)];
        value = value == "true" ? "false" : "true";
        return true;
      };
      if (fill_enabled) { grid.on_fill = [this](const std::vector<TableFillCell> &cells) { ++fills; filled = cells; return true; }; }
      grid.on_fill_limit = [this] { ++fill_limits; };
      if (styles) {
        grid.cell_style = [](int, int column) { return column == 2 ? TableCellStyle::Checkbox : column == 1 ? TableCellStyle::Badge : TableCellStyle::Text; };
        grid.checked = [this](int row, int column) { return values[size_t(row)][size_t(column)] == "true"; };
      }
      spec.grid = std::move(grid);
      layout.table("t", std::move(spec)).disable(!enabled);
      layout.text_field("outside", bind(outside));
      if (modal) { ctx.modal("modal", "Modal", [this] { modal = false; }).label("Modal"); }
    };
    h.frame();
  }
  std::string outside;
  Vec2 cell(int row, int column) {
    const auto &rect = h.w("t").rect;
    const float u = h.ctx->style().unit, p = h.ctx->style().pixel;
    return {rect.x + p + (column * 6 + 2) * u, rect.y + p + (row + 1.5f) * u};
  }
  Vec2 header(int column) {
    auto result = cell(0, column); result.y -= h.ctx->style().unit; return result;
  }
  Vec2 handle(int row, int column) {
    const auto &rect = h.w("t").rect;
    const float u = h.ctx->style().unit;
    return {rect.x + (column + 1) * 6 * u - .175f * u, rect.y + (row + 2) * u - .175f * u};
  }
};
}  // namespace

TEST(TableGrid, FillRepeatsSortedRectangleOnceOnReleaseWithoutChangingSelection)
{
  for (const float scale : {1.0f, 2.0f}) {
    Grid g(scale); g.fill_enabled = true; g.h.frame();
    g.h.click(g.header(0)); // Visible a,b,c => model 1,2,0.
    g.h.drag(g.cell(0, 0), g.cell(1, 1));
    const auto selected = g.selected;
    g.h.send(Event::mouse_down(g.handle(1, 1)));
    g.h.move(g.cell(2, 1));
    EXPECT_EQ(g.fills, 0);
    EXPECT_EQ(g.selected, selected);
    g.h.send(Event::mouse_up(g.cell(2, 1)));
    EXPECT_EQ(g.fills, 1);
    EXPECT_EQ(g.filled, (std::vector<TableFillCell>{{{1, 0}, {0, 0}}, {{1, 1}, {0, 1}}}));
    EXPECT_EQ(g.selected, selected);
    EXPECT_EQ(g.commits, 0);
  }
}

TEST(TableGrid, FillUpAndLeftRepeatPatternAndNeverIncludeRowLabels)
{
  Grid g; g.fill_enabled = true; g.h.frame();
  g.h.drag(g.cell(1, 1), g.cell(2, 1));
  g.h.drag(g.handle(2, 1), g.cell(0, 1));
  EXPECT_EQ(g.filled, (std::vector<TableFillCell>{{{2, 1}, {0, 1}}}));
  g.h.drag(g.cell(0, 1), g.cell(0, 2));
  g.h.drag(g.handle(0, 2), g.cell(0, 0));
  EXPECT_EQ(g.filled, (std::vector<TableFillCell>{{{0, 2}, {0, 0}}}));
  EXPECT_EQ(g.fills, 2);
  g.first_column = 1; g.h.frame();
  g.h.drag(g.handle(0, 2), g.cell(0, 0));
  EXPECT_EQ(g.fills, 2);
}

TEST(TableGrid, FillCancelsOnEscapeFocusLossVersionSelectionDisabledAndModal)
{
  for (int reason = 0; reason < 7; ++reason) {
    SCOPED_TRACE(reason);
    Grid g; g.fill_enabled = true; g.h.frame();
    g.h.send(Event::mouse_down(g.handle(0, 0)));
    g.h.move(g.cell(2, 0));
    switch (reason) {
      case 0: g.h.key(Key::Escape); break;
      case 1: { Event e; e.type = EventType::FocusLost; g.h.send(e); break; }
      case 2: ++g.version; break;
      case 3: g.selected = {{1, 0}, {1, 0}}; break;
      case 4: g.enabled = false; break;
      case 5: g.modal = true; break;
      case 6: g.visible = false; break;
    }
    g.h.frame();
    g.h.send(Event::mouse_up({60, 80}));
    EXPECT_EQ(g.fills, 0);
  }
}

TEST(TableGrid, FillIgnoresNonLeftReleaseAndReleaseOutsideOrWithoutExtension)
{
  Grid g; g.fill_enabled = true; g.h.frame();
  g.h.click(g.handle(0, 0));
  EXPECT_EQ(g.fills, 0);
  g.h.send(Event::mouse_down(g.handle(0, 0)));
  g.h.move(g.cell(2, 0));
  g.h.send(Event::mouse_up(g.cell(2, 0), MouseButton::Right));
  EXPECT_EQ(g.fills, 0);
  EXPECT_NE(g.h.ctx->active(), 0);
  g.h.send(Event::mouse_up({590, 590}));
  EXPECT_EQ(g.fills, 0);
  EXPECT_EQ(g.h.ctx->active(), 0);
}

TEST(TableGrid, FillLimitReportsWithoutSendingAPartialBatch)
{
  Grid g; g.fill_enabled = true; g.values.resize(400, {"a", "A", "false"});
  g.visible_rows = 400; g.h.window.y = 10000; g.h.frame();
  g.h.drag(g.cell(0, 0), g.cell(0, 2));
  g.h.drag(g.handle(0, 2), g.cell(399, 2));
  EXPECT_EQ(g.fills, 0);
  EXPECT_EQ(g.fill_limits, 1);
  g.h.drag(g.handle(0, 2), g.cell(333, 2));
  EXPECT_EQ(g.fills, 1);
  EXPECT_EQ(g.filled.size(), 999u);
  EXPECT_EQ(g.fill_limits, 1);
}

TEST(TableGrid, SortedRectangleExportsCompleteQuotedValuesAndPlansPasteWithoutMutation)
{
  Grid g;
  g.values[1][1] = "A\tfull\n\"quoted\"";
  g.h.frame();
  g.h.click(g.header(0)); // a,b,c; model rows 1,2,0.
  g.h.click(g.cell(0, 0));
  g.h.key(Key::Down, MOD_SHIFT);
  g.h.key(Key::Right, MOD_SHIFT);
  EXPECT_EQ(g.selected, (TableSelection{{1, 0}, {2, 1}}));
  g.h.key(Key::C, MOD_CTRL);
  EXPECT_EQ(g.h.clipboard.text, "a\t\"A\tfull\n\"\"quoted\"\"\"\nb\tB");
  g.h.clipboard.text = "17\t18\r\n19\t20";
  const auto original = g.values;
  g.h.key(Key::V, MOD_CTRL);
  EXPECT_EQ(g.pasted_rows, (std::vector<int>{1, 2, 0}));
  EXPECT_EQ(g.pasted_column, 0);
  EXPECT_EQ(g.pasted_text, "17\t18\r\n19\t20");
  EXPECT_EQ(g.values, original) << "the UI does not apply part of a rejected paste";
  g.h.key(Key::Delete);
  EXPECT_EQ(g.cleared_rows, (std::vector<int>{1, 2}));
  EXPECT_EQ(g.cleared_column, 0); EXPECT_EQ(g.cleared_columns, 2);
  EXPECT_EQ(g.values, original);
}

TEST(TableGrid, PointerDragExtendsRectangleAndRejectedSelectionsDoNotMoveOrEdit)
{
  Grid g;
  g.h.drag(g.cell(0, 0), g.cell(2, 1));
  EXPECT_EQ(g.selected, (TableSelection{{0, 0}, {2, 1}}));
  const auto accepted = g.selected;
  g.accept = false;
  g.h.key(Key::Right);
  EXPECT_EQ(g.selected, accepted);
  g.h.click(g.cell(1, 0));
  EXPECT_EQ(g.selected, accepted);
  EXPECT_EQ(g.h.ctx->editing(), 0);
  EXPECT_TRUE(g.drafts.empty());
  EXPECT_EQ(g.commits, 0);
}

TEST(TableGrid, ExplicitCommitRetainsInvalidDraftAndBlurDisappearAndRevisionNeverWrite)
{
  Grid g;
  g.h.click(g.cell(0, 0));
  g.h.key(Key::F2);
  g.h.type("changed");
  EXPECT_EQ(g.drafts.at({0, 0}), "changed");
  g.commit_ok = false;
  g.h.key(Key::Enter);
  EXPECT_EQ(g.commits, 1);
  ASSERT_NE(g.h.ctx->edit_state(), nullptr);
  EXPECT_EQ(g.h.ctx->edit_state()->text(), "changed");
  EXPECT_EQ(g.selected.active, (TableCell{0, 0}));
  g.h.click("outside");
  EXPECT_EQ(g.commits, 1); EXPECT_EQ(g.drafts.at({0, 0}), "changed");
  g.h.click(g.cell(0, 0)); g.h.key(Key::F2);
  EXPECT_EQ(g.h.ctx->edit_state()->text(), "changed");
  g.visible = false; g.h.frame();
  EXPECT_EQ(g.commits, 1); EXPECT_EQ(g.drafts.at({0, 0}), "changed");
  g.visible = true; g.h.frame(); g.h.click(g.cell(0, 0)); g.h.key(Key::F2);
  ++g.version; g.h.frame();
  EXPECT_EQ(g.h.ctx->editing(), 0); EXPECT_EQ(g.commits, 1);
  g.drafts.clear(); // The application explicitly discarded its persistent draft.
  g.h.key(Key::F2);
  ASSERT_NE(g.h.ctx->edit_state(), nullptr);
  EXPECT_EQ(g.h.ctx->edit_state()->text(), "c");
  g.h.key(Key::Escape);
  EXPECT_EQ(g.cancels, 1);
}

TEST(TableGrid, TypingImeAndDoubleClickUseTheTextEditorAndTabNavigatesCells)
{
  Grid g;
  g.h.click(g.cell(0, 0));
  g.h.send(Event::ime_preedit("聚合物", 3));
  ASSERT_NE(g.h.ctx->edit_state(), nullptr);
  EXPECT_TRUE(g.h.ctx->edit_state()->composing());
  g.h.key(Key::Enter); // IME owns confirmation, not the database.
  EXPECT_EQ(g.commits, 0);
  g.h.send(Event::ime_commit("聚合物"));
  EXPECT_EQ(g.drafts.at({0, 0}), "聚合物");
  g.h.key(Key::Tab);
  EXPECT_EQ(g.commits, 1); EXPECT_EQ(g.values[0][0], "聚合物");
  EXPECT_EQ(g.selected.active, (TableCell{0, 1}));
  g.h.key(Key::Tab, MOD_SHIFT);
  EXPECT_EQ(g.selected.active, (TableCell{0, 0}));
  g.h.type("replacement");
  EXPECT_EQ(g.drafts.at({0, 0}), "replacement");
  g.h.key(Key::Escape);
  // True double-click, unlike Harness::click which separates successive clicks by one second.
  const auto point = g.cell(1, 1);
  g.h.click(point);
  g.h.t -= 0.9;
  g.h.click(point);
  ASSERT_NE(g.h.ctx->edit_state(), nullptr);
  EXPECT_EQ(g.h.ctx->edit_state()->text(), "A");
}

TEST(TableGrid, FrozenColumnKeepsHitSelectionAndEditorCaretAlignedAfterLargeHorizontalScroll)
{
  for (const float scale : {1.0f, 1.5f, 2.0f}) {
    Grid g(scale); g.width = 300; g.frozen = 1; g.h.frame();
    g.h.send(Event::wheel(g.cell(0, 0), -1000, 0, MOD_SHIFT));
    g.h.click(g.cell(0, 0));
    EXPECT_EQ(g.selected.active, (TableCell{0, 0}));
    const Rect rect = g.h.w("t").rect;
    const float u = g.h.ctx->style().unit, p = g.h.ctx->style().pixel;
    const float maximum = 18 * u - (rect.w - 2 * p - g.h.ctx->style().scrollbar);
    g.h.click({rect.x + p + 14 * u - maximum, g.cell(0, 0).y});
    EXPECT_EQ(g.selected.active, (TableCell{0, 2}));
    g.h.key(Key::Left); g.h.key(Key::F2);
    ASSERT_NE(g.h.ctx->edit_state(), nullptr);
    const Rect caret = g.h.ctx->text_input_rect();
    EXPECT_GE(caret.x, rect.x + p + 6 * u);
    EXPECT_LE(caret.x1(), rect.x1());
    g.h.key(Key::Escape);
    g.h.key(Key::Home); g.h.key(Key::F2);
    EXPECT_LT(g.h.ctx->text_input_rect().x, rect.x + p + 6 * u);
  }
}

TEST(TableGrid, WidthKeysSurviveReorderingAndExternalWidthsControlTheSameGeometry)
{
  Grid g;
  const float u = g.h.ctx->style().unit, p = g.h.ctx->style().pixel;
  const Rect rect = g.h.w("t").rect;
  const Vec2 edge{rect.x + p + 6 * u, g.header(0).y};
  g.h.drag(edge, {edge.x + 2 * u, edge.y});
  EXPECT_NEAR(g.widths.at("name"), 8, 0.01);
  std::swap(g.columns[0], g.columns[1]);
  ++g.version; g.h.frame();
  g.widths["value"] = 3;
  g.h.frame();
  g.h.click({rect.x + p + 4 * u, g.cell(0, 0).y});
  EXPECT_EQ(g.selected.active.column, 1) << "the first column is now value, with externally set width 3";
  g.h.key(Key::F2);
  EXPECT_GE(g.h.ctx->text_input_rect().x, rect.x + p + 3 * u);
}

TEST(TableGrid, ColumnMenuUsesDisabledEntriesAndDropsWhenItsDataChanges)
{
  Grid g; g.menus = true; g.h.frame();
  g.h.send(Event::mouse_down(g.header(0), MouseButton::Right));
  ASSERT_TRUE(g.h.ctx->popup_open());
  g.h.key(Key::Down); g.h.key(Key::Enter);
  EXPECT_EQ(g.menu_calls, 1);
  g.h.send(Event::mouse_down(g.header(0), MouseButton::Right));
  ASSERT_TRUE(g.h.ctx->popup_open());
  ++g.version; g.h.frame();
  EXPECT_FALSE(g.h.ctx->popup_open());
  EXPECT_EQ(g.menu_calls, 1);
}

TEST(TableGrid, CheckboxAndBadgeAreOptionalAndReadonlyCellsDoNotStartEditing)
{
  Grid g; g.styles = true; g.h.frame();
  g.h.click(g.cell(0, 2));
  EXPECT_EQ(g.toggles, 1); EXPECT_EQ(g.values[0][2], "true");
  g.h.key(Key::F2); g.h.type("not editable");
  EXPECT_EQ(g.h.ctx->editing(), 0); EXPECT_TRUE(g.drafts.empty());
  g.h.key(Key::Space);
  EXPECT_EQ(g.toggles, 2); EXPECT_EQ(g.values[0][2], "false");
  bool check = false;
  for (const auto &command : g.h.ctx->draw_list().cmds) { check |= command.tria == Tria::Check; }
  EXPECT_TRUE(check) << "another checked model row is still rendered";
}

TEST(TableGrid, MacClipboardUsesCommandAndDensitySharesRenderHitAndNavigation)
{
  Grid g;
  ContextConfig config;
  config.measurer = &g.h.measurer; config.clipboard = &g.h.clipboard;
  config.catalog = &g.h.catalog; config.mac_shortcuts = true;
  g.h.ctx = std::make_unique<Context>(config);
  g.h.ui = [&](Context &ctx) {
    TableSpec spec;
    spec.columns = {{"A", 6}}; spec.rows = 3; spec.row_height = 1.5f;
    TableGridSpec grid;
    grid.selection = bind(g.selected);
    grid.export_cell = [&](int row, int) { return g.values[size_t(row)][0]; };
    spec.grid = std::move(grid);
    ctx.block("density", {0, 0, 300, 500}).layout().table("t", std::move(spec));
  };
  g.h.frame();
  const auto rect = g.h.w("t").rect;
  const float row = 1.5f * g.h.ctx->style().unit;
  g.h.click({rect.x + 20, rect.y + g.h.ctx->style().pixel + 2.5f * row});
  EXPECT_EQ(g.selected.active, (TableCell{1, 0}));
  g.h.clipboard.text = "unchanged";
  g.h.key(Key::C, MOD_CTRL);
  EXPECT_EQ(g.h.clipboard.text, "unchanged");
  g.h.key(Key::C, MOD_SUPER);
  EXPECT_EQ(g.h.clipboard.text, "a");
  g.h.key(Key::Down);
  EXPECT_EQ(g.selected.active, (TableCell{2, 0}));
}

TEST(TableGrid, LegacyRowOnlyTablesDoNotAcquireCellEditingOrClipboardShortcuts)
{
  Harness h;
  int row = 0, cell_calls = 0;
  std::string other;
  h.ui = [&](Context &ctx) {
    auto &layout = ctx.block("legacy", {0, 0, 400, 500}).layout();
    TableSpec spec;
    spec.columns = {{"Legacy", 6}}; spec.rows = 3;
    spec.cell = [](int r, int) { return std::to_string(r); };
    spec.selected = bind(row);
    spec.on_cell_select = [&](int, int) { ++cell_calls; };
    layout.table("t", std::move(spec));
    layout.text_field("other", bind(other));
  };
  h.frame();
  const auto rect = h.w("t").rect;
  h.click({rect.x + 20, rect.y + h.ctx->style().pixel + 1.5f * h.ctx->style().unit});
  h.key(Key::Down);
  EXPECT_EQ(row, 1); EXPECT_EQ(cell_calls, 1);
  h.key(Key::F2); h.key(Key::Enter); h.type("new");
  EXPECT_EQ(h.ctx->editing(), 0);
  h.clipboard.text = "original";
  h.key(Key::C, MOD_CTRL);
  EXPECT_EQ(h.clipboard.text, "original");
  h.key(Key::Tab);
  EXPECT_EQ(h.ctx->focused(), h.w("other").id);
}

TEST(TableGrid, RowLabelsMapToFirstDataCellAndStayOutsideSelectionAndClipboard)
{
  Grid g; g.first_column = 1; g.frozen = 1; g.h.frame();
  g.h.click(g.cell(0, 0));
  EXPECT_EQ(g.selected, (TableSelection{{0, 1}, {0, 1}}));
  g.h.key(Key::Left); g.h.key(Key::Home);
  EXPECT_EQ(g.selected.active, (TableCell{0, 1}));
  g.h.key(Key::Tab); g.h.key(Key::Tab);
  EXPECT_EQ(g.selected.active, (TableCell{1, 1}));
  g.h.key(Key::Tab, MOD_SHIFT);
  EXPECT_EQ(g.selected.active, (TableCell{0, 2}));
  g.h.key(Key::A, MOD_CTRL);
  EXPECT_EQ(g.selected, (TableSelection{{0, 1}, {2, 2}}));
  g.h.key(Key::C, MOD_CTRL);
  EXPECT_EQ(g.h.clipboard.text, "C\tfalse\nA\ttrue\nB\tfalse");
  g.h.key(Key::Delete);
  EXPECT_EQ(g.cleared_column, 1); EXPECT_EQ(g.cleared_columns, 2);
  g.h.clipboard.text = "data";
  g.h.key(Key::V, MOD_CTRL);
  EXPECT_EQ(g.pasted_column, 1);
}

TEST(TableGrid, ExternalSortRequestsGlobalOrderWithoutLocallySortingTheCurrentPage)
{
  Harness h;
  int row = -1, requested_column = -1, calls = 0;
  bool ascending = false;
  std::vector<std::string> page{"c", "a", "b"};
  uint64_t version = 1;
  h.ui = [&](Context &ctx) {
    TableSpec spec;
    spec.columns = {{"Value", 8}}; spec.rows = int(page.size()); spec.data_version = version;
    spec.cell = [&](int r, int) { return page[size_t(r)]; };
    spec.selected = bind(row);
    spec.on_sort = [&](int c, bool up) { requested_column = c; ascending = up; ++calls; };
    ctx.block("remote", {0, 0, 400, 500}).layout().table("t", std::move(spec));
  };
  h.frame();
  const auto rect = h.w("t").rect;
  const float u = h.ctx->style().unit, p = h.ctx->style().pixel;
  const Vec2 header{rect.x + 20, rect.y + p + .5f * u};
  const Vec2 first{rect.x + 20, rect.y + p + 1.5f * u};
  h.click(header); h.click(first);
  EXPECT_EQ(calls, 1); EXPECT_EQ(requested_column, 0); EXPECT_TRUE(ascending);
  EXPECT_EQ(row, 0) << "an async request cannot reorder or edit a different current-page record";
  h.key(Key::Down); EXPECT_EQ(row, 1);
  page = {"global-first", "global-second", "global-third"}; ++version; h.frame();
  h.click(header); h.click(first);
  EXPECT_EQ(calls, 2); EXPECT_FALSE(ascending); EXPECT_EQ(row, 0);
}

TEST(TableGrid, SavedViewMaximumRowHeightUsesTheSameTallRowsForLayoutHitAndScroll)
{
  Harness h;
  TableSelection selection{{0, 0}, {0, 0}};
  h.ui = [&](Context &ctx) {
    TableSpec spec;
    spec.columns = {{"Tall", 6}}; spec.rows = 3; spec.visible_rows = 1;
    spec.row_height = 240.0f / 32.0f;
    spec.cell = [](int row, int) { return "row" + std::to_string(row); };
    TableGridSpec grid; grid.selection = bind(selection); spec.grid = std::move(grid);
    ctx.block("tall", {0, 0, 400, 500}).layout().table("t", std::move(spec));
  };
  h.frame();
  const auto rect = h.w("t").rect;
  const float height = 7.5f * h.ctx->style().unit, pixel = h.ctx->style().pixel;
  EXPECT_FLOAT_EQ(rect.h, 2 * height + 2 * pixel);
  const Vec2 first{rect.x + 20, rect.y + pixel + 1.5f * height};
  h.click(first); EXPECT_EQ(selection.active, (TableCell{0, 0}));
  h.key(Key::Down);
  EXPECT_EQ(selection.active, (TableCell{1, 0}));
  EXPECT_FLOAT_EQ(h.ctx->scroll_of(h.w("t").id), height);
  h.click(first); EXPECT_EQ(selection.active, (TableCell{1, 0}));
}
