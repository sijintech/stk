/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Layout persistence: the screen tree (Screen::to_json), language, UI scale and window geometry
 * in one versioned JSON file, by default `<user config>/desktop/layout.json`
 * (~/.config/stk/desktop/layout.json on Linux, see stk::core::user_config_dir).
 *
 *   {
 *     "format": "stk.desktop.layout", "version": 1,
 *     "window": {"width": 1280, "height": 800, "x": 0, "y": 0, "maximized": false},
 *     "language": "zh_CN", "ui_scale": 1.0,
 *     "screen": {"maximized": null, "root": {...}}
 *   }
 *
 * Loading validates the header here and the tree in Screen::from_json; a missing, unreadable,
 * corrupt or newer-version file makes the application fall back to its default layout.
 */
#pragma once

#include <filesystem>
#include <string>

#include <nlohmann/json.hpp>

namespace stk::wm {

inline constexpr const char *kLayoutFormat = "stk.desktop.layout";
inline constexpr int kLayoutVersion = 1;
/** Files above this size are rejected as corrupt (a real layout is a few KiB). */
inline constexpr size_t kLayoutMaxBytes = 1 << 20;

struct WindowGeometry {
  /** Client size in logical points (0 = application default). */
  int width = 0;
  int height = 0;
  /** Top-left position in screen coordinates (ignored on Wayland, which has no positions). */
  int x = 0;
  int y = 0;
  bool has_position = false;
  bool maximized = false;
};

struct LayoutFile {
  int version = kLayoutVersion;
  WindowGeometry window;
  /** Catalog language ("zh_CN", "en"). */
  std::string language;
  /** User UI scale (multiplied with the display DPI factor). */
  float ui_scale = 1.0f;
  /** Screen::to_json(). */
  nlohmann::json screen;
};

nlohmann::json layout_to_json(const LayoutFile &file);
/** Validates the header fields (not the screen tree). */
bool layout_from_json(const nlohmann::json &json, LayoutFile &r_file, std::string *r_error = nullptr);

/** `<user config>/desktop/layout.json`. */
std::filesystem::path default_layout_path();

/** Writes atomically (temporary file + rename), creating the parent directory. */
bool save_layout_file(const std::filesystem::path &path, const LayoutFile &file, std::string *r_error = nullptr);

enum class LayoutLoad : uint8_t { Ok, Missing, Corrupt };
LayoutLoad load_layout_file(const std::filesystem::path &path, LayoutFile &r_file, std::string *r_error = nullptr);

/**
 * Moves a corrupt layout file aside to `<path>.corrupt` (replacing an older one) so the next save
 * does not silently destroy it. Returns the new path (empty on failure).
 */
std::filesystem::path quarantine_layout_file(const std::filesystem::path &path);

}  // namespace stk::wm
