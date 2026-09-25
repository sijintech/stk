/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Text measurement interface (implemented by BLF in ui_gpu, by a deterministic fake in tests),
 * CJK-aware line breaking, word navigation, ellipsis clipping and ANSI escape stripping.
 */
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace stk::ui {

enum class FontKind : uint8_t {
  Regular = 0, /**< UI font (Inter + Noto Sans CJK fallback stack). */
  Mono = 1,    /**< DejaVu Sans Mono (+ fallback), logs and code. */
};

struct FontStyle {
  FontKind kind = FontKind::Regular;
  float size_px = 11.0f;
  bool operator==(const FontStyle &o) const = default;
};

struct FontMetrics {
  float ascent = 0.0f;  /**< Above the baseline, positive. */
  float descent = 0.0f; /**< Below the baseline, positive. */
  float line_height() const { return ascent + descent; }
};

/** Measures UTF-8 text. Implementations must be deterministic for a given style. */
class TextMeasurer {
 public:
  virtual ~TextMeasurer() = default;
  virtual float width(std::string_view text, const FontStyle &style) const = 0;
  virtual FontMetrics metrics(const FontStyle &style) const = 0;

  /** X offset of the caret before byte `index`. */
  float caret_x(std::string_view text, size_t index, const FontStyle &style) const;
  /** Nearest codepoint boundary to x (relative to the text start). */
  size_t index_at_x(std::string_view text, float x, const FontStyle &style) const;
};

/**
 * Deterministic fake for tests and goldens: ASCII advances 0.5 em (0.6 em mono), wide (CJK)
 * characters 1 em, other characters 0.6 em; ascent 0.8 em, descent 0.2 em.
 */
class FakeTextMeasurer final : public TextMeasurer {
 public:
  float width(std::string_view text, const FontStyle &style) const override;
  FontMetrics metrics(const FontStyle &style) const override;
  static float advance(uint32_t cp, const FontStyle &style);
};

/** One wrapped line: bytes [begin, end) of the source, trailing spaces and newline excluded. */
struct TextLine {
  size_t begin = 0;
  size_t end = 0;
  float width = 0.0f;
};

/**
 * Greedy line breaking with CJK rules: break at spaces, between CJK characters and at CJK/Latin
 * boundaries; Latin words stay together (split by character only when longer than a line);
 * kinsoku: closing punctuation (。，、！？）」 …) never starts a line, opening brackets never end
 * one. '\n' forces a break. max_width <= 0 means no wrapping.
 */
std::vector<TextLine> break_lines(std::string_view text,
                                  float max_width,
                                  const TextMeasurer &measurer,
                                  const FontStyle &style);

/** Byte offsets where a line may break before (sorted, excludes 0 and size). */
std::vector<size_t> break_opportunities(std::string_view text);

/**
 * Word navigation (Ctrl+Left/Right): words are runs of the same class — Latin letters/digits,
 * Han ideographs, kana, hangul, punctuation — separated by spaces.
 */
size_t next_word_boundary(std::string_view text, size_t pos);
size_t prev_word_boundary(std::string_view text, size_t pos);
/** The word (same-class run) around `pos`, for double-click selection. */
void word_at(std::string_view text, size_t pos, size_t *r_begin, size_t *r_end);

/** Returns `text` cut to fit `max_width`, with "…" appended when cut. */
std::string clip_text(std::string_view text,
                      float max_width,
                      const TextMeasurer &measurer,
                      const FontStyle &style);

/**
 * Removes ANSI/VT escape sequences (CSI, OSC, two-byte ESC sequences) incrementally, so a
 * sequence split across chunks is still removed.
 */
class AnsiStripper {
 public:
  std::string feed(std::string_view chunk);
  void reset() { state_ = State::Text; }

 private:
  enum class State : uint8_t { Text, Esc, Csi, Osc, OscEsc, Charset };
  State state_ = State::Text;
};

std::string strip_ansi(std::string_view s);

}  // namespace stk::ui
