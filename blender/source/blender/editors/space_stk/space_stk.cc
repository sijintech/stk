/* SPDX-FileCopyrightText: 2026 STK Authors
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** STK's native editor. No network, solver, or VTK work runs on this thread. */
#include <charconv>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>

#include "BKE_context.hh"
#include "BKE_screen.hh"
#include "BLF_api.hh"
#include "BLI_listbase.h"
#include "BLI_path_utils.hh"
#include "BLI_serialize.hh"
#include "BLI_string_utf8.h"
#include "BLO_read_write.hh"
#include "DNA_space_types.h"
#include "DNA_windowmanager_types.h"
#include "ED_screen.hh"
#include "ED_space_api.hh"
#include "GPU_batch.hh"
#include "GPU_framebuffer.hh"
#include "GPU_immediate.hh"
#include "GPU_matrix.hh"
#include "GPU_shader_builtin.hh"
#include "GPU_state.hh"
#include "GPU_viewport.hh"
#include "MEM_guardedalloc.h"
#include "RNA_access.hh"
#include "UI_interface.hh"
#include "UI_view2d.hh"
#include "WM_api.hh"
#include "WM_types.hh"
#include "stk_scene.hh"

namespace blender {
namespace ed::stk {
namespace js = io::serialize;
using Dict = js::DictionaryValue;
using Array = js::ArrayValue;

static std::string str(const Dict *d, const char *key, const char *fallback = "")
{
  if (d) {
    const auto v = d->lookup_str(key);
    if (v)
      return std::string(*v);
  }
  return fallback;
}

static const Dict *dict(const Dict *d, const char *key)
{
  return d ? d->lookup_dict(key) : nullptr;
}

static double number(const js::Value &v)
{
  if (const auto *n = v.as_double_value())
    return n->value();
  if (const auto *n = v.as_int_value())
    return double(n->value());
  return std::numeric_limits<double>::quiet_NaN();
}

static bool point(const Array *array, Point &out)
{
  if (!array || array->elements().size() != 3)
    return false;
  for (int d = 0; d < 3; d++)
    out[d] = number(*array->elements()[d]);
  return true;
}

struct Runtime {
  std::shared_ptr<js::Value> state;
  const Dict *manifest = nullptr;
  std::shared_ptr<js::Value> scene_json;
  Scene scene;
  gpu::Batch *batch = nullptr;
  std::filesystem::file_time_type state_time{}, scene_time{};
  char prompt[4096] = "", url[512] = "http://127.0.0.1:8790", code[128] = "";
  char workspace[128] = "科学计算项目";
  int axis = 2, index = 0, component = 0;
  char level[64] = "0";
  bool camera_initialized = false;
  int scroll[3] = {};
  std::string error;
  ~Runtime()
  {
    GPU_BATCH_DISCARD_SAFE(batch);
  }
};
}  // namespace ed::stk

/* DNA stores only this opaque pointer. Credentials and chat text are not saved
 * in .blend files, nor restored through undo or space duplication. */
struct SpaceSTK_Runtime : ed::stk::Runtime {};

namespace ed::stk {
static Runtime &runtime(SpaceSTK &space)
{
  if (!space.runtime)
    space.runtime = MEM_new<SpaceSTK_Runtime>(__func__);
  return *space.runtime;
}

static bool changed_file(const char *name,
                         std::filesystem::file_time_type &stamp,
                         std::shared_ptr<js::Value> &value)
{
  const char *root = BLI_getenv("STK_BLENDER_STATE_DIR");
  if (!root)
    return false;
  const auto path = std::filesystem::path(
                        std::u8string_view(reinterpret_cast<const char8_t *>(root))) /
                    name;
  std::error_code ec;
  const auto time = std::filesystem::last_write_time(path, ec);
  if (ec || time == stamp)
    return false;
  const auto size = std::filesystem::file_size(path, ec);
  if (ec || size > 16 * 1024 * 1024)
    return false;
  std::ifstream stream(path, std::ios::binary);
  auto next = js::JsonFormatter().deserialize(stream);
  if (!next || !next->as_dictionary_value())
    return false;
  value = std::move(next);
  stamp = time;
  return true;
}

static void load_scene(Runtime &r)
{
  std::shared_ptr<js::Value> next;
  if (!changed_file("scene.json", r.scene_time, next))
    return;
  const Dict *root = next->as_dictionary_value();
  const Dict *m = dict(root, "manifest"), *mesh = dict(root, "mesh");
  Scene scene;
  bool valid = m && mesh && m->lookup_int("version") == 1 &&
               str(m, "association", "point") == "point";
  const Array *positions = mesh ? mesh->lookup_array("positions") : nullptr;
  const Array *values = mesh ? mesh->lookup_array("values") : nullptr;
  const Array *indices = mesh ? mesh->lookup_array("indices") : nullptr;
  const Array *range = m ? m->lookup_array("value_range") : nullptr;
  valid = valid && positions && values && indices && range && range->elements().size() == 2;
  if (valid) {
    valid = positions->elements().size() <= 80000 && indices->elements().size() <= 480000 &&
            values->elements().size() == positions->elements().size() &&
            point(m->lookup_array("render_origin"), scene.render_origin);
  }
  if (valid) {
    scene.lower = number(*range->elements()[0]);
    scene.upper = number(*range->elements()[1]);
    for (const auto &v : positions->elements()) {
      Point p;
      if (!point(v->as_array_value(), p)) {
        valid = false;
        break;
      }
      scene.positions.push_back(p);
    }
    for (const auto &v : values->elements())
      scene.values.push_back(number(*v));
    for (const auto &v : indices->elements()) {
      const auto *i = v->as_int_value();
      if (!i || i->value() < 0 || i->value() >= int64_t(scene.positions.size())) {
        valid = false;
        break;
      }
      scene.indices.push_back(uint32_t(i->value()));
    }
  }
  if (!valid || !scene.validate()) {
    r.error = "科学视图数据无效，保留上次有效画面";
    return;
  }
  GPU_BATCH_DISCARD_SAFE(r.batch);
  r.scene = std::move(scene);
  r.scene_json = std::move(next);
  r.manifest = m;
  r.error.clear();
  if (!r.scene.indices.empty()) {
    GPUVertFormat *format = immVertexFormat();
    const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32_32);
    const uint col = GPU_vertformat_attr_add(
        format, "color", gpu::VertAttrType::SFLOAT_32_32_32_32);
    immBindBuiltinProgram(GPU_SHADER_3D_SMOOTH_COLOR);
    r.batch = immBeginBatch(GPU_PRIM_TRIS, uint(r.scene.indices.size()));
    for (uint32_t i : r.scene.indices) {
      const auto rgba = color(r.scene.values[i], r.scene.lower, r.scene.upper);
      const Point &p = r.scene.positions[i];
      immAttr4fv(col, rgba.data());
      immVertex3f(pos,
                  float((p[0] - r.scene.center[0]) * 2 / r.scene.extent),
                  float((p[1] - r.scene.center[1]) * 2 / r.scene.extent),
                  float((p[2] - r.scene.center[2]) * 2 / r.scene.extent));
    }
    immEnd();
    immUnbindProgram();
  }
}

static Camera camera(const SpaceSTK &s)
{
  return {s.yaw, s.pitch, s.zoom, s.pan[0], s.pan[1]};
}

static std::string scientific_number(double value)
{
  std::ostringstream out;
  out << std::setprecision(10) << value;
  return out.str();
}

struct Layout {
  int w, h, left, right, bottom, chat;
  explicit Layout(const SpaceSTK &s, const ARegion &region)
  {
    w = region.winx;
    h = region.winy;
    left = int(w * std::clamp(s.panels[0], .12f, .32f));
    right = int(w * (1 - std::clamp(s.panels[1], .18f, .38f)));
    bottom = int(h * std::clamp(s.panels[2], .12f, .38f));
    chat = int(h * std::clamp(s.panels[3], .28f, .62f));
  }
  bool viewport(int x, int y) const
  {
    return x > left + 5 && x < right - 5 && y > bottom + 5 && y < h - 32;
  }
};

static void send(bContext &C,
                 const char *kind,
                 const std::shared_ptr<Dict> &payload,
                 const std::string &node_id = "")
{
  Dict body;
  body.append_str("kind", kind);
  body.append("payload", payload);
  if (!node_id.empty())
    body.append_str("node_id", node_id);
  std::stringstream json;
  js::JsonFormatter().serialize(json, body);
  PointerRNA props = WM_operator_properties_create("STK_OT_dispatch");
  RNA_string_set(&props, "body", json.str().c_str());
  WM_operator_name_call(&C, "STK_OT_dispatch", wm::OpCallContext::ExecDefault, &props, nullptr);
  WM_operator_properties_free(&props);
}

static std::shared_ptr<Dict> payload(const char *key = nullptr, const std::string &value = "")
{
  auto d = std::make_shared<Dict>();
  if (key)
    d->append_str(key, value);
  return d;
}

static void text_at(float x, float y, const std::string &text, int width, float size = 13)
{
  const int font = BLF_default();
  BLF_size(font, size * UI_SCALE_FAC);
  BLF_color4f(font, .82f, .85f, .9f, 1);
  BLF_position(font, x, y, 0);
  BLF_clipping(font, x, 0, x + width, y + size * 2);
  BLF_enable(font, BLF_CLIPPING);
  BLF_draw(font, text.c_str(), text.size());
  BLF_disable(font, BLF_CLIPPING);
}

static void rect(float x, float y, float width, float height, const std::array<float, 4> &color)
{
  const uint pos = GPU_vertformat_attr_add(
      immVertexFormat(), "pos", gpu::VertAttrType::SFLOAT_32_32);
  immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
  immUniformColor4fv(color.data());
  immRectf(pos, x, y, x + width, y + height);
  immUnbindProgram();
}

class Panel {
  ui::Block *block;
  int x, width, y, bottom, row, scroll;

