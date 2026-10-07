/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_graph_canvas.hh"
#include "stk/core/utf8.hh"

#include <algorithm>
#include <cmath>
#include <limits>

namespace stk::app {
namespace {

std::shared_ptr<AnalysisGraphView> single()
{
  auto result = std::make_shared<AnalysisGraphView>();
  AnalysisGraphNode node;
  node.id = "source"; node.type = "stk.source.data@1"; node.label = "source";
  node.title_en = "Data source"; node.title_zh = "数据来源";
  node.known_type = true; node.stage = "source";
  node.rect = {50, 40, 180, 80};
  AnalysisGraphPort output;
  output.name = "out"; output.type_text = "dataset"; output.declared = true;
  output.point = {230, 84};
  node.outputs.push_back(output);
  result->nodes.push_back(node);
  result->bounds = node.rect;
  return result;
}

std::shared_ptr<AnalysisGraphView> linked()
{
  auto result = single();
  auto target = result->nodes[0];
  target.id = "target"; target.label = "target"; target.title_en = "Result"; target.title_zh = "结果";
  target.rect = {500, 180, 180, 80};
  target.inputs = target.outputs;
  target.inputs[0].name = "in"; target.inputs[0].point = {500, 224};
  target.outputs.clear();
  result->nodes.push_back(target);
  result->bounds = {50, 40, 630, 220};
  AnalysisGraphEdge edge;
  edge.source = 0; edge.target = 1; edge.output = 0; edge.input = 0;
  edge.from = result->nodes[0].outputs[0].point; edge.to = target.inputs[0].point;
  result->edges.push_back(edge);
  return result;
}

void finite_commands(const ui::DrawList &draw)
{
  for (const auto &command : draw.cmds) {
    EXPECT_TRUE(std::isfinite(command.rect.x));
    EXPECT_TRUE(std::isfinite(command.rect.y));
    EXPECT_TRUE(std::isfinite(command.rect.w));
    EXPECT_TRUE(std::isfinite(command.rect.h));
    EXPECT_TRUE(std::isfinite(command.pos.x));
    EXPECT_TRUE(std::isfinite(command.pos.y));
    EXPECT_TRUE(std::isfinite(command.font.size_px));
    for (const auto &point : command.p) { EXPECT_TRUE(std::isfinite(point.x)); EXPECT_TRUE(std::isfinite(point.y)); }
  }
}

TEST(AnalysisGraphCanvas, FitCentersBoundsAndTransformsRoundTripAtHiDpi)
{
  const auto view = linked();
  AnalysisGraphCanvas canvas;
  canvas.set_view(view);
  ASSERT_TRUE(canvas.fit(1100, 700, 2));
  EXPECT_EQ(canvas.ui_scale(), 2);
  const auto center = canvas.to_screen({view->bounds.x + view->bounds.width / 2, view->bounds.y + view->bounds.height / 2});
  EXPECT_NEAR(center.x, 550, 1e-9);
  EXPECT_NEAR(center.y, 350, 1e-9);
  const auto first = canvas.to_screen({view->bounds.x, view->bounds.y});
  const auto last = canvas.to_screen({view->bounds.x + view->bounds.width, view->bounds.y + view->bounds.height});
  EXPECT_GE(first.x, 64 - 1e-9);
  EXPECT_GE(first.y, 64 - 1e-9);
  EXPECT_LE(last.x, 1036 + 1e-9);
  EXPECT_LE(last.y, 636 + 1e-9);
  const auto original = AnalysisGraphPoint{-432.25, 918.125};
  const auto restored = canvas.to_graph(canvas.to_screen(original));
  EXPECT_NEAR(restored.x, original.x, 1e-9);
  EXPECT_NEAR(restored.y, original.y, 1e-9);
}

TEST(AnalysisGraphCanvas, FitIncludesExtremeContractPositionsWithoutOverflowOrAnArbitraryZoomFloor)
{
  auto view = linked();
  view->nodes[0].rect = {-1e6, -1e6, 180, 80};
  view->nodes[1].rect = {1e6, 1e6, 180, 80};
  view->nodes[0].outputs.clear(); view->nodes[1].inputs.clear(); view->edges.clear();
  view->bounds = {-1e6, -1e6, 2e6 + 180, 2e6 + 80};
  AnalysisGraphCanvas canvas;
  canvas.set_view(view);
  ASSERT_TRUE(canvas.fit(800, 600));
  EXPECT_LT(canvas.zoom(), .001);
  EXPECT_GE(canvas.zoom(), AnalysisGraphCanvas::min_zoom);
  const auto low = canvas.to_screen({-1e6, -1e6});
  const auto high = canvas.to_screen({1e6 + 180, 1e6 + 80});
  EXPECT_GE(low.x, 32 - 1e-8);
  EXPECT_GE(low.y, 32 - 1e-8);
  EXPECT_LE(high.x, 768 + 1e-8);
  EXPECT_LE(high.y, 568 + 1e-8);
  ui::FakeTextMeasurer measurer;
  const auto draw = canvas.draw_list(800, 600, 1, measurer, "zh_CN");
  finite_commands(draw);
  EXPECT_FALSE(std::any_of(draw.cmds.begin(), draw.cmds.end(), [](const auto &cmd) { return cmd.type == ui::CmdType::Text; }));
}

TEST(AnalysisGraphCanvas, InvalidFitAndNavigationInputsLeaveTheTransformUnchanged)
{
  AnalysisGraphCanvas canvas;
  canvas.set_view(single());
  ASSERT_TRUE(canvas.fit(600, 400));
  const double zoom = canvas.zoom(), x = canvas.pan_x(), y = canvas.pan_y();
  const double nan = std::numeric_limits<double>::quiet_NaN(), inf = std::numeric_limits<double>::infinity();
  EXPECT_FALSE(canvas.fit(0, 400));
  EXPECT_FALSE(canvas.fit(nan, 400));
  EXPECT_FALSE(canvas.fit(400, inf));
  EXPECT_FALSE(canvas.fit(400, 400, 0));
  EXPECT_FALSE(canvas.fit(400, 400, 9));
  EXPECT_FALSE(canvas.pan(nan, 2));
  EXPECT_FALSE(canvas.pan(0, inf));
  EXPECT_FALSE(canvas.pan(1e12, 0));
  EXPECT_FALSE(canvas.zoom_at(0, 300, 200));
  EXPECT_FALSE(canvas.zoom_at(-1, 300, 200));
  EXPECT_FALSE(canvas.zoom_at(inf, 300, 200));
  EXPECT_FALSE(canvas.zoom_at(1, nan, 200));
  EXPECT_EQ(canvas.zoom(), zoom);
  EXPECT_EQ(canvas.pan_x(), x);
  EXPECT_EQ(canvas.pan_y(), y);
  ui::FakeTextMeasurer measurer;
  EXPECT_TRUE(canvas.draw_list(-1, 400, 1, measurer, "en").cmds.empty());
  EXPECT_EQ(canvas.pan_x(), x);
}

TEST(AnalysisGraphCanvas, CursorAnchoredZoomAndPhysicalPanKeepTheirExactMeaning)
{
  AnalysisGraphCanvas canvas;
  canvas.set_view(linked());
  ASSERT_TRUE(canvas.fit(900, 600, 1.5));
  const auto anchor = canvas.to_graph({233, 317});
  ASSERT_TRUE(canvas.zoom_at(1.3, 233, 317));
  const auto after = canvas.to_graph({233, 317});
  EXPECT_NEAR(after.x, anchor.x, 1e-9);
  EXPECT_NEAR(after.y, anchor.y, 1e-9);
  const auto before_pan = canvas.to_screen(anchor);
  ASSERT_TRUE(canvas.pan(81.25, -43.5));
  const auto after_pan = canvas.to_screen(anchor);
  EXPECT_NEAR(after_pan.x - before_pan.x, 81.25, 1e-9);
  EXPECT_NEAR(after_pan.y - before_pan.y, -43.5, 1e-9);
  ASSERT_TRUE(canvas.zoom_at(1e6, 400, 300));
  EXPECT_EQ(canvas.zoom(), AnalysisGraphCanvas::max_zoom);
  ASSERT_TRUE(canvas.zoom_at(1e-12, 400, 300));
  EXPECT_EQ(canvas.zoom(), AnalysisGraphCanvas::min_zoom);
  EXPECT_TRUE(std::isfinite(canvas.pan_x()));
  EXPECT_TRUE(std::isfinite(canvas.pan_y()));
}

TEST(AnalysisGraphCanvas, ResizePreservesNavigationAndDpiChangeKeepsCenterWorldAnchor)
{
  AnalysisGraphCanvas canvas;
  canvas.set_view(linked());
  ASSERT_TRUE(canvas.fit(900, 600));
  ASSERT_TRUE(canvas.pan(-100, 50));
  const double zoom = canvas.zoom(), x = canvas.pan_x(), y = canvas.pan_y();
  ui::FakeTextMeasurer measurer;
  canvas.draw_list(1200, 800, 1, measurer, "en");
  EXPECT_EQ(canvas.zoom(), zoom);
  EXPECT_EQ(canvas.pan_x(), x);
  EXPECT_EQ(canvas.pan_y(), y);
  const auto anchor = canvas.to_graph({600, 400});
  canvas.draw_list(1200, 800, 2, measurer, "en");
  EXPECT_EQ(canvas.zoom(), zoom);
  EXPECT_EQ(canvas.ui_scale(), 2);
  const auto after = canvas.to_graph({600, 400});
  EXPECT_NEAR(after.x, anchor.x, 1e-9);
  EXPECT_NEAR(after.y, anchor.y, 1e-9);
}

TEST(AnalysisGraphCanvas, SameViewRetainsNavigationAndReplacementResetsWithoutRestoringOldSelection)
{
  const auto view = single();
  AnalysisGraphCanvas canvas;
  canvas.set_view(view);
  ASSERT_TRUE(canvas.fit(800, 600));
  ASSERT_TRUE(canvas.pan(15, 27));
  const double zoom = canvas.zoom(), x = canvas.pan_x(), y = canvas.pan_y();
  canvas.set_view(view);
  EXPECT_EQ(canvas.zoom(), zoom);
  EXPECT_EQ(canvas.pan_x(), x);
  EXPECT_EQ(canvas.pan_y(), y);
  canvas.set_view(single());
  EXPECT_EQ(canvas.zoom(), 1);
  EXPECT_EQ(canvas.pan_x(), 0);
  EXPECT_EQ(canvas.pan_y(), 0);
  EXPECT_FALSE(canvas.hit(100, 80));
  canvas.set_view({});
  EXPECT_FALSE(canvas.fit(800, 600));
  EXPECT_FALSE(canvas.hit(100, 80));
}

TEST(AnalysisGraphCanvas, EditedVersionsKeepNavigationSocketsHitAndDraggedNodesMoveWithTheirLinks)
{
  AnalysisGraphCanvas canvas;
  canvas.set_view(linked());
  ASSERT_TRUE(canvas.fit(900, 600));
  ASSERT_TRUE(canvas.pan(12, -8));
  const double zoom = canvas.zoom(), x = canvas.pan_x(), y = canvas.pan_y();
  canvas.set_view(linked(), true);  // an edited version of the same graph keeps the camera
  EXPECT_EQ(canvas.zoom(), zoom); EXPECT_EQ(canvas.pan_x(), x); EXPECT_EQ(canvas.pan_y(), y);
  ui::FakeTextMeasurer measurer;
  canvas.draw_list(900, 600, 1, measurer, "en");
  const auto output = canvas.to_screen({230, 84}), input = canvas.to_screen({500, 224});
  const auto hit_out = canvas.hit_port(output.x + 3, output.y - 2);
  ASSERT_TRUE(hit_out); EXPECT_TRUE(hit_out->output); EXPECT_EQ(hit_out->node, 0u); EXPECT_EQ(hit_out->port, 0u);
  const auto hit_in = canvas.hit_port(input.x, input.y);
  ASSERT_TRUE(hit_in); EXPECT_FALSE(hit_in->output); EXPECT_EQ(hit_in->node, 1u);
  EXPECT_FALSE(canvas.hit_port(input.x + 40, input.y + 40));
  // A pending link adds drawing on top; clearing it removes it again.
  const auto plain = canvas.draw_list(900, 600, 1, measurer, "en").cmds.size();
  canvas.set_pending_link(std::pair{output, AnalysisGraphPoint{output.x + 200, output.y + 100}});
  const auto pending = canvas.draw_list(900, 600, 1, measurer, "en");
  EXPECT_GT(pending.cmds.size(), plain);
  finite_commands(pending);
  canvas.set_pending_link(std::nullopt);
  EXPECT_EQ(canvas.draw_list(900, 600, 1, measurer, "en").cmds.size(), plain);
  // Moving the target shifts its rect, sockets and the end of its link only.
  const auto moved = analysis_graph_view_moved(*linked(), 1, 30, -10);
  EXPECT_EQ(moved.nodes[1].rect.x, 530); EXPECT_EQ(moved.nodes[1].rect.y, 170);
  EXPECT_EQ(moved.nodes[1].inputs[0].point.x, 530);
  EXPECT_EQ(moved.edges[0].to.x, 530); EXPECT_EQ(moved.edges[0].from.x, 230);
  EXPECT_EQ(moved.nodes[0].rect.x, 50);
  EXPECT_EQ(analysis_graph_view_moved(*linked(), 9, 1, 1).nodes[1].rect.x, 500);  // out of range: unchanged
}

TEST(AnalysisGraphCanvas, HitTestingUsesReverseDrawOrderAndViewportClipping)
{
  auto view = single();
  view->nodes.push_back(view->nodes.front());
  view->nodes.back().id = "overlap";
  AnalysisGraphCanvas canvas;
  canvas.set_view(view);
  ASSERT_TRUE(canvas.fit(800, 600));
  const auto point = canvas.to_screen({100, 80});
  ASSERT_TRUE(canvas.hit(point.x, point.y));
  EXPECT_EQ(*canvas.hit(point.x, point.y), 1u);
  const auto right = canvas.to_screen({230, 80});
  EXPECT_FALSE(canvas.hit(right.x, right.y));
  EXPECT_FALSE(canvas.hit(-1, point.y));
  EXPECT_FALSE(canvas.hit(800, point.y));
  EXPECT_FALSE(canvas.hit(point.x, 600));
  EXPECT_FALSE(canvas.hit(std::numeric_limits<double>::quiet_NaN(), 0));
  ui::FakeTextMeasurer measurer;
  canvas.draw_list(800, 600, 1, measurer, "en", 0);
  EXPECT_EQ(*canvas.hit(point.x, point.y), 1u) << "Highlighting must not secretly change draw/hit ordering";
}

TEST(AnalysisGraphCanvas, DrawListClipsCurvesAndNodesAndKeepsClipCommandsBalanced)
{
  const auto view = linked();
  AnalysisGraphCanvas canvas;
  canvas.set_view(view);
  ASSERT_TRUE(canvas.fit(800, 600));
  ASSERT_TRUE(canvas.pan(-250, 0));
  ui::FakeTextMeasurer measurer;
  const auto draw = canvas.draw_list(800, 600, 1, measurer, "en", 1);
  ASSERT_FALSE(draw.cmds.empty());
  EXPECT_EQ(draw.cmds.front().type, ui::CmdType::ClipPush);
  EXPECT_EQ(draw.cmds.front().rect, (ui::Rect{0, 0, 800, 600}));
  EXPECT_EQ(draw.cmds.back().type, ui::CmdType::ClipPop);
  int depth = 0, triangles = 0;
  bool highlighted = false;
  for (const auto &cmd : draw.cmds) {
    if (cmd.type == ui::CmdType::ClipPush) { ++depth; }
    if (cmd.type == ui::CmdType::ClipPop) { --depth; }
    EXPECT_GE(depth, 0);
    if (cmd.type == ui::CmdType::Triangle) {
      ++triangles;
      for (const auto &p : cmd.p) { EXPECT_GE(p.x, -4); EXPECT_LE(p.x, 804); EXPECT_GE(p.y, -4); EXPECT_LE(p.y, 604); }
    }
    if (cmd.type == ui::CmdType::RoundBox && cmd.outline == ui::Color::rgb(0xBBDCF2)) { highlighted = true; }
  }
  EXPECT_EQ(depth, 0);
  EXPECT_GT(triangles, 0);
  EXPECT_LE(triangles, 40);
  EXPECT_TRUE(highlighted);
  finite_commands(draw);
}

TEST(AnalysisGraphCanvas, GridAndEdgeDrawCommandsStayBoundedEvenForMalformedOversizeView)
{
  ui::FakeTextMeasurer measurer;
  AnalysisGraphCanvas empty;
  EXPECT_LE(empty.draw_list(1e6, 1e6, 1, measurer, "en").cmds.size(), 260u);
  auto view = linked();
  const auto edge = view->edges.front();
  view->edges.assign(5000, edge);
  AnalysisGraphCanvas canvas;
  canvas.set_view(view);
  ASSERT_TRUE(canvas.fit(900, 600));
  const auto draw = canvas.draw_list(900, 600, 1, measurer, "en");
  const auto triangles = std::count_if(draw.cmds.begin(), draw.cmds.end(), [](const auto &cmd) { return cmd.type == ui::CmdType::Triangle; });
  EXPECT_EQ(triangles, AnalysisGraphView::max_edges * 40);
  EXPECT_LT(draw.cmds.size(), AnalysisGraphView::max_edges * 40 + 200);
}

TEST(AnalysisGraphCanvas, FarGeometryIsCulledBeforeFloatConversionAndInvalidCoordinatesNeverDraw)
{
  auto view = linked();
  view->nodes[0].rect.x = 1e6;
  view->nodes[1].rect.x = std::numeric_limits<double>::infinity();
  view->edges[0].from = {1e300, 1e300};
  view->edges[0].to = {-1e300, -1e300};
  AnalysisGraphCanvas canvas;
  canvas.set_view(view);
  ui::FakeTextMeasurer measurer;
  const auto draw = canvas.draw_list(800, 600, 1, measurer, "en");
  EXPECT_FALSE(std::any_of(draw.cmds.begin(), draw.cmds.end(), [](const auto &cmd) {
    return cmd.type == ui::CmdType::RoundBox || cmd.type == ui::CmdType::Triangle || cmd.type == ui::CmdType::Text;
  }));
  finite_commands(draw);
}

TEST(AnalysisGraphCanvas, CjkTitlesAreClippedAsUtf8AndFineLabelsDisappearAtOverviewZoom)
{
  auto view = single();
  view->nodes[0].title_zh.clear();
  for (int i = 0; i < 60; ++i) { view->nodes[0].title_zh += "温度🧪"; }
  AnalysisGraphCanvas canvas;
  canvas.set_view(view);
  ASSERT_TRUE(canvas.fit(600, 400));
  ui::FakeTextMeasurer measurer;
  const auto chinese = canvas.draw_list(600, 400, 1, measurer, "zh_CN");
  bool found = false;
  const double room = (view->nodes[0].rect.width - 16) * canvas.zoom();
  for (const auto &cmd : chinese.cmds) {
    if (cmd.type != ui::CmdType::Text) { continue; }
    EXPECT_TRUE(core::utf8::is_valid(cmd.text));
    if (cmd.text.starts_with("温度")) {
      found = true;
      EXPECT_TRUE(cmd.text.ends_with("…"));
      EXPECT_LE(measurer.width(cmd.text, cmd.font), room + .001);
    }
  }
  EXPECT_TRUE(found);
  ASSERT_TRUE(canvas.zoom_at(.1, 300, 200));
  const auto overview = canvas.draw_list(600, 400, 1, measurer, "zh_CN");
  EXPECT_FALSE(std::any_of(overview.cmds.begin(), overview.cmds.end(), [](const auto &cmd) { return cmd.type == ui::CmdType::Text; }));
  EXPECT_EQ(view->nodes[0].title_zh.size(), std::string("温度🧪").size() * 60);
}

}  // namespace
}  // namespace stk::app
