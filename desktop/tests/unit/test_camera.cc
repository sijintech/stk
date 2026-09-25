/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Camera parity: suan.render.layers.fit_camera / default_view_up (Python) and web/src/camera.ts
 * cameraPose / presetOf / cameraSignature (web), plus navigation and camera-relative matrices. */
#include "support.hh"

#include "stk/io/payload.hh"
#include "stk/viewer/camera.hh"
#include "stk/viewer/scene.hh"

#include <gtest/gtest.h>

#include <cmath>
#include <numbers>

using namespace stk;
using namespace stk::viewer;
using io::Json;

namespace {

dvec3 vec(const Json &j)
{
  return {j[0].get<double>(), j[1].get<double>(), j[2].get<double>()};
}

void expect_near(const dvec3 &a, const dvec3 &b, double tol, const std::string &what)
{
  const double scale = std::max(1.0, length(b));
  EXPECT_LE(length(a - b), tol * scale) << what << ": (" << a.x << ", " << a.y << ", " << a.z << ") vs (" << b.x
                                        << ", " << b.y << ", " << b.z << ")";
}

Bounds web_bounds(const Json &b)
{
  return {{b[0].get<double>(), b[2].get<double>(), b[4].get<double>()},
          {b[1].get<double>(), b[3].get<double>(), b[5].get<double>()}};
}

void expect_pose(const CameraPose &pose, const Json &web, const std::string &what)
{
  expect_near(pose.position, vec(web["position"]), 1e-12, what + " position");
  expect_near(pose.focal_point, vec(web["focalPoint"]), 1e-12, what + " focal");
  expect_near(pose.view_up, vec(web["viewUp"]), 1e-12, what + " up");
  EXPECT_NEAR(pose.view_angle_deg, web["viewAngle"].get<double>(), 1e-12) << what;
  EXPECT_EQ(pose.parallel, web["parallel"].get<bool>()) << what;
  EXPECT_NEAR(pose.parallel_scale, web["parallelScale"].get<double>(), 1e-12 * std::max(1.0, pose.parallel_scale))
      << what;
}

}  // namespace

TEST(CameraParity, FitCameraMatchesPython)
{
  const Json cases = test::fixture_json("camera_cases.json");
  for (const Json &c : cases["fit"]) {
    const Bounds b{vec(c["bounds"][0]), vec(c["bounds"][1])};
    const auto preset = parse_camera_preset(c["preset"].get<std::string>());
    ASSERT_TRUE(preset.has_value());
    const CameraPose pose = fit_camera(b, *preset, c["angle"].get<double>(), c["zoom"].get<double>());
    const std::string what = c["preset"].get<std::string>();
    expect_near(pose.position, vec(c["position"]), 1e-14, what);
    expect_near(pose.focal_point, vec(c["focal_point"]), 1e-15, what);
    expect_near(pose.view_up, vec(c["view_up"]), 0, what);
    EXPECT_NEAR(pose.parallel_scale, c["parallel_scale"].get<double>(), 1e-15 * pose.parallel_scale);
  }
  for (const Json &c : cases["default_view_up"]) {
    EXPECT_EQ(default_view_up(vec(c["position"]), vec(c["focal"])), vec(c["up"]));
  }
}

