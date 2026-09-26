/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file STK shim: minimal ImBuf API used by GHOST (clipboard / drag & drop images).
 * Allocation is real; decoding/encoding goes through an optional codec hook
 * (#stk_imbuf_set_codec, e.g. from stk_io's PNG I/O) and otherwise reports "unsupported". */
#pragma once

#include <cstddef>

#include "BLI_vector.hh"

#include "IMB_imbuf_types.hh"

namespace blender {

ImBuf *IMB_allocImBuf(unsigned int x, unsigned int y, ImBufFlags flags);
ImBuf *IMB_allocFromBuffer(const uint8_t *byte_buffer,
                           const float *float_buffer,
                           unsigned int w,
                           unsigned int h,
                           unsigned int channels);
void IMB_freeImBuf(ImBuf *ibuf);
ImBuf *IMB_load_image_from_memory(const unsigned char *mem,
                                  size_t size,
                                  ImBufFlags flags,
                                  const char *descr,
                                  const char *filepath = nullptr,
                                  char *r_colorspace = nullptr);
ImBuf *IMB_load_image_from_filepath(const char *filepath,
                                    ImBufFlags flags,
                                    char *r_colorspace = nullptr);
Vector<uint8_t> IMB_save_image_to_buffer(ImBuf *ibuf, ImBufFlags flags);
bool IMB_test_image(const char *filepath);

/** STK extension: RGBA8 image codec callbacks. */
struct StkImbufCodec {
  /** Decode into a MEM-allocated RGBA8 buffer; false when unsupported. */
  bool (*decode)(const unsigned char *mem, size_t size, uint8_t **r_rgba, int *r_w, int *r_h);
  /** Encode RGBA8 pixels as PNG. */
  bool (*encode_png)(const uint8_t *rgba, int w, int h, Vector<uint8_t> &r_bytes);
};
void stk_imbuf_set_codec(const StkImbufCodec *codec);

}  // namespace blender
