/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * GPU painter. The rounded-box path follows Blender's interface_widgets.cc: the widget batch
 * (batch_roundbox_widget_get: 12 vertices, 6 triangles, positions computed in the shader) with
 * GPU_SHADER_2D_WIDGET_BASE and the WidgetBaseParameters uniform block (round_box__edges,
 * shape_preset_* for the decorations).
 */
#include "stk/ui/gpu_painter.hh"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

#include "BLF_api.hh"
#include "GPU_batch.hh"
#include "GPU_immediate.hh"
#include "GPU_immediate_util.hh"
#include "GPU_index_buffer.hh"
#include "GPU_matrix.hh"
#include "GPU_shader.hh"
#include "GPU_state.hh"
#include "GPU_texture.hh"
#include "GPU_vertex_buffer.hh"
#include "GPU_vertex_format.hh"

namespace stk::ui::gpu {

namespace bgpu = blender::gpu;
using namespace blender;

/* -------------------------------------------------------------------- */
/* Fonts and measurement */

float BlfTextMeasurer::width(std::string_view text, const FontStyle &style) const
{
  if (text.empty()) {
    return 0.0f;
  }
  const int id = font(style);
  BLF_size(id, style.size_px);
  return BLF_width(id, text.data(), text.size());
}

FontMetrics BlfTextMeasurer::metrics(const FontStyle &style) const
{
  const int id = font(style);
  BLF_size(id, style.size_px);
  return {float(BLF_ascender(id)), std::fabs(float(BLF_descender(id)))};
}

/* -------------------------------------------------------------------- */
/* Painter */

namespace {

/** Must match the widget-base shader layout (Blender's WidgetBaseParameters). */
struct WidgetParams {
  float recti[4]; /* xmin, xmax, ymin, ymax */
  float rect[4];
  float radi, rad;
  float facxi, facyi;
  float round_corners[4]; /* bottom-left, bottom-right, top-right, top-left */
  float color_inner1[4], color_inner2[4];
  float color_outline[4], color_emboss[4];
  float color_tria[4];
  float tria1_center[2], tria2_center[2];
  float tria1_size, tria2_size;
  float shade_dir;
  float alpha_discard;
  float tria_type;
  float pad[3];
};
static_assert(sizeof(WidgetParams) == 12 * 4 * sizeof(float));

enum { TRIA_NONE = 0, TRIA_ARROWS = 1, TRIA_SCROLL = 2, TRIA_MENU = 3, TRIA_CHECK = 4, TRIA_HOLD = 5, TRIA_DASH = 6 };

void set_color(float dst[4], const Color &c)
{
  dst[0] = c.r / 255.0f;
  dst[1] = c.g / 255.0f;
  dst[2] = c.b / 255.0f;
  dst[3] = c.a / 255.0f;
}

bgpu::Batch *create_widget_batch()
{
  static GPUVertFormat format = {0};
  if (format.attr_len == 0) {
    GPU_vertformat_attr_add(&format, "vflag", bgpu::VertAttrType::UINT_32);
  }
  bgpu::VertBuf *vbo = GPU_vertbuf_create_with_format(format);
  /* The shader derives positions from the vertex index; the attribute only fixes the layout
   * (Blender leaves the data uninitialized too). */
  GPU_vertbuf_data_alloc(*vbo, 12);
  GPUIndexBufBuilder ibuf;
  GPU_indexbuf_init(&ibuf, GPU_PRIM_TRIS, 6, 12);
  GPU_indexbuf_add_tri_verts(&ibuf, 0, 1, 2);
  GPU_indexbuf_add_tri_verts(&ibuf, 2, 1, 3);
  GPU_indexbuf_add_tri_verts(&ibuf, 4, 5, 6);
  GPU_indexbuf_add_tri_verts(&ibuf, 6, 5, 7);
  GPU_indexbuf_add_tri_verts(&ibuf, 8, 9, 10);
  GPU_indexbuf_add_tri_verts(&ibuf, 10, 9, 11);
  return GPU_batch_create_ex(GPU_PRIM_TRIS, vbo, GPU_indexbuf_build(&ibuf),
                             GPU_BATCH_OWNS_INDEX | GPU_BATCH_OWNS_VBO);
}

/** Scissor stack. Clip rectangles are viewport-local (top-left origin); the scissor is set in
 * framebuffer pixels, offset by the viewport origin (a WP1 region draws with its own viewport) and
 * never larger than the viewport. */
struct Clip {
  std::vector<Rect> stack;
  int vp[4] = {0, 0, 0, 0}; /* viewport x, y, w, h in framebuffer pixels */

