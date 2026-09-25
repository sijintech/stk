/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Widget theme (Blender's uiWidgetColors per widget type plus the few space colours the toolkit
 * uses) and the metric style derived from the UI scale. Theme::blender_dark() carries the values of
 * Blender 5.2.1's default theme (see theme.cc for the source file and field mapping).
 */
#pragma once

#include "stk/ui/geom.hh"
#include "stk/ui/text.hh"

namespace stk::ui {

/** Mirrors Blender's uiWidgetColors (DNA_theme_types.h). */
struct WidgetColors {
  Color outline, outline_sel;
  Color inner, inner_sel;
  Color item;
  Color text, text_sel;
  /** Corner radius as a fraction of the widget unit (Blender: roundness * U.widget_unit). */
  float roundness = 0.2f;
};

/** Mirrors uiWidgetStateColors (subset). */
struct StateColors {
  Color error, warning, info, success;
};

struct Theme {
  WidgetColors regular, tool, text, option, toggle, num, numslider, tab, menu, pulldown, menu_back,
      menu_item, tooltip, box, scroll, progress, list_item;
  StateColors state;
  Color widget_emboss;
  float menu_shadow_fac = 0.2f;
  float menu_shadow_width = 6.0f; /* Pixels at scale 1. */
  Color editor_border;
  Color text_cursor;
  Color link;
  float panel_roundness = 0.4f;
  Color panel_header, panel_back, panel_sub_back, panel_outline, panel_title, panel_text;
  /** Region/space colours (Properties editor). */
  Color region_back, header_back, space_text, space_text_hi, space_title;
  /** Dimming behind modal dialogs (toolkit addition, not in Blender). */
  Color modal_dim;

  static Theme blender_dark();
};

/**
 * Metrics derived from the UI scale (DPI scale x user scale). Everything is defined in UI units
 * (1 U = Blender's U.widget_unit = round(18 * scale) + 2 * pixelsize, i.e. 20 px at scale 1) and
 * rounded to whole pixels, following Blender's uiStyle defaults.
 */
struct Style {
  float scale = 1.0f;
  float pixel = 1.0f; /**< U.pixelsize: line width. */
  float unit = 20.0f; /**< U.widget_unit. */
  FontStyle font;      /**< Widget text: 11 pt x scale. */
  FontStyle mono;
  float space_x = 8.0f;       /**< buttonspacex: gap between row items. */
  float space_y = 2.0f;       /**< buttonspacey: gap between column items. */
  float column_space = 8.0f;  /**< columnspace: grid-flow column gap. */
  float box_space = 5.0f;     /**< boxspace: box padding. */
  float text_margin = 8.0f;   /**< UI_TEXT_MARGIN_X (0.4 U). */
  float panel_margin = 8.0f;  /**< UI_PANEL_MARGIN_X. */
  float panel_space = 8.0f;   /**< panelspace: gap between panels. */
  float panel_header = 24.0f; /**< Panel header height (1.2 U). */
  float line_height = 16.0f;  /**< Paragraph line advance. */
  float scrollbar = 7.0f;     /**< Scrollbar width (0.35 U). */

  static Style from_scale(float scale);
  /** Converts UI units to pixels (rounded). */
  float u(float units) const;
};

}  // namespace stk::ui
