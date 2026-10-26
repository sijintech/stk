/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

namespace stk::app {
class AppStore;
class ProjectState;
class ProjectScopeSubscription;

struct ReportPreviewIdentity {
  std::string project_id, report_id, source_sha256, session_id;
};
struct ReportPreviewAsset {
  std::string path, mime;
  std::vector<uint8_t> bytes;
};
struct PreparedReportPreview {
  ReportPreviewIdentity identity;
  std::string entry_path;
  // Sanitized HTML followed by verified raster images, or one unchanged PDF entry.
  std::vector<ReportPreviewAsset> assets;
  // Transient AppStore scope, never serialized or treated as a persistent report identity.
  uint64_t project_scope_epoch = 0;
};

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

  /** Whether the selected entry's MIME/budget and advertised bridge methods permit preview. */
  bool supports_preview() const;
  /** Explicit preparation. HTML verifies entry plus images; PDF verifies one unchanged entry.
   * No view/session is created and no partial assets escape. */
  bool prepare_preview();
  void clear_preview();
  bool preview_busy() const { return preview_busy_; }
  const std::string &preview_error() const { return preview_error_; }
  uint64_t preview_version() const { return preview_version_; }
  const std::optional<PreparedReportPreview> &prepared_preview() const { return prepared_preview_; }
  /** Transfer verified bytes to their native owner without copying the collection. */
  std::optional<PreparedReportPreview> take_prepared_preview();
  /** One tab-local native owner. Close its session synchronously when this reader changes
   * report or clears a preview. The handler must not throw or call back into this reader. */
  std::function<void()> on_preview_invalidated;

  bool load_page(int64_t offset = 0);
  /** An expected digest is used by workspace restoration; a changed version is not adopted. */
  bool load(const std::string &report_id, const std::string &expected_source_sha256 = {});
  bool select_asset(const std::string &path);
  bool read_asset();
  /** Explicit create-if-absent export. An uncertain reply is never replayed automatically. */
  bool export_file(const std::string &destination);
  void clear();

 private:
  struct PreviewPreparation;
  bool preview_call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done);
  void accept_preview(const io::Json &result);
  void accept_pdf_preview(const io::Json &result);
  void read_preview_resource();
  void fail_preview(const std::string &error);
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
  std::optional<bridge::Future<io::Json>> future_, preview_future_;
  std::unique_ptr<PreviewPreparation> preview_pending_;
  std::optional<PreparedReportPreview> prepared_preview_;
  std::string preview_error_;
  uint64_t preview_generation_ = 0, preview_request_ = 0, preview_version_ = 0;
  bool preview_busy_ = false;
  std::unique_ptr<ProjectScopeSubscription> scope_subscription_;
};
}  // namespace stk::app
