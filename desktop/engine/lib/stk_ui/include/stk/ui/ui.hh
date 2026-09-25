/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * STK UI toolkit (ui_core): Blender uiBlock/uiLayout-style immediate building over a retained
 * block.
 *
 *   ui::Context ctx({.measurer = &m, .clipboard = &cb, .catalog = &cat});
 *   ctx.set_scale(dpi_scale, user_scale);
 *   // Every (on-demand) frame, rebuild from application state:
 *   ctx.begin_frame(window_size, now);
 *   ui::Layout &l = ctx.block("props", region_rect).layout();
 *   l.label(ctx.tr("props.title"));
 *   ui::Layout &row = l.row(true);                          // aligned row
 *   row.number("thr", "阈值", ui::bind(state.threshold), {.min = 0, .step = 0.01});
 *   if (ui::Layout *body = l.panel("adv", ctx.tr("props.advanced"))) { ... }
 *   ctx.end_frame();                                         // resolve layout, overlays, draw list
 *   painter.paint(ctx.draw_list(), window_size);
 *   // Between frames:
 *   if (ctx.handle_event(ev).redraw) schedule_redraw();
 *   // and wake up at ctx.next_wakeup() for tooltips/toasts.
 *
 * Widgets bind values through getter/setter closures (ui::Binding); the setter runs while
 * handling events. Widget ids are stable hashes of (block, scope path, key); hover, press, drag,
 * text edit, open popups, panel open state and scroll offsets are keyed by them and survive
 * rebuilds. Events hit-test the widgets of the last built frame.
 */
#pragma once

#include <deque>
#include <functional>
#include <limits>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

#include "stk/ui/draw_list.hh"
#include "stk/ui/event.hh"
#include "stk/ui/geom.hh"
#include "stk/ui/i18n.hh"
#include "stk/ui/log_buffer.hh"
#include "stk/ui/number.hh"
#include "stk/ui/text.hh"
#include "stk/ui/text_edit.hh"
#include "stk/ui/theme.hh"

namespace stk::ui {

using WidgetId = uint64_t;

/** Getter/setter pair binding a widget to application state. */
template<class T> struct Binding {
  std::function<T()> get;
  std::function<void(T)> set;

  T value() const { return get ? get() : T{}; }
  void assign(T v) const
  {
    if (set) {
      set(std::move(v));
    }
  }
  explicit operator bool() const { return bool(get); }
};

/** Binds directly to a variable (which must outlive the frame's event handling). */
template<class T> Binding<T> bind(T &ref)
{
  return {[&ref]() { return ref; }, [&ref](T v) { ref = std::move(v); }};
}
/** Binds a float variable to a double-valued widget. */
Binding<double> bind_float(float &ref);
Binding<double> bind_int(int &ref);

/** Host clipboard (GHOST getClipboard/putClipboard). */
class Clipboard {
 public:
  virtual ~Clipboard() = default;
  virtual std::string get() = 0;
  virtual void set(std::string_view text) = 0;
};

class MemoryClipboard final : public Clipboard {
 public:
  std::string get() override { return text; }
  void set(std::string_view t) override { text = std::string(t); }
  std::string text;
};

enum class WidgetType : uint8_t {
  Label,
  Paragraph,
  Button,
  Checkbox,
  TextField,
  Number,
  Slider,
  Dropdown,
  ColormapDropdown,
  MenuButton,
  Tabs,
  PanelHeader,
  Progress,
  VirtualList,
  LogView,
  Table,
  Image,
  SplitterBar,
  MenuItem,
};
const char *widget_type_name(WidgetType t);

enum class Align : uint8_t { Left, Center, Right };
enum class LayoutAlign : uint8_t { Expand, Left, Center, Right };
enum class ToastKind : uint8_t { Info, Success, Warning, Error };

struct ColormapItem {
  std::string name;
  /** LUT (typically 256 entries), drawn as a gradient swatch. */
  std::vector<Color> lut;
};

struct MenuEntry {
  std::string text;
  std::function<void()> action;
  bool enabled = true;
};

struct ListSpec {
  int count = 0;
  std::function<std::string(int)> text;
  Binding<int> selected;
  /** Visible height in rows. */
  float rows = 8.0f;
  /** Double-click or Enter on a row. */
  std::function<void(int)> on_activate;
};

struct TableColumn {
  std::string title;
  float width = 6.0f; /**< Initial width in UI units (resizable by dragging the header edge). */
  bool sortable = true;
  bool numeric = false; /**< Sort numerically and right-align. */
};

struct TableSpec {
  std::vector<TableColumn> columns;
  int rows = 0;
  std::function<std::string(int row, int col)> cell;
  /** Selected model row (not view row). */
  Binding<int> selected;
  float visible_rows = 8.0f;
  /** Bump when the data changes so the cached sort order is rebuilt. */
  uint64_t data_version = 0;
  /** Optional text colour of a cell (model row); alpha 0 keeps the list text colour. Selected rows
   * keep the selection text colour. */
  std::function<Color(int row, int col)> cell_color;
};

struct ImageSpec {
  uint64_t texture = 0; /**< Host texture handle (ui_gpu: blender::gpu::Texture *). */
  int width = 0;
  int height = 0;
  float height_units = 8.0f;
};

struct TextFieldOptions {
  std::string placeholder;
  size_t max_length = 0;
  bool mono = false;
  /** Shows every character as a bullet (secrets); copying and cutting are disabled. */
  bool password = false;
};

class Block;
class Context;
class Layout;

/** One button (Blender "uiBut"): resolved rect plus the bindings used by event handling. */
struct Widget {
  WidgetType type = WidgetType::Label;
  WidgetId id = 0;
  std::string key; /**< Debug path "block/scope/key", used by Context::find(). */
  Rect rect;
  Rect clip;       /**< Visible part (block clip); events outside are ignored. */
  std::string text;
  std::string tooltip;
  Align align = Align::Left;
  bool enabled = true;
  uint8_t corners = CORNER_ALL;
  float height = 0.0f;      /**< Pixels; set at creation (width-dependent types at layout). */
  float fixed_width = 0.0f; /**< Pixels; 0 = flexible. */
  bool mono = false;
  Block *block = nullptr;

