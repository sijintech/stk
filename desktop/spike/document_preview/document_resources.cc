/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "document_resources.hh"

#include <algorithm>
#include <array>
#include <utility>

namespace stk::document_preview {
namespace {

constexpr size_t kMaxAssets = 64;
constexpr size_t kMaxAssetBytes = 4 * 1024 * 1024;
constexpr size_t kMaxTotalBytes = 32 * 1024 * 1024;
constexpr size_t kMaxPathBytes = 1024;
constexpr size_t kMaxVersionBytes = 256;
constexpr size_t kMaxUrlBytes = 8192;
constexpr std::string_view kScheme = "stk-preview://local/";
constexpr std::string_view kHttpsScheme = "https://stk-preview.invalid/";

bool valid_utf8(std::string_view value, bool reject_controls)
{
  for (size_t i = 0; i < value.size();) {
    const auto first = static_cast<uint8_t>(value[i++]);
    uint32_t code = first;
    uint32_t minimum = 0;
    size_t following = 0;
    if (first >= 0xc2 && first <= 0xdf) {
      code = first & 0x1f;
      minimum = 0x80;
      following = 1;
    }
    else if (first >= 0xe0 && first <= 0xef) {
      code = first & 0x0f;
      minimum = 0x800;
      following = 2;
    }
    else if (first >= 0xf0 && first <= 0xf4) {
      code = first & 0x07;
      minimum = 0x10000;
      following = 3;
    }
    else if (first >= 0x80) {
      return false;
    }
    if (following > value.size() - i) {
      return false;
    }
    for (size_t j = 0; j < following; ++j) {
      const auto next = static_cast<uint8_t>(value[i++]);
      if ((next & 0xc0) != 0x80) {
        return false;
      }
      code = (code << 6) | (next & 0x3f);
    }
    if (code < minimum || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff) ||
        (reject_controls && (code < 0x20 || (code >= 0x7f && code <= 0x9f)))) {
      return false;
    }
  }
  return true;
}

bool canonical_uuid(std::string_view value)
{
  if (value.size() != 36) {
    return false;
  }
  for (size_t i = 0; i < value.size(); ++i) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (value[i] != '-') {
        return false;
      }
    }
    else if (!((value[i] >= '0' && value[i] <= '9') ||
               (value[i] >= 'a' && value[i] <= 'f'))) {
      return false;
    }
  }
  return true;
}

bool valid_version(std::string_view value)
{
  return !value.empty() && value.size() <= kMaxVersionBytes && value.front() != ' ' &&
         value.back() != ' ' && value != "." && value != ".." &&
         value.find_first_of("/\\?") == std::string_view::npos && valid_utf8(value, true);
}

bool valid_asset_path(std::string_view value)
{
  if (value.empty() || value.size() > kMaxPathBytes || value.front() == '/' ||
      value.back() == '/' || value.find_first_of("\\?:") != std::string_view::npos ||
      !valid_utf8(value, true)) {
    return false;
  }
  size_t begin = 0;
  while (begin < value.size()) {
    const size_t end = value.find('/', begin);
    const std::string_view part = value.substr(begin, end - begin);
    if (part.empty() || part == "." || part == "..") {
      return false;
    }
    if (end == std::string_view::npos) {
      break;
    }
    begin = end + 1;
  }
  return true;
}

std::string_view supported_mime(std::string_view mime)
{
  // Do not admit executable types, SVG or arbitrary charset/parameter variants.
  if (mime == "text/html" || mime == "text/html; charset=utf-8") {
    return "text/html; charset=utf-8";
  }
  if (mime == "text/css" || mime == "text/css; charset=utf-8") {
    return "text/css; charset=utf-8";
  }
  if (mime == "text/plain" || mime == "text/plain; charset=utf-8") {
    return "text/plain; charset=utf-8";
  }
  constexpr std::array<std::string_view, 5> binary = {
      "image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"};
  const auto found = std::find(binary.begin(), binary.end(), mime);
  return found == binary.end() ? std::string_view{} : *found;
}

bool unreserved(uint8_t value)
{
  return (value >= 'a' && value <= 'z') || (value >= 'A' && value <= 'Z') ||
         (value >= '0' && value <= '9') || value == '-' || value == '.' || value == '_' ||
         value == '~';
}

std::string encode(std::string_view value, bool keep_slashes)
{
  constexpr char hex[] = "0123456789ABCDEF";
  std::string result;
  result.reserve(value.size());
  for (const unsigned char byte : value) {
    if (unreserved(byte) || (keep_slashes && byte == '/')) {
      result.push_back(static_cast<char>(byte));
    }
    else {
      result.push_back('%');
      result.push_back(hex[byte >> 4]);
      result.push_back(hex[byte & 15]);
    }
  }
  return result;
}

int hex_value(char value)
{
  if (value >= '0' && value <= '9') {
    return value - '0';
  }
  if (value >= 'a' && value <= 'f') {
    return value - 'a' + 10;
  }
  if (value >= 'A' && value <= 'F') {
    return value - 'A' + 10;
  }
  return -1;
}

bool decode_once(std::string_view value, bool path, std::string &result)
{
  result.clear();
  result.reserve(value.size());
  for (size_t i = 0; i < value.size(); ++i) {
    uint8_t byte = static_cast<uint8_t>(value[i]);
    if (byte == '%') {
      if (value.size() - i < 3) {
        return false;
      }
      const int high = hex_value(value[i + 1]);
      const int low = hex_value(value[i + 2]);
      if (high < 0 || low < 0) {
        return false;
      }
      byte = static_cast<uint8_t>((high << 4) | low);
      i += 2;
      if (path && (byte == '/' || byte == '\\')) {
        return false;
      }
    }
    result.push_back(static_cast<char>(byte));
  }
  return valid_utf8(result, true) && result.find('\\') == std::string::npos;
}

