/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file STK shim: the minimal #ImBuf subset GHOST uses for drag & drop and clipboard images.
 * Only the members GHOST touches exist (not layout compatible with imbuf). */
#pragma once

#include <cstdint>

namespace blender {

enum class ImBufFlags { Zero = 0, ByteData = 1 << 0, Test = 1 << 1, FloatData = 1 << 5, MultiLayer = 1 << 7 };
constexpr ImBufFlags operator|(ImBufFlags a, ImBufFlags b)
{
  return ImBufFlags(int(a) | int(b));
}
enum eImbFileType : int8_t { IMB_FTYPE_NONE = 0, IMB_FTYPE_PNG = 1 };

struct ImbFormatOptions {
  int16_t flag = 0;
  int8_t quality = 90;
};

struct ImBufByteBuffer {
  uint8_t *data = nullptr;
};

struct ImBuf {
  int x = 0, y = 0;
  eImbFileType ftype = IMB_FTYPE_NONE;
  ImbFormatOptions foptions;
  /** RGBA, 4 bytes per pixel. */
  ImBufByteBuffer byte_buffer;

  const uint8_t *byte_data() const
  {
    return byte_buffer.data;
  }
  uint8_t *byte_data_for_write()
  {
    return byte_buffer.data;
  }
};

}  // namespace blender
