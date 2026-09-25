/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/blob_cache.hh"

#include "stk/core/log.hh"
#include "stk/core/sha256.hh"

namespace stk::io {

BlobCache::BlobCache(std::filesystem::path root) : root_(std::move(root)) {}

std::filesystem::path BlobCache::path_for(std::string_view sha256) const
{
  if (!core::is_sha256_hex(sha256)) {
    throw PayloadError("invalid blob id '" + std::string(sha256) + "'", "", "invalid_blob");
  }
  return root_ / std::string(sha256.substr(0, 2)) / std::string(sha256);
}

bool BlobCache::contains(std::string_view sha256) const
{
  if (!core::is_sha256_hex(sha256)) {
    return false;
  }
  std::error_code ec;
  return std::filesystem::is_regular_file(path_for(sha256), ec);
}

std::optional<core::SharedBytes> BlobCache::open(std::string_view sha256, bool verify, bool use_mmap) const
{
  if (!contains(sha256)) {
    return std::nullopt;
  }
  const std::filesystem::path path = path_for(sha256);
  core::SharedBytes bytes;
  try {
    bytes = core::SharedBytes::from_file(path, use_mmap);
  }
  catch (const core::FileError &error) {
    core::log_warning("blob_cache", "cannot read {}: {}", std::string(sha256), error.what());
    return std::nullopt;
  }
  if (verify && core::Sha256::hex(bytes.span()) != sha256) {
    core::log_warning("blob_cache", "removing corrupt blob {}", std::string(sha256));
    bytes = {};
    std::error_code ec;
    std::filesystem::remove(path, ec);
    return std::nullopt;
  }
  return bytes;
}

std::string BlobCache::put(std::span<const uint8_t> data) const
{
  const std::string sha = core::Sha256::hex(data);
  if (contains(sha)) {
    return sha;
  }
  const std::filesystem::path path = path_for(sha);
  std::error_code ec;
  std::filesystem::create_directories(path.parent_path(), ec);
  if (ec) {
    throw core::FileError("cannot create " + path.parent_path().string() + ": " + ec.message());
  }
#ifndef _WIN32
  std::filesystem::permissions(root_, std::filesystem::perms::owner_all, std::filesystem::perm_options::replace, ec);
  std::filesystem::permissions(path.parent_path(), std::filesystem::perms::owner_all,
                               std::filesystem::perm_options::replace, ec);
#endif
  core::write_file_atomic(path, data);
  return sha;
}

BlobProvider BlobCache::provider(bool verify, bool use_mmap) const
{
  return [cache = *this, verify, use_mmap](std::string_view sha) { return cache.open(sha, verify, use_mmap); };
}

}  // namespace stk::io
