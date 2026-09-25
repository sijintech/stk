/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/payload.hh"

#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/core/thread_pool.hh"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <set>

namespace stk::io {

namespace {

std::string with_path(const std::string &message, const std::string &path)
{
  return path.empty() ? message : path + ": " + message;
}

}  // namespace

PayloadError::PayloadError(const std::string &message, std::string path, std::string code)
    : std::runtime_error(with_path(message, path)), message_(message), path_(std::move(path)), code_(std::move(code))
{
}

std::optional<ComponentType> parse_component_type(std::string_view name)
{
  static constexpr std::pair<std::string_view, ComponentType> names[] = {
      {"i8", ComponentType::I8},
      {"u8", ComponentType::U8},
      {"i16", ComponentType::I16},
      {"u16", ComponentType::U16},
      {"i32", ComponentType::I32},
      {"u32", ComponentType::U32},
      {"f32", ComponentType::F32},
      {"f64", ComponentType::F64},
  };
  for (const auto &[text, type] : names) {
    if (text == name) {
      return type;
    }
  }
  return std::nullopt;
}

std::string_view component_type_name(ComponentType type)
{
  switch (type) {
    case ComponentType::I8:
      return "i8";
    case ComponentType::U8:
      return "u8";
    case ComponentType::I16:
      return "i16";
    case ComponentType::U16:
      return "u16";
    case ComponentType::I32:
      return "i32";
    case ComponentType::U32:
      return "u32";
    case ComponentType::F32:
      return "f32";
    case ComponentType::F64:
      return "f64";
  }
  return "?";
}

size_t component_size(ComponentType type)
{
  switch (type) {
    case ComponentType::I8:
    case ComponentType::U8:
      return 1;
    case ComponentType::I16:
    case ComponentType::U16:
      return 2;
    case ComponentType::I32:
    case ComponentType::U32:
    case ComponentType::F32:
      return 4;
    case ComponentType::F64:
      return 8;
  }
  return 1;
}

bool component_is_float(ComponentType type)
{
  return type == ComponentType::F32 || type == ComponentType::F64;
}

bool component_is_signed(ComponentType type)
{
  return type == ComponentType::I8 || type == ComponentType::I16 || type == ComponentType::I32 ||
         component_is_float(type);
}

bool is_payload_id(std::string_view id)
{
  if (id.empty() || id.size() > 128 || id == "__proto__" || id == "constructor" || id == "prototype") {
    return false;
  }
  const auto word = [](char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_';
  };
  if (!word(id[0])) {
    return false;
  }
  for (char c : id.substr(1)) {
    if (!word(c) && c != '.' && c != ':' && c != '-') {
      return false;
    }
  }
  return true;
}

bool is_label_format(std::string_view f)
{
  size_t i = 0;
  const auto peek = [&]() -> char { return i < f.size() ? f[i] : '\0'; };
  const auto digit = [](char c) { return c >= '0' && c <= '9'; };
  if (peek() == '+' || peek() == '-' || peek() == ' ') {
    i++;
  }
  if (peek() == '#') {
    i++;
  }
  if (peek() == '0') {
    i++;
  }
  if (peek() >= '1' && peek() <= '9') {
    i++;
    if (digit(peek())) {
      i++;
    }
  }
  if (peek() == ',') {
    i++;
  }
  if (peek() == 'd') {
    return i + 1 == f.size();
  }
  if (peek() == '.') {
    i++;
    if (!digit(peek())) {
      return false;
    }
    i++;
    if (digit(peek())) {
      i++;
    }
  }
  if (i < f.size() && std::string_view("eEfFgG%").find(f[i]) != std::string_view::npos) {
    i++;
  }
  return i == f.size();
}

/* ------------------------------------------------------------------------------------------ */
/* Payload accessors */

bool Payload::has_accessor(std::string_view id) const
{
  return accessor_index_.count(std::string(id)) != 0;
}

const PayloadAccessor &Payload::accessor(std::string_view id) const
{
  const auto it = accessor_index_.find(std::string(id));
  if (it == accessor_index_.end()) {
    throw PayloadError("no accessor '" + std::string(id) + "'");
  }
  return accessors[it->second];
}

std::span<const uint8_t> Payload::accessor_bytes(const PayloadAccessor &a) const
{
  const core::SharedBytes &bytes = buffers[a.buffer].bytes;
  return bytes.span().subspan(size_t(a.byte_offset), size_t(a.byte_size()));
}

std::span<const uint8_t> Payload::accessor_bytes(std::string_view id) const
{
  return accessor_bytes(accessor(id));
}

namespace {

template<typename T> T load(const uint8_t *p)
{
  T value;
  std::memcpy(&value, p, sizeof(T));
  return value;
}

double element_at(const uint8_t *base, ComponentType type, uint64_t index)
{
  switch (type) {
    case ComponentType::I8:
      return load<int8_t>(base + index);
    case ComponentType::U8:
      return load<uint8_t>(base + index);
    case ComponentType::I16:
      return load<int16_t>(base + 2 * index);
    case ComponentType::U16:
      return load<uint16_t>(base + 2 * index);
    case ComponentType::I32:
      return load<int32_t>(base + 4 * index);
    case ComponentType::U32:
      return load<uint32_t>(base + 4 * index);
    case ComponentType::F32:
      return load<float>(base + 4 * index);
    case ComponentType::F64:
      return load<double>(base + 8 * index);
  }
  return 0.0;
}

double normalized_max(ComponentType type)
{
  switch (type) {
    case ComponentType::I8:
      return 127.0;
    case ComponentType::U8:
      return 255.0;
    case ComponentType::I16:
      return 32767.0;
    case ComponentType::U16:
      return 65535.0;
    case ComponentType::I32:
      return 2147483647.0;
    case ComponentType::U32:
      return 4294967295.0;
    default:
      return 1.0;
  }
}

}  // namespace

double Payload::element(const PayloadAccessor &a, uint64_t index) const
{
  return element_at(accessor_bytes(a).data(), a.type, index);
}

std::vector<float> Payload::floats(std::string_view id) const
{
  const PayloadAccessor &a = accessor(id);
  const uint8_t *base = accessor_bytes(a).data();
  std::vector<float> out(size_t(a.value_count()));
  if (out.empty()) {
    return out; /* count 0: the view may be a null pointer */
  }
  if (a.type == ComponentType::F32) {
    std::memcpy(out.data(), base, out.size() * sizeof(float));
    return out;
  }
  const bool normalized = a.normalized && !component_is_float(a.type);
  const double scale = normalized ? 1.0 / normalized_max(a.type) : 1.0;
  const bool clamp = normalized && component_is_signed(a.type);
  for (size_t i = 0; i < out.size(); i++) {
    const double v = element_at(base, a.type, i) * scale;
    out[i] = float(clamp ? std::max(-1.0, v) : v);
  }
  return out;
}

std::vector<double> Payload::doubles(std::string_view id) const
{
  const PayloadAccessor &a = accessor(id);
  const uint8_t *base = accessor_bytes(a).data();
  std::vector<double> out(size_t(a.value_count()));
  for (size_t i = 0; i < out.size(); i++) {
    out[i] = element_at(base, a.type, i);
  }
  return out;
}

const Json *Payload::colormap(std::string_view id) const
{
  const auto it = colormap_index_.find(std::string(id));
  return it == colormap_index_.end() ? nullptr : &manifest["colormaps"][it->second];
}

const Json *Payload::layer(std::string_view id) const
{
  const auto it = layer_index_.find(std::string(id));
  return it == layer_index_.end() ? nullptr : &manifest["layers"][it->second];
}

const Json &Payload::layers() const
{
  return manifest["layers"];
}

std::array<double, 3> Payload::layer_origin(const Json &layer) const
{
  const auto it = layer.find("origin");
  if (it != layer.end() && it->is_array() && it->size() == 3) {
    return {(*it)[0].get<double>(), (*it)[1].get<double>(), (*it)[2].get<double>()};
  }
  return render_origin;
}

bool Payload::skipped(std::string_view layer_id) const
{
  return std::any_of(warnings.begin(), warnings.end(), [&](const PayloadWarning &w) { return w.layer == layer_id; });
}

uint64_t Payload::total_bytes() const
{
  uint64_t total = 0;
  for (const PayloadBuffer &buffer : buffers) {
    total += buffer.bytes.size();
  }
  return total;
}

/* ------------------------------------------------------------------------------------------ */
/* Blobs and hashing */

namespace {

struct Blob {
  core::SharedBytes bytes;
  bool verified = false; /* hashed against its key already (unpack_stkp, blob cache) */
};
using BlobMap = std::map<std::string, Blob, std::less<>>;

const Json *get(const Json &object, std::string_view key)
{
  const auto it = object.find(key);
  return it == object.end() ? nullptr : &*it;
}

std::string repr(const Json *value)
{
  if (!value) {
    return "None";
  }
  if (value->is_string()) {
    return "'" + value->get<std::string>() + "'";
  }
  return python_json_dumps(*value);
}

/** sha256 of each blob not yet verified, computed in parallel when a pool is given. */
std::map<std::string, std::string, std::less<>> hash_blobs(const BlobMap &blobs, core::ThreadPool *pool)
{
  std::vector<std::pair<const std::string *, const core::SharedBytes *>> todo;
  for (const auto &[sha, blob] : blobs) {
    if (!blob.verified) {
      todo.emplace_back(&sha, &blob.bytes);
    }
  }
  std::vector<std::string> digests(todo.size());
  const auto work = [&](size_t begin, size_t end) {
    for (size_t i = begin; i < end; i++) {
      digests[i] = core::Sha256::hex(todo[i].second->span());
    }
  };
  if (pool && todo.size() > 1) {
    pool->parallel_for(todo.size(), 1, work);
  }
  else {
    work(0, todo.size());
  }
  std::map<std::string, std::string, std::less<>> result;
  for (size_t i = 0; i < todo.size(); i++) {
    result.emplace(*todo[i].first, std::move(digests[i]));
  }
  return result;
}

/* _check_blob: sha256 format, byteLength and hash. */
void check_blob(const Json &buffer,
                const core::SharedBytes &bytes,
                const std::string &path,
                const std::string *computed /* nullptr: hash now; empty string: verified */)
{
  const Json *digest = get(buffer, "sha256");
  if (!digest || !digest->is_string() || !core::is_sha256_hex(digest->get_ref<const std::string &>())) {
    throw PayloadError("sha256 must be 64 lower-case hex digits", path + "/sha256");
  }
  const Json *length = get(buffer, "byteLength");
  if (!length || !is_safe_integer(*length) || length->get<double>() != double(bytes.size())) {
    throw PayloadError("byteLength " + repr(length) + " differs from the data size " + std::to_string(bytes.size()),
                       path + "/byteLength");
  }
  if (computed && computed->empty()) {
    return;
  }
  const std::string actual = computed ? *computed : core::Sha256::hex(bytes.span());
  if (actual != digest->get_ref<const std::string &>()) {
    throw PayloadError("buffer bytes do not hash to its sha256", path + "/sha256");
  }
}

/* _buffer_entries: the manifest's buffers list (objects only). */
const Json &buffer_entries(const Json &manifest)
{
  static const Json empty = Json::array();
  if (!manifest.is_object()) {
    throw PayloadError("manifest must be a JSON object");
  }
  const Json *buffers = get(manifest, "buffers");
  if (!buffers) {
    return empty;
  }
  if (!buffers->is_array() || !std::all_of(buffers->begin(), buffers->end(), [](const Json &b) {
        return b.is_object();
      }))
  {
    throw PayloadError("buffers must be a list of objects", "/buffers");
  }
  return *buffers;
}

}  // namespace

/* ------------------------------------------------------------------------------------------ */
/* Validator: suan/render/payload.py _Validator, check for check (same order, same JSON-pointer paths). */

namespace {

/* A string member, or absent/null (Python `value is None or isinstance(value, str)`). */
bool optional_string(const Json *value)
{
  return !value || value->is_null() || value->is_string();
}

bool present(const Json *value)
{
  return value && !value->is_null();
}

bool finite_pair(const Json &value)
{
  return value.is_array() && value.size() == 2 && is_finite_number(value[0]) && is_finite_number(value[1]);
}

}  // namespace

std::vector<std::string> overlay_problems(const Json &layer)
{
  std::vector<std::string> problems;
  const auto check = [&](bool ok, const char *key, const char *text) {
    if (!ok) {
      problems.push_back(std::string(key) + " " + text);
    }
  };
  const auto optional = [&](const char *key, auto ok) {
    const Json *value = get(layer, key);
    return !present(value) || ok(*value);
  };
  const auto size = [](const Json &v) {
    return (is_finite_number(v) && v.get<double>() > 0) ||
           (finite_pair(v) && v[0].get<double>() > 0 && v[1].get<double>() > 0);
  };
  check(optional_string(get(layer, "title")), "title", "must be a string");
  check(optional_string(get(layer, "anchor")), "anchor", "must be a string");
  check(optional_string(get(layer, "source_layer")), "source_layer", "must be a string");
  check(optional("offset_px", finite_pair), "offset_px", "must be 2 finite numbers");
  check(optional("size_px", size), "size_px", "must be a positive number or 2 positive numbers");
  const Json *kind = get(layer, "kind");
  const std::string k = kind && kind->is_string() ? kind->get<std::string>() : std::string();
  if (k == "scalar_bar") {
    check(optional_string(get(layer, "unit")), "unit", "must be a string");
    check(optional_string(get(layer, "orientation")), "orientation", "must be a string");
  }
  else if (k == "legend") {
    check(optional("values",
                   [](const Json &v) {
                     return v.is_array() && std::all_of(v.begin(), v.end(), [](const Json &x) { return is_safe_integer(x); });
                   }),
          "values",
          "must be a list of integers");
    check(optional("columns", [](const Json &v) { return is_safe_integer(v); }), "columns", "must be an integer");
  }
  else if (k == "orientation_legend") {
    check(optional("lightness_range", finite_pair), "lightness_range", "must be 2 finite numbers");
  }
  else if (k == "text") {
    check(optional("font_size_px", [](const Json &v) { return is_finite_number(v) && v.get<double>() > 0; }),
          "font_size_px",
          "must be a positive number");
    check(optional("color",
                   [](const Json &v) {
                     return v.is_array() && (v.size() == 3 || v.size() == 4) &&
                            std::all_of(v.begin(), v.end(), [](const Json &x) { return is_finite_number(x); });
                   }),
          "color",
          "must be 3 or 4 finite numbers");
  }
  else if (k == "axes_triad") {
    check(optional("labels",
                   [](const Json &v) {
                     return v.is_array() && v.size() == 3 &&
                            std::all_of(v.begin(), v.end(), [](const Json &x) { return x.is_string(); });
                   }),
          "labels",
          "must be 3 strings");
  }
  return problems;
}

class PayloadValidator {
 public:
  PayloadValidator(Payload &payload, const BlobMap &blobs, core::ThreadPool *pool)
      : p_(payload), m_(payload.manifest), blobs_(blobs), pool_(pool)
  {
  }

