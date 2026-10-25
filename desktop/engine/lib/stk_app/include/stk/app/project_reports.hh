/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

namespace stk::app {
class AppStore;
class ProjectState;

/** Tab-local frozen report reader. Every response is bound to the bridge session, opened
 * project and revision. Asset bytes are retained only after their manifest hash is verified.
 * Reads never execute a document or change the shared Viewer/table selection. */
class ProjectReports {
 public:
  explicit ProjectReports(AppStore &store);
  ~ProjectReports();
  ProjectReports(const ProjectReports &) = delete;
  ProjectReports &operator=(const ProjectReports &) = delete;
  void sync();
  bool supported() const;
  bool supports(const std::string &method) const;
  bool busy() const { return busy_; }
  bool exporting() const { return exporting_; }
  uint64_t epoch() const { return epoch_; }
  uint64_t version() const { return version_; }
  const std::string &project_id() const { return project_id_; }
  const std::string &handle() const { return handle_; }
  int64_t revision() const { return revision_; }
  const std::string &error() const { return error_; }
  const std::string &notice() const { return notice_; }
  const io::Json &page() const { return page_; }
  const io::Json &selected() const { return selected_; }
  const io::Json &export_receipt() const { return export_receipt_; }
  const std::string &asset_path() const { return asset_path_; }
  const std::string &asset_mime() const { return asset_mime_; }
  const std::vector<uint8_t> &asset_bytes() const { return asset_bytes_; }
  bool asset_loaded() const { return asset_loaded_; }
  uint64_t asset_version() const { return asset_version_; }

  bool load_page(int64_t offset = 0);
  /** An expected digest is used by workspace restoration; a changed version is not adopted. */
  bool load(const std::string &report_id, const std::string &expected_source_sha256 = {});
  bool select_asset(const std::string &path);
  bool read_asset();
  /** Explicit create-if-absent export. An uncertain reply is never replayed automatically. */
  bool export_file(const std::string &destination);
  void clear();

 private:
  void reset();
  void clear_asset();
  void changed();
  bool call(const std::string &method, io::Json params,
            std::function<void(const io::Json &)> done, bool exporting = false);
  const io::Json *selected_asset() const;
  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string session_, project_id_, handle_, error_, notice_, asset_path_, asset_mime_;
  int64_t revision_ = -1;
  uint64_t epoch_ = 0, version_ = 0, asset_version_ = 0, request_ = 0;
  bool busy_ = false, exporting_ = false, asset_loaded_ = false;
  io::Json page_, selected_, export_receipt_;
  std::vector<uint8_t> asset_bytes_;
  std::optional<bridge::Future<io::Json>> future_;
};
}  // namespace stk::app
