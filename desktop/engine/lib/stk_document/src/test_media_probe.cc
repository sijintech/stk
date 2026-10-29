/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/document/test_media_probe.hh"

#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES

#include "stk/io/json.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace stk::document_preview::test {
namespace {
constexpr std::array<std::string_view, 17> kFields = {
    "paused", "ended", "seeking", "duration_known", "current_time", "duration",
    "rect_x", "rect_y", "rect_width", "rect_height", "viewport_width", "viewport_height",
    "ready_state", "network_state", "error_code", "video_width", "video_height"};
struct InvalidSnapshot {};
}  // namespace

bool parse_media_snapshot(std::string_view json, MediaSnapshot &media, std::string &error)
{
  error.clear();
  if (json.empty() || json.size() > 4096 || json.starts_with("\xef\xbb\xbf")) {
    error = "Media probe JSON must be nonempty UTF-8 without a BOM and at most 4096 bytes";
    return false;
  }
  try {
    uint32_t seen = 0;
    // Reject duplicate/unknown keys before the DOM parser could replace a value.
    // Nested objects and all arrays are outside this flat, exact probe contract.
    const auto callback = [&](int depth, io::Json::parse_event_t event, io::Json &value) {
      if (event == io::Json::parse_event_t::array_start ||
          (event == io::Json::parse_event_t::object_start && depth != 0)) { throw InvalidSnapshot{}; }
      if (event == io::Json::parse_event_t::key) {
        if (depth != 1 || !value.is_string()) { throw InvalidSnapshot{}; }
        const auto &key = value.get_ref<const std::string &>();
        const auto found = std::find(kFields.begin(), kFields.end(), key);
        if (found == kFields.end()) { throw InvalidSnapshot{}; }
        const uint32_t bit = uint32_t(1) << size_t(found - kFields.begin());
        if (seen & bit) { throw InvalidSnapshot{}; }
        seen |= bit;
      }
      return true;
    };
    const auto value = io::Json::parse(json.begin(), json.end(), callback);
    if (!value.is_object() || value.size() != kFields.size() ||
        seen != (uint32_t(1) << kFields.size()) - 1) { throw InvalidSnapshot{}; }
    const auto boolean = [&](const char *field) {
      const auto &item = value.at(field);
      if (!item.is_boolean()) { throw InvalidSnapshot{}; }
      return item.get<bool>();
    };
    const auto number = [&](const char *field, bool nonnegative = true) {
      const auto &item = value.at(field);
      if (!item.is_number()) { throw InvalidSnapshot{}; }
      const double result = item.get<double>();
      if (!std::isfinite(result) || (nonnegative && result < 0)) { throw InvalidSnapshot{}; }
      return result;
    };
    const auto integer = [&](const char *field, int maximum) {
      const auto &item = value.at(field);
      if (item.is_number_unsigned()) {
        const auto result = item.get<uint64_t>();
        if (result > uint64_t(maximum)) { throw InvalidSnapshot{}; }
        return int(result);
      }
      if (!item.is_number_integer()) { throw InvalidSnapshot{}; }
      const auto result = item.get<int64_t>();
      if (result < 0 || result > maximum) { throw InvalidSnapshot{}; }
      return int(result);
    };
    MediaSnapshot parsed;
    parsed.paused = boolean("paused");
    parsed.ended = boolean("ended");
    parsed.seeking = boolean("seeking");
    parsed.duration_known = boolean("duration_known");
    parsed.current_time = number("current_time");
    parsed.duration = number("duration");
    if (!parsed.duration_known && parsed.duration != 0) { throw InvalidSnapshot{}; }
    parsed.rect_x = number("rect_x", false);
    parsed.rect_y = number("rect_y", false);
    parsed.rect_width = number("rect_width");
    parsed.rect_height = number("rect_height");
    parsed.viewport_width = number("viewport_width");
    parsed.viewport_height = number("viewport_height");
    parsed.ready_state = integer("ready_state", 4);
    parsed.network_state = integer("network_state", 3);
    parsed.error_code = integer("error_code", 4);
    parsed.video_width = integer("video_width", std::numeric_limits<int>::max());
    parsed.video_height = integer("video_height", std::numeric_limits<int>::max());
    parsed.navigation_generation = media.navigation_generation;
    media = parsed;
    return true;
  }
  catch (...) {
    // Never put DOM values, document text or JSON parser excerpts in native logs.
    error = "Media probe JSON must contain exactly the typed, finite snapshot fields and valid ranges";
    return false;
  }
}

}  // namespace stk::document_preview::test

#endif  // STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
