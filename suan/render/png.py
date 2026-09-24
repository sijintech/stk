"""Minimal PNG helpers (standard library; NumPy for :func:`decode_png`).

``png_size`` reads the IHDR of any PNG. ``decode_png`` handles what the
offscreen renderer and matplotlib write: 8-bit grey, grey+alpha, RGB and RGBA,
non-interlaced, all five scanline filters. It uses Pillow when importable
(fast) and otherwise a small pure-Python decoder, so tests and services can
compare images without extra dependencies.
"""
import io
import struct
import zlib

__all__ = ["PNG_SIGNATURE", "decode_png", "png_size"]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
_MODES = {"L": 1, "LA": 2, "RGB": 3, "RGBA": 4}


def _chunks(data):
    if data[:8] != PNG_SIGNATURE:
        raise ValueError("Not a PNG file")
    offset = 8
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, offset)
        yield kind, data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IEND":
            return


def png_size(data):
    """``(width, height)`` of PNG bytes."""
    for kind, body in _chunks(bytes(data[:64])):
        if kind == b"IHDR":
            return struct.unpack(">II", body[:8])
    raise ValueError("PNG has no IHDR chunk")


def decode_png(data):
    """``(height, width, channels)`` uint8 array of an 8-bit, non-interlaced PNG."""
    import numpy as np
    data = bytes(data)
    header, idat = None, []
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
    if header is None:
        raise ValueError("PNG has no IHDR chunk")
    width, height, depth, color_type, _, _, interlace = header
    if depth != 8 or color_type not in _CHANNELS or interlace:
        raise ValueError("Only 8-bit, non-interlaced grey/RGB(A) PNGs are supported")
    bpp = _CHANNELS[color_type]
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is not None:
        with Image.open(io.BytesIO(data)) as image:
            if image.mode in _MODES and _MODES[image.mode] == bpp:
                return np.asarray(image, dtype=np.uint8).reshape(height, width, bpp)
    stride = width * bpp
    raw = zlib.decompress(b"".join(idat))
    out = bytearray(height * stride)
    prior = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, row = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        if kind == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 255
        elif kind == 2:
            row = bytearray((a + b) & 255 for a, b in zip(row, prior))
        elif kind == 3:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prior[i]) >> 1)) & 255
        elif kind == 4:
            for i in range(stride):
                a = row[i - bpp] if i >= bpp else 0
                b = prior[i]
                c = prior[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        elif kind != 0:
            raise ValueError(f"Unknown PNG filter type {kind}")
        out[y * stride:(y + 1) * stride] = row
        prior = row
    return np.frombuffer(bytes(out), dtype=np.uint8).reshape(height, width, bpp)