  std::function<void()> on_click;
  Binding<bool> boolean;
  Binding<double> number;
  NumberProps props;
  Binding<std::string> string;
  TextFieldOptions text_opts;
  Binding<int> index;
  std::vector<std::string> items;
  std::shared_ptr<const std::vector<ColormapItem>> colormaps;
  std::vector<MenuEntry> menu;
  float fraction = 0.0f;
  std::shared_ptr<ListSpec> list;
  std::shared_ptr<TableSpec> table;
  const LogBuffer *log = nullptr;
  ImageSpec image;
  Binding<float> factor;
  std::vector<TextLine> lines; /**< Paragraph lines (layout output). */
  int menu_index = -1;         /**< MenuItem: index in the popup. */

  bool focusable() const;

  /* Chainable modifiers. */
  Widget &tip(std::string_view text);
  Widget &disable(bool disabled = true);
  Widget &width(float units);
};

/** Layout container (Blender uiLayout). Owned by its Block; valid until the next begin_frame. */
class Layout {
 public:
  enum class Kind : uint8_t { Column, Row, Split, Grid, Box, Panel, Splitter };

  /* Containers. */
  Layout &row(bool align = false);
  Layout &column(bool align = false);
  /** First child gets `factor` of the width, the others share the rest. */
  Layout &split(float factor = 0.5f, bool align = false);
  /** Grid flow with a fixed number of columns (row-major). */
  Layout &grid(int columns, bool align = false);
  Layout &box();
  /** Collapsible panel; returns the body layout, or nullptr while collapsed. */
  Layout *panel(std::string_view key, std::string_view title, bool default_open = true);
  /** Property-split row (label right-aligned in the left 40 %); returns the value layout. */
  Layout &prop(std::string_view label, std::string_view tooltip = {});
  /** Side-by-side panes separated by a draggable bar; `factor` is the left share. */
  std::pair<Layout *, Layout *> splitter(std::string_view key, Binding<float> factor);
  /** Column whose widget ids are scoped by `key` (for repeated sub-trees). */
  Layout &scope(std::string_view key);
  void separator(float units = 0.5f);

  Layout &scale_y(float s);
  Layout &alignment(LayoutAlign a);
  Layout &enabled(bool e);

