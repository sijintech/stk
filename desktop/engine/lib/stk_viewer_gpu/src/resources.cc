/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "resources.hh"

#include <algorithm>
#include <cstring>
#include <vector>

#include "GPU_storage_buffer.hh"
#include "GPU_texture.hh"

namespace stk::viewer_gpu {

using namespace blender;

GpuResource::~GpuResource()
{
  if (ssbo) {
    GPU_storagebuf_free(ssbo);
  }
  if (texture) {
    GPU_texture_free(texture);
  }
}

ResourcePtr make_storage(std::span<const uint8_t> data, const char *name)
{
  const size_t size = std::max<size_t>(16, (data.size() + 15) / 16 * 16);
  auto r = std::make_shared<GpuResource>();
  if (size == data.size()) {
    r->ssbo = GPU_storagebuf_create_ex(size, data.data(), GPU_USAGE_STATIC, name);
  }
  else {
    std::vector<uint8_t> padded(size, 0);
    if (!data.empty()) {
      std::memcpy(padded.data(), data.data(), data.size());
    }
    r->ssbo = GPU_storagebuf_create_ex(size, padded.data(), GPU_USAGE_STATIC, name);
  }
  r->bytes = size;
  return r;
}

ResourceCache::~ResourceCache()
{
  clear();
}

ResourcePtr ResourceCache::get(const std::string &key, const std::function<ResourcePtr()> &create)
{
  clock_++;
  auto it = entries_.find(key);
  if (it != entries_.end()) {
    it->second.last_use = clock_;
    hits_++;
    return it->second.resource;
  }
  ResourcePtr r = create();
  if (r) {
    r->key = key;
    entries_[key] = {r, clock_};
    uploads_++;
  }
  return r;
}

uint64_t ResourceCache::resident() const
{
  uint64_t total = 0;
  for (const auto &[key, e] : entries_) {
    total += e.resource->bytes;
  }
  return total;
}

void ResourceCache::evict(const uint64_t budget)
{
  uint64_t total = resident();
  if (total <= budget) {
    return;
  }
  std::vector<std::pair<uint64_t, std::string>> candidates;
  for (const auto &[key, e] : entries_) {
    if (e.resource.use_count() == 1) {
      candidates.emplace_back(e.last_use, key);
    }
  }
  std::sort(candidates.begin(), candidates.end());
  for (const auto &[use, key] : candidates) {
    if (total <= budget) {
      break;
    }
    auto it = entries_.find(key);
    total -= it->second.resource->bytes;
    entries_.erase(it);
    evictions_++;
  }
}

void ResourceCache::clear()
{
  entries_.clear();
}

}  // namespace stk::viewer_gpu
