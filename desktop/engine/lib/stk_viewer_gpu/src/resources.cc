/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "resources.hh"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

#include "GPU_storage_buffer.hh"
#include "GPU_texture.hh"

#include "stk/viewer_gpu/diagnostics.hh"

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

namespace {
std::atomic<uint64_t> g_nonfinite{0};
}

uint64_t nonfinite_float_uploads()
{
  return g_nonfinite.load();
}

size_t check_finite_upload(std::span<const float> data, const char *what, std::vector<float> *sanitized)
{
  size_t bad = 0;
  for (const float v : data) {
    bad += std::isfinite(v) ? 0 : 1;
  }
  if (bad == 0) {
    return 0;
  }
  g_nonfinite += bad;
  std::fprintf(stderr, "stk_viewer_gpu: non-finite float upload: %zu of %zu values of %s (replaced by 0)\n", bad,
               data.size(), what);
  if (sanitized) {
    sanitized->assign(data.begin(), data.end());
    for (float &v : *sanitized) {
      if (!std::isfinite(v)) {
        v = 0.0f;
      }
    }
  }
  return bad;
}

ResourcePtr make_float_storage(std::span<const float> data, const char *name)
{
  std::vector<float> sanitized;
  if (check_finite_upload(data, name, &sanitized) > 0) {
    data = sanitized;
  }
  return make_storage({reinterpret_cast<const uint8_t *>(data.data()), data.size_bytes()}, name);
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