  void apply() const
  {
    int x0 = 0, y0 = 0, x1 = vp[2], y1 = vp[3];
    if (!stack.empty()) {
      const Rect &r = stack.back();
      x0 = std::max(x0, int(std::floor(r.x)));
      x1 = std::min(x1, int(std::ceil(r.x1())));
      y0 = std::max(y0, int(std::floor(float(vp[3]) - r.y1())));
      y1 = std::min(y1, int(std::ceil(float(vp[3]) - r.y)));
    }
    GPU_scissor(vp[0] + x0, vp[1] + y0, std::max(0, x1 - x0), std::max(0, y1 - y0));
    GPU_scissor_test(true);
  }
};

}  // namespace

GpuPainter::~GpuPainter()
{
  if (widget_batch_) {
    GPU_batch_discard(widget_batch_);
  }
}

void GpuPainter::paint(const DrawList &list, Vec2 viewport)
{
  const float H = viewport.y;
  if (!widget_batch_) {
    widget_batch_ = create_widget_batch();
  }
  GPU_matrix_push_projection();
  GPU_matrix_ortho_set(0.0f, viewport.x, 0.0f, H, -1.0f, 1.0f);
  GPU_matrix_push();
  GPU_matrix_identity_set();
  GPU_blend(GPU_BLEND_ALPHA);
  Clip clip;
  GPU_viewport_size_get_i(clip.vp);
  clip.apply();

  const float checker[3] = {0.2f, 0.3f, 8.0f};
  const float px = pixel_;

  for (const DrawCmd &c : list.cmds) {
    /* BLF and immediate mode may change the blend state; widgets need straight alpha blending. */
    GPU_blend(GPU_BLEND_ALPHA);
    switch (c.type) {
      case CmdType::ClipPush: {
        Rect r = c.rect;
        if (!clip.stack.empty()) {
          r = r.intersect(clip.stack.back());
        }
        clip.stack.push_back(r);
        clip.apply();
        break;
      }
      case CmdType::ClipPop:
        if (!clip.stack.empty()) {
          clip.stack.pop_back();
        }
        clip.apply();
        break;
      case CmdType::Rect: {
        GPUVertFormat *format = immVertexFormat();
        const uint pos = GPU_vertformat_attr_add(format, "pos", bgpu::VertAttrType::SFLOAT_32_32);
        immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
        immUniformColor4ub(c.color.r, c.color.g, c.color.b, c.color.a);
        immRectf(pos, c.rect.x, H - c.rect.y1(), c.rect.x1(), H - c.rect.y);
        immUnbindProgram();
        break;
      }
      case CmdType::Triangle: {
        GPUVertFormat *format = immVertexFormat();
        const uint pos = GPU_vertformat_attr_add(format, "pos", bgpu::VertAttrType::SFLOAT_32_32);
        immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
        immUniformColor4ub(c.color.r, c.color.g, c.color.b, c.color.a);
        immBegin(GPU_PRIM_TRIS, 3);
        for (int i = 0; i < 3; i++) {
          immVertex2f(pos, c.p[i].x, H - c.p[i].y);
        }
        immEnd();
        immUnbindProgram();
        break;
      }
      case CmdType::RoundBox: {
        if (c.color.a == 0 && c.color2.a == 0 && c.outline.a == 0 && c.emboss.a == 0 && c.tria == Tria::None) {
          break;
        }
        WidgetParams p;
        std::memset(&p, 0, sizeof(p));
        const float xmin = c.rect.x, xmax = c.rect.x1();
        const float ymin = H - c.rect.y1(), ymax = H - c.rect.y;
        const bool outline = c.outline.a > 0;
        const float lw = outline ? px : 0.0f;
        p.rect[0] = xmin;
        p.rect[1] = xmax;
        p.rect[2] = ymin;
        p.rect[3] = ymax;
        p.recti[0] = xmin + lw;
        p.recti[1] = xmax - lw;
        p.recti[2] = ymin + lw;
        p.recti[3] = ymax - lw;
        const float minsize = std::min(c.rect.w, c.rect.h);
        float rad = std::min(c.radius, 0.5f * minsize);
        float radi = std::max(0.0f, rad - lw);
        p.rad = rad;
        p.radi = radi;
        p.facxi = (p.recti[1] != p.recti[0]) ? 1.0f / (p.recti[1] - p.recti[0]) : 0.0f;
        p.facyi = (p.recti[3] != p.recti[2]) ? 1.0f / (p.recti[3] - p.recti[2]) : 0.0f;
        p.round_corners[0] = (c.corners & CORNER_BOTTOM_LEFT) ? 1.0f : 0.0f;
        p.round_corners[1] = (c.corners & CORNER_BOTTOM_RIGHT) ? 1.0f : 0.0f;
        p.round_corners[2] = (c.corners & CORNER_TOP_RIGHT) ? 1.0f : 0.0f;
        p.round_corners[3] = (c.corners & CORNER_TOP_LEFT) ? 1.0f : 0.0f;
        set_color(p.color_inner1, c.color);
        set_color(p.color_inner2, c.color2);
        set_color(p.color_outline, outline ? c.outline : Color{0, 0, 0, 0});
        set_color(p.color_emboss, c.emboss);
        set_color(p.color_tria, c.tria_color);
        p.shade_dir = 1.0f;
        p.alpha_discard = 1.0f;
        const float tcx = c.tria_center.x, tcy = H - c.tria_center.y;
        switch (c.tria) {
          case Tria::None:
            p.tria_type = TRIA_NONE;
            break;
          case Tria::ArrowLeft:
            p.tria_type = TRIA_ARROWS;
            p.tria1_center[0] = tcx;
            p.tria1_center[1] = tcy;
            p.tria1_size = -c.tria_size;
            break;
          case Tria::ArrowRight:
            p.tria_type = TRIA_ARROWS;
            p.tria2_center[0] = tcx;
            p.tria2_center[1] = tcy;
            p.tria2_size = -c.tria_size;
            break;
          case Tria::Menu:
            p.tria_type = TRIA_MENU;
            p.tria1_center[0] = tcx;
            p.tria1_center[1] = tcy;
            p.tria1_size = c.tria_size;
            break;
          case Tria::Check:
            p.tria_type = TRIA_CHECK;
            p.tria1_center[0] = tcx;
            p.tria1_center[1] = tcy;
            p.tria1_size = c.tria_size;
            break;
          case Tria::Dash:
            p.tria_type = TRIA_DASH;
            p.tria1_center[0] = tcx;
            p.tria1_center[1] = tcy;
            p.tria1_size = c.tria_size;
            break;
        }
        GPU_batch_program_set_builtin(widget_batch_, GPU_SHADER_2D_WIDGET_BASE);
        GPU_batch_uniform_4fv_array(widget_batch_, "parameters", 12, reinterpret_cast<const float(*)[4]>(&p));
        GPU_batch_uniform_3fv(widget_batch_, "checkerColorAndSize", checker);
        GPU_batch_draw(widget_batch_);
        break;
      }
      case CmdType::Text: {
        const int font = c.font.kind == FontKind::Mono ? mono_ : ui_;
        BLF_size(font, c.font.size_px);
        const unsigned char rgba[4] = {c.color.r, c.color.g, c.color.b, c.color.a};
        BLF_color4ubv(font, rgba);
        BLF_position(font, std::round(c.pos.x), std::round(H - c.pos.y), 0.0f);
        BLF_draw(font, c.text.data(), c.text.size());
        break;
      }
      case CmdType::ColorStrip: {
        const size_t n = c.colors.size();
        if (n == 0) {
          break;
        }
        GPUVertFormat *format = immVertexFormat();
        const uint pos = GPU_vertformat_attr_add(format, "pos", bgpu::VertAttrType::SFLOAT_32_32);
        const uint col = GPU_vertformat_attr_add(format, "color", bgpu::VertAttrType::SFLOAT_32_32_32_32);
        immBindBuiltinProgram(GPU_SHADER_3D_SMOOTH_COLOR);
        const size_t segs = std::max<size_t>(1, n - 1);
        immBegin(GPU_PRIM_TRI_STRIP, uint((segs + 1) * 2));
        for (size_t i = 0; i <= segs; i++) {
          const Color &cc = c.colors[std::min(i, n - 1)];
          const float x = c.rect.x + c.rect.w * float(i) / float(segs);
          immAttr4f(col, cc.r / 255.0f, cc.g / 255.0f, cc.b / 255.0f, cc.a / 255.0f);
          immVertex2f(pos, x, H - c.rect.y1());
          immAttr4f(col, cc.r / 255.0f, cc.g / 255.0f, cc.b / 255.0f, cc.a / 255.0f);
          immVertex2f(pos, x, H - c.rect.y);
        }
        immEnd();
        immUnbindProgram();
        break;
      }
      case CmdType::Image: {
        if (!c.texture) {
          break;
        }
        bgpu::Texture *tex = reinterpret_cast<bgpu::Texture *>(uintptr_t(c.texture));
        GPUVertFormat *format = immVertexFormat();
        const uint pos = GPU_vertformat_attr_add(format, "pos", bgpu::VertAttrType::SFLOAT_32_32);
        const uint uv = GPU_vertformat_attr_add(format, "texCoord", bgpu::VertAttrType::SFLOAT_32_32);
        immBindBuiltinProgram(GPU_SHADER_3D_IMAGE_COLOR);
        immUniformColor4ub(c.color.r, c.color.g, c.color.b, c.color.a);
        immBindTexture("image", tex);
        /* v = 0 is the top row of the image (rows uploaded top-first). */
        const float u0 = c.uv.x, u1 = c.uv.x1(), v0 = c.uv.y, v1 = c.uv.y1();
        immBegin(GPU_PRIM_TRI_FAN, 4);
        immAttr2f(uv, u0, v1);
        immVertex2f(pos, c.rect.x, H - c.rect.y1());
        immAttr2f(uv, u1, v1);
        immVertex2f(pos, c.rect.x1(), H - c.rect.y1());
        immAttr2f(uv, u1, v0);
        immVertex2f(pos, c.rect.x1(), H - c.rect.y);
        immAttr2f(uv, u0, v0);
        immVertex2f(pos, c.rect.x, H - c.rect.y);
        immEnd();
        immUnbindProgram();
        break;
      }
    }
  }
  clip.stack.clear();
  clip.apply(); /* leave the scissor at the viewport, as WP1 regions expect */
  GPU_blend(GPU_BLEND_NONE);
  GPU_matrix_pop();
  GPU_matrix_pop_projection();
}

}  // namespace stk::ui::gpu
