"""Categorical palettes and orientation colours (docs/specs/domain-classifiers.md §6). Standard library only.

Colours are display aids, never measurements. A field's ``categories[].color``
always wins over its palette; these functions provide the defaults.

* ``stk:categorical`` -- generic label fields: golden-angle hues (§6.5);
* ``stk:cubic-26-orientation`` -- numbering ``stk``: each variant coloured by
  its direction with ``stk:orientation-hsl`` at lightness range [0.2, 0.8] (§6.3);
* ``stk-legacy:ferro27`` -- numbering ``stk-legacy``: the 27-entry table STK
  already publishes under MIT (``toolkits/sviz/nt_vtk.py``, ``mupro_domain.json``),
  indexed by legacy label (§6.4). Its origin is an open owner question.
"""
import math

__all__ = [
    "CATEGORICAL", "CUBIC26_ORIENTATION", "FERRO27", "LEGACY_FERRO27", "PALETTES", "SUBSTRATE", "UNCLASSIFIED",
    "categorical_color", "cubic26_color", "ferro27_color", "hsl_to_rgb", "orientation_color", "palette_color",
    "to_hex", "to_rgb8",
]

CATEGORICAL = "stk:categorical"
CUBIC26_ORIENTATION = "stk:cubic-26-orientation"
LEGACY_FERRO27 = "stk-legacy:ferro27"
PALETTES = (CATEGORICAL, CUBIC26_ORIENTATION, LEGACY_FERRO27)

UNCLASSIFIED = (1.0, 1.0, 1.0)   # label -1 in every palette
SUBSTRATE = (0.75, 0.75, 0.75)   # label 0 in the STK palettes
GOLDEN_ANGLE = 137.50776405003785

# stk-legacy:ferro27 by legacy label 0..26 (label 0 = substrate); domain-classifiers.md §6.4.
FERRO27 = (
    (0.752912, 0.752912, 0.752912),
    (0.0, 0.0, 1.0),
    (0.46, 0.7175, 0.8135),
    (0.0, 0.153787, 0.0),
    (0.0, 1.0, 0.0),
    (1.0, 0.0, 0.0),
    (1.0, 0.566921, 0.633741),
    (1.0, 0.418685, 0.0),
    (1.0, 1.0, 0.0),
    (1.0, 0.0, 1.0),
    (0.64629, 0.130165, 0.130165),
    (0.9, 0.566921, 0.633741),
    (0.751111, 0.393695, 0.751111),
    (0.418685, 0.027128, 0.027128),
    (0.678201, 0.49827, 0.301423),
    (0.476371, 0.035432, 0.14173),
    (0.961169, 0.251965, 0.199862),
    (0.355309, 0.968874, 0.355309),
    (0.038446, 0.64629, 0.038446),
    (0.766921, 0.766921, 0.766921),
    (0.16955, 0.16955, 0.16955),
    (0.566921, 0.566921, 0.566921),
    (0.393695, 0.015747, 0.885813),
    (0.0, 0.0, 0.0),
    (1.0, 0.710881, 0.0),
    (0.885813, 0.813533, 0.301423),
    (0.8867188, 0.4335937, 0.0273438),
)


def hsl_to_rgb(h, s, l):  # noqa: E741 (the conventional name)
    """CSS Color 4 HSL -> RGB in [0, 1]: ``h`` in degrees, ``s`` and ``l`` in [0, 1] (§6.1)."""
    c = (1 - abs(2 * l - 1)) * s
    hp = (h % 360) / 60
    x = c * (1 - abs(hp % 2 - 1))
    sector = int(hp) % 6
    r1, g1, b1 = ((c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x))[sector]
    m = l - c / 2
    return (r1 + m, g1 + m, b1 + m)


def orientation_color(vector, max_magnitude=1.0, lightness_range=(0.0, 1.0)):
    """``stk:orientation-hsl`` of one vector (§6.2): hue = in-plane azimuth, saturation = |p| / M,
    lightness from p_z / |p|; grey when the vector is (nearly) along z or zero."""
    px, py, pz = (float(v) for v in vector)
    l0, l1 = (float(v) for v in lightness_range)
    big = float(max_magnitude)
    m = math.sqrt(px * px + py * py + pz * pz)
    if big <= 0 or m == 0:
        return hsl_to_rgb(0.0, 0.0, l0 + (l1 - l0) / 2)
    if math.hypot(px, py) < 1e-5 * big:
        return hsl_to_rgb(0.0, 0.0, l0 + (l1 - l0) * min(max((pz + big) / (2 * big), 0.0), 1.0))
    hue = math.degrees(math.atan2(py, px)) % 360
    return hsl_to_rgb(hue, min(m / big, 1.0), l0 + (l1 - l0) * (pz / m + 1) / 2)


def cubic26_color(direction):
    """``stk:cubic-26-orientation`` colour of a variant direction (compressed lightness [0.2, 0.8])."""
    return orientation_color(direction, 1.0, (0.2, 0.8))


def categorical_color(value):
    """``stk:categorical`` colour of a label value (§6.5)."""
    if value == -1:
        return UNCLASSIFIED
    if value == 0:
        return SUBSTRATE
    if value < -1:
        return (0.5, 0.5, 0.5)
    i = value - 1
    return hsl_to_rgb((i * GOLDEN_ANGLE) % 360, 0.65, (0.50, 0.38, 0.62)[i % 3])


def ferro27_color(label):
    """``stk-legacy:ferro27`` colour of a legacy label (-1 -> white, 0 -> substrate grey)."""
    if label == -1:
        return UNCLASSIFIED
    if not 0 <= label < len(FERRO27):
        raise ValueError(f"stk-legacy:ferro27 has no label {label}")
    return FERRO27[label]


def palette_color(palette, value, direction=None):
    """Default colour of ``value`` in ``palette``; ``stk:cubic-26-orientation`` variants need ``direction``."""
    if palette == CATEGORICAL:
        return categorical_color(value)
    if palette == LEGACY_FERRO27:
        return ferro27_color(value)
    if palette == CUBIC26_ORIENTATION:
        if value == -1:
            return UNCLASSIFIED
        if value == 0:
            return SUBSTRATE
        if direction is None:
            raise ValueError("stk:cubic-26-orientation colours need the variant direction")
        return cubic26_color(direction)
    raise ValueError(f"Unknown palette {palette!r}; known: {', '.join(PALETTES)}")


def to_rgb8(color):
    """8-bit RGB (``floor(255 c + 0.5)``, §6.1)."""
    return tuple(int(math.floor(255 * float(c) + 0.5)) for c in color[:3])


def to_hex(color):
    """``#rrggbb`` of an RGB(A) colour in [0, 1]; ``""`` for ``None``."""
    if color is None:
        return ""
    return "#" + "".join(f"{v:02x}" for v in to_rgb8(color))
