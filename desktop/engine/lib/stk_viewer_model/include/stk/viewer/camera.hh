/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Float64 camera of the payload viewer (docs/specs/stk-graph-v1.md §7, web/src/camera.ts,
 * suan/render/layers.py fit_camera). Poses are kept relative to the payload's render_origin so every
 * matrix handed to the GPU is camera-relative: float32 vertex positions (relative to a layer origin)
 * are transformed by a model-view matrix whose translation is the small double difference
 * (layer origin - camera eye), so far-from-zero scenes (render_origin = 1e6) keep full precision. */

#include "stk/io/json.hh"
#include "stk/viewer/math.hh"

#include <optional>
#include <string>
#include <string_view>

namespace stk::viewer {

enum class CameraPreset { PosX, NegX, PosY, NegY, PosZ, NegZ, Iso };
inline constexpr CameraPreset kCameraPresets[] = {CameraPreset::Iso,
                                                  CameraPreset::PosX,
                                                  CameraPreset::NegX,
                                                  CameraPreset::PosY,
                                                  CameraPreset::NegY,
                                                  CameraPreset::PosZ,
                                                  CameraPreset::NegZ};

std::optional<CameraPreset> parse_camera_preset(std::string_view name);
std::string_view camera_preset_name(CameraPreset preset);
/** Unit direction from the focal point to the camera ("+x" = looking from +x) and the view-up. */
struct PresetFrame {
  dvec3 direction, view_up;
};
PresetFrame preset_frame(CameraPreset preset);

/** Axis-aligned bounds relative to render_origin. */
struct Bounds {
  dvec3 lo{-1, -1, -1}, hi{1, 1, 1};

  dvec3 center() const
  {
    return (lo + hi) * 0.5;
  }
  /** Bounding-sphere radius (half the diagonal; 1 for empty bounds, as web/offscreen). */
  double radius() const;
  bool valid() const;
  void expand(const dvec3 &p);
  static Bounds empty();
};

/** A camera pose relative to render_origin. */
struct CameraPose {
  dvec3 position{0, 0, 1};
  dvec3 focal_point{0, 0, 0};
  dvec3 view_up{0, 1, 0};
  double view_angle_deg = 30.0;
  bool parallel = false;
  double parallel_scale = 1.0;

  double distance() const
  {
    return length(position - focal_point);
  }
  /** Unit direction of projection (camera -> focal point). */
  dvec3 direction() const
  {
    return normalize(focal_point - position);
  }
  /** Orthonormal camera frame: right, up, back (towards the viewer). */
  void frame(dvec3 &right, dvec3 &up, dvec3 &back) const;
};

/** suan.render.layers.fit_camera: focal point = centre, position = c + u r / sin(theta/2) / zoom,
 * parallel scale r / zoom. */
CameraPose fit_camera(const Bounds &bounds,
                      CameraPreset preset,
                      double view_angle_deg = 30.0,
                      double zoom = 1.0,
                      bool parallel = false);

/** suan.render.layers.default_view_up: +z, or +y when the view direction is within 0.999 of z. */
dvec3 default_view_up(const dvec3 &position, const dvec3 &focal_point);

/** The stk.view/1 camera object of a view document ({} when absent or malformed). */
io::Json view_camera(const io::Json &view);
/** web presetOf: the camera or view preset; nullopt for a numeric camera (position + focal point). */
std::optional<std::string> view_preset(const io::Json &view);
/** web cameraSignature: changes only when the requested view changes (not with new step bounds). */
std::string camera_signature(const io::Json &view);

/**
 * web cameraPose: the numeric camera when given (physical coordinates, converted relative to
 * render_origin; a numeric camera without a preset narrows the view angle by its zoom), else the
 * preset fitted to `bounds`. View-up falls back to z (or y when looking along z).
 */
CameraPose camera_pose(const io::Json &view, const dvec3 &render_origin, const Bounds &bounds);

/** Numeric stk.view/1 camera (physical coordinates) of a pose, e.g. for the numeric-camera panel. */
io::Json numeric_camera_json(const CameraPose &pose, const dvec3 &render_origin);

struct Viewport {
  double width = 1, height = 1;
  double aspect() const
  {
    return height > 0 ? width / height : 1.0;
  }
};

enum class NavigationStyle {
  Blender,  /* turntable about world +z; pan and dolly as Blender's viewport */
  ParaView, /* trackball camera (vtkInteractorStyleTrackballCamera: azimuth/elevation about view up) */
};

/** Orbit by a mouse drag of (dx, dy) pixels (y down). */
void orbit(CameraPose &pose, NavigationStyle style, double dx, double dy, const Viewport &viewport);
/** Pan so the point under the cursor follows the mouse at focal-point depth. */
void pan(CameraPose &pose, double dx, double dy, const Viewport &viewport);
/** Dolly (perspective) or zoom (parallel) by `factor` (> 1 moves closer). */
void dolly(CameraPose &pose, double factor);
/** Dolly towards the point under the cursor (Blender "zoom to mouse position"). */
void dolly_to(CameraPose &pose, double factor, double x, double y, const Viewport &viewport);
/** Roll about the view direction. */
void roll(CameraPose &pose, double degrees);
/** Keep the view direction and up; fit the distance (and parallel scale) to `bounds`. */
void view_all(CameraPose &pose, const Bounds &bounds);
/** Re-orthogonalize view_up against the view direction (vtkCamera::OrthogonalizeViewUp). */
void orthogonalize_view_up(CameraPose &pose);

/** Near/far planes enclosing `bounds` (relative to render_origin) with a margin. */
struct ClipRange {
  double near_z, far_z;
};
ClipRange clip_range(const CameraPose &pose, const Bounds &bounds);

/**
 * Camera-relative matrices. `view` has no translation (the eye is at the origin of eye space);
 * `model_view(offset)` maps float32 positions stored relative to a layer origin, where
 * offset = layer origin - render_origin, by rotating (p + offset - eye) — the translation is formed
 * in double before the cast, so it stays exact near the camera.
 */
struct CameraMatrices {
  dmat4 view_rotation;
  dmat4 projection;
  dvec3 eye; /* relative to render_origin */

  dmat4 model_view(const dvec3 &layer_offset) const;
  dmat4 model_view_projection(const dvec3 &layer_offset) const;
  std::array<float, 16> model_view_projection_f(const dvec3 &layer_offset) const
  {
    return model_view_projection(layer_offset).to_float();
  }
};
CameraMatrices camera_matrices(const CameraPose &pose, double aspect, const ClipRange &clip);

/** A ray relative to render_origin: origin + t * direction (direction normalized). */
struct Ray {
  dvec3 origin, direction;
  dvec3 at(double t) const
  {
    return origin + direction * t;
  }
};
/** The ray through pixel coordinates (x, y) (continuous, y down, (0,0) = top-left corner). */
Ray pixel_ray(const CameraPose &pose, const Viewport &viewport, double x, double y);
/** Screen position (pixels, y down) and eye depth of a point relative to render_origin; nullopt behind the camera. */
std::optional<dvec3> project(const CameraPose &pose, const Viewport &viewport, const dvec3 &point);

}  // namespace stk::viewer
