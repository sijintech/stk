/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/golden.hh"

#include <cmath>
#include <sstream>

#include "stk/ui/utf8.hh"

namespace stk::ui {

using ojson = nlohmann::ordered_json;

static double r2(float v)
{
  return std::round(double(v) * 100.0) / 100.0;
}

static ojson rect_json(const Rect &r)
{
  return ojson::array({r2(r.x), r2(r.y), r2(r.w), r2(r.h)});
}

static const char *tria_name(Tria t)
{
  switch (t) {
    case Tria::None: return "none";
    case Tria::ArrowLeft: return "arrow_left";
    case Tria::ArrowRight: return "arrow_right";
    case Tria::Menu: return "menu";
    case Tria::Check: return "check";
    case Tria::Dash: return "dash";
  }
  return "?";
}

ojson draw_cmd_to_json(const DrawCmd &c)
{
  ojson j;
  switch (c.type) {
    case CmdType::RoundBox:
      j["op"] = "box";
      j["r"] = rect_json(c.rect);
      j["rad"] = r2(c.radius);
      j["corners"] = int(c.corners);
      j["c"] = c.color.to_hex();
      if (!(c.color2 == c.color)) {
        j["c2"] = c.color2.to_hex();
      }
      if (c.outline.a) {
        j["o"] = c.outline.to_hex();
      }
      if (c.emboss.a) {
        j["e"] = c.emboss.to_hex();
      }
      if (c.tria != Tria::None) {
        j["tria"] = tria_name(c.tria);
        j["tc"] = ojson::array({r2(c.tria_center.x), r2(c.tria_center.y)});
        j["ts"] = r2(c.tria_size);
        j["tcol"] = c.tria_color.to_hex();
      }
      break;
    case CmdType::Rect:
      j["op"] = "rect";
      j["r"] = rect_json(c.rect);
      j["c"] = c.color.to_hex();
      break;
    case CmdType::Triangle:
      j["op"] = "tri";
      j["p"] = ojson::array({r2(c.p[0].x), r2(c.p[0].y), r2(c.p[1].x), r2(c.p[1].y), r2(c.p[2].x), r2(c.p[2].y)});
      j["c"] = c.color.to_hex();
      break;
    case CmdType::Text:
      j["op"] = "text";
      j["t"] = c.text;
      j["p"] = ojson::array({r2(c.pos.x), r2(c.pos.y)});
      j["f"] = c.font.kind == FontKind::Mono ? "mono" : "regular";
      j["s"] = r2(c.font.size_px);
      j["c"] = c.color.to_hex();
      break;
    case CmdType::ColorStrip: {
      j["op"] = "strip";
      j["r"] = rect_json(c.rect);
      j["n"] = c.colors.size();
      uint64_t h = utf8::FNV_OFFSET;
      for (const Color &col : c.colors) {
        h = utf8::hash_combine(h, (uint64_t(col.r) << 24) | (uint64_t(col.g) << 16) | (uint64_t(col.b) << 8) | col.a);
      }
      std::ostringstream ss;
      ss << std::hex << h;
      j["hash"] = ss.str();
      break;
    }
    case CmdType::Image:
      j["op"] = "image";
      j["r"] = rect_json(c.rect);
      j["tex"] = c.texture;
      j["uv"] = rect_json(c.uv);
      break;
    case CmdType::ClipPush:
      j["op"] = "clip";
      j["r"] = rect_json(c.rect);
      break;
    case CmdType::ClipPop:
      j["op"] = "unclip";
      break;
  }
  return j;
}

static const char *block_kind(Block::Kind k)
{
  switch (k) {
    case Block::Kind::Region: return "region";
    case Block::Kind::Modal: return "modal";
    case Block::Kind::Popup: return "popup";
    case Block::Kind::Tooltip: return "tooltip";
    case Block::Kind::Toast: return "toast";
  }
  return "?";
}

std::string dump_frame(const Context &ctx)
{
  std::ostringstream out;
  const Style &st = ctx.style();
  ojson head;
  head["window"] = ojson::array({r2(ctx.window_size().x), r2(ctx.window_size().y)});
  head["scale"] = r2(st.scale);
  head["unit"] = r2(st.unit);
  head["font_px"] = r2(st.font.size_px);
  out << "{\n\"frame\": " << head.dump() << ",\n\"blocks\": [\n";
  bool first_block = true;
  for (const auto &b : ctx.blocks()) {
    ojson bj;
    bj["name"] = b->name();
    bj["kind"] = block_kind(b->kind());
    bj["rect"] = rect_json(b->rect());
    bj["frame"] = rect_json(b->frame());
    bj["content_h"] = r2(b->content_height());
    const std::string bs = bj.dump();
    out << (first_block ? "" : ",\n") << bs.substr(0, bs.size() - 1) << ", \"widgets\": [\n";
    first_block = false;
    bool first = true;
    for (const Widget &w : b->widgets()) {
      ojson wj;
      wj["key"] = w.key;
      wj["type"] = widget_type_name(w.type);
      wj["rect"] = rect_json(w.rect);
      if (!w.enabled) {
        wj["disabled"] = true;
      }
      if (w.corners != CORNER_ALL) {
        wj["corners"] = int(w.corners);
      }
      out << (first ? "  " : ",\n  ") << wj.dump();
      first = false;
    }
    out << "\n]}";
  }
  out << "\n],\n\"draw\": [\n";
  bool first = true;
  for (const DrawCmd &c : ctx.draw_list().cmds) {
    out << (first ? "  " : ",\n  ") << draw_cmd_to_json(c).dump();
    first = false;
  }
  out << "\n]\n}\n";
  return out.str();
}

}  // namespace stk::ui