std::string identity_prefix(const PreviewIdentity &identity, bool encoded)
{
  return identity.session_id + "/" + identity.project_id + "/" + identity.resource_id + "/" +
         (encoded ? encode(identity.source_version, false) : identity.source_version) + "/assets/";
}

bool resolve_url(std::string_view url, const PreviewIdentity &identity, std::string &asset_path)
{
  if (url.empty() || url.size() > kMaxUrlBytes || !valid_utf8(url, true) ||
      url.find(' ') != std::string_view::npos || url.find('\\') != std::string_view::npos) {
    return false;
  }
  if (url.starts_with(kScheme)) {
    url.remove_prefix(kScheme.size());
  }
  else if (url.starts_with(kHttpsScheme)) {
    url.remove_prefix(kHttpsScheme.size());
  }
  else {
    return false;
  }
  const size_t fragment = url.find('#');
  if (fragment != std::string_view::npos) {
    std::string ignored;
    if (!decode_once(url.substr(fragment + 1), false, ignored)) {
      return false;
    }
    url = url.substr(0, fragment);
  }
  if (url.find('?') != std::string_view::npos) {
    return false;
  }
  std::string decoded;
  if (!decode_once(url, true, decoded)) {
    return false;
  }
  const std::string prefix = identity_prefix(identity, false);
  if (!decoded.starts_with(prefix)) {
    return false;
  }
  asset_path = decoded.substr(prefix.size());
  return valid_asset_path(asset_path);
}

std::string content_policy(const PreviewIdentity &identity)
{
  const std::string prefix = identity_prefix(identity, true);
  const std::string sources = std::string(kScheme) + prefix + " " + std::string(kHttpsScheme) + prefix;
  return "default-src 'none'; script-src 'none'; script-src-attr 'none'; connect-src 'none'; "
         "frame-src 'none'; child-src 'none'; object-src 'none'; form-action 'none'; "
         "base-uri 'none'; frame-ancestors 'none'; font-src 'none'; media-src 'none'; "
         "style-src 'unsafe-inline' " +
         sources + "; img-src " + sources + ";";
}

ResourceResponse response(int status, const PreviewIdentity &identity)
{
  ResourceResponse result;
  result.status = status;
  result.content_security_policy = content_policy(identity);
  return result;
}

}  // namespace

std::shared_ptr<ResourceSession> ResourceSession::create(PreviewIdentity identity,
                                                       std::vector<ResourceAsset> assets,
                                                       std::string &error)
{
  error.clear();
  if (!canonical_uuid(identity.project_id) || !canonical_uuid(identity.resource_id) ||
      !canonical_uuid(identity.session_id) || !valid_version(identity.source_version)) {
    error = "Preview identity requires canonical UUIDs and an explicit bounded source version.";
    return {};
  }
  if (assets.empty() || assets.size() > kMaxAssets) {
    error = "A preview requires between 1 and 64 explicitly listed assets.";
    return {};
  }
  auto session = std::shared_ptr<ResourceSession>(new ResourceSession);
  session->identity_ = std::move(identity);
  size_t total = 0;
  for (auto &asset : assets) {
    if (!valid_asset_path(asset.path)) {
      error = "Preview asset paths must be bounded relative virtual paths without traversal.";
      return {};
    }
    const std::string_view mime = supported_mime(asset.mime);
    if (mime.empty()) {
      error = "Preview asset MIME type is not supported by this static-content prototype.";
      return {};
    }
    if (asset.bytes.size() > kMaxAssetBytes || asset.bytes.size() > kMaxTotalBytes - total) {
      error = "Preview assets exceed the 4 MiB per-asset or 32 MiB per-session byte budget.";
      return {};
    }
    if (mime.starts_with("text/") && !asset.bytes.empty() &&
        !valid_utf8(std::string_view(reinterpret_cast<const char *>(asset.bytes.data()),
                                    asset.bytes.size()),
                    false)) {
      error = "Preview text assets must contain valid UTF-8.";
      return {};
    }
    total += asset.bytes.size();
    asset.mime = std::string(mime);
    const std::string path = asset.path;
    if (!session->assets_.emplace(path, std::move(asset)).second) {
      error = "Preview asset paths must be unique.";
      return {};
    }
  }
  return session;
}

std::string ResourceSession::url(std::string_view asset_path, bool https) const
{
  if (!active() || !valid_asset_path(asset_path) || assets_.find(asset_path) == assets_.end()) {
    return {};
  }
  const std::string result = std::string(https ? kHttpsScheme : kScheme) +
                             identity_prefix(identity_, true) + encode(asset_path, true);
  return active() ? result : std::string{};
}

ResourceResponse ResourceSession::read(std::string_view url, std::string_view method) const
{
  if (!active()) {
    return response(410, identity_);
  }
  if (method != "GET" && method != "HEAD") {
    return response(405, identity_);
  }
  std::string path;
  if (!resolve_url(url, identity_, path)) {
    return response(403, identity_);
  }
  const auto asset = assets_.find(path);
  if (asset == assets_.end()) {
    return response(404, identity_);
  }
  ResourceResponse result = response(200, identity_);
  result.mime = asset->second.mime;
  if (method == "GET") {
    result.bytes = asset->second.bytes;
  }
  return active() ? result : response(410, identity_);
}

bool ResourceSession::allows_navigation(std::string_view url) const
{
  std::string path;
  return active() && resolve_url(url, identity_, path) && assets_.find(path) != assets_.end() &&
         active();
}

void ResourceSession::close()
{
  active_.store(false, std::memory_order_release);
}

bool ResourceSession::active() const
{
  return active_.load(std::memory_order_acquire);
}

}  // namespace stk::document_preview
