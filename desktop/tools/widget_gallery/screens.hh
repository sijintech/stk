/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Widget gallery screens (ui_core only): the same screens drive the layout goldens in
 * desktop/tests/ui and the GPU widget_gallery executable.
 */
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "stk/ui/form.hh"
#include "stk/ui/ui.hh"

namespace stk::ui::gallery {

enum class Screen { Widgets, Lists, Form, Overlays, Gallery };
const char *screen_name(Screen s);

struct Job {
  int id;
  std::string name;
  int state; /* 0 done, 1 running, 2 failed */
  double seconds;
};

/** Application state the gallery widgets are bound to. */
struct State {
  Catalog catalog;
  bool show_grid = true;
  bool autorefresh = false;
  std::string job_name;
  double threshold = 0.1;
  double length = 12.5;
  double small_step = 1.0e-4;
  float opacity = 0.75f;
  int view = 0;
  int colormap = 0;
  int tab = 0;
  float progress = 0.62f;
  int list_selected = 42;
  int table_selected = 3;
  float split = 0.45f;
  int clicks = 0;
  bool modal_open = true;
  LogBuffer log;
  std::vector<Job> jobs;
  std::shared_ptr<std::vector<ColormapItem>> colormaps;
  SchemaNode form_schema;
  FormModel form;
  bool has_form = false;
  uint64_t image_texture = 1;
  int image_w = 96;
  int image_h = 64;
};

/** Viridis, plasma (polynomial fits), coolwarm and gray, 256 entries each. */
std::vector<ColormapItem> make_colormaps();

/** Loads desktop/app/i18n and sets the language ("zh_CN" or "en"). */
bool init_state(State &s, const std::string &desktop_dir, const std::string &lang, std::string *err = nullptr);
/** Loads the muferro-domains preset form from the repository (catalog + preset JSON). */
bool load_form(State &s, const std::string &repo_root, std::string *err = nullptr);

/** Builds one frame of a screen (begin_frame .. end_frame). */
void build(Context &ctx, State &s, Screen screen, Vec2 window, double now);
/**
 * Builds the screen and stages the interactive overlays shown by the gallery and the overlay
 * golden: IME preedit in the job-name field, the view dropdown open, the Run tooltip, a toast
 * (and the modal, which the screen builds while `modal_open`).
 */
void build_staged(Context &ctx, State &s, Screen screen, Vec2 window, double now);

/** Logical window size of a screen at scale 1. */
Vec2 screen_size(Screen s);

}  // namespace stk::ui::gallery