 public:
  Panel(ui::Block *b, int x_, int top, int width_, int bottom_, int scroll_ = 0)
      : block(b),
        x(x_ + 10),
        width(std::max(10, width_ - 20)),
        y(top - 30),
        bottom(bottom_ + 8),
        row(std::max(22, int(24 * UI_SCALE_FAC))),
        scroll(scroll_)
  {
  }
  bool advance()
  {
    y -= row;
    if (scroll > 0) {
      scroll--;
      y += row;
      return false;
    }
    return y > bottom;
  }
  void label(const std::string &name)
  {
    if (advance())
      text_at(x, y + 6, name, width);
  }
  void paragraph(const std::string &value)
  {
    const int font = BLF_default();
    BLF_size(font, 13 * UI_SCALE_FAC);
    std::string line;
    float used = 0;
    for (size_t i = 0; i < value.size();) {
      const int bytes = std::min(size_t(BLI_str_utf8_size_safe(value.c_str() + i)),
                                 value.size() - i);
      const float next = BLF_width(font, value.c_str() + i, bytes);
      if (value[i] == '\n' || (used + next > width && !line.empty())) {
        label(line);
        line.clear();
        used = 0;
      }
      if (value[i] != '\n') {
        line.append(value, i, bytes);
        used += next;
      }
      i += bytes;
    }
    if (!line.empty())
      label(line);
  }
  void button(const std::string &name, std::function<void(bContext &)> fn)
  {
    if (!advance())
      return;
    auto *but = ui::uiDefBut(
        block, ui::ButtonType::But, name, x, y, width, row - 3, nullptr, 0, 0, std::nullopt);
    ui::button_func_set(but, std::move(fn));
  }
  void input(const char *name, char *value, int capacity)
  {
    if (advance())
      ui::uiDefBut(block,
                   ui::ButtonType::Text,
                   name,
                   x,
                   y,
                   width,
                   row - 3,
                   value,
                   0,
                   float(capacity),
                   std::nullopt);
  }
  template<typename T> void number_input(const char *name, T *value, float lower, float upper)
  {
    if (advance()) {
      auto *button = ui::uiDefButV(block,
                                   ui::ButtonType::Num,
                                   name,
                                   x,
                                   y,
                                   width,
                                   row - 3,
                                   value,
                                   lower,
                                   upper,
                                   std::nullopt);
      ui::button_number_step_size_set(button, 1);
      ui::button_number_precision_set(button, 3);
    }
  }
};

static void task_action(bContext &C, Runtime &r, const char *kind)
{
  const Dict *s = r.state ? dict(r.state->as_dictionary_value(), "selection") : nullptr;
  send(C, kind, payload("task_id", str(s, "task_id")));
}

static void view_action(bContext &C, Runtime &r, const char *mode)
{
  double level = 0;
  if (std::string_view(mode) == "iso") {
    const char *end = r.level + std::char_traits<char>::length(r.level);
    const auto parsed = std::from_chars(r.level, end, level);
    if (parsed.ec != std::errc{} || parsed.ptr != end || !std::isfinite(level)) {
      r.error = "等值面值须为有限数值，可使用科学计数法";
      ED_area_tag_redraw(CTX_wm_area(&C));
      return;
    }
  }
  const Dict *s = r.state ? dict(r.state->as_dictionary_value(), "selection") : nullptr;
  auto p = payload("task_id", str(s, "task_id"));
  p->append_str("path", str(s, "path"));
  auto options = p->append_dict("options");
  options->append_str("mode", mode);
  options->append_int("axis", r.axis);
  options->append_int("index", r.index);
  if (r.component < 0)
    options->append_str("component", "magnitude");
  else
    options->append_int("component", r.component);
  options->append_double("level", level);
  send(C, "view.build", p);
}

static void draw(const bContext *C, ARegion *region)
{
  auto &s = *reinterpret_cast<SpaceSTK *>(CTX_wm_space_data(C));
  Runtime &r = runtime(s);
  changed_file("state.json", r.state_time, r.state);
  load_scene(r);
  const Dict *state = r.state ? r.state->as_dictionary_value() : nullptr;
  const Dict *selection = dict(state, "selection");
  Layout l(s, *region);
  const int vw = std::max(1, l.right - l.left - 2), vh = std::max(1, l.h - l.bottom - 34);
  if (!r.camera_initialized && !r.scene.positions.empty()) {
    s.zoom = float(r.scene.fit_zoom(camera(s), double(vw) / vh));
    r.camera_initialized = true;
  }

  GPUViewport *viewport = WM_draw_region_get_viewport(region);
  GPU_framebuffer_bind_no_srgb(GPU_viewport_framebuffer_render_get(viewport));
  GPU_clear_color(0, 0, 0, 0);
  GPU_framebuffer_bind_no_srgb(GPU_viewport_framebuffer_overlay_get(viewport));
  GPU_framebuffer_clear_color_depth(GPU_framebuffer_active_get(), {.045, .055, .072, 1}, 1);
  GPU_matrix_push();
  GPU_matrix_push_projection();
  GPU_matrix_identity_set();
  GPU_matrix_ortho_set(-float(vw) / vh, float(vw) / vh, -1, 1, -1000, 1000);
  int old_view[4];
  GPU_viewport_size_get_i(old_view);
  GPU_viewport(old_view[0] + l.left + 1, old_view[1] + l.bottom + 1, vw, vh);
  GPU_matrix_translate_3f(s.pan[0], s.pan[1], 0);
  GPU_matrix_scale_1f(s.zoom);
  GPU_matrix_rotate_axis(s.pitch, 'X');
  GPU_matrix_rotate_axis(s.yaw, 'Z');
  GPU_depth_test(GPU_DEPTH_LESS_EQUAL);
  GPU_depth_mask(true);
  if (r.batch) {
    GPU_batch_program_set_builtin(r.batch, GPU_SHADER_3D_SMOOTH_COLOR);
    GPU_batch_draw(r.batch);
  }
  GPU_depth_test(GPU_DEPTH_NONE);
  GPU_depth_mask(false);
  GPU_viewport(old_view[0], old_view[1], old_view[2], old_view[3]);
  GPU_matrix_identity_set();
  GPU_matrix_ortho_set(0, float(l.w), 0, float(l.h), -1, 1);

  rect(0, 0, l.left, l.h, {.073f, .083f, .105f, 1});
  rect(l.right, 0, l.w - l.right, l.h, {.073f, .083f, .105f, 1});
  rect(l.left, 0, l.right - l.left, l.bottom, {.060f, .068f, .088f, 1});
  const std::array<float, 4> line{.19f, .22f, .27f, 1};
  rect(l.left, 0, 2, l.h, line);
  rect(l.right, 0, 2, l.h, line);
  rect(l.left, l.bottom, l.right - l.left, 2, line);
  rect(l.right, l.chat, l.w - l.right, 2, line);
  text_at(12, l.h - 23, "STK / 项目与任务", l.left - 20, 15);
  text_at(l.right + 12, l.h - 23, "科学视图 / 参数", l.w - l.right - 20, 15);
  text_at(l.right + 12, l.chat - 23, "AI / 跨设备会话", l.w - l.right - 20, 15);
  text_at(l.left + 12, l.bottom - 23, "日志与数值探针", l.right - l.left - 24, 15);
  text_at(
      l.left + 12, l.h - 23, str(r.manifest, "field", "等待科学数据"), l.right - l.left - 24, 15);
  text_at(l.left + 12,
          l.bottom + 18,
          "中键旋转 · Shift 中键平移 · 滚轮缩放 · 单击原始数据探针",
          l.right - l.left - 30);
  const Dict *source = dict(r.manifest, "source");
  if (source && (str(source, "path") != str(selection, "path") ||
                 str(source, "task_id") != str(selection, "task_id")))
  {
    text_at(l.left + 12,
            l.h - 46,
            "当前画面：" + str(source, "path") + "（选择已变化，生成视图后更新）",
            l.right - l.left - 30);
  }

  ui::Block *block = ui::block_begin(C, region, "STK Workbench", ui::EmbossType::Emboss);
  Panel projects(block, 0, l.h - 12, l.left, 0, r.scroll[0]);
  projects.label(str(state, "status", "等待通信桥接进程"));
  projects.label("最后同步 " + str(state, "last_seen", "尚未连接"));
  projects.input("服务 ", r.url, sizeof(r.url));
  projects.input("配对码 ", r.code, sizeof(r.code));
  projects.button("连接 / 配对", [&r](bContext &ctx) {
    auto p = payload("url", r.url);
    p->append_str("code", r.code);
    send(ctx, "pair", p);
    r.code[0] = '\0';
  });
  projects.button("刷新状态", [](bContext &ctx) { send(ctx, "refresh", payload()); });
  const Array *devices = state ? state->lookup_array("devices") : nullptr;
  const Dict *node = nullptr;
  if (devices)
    for (const auto &v : devices->elements()) {
      const Dict *d = v->as_dictionary_value();
      if (!d || str(d, "role") != "node")
        continue;
      const std::string id = str(d, "id");
      if (id == str(selection, "node_id"))
        node = d;
      const bool online = d->lookup_bool("online").value_or(false);
      projects.button((id == str(selection, "node_id") ? "● " : "○ ") + str(d, "name") +
                          (online ? " / 在线" : " / 离线"),
                      [id](bContext &ctx) { send(ctx, "select", payload("node_id", id)); });
    }
  projects.input("项目名 ", r.workspace, sizeof(r.workspace));
  projects.button("创建项目", [&r](bContext &ctx) {
    send(ctx, "workspace.create", payload("name", r.workspace));
  });
  const Dict *snapshot = dict(node, "snapshot");
  const Array *workspaces = snapshot ? snapshot->lookup_array("workspaces") : nullptr;
  if (workspaces)
    for (const auto &v : workspaces->elements()) {
      const Dict *w = v->as_dictionary_value();
      const std::string id = str(w, "id");
      projects.button((id == str(selection, "workspace_id") ? "● " : "○ ") + str(w, "name"),
                      [id](bContext &ctx) { send(ctx, "select", payload("workspace_id", id)); });
    }
  projects.button("运行已授权解析场模板", [&r](bContext &ctx) {
    const Dict *sel = r.state ? dict(r.state->as_dictionary_value(), "selection") : nullptr;
    auto p = payload("template", "demo-field");
    p->append_str("workspace_id", str(sel, "workspace_id"));
    send(ctx, "task.submit", p);
  });
  const Array *tasks = snapshot ? snapshot->lookup_array("tasks") : nullptr;
  if (tasks)
    for (const auto &v : tasks->elements()) {
      const Dict *t = v->as_dictionary_value();
      if (str(t, "workspace_id") != str(selection, "workspace_id"))
        continue;
      const std::string id = str(t, "id");
      projects.button((id == str(selection, "task_id") ? "● " : "○ ") + str(t, "name") + " / " +
                          str(t, "state"),
                      [id](bContext &ctx) { send(ctx, "select", payload("task_id", id)); });
    }
  projects.button("读取日志", [&r](bContext &ctx) { task_action(ctx, r, "task.logs"); });
  projects.button("取消所选任务", [&r](bContext &ctx) { task_action(ctx, r, "task.cancel"); });
  projects.button("读取结果文件", [&r](bContext &ctx) { task_action(ctx, r, "task.artifacts"); });
  const Array *artifacts = state ? state->lookup_array("artifacts") : nullptr;
  if (artifacts)
    for (const auto &v : artifacts->elements()) {
      const std::string path = str(v->as_dictionary_value(), "path");
      projects.button((path == str(selection, "path") ? "● " : "○ ") + path,
                      [path](bContext &ctx) { send(ctx, "select", payload("path", path)); });
    }

  Panel properties(block, l.right, l.h - 12, l.w - l.right, l.chat);
  properties.label(str(selection, "path", "请选择结果文件"));
  properties.number_input("切片轴 0/1/2 ", &r.axis, 0, 2);
  properties.number_input("切片索引 ", &r.index, 0, 1000000);
  properties.number_input("分量 -1=模长 ", &r.component, -1, 8);
  properties.input("等值面值 ", r.level, sizeof(r.level));
  properties.label(
      "时间步 " + std::to_string(r.manifest ? r.manifest->lookup_int("timestep").value_or(0) : 0));
  properties.button("生成切片", [&r](bContext &ctx) { view_action(ctx, r, "slice"); });
  properties.button("生成等值面", [&r](bContext &ctx) { view_action(ctx, r, "iso"); });
  properties.button("生成向量箭头", [&r](bContext &ctx) { view_action(ctx, r, "vectors"); });
  properties.button("重置相机", [&s, &r](bContext &ctx) {
    s.yaw = 30;
    s.pitch = 55;
    s.zoom = .85f;
    r.camera_initialized = false;
    s.pan[0] = s.pan[1] = 0;
    ED_area_tag_redraw(CTX_wm_area(&ctx));
  });
  properties.label("单位 " + str(r.manifest, "units") + " / 坐标 " +
                   str(r.manifest, "coordinate_units"));
  properties.label("范围 " + scientific_number(r.scene.lower) + " … " +
                   scientific_number(r.scene.upper));
  if (!r.error.empty())
    properties.label(r.error);

  const int composer_row = std::max(22, int(24 * UI_SCALE_FAC));
  const int composer_height = 2 * composer_row + 46;
  Panel chat(block, l.right, l.chat - 12, l.w - l.right, composer_height - 30, r.scroll[1]);
  chat.label("会话 " + str(state, "session_id"));
  const Array *sessions = state ? state->lookup_array("sessions") : nullptr;
  if (sessions)
    for (const auto &v : sessions->elements()) {
      const auto id = str(v->as_dictionary_value(), "id");
      chat.button("恢复 " + id,
                  [id](bContext &ctx) { send(ctx, "session.select", payload("session_id", id)); });
    }
  const Array *messages = state ? state->lookup_array("messages") : nullptr;
  if (messages)
    for (const auto &v : messages->elements()) {
      const Dict *message = v->as_dictionary_value();
      chat.paragraph(str(message, "role") + ": " + str(message, "content"));
    }
  const Array *actions = state ? state->lookup_array("actions") : nullptr;
  if (actions)
    for (const auto &v : actions->elements()) {
      const Dict *action = v->as_dictionary_value();
      if (str(action, "state") != "review")
        continue;
      const auto id = str(action, "id");
      chat.label("复核 " + str(action, "review_reason"));
      chat.button("查看操作详情",
                  [id](bContext &ctx) { send(ctx, "review.inspect", payload("action_id", id)); });
      chat.button("批准所选操作", [id](bContext &ctx) {
        auto p = payload("action_id", id);
        p->append_bool("approved", true);
        send(ctx, "review", p);
      });
      chat.button("拒绝所选操作", [id](bContext &ctx) {
        auto p = payload("action_id", id);
        p->append_bool("approved", false);
        send(ctx, "review", p);
      });
    }
  Panel composer(block, l.right, composer_height, l.w - l.right, 0);
  composer.input("对话 ", r.prompt, sizeof(r.prompt));
  composer.button("发送", [&r](bContext &ctx) {
    send(ctx, "chat", payload("content", r.prompt));
    r.prompt[0] = '\0';
  });
  std::istringstream lines(str(state, "logs"));
  std::string line_text;
  Panel logs(block, l.left, l.bottom - 12, l.right - l.left, 0, r.scroll[2]);
  while (std::getline(lines, line_text))
    logs.paragraph(line_text);
  ui::block_end(C, block);
  ui::block_draw(C, block);
  /* This is a display legend, never a replacement for original-data probing. */
  for (int i = 0; i < 64; i++) {
    rect(l.left + 16 + i * 3, l.bottom + 42, 3, 8, color(i / 63.0, 0, 1));
  }
  text_at(l.left + 16, l.bottom + 56, scientific_number(r.scene.lower), 120);
  text_at(l.left + 145, l.bottom + 56, scientific_number(r.scene.upper), 120);
  GPU_matrix_pop_projection();
  GPU_matrix_pop();
}

struct Drag {
  int mode, x, y;
  float panels[4], yaw, pitch, pan[2];
};

static wmOperatorStatus interact_invoke(bContext *C, wmOperator *op, const wmEvent *event)
{
  auto *s = reinterpret_cast<SpaceSTK *>(CTX_wm_space_data(C));
  ARegion *region = CTX_wm_region(C);
  if (!s || s->spacetype != SPACE_STK || !region)
    return OPERATOR_PASS_THROUGH;
  const Layout l(*s, *region);
  const int x = event->mval[0], y = event->mval[1];
  Runtime &r = runtime(*s);
  if (ELEM(event->type, WHEELUPMOUSE, WHEELDOWNMOUSE)) {
    const int direction = event->type == WHEELUPMOUSE ? 1 : -1;
    if (l.viewport(x, y))
      s->zoom = std::clamp(s->zoom * float(std::pow(1.12, direction)), .02f, 100.f);
    else {
      const int panel = x < l.left ? 0 : (x > l.right ? 1 : 2);
      r.scroll[panel] = std::max(0, r.scroll[panel] - direction * 3);
    }
    ED_region_tag_redraw(region);
    return OPERATOR_FINISHED;
  }
  int mode = -1;
  if (event->type == LEFTMOUSE) {
    if (std::abs(x - l.left) < 5)
      mode = 0;
    else if (std::abs(x - l.right) < 5)
      mode = 1;
    else if (x > l.left && x < l.right && std::abs(y - l.bottom) < 5)
      mode = 2;
    else if (x > l.right && std::abs(y - l.chat) < 5)
      mode = 3;
    else if (l.viewport(x, y)) {
      const double vw = l.right - l.left - 2, vh = l.h - l.bottom - 34;
      const auto hit = r.scene.pick(
          camera(*s), 2 * (x - l.left - 1) / vw - 1, 2 * (y - l.bottom - 1) / vh - 1, vw / vh);
      if (hit && str(r.manifest, "mode") != "demo") {
        /* Use the displayed scene's immutable source, not a newly selected file. */
        const Dict *source = dict(r.manifest, "source");
        auto p = payload("task_id", str(source, "task_id"));
        p->append_str("path", str(source, "path"));
        auto location = p->append_array("position");
        for (double n : *hit)
          location->append_double(n);
        send(*C, "view.probe", p, str(source, "node_id"));
      }
      return OPERATOR_FINISHED;
    }
  }
  else if (event->type == MIDDLEMOUSE && l.viewport(x, y)) {
    mode = (event->modifier & KM_SHIFT) ? 5 : 4;
  }
  if (mode < 0)
    return OPERATOR_PASS_THROUGH;
  auto *drag = MEM_new<Drag>(__func__);
  drag->mode = mode;
  drag->x = x;
  drag->y = y;
  drag->yaw = s->yaw;
  drag->pitch = s->pitch;
  std::copy_n(s->panels, 4, drag->panels);
  std::copy_n(s->pan, 2, drag->pan);
  op->customdata = drag;
  WM_event_add_modal_handler(C, op);
  return OPERATOR_RUNNING_MODAL;
}

static void interact_cancel(bContext *C, wmOperator *op)
{
  auto *drag = static_cast<Drag *>(op->customdata);
  if (!drag)
    return;
  auto *s = reinterpret_cast<SpaceSTK *>(CTX_wm_space_data(C));
  s->yaw = drag->yaw;
  s->pitch = drag->pitch;
  std::copy_n(drag->panels, 4, s->panels);
  std::copy_n(drag->pan, 2, s->pan);
  MEM_delete(drag);
  op->customdata = nullptr;
  ED_area_tag_redraw(CTX_wm_area(C));
}

static wmOperatorStatus interact_modal(bContext *C, wmOperator *op, const wmEvent *event)
{
  auto *drag = static_cast<Drag *>(op->customdata);
  auto *s = reinterpret_cast<SpaceSTK *>(CTX_wm_space_data(C));
  ARegion *region = CTX_wm_region(C);
  if (event->type == EVT_ESCKEY) {
    interact_cancel(C, op);
    return OPERATOR_CANCELLED;
  }
  if (ELEM(event->type, LEFTMOUSE, MIDDLEMOUSE) && event->val == KM_RELEASE) {
    MEM_delete(drag);
    op->customdata = nullptr;
    return OPERATOR_FINISHED;
  }
  if (event->type == MOUSEMOVE) {
    const float dx = float(event->mval[0] - drag->x), dy = float(event->mval[1] - drag->y);
    switch (drag->mode) {
      case 0:
        s->panels[0] = std::clamp(drag->panels[0] + dx / region->winx, .12f, .32f);
        break;
      case 1:
        s->panels[1] = std::clamp(drag->panels[1] - dx / region->winx, .18f, .38f);
        break;
      case 2:
        s->panels[2] = std::clamp(drag->panels[2] + dy / region->winy, .12f, .38f);
        break;
      case 3:
        s->panels[3] = std::clamp(drag->panels[3] + dy / region->winy, .28f, .62f);
        break;
      case 4:
        s->yaw = drag->yaw + dx * .4f;
        s->pitch = drag->pitch - dy * .4f;
        break;
      case 5: {
        const Layout l(*s, *region);
        const float h = std::max(1, l.h - l.bottom - 34);
        s->pan[0] = drag->pan[0] + 2 * dx / h;
        s->pan[1] = drag->pan[1] + 2 * dy / h;
        break;
      }
    }
    ED_region_tag_redraw(region);
  }
  return OPERATOR_RUNNING_MODAL;
}

static void STK_OT_interact(wmOperatorType *ot)
{
  ot->name = "STK View Interaction";
  ot->idname = "STK_OT_interact";
  ot->description = "Resize workbench regions, navigate and probe scientific data";
  ot->invoke = interact_invoke;
  ot->modal = interact_modal;
  ot->cancel = interact_cancel;
}

static void region_init(wmWindowManager *wm, ARegion *region)
{
  ui::view2d_region_reinit(&region->v2d, ui::V2D_COMMONVIEW_STANDARD, region->winx, region->winy);
  wmKeyMap *km = WM_keymap_ensure(wm->runtime->defaultconf, "STK", SPACE_STK, RGN_TYPE_WINDOW);
  WM_event_add_keymap_handler(&region->runtime->handlers, km);
}

static SpaceLink *create(const ScrArea *, const blender::Scene *)
{
  auto *s = MEM_new<SpaceSTK>(__func__);
  ARegion *region = BKE_area_region_new();
  region->regiontype = RGN_TYPE_WINDOW;
  BLI_addtail(&s->regionbase, region);
  return reinterpret_cast<SpaceLink *>(s);
}

static void free_space(SpaceLink *sl)
{
  auto *s = reinterpret_cast<SpaceSTK *>(sl);
  if (s->runtime)
    MEM_delete(s->runtime);
  s->runtime = nullptr;
}
}  // namespace ed::stk

