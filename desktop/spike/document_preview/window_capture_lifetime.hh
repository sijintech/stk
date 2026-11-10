/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include <atomic>
#include <cstdint>

namespace stk::document_preview::capture_lifetime {
struct Owner {
  uintptr_t window = 0;
  uint64_t process = 0, thread = 0;
  bool operator==(const Owner &) const = default;
};

// The window-destruction hook and the item's Closed event permanently retire a lease.
// The event may arrive off-thread. It only changes this flag, never COM or the HWND.
class Lifetime {
 public:
  explicit Lifetime(Owner owner) : owner_(owner) {}
  bool accepts(Owner current, uint64_t caller_thread)
  {
    if (!owner_.window || !owner_.process || !owner_.thread || current != owner_ ||
        caller_thread != owner_.thread) {
      invalidate();
    }
    return !closed_.load();
  }
  void invalidate() { closed_.store(true); }
  uint64_t thread() const { return owner_.thread; }

 private:
  Owner owner_;
  std::atomic<bool> closed_{false};
};
}  // namespace stk::document_preview::capture_lifetime
