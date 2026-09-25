/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/wm/csd.hh"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>

#include "GHOST_ISystem.hh"
#include "GHOST_IWindow.hh"
#include "GHOST_Types.hh"

#include "stk/wm/window.hh"

namespace stk::wm {

namespace {
CsdConfig g_config;
/* The manager whose user scale the callback applies. Callbacks only run while its windows exist;
 * a new manager replaces it in csd_install. */
WindowManager *g_wm = nullptr;
std::atomic<uint64_t> g_calls{0};

int px(const float v_1x, const float scale)
{
  return std::max(1, int(std::lround(v_1x * scale)));
}

void split_ghost_layout(const GHOST_CSD_Layout &l,
                        std::vector<CsdButtonKind> &left,
                        std::vector<CsdButtonKind> &right)
{
  bool after_title = false;
  for (int i = 0; i < l.buttons_num && i < int(sizeof(l.buttons) / sizeof(l.buttons[0])); i++) {
    CsdButtonKind kind;
    switch (l.buttons[i]) {
      case GHOST_kCSDTypeTitlebar:
        after_title = true;
        continue;
      case GHOST_kCSDTypeButtonClose: kind = CsdButtonKind::Close; break;
      case GHOST_kCSDTypeButtonMaximize: kind = CsdButtonKind::Maximize; break;
      case GHOST_kCSDTypeButtonMinimize: kind = CsdButtonKind::Minimize; break;
      case GHOST_kCSDTypeButtonMenu: kind = CsdButtonKind::Menu; break;
      default: continue;
    }
    (after_title ? right : left).push_back(kind);
  }
}

GHOST_TCSD_Type ghost_type(const CsdButtonKind k)
{
  switch (k) {
    case CsdButtonKind::Close: return GHOST_kCSDTypeButtonClose;
    case CsdButtonKind::Maximize: return GHOST_kCSDTypeButtonMaximize;
    case CsdButtonKind::Minimize: return GHOST_kCSDTypeButtonMinimize;
    case CsdButtonKind::Menu: return GHOST_kCSDTypeButtonMenu;
  }
  return GHOST_kCSDTypeBody;
}

int32_t layout_callback(const int32_t window_size[2],
                        const int32_t fractional_scale[2],
                        const GHOST_TWindowState state,
                        const GHOST_CSD_Layout *csd_layout,
                        GHOST_CSD_Elem *elems)
{
  g_calls++;
  const int w = std::max(1, int(window_size[0])), h = std::max(1, int(window_size[1]));
  float scale = fractional_scale[0] > 0 ? float(fractional_scale[1]) / float(fractional_scale[0]) : 1.0f;
  if (g_wm) {
    scale *= g_wm->user_scale();
  }
  std::vector<CsdButtonKind> left, right;
  if (csd_layout) {
    split_ghost_layout(*csd_layout, left, right);
  }
  const CsdLayout l = csd_compute_layout(w, h, scale, left, right, state != GHOST_kWindowStateNormal);

  /* GHOST: top-left origin, inclusive bounds, first match wins; at most GHOST_kCSDType_NUM. */
  int n = 0;
  auto add = [&](const Rect &r, const GHOST_TCSD_Type type) {
    if (r.empty() || n >= GHOST_kCSDType_NUM) {
      return;
    }
    GHOST_CSD_Elem &e = elems[n++];
    e.bounds[0][0] = r.xmin;
    e.bounds[0][1] = r.xmax - 1;
    e.bounds[1][0] = h - r.ymax;
    e.bounds[1][1] = h - r.ymin - 1;
    e.type = type;
  };
  if (l.border > 0) {
    const int b = l.border, c = 3 * l.border;
    add({0, h - c, c, h}, GHOST_kCSDTypeBorderTopLeft);
    add({w - c, h - c, w, h}, GHOST_kCSDTypeBorderTopRight);
    add({0, 0, c, c}, GHOST_kCSDTypeBorderBottomLeft);
    add({w - c, 0, w, c}, GHOST_kCSDTypeBorderBottomRight);
    add({0, h - b, w, h}, GHOST_kCSDTypeBorderTop);
    add({0, 0, w, b}, GHOST_kCSDTypeBorderBottom);
    add({0, 0, b, h}, GHOST_kCSDTypeBorderLeft);
    add({w - b, 0, w, h}, GHOST_kCSDTypeBorderRight);
  }
  for (const CsdButton &btn : l.buttons) {
    add(btn.rect, ghost_type(btn.kind));
  }
  add(l.drag, GHOST_kCSDTypeTitlebar);
  /* Everything else (the menus and the content) belongs to the application. */
  add({0, 0, w, h}, GHOST_kCSDTypeBody);
  return n;
}

}  // namespace

void csd_configure(const CsdConfig &config)
{
  g_config = config;
}

const CsdConfig &csd_config()
{
  return g_config;
}

CsdLayout csd_compute_layout(const int width,
                             const int height,
                             const float ui_scale_in,
                             const std::vector<CsdButtonKind> &left,
                             const std::vector<CsdButtonKind> &right,
                             const bool maximized)
{
  const float s = ui_scale_in > 0.0f ? ui_scale_in : 1.0f;
  CsdLayout l;
  const int bar = std::min(height, ui_bar_height_px(s));
  l.titlebar = {0, height - bar, width, height};
  l.border = maximized ? 0 : px(g_config.border_1x, s);
  const int bw = px(g_config.button_width_1x, s);
  int x = 0;
  for (const CsdButtonKind k : left) {
    l.buttons.push_back({k, {x, height - bar, std::min(width, x + bw), height}});
    x += bw;
  }
  l.left_reserve = x;
  int xr = width;
  for (auto it = right.rbegin(); it != right.rend(); ++it) {
    l.buttons.push_back({*it, {std::max(0, xr - bw), height - bar, xr, height}});
    xr -= bw;
  }
  l.right_reserve = width - xr;
  const int drag_x0 = std::min(xr, l.left_reserve + px(g_config.menu_width_1x, s));
  l.drag = {drag_x0, height - bar, std::max(drag_x0, xr), height};
  return l;
}

bool csd_active(const WindowManager &wm)
{
  const char *backend = GHOST_ISystem::getSystemBackend();
  if (!backend || strcmp(backend, "WAYLAND") != 0) {
    return false;
  }
  return (wm.ghost_system().getCapabilities() & GHOST_kCapabilityWindowDecorationServerSide) == 0;
}

CsdLayout csd_layout(const Window &window)
{
  if (!csd_active(window.manager()) || !window.ghost_window()) {
    return {};
  }
  std::vector<CsdButtonKind> left, right;
  split_ghost_layout(window.manager().ghost_system().getWindowCSD_Layout(), left, right);
  const GHOST_TWindowState state = window.ghost_window()->getState();
  return csd_compute_layout(
      window.width(), window.height(), window.ui_scale(), left, right, state != GHOST_kWindowStateNormal);
}

uint64_t csd_layout_calls()
{
  return g_calls.load();
}

void csd_install(WindowManager &wm)
{
  g_wm = &wm;
  GHOST_CSD_Params params{};
  params.layout_callback = layout_callback;
  params.cursor_drag_threshold = 3;
  params.cursor_double_click_ms = 350;
  wm.ghost_system().setWindowCSD(params);
}

}  // namespace stk::wm
