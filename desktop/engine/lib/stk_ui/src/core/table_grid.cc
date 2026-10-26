/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/ui.hh"

#include <algorithm>
#include <cmath>

namespace stk::ui {
namespace {
constexpr size_t clipboard_limit = 16 * 1024 * 1024;
constexpr size_t selection_limit = 100000;

bool valid(const TableSpec &table, TableCell cell)
{
  return cell.row >= 0 && cell.row < table.rows && cell.column >= 0 &&
         size_t(cell.column) < table.columns.size();
}

std::string tsv_quote(std::string_view value)
{
  if (value.find_first_of("\t\r\n\"") == std::string_view::npos) { return std::string(value); }
  std::string result = "\"";
  for (const char c : value) { result += c; if (c == '"') { result += '"'; } }
  return result + '"';
}
}  // namespace

Rect Context::table_column_rect(const Widget &w, const int column)
{
  const int frozen = std::clamp(w.table->frozen_columns, 0, int(w.table->columns.size()));
  float x = w.rect.x + style_.pixel;
  for (int c = 0; c < column; ++c) { x += table_col_px(w, c); }
  if (column >= frozen) { x -= table_scroll_x(w); }
  return {x, w.rect.y + style_.pixel, table_col_px(w, column), list_row_height(w)};
}

Rect Context::table_column_clip(const Widget &w, const int column)
{
  const int frozen = std::clamp(w.table->frozen_columns, 0, int(w.table->columns.size()));
  float width = 0;
  for (int c = 0; c < frozen; ++c) { width += table_col_px(w, c); }
  const Rect area{w.rect.x + style_.pixel, w.rect.y + style_.pixel,
                  std::max(0.0f, w.rect.w - 2 * style_.pixel - style_.scrollbar),
                  std::max(0.0f, w.rect.h - 2 * style_.pixel)};
  if (column < frozen) { return area.intersect({area.x, area.y, width, area.h}); }
  const float x = std::min(area.x1(), area.x + width);
  return {x, area.y, std::max(0.0f, area.x1() - x), area.h};
}

int Context::table_view_row(const Widget &w, const int model_row)
{
  const auto &order = table_perm(w);
  const auto found = std::find(order.begin(), order.end(), model_row);
  return found == order.end() ? -1 : int(found - order.begin());
}

Rect Context::table_cell_rect(const Widget &w, const TableCell cell)
{
  if (!valid(*w.table, cell)) { return {}; }
  const int row = table_view_row(w, cell.row);
  if (row < 0) { return {}; }
  Rect result = table_column_rect(w, cell.column);
  result.y = list_body(w).y + row * list_row_height(w) - scroll_of(w.id);
  return result;
}

TableCell Context::table_hit_cell(const Widget &w, const Vec2 position)
{
  const Rect body = list_body(w);
  if (!body.contains(position)) { return {}; }
  const int row = int((position.y - body.y + scroll_of(w.id)) / list_row_height(w));
  if (row < 0 || row >= w.table->rows) { return {}; }
  for (int c = 0; c < int(w.table->columns.size()); ++c) {
    Rect cell = table_column_rect(w, c);
    cell.y = body.y; cell.h = body.h;
    if (cell.intersect(table_column_clip(w, c)).contains(position)) {
      return {table_perm(w)[size_t(row)], c};
    }
  }
  return {};
}

Rect Context::table_fill_handle(const Widget &w)
{
  if (!w.enabled || edit_.id || !w.table || !w.table->grid || !w.table->grid->on_fill ||
      w.table->rows > int(selection_limit)) { return {}; }
  const auto &grid = *w.table->grid;
  const auto s = grid.selection.value();
  if (!valid(*w.table, s.anchor) || !valid(*w.table, s.active) ||
      std::min(s.anchor.column, s.active.column) < std::max(0, grid.first_column)) { return {}; }
  const int a = table_view_row(w, s.anchor.row), b = table_view_row(w, s.active.row);
  if (a < 0 || b < 0) { return {}; }
  const int column = std::max(s.anchor.column, s.active.column);
  const Rect cell = table_cell_rect(w, {table_perm(w)[size_t(std::max(a, b))], column});
  const float side = std::max(3 * style_.pixel, .35f * style_.unit);
  const Rect handle{cell.x1() - side - style_.pixel, cell.y1() - side - style_.pixel, side, side};
  const Rect clip = table_column_clip(w, column).intersect(list_body(w)).intersect(w.clip);
  if (handle.x < clip.x || handle.y < clip.y || handle.x1() > clip.x1() || handle.y1() > clip.y1()) { return {}; }
  return handle;
}

bool Context::table_fill_current(const Widget &w)
{
  if (drag_.kind != DragState::Kind::TableFill || drag_.id != w.id || !w.enabled || edit_.id ||
      popup_.owner || !w.table || !w.table->grid || !w.table->grid->on_fill ||
      w.table->data_version != drag_.table_version || w.table->columns.size() != drag_.table_columns ||
      w.table->grid->selection.value() != drag_.fill_selection || table_perm(w) != drag_.fill_order) { return false; }
  for (auto it = blocks_.rbegin(); it != blocks_.rend(); ++it) {
    if ((*it)->kind() == Block::Kind::Modal) { return it->get() == w.block; }
  }
  return true;
}

std::vector<TableFillCell> Context::table_fill_cells(const Widget &w, bool *over_limit)
{
  if (over_limit) { *over_limit = false; }
  if (!table_fill_current(w) || !valid(*w.table, drag_.fill_target)) { return {}; }
  const auto s = drag_.fill_selection;
  const int a = table_view_row(w, s.anchor.row), b = table_view_row(w, s.active.row);
  const int row = table_view_row(w, drag_.fill_target.row), col = drag_.fill_target.column;
  const int top = std::min(a, b), bottom = std::max(a, b);
  const int left = std::min(s.anchor.column, s.active.column), right = std::max(s.anchor.column, s.active.column);
  if (top < 0 || row < 0 || left < std::max(0, w.table->grid->first_column)) { return {}; }
  const int dy = row < top ? row - top : row > bottom ? row - bottom : 0;
  const int dx = col < left ? col - left : col > right ? col - right : 0;
  if (!dy && !dx) { return {}; }
  // A diagonal gesture extends only its dominant physical axis.
  const bool vertical = dy && (!dx || std::fabs(drag_.last.y - drag_.start.y) >= std::fabs(drag_.last.x - drag_.start.x));
  const int r0 = vertical ? (dy < 0 ? row : bottom + 1) : top;
  const int r1 = vertical ? (dy < 0 ? top - 1 : row) : bottom;
  const int c0 = vertical ? left : (dx < 0 ? col : right + 1);
  const int c1 = vertical ? right : (dx < 0 ? left - 1 : col);
  if (c0 < std::max(0, w.table->grid->first_column)) { return {}; }
  if (int64_t(r1 - r0 + 1) * int64_t(c1 - c0 + 1) > 1000) {
    if (over_limit) { *over_limit = true; }
    return {};
  }
  const auto mod = [](int n, int d) { return (n % d + d) % d; };
  std::vector<TableFillCell> result;
  for (int r = r0; r <= r1; ++r) {
    for (int c = c0; c <= c1; ++c) {
      result.push_back({{drag_.fill_order[size_t(top + mod(r - top, bottom - top + 1))],
                         left + mod(c - left, right - left + 1)}, {drag_.fill_order[size_t(r)], c}});
    }
  }
  return result;
}

bool Context::table_select(const Widget &w, const TableCell cell, const bool extend)
{
  if (!w.table->grid || !valid(*w.table, cell)) { return false; }
  const int first = std::max(0, w.table->grid->first_column);
  if (size_t(first) >= w.table->columns.size()) { return false; }
  const TableCell target{cell.row, std::max(first, cell.column)};
  const auto &binding = w.table->grid->selection;
  if (!binding || !binding.set) { return false; }
  TableSelection requested = binding.value();
  if (!extend || !valid(*w.table, requested.anchor) || requested.anchor.column < first) { requested.anchor = target; }
  requested.active = target;
  binding.assign(requested);
  // The application may reject a selection change to protect a persistent draft.
  if (binding.value() != requested) { return false; }
  table_reveal(w, target);
  redraw_ = true;
  return true;
}

void Context::table_reveal(const Widget &w, const TableCell cell)
{
  const Rect body = list_body(w);
  const float height = list_row_height(w);
  const int row = table_view_row(w, cell.row);
  if (row < 0) { return; }
  const float top = row * height;
  float scroll = scroll_of(w.id);
  if (top < scroll) { scroll = top; }
  else if (top + height > scroll + body.h) { scroll = top + height - body.h; }
  set_scroll(w.id, scroll, max_scroll(w));
  if (cell.column < std::clamp(w.table->frozen_columns, 0, int(w.table->columns.size()))) { return; }
  const Rect column = table_column_rect(w, cell.column), clip = table_column_clip(w, cell.column);
  auto &state = table_state(w);
  if (column.x < clip.x) { state.scroll_x += column.x - clip.x; }
  else if (column.x1() > clip.x1()) { state.scroll_x += column.x1() - clip.x1(); }
  state.scroll_x = std::clamp(state.scroll_x, 0.0f, table_scroll_max(w));
}

std::vector<int> Context::table_selection_rows(const Widget &w, const bool remaining)
{
  if (!w.table->grid) { return {}; }
  const auto selection = w.table->grid->selection.value();
  if (!valid(*w.table, selection.anchor) || !valid(*w.table, selection.active)) { return {}; }
  int a = table_view_row(w, selection.anchor.row), b = table_view_row(w, selection.active.row);
  if (a < 0 || b < 0) { return {}; }
  if (a > b) { std::swap(a, b); }
  if (remaining) { b = w.table->rows - 1; }
  if (size_t(b - a + 1) > selection_limit) { return {}; }
  const auto &order = table_perm(w);
  return {order.begin() + a, order.begin() + b + 1};
}

bool Context::begin_table_edit(const Widget &w, const bool replace)
{
  if (!w.enabled || !w.table || !w.table->grid) { return false; }
  const auto &grid = *w.table->grid;
  const TableCell cell = grid.selection.value().active;
  if (!valid(*w.table, cell) || cell.column < std::max(0, grid.first_column) || !grid.editable || !grid.editable(cell) || !grid.edit_text ||
      !grid.on_change || !grid.on_commit) { return false; }
  if (edit_.id) { commit_edit(); } // A prior grid editor is suspended, never implicitly committed.
  table_reveal(w, cell);
  edit_ = {};
  edit_.id = w.id;
  edit_.table = true;
  edit_.cell = cell;
  edit_.table_version = w.table->data_version;
  edit_.table_change = grid.on_change;
  edit_.table_cancel = grid.on_cancel;
  edit_.commit = [commit = grid.on_commit, cell](const std::string &text) { return commit(cell, text); };
  edit_.edit.set_text(replace ? std::string() : grid.edit_text(cell), !replace);
  focus_ = w.id;
  if (replace) { table_edit_changed(); }
  redraw_ = true;
  return true;
}

bool Context::table_edit_current() const
{
  const Widget *w = find_id(edit_.id);
  return edit_.table && w && w->enabled && w->table && w->table->grid &&
         w->table->data_version == edit_.table_version && valid(*w->table, edit_.cell) &&
         w->table->grid->selection.value().active == edit_.cell;
}

void Context::table_edit_changed()
{
  if (edit_.table && edit_.table_change) {
    const auto changed = edit_.table_change;
    changed(edit_.cell, edit_.edit.text());
  }
}

bool Context::commit_table_edit(const Event &e)
{
  if (!table_edit_current()) { commit_edit(); return true; }
  const Widget *w = find_id(edit_.id);
  const auto commit = edit_.commit;
  if (!commit || !commit(edit_.edit.text())) { redraw_ = true; return true; }
  edit_ = {};
  Event move = e;
  if (e.key == Key::Enter) { move.key = (e.mods & MOD_SHIFT) ? Key::Up : Key::Down; }
  move.mods &= ~MOD_SHIFT;
  // Tab's backward direction still needs Shift, but must not extend the rectangle.
  if (e.key == Key::Tab && (e.mods & MOD_SHIFT)) { move.mods |= MOD_SHIFT; }
  table_grid_key(*w, move);
  return true;
}

bool Context::table_grid_key(const Widget &w, const Event &e)
{
  if (!w.table || !w.table->grid || !w.enabled) { return false; }
  const auto &grid = *w.table->grid;
  const int first = std::max(0, grid.first_column);
  if (size_t(first) >= w.table->columns.size()) { return false; }
  const bool navigation = e.key == Key::Left || e.key == Key::Right || e.key == Key::Up || e.key == Key::Down ||
                          e.key == Key::Home || e.key == Key::End || e.key == Key::PageUp || e.key == Key::PageDown ||
                          e.key == Key::Tab || e.key == Key::Enter || e.key == Key::F2 || e.key == Key::Space ||
                          e.key == Key::Delete || e.key == Key::Backspace;
  if (!navigation && (!(e.mods & primary_mod()) || (e.key != Key::A && e.key != Key::C && e.key != Key::V))) { return false; }
  TableSelection selection = grid.selection.value();
  const bool prim = (e.mods & primary_mod()) != 0, shift = (e.mods & MOD_SHIFT) != 0;
  const bool selected = valid(*w.table, selection.active) && valid(*w.table, selection.anchor) &&
                        selection.active.column >= first && selection.anchor.column >= first;
  if (prim && e.key == Key::A) {
    if (w.table->rows && !w.table->columns.empty()) {
      const auto &order = table_perm(w);
      grid.selection.assign({{order.front(), first}, {order.back(), int(w.table->columns.size()) - 1}});
    }
    return true;
  }
  if (!selected) {
    if (w.table->rows <= 0 || w.table->columns.empty()) { return false; }
    if (!table_select(w, {table_perm(w).front(), first}, false)) { return true; }
    selection = grid.selection.value();
  }
  const int left = std::min(selection.anchor.column, selection.active.column);
  const int right = std::max(selection.anchor.column, selection.active.column);
  if (prim && e.key == Key::C) {
    if (!config_.clipboard || !grid.export_cell) { return true; }
    const auto rows = table_selection_rows(w);
    if (rows.empty() || rows.size() * size_t(right - left + 1) > selection_limit) { return true; }
    std::string text;
    for (size_t r = 0; r < rows.size(); ++r) {
      if (r) { text += '\n'; }
      for (int c = left; c <= right; ++c) {
        if (c != left) { text += '\t'; }
        const std::string value = grid.export_cell(rows[r], c);
        if (value.size() > clipboard_limit || text.size() > clipboard_limit - value.size()) { return true; }
        text += tsv_quote(value);
        if (text.size() > clipboard_limit) { return true; }
      }
    }
    config_.clipboard->set(text);
    return true;
  }
  if (prim && e.key == Key::V) {
    if (config_.clipboard && grid.on_paste) {
      const std::string text = config_.clipboard->get();
      const auto rows = table_selection_rows(w, true);
      if (text.size() <= clipboard_limit && !rows.empty()) { grid.on_paste(rows, left, text); }
    }
    return true;
  }
  if (e.key == Key::Delete || e.key == Key::Backspace) {
    const auto rows = table_selection_rows(w);
    if (grid.on_clear && !rows.empty() && rows.size() * size_t(right - left + 1) <= selection_limit) {
      grid.on_clear(rows, left, right - left + 1);
    }
    return true;
  }
  if (e.key == Key::Space && grid.on_toggle && grid.cell_style &&
      grid.cell_style(selection.active.row, selection.active.column) == TableCellStyle::Checkbox) {
    grid.on_toggle(selection.active); return true;
  }
  if (e.key == Key::Enter || e.key == Key::F2) { begin_table_edit(w); return true; }
  int row = table_view_row(w, selection.active.row), column = selection.active.column;
  const int last_column = int(w.table->columns.size()) - 1;
  const int page = std::max(1, int(list_body(w).h / list_row_height(w)) - 1);
  bool extend = shift;
  switch (e.key) {
    case Key::Left: --column; break;
    case Key::Right: ++column; break;
    case Key::Up: --row; break;
    case Key::Down: ++row; break;
    case Key::PageUp: row -= page; break;
    case Key::PageDown: row += page; break;
    case Key::Home: column = first; if (prim) { row = 0; } break;
    case Key::End: column = last_column; if (prim) { row = w.table->rows - 1; } break;
    case Key::Tab:
      extend = false;
      column += shift ? -1 : 1;
      if (column > last_column) { column = first; ++row; }
      else if (column < first) { column = last_column; --row; }
      break;
    default: return false;
  }
  row = std::clamp(row, 0, w.table->rows - 1);
  column = std::clamp(column, first, last_column);
  table_select(w, {table_perm(w)[size_t(row)], column}, extend);
  return true;
}

void Context::table_open_menu(const Widget &w, const int column)
{
  if (!w.table || !w.table->column_menu || column < 0 || size_t(column) >= w.table->columns.size()) { return; }
  auto entries = w.table->column_menu(column);
  if (entries.empty()) { return; }
  notify_native_view_invalidated();
  popup_ = {};
  popup_.owner = w.id; popup_.owner_key = w.key;
  popup_.menu = true;
  popup_.table_column = column;
  popup_.table_version = w.table->data_version;
  popup_.entries = std::move(entries);
  popup_.anchor = table_column_rect(w, column).intersect(table_column_clip(w, column));
  popup_.count = int(popup_.entries.size());
  focus_ = w.id;
  redraw_ = true;
}
}  // namespace stk::ui
