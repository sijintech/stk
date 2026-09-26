/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Validation of bridge messages against desktop-bridge-1.schema.json (debug / CI aid).
 *
 * The schema uses the JSON Schema subset of stk::io::check_value plus local `$ref`
 * ("#/$defs/..."), which stk_io does not resolve: references are inlined here first, exactly as
 * suan.desktop_bridge.schema does ({"$ref": r, ...rest} -> {"allOf": [target, rest]}).
 */
#pragma once

#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

#include "stk/bridge/protocol.hh"
#include "stk/io/schema.hh"

namespace stk::bridge {

/** Inlines every local `$ref` of `node` against `document` (drops $defs/$schema/$id). Throws
 * std::runtime_error for a non-local, unresolvable or recursive reference. */
Json inline_schema_refs(const Json &node, const Json &document);

class ProtocolSchema {
 public:
  /** The copy of suan/contracts/schemas/desktop-bridge-1.schema.json built into the library. */
  static const ProtocolSchema &embedded();
  explicit ProtocolSchema(Json document);

  const Json &document() const
  {
    return document_;
  }
  std::vector<std::string> method_names() const;
  std::vector<std::string> event_names() const;
  bool has_method(std::string_view method) const;
  bool has_event(std::string_view event) const;

  /** A request the client sends: the envelope, then its method's params. */
  std::vector<io::SchemaIssue> check_request(const Json &message) const;
  /** A response: the envelope, then the result of `method` (skipped when unknown / empty). */
  std::vector<io::SchemaIssue> check_response(const Json &message, std::string_view method) const;
  /** An event: the envelope, then its data (an unknown event name is an issue). */
  std::vector<io::SchemaIssue> check_event(const Json &message) const;

  /** The fully inlined schema at a local reference ("#/$defs/request"); cached. */
  const Json &resolved(const std::string &ref) const;

 private:
  Json document_;
  mutable std::mutex mutex_;
  mutable std::map<std::string, std::unique_ptr<Json>> cache_;
};

}  // namespace stk::bridge