TEST(CameraParity, CameraPoseMatchesTheWebViewer)
{
  const Json web = test::fixture_json("web_vectors.json");
  int count = 0;
  for (const Json &c : web["cameras"]) {
    const Json view = c["view"].is_null() ? Json() : c["view"];
    const CameraPose pose = camera_pose(view, vec(c["origin"]), web_bounds(c["bounds"]));
    expect_pose(pose, c["pose"], view.dump());
    const auto preset = view_preset(view);
    if (c["preset"].is_null()) {
      EXPECT_FALSE(preset.has_value()) << view.dump();
    }
    else {
      EXPECT_EQ(preset.value_or("<numeric>"), c["preset"].get<std::string>()) << view.dump();
    }
    count++;
  }
  /* Signatures: equal exactly when the web signatures are equal. */
  const Json &cameras = web["cameras"];
  for (size_t i = 0; i < cameras.size(); i++) {
    for (size_t j = i + 1; j < cameras.size(); j++) {
      const bool web_equal = cameras[i]["signature"] == cameras[j]["signature"];
      const Json vi = cameras[i]["view"].is_null() ? Json() : cameras[i]["view"];
      const Json vj = cameras[j]["view"].is_null() ? Json() : cameras[j]["view"];
      EXPECT_EQ(camera_signature(vi) == camera_signature(vj), web_equal) << vi.dump() << " vs " << vj.dump();
    }
  }
  /* The payload fixtures (example and the encoded scenes). */
  for (auto it = web["payloads"].begin(); it != web["payloads"].end(); ++it) {
    const io::Payload p = it.key() == "example"
                              ? io::read_directory(test::example_dir())
                              : io::read_stkp(test::fixtures_dir() / "payload" / "scenes" / (it.key() + ".stkp"));
    const Json *manifest_bounds = &p.manifest["bounds"];
    const Bounds b = p.manifest.contains("bounds") ? Bounds{vec((*manifest_bounds)[0]), vec((*manifest_bounds)[1])}
                                                   : Bounds{};
    const Json view = p.manifest.value("view", Json());
    expect_pose(camera_pose(view, dvec3::from(p.render_origin), b), it.value()["camera"], it.key());
    count++;
  }
  std::printf("[camera parity] %d poses identical to web/src/camera.ts cameraPose (<= 1e-12)\n", count);
  for (const std::string name : {"+x", "-x", "+y", "-y", "+z", "-z", "iso"}) {
    const PresetFrame f = preset_frame(*parse_camera_preset(name));
    const Json &w = web["presets"][name];
    expect_near(f.direction, vec(w["u"]), 0, "preset u");
    expect_near(f.view_up, vec(w["up"]), 0, "preset up");
  }
}

TEST(Camera, NavigationKeepsInvariants)
{
  const Bounds b{{-1, -2, -3}, {3, 2, 1}};
  const Viewport vp{800, 600};
  for (NavigationStyle style : {NavigationStyle::Blender, NavigationStyle::ParaView}) {
    CameraPose pose = fit_camera(b, CameraPreset::Iso);
    const double d = pose.distance();
    const dvec3 focal = pose.focal_point;
    orbit(pose, style, 37, -12, vp);
    EXPECT_NEAR(pose.distance(), d, 1e-12 * d);
    expect_near(pose.focal_point, focal, 0, "orbit keeps the focal point");
    EXPECT_NEAR(dot(pose.view_up, pose.direction()), 0.0, 1e-12);
    EXPECT_NEAR(length(pose.view_up), 1.0, 1e-12);
  }
  /* Blender turntable: yaw there and back is the identity; ParaView: 360 degrees of azimuth. */
  CameraPose a = fit_camera(b, CameraPreset::PosX);
  const CameraPose start = a;
  orbit(a, NavigationStyle::Blender, 50, 0, vp);
  orbit(a, NavigationStyle::Blender, -50, 0, vp);
  expect_near(a.position, start.position, 1e-12, "turntable round trip");
  CameraPose t = fit_camera(b, CameraPreset::Iso);
  const CameraPose t0 = t;
  orbit(t, NavigationStyle::ParaView, -vp.width * 1.8, 0, vp); /* 360 degrees */
  expect_near(t.position, t0.position, 1e-9, "trackball full turn");

  /* Pan: the focal point follows the cursor. */
  CameraPose p = fit_camera(b, CameraPreset::Iso);
  const dvec3 focal0 = p.focal_point;
  pan(p, 40, -25, vp);
  const auto s = project(p, vp, focal0);
  ASSERT_TRUE(s.has_value());
  EXPECT_NEAR(s->x, vp.width / 2 + 40, 1e-9);
  EXPECT_NEAR(s->y, vp.height / 2 - 25, 1e-9);

  /* Dolly and zoom-to-point. */
  CameraPose z = fit_camera(b, CameraPreset::Iso);
  const double d0 = z.distance();
  dolly(z, 2.0);
  EXPECT_NEAR(z.distance(), d0 / 2, 1e-12 * d0);
  CameraPose q = fit_camera(b, CameraPreset::PosZ);
  const Ray r0 = pixel_ray(q, vp, 600, 150);
  const double t_focal = dot(q.focal_point - r0.origin, q.direction()) / dot(r0.direction, q.direction());
  const dvec3 under = r0.at(t_focal);
  dolly_to(q, 1.7, 600, 150, vp);
  const auto s2 = project(q, vp, under);
  ASSERT_TRUE(s2.has_value());
  EXPECT_NEAR(s2->x, 600, 1e-9);
  EXPECT_NEAR(s2->y, 150, 1e-9);
  CameraPose par = fit_camera(b, CameraPreset::PosY, 30, 1, true);
  dolly(par, 4.0);
  EXPECT_NEAR(par.parallel_scale, b.radius() / 4, 1e-15);

  /* Roll and view_all. */
  CameraPose rl = fit_camera(b, CameraPreset::PosX);
  roll(rl, 90);
  EXPECT_NEAR(std::abs(dot(rl.view_up, {0, 1, 0})), 1.0, 1e-12);
  view_all(rl, b);
  EXPECT_NEAR(rl.distance(), b.radius() / std::sin(15 * std::numbers::pi / 180), 1e-12);
}