  void run();

 private:
  [[noreturn]] void fail(const std::string &message, const std::string &path)
  {
    throw PayloadError(message, path);
  }
  void warn(const Json &layer, const std::string &path, const std::string &message)
  {
    p_.warnings.push_back({path, get_string(layer, "id"), message});
  }

  const Json &list(const Json *value, const std::string &path);
  const Json &object(const Json *value, const std::string &path, const char *what);
  void unique_id(const Json &item, const std::set<std::string, std::less<>> &seen, const std::string &path);
  void vec3(const Json *value, const std::string &path);
  void interval(const Json *value, const std::string &path);
  void rgb(const Json *value, const std::string &path);
  const PayloadAccessor &expect(const Json *accessor_id,
                                std::initializer_list<ComponentType> types,
                                std::optional<uint32_t> components,
                                std::optional<double> count,
                                const std::string &path);
  uint64_t positions(const Json &owner, const std::string &path);
  const Json *attributes(const Json &layer,
                         const std::string &path,
                         std::optional<double> points,
                         std::optional<double> cells);
  const Json &appearance(const Json &layer, const std::string &path);
  void color(const Json *spec, const Json *attributes, const std::string &path);
  uint64_t indices(const Json *accessor_id, uint64_t n_points, uint64_t multiple, const std::string &path);
  bool has_attribute(const Json *attributes, const Json *name);
  bool categorical_colormap(const Json *id);