  /* Widgets. */
  Widget &label(std::string_view text, Align align = Align::Left);
  /** Wrapped text (CJK line breaking); height depends on the resolved width. */
  Widget &paragraph(std::string_view text);
  Widget &button(std::string_view key, std::string_view text, std::function<void()> on_click);
  Widget &checkbox(std::string_view key, std::string_view text, Binding<bool> value);
  Widget &text_field(std::string_view key, Binding<std::string> value, TextFieldOptions opts = {});
  Widget &number(std::string_view key, std::string_view label, Binding<double> value, NumberProps props = {});
  Widget &slider(std::string_view key, std::string_view label, Binding<double> value, NumberProps props = {});
  Widget &dropdown(std::string_view key, std::vector<std::string> items, Binding<int> selected);
  Widget &colormap_dropdown(std::string_view key,
                            std::shared_ptr<const std::vector<ColormapItem>> colormaps,
                            Binding<int> selected);
  Widget &menu_button(std::string_view key, std::string_view text, std::vector<MenuEntry> entries);
  Widget &tabs(std::string_view key, std::vector<std::string> labels, Binding<int> selected);
  /** fraction in [0, 1]; text empty = percentage. */
  Widget &progress(float fraction, std::string_view text = {});
  Widget &virtual_list(std::string_view key, ListSpec spec);
  Widget &log_view(std::string_view key, const LogBuffer &log, float height_units = 8.0f);
  Widget &table(std::string_view key, TableSpec spec);
  Widget &image(std::string_view key, ImageSpec spec);

  Block &block() const { return *block_; }
  Context &ctx() const;
  Kind kind() const { return kind_; }

  /* Resolved geometry (after Context::end_frame). */
  Rect rect;

 private:
  friend class Block;
  friend class Context;
  friend struct LayoutEngine;
  struct Item {
    Layout *layout = nullptr;
    Widget *widget = nullptr;
    float space = 0.0f; /**< Separator height/width in pixels when both pointers are null. */
  };

  Layout &add_child(Kind kind, bool align);
  Widget &add_widget(WidgetType type, std::string_view key);

  Kind kind_ = Kind::Column;
  Block *block_ = nullptr;
  std::vector<Item> items_;
  bool align_ = false;
  bool enabled_ = true;
  float scale_y_ = 1.0f;
  LayoutAlign alignment_ = LayoutAlign::Expand;
  float split_factor_ = 0.5f;
  int columns_ = 1;
  WidgetId scope_ = 0;
  std::string path_;
  int auto_key_ = 0;
  /* Panel. */
  Widget *header_ = nullptr;
  bool open_ = true;
  /* Layout pass scratch. */
  float pref_w_ = 0.0f;
};

/** A region's widget tree for one frame (Blender uiBlock). */
class Block {
 public:
  enum class Kind : uint8_t { Region, Modal, Popup, Tooltip, Toast };

  Layout &layout() { return *root_; }
  const std::string &name() const { return name_; }
  const Rect &rect() const { return rect_; }
  Kind kind() const { return kind_; }
  Context &ctx() const { return *ctx_; }
  const std::deque<Widget> &widgets() const { return widgets_; }
  float content_height() const { return content_h_; }
  float scroll() const;
  /** Frame of overlay blocks (modal dialog, popup, tooltip); == rect for regions. */
  const Rect &frame() const { return frame_; }
  const std::string &title() const { return title_; }
  /**
   * Region blocks: background colour painted under the widgets (default Theme::region_back);
   * alpha 0 paints none, so GPU content drawn under the block (a 3D viewport) stays visible.
   */
  void set_background(Color c) { background_ = c; has_background_ = true; }
  /** Commands of this block in Context::draw_list(): [draw_begin, draw_end) (after end_frame). */
  size_t draw_begin() const { return draw_begin_; }
  size_t draw_end() const { return draw_end_; }

 private:
  friend class Context;
  friend class Layout;
  friend struct LayoutEngine;

