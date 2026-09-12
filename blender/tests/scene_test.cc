/* SPDX-FileCopyrightText: 2026 STK Authors
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk_scene.hh"
#include <cassert>
using namespace blender::ed::stk;

static bool near(double a, double b)
{
  return std::abs(a - b) < 1e-9;
}

int main()
{
  Scene s;
  s.positions = {{0, 0, 0}, {2, 0, 0}, {0, 2, 0}};
  s.values = {0, 2, 4};
  s.indices = {0, 1, 2};
  s.render_origin = {1e6, -3, 10};
  s.lower = 0;
  s.upper = 4;
  assert(s.validate());
  Camera camera{0, 0, 1, 0, 0};
  auto p = s.pick(camera, -.5, -.5, 1);
  assert(p && near((*p)[0], 1e6 + .5) && near((*p)[1], -2.5) && near((*p)[2], 10));
  assert(!s.pick(camera, .9, .9, 1));
  assert(!s.pick(camera, 0, 0, 0));
  // The front triangle must win regardless of index order.
  s.positions.insert(s.positions.end(), {{0, 0, 1}, {2, 0, 1}, {0, 2, 1}});
  s.values.insert(s.values.end(), {1, 3, 5});
  s.indices.insert(s.indices.end(), {3, 4, 5});
  assert(s.validate());
  p = s.pick(camera, -.5, -.5, 1);
  assert(p && near((*p)[2], 11));
  camera.yaw = 90;
  camera.zoom = 2;
  camera.pan_x = .1;
  camera.pan_y = -.2;
  // Independent 90-degree rotation: (-.5,-.5) becomes (.5,-.5),
  // then zoom and pan, and a 2:1 viewport applies only to horizontal scale.
  p = s.pick(camera, .55, -1.2, 2);
  assert(p && near((*p)[0], 1e6 + .5) && near((*p)[1], -2.5) && near((*p)[2], 11));
  camera = Camera{};
  camera.zoom = s.fit_zoom(camera, .4);
  for (const auto &vertex : s.positions) {
    const auto projected = camera.project(vertex, s.center, s.extent, .4);
    assert(std::abs(projected[0]) <= .800001 && std::abs(projected[1]) <= .800001);
  }
  const auto low = color(-100, 0, 4), high = color(100, 0, 4), midpoint = color(7, 7, 7);
  assert(low[0] == .10f && high[0] == .98f && midpoint[1] == .67f);
  s.indices.push_back(0);
  assert(!s.validate());
  s.indices.pop_back();
  s.indices[0] = 999;
  assert(!s.validate());
  s.indices[0] = 0;
  s.values[0] = std::numeric_limits<double>::quiet_NaN();
  assert(!s.validate());
}
