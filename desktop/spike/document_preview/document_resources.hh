/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <atomic>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace stk::document_preview {

struct PreviewIdentity {
  std::string project_id;
  std::string resource_id;
  std::string source_version;
  std::string session_id;
};

struct ResourceAsset {
  std::string path;  // Relative virtual path, never a path to open on the host.
  std::string mime;
  std::vector<uint8_t> bytes;
};

struct ResourceResponse {
  int status = 403;
  std::string mime = "text/plain; charset=utf-8";
  std::vector<uint8_t> bytes;
  std::string content_security_policy;
};

/** Immutable, bounded bytes explicitly admitted to one preview session.
 * No filesystem or network access takes place in read(). Closing invalidates all URLs.
 * Platform adapters must also reject external navigation and disable active content.
 */
class ResourceSession {
 public:
  static std::shared_ptr<ResourceSession> create(PreviewIdentity identity,
                                                std::vector<ResourceAsset> assets,
                                                std::string &error);
  /** WKWebView uses stk-preview://local/; WebView2 uses https://stk-preview.invalid/.
   * Both carry the exact session identity in the path and resolve the same manifest.
   * Returns empty for an unlisted/invalid path or a closed session.
   */
  std::string url(std::string_view asset_path, bool https = false) const;
  ResourceResponse read(std::string_view url, std::string_view method = "GET") const;
  bool allows_navigation(std::string_view url) const;
  void close();
  bool active() const;
  const PreviewIdentity &identity() const { return identity_; }

 private:
  PreviewIdentity identity_;
  std::map<std::string, ResourceAsset, std::less<>> assets_;
  std::atomic<bool> active_{true};
};

}  // namespace stk::document_preview