  Context *ctx_ = nullptr;
  Kind kind_ = Kind::Region;
  std::string name_;
  std::string title_;
  WidgetId id_ = 0;
  Rect rect_;
  Rect frame_;
  std::deque<Layout> layouts_;
  std::deque<Widget> widgets_;
  Layout *root_ = nullptr;
  float content_h_ = 0.0f;
  float width_units_ = 0.0f;
  bool has_pos_ = false;
  Vec2 pos_;
  std::function<void()> on_close;
  ToastKind toast_kind_ = ToastKind::Info;
  Color background_;
  bool has_background_ = false;
  size_t draw_begin_ = 0, draw_end_ = 0;
};

struct ContextConfig {
  const TextMeasurer *measurer = nullptr; /**< Required. */
  Clipboard *clipboard = nullptr;         /**< Optional; copy/paste disabled without. */
  const Catalog *catalog = nullptr;       /**< Optional; tr() returns keys without. */
  Theme theme = Theme::blender_dark();
  double tooltip_delay = 0.5; /**< UI_TOOLTIP_DELAY. */
  double double_click_time = 0.35;
  /** Use Super (Cmd) instead of Ctrl as the shortcut modifier (macOS). */
  bool mac_shortcuts = false;
};

struct ModalOptions {
  float width_units = 18.0f;
  /** Top-left position in window pixels; default = centered. */
  bool has_pos = false;
  Vec2 pos;
};

class Context {
 public:
  explicit Context(ContextConfig config);
  ~Context();
  Context(const Context &) = delete;
  Context &operator=(const Context &) = delete;

  /* Configuration. */
  /** UI scale = DPI scale (GHOST native pixel size / DPI hint) x user scale. */
  void set_scale(float dpi_scale, float user_scale = 1.0f);
  float scale() const { return style_.scale; }
  const Style &style() const { return style_; }
  const Theme &theme() const { return config_.theme; }
  const TextMeasurer &measurer() const { return *config_.measurer; }
  const Catalog *catalog() const { return config_.catalog; }
  void set_catalog(const Catalog *c) { config_.catalog = c; }
  std::string_view tr(std::string_view key) const;

  /* Frame building. */
  void begin_frame(Vec2 window_size, double now);
  Block &block(std::string_view name, Rect region);
  /** An open modal dialog for this frame (call every frame while it should stay open). */
  Layout &modal(std::string_view key, std::string_view title, std::function<void()> on_close, ModalOptions opts = {});
  void end_frame();
  const DrawList &draw_list() const { return draw_; }
  /**
   * First draw-list command after the region blocks: modal dimming, modals, popups, tooltips and
   * toasts follow from here, so a host can paint GPU content between region blocks and overlays.
   */
  size_t overlay_draw_begin() const { return overlay_begin_; }
  Vec2 window_size() const { return window_; }

  /* Services. */
  void toast(std::string text, ToastKind kind = ToastKind::Info, double seconds = 4.0);
  /** Opens the popup of a dropdown/menu widget of the last frame (by key or path suffix). */
  bool open_popup(std::string_view widget_key);
  void close_popup();
  bool popup_open() const { return popup_.owner != 0; }
  /** Shows the tooltip of a widget immediately (gallery, tests). */
  bool force_tooltip(std::string_view widget_key);

  /* Events. */
  EventResult handle_event(const Event &e);
  /** Absolute time of the next timed change (tooltip, toast expiry); +inf when idle. */
  double next_wakeup() const;
  bool redraw_requested() const { return redraw_; }
  void clear_redraw() { redraw_ = false; }
  void request_redraw() { redraw_ = true; }

  /* Text input state for the window manager (IME enable + candidate window placement). */
  bool text_input_active() const { return edit_.id != 0; }
  /** Caret rectangle of the field being edited, window pixels. */
  Rect text_input_rect() const { return edit_caret_; }

  /* Queries (tests, tools). */
  const Widget *find(std::string_view key) const;
  const std::vector<std::unique_ptr<Block>> &blocks() const { return blocks_; }
  WidgetId hovered() const { return hover_; }
  WidgetId active() const { return drag_.id; }
  WidgetId focused() const { return focus_; }
  WidgetId editing() const { return edit_.id; }
  const TextEdit *edit_state() const { return edit_.id ? &edit_.edit : nullptr; }
  double now() const { return now_; }
  bool panel_open(WidgetId id, bool default_open) const;
  float scroll_of(WidgetId id) const;

 private:
  friend class Layout;
  friend class Block;
  friend struct LayoutEngine;

