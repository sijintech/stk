/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/camera.hh"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>

namespace stk::viewer {

using io::Json;

namespace {

constexpr double kDeg = std::numbers::pi / 180.0;

const Json *get(const Json &object, std::string_view key)
{
  if (!object.is_object()) {
    return nullptr;
  }
  const auto it = object.find(key);
  return it == object.end() ? nullptr : &*it;
}

/* web camera.ts isVec3: three finite numbers (booleans are not numbers). */
std::optional<dvec3> vec3(const Json *value)
{
  if (!value || !value->is_array() || value->size() != 3) {
    return std::nullopt;
  }
  for (const Json &v : *value) {
    if (!io::is_finite_number(v)) {
      return std::nullopt;
    }
  }
  return dvec3{(*value)[0].get<double>(), (*value)[1].get<double>(), (*value)[2].get<double>()};
}

/* web camera.ts positive(v, fallback). */
double positive(const Json *value, double fallback)
{
  if (value && io::is_finite_number(*value) && value->get<double>() > 0) {
    return value->get<double>();
  }
  return fallback;
}

/* Rotate `p` about the axis through `center` by `radians`. */
dvec3 rotate_about(const dvec3 &p, const dvec3 &center, const dvec3 &axis, double radians)
{
  return dmat4::rotation(axis, radians).transform_direction(p - center) + center;
}

}  // namespace

std::optional<CameraPreset> parse_camera_preset(std::string_view name)
{
  for (CameraPreset preset : kCameraPresets) {
    if (camera_preset_name(preset) == name) {
      return preset;
    }
  }
  return std::nullopt;
}

std::string_view camera_preset_name(CameraPreset preset)
{
  switch (preset) {
    case CameraPreset::PosX:
      return "+x";
    case CameraPreset::NegX:
      return "-x";
    case CameraPreset::PosY:
      return "+y";
    case CameraPreset::NegY:
      return "-y";
    case CameraPreset::PosZ:
      return "+z";
    case CameraPreset::NegZ:
      return "-z";
    case CameraPreset::Iso:
      return "iso";
  }
  return "iso";
}

PresetFrame preset_frame(CameraPreset preset)
{
  const double s3 = 1.0 / std::sqrt(3.0);
  switch (preset) {
    case CameraPreset::PosX:
      return {{1, 0, 0}, {0, 0, 1}};
    case CameraPreset::NegX:
      return {{-1, 0, 0}, {0, 0, 1}};
    case CameraPreset::PosY:
      return {{0, 1, 0}, {0, 0, 1}};
    case CameraPreset::NegY:
      return {{0, -1, 0}, {0, 0, 1}};
    case CameraPreset::PosZ:
      return {{0, 0, 1}, {0, 1, 0}};
    case CameraPreset::NegZ:
      return {{0, 0, -1}, {0, 1, 0}};
    case CameraPreset::Iso:
      return {{s3, -s3, s3}, {0, 0, 1}};
  }
  return {{s3, -s3, s3}, {0, 0, 1}};
}

double Bounds::radius() const
{
  const double r = 0.5 * std::hypot(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z);
  return (r > 0 && std::isfinite(r)) ? r : 1.0;
}

bool Bounds::valid() const
{
  return is_finite(lo) && is_finite(hi) && lo.x <= hi.x && lo.y <= hi.y && lo.z <= hi.z;
}

void Bounds::expand(const dvec3 &p)
{
  lo = {std::min(lo.x, p.x), std::min(lo.y, p.y), std::min(lo.z, p.z)};
  hi = {std::max(hi.x, p.x), std::max(hi.y, p.y), std::max(hi.z, p.z)};
}

Bounds Bounds::empty()
{
  const double inf = std::numeric_limits<double>::infinity();
  return {{inf, inf, inf}, {-inf, -inf, -inf}};
}

void CameraPose::frame(dvec3 &right, dvec3 &up, dvec3 &back) const
{
  const dvec3 dop = direction();
  right = normalize(cross(dop, view_up));
  up = cross(right, dop);
  back = -dop;
}

CameraPose fit_camera(const Bounds &bounds, CameraPreset preset, double view_angle_deg, double zoom, bool parallel)
{
  const PresetFrame f = preset_frame(preset);
  const dvec3 center = bounds.center();
  const double r = bounds.radius();
  const double distance = r / std::sin(view_angle_deg * kDeg / 2.0) / zoom;
  CameraPose pose;
  pose.focal_point = center;
  pose.position = center + f.direction * distance;
  pose.view_up = f.view_up;
  pose.view_angle_deg = view_angle_deg;
  pose.parallel = parallel;
  pose.parallel_scale = r / zoom;
  return pose;
}

namespace {

/* web camera.ts unit(): a / (|a| || 1). */
dvec3 unit_or_zero(const dvec3 &a)
{
  double l = std::hypot(a.x, a.y, a.z);
  if (!(l != 0.0) || std::isnan(l)) {
    l = 1.0;
  }
  return a * (1.0 / l);
}

/* `up`, unless within 1e-6 of the view direction: then +z, or +y when looking along z (spec §2.1). */
dvec3 up_for(const dvec3 &up, const dvec3 &direction)
{
  if (length(cross(unit_or_zero(up), direction)) < 1e-6) {
    return std::abs(direction.z) > 0.99 ? dvec3{0, 1, 0} : dvec3{0, 0, 1};
  }
  return up;
}

}  // namespace

dvec3 default_view_up(const dvec3 &position, const dvec3 &focal_point)
{
  return up_for({0, 0, 1}, unit_or_zero(focal_point - position));
}

Json view_camera(const Json &view)
{
  const Json *camera = get(view, "camera");
  return camera && camera->is_object() ? *camera : Json::object();
}

std::optional<std::string> view_preset(const Json &view)
{
  const Json camera = view_camera(view);
  const Json *preset = get(camera, "preset");
  if (!preset || preset->is_null()) {
    preset = view.is_object() ? get(view, "preset") : nullptr; /* cam.preset ?? view.preset */
  }
  if (preset && preset->is_string() && !preset->get_ref<const std::string &>().empty()) {
    return preset->get<std::string>();
  }
  if (vec3(get(camera, "position")) && vec3(get(camera, "focal_point"))) {
    return std::nullopt;
  }
  return std::string("iso");
}

std::string camera_signature(const Json &view)
{
  const Json camera = view_camera(view);
  const auto or_null = [&](const char *key) {
    const Json *v = get(camera, key);
    return v ? *v : Json();
  };
  const std::optional<std::string> preset = view_preset(view);
  Json signature = Json::array();
  if (preset) {
    signature = {"preset", *preset};
  }
  else {
    signature = {"numeric", or_null("position"), or_null("focal_point")};
  }
  for (const char *key : {"projection", "view_angle_deg", "zoom", "view_up"}) {
    signature.push_back(or_null(key));
  }
  return io::canonical_json(signature);
}

CameraPose camera_pose(const Json &view, const dvec3 &o, const Bounds &b)
{
  const Json camera = view_camera(view);
  const dvec3 center = b.center();
  double radius = 0.5 * std::hypot(b.hi.x - b.lo.x, b.hi.y - b.lo.y, b.hi.z - b.lo.z);
  if (!(radius != 0.0) || std::isnan(radius)) {
    radius = 1.0; /* `|| 1` in camera.ts */
  }
  const double requested = positive(get(camera, "view_angle_deg"), 30.0);
  const double angle = requested < 180 ? requested : 30.0;
  const double zoom = positive(get(camera, "zoom"), 1.0);
  const Json *projection = get(camera, "projection");
  const bool parallel = projection && projection->is_string() && *projection == "parallel";
  const std::optional<std::string> preset = view_preset(view);
  const double parallel_scale = positive(get(camera, "parallel_scale"), radius / zoom);
  const auto position = vec3(get(camera, "position"));
  const auto focal = vec3(get(camera, "focal_point"));
  const auto requested_up = vec3(get(camera, "view_up"));
  CameraPose pose;
  pose.parallel = parallel;
  pose.parallel_scale = parallel_scale;
  if (position && focal && *position != *focal) {
    pose.position = *position - o;
    pose.focal_point = *focal - o;
    const dvec3 dop = unit_or_zero(pose.focal_point - pose.position);
    pose.view_up = up_for(requested_up ? *requested_up : dvec3{0, 0, 1}, dop);
    pose.view_angle_deg = !parallel && !preset ? angle / zoom : angle;
    return pose;
  }
  const CameraPreset fitted = parse_camera_preset(preset.value_or("iso")).value_or(CameraPreset::Iso);
  const PresetFrame f = preset_frame(fitted);
  const double distance = radius / std::sin(angle * std::numbers::pi / 360.0) / zoom;
  pose.view_up = f.view_up;
  if (requested_up && length(cross(unit_or_zero(*requested_up), f.direction)) > 1e-6) {
    pose.view_up = *requested_up;
  }
  pose.position = center + f.direction * distance;
  pose.focal_point = center;
  pose.view_angle_deg = angle;
  return pose;
}

Json numeric_camera_json(const CameraPose &pose, const dvec3 &o)
{
  const auto arr = [](const dvec3 &v) { return Json::array({v.x, v.y, v.z}); };
  return {{"projection", pose.parallel ? "parallel" : "perspective"},
          {"position", arr(pose.position + o)},
          {"focal_point", arr(pose.focal_point + o)},
          {"view_up", arr(pose.view_up)},
          {"view_angle_deg", pose.view_angle_deg},
          {"parallel_scale", pose.parallel_scale}};
}

void orthogonalize_view_up(CameraPose &pose)
{
  const dvec3 dop = pose.direction();
  dvec3 up = pose.view_up - dop * dot(pose.view_up, dop);
  if (length(up) < 1e-12) {
    up = default_view_up(pose.position, pose.focal_point);
    up = up - dop * dot(up, dop);
  }
  pose.view_up = normalize(up);
}

void orbit(CameraPose &pose, NavigationStyle style, double dx, double dy, const Viewport &viewport)
{
  if (style == NavigationStyle::Blender) {
    /* Turntable (Blender's default): yaw about world +z, pitch about the camera's right axis;
     * 0.4 degrees per pixel (U.view_rotate_sensitivity_turntable). */
    const double k = 0.4 * kDeg;
    dvec3 right, up, back;
    pose.frame(right, up, back);
    const dmat4 yaw = dmat4::rotation({0, 0, 1}, -dx * k);
    const dmat4 pitch = dmat4::rotation(right, -dy * k);
    const dmat4 r = yaw * pitch;
    pose.position = r.transform_direction(pose.position - pose.focal_point) + pose.focal_point;
    pose.view_up = normalize(r.transform_direction(up));
    return;
  }
  /* vtkInteractorStyleTrackballCamera::Rotate: MotionFactor 10, -20/size degrees per pixel,
   * VTK's y axis points up. */
  const double azimuth = dx * (-20.0 / std::max(1.0, viewport.width)) * 10.0;
  const double elevation = -dy * (-20.0 / std::max(1.0, viewport.height)) * 10.0;
  /* vtkCamera::Azimuth: rotate the position about the view up through the focal point. */
  pose.position = rotate_about(pose.position, pose.focal_point, pose.view_up, azimuth * kDeg);
  /* vtkCamera::Elevation: rotate about -right (the negated first row of the view matrix). */
  dvec3 right, up, back;
  pose.frame(right, up, back);
  pose.position = rotate_about(pose.position, pose.focal_point, -right, elevation * kDeg);
  orthogonalize_view_up(pose);
}

namespace {

double world_per_pixel(const CameraPose &pose, const Viewport &viewport)
{
  const double h = std::max(1.0, viewport.height);
  if (pose.parallel) {
    return 2.0 * pose.parallel_scale / h;
  }
  return 2.0 * pose.distance() * std::tan(pose.view_angle_deg * kDeg / 2.0) / h;
}

}  // namespace

void pan(CameraPose &pose, double dx, double dy, const Viewport &viewport)
{
  dvec3 right, up, back;
  pose.frame(right, up, back);
  const double k = world_per_pixel(pose, viewport);
  const dvec3 shift = right * (-dx * k) + up * (dy * k);
  pose.position += shift;
  pose.focal_point += shift;
}

void dolly(CameraPose &pose, double factor)
{
  if (!(factor > 0) || !std::isfinite(factor)) {
    return;
  }
  if (pose.parallel) {
    pose.parallel_scale /= factor;
    return;
  }
  const dvec3 dop = pose.direction();
  pose.position = pose.focal_point - dop * (pose.distance() / factor);
}

void dolly_to(CameraPose &pose, double factor, double x, double y, const Viewport &viewport)
{
  if (!(factor > 0) || !std::isfinite(factor)) {
    return;
  }
  dvec3 right, up, back;
  pose.frame(right, up, back);
  const double k = world_per_pixel(pose, viewport);
  /* The focal-plane point under the cursor stays under the cursor. */
  const dvec3 target = pose.focal_point + right * ((x - viewport.width / 2.0) * k) +
                       up * ((viewport.height / 2.0 - y) * k);
  const dvec3 shift = (target - pose.focal_point) * (1.0 - 1.0 / factor);
  pose.focal_point += shift;
  pose.position += shift;
  dolly(pose, factor);
}

void roll(CameraPose &pose, double degrees)
{
  pose.view_up = normalize(dmat4::rotation(pose.direction(), -degrees * kDeg).transform_direction(pose.view_up));
}

void view_all(CameraPose &pose, const Bounds &bounds)
{
  const dvec3 dop = pose.direction();
  const double r = bounds.radius();
  pose.focal_point = bounds.center();
  pose.position = pose.focal_point - dop * (r / std::sin(pose.view_angle_deg * kDeg / 2.0));
  pose.parallel_scale = r;
}

ClipRange clip_range(const CameraPose &pose, const Bounds &bounds)
{
  const dvec3 dop = pose.direction();
  const double r = bounds.radius() * 1.01;
  const double depth = dot(bounds.center() - pose.position, dop);
  double far_z = depth + r;
  double near_z = depth - r;
  if (!pose.parallel) {
    far_z = std::max(far_z, 1e-6);
    near_z = std::max(near_z, far_z * 1e-4);
  }
  if (!(far_z > near_z)) {
    far_z = near_z + 1.0;
  }
  return {near_z, far_z};
}

dmat4 CameraMatrices::model_view(const dvec3 &layer_offset) const
{
  return view_rotation * dmat4::translation(layer_offset - eye);
}

dmat4 CameraMatrices::model_view_projection(const dvec3 &layer_offset) const
{
  return projection * model_view(layer_offset);
}

CameraMatrices camera_matrices(const CameraPose &pose, double aspect, const ClipRange &clip)
{
  CameraMatrices out;
  out.eye = pose.position;
  out.view_rotation = look_at({0, 0, 0}, pose.focal_point - pose.position, pose.view_up);
  if (pose.parallel) {
    const double s = pose.parallel_scale;
    out.projection = orthographic(-s * aspect, s * aspect, -s, s, clip.near_z, clip.far_z);
  }
  else {
    out.projection = perspective(pose.view_angle_deg, aspect, clip.near_z, clip.far_z);
  }
  return out;
}

Ray pixel_ray(const CameraPose &pose, const Viewport &viewport, double x, double y)
{
  dvec3 right, up, back;
  pose.frame(right, up, back);
  const double nx = 2.0 * x / std::max(1.0, viewport.width) - 1.0;
  const double ny = 1.0 - 2.0 * y / std::max(1.0, viewport.height);
  const double aspect = viewport.aspect();
  const dvec3 dop = -back;
  if (pose.parallel) {
    const double s = pose.parallel_scale;
    return {pose.position + right * (nx * s * aspect) + up * (ny * s), dop};
  }
  const double t = std::tan(pose.view_angle_deg * kDeg / 2.0);
  return {pose.position, normalize(dop + right * (nx * t * aspect) + up * (ny * t))};
}

std::optional<dvec3> project(const CameraPose &pose, const Viewport &viewport, const dvec3 &point)
{
  dvec3 right, up, back;
  pose.frame(right, up, back);
  const dvec3 e = point - pose.position;
  const double ex = dot(e, right), ey = dot(e, up), depth = -dot(e, back);
  double nx, ny;
  if (pose.parallel) {
    nx = ex / (pose.parallel_scale * viewport.aspect());
    ny = ey / pose.parallel_scale;
  }
  else {
    if (!(depth > 0)) {
      return std::nullopt;
    }
    const double t = std::tan(pose.view_angle_deg * kDeg / 2.0);
    nx = ex / (depth * t * viewport.aspect());
    ny = ey / (depth * t);
  }
  return dvec3{(nx + 1.0) / 2.0 * viewport.width, (1.0 - ny) / 2.0 * viewport.height, depth};
}

}  // namespace stk::viewer
