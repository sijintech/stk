/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "payload_fuzz.hh"

#include "stk/core/mmap.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/io/payload.hh"
#include "stk/viewer/colormap.hh"
#include "stk/viewer/glyph.hh"
#include "stk/viewer/scene.hh"
#include "stk/viewer/volume.hh"

#include <algorithm>
#include <cstring>
#include <filesystem>
#include <stdexcept>

namespace stk::fuzz {

using io::Json;

namespace {

void exercise(const io::Payload &p)
{
  for (const io::PayloadAccessor &a : p.accessors) {
    const std::vector<double> values = p.doubles(a.id);
    const std::vector<float> floats = p.floats(a.id);
    if (values.size() != a.value_count() || floats.size() != a.value_count()) {
      throw std::logic_error("accessor size mismatch");
    }
  }
  (void)viewer::payload_bounds(p);
  for (const Json &layer : p.layers()) {
    const std::string type = io::get_string(layer, "type");
    const Json appearance = layer.contains("appearance") && layer["appearance"].is_object() ? layer["appearance"]
                                                                                            : Json::object();
    const Json color = appearance.value("color", Json());
    if (type == "triangles" || type == "points" || type == "instances") {
      const size_t count = p.accessor(layer["positions"].get<std::string>()).count;
      std::vector<float> vectors;
      if (type == "instances") {
        vectors = p.floats(layer["directions"].get<std::string>());
        const auto scales = viewer::instance_scales(vectors, {}, viewer::GlyphScale::from_json(appearance.value("scale", Json())));
        (void)scales;
      }
      (void)viewer::layer_colors(p, layer, color, count, "point", vectors);
    }
    else if (type == "volume") {
      const viewer::VolumeTransfer tf = viewer::volume_transfer(p, layer);
      (void)viewer::transfer_lut(tf, 0, 255, 64);
    }
    else if (type == "overlay" && io::get_string(layer, "kind") == "legend") {
      const auto cm = viewer::resolve_colormap(p, layer["colormap"].get<std::string>());
      if (cm && cm->categorical) {
        (void)viewer::legend_items(*cm->categorical, layer.value("values", Json()));
      }
    }
  }
}

template<typename T> T pick(std::mt19937_64 &rng, T lo, T hi)
{
  return std::uniform_int_distribution<T>(lo, hi)(rng);
}

/* The chunk list of well-framed .stkp bytes (empty when the framing is broken). */
struct Chunk {
  char kind[4];
  std::vector<uint8_t> data;
};

bool split(const std::vector<uint8_t> &bytes, std::vector<Chunk> &chunks)
{
  if (bytes.size() < 16 || std::memcmp(bytes.data(), "STKP", 4) != 0) {
    return false;
  }
  size_t offset = 16;
  while (offset + 16 <= bytes.size()) {
    uint64_t length;
    std::memcpy(&length, bytes.data() + offset, 8);
    Chunk c;
    std::memcpy(c.kind, bytes.data() + offset + 8, 4);
    offset += 16;
    if (length > bytes.size() - offset) {
      return false;
    }
    c.data.assign(bytes.begin() + std::ptrdiff_t(offset), bytes.begin() + std::ptrdiff_t(offset + length));
    chunks.push_back(std::move(c));
    offset += length + (8 - length % 8) % 8;
  }
  return !chunks.empty();
}

std::vector<uint8_t> join(const std::vector<Chunk> &chunks)
{
  std::vector<uint8_t> body;
  for (const Chunk &c : chunks) {
    uint8_t header[16] = {};
    const uint64_t length = c.data.size();
    std::memcpy(header, &length, 8);
    std::memcpy(header + 8, c.kind, 4);
    body.insert(body.end(), header, header + 16);
    body.insert(body.end(), c.data.begin(), c.data.end());
    body.insert(body.end(), (8 - c.data.size() % 8) % 8, std::memcmp(c.kind, "JSON", 4) == 0 ? ' ' : 0);
  }
  std::vector<uint8_t> out(16);
  std::memcpy(out.data(), "STKP", 4);
  const uint32_t version = 2;
  const uint64_t total = 16 + body.size();
  std::memcpy(out.data() + 4, &version, 4);
  std::memcpy(out.data() + 8, &total, 8);
  out.insert(out.end(), body.begin(), body.end());
  return out;
}

const Json kReplacements = io::parse_json(R"([null, true, false, 0, -1, 1, 7, 2.5, -3.75, 1e300, 256, 65536,
  1099511627776, 18446744073709551615, -9223372036854775808, "", "x", "#1", "#999999999999999999999", "u8", "f32", "i16",
  "point", "cell", "arrow", "segments", "polylines", "direction", "attribute", [], {}, [0, 0, 0], [1, 2],
  [0.0, 1.0], [[0, 0], [1, 1]], {"a": 1}, {"by": "attribute", "attribute": "nope"}, {"schema": "stk.view/1"},
  "stk:orientation-hsl", "pal0", "cm0", [1e308, -1e308, 0], [4294967295, 0, 1]])");

void collect(Json &value, std::vector<Json *> &out)
{
  out.push_back(&value);
  if (value.is_object()) {
    for (auto it = value.begin(); it != value.end(); ++it) {
      collect(it.value(), out);
    }
  }
  else if (value.is_array()) {
    for (Json &item : value) {
      collect(item, out);
    }
  }
}

void mutate_json(Json &manifest, std::mt19937_64 &rng)
{
  std::vector<Json *> nodes;
  collect(manifest, nodes);
  Json *target = nodes[pick<size_t>(rng, 0, nodes.size() - 1)];
  const int choice = pick(rng, 0, 9);
  if (choice == 0 && target->is_object() && !target->empty()) {
    auto it = target->begin();
    std::advance(it, pick<size_t>(rng, 0, target->size() - 1));
    target->erase(it.key());
  }
  else if (choice == 1 && target->is_array() && !target->empty()) {
    target->erase(pick<size_t>(rng, 0, target->size() - 1));
  }
  else if (choice == 2 && target->is_array() && !target->empty()) {
    target->push_back((*target)[pick<size_t>(rng, 0, target->size() - 1)]);
  }
  else if (choice == 3 && target->is_number()) {
    const double deltas[] = {1, -1, 8, -8, 0.5, 1e9};
    *target = target->get<double>() + deltas[pick(rng, 0, 5)];
    if (pick(rng, 0, 1)) {
      *target = int64_t(std::clamp(target->get<double>(), -9e18, 9e18));
    }
  }
  else if (choice == 4) {
    *target = *nodes[pick<size_t>(rng, 0, nodes.size() - 1)]; /* copy another subtree */
  }
  else {
    *target = kReplacements[pick<size_t>(rng, 0, kReplacements.size() - 1)];
  }
}

}  // namespace

