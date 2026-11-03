/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/literature_page.hh"
#include "stk/app/literature_contract.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/literature_state.hh"
#include "stk/bridge/schema.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include <cmath>
#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {
void require(bool condition) { if (!condition) { throw std::invalid_argument("literature.invalid_page"); } }
bool exact(const Json &a, const Json &b) { return io::python_json_dumps(a, true, true) == io::python_json_dumps(b, true, true); }
std::vector<uint8_t> decode_base64(const std::string &value)
{
  require(!value.empty() && value.size() <= 5592408 && value.size() % 4 == 0);
  const auto digit = [](char c) -> int {
    if (c >= 'A' && c <= 'Z') { return c - 'A'; }
    if (c >= 'a' && c <= 'z') { return c - 'a' + 26; }
    if (c >= '0' && c <= '9') { return c - '0' + 52; }
    return c == '+' ? 62 : c == '/' ? 63 : -1;
  };
  std::vector<uint8_t> result; result.reserve(value.size() / 4 * 3);
  for (size_t i = 0; i < value.size(); i += 4) {
    const int a = digit(value[i]), b = digit(value[i + 1]);
    const bool p2 = value[i + 2] == '=', p3 = value[i + 3] == '=';
    const int c = p2 ? 0 : digit(value[i + 2]), d = p3 ? 0 : digit(value[i + 3]);
    require(a >= 0 && b >= 0 && c >= 0 && d >= 0 && (!p2 || p3) &&
        (!(p2 || p3) || i + 4 == value.size()) && (!p2 || (b & 15) == 0) && (!p3 || p2 || (c & 3) == 0));
    result.push_back(uint8_t(a << 2 | b >> 4));
    if (!p2) { result.push_back(uint8_t(b << 4 | c >> 2)); }
    if (!p3) { result.push_back(uint8_t(c << 6 | d)); }
  }
  require(!result.empty() && result.size() <= 4 * 1024 * 1024); return result;
}
// Python evaluates each binary operation separately; volatile prevents FMA
// contraction changing a coordinate or the typed JSON geometry checksum.
double point(const std::array<double, 6> &m, double x, double y, size_t offset)
{
  const volatile double a = m[offset] * x, b = m[offset + 1] * y;
  const volatile double sum = a + b;
  return double(sum) + m[offset + 2];
}
}
void LiteraturePage::clear()
{
  image_.reset(); png_.clear(); highlights_.reset(); citation_ = nullptr; error_.clear();
}
bool LiteraturePage::affine_matches(const Json &page, uint32_t width, uint32_t height, const std::array<double, 6> &m)
{
  try {
    check_analysis_json_bounds(page, 4096);
    require(literature_shape(page, bridge::ProtocolSchema::embedded().resolved("#/$defs/literaturePage")));
    require(width && height && width <= 2048 && height <= 2048);
    for (const double value : m) { require(std::isfinite(value) && std::abs(value) <= 1e9); }
    const auto &box = page.at("page_box");
    const double left = box[0].get<double>(), bottom = box[1].get<double>(), right = box[2].get<double>(), top = box[3].get<double>();
    require(left < right && bottom < top);
    std::array<double, 6> expected{};
    const double sx = width / (right - left), sy = height / (top - bottom);
    switch (io::get_int(page, "rotation", -1)) {
      case 0: expected = {sx, 0, -left * sx, 0, -sy, top * sy}; break;
      case 90: expected = {0, width / (top - bottom), -bottom * width / (top - bottom), height / (right - left), 0, -left * height / (right - left)}; break;
      case 180: expected = {-sx, 0, right * sx, 0, sy, -bottom * sy}; break;
      case 270: expected = {0, -double(width) / (top - bottom), top * width / (top - bottom), -double(height) / (right - left), 0, right * height / (right - left)}; break;
      default: require(false);
    }
    for (const auto &xy : std::array<std::array<double, 2>, 4>{{{left, bottom}, {right, bottom}, {right, top}, {left, top}}}) {
      for (const size_t offset : {0u, 3u}) { require(std::abs(point(m, xy[0], xy[1], offset) - point(expected, xy[0], xy[1], offset)) <= .02); }
    }
    return true;
  }
  catch (const std::exception &) { return false; }
}
bool LiteraturePage::adopt(const Json &resolved, const Json &rendered)
{
  clear();
  try {
    check_analysis_json_bounds(resolved, 8 * 1024 * 1024); check_analysis_json_bounds(rendered, 8 * 1024 * 1024);
    const auto &schema = bridge::ProtocolSchema::embedded();
    require(literature_shape(resolved, schema.resolved("#/$defs/literatureResolvedCitation")));
    require(literature_shape(rendered, schema.resolved("#/$defs/literatureRenderedPage")));
    require(exact(resolved.at("citation"), rendered.at("citation")) && exact(resolved.at("page"), rendered.at("page")) &&
        exact(resolved.at("text_status"), rendered.at("text_status")) && exact(resolved.at("structure_status"), rendered.at("structure_status")));
    const auto &citation = resolved.at("citation"); const auto &inner = citation.at("inner");
    const auto &base = inner.contains("base") ? inner.at("base") : inner;
    const auto &text = resolved.at("text").get_ref<const std::string &>();
    require(core::Sha256::hex(text) == io::get_string(inner, "text_sha256"));
    const int64_t span_start = io::get_int(base, "start", -1) + (inner.contains("base") ? io::get_int(inner, "start", -1) : 0);
    const int64_t span_end = inner.contains("base") ? io::get_int(base, "start", -1) + io::get_int(inner, "end", -1) : io::get_int(base, "end", -1);
    require(span_start >= 0 && span_start < span_end && int64_t(core::utf8::count_code_points(text)) == span_end - span_start);
    require(io::get_string(resolved, "corpus_id") == io::get_string(citation, "corpus_id") &&
        io::get_string(resolved, "database_id") == io::get_string(citation, "database_id"));
    auto evidence = citation; evidence.erase("evidence_sha256");
    require(LiteratureState::checksum(evidence) == io::get_string(citation, "evidence_sha256"));
    require(io::get_string(rendered, "source_sha256") == io::get_string(base, "source_sha256") &&
        io::get_int(base, "page_index", -1) == io::get_int(resolved.at("page"), "page_index", -2));
    require(io::get_string(rendered.at("renderer"), "binary_sha256") == io::get_string(resolved.at("parser"), "binary_sha256") &&
        io::get_string(rendered.at("renderer"), "pypdfium2") == io::get_string(resolved.at("parser"), "pypdfium2"));
    const auto &image = rendered.at("image"); auto png = decode_base64(image.at("data_base64").get_ref<const std::string &>());
    require(int64_t(png.size()) == io::get_int(image, "bytes", -1) && core::Sha256::hex(png) == io::get_string(image, "sha256"));
    const uint32_t width = uint32_t(io::get_int(image, "width", 0)), height = uint32_t(io::get_int(image, "height", 0));
    require(width && height && width <= 2048 && height <= 2048 && uint64_t(width) * height <= 4 * 1024 * 1024);
    io::check_rgba8_filter_zero_png(png, {2048, 2048, 4 * 1024 * 1024});
    std::array<double, 6> m{};
    for (size_t i = 0; i < 6; ++i) { m[i] = rendered.at("pdf_to_pixel")[i].get<double>(); }
    require(affine_matches(rendered.at("page"), width, height, m));
    const auto &highlights = rendered.at("highlights");
    require(LiteratureState::checksum(highlights) == io::get_string(rendered, "geometry_sha256"));
    Json actual = Json::array(); auto quads = std::make_shared<std::vector<Quad>>();
    for (const auto &character : resolved.at("characters")) {
      if (character.at("box").is_null()) { continue; }
      const auto &b = character.at("box"); const double l = b[0].get<double>(), lo = b[1].get<double>(), r = b[2].get<double>(), hi = b[3].get<double>();
      require(l <= r && lo <= hi);
      Quad quad; quad.index = uint32_t(io::get_int(character, "index", 0)); quad.start = uint32_t(io::get_int(character, "text_start", 0)); quad.end = uint32_t(io::get_int(character, "text_end", 0));
      require(quad.start < quad.end && quad.start >= span_start && quad.end <= span_end);
      const std::array<std::array<double, 2>, 4> corners = {{{l, lo}, {r, lo}, {r, hi}, {l, hi}}}; Json points = Json::array();
      for (size_t i = 0; i < 4; ++i) { quad.points[i] = {point(m, corners[i][0], corners[i][1], 0), point(m, corners[i][0], corners[i][1], 3)}; points.push_back(Json::array({quad.points[i][0], quad.points[i][1]})); }
      actual.push_back({{"index", character.at("index")}, {"text_start", character.at("text_start")}, {"text_end", character.at("text_end")}, {"quad", std::move(points)}});
      quads->push_back(quad);
    }
    require(exact(actual, highlights));
    auto decoded = io::decode_png(png, {2048, 2048, 4 * 1024 * 1024});
    require(decoded.width == width && decoded.height == height);
    png_ = std::move(png); image_ = std::move(decoded); citation_ = citation; highlights_ = std::move(quads); return true;
  }
  catch (const std::exception &) { clear(); error_ = "literature.invalid_page"; return false; }
}
}  // namespace stk::app
