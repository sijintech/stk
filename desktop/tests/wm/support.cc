/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "support.hh"

#include <atomic>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <sstream>

#include <nlohmann/json.hpp>

namespace stk::wmtest {

namespace fs = std::filesystem;

std::string desktop_dir()
{
  return STK_DESKTOP_DIR;
}

std::string read_text(const std::string &path)
{
  std::ifstream in(path, std::ios::binary);
  std::ostringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

bool write_text(const std::string &path, const std::string &text)
{
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  out << text;
  return bool(out);
}

std::string temp_dir(const std::string &tag)
{
  static std::atomic<int> counter{0};
  const auto now = std::chrono::steady_clock::now().time_since_epoch().count();
  fs::path p = fs::temp_directory_path() /
               ("stk-wm-test-" + tag + "-" + std::to_string(now) + "-" + std::to_string(counter++));
  fs::create_directories(p);
  return p.string();
}

/* -------------------------------------------------------------------- */

ScreenDriver::ScreenDriver(wm::Screen &s, const int width, const int height, const float scale) : screen(s)
{
  ctx.ui_scale = scale;
  ctx.rect = {0, 0, width, height};
  ctx.now = double(time_ms) / 1000.0;
}

void ScreenDriver::frame()
{
  ctx.now = double(time_ms) / 1000.0;
  screen.update(ctx);
}

bool ScreenDriver::send(wm::Event e)
{
  e.time_ms = time_ms;
  ctx.now = double(time_ms) / 1000.0;
  return screen.dispatch(e, ctx);
}

bool ScreenDriver::move(const int x, const int y)
{
  wm::Event e;
  e.type = wm::EventType::MouseMove;
  e.x = x;
  e.y = y;
  return send(e);
}

bool ScreenDriver::down(const int x, const int y, const wm::MouseButton b)
{
  wm::Event e;
  e.type = wm::EventType::MouseDown;
  e.x = x;
  e.y = y;
  e.button = b;
  return send(e);
}

bool ScreenDriver::up(const int x, const int y, const wm::MouseButton b)
{
  wm::Event e;
  e.type = wm::EventType::MouseUp;
  e.x = x;
  e.y = y;
  e.button = b;
  return send(e);
}

void ScreenDriver::drag(const int x0, const int y0, const int x1, const int y1, const int steps)
{
  move(x0, y0);
  down(x0, y0);
  for (int i = 1; i <= steps; i++) {
    time_ms += 16;
    move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps);
    frame();
  }
  up(x1, y1);
  frame();
}

bool ScreenDriver::click(const int x, const int y, const wm::MouseButton b)
{
  move(x, y);
  const bool d = down(x, y, b);
  up(x, y, b);
  time_ms += 500; /* No accidental double clicks between helper calls. */
  frame();
  return d;
}

bool ScreenDriver::key(const wm::Key k, const uint32_t mods, const std::string &text)
{
  wm::Event e;
  e.type = wm::EventType::KeyDown;
  e.key = k;
  e.modifiers = mods;
  e.text = text;
  const bool r = send(e);
  e.type = wm::EventType::KeyUp;
  e.text.clear();
  send(e);
  frame();
  return r;
}

/* -------------------------------------------------------------------- */

AppFixture::AppFixture(const std::string &lang, const float scale, const int width, const int height)
{
  app::ShellOptions so;
  so.i18n_dir = desktop_dir() + "/app/i18n";
  so.language = lang == "en" ? "en" : "zh_CN";
  so.measurer = &measurer;
  so.interactive = false;
  shell = std::make_unique<app::AppShell>(so);
  shell->layout_path.clear();
  shell->install(screen, nullptr);
  shell->build_default_layout(screen);
  drv = std::make_unique<ScreenDriver>(screen, width, height, scale);
  drv->frame();
}

app::EditorArea &AppFixture::area(const std::string &id)
{
  wm::Area *a = screen.find_area(id);
  EXPECT_NE(a, nullptr) << id;
  return *dynamic_cast<app::EditorArea *>(a);
}

std::pair<int, int> AppFixture::widget_center(const std::string &key) const
{
  const ui::Widget *w = screen.ui() ? screen.ui()->find(key) : nullptr;
  EXPECT_NE(w, nullptr) << key;
  if (!w) {
    return {-1, -1};
  }
  const int top = screen.rect().ymax;
  return {int(w->rect.cx()), top - 1 - int(w->rect.cy())};
}

/* -------------------------------------------------------------------- */

static nlohmann::ordered_json rect_json(const wm::Rect &r)
{
  return nlohmann::ordered_json::array({r.xmin, r.ymin, r.xmax, r.ymax});
}

static nlohmann::ordered_json urect_json(const ui::Rect &r)
{
  auto q = [](float v) { return std::round(v * 100.0f) / 100.0f; };
  return nlohmann::ordered_json::array({q(r.x), q(r.y), q(r.w), q(r.h)});
}

std::string dump_screen(const wm::Screen &screen)
{
  nlohmann::ordered_json j;
  j["window"] = rect_json(screen.rect());
  j["scale"] = std::round(screen.ui_scale() * 1000.0f) / 1000.0f;
  j["tree"] = rect_json(screen.tree_rect());
  nlohmann::ordered_json areas = nlohmann::ordered_json::array();
  auto add_area = [&](const wm::Area *a) {
    nlohmann::ordered_json ja;
    ja["id"] = a->id();
    ja["type"] = a->type();
    ja["rect"] = rect_json(a->rect());
    nlohmann::ordered_json regions = nlohmann::ordered_json::array();
    for (const auto &r : a->regions()) {
      regions.push_back({{"name", r->name()}, {"visible", r->visible()}, {"rect", rect_json(r->rect())}});
    }
    ja["regions"] = regions;
    areas.push_back(ja);
  };
  for (const wm::Area *a : screen.areas()) {
    add_area(a);
  }
  for (const wm::RegionAlign edge : {wm::RegionAlign::Top, wm::RegionAlign::Bottom}) {
    if (const wm::Area *g = screen.global_area(edge)) {
      add_area(g);
    }
  }
  j["areas"] = areas;
  nlohmann::ordered_json splitters = nlohmann::ordered_json::array();
  for (const wm::Splitter &s : screen.splitters()) {
    splitters.push_back({{"dir", wm::split_dir_name(s.dir)}, {"index", s.index}, {"rect", rect_json(s.rect)}});
  }
  j["splitters"] = splitters;
  nlohmann::ordered_json blocks = nlohmann::ordered_json::array();
  if (const ui::Context *ui = screen.ui()) {
    for (const auto &b : ui->blocks()) {
      nlohmann::ordered_json jb;
      jb["name"] = b->name();
      jb["rect"] = urect_json(b->rect());
      nlohmann::ordered_json widgets = nlohmann::ordered_json::array();
      for (const ui::Widget &w : b->widgets()) {
        widgets.push_back({{"key", w.key}, {"type", ui::widget_type_name(w.type)}, {"rect", urect_json(w.rect)}});
      }
      jb["widgets"] = widgets;
      blocks.push_back(jb);
    }
  }
  j["blocks"] = blocks;
  /* One area / block per line keeps golden diffs readable. */
  std::string out = "{\n";
  bool first = true;
  for (auto it = j.begin(); it != j.end(); ++it) {
    out += first ? "" : ",\n";
    first = false;
    out += "  \"" + it.key() + "\": ";
    if (it->is_array() && !it->empty() && it->front().is_object()) {
      out += "[\n";
      for (size_t i = 0; i < it->size(); i++) {
        out += "    " + (*it)[i].dump() + (i + 1 < it->size() ? ",\n" : "\n");
      }
      out += "  ]";
    }
    else {
      out += it->dump();
    }
  }
  out += "\n}\n";
  return out;
}

}  // namespace stk::wmtest
