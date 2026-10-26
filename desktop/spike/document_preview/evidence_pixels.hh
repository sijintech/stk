/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/png.hh"
#include <array>
#include <cstdint>
namespace stk::document_preview {
// These six colors are only emitted by the HTML fixture, never by the STK GPU host.
inline constexpr std::array<std::array<uint8_t, 3>, 6> kEvidenceColors = {{
    {26, 78, 210}, {230, 118, 24}, {30, 174, 74},
    {154, 42, 190}, {24, 186, 202}, {218, 38, 58}}};
// Require a spatially contiguous six-color stripe, repeated on >=8 consecutive rows.
// page=1 normal order, page=2 reverse order. No rendering/GPU/OS dependencies.
bool evidence_marker(const io::Image &image, int page);
// Recognize this separate, neutral high-contrast U+2588/space text in a <pre>:
//   2 blocks, 2 spaces, 4 blocks, 2 spaces, 3 blocks, 2 spaces, 5 blocks
//   5 blocks, 2 spaces, 2 blocks, 2 spaces, 4 blocks, 2 spaces, 3 blocks
//   3 blocks, 2 spaces, 5 blocks, 2 spaces, 2 blocks, 2 spaces, 4 blocks
// Requires all three aligned 20-column rows, consistent cell/line geometry and
// contrasting background. Supports light/dark pages and fractional pixel cells.
// This is a fixture pixel predicate, not OCR or proof of arbitrary document text.
bool evidence_text_marker(const io::Image &image);
}  // namespace stk::document_preview
