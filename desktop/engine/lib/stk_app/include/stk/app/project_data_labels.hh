/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace stk::app {
class AppStore;
class ProjectState;

/** Which parameter tables and file records of the open project are labelled public (project.labels.*, format 12;
 * docs/design/model-gateway.md), and from format 13 which tables only have their structure public (names, fields,
 * units and row counts; docs/design/agent-harness.md). Data is private unless labelled, and only public data may be
 * sent to external model endpoints. Read again after project.labels.changed or an own change; replies of a closed or
 * replaced project opening or bridge are ignored. Labelling never changes the project's revision. */
class ProjectDataLabels {
 public:
  explicit ProjectDataLabels(AppStore &store);
  ~ProjectDataLabels();
  ProjectDataLabels(const ProjectDataLabels &) = delete;
  ProjectDataLabels &operator=(const ProjectDataLabels &) = delete;

  void sync();
  /** The service labels data and the project is format 12 or later. */
  bool supported() const;
  bool loaded() const { return loaded_; }
  bool busy() const { return read_.has_value() || write_.has_value(); }
  /** The table's structure may be labelled public on its own (format 13). */
  bool structure_supported() const;
  bool is_public(const std::string &kind, const std::string &id) const;
  /** "public", "structure" or "private". */
  std::string label(const std::string &kind, const std::string &id) const;
  uint64_t version() const { return version_; }
  bool set(const std::string &kind, const std::vector<std::string> &ids, bool make_public);
  bool set(const std::string &kind, const std::vector<std::string> &ids, const std::string &label);

 private:
  void reset();
  bool read();

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  bridge::ListenerHandle listener_;
  std::string handle_, session_;
  uint64_t epoch_ = 0, version_ = 0;
  bool stale_ = true, loaded_ = false;
  std::map<std::string, std::map<std::string, std::string>> labels_;  // kind -> id -> public | structure
  std::optional<bridge::Future<io::Json>> read_, write_;
};
}  // namespace stk::app