void run_one(const uint8_t *data, size_t size, Stats &stats)
{
  stats.runs++;
  try {
    const io::Payload p = io::decode_stkp(core::SharedBytes::copy_of({data, size}));
    exercise(p);
    stats.accepted++;
  }
  catch (const io::PayloadError &) {
    stats.rejected++;
  }
  catch (const std::exception &error) {
    throw std::logic_error(std::string("unexpected exception: ") + error.what());
  }
}

std::vector<uint8_t> mutate(const std::vector<uint8_t> &input, const std::vector<std::vector<uint8_t>> &corpus,
                            std::mt19937_64 &rng)
{
  std::vector<uint8_t> out = input;
  const int strategy = pick(rng, 0, 9);
  std::vector<Chunk> chunks;
  if (strategy <= 3 && split(out, chunks)) {
    /* Structure-aware: mutate the manifest JSON and re-pack. */
    try {
      Json manifest = io::parse_json(std::string_view(reinterpret_cast<const char *>(chunks[0].data.data()),
                                                      chunks[0].data.size()));
      for (int k = pick(rng, 1, 3); k > 0; k--) {
        mutate_json(manifest, rng);
      }
      const std::string text = manifest.dump();
      chunks[0].data.assign(text.begin(), text.end());
      return join(chunks);
    }
    catch (const std::exception &) {
      return out;
    }
  }
  if (strategy <= 5 && split(out, chunks) && chunks.size() > 1) {
    /* Edit a blob and fix its sha256 so the data-level checks (finite positions, index ranges) run. */
    try {
      Json manifest = io::parse_json(std::string_view(reinterpret_cast<const char *>(chunks[0].data.data()),
                                                      chunks[0].data.size()));
      const size_t k = pick<size_t>(rng, 1, chunks.size() - 1);
      std::vector<uint8_t> &blob = chunks[k].data;
      if (!blob.empty()) {
        static const uint32_t specials[] = {0x7FC00000u /* NaN */, 0x7F800000u /* inf */, 0xFFFFFFFFu, 0x80000000u, 0};
        for (int edits = pick(rng, 1, 4); edits > 0; edits--) {
          const size_t at = pick<size_t>(rng, 0, blob.size() - 1) & ~size_t(3);
          const uint32_t v = pick(rng, 0, 1) ? specials[pick(rng, 0, 4)] : uint32_t(rng());
          std::memcpy(blob.data() + at, &v, std::min<size_t>(4, blob.size() - at));
        }
      }
      if (manifest.contains("buffers") && manifest["buffers"].is_array()) {
        for (Json &buffer : manifest["buffers"]) {
          if (io::get_string(buffer, "uri") == "#" + std::to_string(k)) {
            const std::string sha = core::Sha256::hex(blob);
            buffer["sha256"] = sha;
            buffer["byteLength"] = blob.size();
          }
        }
      }
      const std::string text = manifest.dump();
      chunks[0].data.assign(text.begin(), text.end());
      return join(chunks);
    }
    catch (const std::exception &) {
      return out;
    }
  }
  /* Raw byte mutations. */
  if (out.empty()) {
    out.push_back(uint8_t(rng()));
  }
  for (int edits = pick(rng, 1, 8); edits > 0; edits--) {
    const size_t at = pick<size_t>(rng, 0, out.size() - 1);
    switch (pick(rng, 0, 6)) {
      case 0:
        out[at] ^= uint8_t(1u << pick(rng, 0, 7));
        break;
      case 1:
        out[at] = uint8_t(rng());
        break;
      case 2: {
        const uint64_t v = pick(rng, 0, 1) ? ~uint64_t(0) : uint64_t(pick(rng, 0, 1 << 20));
        std::memcpy(out.data() + at, &v, std::min<size_t>(8, out.size() - at));
        break;
      }
      case 3:
        out.erase(out.begin() + std::ptrdiff_t(at), out.begin() + std::ptrdiff_t(std::min(out.size(), at + pick<size_t>(rng, 1, 16))));
        break;
      case 4:
        out.insert(out.begin() + std::ptrdiff_t(at), pick<size_t>(rng, 1, 16), uint8_t(rng()));
        break;
      case 5:
        out.resize(at + 1);
        break;
      default:
        if (!corpus.empty()) {
          const auto &other = corpus[pick<size_t>(rng, 0, corpus.size() - 1)];
          if (!other.empty()) {
            const size_t from = pick<size_t>(rng, 0, other.size() - 1);
            const size_t n = std::min<size_t>(pick<size_t>(rng, 1, 64), other.size() - from);
            out.insert(out.begin() + std::ptrdiff_t(at), other.begin() + std::ptrdiff_t(from), other.begin() + std::ptrdiff_t(from + n));
          }
        }
    }
    if (out.empty()) {
      break;
    }
  }
  return out;
}

std::vector<std::vector<uint8_t>> load_corpus(const std::string &directory)
{
  std::vector<std::vector<uint8_t>> corpus;
  std::vector<std::filesystem::path> files;
  for (const auto &entry : std::filesystem::directory_iterator(core::path_from_utf8(directory))) {
    if (entry.is_regular_file()) {
      files.push_back(entry.path());
    }
  }
  std::sort(files.begin(), files.end());
  for (const auto &file : files) {
    corpus.push_back(core::read_file(file));
  }
  return corpus;
}

}  // namespace stk::fuzz
