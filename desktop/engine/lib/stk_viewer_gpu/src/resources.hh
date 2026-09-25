/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* GPU buffers and textures of payload layers, content-addressed and budgeted.
 *
 * Keys are content descriptors: a raw accessor upload is keyed by its buffer's sha256, byte offset
 * and size, so static geometry shared by several timesteps (the producer keeps render_origin fixed
 * per view, spec §4) is uploaded once. Derived data (colour values, normals, instance transforms,
 * textures) is keyed by the descriptors of its inputs and parameters. A resource stays alive while
 * a scene holds it; unreferenced ones stay cached for the next step until the budget needs their
 * memory (least recently used first). */

#include <cstdint>
#include <functional>
#include <memory>
#include <span>
#include <string>
#include <unordered_map>

namespace blender::gpu {
class StorageBuf;
class Texture;
}  // namespace blender::gpu

namespace stk::viewer_gpu {

struct GpuResource {
  blender::gpu::StorageBuf *ssbo = nullptr;
  blender::gpu::Texture *texture = nullptr;
  uint64_t bytes = 0;
  std::string key;

  GpuResource() = default;
  ~GpuResource();
  GpuResource(const GpuResource &) = delete;
  GpuResource &operator=(const GpuResource &) = delete;
};
using ResourcePtr = std::shared_ptr<GpuResource>;

/** A storage buffer with a copy of `data` (padded to a multiple of 16 bytes; empty data gives a
 * 16-byte zero buffer). */
ResourcePtr make_storage(std::span<const uint8_t> data, const char *name);

class ResourceCache {
 public:
  explicit ResourceCache(uint64_t budget) : budget_(budget) {}
  ~ResourceCache();

  /** The cached resource of `key`, else the one `create` returns (cached unless null). */
  ResourcePtr get(const std::string &key, const std::function<ResourcePtr()> &create);
  /** Free unreferenced resources, least recently used first, until resident <= `budget`. */
  void evict(uint64_t budget);
  void evict_to_budget()
  {
    evict(budget_);
  }
  /** Free every unreferenced resource. */
  void trim()
  {
    evict(0);
  }
  void clear();

  uint64_t resident() const;
  uint64_t budget() const
  {
    return budget_;
  }
  void set_budget(uint64_t budget)
  {
    budget_ = budget;
  }
  size_t size() const
  {
    return entries_.size();
  }
  size_t evictions() const
  {
    return evictions_;
  }
  size_t uploads() const
  {
    return uploads_;
  }
  size_t hits() const
  {
    return hits_;
  }

 private:
  struct Entry {
    ResourcePtr resource;
    uint64_t last_use = 0;
  };
  std::unordered_map<std::string, Entry> entries_;
  uint64_t budget_;
  uint64_t clock_ = 0;
  size_t evictions_ = 0, uploads_ = 0, hits_ = 0;
};

}  // namespace stk::viewer_gpu