TEST(Camera, RaysAndProjectionAreInverse)
{
  const Viewport vp{640, 480};
  for (bool parallel : {false, true}) {
    CameraPose pose = fit_camera(Bounds{{-5, -5, -5}, {5, 5, 5}}, CameraPreset::Iso, 40, 1, parallel);
    for (double x : {0.0, 100.5, 320.0, 639.0}) {
      for (double y : {0.0, 240.0, 479.5}) {
        const Ray ray = pixel_ray(pose, vp, x, y);
        const auto s = project(pose, vp, ray.at(7.25));
        ASSERT_TRUE(s.has_value());
        EXPECT_NEAR(s->x, x, 1e-9);
        EXPECT_NEAR(s->y, y, 1e-9);
      }
    }
  }
}

TEST(Camera, MatricesAreCameraRelative)
{
  /* A scene 1e6 away from zero: poses and layer offsets are relative to render_origin, and the model-view
   * translation (layer offset - eye) is formed in double before the float cast. */
  const dvec3 render_origin{1e6, -3, 7};
  Json view = {{"schema", "stk.view/1"},
               {"camera", {{"position", {1e6 + 10, -3 + 0.5, 7 + 4}}, {"focal_point", {1e6 + 0.25, -3, 7}}}}};
  const Bounds b{{-1, -1, -1}, {1, 1, 1}};
  const CameraPose pose = camera_pose(view, render_origin, b);
  expect_near(pose.position, {10, 0.5, 4}, 1e-15, "relative position");
  const CameraMatrices m = camera_matrices(pose, 4.0 / 3.0, clip_range(pose, b));
  /* The focal point projects to the centre of the viewport. */
  const dvec3 layer_offset{0.125, 0, 0};
  const dmat4 mvp = m.model_view_projection(layer_offset);
  const dvec3 ndc = mvp.transform_point(pose.focal_point - layer_offset);
  EXPECT_NEAR(ndc.x, 0.0, 1e-12);
  EXPECT_NEAR(ndc.y, 0.0, 1e-12);
  EXPECT_GT(ndc.z, -1.0);
  EXPECT_LT(ndc.z, 1.0);
  /* Float32 matrices keep sub-micrometre precision next to the camera even at 1e6. */
  const std::array<float, 16> f = m.model_view_projection_f(layer_offset);
  const dvec3 p{0.25 - 0.125 + 1e-6, 0, 0};
  const double x = f[0] * p.x + f[4] * p.y + f[8] * p.z + f[12];
  const double w = f[3] * p.x + f[7] * p.y + f[11] * p.z + f[15];
  const dvec3 exact = mvp.transform_point(p);
  EXPECT_NEAR(x / w, exact.x, 1e-6);
  const auto inv = m.model_view(layer_offset).inverted() * m.model_view(layer_offset);
  for (int i = 0; i < 4; i++) {
    for (int j = 0; j < 4; j++) {
      EXPECT_NEAR(inv.m[i][j], i == j ? 1.0 : 0.0, 1e-12);
    }
  }
  const Json numeric = numeric_camera_json(pose, render_origin);
  EXPECT_EQ(numeric["position"][0].get<double>(), 1e6 + 10);
}
