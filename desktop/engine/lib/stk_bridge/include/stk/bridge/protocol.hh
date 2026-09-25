/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Wire level of the STK desktop bridge protocol v1 (docs/specs/stk-desktop-bridge-v1.md): the
 * closed error codes (§4), strict NDJSON framing (§2) and the retry class of each method (what the
 * client may repeat by itself after a bridge restart, §1 / §7 idempotency).
 */
#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <string>
#include <string_view>

#include "stk/io/json.hh"

namespace stk::bridge {

using Json = io::Json;

inline constexpr int kProtocolVersion = 1;
/** limits.max_line_bytes of protocol 1 (excluding the newline). */
inline constexpr size_t kDefaultMaxLineBytes = size_t(16) * 1024 * 1024;

/** The closed error codes of protocol 1 (§4); Unknown only for a code a newer bridge might add. */
enum class ErrorCode : uint8_t {
  ParseError,
  LineTooLong,
  InvalidRequest,
  UnknownMethod,
  InvalidParams,
  Unsupported,
  NotFound,
  Unauthorized,
  Unavailable,
  Conflict,
  ReviewNotInspected,
  RemoteError,
  ChecksumMismatch,
  GraphError,
  Cancelled,
  Timeout,
  Busy,
  ResultTooLarge,
  ShuttingDown,
  InternalError,
  Unknown,
};

/** "parse_error", ... ("unknown" for ErrorCode::Unknown). */
std::string_view error_code_name(ErrorCode code);
/** The code of a wire name; Unknown for anything else. */
ErrorCode error_code_from_name(std::string_view name);
/** The `retryable` default of a code (§4 table). */
bool error_code_retryable(ErrorCode code);

struct Error {
  ErrorCode code = ErrorCode::InternalError;
  /** The wire code ("unavailable"); keeps an unknown code's original text. */
  std::string name;
  std::string message;
  bool retryable = false;
  /** `error.data` (null when absent). */
  Json data;
  /** Produced by the client itself (no bridge response): timeouts, cancellation, restarts. */
  bool local = false;

  static Error make(ErrorCode code, std::string message, bool local = true, Json data = nullptr);
  /** From a response's `error` object (tolerant: missing keys get defaults). */
  static Error from_json(const Json &error);
  Json to_json() const;
  /** "unavailable: The bridge restarted ..." */
  std::string describe() const;
};

/** Thrown by Result::value() on an error result. */
class BridgeException : public std::runtime_error {
 public:
  explicit BridgeException(Error error);
  const Error &error() const
  {
    return error_;
  }

 private:
  Error error_;
};

/** A line the bridge sent that is not a protocol message (framing, UTF-8, JSON or envelope). */
class ProtocolError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

/**
 * Decodes one protocol line (without its '\n'; a final '\r' is dropped): strict UTF-8 and strict
 * JSON (RFC 8259, no NaN/Infinity, no duplicate keys) holding an object. Throws ProtocolError.
 */
Json decode_line(std::string_view line);

/**
 * One NDJSON line (ending in '\n') for `message`. Throws ProtocolError when the message holds
 * a non-finite number or a string that is not valid UTF-8 (protocol JSON is strict).
 */
std::string encode_line(const Json &message);

enum class MessageKind { Response, Event, Invalid };
/** Envelope class of a decoded bridge message (§3); `why` explains Invalid. */
MessageKind classify_message(const Json &message, std::string *why = nullptr);

/**
 * Splits a byte stream into lines of at most `max_line_bytes` bytes (excluding '\n'). An
 * oversized line is discarded up to its newline and reported once through `on_oversize` with its
 * length. Bytes after the last newline stay pending (a partial final line at EOF is not a
 * message: the bridge writes whole lines, so it was cut by a crash).
 */
class LineSplitter {
 public:
  explicit LineSplitter(size_t max_line_bytes = kDefaultMaxLineBytes) : max_(max_line_bytes) {}
  void set_max_line_bytes(size_t max_line_bytes)
  {
    max_ = max_line_bytes;
  }
  size_t max_line_bytes() const
  {
    return max_;
  }
  void feed(std::string_view data,
            const std::function<void(std::string_view line)> &on_line,
            const std::function<void(size_t length)> &on_oversize);
  /** Bytes of an unterminated line (or of a line being discarded). */
  size_t pending() const
  {
    return discarding_ ? discarded_ : buffer_.size();
  }
  void reset();

 private:
  std::string buffer_;
  size_t max_;
  bool discarding_ = false;
  size_t discarded_ = 0;
};

/**
 * Whether the client may send `method` again by itself after the bridge died with the request in
 * flight: reads, and creating operations whose idempotency key (or eval_id on a hub) makes a
 * repeat return the first result. Everything else fails with `unavailable` (see client.hh).
 */
bool method_is_retry_safe(std::string_view method, const Json &params);

/** Methods that start a subscription (watch, logs.subscribe, events.subscribe, hub.subscribe). */
bool method_is_subscribe(std::string_view method);

}  // namespace stk::bridge