  void layer_triangles(const Json &layer, const std::string &path);
  void layer_slice_image(const Json &layer, const std::string &path);
  void layer_lines(const Json &layer, const std::string &path);
  void layer_points(const Json &layer, const std::string &path);
  void layer_instances(const Json &layer, const std::string &path);
  void layer_volume(const Json &layer, const std::string &path);
  void layer_overlay(const Json &layer, const std::string &path);

  template<typename Map> auto lookup(const Map &map, const Json *key) -> decltype(&map.begin()->second)
  {
    if (!key || !key->is_string()) {
      return nullptr;
    }
    const auto it = map.find(key->get_ref<const std::string &>());
    return it == map.end() ? nullptr : &it->second;
  }

  Payload &p_;
  const Json &m_;
  const BlobMap &blobs_;
  core::ThreadPool *pool_;
  std::map<std::string, size_t, std::less<>> buffers_;          /* id -> Payload::buffers index */
  std::map<std::string, size_t, std::less<>> accessors_;        /* id -> Payload::accessors index */
  std::map<std::string, const Json *, std::less<>> colormaps_;  /* id -> manifest entry */
};

const Json &PayloadValidator::list(const Json *value, const std::string &path)
{
  if (!value || !value->is_array()) {
    fail("must be a list", path);
  }
  for (size_t i = 0; i < value->size(); i++) {
    if (!(*value)[i].is_object()) {
      fail("must be an object", path + "/" + std::to_string(i));
    }
  }
  return *value;
}

const Json &PayloadValidator::object(const Json *value, const std::string &path, const char *what)
{
  if (!value || !value->is_object()) {
    fail(std::string(what) + " must be an object", path);
  }
  return *value;
}

void PayloadValidator::unique_id(const Json &item, const std::set<std::string, std::less<>> &seen, const std::string &path)
{
  const Json *id = get(item, "id");
  if (!id || !id->is_string() || !is_payload_id(id->get_ref<const std::string &>())) {
    fail("invalid id " + repr(id), path + "/id");
  }
  if (seen.count(id->get_ref<const std::string &>())) {
    fail("duplicate id " + repr(id), path + "/id");
  }
}

void PayloadValidator::vec3(const Json *value, const std::string &path)
{
  if (!value || !value->is_array() || value->size() != 3 ||
      !std::all_of(value->begin(), value->end(), [](const Json &v) { return is_finite_number(v); }))
  {
    fail("must be 3 finite numbers", path);
  }
}

void PayloadValidator::interval(const Json *value, const std::string &path)
{
  if (!value || !finite_pair(*value)) {
    fail("must be [lo, hi] (two finite numbers)", path);
  }
}

void PayloadValidator::rgb(const Json *value, const std::string &path)
{
  if (!value || !value->is_array() || (value->size() != 3 && value->size() != 4) ||
      !std::all_of(value->begin(), value->end(), [](const Json &v) {
        return is_finite_number(v) && v.get<double>() >= 0.0 && v.get<double>() <= 1.0;
      }))
  {
    fail("colour must be 3 or 4 numbers in [0, 1]", path);
  }
}

const PayloadAccessor &PayloadValidator::expect(const Json *accessor_id,
                                                std::initializer_list<ComponentType> types,
                                                std::optional<uint32_t> components,
                                                std::optional<double> count,
                                                const std::string &path)
{
  const size_t *index = lookup(accessors_, accessor_id);
  if (!index) {
    fail("unknown accessor " + repr(accessor_id), path);
  }
  const PayloadAccessor &a = p_.accessors[*index];
  if (types.size() && std::find(types.begin(), types.end(), a.type) == types.end()) {
    std::string names;
    for (ComponentType t : types) {
      names += (names.empty() ? "" : "/") + std::string(component_type_name(t));
    }
    fail("accessor '" + a.id + "' must have type " + names + ", not " + std::string(component_type_name(a.type)), path);
  }
  if (components && a.components != *components) {
    fail("accessor '" + a.id + "' must have " + std::to_string(*components) + " components", path);
  }
  if (count && double(a.count) != *count) {
    fail("accessor '" + a.id + "' has " + std::to_string(a.count) + " elements; expected " +
             python_float_repr(*count),
         path);
  }
  return a;
}

uint64_t PayloadValidator::positions(const Json &owner, const std::string &path)
{
  const PayloadAccessor &a = expect(get(owner, "positions"), {ComponentType::F32}, 3, std::nullopt, path + "/positions");
  const std::span<const uint8_t> bytes = p_.accessor_bytes(a);
  for (uint64_t i = 0; i < a.value_count(); i++) {
    if (!std::isfinite(load<float>(bytes.data() + 4 * i))) {
      fail("positions must be finite", path + "/positions");
    }
  }
  return a.count;
}

const Json *PayloadValidator::attributes(const Json &layer,
                                         const std::string &path,
                                         std::optional<double> points,
                                         std::optional<double> cells)
{
  static const Json empty = Json::object();
  const Json *attrs = get(layer, "attributes");
  if (!present(attrs)) {
    return &empty;
  }
  object(attrs, path + "/attributes", "attributes");
  for (auto it = attrs->begin(); it != attrs->end(); ++it) {
    const std::string apath = path + "/attributes/" + it.key();
    const Json &attribute = object(&it.value(), apath, "an attribute");
    const Json *association = get(attribute, "association");
    std::optional<double> count;
    bool valid = false;
    if (!present(association) || (association->is_string() && *association == "point")) {
      valid = points.has_value();
      count = points;
    }
    else if (association->is_string() && *association == "cell") {
      valid = cells.has_value();
      count = cells;
    }
    if (!valid) {
      fail("association " + (present(association) ? repr(association) : std::string("'point'")) +
               " is not valid here",
           apath + "/association");
    }
    expect(get(attribute, "accessor"), {}, std::nullopt, *count, apath + "/accessor");
    const Json *palette = get(attribute, "palette");
    if (present(palette) && !categorical_colormap(palette)) {
      fail("palette " + repr(palette) + " is not a categorical colormap", apath + "/palette");
    }
  }
  return attrs;
}

bool PayloadValidator::categorical_colormap(const Json *id)
{
  const Json *const *colormap = lookup(colormaps_, id);
  if (!colormap) {
    return false;
  }
  const Json *flag = get(**colormap, "categorical");
  return flag && flag->is_boolean() && flag->get<bool>();
}

bool PayloadValidator::has_attribute(const Json *attributes, const Json *name)
{
  return name && name->is_string() && attributes->contains(name->get_ref<const std::string &>());
}

const Json &PayloadValidator::appearance(const Json &layer, const std::string &path)
{
  static const Json empty = Json::object();
  const Json *value = get(layer, "appearance");
  return present(value) ? object(value, path + "/appearance", "appearance") : empty;
}

void PayloadValidator::color(const Json *spec, const Json *attributes, const std::string &path)
{
  if (!present(spec)) {
    return;
  }
  object(spec, path, "a colour spec");
  const Json *by_json = get(*spec, "by");
  std::string by = "solid"; /* spec §5: the default mode */
  if (present(by_json)) {
    const bool known = by_json->is_string() &&
                       (*by_json == "solid" || *by_json == "attribute" || *by_json == "direction");
    if (!known) {
      fail("unknown colour mode " + repr(by_json), path + "/by");
    }
    by = by_json->get<std::string>();
  }
  const Json *attribute = get(*spec, "attribute");
  if ((by == "attribute" || (by == "direction" && present(attribute))) && !has_attribute(attributes, attribute)) {
    fail("unknown attribute " + repr(attribute), path + "/attribute");
  }
  const Json *colormap = get(*spec, "colormap");
  if (present(colormap)) {
    const bool orientation = colormap->is_string() && *colormap == "stk:orientation-hsl";
    if (by == "direction" && !orientation) {
      fail("direction colouring uses 'stk:orientation-hsl', not " + repr(colormap), path + "/colormap");
    }
    if (!orientation && !lookup(colormaps_, colormap)) {
      fail("unknown colormap " + repr(colormap), path + "/colormap");
    }
  }
  if (const Json *range = get(*spec, "range"); present(range)) {
    interval(range, path + "/range");
  }
}

uint64_t PayloadValidator::indices(const Json *accessor_id, uint64_t n_points, uint64_t multiple, const std::string &path)
{
  const PayloadAccessor &a = expect(accessor_id, {ComponentType::U32, ComponentType::U16}, 1, std::nullopt, path);
  if (a.count % multiple) {
    fail("index count must be a multiple of " + std::to_string(multiple), path);
  }
  const std::span<const uint8_t> bytes = p_.accessor_bytes(a);
  uint64_t max = 0;
  if (a.type == ComponentType::U32) {
    for (uint64_t i = 0; i < a.count; i++) {
      max = std::max<uint64_t>(max, load<uint32_t>(bytes.data() + 4 * i));
    }
  }
  else {
    for (uint64_t i = 0; i < a.count; i++) {
      max = std::max<uint64_t>(max, load<uint16_t>(bytes.data() + 2 * i));
    }
  }
  if (a.count && max >= n_points) {
    fail("index refers to a missing position", path);
  }
  return a.count / multiple;
}

void PayloadValidator::layer_triangles(const Json &layer, const std::string &path)
{
  const uint64_t n = positions(layer, path);
  const uint64_t n_tri = indices(get(layer, "indices"), n, 3, path + "/indices");
  if (const Json *normals = get(layer, "normals"); present(normals)) {
    expect(normals, {ComponentType::F32}, 3, double(n), path + "/normals");
  }
  const Json *attrs = attributes(layer, path, double(n), double(n_tri));
  color(get(appearance(layer, path), "color"), attrs, path + "/appearance/color");
  static const Json no_lods = Json::array();
  const Json *lods = get(layer, "lods");
  const Json &lod_list = list(present(lods) ? lods : &no_lods, path + "/lods");
  for (size_t j = 0; j < lod_list.size(); j++) {
    const Json &lod = lod_list[j];
    const std::string lpath = path + "/lods/" + std::to_string(j);
    const uint64_t count = positions(lod, lpath);
    const uint64_t cells = indices(get(lod, "indices"), count, 3, lpath + "/indices");
    if (const Json *normals = get(lod, "normals"); present(normals)) {
      expect(normals, {ComponentType::F32}, 3, double(count), lpath + "/normals");
    }
    attributes(lod, lpath, double(count), double(cells));
  }
}

void PayloadValidator::layer_slice_image(const Json &layer, const std::string &path)
{
  const Json &plane = layer["plane"];
  for (const char *key : {"origin", "u", "v"}) {
    vec3(plane.is_object() ? get(plane, key) : nullptr, path + "/plane/" + key);
  }
  const Json &size = layer["size"];
  if (!size.is_array() || size.size() != 2 || !std::all_of(size.begin(), size.end(), [](const Json &v) {
        return is_safe_integer(v) && v.get<double>() >= 1;
      }))
  {
    fail("size must be [w, h] positive integers", path + "/size");
  }
  const double samples = size[0].get<double>() * size[1].get<double>();
  const Json *attrs = attributes(layer, path, samples, std::nullopt);
  if (attrs->empty()) {
    fail("slice_image layers need at least one attribute", path + "/attributes");
  }
  color(get(appearance(layer, path), "color"), attrs, path + "/appearance/color");
}

void PayloadValidator::layer_lines(const Json &layer, const std::string &path)
{
  const uint64_t n = positions(layer, path);
  const Json &mode = layer["mode"];
  uint64_t segments = 0;
  if (mode.is_string() && mode == "segments") {
    segments = indices(get(layer, "indices"), n, 2, path + "/indices");
  }
  else if (mode.is_string() && mode == "polylines") {
    const uint64_t count = indices(get(layer, "indices"), n, 1, path + "/indices");
    const Json *offsets_id = get(layer, "offsets");
    if (!present(offsets_id)) {
      fail("polylines need offsets", path);
    }
    const PayloadAccessor &offsets = expect(offsets_id, {ComponentType::U32}, 1, std::nullopt, path + "/offsets");
    const std::span<const uint8_t> bytes = p_.accessor_bytes(offsets);
    const auto at = [&](uint64_t i) { return uint64_t(load<uint32_t>(bytes.data() + 4 * i)); };
    bool ok = offsets.count >= 1 && at(0) == 0 && at(offsets.count - 1) == count;
    for (uint64_t i = 1; ok && i < offsets.count; i++) {
      if (at(i) < at(i - 1)) {
        ok = false;
      }
      else if (at(i) - at(i - 1) > 1) {
        segments += at(i) - at(i - 1) - 1; /* cell attributes are per segment */
      }
    }
    if (!ok) {
      fail("offsets must rise from 0 to the index count", path + "/offsets");
    }
  }
  else {
    fail("unknown lines mode " + repr(&mode), path + "/mode");
  }
  const Json *attrs = attributes(layer, path, double(n), double(segments));
  color(get(appearance(layer, path), "color"), attrs, path + "/appearance/color");
}

void PayloadValidator::layer_points(const Json &layer, const std::string &path)
{
  const uint64_t n = positions(layer, path);
  if (const Json *radii = get(layer, "radii"); present(radii)) {
    expect(radii, {ComponentType::F32}, 1, double(n), path + "/radii");
  }
  const Json *attrs = attributes(layer, path, double(n), std::nullopt);
  color(get(appearance(layer, path), "color"), attrs, path + "/appearance/color");
}

void PayloadValidator::layer_instances(const Json &layer, const std::string &path)
{
  const uint64_t n = positions(layer, path);
  expect(get(layer, "directions"), {ComponentType::F32}, 3, double(n), path + "/directions");
  if (const Json *scales = get(layer, "scales"); present(scales)) {
    expect(scales, {ComponentType::F32}, 1, double(n), path + "/scales");
  }
  const Json &glyph = object(&layer["glyph"], path + "/glyph", "glyph");
  const Json *shape = get(glyph, "shape");
  static const char *shapes[] = {"arrow", "cone", "sphere", "line", "cube"};
  if (!shape || !shape->is_string() ||
      std::none_of(std::begin(shapes), std::end(shapes), [&](const char *s) { return *shape == s; }))
  {
    fail("unknown glyph shape " + repr(shape), path + "/glyph/shape");
  }
  const Json *attrs = attributes(layer, path, double(n), std::nullopt);
  const Json &app = appearance(layer, path);
  color(get(app, "color"), attrs, path + "/appearance/color");
  const Json *scale = get(app, "scale");
  if (present(scale)) {
    object(scale, path + "/appearance/scale", "scale");
    const Json *by = get(*scale, "by");
    const Json *attribute = get(*scale, "attribute");
    if (by && by->is_string() && *by == "attribute" && !has_attribute(attrs, attribute)) {
      fail("unknown scale attribute " + repr(attribute), path + "/appearance/scale");
    }
    const Json *factor = get(*scale, "factor");
    if (present(factor) && !(is_finite_number(*factor) && factor->get<double>() > 0)) {
      fail("scale factor must be a finite number > 0", path + "/appearance/scale/factor");
    }
  }
}

namespace {

bool positive_dimensions(const Json *dims)
{
  return dims && dims->is_array() && dims->size() == 3 && std::all_of(dims->begin(), dims->end(), [](const Json &v) {
           return is_safe_integer(v) && v.get<double>() >= 1;
         });
}

double product(const Json &dims)
{
  double result = 1.0;
  for (const Json &v : dims) {
    result *= v.get<double>();
  }
  return result;
}

}  // namespace

void PayloadValidator::layer_volume(const Json &layer, const std::string &path)
{
  const Json &grid = layer["grid"];
  const Json *dims = grid.is_object() ? get(grid, "dimensions") : nullptr;
  if (!positive_dimensions(dims)) {
    fail("dimensions must be 3 positive integers", path + "/grid/dimensions");
  }
  vec3(get(grid, "origin"), path + "/grid/origin");
  vec3(get(grid, "spacing"), path + "/grid/spacing");
  const Json &spacing = grid["spacing"];
  if (std::min({spacing[0].get<double>(), spacing[1].get<double>(), spacing[2].get<double>()}) <= 0) {
    fail("spacing must be positive", path + "/grid/spacing");
  }
  if (const Json *direction = get(grid, "direction"); present(direction)) {
    if (!direction->is_array() || direction->size() != 9 ||
        !std::all_of(direction->begin(), direction->end(), [](const Json &v) { return is_finite_number(v); }))
    {
      fail("direction must be 9 finite numbers (row-major 3x3)", path + "/grid/direction");
    }
  }
  expect(get(layer, "data"), {ComponentType::U8, ComponentType::U16, ComponentType::F32}, 1, product(*dims),
         path + "/data");
  interval(get(layer, "value_range"), path + "/value_range");
  for (const char *key : {"value_scale", "value_offset"}) {
    if (const Json *value = get(layer, key); present(value) && !is_finite_number(*value)) {
      fail(std::string(key) + " must be a finite number", path + "/" + key);
    }
  }
  const std::string tpath = path + "/transfer_function";
  const Json &tf = object(&layer["transfer_function"], tpath, "transfer_function");
  if (!lookup(colormaps_, get(tf, "colormap"))) { /* continuous LUT, or a categorical palette (values +- 0.499) */
    fail("unknown colormap " + repr(get(tf, "colormap")), tpath + "/colormap");
  }
  interval(get(tf, "range"), tpath + "/range");
  const Json *opacity = get(tf, "opacity");
  if (!opacity || !opacity->is_array() || opacity->size() < 2) {
    fail("opacity must be a list of at least two [value, alpha] points", tpath + "/opacity");
  }
  for (size_t j = 0; j < opacity->size(); j++) {
    const Json &point = (*opacity)[j];
    if (!finite_pair(point) || point[1].get<double>() < 0 || point[1].get<double>() > 1) {
      fail("opacity points are [finite value, alpha in [0, 1]]", tpath + "/opacity/" + std::to_string(j));
    }
  }
  static const Json no_lods = Json::array();
  const Json *lods = get(layer, "lods");
  const Json &lod_list = list(present(lods) ? lods : &no_lods, path + "/lods");
  for (size_t j = 0; j < lod_list.size(); j++) {
    const std::string lpath = path + "/lods/" + std::to_string(j);
    const Json *lod_dims = get(lod_list[j], "dimensions");
    if (!positive_dimensions(lod_dims)) {
      fail("dimensions must be 3 positive integers", lpath + "/dimensions");
    }
    expect(get(lod_list[j], "data"), {ComponentType::U8, ComponentType::U16, ComponentType::F32}, 1,
           product(*lod_dims), lpath + "/data");
  }
}

void PayloadValidator::layer_overlay(const Json &layer, const std::string &path)
{
  const Json &kind = layer["kind"];
  if (!kind.is_string()) {
    fail("kind must be a string", path + "/kind");
  }
  static const char *kinds[] = {"scalar_bar", "legend", "orientation_legend", "text", "axes_triad"};
  if (std::none_of(std::begin(kinds), std::end(kinds), [&](const char *k) { return kind == k; })) {
    warn(layer, path, "unknown overlay kind " + repr(&kind) + " (skipped)");
    return; /* clients skip overlays of unknown kind (spec §1) */
  }
  const Json *colormap_id = get(layer, "colormap");
  const Json *colormap = nullptr;
  if (kind == "scalar_bar" || kind == "legend") {
    const Json *const *found = lookup(colormaps_, colormap_id);
    if (!found) {
      fail("unknown colormap " + repr(colormap_id), path + "/colormap");
    }
    colormap = *found;
  }
  if (kind == "scalar_bar") {
    if (categorical_colormap(colormap_id)) {
      fail("a scalar bar needs a continuous colormap", path + "/colormap");
    }
    interval(get(layer, "range"), path + "/range");
    const Json *count = get(layer, "label_count");
    if (present(count) && (!is_safe_integer(*count) || count->get<double>() < 2 || count->get<double>() > 20)) {
      fail("label_count must be an integer from 2 to 20", path + "/label_count");
    }
    const Json *format = get(layer, "format");
    if (present(format) && (!format->is_string() || !is_label_format(format->get_ref<const std::string &>()))) {
      fail("unsupported label format " + repr(format) + " (e.g. '.3g', '.2f', '.1e', '+.0%', 'd')", path + "/format");
    }
  }
  if (kind == "legend" && !categorical_colormap(colormap_id)) {
    fail("a legend needs a categorical colormap", path + "/colormap");
  }
  (void)colormap;
  if (kind == "text") {
    const Json *text = get(layer, "text");
    if (!text || !text->is_string()) {
      fail("text overlays need 'text'", path + "/text");
    }
  }
  if (const std::vector<std::string> problems = overlay_problems(layer); !problems.empty()) {
    std::string joined;
    for (const std::string &problem : problems) {
      joined += (joined.empty() ? "" : "; ") + problem;
    }
    warn(layer, path, "overlay skipped: " + joined);
  }
}

void PayloadValidator::run()
{
  if (!m_.is_object()) {
    throw PayloadError("manifest must be a JSON object");
  }
  const Json *schema = get(m_, "schema");
  if (!schema || *schema != kPayloadSchema) {
    fail("schema must be 'stk.payload/2', got " + repr(schema), "/schema");
  }
  for (const char *key : {"render_origin", "length_unit", "buffers", "accessors", "layers"}) {
    if (!m_.contains(key)) {
      fail(std::string("missing required key '") + key + "'", "");
    }
  }
  vec3(get(m_, "render_origin"), "/render_origin");
  const Json &unit = m_["length_unit"];
  if (!unit.is_string() || unit.get_ref<const std::string &>().empty()) {
    fail("length_unit must be a non-empty string", "/length_unit");
  }
  for (int i = 0; i < 3; i++) {
    p_.render_origin[i] = m_["render_origin"][i].get<double>();
  }
  p_.length_unit = unit.get<std::string>();
  p_.warnings.clear();

  /* Buffers (hashes computed up front, in parallel when a pool is given; checked in order). */
  const auto digests = hash_blobs(blobs_, pool_);
  const Json &buffers = list(get(m_, "buffers"), "/buffers");
  std::set<std::string, std::less<>> seen;
  for (size_t i = 0; i < buffers.size(); i++) {
    const std::string path = "/buffers/" + std::to_string(i);
    const Json &buffer = buffers[i];
    unique_id(buffer, seen, path);
    const Json *digest = get(buffer, "sha256");
    const Json *uri = get(buffer, "uri");
    const bool uri_ok = digest && digest->is_string() && uri && uri->is_string() &&
                        uri->get_ref<const std::string &>() == "sha256:" + digest->get_ref<const std::string &>();
    if (!uri_ok) {
      fail("in-memory buffers are referenced as 'sha256:<hex>'", path + "/uri");
    }
    const Json *encoding = get(buffer, "encoding");
    if (present(encoding) && !(encoding->is_string() && *encoding == "raw")) {
      fail("encoding must be 'raw'", path + "/encoding");
    }
    const std::string &sha = digest->get_ref<const std::string &>();
    const auto blob = blobs_.find(sha);
    if (blob == blobs_.end()) {
      fail("missing bytes for sha256 " + sha, path);
    }
    static const std::string verified;
    const auto computed = digests.find(sha);
    check_blob(buffer, blob->second.bytes, path, computed == digests.end() ? &verified : &computed->second);
    const std::string &id = buffer["id"].get_ref<const std::string &>();
    seen.insert(id);
    buffers_.emplace(id, p_.buffers.size());
    p_.buffers.push_back({id, sha, blob->second.bytes.size(), blob->second.bytes});
  }

  /* Accessors. */
  seen.clear();
  const Json &accessors = list(get(m_, "accessors"), "/accessors");
  for (size_t i = 0; i < accessors.size(); i++) {
    const std::string path = "/accessors/" + std::to_string(i);
    const Json &accessor = accessors[i];
    unique_id(accessor, seen, path);
    const Json *buffer_id = get(accessor, "buffer");
    const size_t *buffer = lookup(buffers_, buffer_id);
    if (!buffer) {
      fail("unknown buffer " + repr(buffer_id), path + "/buffer");
    }
    const Json *type_name = get(accessor, "type");
    const auto type = type_name && type_name->is_string() ? parse_component_type(type_name->get_ref<const std::string &>())
                                                          : std::nullopt;
    if (!type) {
      fail("unknown type " + repr(type_name), path + "/type");
    }
    uint64_t values[3];
    const char *keys[3] = {"count", "components", "byteOffset"};
    const double lows[3] = {0, 1, 0};
    for (int k = 0; k < 3; k++) {
      const Json *v = get(accessor, keys[k]);
      if (!v || !is_safe_integer(*v) || v->get<double>() < lows[k]) {
        fail(std::string(keys[k]) + " must be an integer >= " + std::to_string(int(lows[k])), path + "/" + keys[k]);
      }
      values[k] = uint64_t(v->get<double>());
    }
    const uint64_t count = values[0], components = values[1], offset = values[2];
    if (components > 16) {
      fail("components must be <= 16", path + "/components");
    }
    if (offset % 8) {
      fail("byteOffset must be a multiple of 8", path + "/byteOffset");
    }
    const uint64_t length = p_.buffers[*buffer].byte_length;
    const uint64_t size = component_size(*type);
    /* offset + count * components * size > byteLength, without overflow. */
    const bool past = offset > length || (count != 0 && (length - offset) / (components * size) < count);
    if (past) {
      fail("accessor runs past the end of its buffer", path);
    }
    const Json *normalized = get(accessor, "normalized");
    if (present(normalized) && !normalized->is_boolean()) {
      fail("normalized must be a boolean", path + "/normalized");
    }
    const bool is_normalized = present(normalized) && normalized->get<bool>();
    if (is_normalized && component_is_float(*type)) {
      fail("normalized applies to integer types only", path + "/normalized");
    }
    const std::string &id = accessor["id"].get_ref<const std::string &>();
    seen.insert(id);
    accessors_.emplace(id, p_.accessors.size());
    p_.accessor_index_.emplace(id, p_.accessors.size());
    p_.accessors.push_back({id, *buffer, offset, count, *type, uint32_t(components), is_normalized});
  }

  /* Colormaps. */
  seen.clear();
  static const Json no_colormaps = Json::array();
  const Json *colormaps_json = get(m_, "colormaps");
  const Json &colormaps = list(present(colormaps_json) ? colormaps_json : &no_colormaps, "/colormaps");
  for (size_t i = 0; i < colormaps.size(); i++) {
    const std::string path = "/colormaps/" + std::to_string(i);
    const Json &colormap = colormaps[i];
    unique_id(colormap, seen, path);
    const Json *categorical = get(colormap, "categorical");
    if (present(categorical) && !categorical->is_boolean()) {
      fail("categorical must be a boolean", path + "/categorical");
    }
    std::vector<const char *> colour_keys = {"nan_color", "below_color", "above_color"};
    if (present(categorical) && categorical->get<bool>()) {
      const Json &entries = list(get(colormap, "entries"), path + "/entries");
      for (size_t j = 0; j < entries.size(); j++) {
        const std::string epath = path + "/entries/" + std::to_string(j);
        const Json *value = get(entries[j], "value");
        if (!value || !is_safe_integer(*value)) {
          fail("category value must be an integer", epath + "/value");
        }
        const Json *name = get(entries[j], "name");
        if (!name || !name->is_string()) {
          fail("category name must be a string", epath + "/name");
        }
        rgb(get(entries[j], "color"), epath + "/color");
      }
      /* duplicates are reported after every entry was checked, as in Python */
      std::set<int64_t> unique;
      bool duplicate = false;
      for (const Json &entry : entries) {
        duplicate |= !unique.insert(int64_t(entry["value"].get<double>())).second;
      }
      if (duplicate) {
        fail("category values must be unique", path + "/entries");
      }
      colour_keys = {"unknown_color"};
    }
    else {
      expect(get(colormap, "lut"), {ComponentType::U8}, 4, 256.0, path + "/lut");
      const Json *size = get(colormap, "size");
      if (!size || !is_safe_integer(*size) || size->get<double>() != 256.0) {
        fail("size must be 256", path + "/size");
      }
    }
    for (const char *key : colour_keys) {
      if (const Json *colour = get(colormap, key); present(colour)) {
        rgb(colour, path + "/" + key);
      }
    }
    const std::string &id = colormap["id"].get_ref<const std::string &>();
    seen.insert(id);
    colormaps_.emplace(id, &colormap);
    p_.colormap_index_.emplace(id, i);
  }

  /* Layers. */
  seen.clear();
  const Json &layers = list(get(m_, "layers"), "/layers");
  static const std::map<std::string, std::vector<const char *>, std::less<>> required = {
      {"triangles", {"positions", "indices"}},
      {"slice_image", {"plane", "size", "attributes"}},
      {"lines", {"positions", "mode", "indices"}},
      {"points", {"positions"}},
      {"instances", {"positions", "directions", "glyph"}},
      {"volume", {"grid", "data", "value_range", "transfer_function"}},
      {"overlay", {"kind"}},
  };
  for (size_t i = 0; i < layers.size(); i++) {
    const std::string path = "/layers/" + std::to_string(i);
    const Json &layer = layers[i];
    unique_id(layer, seen, path);
    const std::string &id = layer["id"].get_ref<const std::string &>();
    seen.insert(id);
    p_.layer_index_.emplace(id, i);
    if (!optional_string(get(layer, "name"))) {
      fail("name must be a string", path + "/name");
    }
    const Json *kind = get(layer, "type");
    if (!kind || !kind->is_string()) {
      fail("type must be a string", path + "/type");
    }
    const auto *keys = lookup(required, kind);
    if (!keys) {
      warn(layer, path, "unknown layer type " + repr(kind) + " (skipped)");
      continue; /* clients skip layers of unknown type (spec §1) */
    }
    const std::string &type = kind->get_ref<const std::string &>();
    for (const char *key : *keys) {
      if (!layer.contains(key)) {
        fail(type + " layer needs '" + key + "'", path);
      }
    }
    if (const Json *origin = get(layer, "origin"); present(origin)) {
      vec3(origin, path + "/origin");
    }
    if (type == "triangles") {
      layer_triangles(layer, path);
    }
    else if (type == "slice_image") {
      layer_slice_image(layer, path);
    }
    else if (type == "lines") {
      layer_lines(layer, path);
    }
    else if (type == "points") {
      layer_points(layer, path);
    }
    else if (type == "instances") {
      layer_instances(layer, path);
    }
    else if (type == "volume") {
      layer_volume(layer, path);
    }
    else {
      layer_overlay(layer, path);
    }
  }
  if (const Json *bounds = get(m_, "bounds"); present(bounds)) {
    if (!bounds->is_array() || bounds->size() != 2) {
      fail("bounds must be [[min], [max]]", "/bounds");
    }
    vec3(&(*bounds)[0], "/bounds/0");
    vec3(&(*bounds)[1], "/bounds/1");
  }
  if (const Json *view = get(m_, "view"); present(view)) {
    const Json *view_schema = view->is_object() ? get(*view, "schema") : nullptr;
    if (!view_schema || *view_schema != "stk.view/1") {
      fail("view must be an stk.view/1 document", "/view");
    }
  }
}

/* ------------------------------------------------------------------------------------------ */
/* Entry points */

namespace {

Payload build(Json manifest, const BlobMap &blobs, const DecodeOptions &options)
{
  Payload payload;
  payload.manifest = std::move(manifest);
  PayloadValidator(payload, blobs, options.pool).run();
  return payload;
}

constexpr uint8_t kMagic[4] = {'S', 'T', 'K', 'P'};

template<typename T> T read_le(const uint8_t *p)
{
  T value;
  std::memcpy(&value, p, sizeof(T));
  return value;
}

std::pair<Json, BlobMap> unpack(const core::SharedBytes &data, core::ThreadPool *pool)
{
  const uint8_t *bytes = data.data();
  const size_t size = data.size();
  if (size < 16) {
    throw PayloadError("Not an .stkp file (too short)");
  }
  if (std::memcmp(bytes, kMagic, 4) != 0) {
    throw PayloadError("Not an .stkp file (bad magic)");
  }
  const uint32_t version = read_le<uint32_t>(bytes + 4);
  if (version != 2) {
    throw PayloadError(".stkp version " + std::to_string(version) + " is not supported (expected 2)");
  }
  const uint64_t total = read_le<uint64_t>(bytes + 8);
  if (total != size) {
    throw PayloadError(".stkp length field " + std::to_string(total) + " differs from the file size " +
                       std::to_string(size));
  }
  struct Chunk {
    char kind[4];
    core::SharedBytes data;
  };
  std::vector<Chunk> chunks;
  uint64_t offset = 16;
  while (offset < size) {
    if (offset + 16 > size) {
      throw PayloadError(".stkp chunk header is truncated");
    }
    const uint64_t length = read_le<uint64_t>(bytes + offset);
    Chunk chunk;
    std::memcpy(chunk.kind, bytes + offset + 8, 4);
    const uint32_t reserved = read_le<uint32_t>(bytes + offset + 12);
    offset += 16;
    if (reserved != 0) {
      throw PayloadError(".stkp chunk reserved field must be 0");
    }
    if (length > size - offset) {
      throw PayloadError(".stkp chunk data is truncated");
    }
    chunk.data = data.slice(size_t(offset), size_t(length));
    chunks.push_back(std::move(chunk));
    offset += length + ((8 - length % 8) % 8);
  }
  if (offset != size) {
    throw PayloadError(".stkp padding runs past the end of the file");
  }
  if (chunks.empty() || std::memcmp(chunks[0].kind, "JSON", 4) != 0) {
    throw PayloadError(".stkp chunk 0 must be the JSON manifest");
  }
  for (size_t i = 1; i < chunks.size(); i++) {
    if (std::memcmp(chunks[i].kind, "BIN ", 4) != 0) {
      throw PayloadError(".stkp chunks after the manifest must be 'BIN '");
    }
  }
  const std::string_view text(reinterpret_cast<const char *>(chunks[0].data.data()), chunks[0].data.size());
  if (!core::utf8::is_valid(text)) {
    throw PayloadError(".stkp manifest is not valid JSON: not UTF-8");
  }
  if (text.starts_with("\xEF\xBB\xBF")) {
    throw PayloadError(".stkp manifest is not valid JSON: a byte-order mark"); /* as Python's json.loads */
  }
  Json manifest;
  try {
    manifest = parse_json(text);
  }
  catch (const JsonError &error) {
    throw PayloadError(std::string(".stkp manifest is not valid JSON: ") + error.what());
  }
  Json &buffers = const_cast<Json &>(buffer_entries(manifest));
  /* Resolve chunk references first, then hash every referenced chunk (in parallel) and check in order. */
  std::vector<const Chunk *> refs(buffers.size(), nullptr);
  for (size_t i = 0; i < buffers.size(); i++) {
    const Json *uri = get(buffers[i], "uri");
    const std::string path = "/buffers/" + std::to_string(i) + "/uri";
    bool ok = uri && uri->is_string();
    size_t k = 0;
    if (ok) {
      const std::string &text_uri = uri->get_ref<const std::string &>();
      ok = text_uri.size() >= 2 && text_uri[0] == '#' && text_uri[1] >= '1' && text_uri[1] <= '9' &&
           text_uri.size() <= 21;
      for (size_t c = 1; ok && c < text_uri.size(); c++) {
        ok = text_uri[c] >= '0' && text_uri[c] <= '9';
        k = k * 10 + size_t(text_uri[c] - '0');
      }
      ok = ok && k < chunks.size();
    }
    if (!ok) {
      throw PayloadError("Buffer URI " + repr(uri) + " does not name a chunk of this file", path);
    }
    refs[i] = &chunks[k];
  }
  std::vector<std::string> digests(buffers.size());
  const auto work = [&](size_t begin, size_t end) {
    for (size_t i = begin; i < end; i++) {
      digests[i] = core::Sha256::hex(refs[i]->data.span());
    }
  };
  if (pool && buffers.size() > 1) {
    pool->parallel_for(buffers.size(), 1, work);
  }
  else {
    work(0, buffers.size());
  }
  BlobMap blobs;
  for (size_t i = 0; i < buffers.size(); i++) {
    Json &buffer = buffers[i];
    check_blob(buffer, refs[i]->data, "/buffers/" + std::to_string(i), &digests[i]);
    const std::string digest = buffer["sha256"].get<std::string>();
    buffer["uri"] = "sha256:" + digest;
    blobs[digest] = Blob{refs[i]->data, true};
  }
  return {std::move(manifest), std::move(blobs)};
}

}  // namespace

std::pair<Json, std::map<std::string, core::SharedBytes>> unpack_stkp(const core::SharedBytes &data,
                                                                     const DecodeOptions &options)
{
  auto [manifest, blobs] = unpack(data, options.pool);
  std::map<std::string, core::SharedBytes> out;
  for (auto &[sha, blob] : blobs) {
    out.emplace(sha, blob.bytes);
  }
  return {std::move(manifest), std::move(out)};
}

Payload decode_stkp(const core::SharedBytes &data, const DecodeOptions &options)
{
  auto [manifest, blobs] = unpack(data, options.pool);
  return build(std::move(manifest), blobs, options);
}

Payload read_stkp(const std::filesystem::path &path, const DecodeOptions &options)
{
  core::SharedBytes data;
  try {
    data = core::SharedBytes::from_file(path, options.use_mmap);
  }
  catch (const core::FileError &error) {
    throw PayloadError(error.what(), "", "io_error");
  }
  return decode_stkp(data, options);
}

Payload read_directory(const std::filesystem::path &path, const DecodeOptions &options)
{
  std::error_code ec;
  const std::filesystem::path manifest_path = std::filesystem::is_directory(path, ec) ? path / "manifest.json" : path;
  Json manifest;
  try {
    const std::string text = core::read_text_file(manifest_path);
    if (!core::utf8::is_valid(text)) {
      throw PayloadError(core::path_to_utf8(manifest_path.filename()) + " is not valid JSON: not UTF-8");
    }
    if (std::string_view(text).starts_with("\xEF\xBB\xBF")) {
      throw PayloadError(core::path_to_utf8(manifest_path.filename()) + " is not valid JSON: a byte-order mark");
    }
    manifest = parse_json(text);
  }
  catch (const core::FileError &error) {
    throw PayloadError(error.what(), "", "io_error");
  }
  catch (const JsonError &error) {
    throw PayloadError(core::path_to_utf8(manifest_path.filename()) + " is not valid JSON: " + error.what());
  }
  const Json &buffers = buffer_entries(manifest);
  BlobMap blobs;
  for (size_t i = 0; i < buffers.size(); i++) {
    const Json *digest = get(buffers[i], "sha256");
    const Json *uri = get(buffers[i], "uri");
    const std::string path_i = "/buffers/" + std::to_string(i);
    if (!digest || !digest->is_string() || !core::is_sha256_hex(digest->get_ref<const std::string &>()) || !uri ||
        !uri->is_string() || uri->get_ref<const std::string &>() != "sha256:" + digest->get_ref<const std::string &>())
    {
      throw PayloadError("Directory payloads reference buffers as 'sha256:<hex>'", path_i);
    }
    const std::string &sha = digest->get_ref<const std::string &>();
    const std::filesystem::path file = manifest_path.parent_path() / (sha + ".bin");
    if (!std::filesystem::is_regular_file(file, ec)) {
      throw PayloadError("Missing buffer file " + sha + ".bin", path_i);
    }
    if (!blobs.count(sha)) {
      try {
        blobs[sha] = Blob{core::SharedBytes::from_file(file, options.use_mmap), false};
      }
      catch (const core::FileError &error) {
        throw PayloadError(error.what(), path_i, "io_error");
      }
    }
  }
  return build(std::move(manifest), blobs, options);
}

Payload decode_manifest(Json manifest, const BlobProvider &provider, const DecodeOptions &options)
{
  const Json &buffers = buffer_entries(manifest);
  BlobMap blobs;
  for (const Json &buffer : buffers) {
    const Json *digest = get(buffer, "sha256");
    if (!digest || !digest->is_string() || !core::is_sha256_hex(digest->get_ref<const std::string &>())) {
      continue; /* reported by validation */
    }
    const std::string &sha = digest->get_ref<const std::string &>();
    if (blobs.count(sha)) {
      continue;
    }
    if (std::optional<core::SharedBytes> bytes = provider(sha)) {
      blobs[sha] = Blob{std::move(*bytes), false};
    }
  }
  return build(std::move(manifest), blobs, options);
}

Payload decode(Json manifest, std::map<std::string, core::SharedBytes> in, const DecodeOptions &options)
{
  BlobMap blobs;
  for (auto &[sha, bytes] : in) {
    blobs.emplace(sha, Blob{std::move(bytes), false});
  }
  return build(std::move(manifest), blobs, options);
}

void validate_payload(const Payload &payload)
{
  BlobMap blobs;
  for (const PayloadBuffer &buffer : payload.buffers) {
    blobs.emplace(buffer.sha256, Blob{buffer.bytes, false});
  }
  Payload copy;
  copy.manifest = payload.manifest;
  PayloadValidator(copy, blobs, nullptr).run();
}

std::vector<uint8_t> pack_stkp(const Json &manifest, const std::map<std::string, core::SharedBytes> &blobs)
{
  Json packed = manifest;
  std::vector<const core::SharedBytes *> chunks;
  size_t index = 1;
  for (Json &buffer : packed.at("buffers")) {
    buffer["uri"] = "#" + std::to_string(index++);
    chunks.push_back(&blobs.at(buffer.at("sha256").get<std::string>()));
  }
  const std::string text = python_json_dumps(packed, false, true);
  std::vector<uint8_t> body;
  const auto chunk = [&](const char *kind, const uint8_t *data, size_t length, uint8_t pad) {
    uint8_t header[16] = {};
    const uint64_t len = length;
    std::memcpy(header, &len, 8);
    std::memcpy(header + 8, kind, 4);
    body.insert(body.end(), header, header + 16);
    body.insert(body.end(), data, data + length);
    body.insert(body.end(), (8 - length % 8) % 8, pad);
  };
  chunk("JSON", reinterpret_cast<const uint8_t *>(text.data()), text.size(), ' ');
  for (const core::SharedBytes *bytes : chunks) {
    chunk("BIN ", bytes->data(), bytes->size(), 0);
  }
  std::vector<uint8_t> out(16);
  std::memcpy(out.data(), kMagic, 4);
  const uint32_t version = 2;
  const uint64_t total = 16 + body.size();
  std::memcpy(out.data() + 4, &version, 4);
  std::memcpy(out.data() + 8, &total, 8);
  out.insert(out.end(), body.begin(), body.end());
  return out;
}

}  // namespace stk::io
