/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* stk.payload/2 decoder (docs/specs/stk-render-payload-v2.md): directory form, .stkp bundles and
 * manifests whose buffers come from the content-addressed blob cache. Buffers are verified against
 * their sha256 and exposed as zero-copy views (memory-mapped where possible). Validation follows
 * spec §10 exactly as suan/render/payload.py's _Validator does, raising PayloadError with an
 * RFC 6901 JSON-pointer path on the first problem. */

#include "stk/core/mmap.hh"
#include "stk/io/json.hh"

#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <map>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace stk::core {
class ThreadPool;
}

namespace stk::io {

static_assert(std::endian::native == std::endian::little, "payload buffers are little-endian");

inline constexpr std::string_view kPayloadSchema = "stk.payload/2";

class PayloadError : public std::runtime_error {
 public:
  PayloadError(const std::string &message, std::string path = {}, std::string code = "invalid_payload");
  /** Message without the path prefix. */
  const std::string &message() const
  {
    return message_;
  }
  const std::string &path() const
  {
    return path_;
  }
  const std::string &code() const
  {
    return code_;
  }

 private:
  std::string message_, path_, code_;
};

enum class ComponentType : uint8_t { I8, U8, I16, U16, I32, U32, F32, F64 };

std::optional<ComponentType> parse_component_type(std::string_view name);
std::string_view component_type_name(ComponentType type);
size_t component_size(ComponentType type);
bool component_is_float(ComponentType type);
bool component_is_signed(ComponentType type);

template<typename T> constexpr std::optional<ComponentType> component_type_of()
{
  if constexpr (std::is_same_v<T, int8_t>) {
    return ComponentType::I8;
  }
  else if constexpr (std::is_same_v<T, uint8_t>) {
    return ComponentType::U8;
  }
  else if constexpr (std::is_same_v<T, int16_t>) {
    return ComponentType::I16;
  }
  else if constexpr (std::is_same_v<T, uint16_t>) {
    return ComponentType::U16;
  }
  else if constexpr (std::is_same_v<T, int32_t>) {
    return ComponentType::I32;
  }
  else if constexpr (std::is_same_v<T, uint32_t>) {
    return ComponentType::U32;
  }
  else if constexpr (std::is_same_v<T, float>) {
    return ComponentType::F32;
  }
  else if constexpr (std::is_same_v<T, double>) {
    return ComponentType::F64;
  }
  return std::nullopt;
}

struct PayloadBuffer {
  std::string id;
  std::string sha256;
  uint64_t byte_length = 0;
  core::SharedBytes bytes;
};

struct PayloadAccessor {
  std::string id;
  size_t buffer = 0; /* index into Payload::buffers */
  uint64_t byte_offset = 0;
  uint64_t count = 0;
  ComponentType type = ComponentType::U8;
  uint32_t components = 1;
  bool normalized = false;

  uint64_t value_count() const
  {
    return count * components;
  }
  uint64_t byte_size() const
  {
    return value_count() * component_size(type);
  }
};

/** A decoded, validated payload. Views stay valid as long as the Payload (or a copy) lives. */
class Payload {
 public:
  Json manifest; /* buffer URIs rewritten to "sha256:<hex>" as Python's unpack_stkp does */
  std::vector<PayloadBuffer> buffers;
  std::vector<PayloadAccessor> accessors;
  std::array<double, 3> render_origin{};
  std::string length_unit;

  bool has_accessor(std::string_view id) const;
  const PayloadAccessor &accessor(std::string_view id) const;
  std::span<const uint8_t> accessor_bytes(std::string_view id) const;
  std::span<const uint8_t> accessor_bytes(const PayloadAccessor &accessor) const;

  /** Zero-copy typed view (count x components values); throws PayloadError when T does not match the type. */
  template<typename T> std::span<const T> view(std::string_view id) const
  {
    const PayloadAccessor &a = accessor(id);
    if (component_type_of<T>() != a.type) {
      throw PayloadError("accessor '" + a.id + "' has type " + std::string(component_type_name(a.type)));
    }
    const std::span<const uint8_t> bytes = accessor_bytes(a);
    return {reinterpret_cast<const T *>(bytes.data()), size_t(a.value_count())};
  }

  /** Element `index` (of count x components) as double (no normalization). */
  double element(const PayloadAccessor &accessor, uint64_t index) const;
  /** All values as float32 (normalized integers mapped to [0, 1] / [-1, 1], as web floats()). */
  std::vector<float> floats(std::string_view id) const;
  /** All values as float64 (raw integer values, no normalization). */
  std::vector<double> doubles(std::string_view id) const;

  const Json *colormap(std::string_view id) const;
  const Json *layer(std::string_view id) const;
  const Json &layers() const;
  /** Physical origin of a layer's coordinates: its `origin`, else render_origin (spec §4). */
  std::array<double, 3> layer_origin(const Json &layer) const;

  uint64_t total_bytes() const;

 private:
  friend class PayloadValidator;
  std::unordered_map<std::string, size_t> accessor_index_;
  std::unordered_map<std::string, size_t> colormap_index_;
  std::unordered_map<std::string, size_t> layer_index_;
};

struct DecodeOptions {
  /** Map buffer files instead of reading them (directory form, blob cache, .stkp files). */
  bool use_mmap = true;
  /** Hash buffers on this pool (nullptr: the calling thread). */
  core::ThreadPool *pool = nullptr;
};

/** Returns the bytes of a blob by sha256 (hex), or nullopt when unavailable. */
using BlobProvider = std::function<std::optional<core::SharedBytes>(std::string_view sha256)>;

/** Directory form: `path` is the directory or its manifest.json; buffers are sibling <sha256>.bin files. */
Payload read_directory(const std::filesystem::path &path, const DecodeOptions &options = {});
/** A .stkp file (mapped when options.use_mmap). */
Payload read_stkp(const std::filesystem::path &path, const DecodeOptions &options = {});
/** .stkp bytes (chunks are views into `data`). */
Payload decode_stkp(const core::SharedBytes &data, const DecodeOptions &options = {});
/** A manifest with "sha256:<hex>" buffers resolved through `blobs` (the hub/bridge blob cache). */
Payload decode_manifest(Json manifest, const BlobProvider &blobs, const DecodeOptions &options = {});
/** A manifest plus in-memory blobs keyed by sha256 (Python's decode(manifest, blobs)). */
Payload decode(Json manifest, std::map<std::string, core::SharedBytes> blobs, const DecodeOptions &options = {});

/** Split .stkp bytes into the manifest (URIs rewritten to sha256) and its chunk blobs keyed by sha256
 * (Python unpack_stkp: framing, chunk types and each buffer's byteLength/sha256 are checked). */
std::pair<Json, std::map<std::string, core::SharedBytes>> unpack_stkp(const core::SharedBytes &data,
                                                                     const DecodeOptions &options = {});

/** .stkp bytes of a manifest and its blobs (Python pack_stkp; buffers in manifest order). */
std::vector<uint8_t> pack_stkp(const Json &manifest, const std::map<std::string, core::SharedBytes> &blobs);

/** Spec §10 validation of a manifest against its blobs (throws PayloadError). */
void validate_payload(const Payload &payload);

/** Scalar-bar label format subset (Python/d3): `[sign][#][0][width<=2][,][.precision<=2][eEfFgG%]` or
 * `[sign][#][0][width][,]d`, as payload.py's LABEL_FORMAT (without Python's trailing-newline `$`). */
bool is_label_format(std::string_view format);

/** An id as payload.py's _ID: ^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$. */
bool is_payload_id(std::string_view id);

}  // namespace stk::io
