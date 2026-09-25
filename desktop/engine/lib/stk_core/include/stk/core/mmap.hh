/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Read-only file mapping (POSIX mmap / Windows CreateFileMapping) and SharedBytes, a
 * reference-counted byte range that can view a mapping, a sub-range of it (a .stkp chunk)
 * or an owned vector. Payload accessors are zero-copy views into SharedBytes. */

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace stk::core {

class FileError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

/** A read-only mapping of a whole file. Empty files map to an empty span. Not copyable. */
class MappedFile {
 public:
  /** Maps `path`; throws FileError when it cannot be opened or mapped. */
  explicit MappedFile(const std::filesystem::path &path);
  ~MappedFile();
  MappedFile(const MappedFile &) = delete;
  MappedFile &operator=(const MappedFile &) = delete;

  const uint8_t *data() const
  {
    return data_;
  }
  size_t size() const
  {
    return size_;
  }
  std::span<const uint8_t> bytes() const
  {
    return {data_, size_};
  }

 private:
  const uint8_t *data_ = nullptr;
  size_t size_ = 0;
#ifdef _WIN32
  void *file_ = nullptr;
  void *mapping_ = nullptr;
#endif
};

/** Immutable bytes with shared ownership (a mapping, part of one, or an owned buffer). */
class SharedBytes {
 public:
  SharedBytes() = default;
  static SharedBytes from_vector(std::vector<uint8_t> data);
  static SharedBytes copy_of(std::span<const uint8_t> data);
  /** Map a file (use_mmap) or read it into memory. Throws FileError. */
  static SharedBytes from_file(const std::filesystem::path &path, bool use_mmap = true);

  const uint8_t *data() const
  {
    return data_;
  }
  size_t size() const
  {
    return size_;
  }
  bool empty() const
  {
    return size_ == 0;
  }
  std::span<const uint8_t> span() const
  {
    return {data_, size_};
  }
  /** A sub-range sharing ownership; throws std::out_of_range when it does not fit. */
  SharedBytes slice(size_t offset, size_t length) const;
  /** True when the bytes live in a file mapping (not an owned copy). */
  bool mapped() const
  {
    return mapped_;
  }

 private:
  std::shared_ptr<const void> owner_;
  const uint8_t *data_ = nullptr;
  size_t size_ = 0;
  bool mapped_ = false;
};

/** Read a whole file into memory (throws FileError). */
std::vector<uint8_t> read_file(const std::filesystem::path &path);
std::string read_text_file(const std::filesystem::path &path);
/** Write via a temporary sibling and rename (atomic replace on the same filesystem). Throws FileError. */
void write_file_atomic(const std::filesystem::path &path, std::span<const uint8_t> data);

}  // namespace stk::core