void ED_spacetype_stk()
{
  using namespace ed::stk;
  auto st = std::make_unique<SpaceType>();
  st->spaceid = SPACE_STK;
  STRNCPY_UTF8(st->name, "STK Scientific Workbench");
  st->create = create;
  st->free = free_space;
  st->init = [](wmWindowManager *, ScrArea *) {};
  st->duplicate = [](SpaceLink *sl) -> SpaceLink * {
    auto *s = MEM_dupalloc(reinterpret_cast<SpaceSTK *>(sl));
    s->runtime = nullptr;
    return reinterpret_cast<SpaceLink *>(s);
  };
  st->blend_write = [](BlendWriter *writer, SpaceLink *sl) {
    writer->write_struct_cast<SpaceSTK>(sl);
  };
  st->blend_read_data = [](BlendDataReader *, SpaceLink *sl) {
    reinterpret_cast<SpaceSTK *>(sl)->runtime = nullptr;
  };
  st->operatortypes = []() { WM_operatortype_append(STK_OT_interact); };
  st->keymap = [](wmKeyConfig *config) {
    /* Bindings live in Blender's default keymap data, which replaces C++ items. */
    WM_keymap_ensure(config, "STK", SPACE_STK, RGN_TYPE_WINDOW);
  };
  ARegionType *art = MEM_new_zeroed<ARegionType>(__func__);
  art->regionid = RGN_TYPE_WINDOW;
  art->keymapflag = ED_KEYMAP_UI;
  art->init = region_init;
  art->draw = ed::stk::draw;
  BLI_addhead(&st->regiontypes, art);
  BKE_spacetype_register(std::move(st));
}
}  // namespace blender
