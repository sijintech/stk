/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/app_store.hh"
#include "stk/bridge/client.hh"
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace stk::app {

/** One desktop local literature controller. A Library is not an opened project.
 * Construction, sync, detach and restoration never dispatch or resume work. */
class LiteratureState {
 public:
  struct Pending;
  struct Binding {
    std::string database_id;
    int64_t generation = -1;
    bool operator==(const Binding &) const = default;
  };
  struct Expected {
    std::string action, request_sha256, bridge_session, encoder_fingerprint;
    io::Json request;
    std::map<std::string, Binding> corpora;
    uint64_t bridge_epoch = 0, lifetime_epoch = 0, corpus_epoch = 0, scope_epoch = 0, import_epoch = 0,
             query_epoch = 0, encoder_draft_epoch = 0, page_epoch = 0, encoder_epoch = 0;
  };
  struct View {
    ~View();
    std::string corpus, version_id, operation_id, error;
    std::vector<std::string> scopes;
    io::Json operation, citation, historical_result;
    std::map<std::string, io::Json> values;
    std::map<std::string, Expected> originals;
    uint64_t lifetime_epoch = 0, corpus_epoch = 0, scope_epoch = 0, import_epoch = 0,
             query_epoch = 0, encoder_draft_epoch = 0, page_epoch = 0, version = 0;
    double follow_until = 0, next_poll = 0, started = 0;
    bool uncertain = false;
    /** Synchronous: release page bytes/textures; must not call RPC or throw. */
    std::function<void()> on_content_invalidated;
    bool busy() const { return pending.contains("write"); }
    bool reading() const { return !pending.empty(); }
    bool working() const;
   private:
    friend class LiteratureState;
    std::map<std::string, std::shared_ptr<Pending>> pending;
    std::map<std::string, std::string> latest_operations;
  };
  using ViewPtr = std::shared_ptr<View>;
  explicit LiteratureState(AppStore &);
  ~LiteratureState();
  ViewPtr new_view();
  void sync(const ViewPtr &);
  bool supported() const;
  void detach(const ViewPtr &);
  bool set_corpus(const ViewPtr &, const std::string &);
  bool set_scopes(const ViewPtr &, std::vector<std::string>);
  bool set_version(const ViewPtr &, const std::string &);
  bool set_citation(const ViewPtr &, const io::Json &);
  void invalidate_import_draft(const ViewPtr &);
  void invalidate_query_draft(const ViewPtr &);
  void invalidate_encoder_draft(const ViewPtr &);
  /** Only the six passive metadata methods. Operations use dedicated identity-bound methods below. */
  bool read(const ViewPtr &, const std::string &action, io::Json params = io::Json::object());
  /** Exactly the twelve published actions; host interpreter selection is never a form parameter. */
  bool act(const ViewPtr &, const std::string &action, io::Json params);
  bool select_operation(const ViewPtr &, const io::Json &);
  /** Explicitly follows this original identity for at most 90 seconds; never reissues its action. */
  bool check_operation(const ViewPtr &);
  /** Explicit historical read never turns an old review into a current form's authority. */
  bool load_result(const ViewPtr &);
  /** Follows only an explicit action begun here, never a restored or selected historical operation. */
  void pump(const ViewPtr &);
  const io::Json *corpus_info(const std::string &) const;
  const io::Json &encoder_info() const { return encoder_; }
  static std::string new_uuid();
  static std::string checksum(const io::Json &);
  static std::string request_sha256(const std::string &, const io::Json &);
  static bool operation_matches(const io::Json &, const std::string &, const Expected * = nullptr);
  static bool corpus_id(const std::string &);

 private:
  using Apply = std::function<void(const ViewPtr &, const io::Json &)>;
  void follow_bridge();
  void clear_page(View &);
  void clear_content(View &);
  void invalidate_corpus(const std::string &);
  void observe_corpus(const io::Json &);
  void observe_encoder(const io::Json &);
  bool current(const View &, const Expected &) const;
  bool prepare(const View &, Expected &) const;
  bool result_matches(const Expected &, const io::Json &) const;
  bool call(const ViewPtr &, const std::string &slot, const std::string &action, io::Json, Apply,
            const Expected * = nullptr);
  void accept_operation(const ViewPtr &, const io::Json &);
  bool fetch_result(const ViewPtr &, bool explicit_read);
  void accept_result(const ViewPtr &, const Expected &, const io::Json &);
  AppStore &store_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  ProjectScopeSubscription scope_observer_;
  bridge::ListenerHandle state_listener_;
  bridge::Client *client_ = nullptr;
  std::string session_;
  uint64_t epoch_ = 0, bridge_epoch_ = 0, encoder_epoch_ = 0;
  std::map<std::string, io::Json> corpora_;
  io::Json encoder_;
  std::vector<std::weak_ptr<View>> views_;
};
}  // namespace stk::app