  struct EditState {
    WidgetId id = 0;
    TextEdit edit;
    float scroll_x = 0.0f;
    bool numeric = false;
    bool password = false;
    std::function<bool(const std::string &)> commit;
  };
  struct DragState {
    enum class Kind : uint8_t {
      None, Press, Number, Slider, TextSelect, Scroll, ColumnResize, Splitter, ImagePan, Header,
    };
    WidgetId id = 0;
    Kind kind = Kind::None;
    Vec2 start;
    Vec2 last;
    double start_value = 0.0;
    float start_scroll = 0.0f;
    int column = -1;
    int zone = 0; /**< Number field: -1 left arrow, 1 right arrow, 0 middle. */
    bool moved = false;
  };
  struct PopupState {
    WidgetId owner = 0;
    std::string owner_key;
    int highlight = -1;
    int count = 0;
    Rect anchor;
    bool colormap = false;
    bool menu = false;
  };
  struct TableState {
    std::vector<float> widths_u;
    int sort_col = -1;
    bool ascending = true;
    std::vector<int> perm;
    uint64_t perm_version = ~0ull;
    int perm_rows = -1, perm_col = -2;
    bool perm_asc = true;
  };
  struct ImageState {
    float zoom = 0.0f; /**< 0 = fit. */
    Vec2 pan;
  };
  struct Toast {
    std::string text;
    ToastKind kind;
    double expires;
    uint64_t serial;
  };

  /* Helpers (context.cc / widgets.cc). */
  Block &new_block(Block::Kind kind, std::string_view name, Rect region);
  const Widget *hit(Vec2 p, Block **r_block = nullptr) const;
  const Widget *find_id(WidgetId id) const;
  bool in_modal_scope(const Widget &w) const;
  void set_hover(const Widget *w, Vec2 p);
  void begin_edit(const Widget &w, bool select_all, std::string initial = {}, bool use_initial = false);
  void commit_edit();
  void cancel_edit();
  void edit_click(const Widget &w, Vec2 p, bool extend, bool dbl);
  bool edit_key(const Event &e);
  void focus_next(bool backwards);
  bool activate_focused(const Event &e);
  void open_popup_for(const Widget &w);
  void popup_select(int index);
  bool handle_popup_event(const Event &e, EventResult &res);
  EventResult mouse_down(const Event &e);
  EventResult mouse_move(const Event &e);
  EventResult mouse_up(const Event &e);
  EventResult wheel(const Event &e);
  EventResult key_down(const Event &e);
  void drag_number(const Widget &w, const Event &e);
  float list_row_height(const Widget &w) const;
  float max_scroll(const Widget &w) const;
  void set_scroll(WidgetId id, float v, float max);
  TableState &table_state(const Widget &w);
  const std::vector<int> &table_perm(const Widget &w);
  float table_col_px(const Widget &w, int c);
  int table_resize_hit(const Widget &w, Vec2 p);
  int table_header_col(const Widget &w, Vec2 p);
  Rect image_display_rect(const Widget &w);
  Rect scrollbar_rect(const Widget &w, float content, float view, float scroll, Rect area) const;
  uint8_t primary_mod() const { return config_.mac_shortcuts ? MOD_SUPER : MOD_CTRL; }

  void build_overlays();
  void layout_block(Block &b);
  void draw_block(const Block &b);
  void draw_layout(const Layout &l, const Block &b);
  void draw_widget(const Widget &w);
  void draw_scrollbar(const Rect &area, float content, float view, float scroll, bool hot);
  void draw_shadow(const Rect &r, float radius);

  ContextConfig config_;
  Style style_;
  Vec2 window_;
  double now_ = 0.0;
  bool building_ = false;
  bool redraw_ = true;

  std::vector<std::unique_ptr<Block>> blocks_;
  DrawList draw_;
  size_t overlay_begin_ = 0;

  WidgetId hover_ = 0;
  int hover_zone_ = 0;
  double hover_since_ = 0.0;
  Vec2 mouse_;
  WidgetId focus_ = 0;
  WidgetId tooltip_forced_ = 0;
  WidgetId tooltip_shown_ = 0;
  DragState drag_;
  EditState edit_;
  Rect edit_caret_;
  PopupState popup_;
  double last_click_time_ = -1.0;
  Vec2 last_click_pos_;
  WidgetId last_click_id_ = 0;

  std::vector<Toast> toasts_;
  uint64_t toast_serial_ = 0;

  std::unordered_map<WidgetId, bool> panels_;
  std::unordered_map<WidgetId, float> scroll_;
  std::unordered_map<WidgetId, bool> follow_;
  std::unordered_map<WidgetId, TableState> tables_;
  std::unordered_map<WidgetId, ImageState> images_;
};

}  // namespace stk::ui
