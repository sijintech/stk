/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file STK shim: the draw module's debug-draw lock used by #GPU_context_active_set. */
#pragma once

namespace blender::draw {

class DebugDraw {
 public:
  static DebugDraw &get()
  {
    static DebugDraw instance;
    return instance;
  }
  void acquire() {}
  void release() {}
};

}  // namespace blender::draw
