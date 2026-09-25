/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/core/mmap.hh"

#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <random>
#include <system_error>

#ifdef _WIN32
#  include <windows.h>
#else
#  include <fcntl.h>
#  include <sys/mman.h>
#  include <sys/stat.h>
#  include <unistd.h>
#endif

namespace stk::core {

namespace {

std::string describe(const std::filesystem::path &path)
{
  const auto text = path.u8string();
  return std::string(text.begin(), text.end());
}

}  // namespace

#ifdef _WIN32

MappedFile::MappedFile(const std::filesystem::path &path)
{
  HANDLE file = CreateFileW(path.c_str(),
                            GENERIC_READ,
                            FILE_SHARE_READ | FILE_SHARE_DELETE,
                            nullptr,
                            OPEN_EXISTING,
                            FILE_ATTRIBUTE_NORMAL,
                            nullptr);
  if (file == INVALID_HANDLE_VALUE) {
    throw FileError("cannot open " + describe(path) + ": " +
                    std::system_category().message(int(GetLastError())));
  }
  LARGE_INTEGER size{};
  if (!GetFileSizeEx(file, &size)) {
    const DWORD error = GetLastError();
    CloseHandle(file);
    throw FileError("cannot stat " + describe(path) + ": " + std::system_category().message(int(error)));
  }
  file_ = file;
  size_ = size_t(size.QuadPart);
  if (size_ == 0) {
    return;
  }
  HANDLE mapping = CreateFileMappingW(file, nullptr, PAGE_READONLY, 0, 0, nullptr);
  if (!mapping) {
    const DWORD error = GetLastError();
    CloseHandle(file);
    file_ = nullptr;
    throw FileError("cannot map " + describe(path) + ": " + std::system_category().message(int(error)));
  }
  mapping_ = mapping;
  data_ = static_cast<const uint8_t *>(MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0));
  if (!data_) {
    const DWORD error = GetLastError();
    CloseHandle(mapping);
    CloseHandle(file);
    file_ = mapping_ = nullptr;
    throw FileError("cannot map " + describe(path) + ": " + std::system_category().message(int(error)));
  }
}

MappedFile::~MappedFile()
{
  if (data_) {
    UnmapViewOfFile(data_);
  }
  if (mapping_) {
    CloseHandle(static_cast<HANDLE>(mapping_));
  }
  if (file_) {
    CloseHandle(static_cast<HANDLE>(file_));
  }
}

#else

MappedFile::MappedFile(const std::filesystem::path &path)
{
  const int fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
  if (fd < 0) {
    throw FileError("cannot open " + describe(path) + ": " + std::strerror(errno));
  }
  struct stat st{};
  if (::fstat(fd, &st) != 0) {
    const int error = errno;
    ::close(fd);
    throw FileError("cannot stat " + describe(path) + ": " + std::strerror(error));
  }
  if (!S_ISREG(st.st_mode)) {
    ::close(fd);
    throw FileError(describe(path) + " is not a regular file");
  }
  size_ = size_t(st.st_size);
  if (size_ > 0) {
    void *address = ::mmap(nullptr, size_, PROT_READ, MAP_PRIVATE, fd, 0);
    if (address == MAP_FAILED) {
      const int error = errno;
      ::close(fd);
      throw FileError("cannot map " + describe(path) + ": " + std::strerror(error));
    }
    data_ = static_cast<const uint8_t *>(address);
  }
  ::close(fd); /* the mapping keeps the file referenced */
}

MappedFile::~MappedFile()
{
  if (data_) {
    ::munmap(const_cast<uint8_t *>(data_), size_);
  }
}

#endif

SharedBytes SharedBytes::from_vector(std::vector<uint8_t> data)
{
  auto owner = std::make_shared<std::vector<uint8_t>>(std::move(data));
  SharedBytes bytes;
  bytes.data_ = owner->data();
  bytes.size_ = owner->size();
  bytes.owner_ = std::move(owner);
  return bytes;
}

SharedBytes SharedBytes::copy_of(std::span<const uint8_t> data)
{
  return from_vector(std::vector<uint8_t>(data.begin(), data.end()));
}

SharedBytes SharedBytes::from_file(const std::filesystem::path &path, bool use_mmap)
{
  if (!use_mmap) {
    return from_vector(read_file(path));
  }
  auto mapping = std::make_shared<MappedFile>(path);
  SharedBytes bytes;
  bytes.data_ = mapping->data();
  bytes.size_ = mapping->size();
  bytes.mapped_ = true;
  bytes.owner_ = std::move(mapping);
  return bytes;
}

SharedBytes SharedBytes::slice(size_t offset, size_t length) const
{
  if (offset > size_ || length > size_ - offset) {
    throw std::out_of_range("SharedBytes::slice out of range");
  }
  SharedBytes bytes = *this;
  bytes.data_ = data_ + offset;
  bytes.size_ = length;
  return bytes;
}

std::vector<uint8_t> read_file(const std::filesystem::path &path)
{
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw FileError("cannot open " + describe(path));
  }
  stream.seekg(0, std::ios::end);
  const std::streamoff size = stream.tellg();
  if (size < 0) {
    throw FileError("cannot read " + describe(path));
  }
  stream.seekg(0, std::ios::beg);
  std::vector<uint8_t> data(static_cast<size_t>(size));
  if (size > 0 && !stream.read(reinterpret_cast<char *>(data.data()), size)) {
    throw FileError("cannot read " + describe(path));
  }
  return data;
}

std::string read_text_file(const std::filesystem::path &path)
{
  const std::vector<uint8_t> data = read_file(path);
  return std::string(data.begin(), data.end());
}

void write_file_atomic(const std::filesystem::path &path, std::span<const uint8_t> data)
{
  static std::atomic<uint64_t> counter{0};
  std::random_device device;
  const uint64_t token = (uint64_t(device()) << 32) ^ counter.fetch_add(1);
  std::filesystem::path tmp = path;
  tmp += ".tmp" + std::to_string(token);
  {
    std::ofstream stream(tmp, std::ios::binary | std::ios::trunc);
    if (!stream) {
      throw FileError("cannot create " + describe(tmp));
    }
    stream.write(reinterpret_cast<const char *>(data.data()), std::streamsize(data.size()));
    stream.flush();
    if (!stream) {
      stream.close();
      std::error_code ignored;
      std::filesystem::remove(tmp, ignored);
      throw FileError("cannot write " + describe(tmp));
    }
  }
  std::error_code error;
  std::filesystem::rename(tmp, path, error);
  if (error) {
    std::error_code ignored;
    std::filesystem::remove(tmp, ignored);
    throw FileError("cannot rename " + describe(tmp) + " to " + describe(path) + ": " + error.message());
  }
}

}  // namespace stk::core
