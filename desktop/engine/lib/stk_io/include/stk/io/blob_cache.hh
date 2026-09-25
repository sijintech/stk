/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Content-addressed blob cache `<cache>/blobs/<aa>/<sha256>`: the layout of the hub blob store and
 * suan.graph.service.DirectoryBlobSink (root = <cache>/blobs). Files are immutable once written
 * (atomic rename), so readers map them without locking. */

#include "stk/core/mmap.hh"
#include "stk/io/payload.hh"

#include <filesystem>
#include <optional>
#include <span>
#include <string>
#include <string_view>

namespace stk::io {

class BlobCache {
 public:
  /** `root` is the blobs directory itself (e.g. core::default_blob_cache_dir()). */
  explicit BlobCache(std::filesystem::path root);

  const std::filesystem::path &root() const
  {
    return root_;
  }
  /** `<root>/<sha[:2]>/<sha>`; throws PayloadError for anything but 64 lower-case hex digits. */
  std::filesystem::path path_for(std::string_view sha256) const;
  bool contains(std::string_view sha256) const;

  /**
   * The bytes of a blob (mapped when `use_mmap`), or nullopt when absent. With `verify` the content
   * is hashed; a corrupt file is removed and reported as absent (it will be fetched again).
   */
  std::optional<core::SharedBytes> open(std::string_view sha256, bool verify = true, bool use_mmap = true) const;

  /** Store bytes (idempotent, atomic); returns their sha256. */
  std::string put(std::span<const uint8_t> data) const;

  /** A BlobProvider for decode_manifest(). */
  BlobProvider provider(bool verify = true, bool use_mmap = true) const;

 private:
  std::filesystem::path root_;
};

}  // namespace stk::io
