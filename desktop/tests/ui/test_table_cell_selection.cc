/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "support.hh"

using namespace stk::ui;
using stk::ui::test::Harness;

TEST(TableCellSelection, BodyReportsModelRowAndActualColumnAfterRowSelection)
{
  for (const float scale : {1.0f, 1.5f, 2.0f}) {
    Harness h(scale);
    int selected = -1, cell_row = -1, cell_column = -1, calls = 0;
    h.ui = [&](Context &ctx) {
      TableSpec spec;
      spec.columns = {{"Name", 6}, {"Value", 6, true, true}, {"Object", 6}};
      spec.rows = 3;
      spec.visible_rows = 5;
      spec.cell = [](int row, int column) { return column == 1 ? std::to_string(3 - row) : "item"; };
      spec.selected = bind(selected);
      spec.on_cell_select = [&](int row, int column) {
        EXPECT_EQ(selected, row) << "row selection precedes cell selection";
        cell_row = row; cell_column = column; ++calls;
      };
      ctx.block("r", {0, 0, 300 * scale, 600 * scale}).layout().table("t", std::move(spec));
    };
    h.frame();
    const auto rect = h.w("t").rect;
    const auto &style = h.ctx->style();
    const float u = style.unit, p = style.pixel;
    h.click({rect.x + p + 7 * u, rect.y + p + 0.5f * u});  // Value ascending.
    EXPECT_EQ(calls, 0);
    h.click({rect.x + p + 7 * u, rect.y + p + 1.5f * u});
    EXPECT_EQ(cell_row, 2);
    EXPECT_EQ(cell_column, 1);
    h.key(Key::Down);
    EXPECT_EQ(selected, 1);
    EXPECT_EQ(calls, 1) << "keyboard row navigation retains the row-only contract";
    h.send(Event::wheel(h.center("t"), -1000, h.t, MOD_SHIFT));
    const float maximum = 18 * u - (rect.w - 2 * p - style.scrollbar);
    h.click({rect.x + p + 13 * u - maximum, rect.y + p + 1.5f * u});
    EXPECT_EQ(cell_row, 2);
    EXPECT_EQ(cell_column, 2) << "horizontal scrolling does not renumber columns";
    EXPECT_EQ(calls, 2);
    h.click({rect.x + p + 2 * u, rect.y + p + 4.5f * u});  // Empty body row.
    EXPECT_EQ(calls, 2);
    h.click({rect.x + 2 * p, rect.y1() - p - 0.5f * style.scrollbar});
    EXPECT_EQ(calls, 2) << "scrollbar clicks are not cell selections";
  }
}
