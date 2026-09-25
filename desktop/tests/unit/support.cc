/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include "stk/core/paths.hh"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace stk::test {

std::filesystem::path repo_root()
{
  return core::path_from_utf8(STK_REPO_ROOT);
}

std::filesystem::path fixtures_dir()
{
  return core::path_from_utf8(STK_FIXTURES_DIR);
}

std::filesystem::path example_dir()
{
  return repo_root() / "docs" / "specs" / "examples" / "payload-v2";
}

io::Json fixture_json(const std::string &name)
{
  return io::read_json_file(fixtures_dir() / core::path_from_utf8(name));
}

std::vector<uint8_t> base64_decode(const std::string &text)
{
  static const std::string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::vector<uint8_t> out;
  uint32_t buffer = 0;
  int bits = 0;
  for (char c : text) {
    if (c == '=') {
      break;
    }
    const size_t v = alphabet.find(c);
    if (v == std::string::npos) {
      continue;
    }
    buffer = (buffer << 6) | uint32_t(v);
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out.push_back(uint8_t(buffer >> bits));
    }
  }
  return out;
}

namespace {

io::Json *walk(io::Json &root, const io::Json &path, size_t depth)
{
  io::Json *target = &root;
  for (size_t i = 0; i < depth; i++) {
    const io::Json &key = path[i];
    target = key.is_string() ? &(*target)[key.get<std::string>()] : &(*target)[key.get<size_t>()];
  }
  return target;
}

}  // namespace

io::Json apply_patches(io::Json manifest, const io::Json &patches)
{
  for (const io::Json &patch : patches) {
    const std::string op = patch[0].get<std::string>();
    const io::Json &path = patch[1];
    if (op == "set" && path.empty()) {
      manifest = patch[2];
      continue;
    }
    io::Json *parent = walk(manifest, path, path.size() - 1);
    const io::Json &last = path.back();
    if (op == "set") {
      if (last.is_string()) {
        (*parent)[last.get<std::string>()] = patch[2];
      }
      else {
        (*parent)[last.get<size_t>()] = patch[2];
      }
    }
    else if (op == "delete") {
      if (last.is_string()) {
        parent->erase(last.get<std::string>());
      }
      else {
        parent->erase(last.get<size_t>());
      }
    }
    else if (op == "append") {
      (*parent)[last.get<std::string>()].push_back(patch[2]);
    }
    else {
      throw std::runtime_error("unknown patch op " + op);
    }
  }
  return manifest;
}

std::map<std::string, core::SharedBytes> example_blobs()
{
  std::map<std::string, core::SharedBytes> blobs;
  for (const auto &entry : std::filesystem::directory_iterator(example_dir())) {
    if (entry.path().extension() == ".bin") {
      blobs[core::path_to_utf8(entry.path().stem())] = core::SharedBytes::from_file(entry.path());
    }
  }
  return blobs;
}

double fixture_number(const io::Json &value)
{
  if (value.is_string()) {
    const std::string s = value.get<std::string>();
    if (s == "nan") {
      return std::numeric_limits<double>::quiet_NaN();
    }
    if (s == "inf" || s == "Infinity") {
      return std::numeric_limits<double>::infinity();
    }
    if (s == "-inf" || s == "-Infinity") {
      return -std::numeric_limits<double>::infinity();
    }
    if (s == "NaN") {
      return std::numeric_limits<double>::quiet_NaN();
    }
    throw std::runtime_error("not a number: " + s);
  }
  return value.get<double>();
}

std::filesystem::path scratch_dir(const std::string &name)
{
  const std::filesystem::path dir = core::path_from_utf8(STK_TEST_SCRATCH_DIR) / name;
  std::error_code ec;
  std::filesystem::remove_all(dir, ec);
  std::filesystem::create_directories(dir);
  return dir;
}

}  // namespace stk::test
