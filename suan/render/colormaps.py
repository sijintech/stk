"""Colour maps for STK render payloads (docs/specs/stk-render-payload-v2.md §5, domain-classifiers.md §6).

Continuous colormaps travel as 256-entry RGBA8 lookup tables so that the web
viewer, the offscreen VTK renderer and Blender produce identical colours.
Built-ins: ``viridis``, ``cividis``, ``coolwarm``, ``turbo`` and ``gray``
(alias ``grey``). ``stk:orientation-hsl`` is the only *function* colormap: it
colours vectors by direction. Categorical palettes (``stk:categorical``,
``stk:cubic-26-orientation``) come from the categories of label fields; a
category's own ``color`` always wins.

LUT data: viridis and cividis are CC0 (van der Walt, Smith and Nuñez et al.);
coolwarm is Kenneth Moreland's diverging map; turbo is (c) Google LLC,
Apache-2.0. The tables were sampled once from matplotlib's 256-entry maps and
rounded to 8 bits (``floor(255 * c + 0.5)``); ``gray`` is ``k -> (k, k, k)``.

The scalar mapping (spec §5): ``t = (v - lo) / (hi - lo)`` (0.5 when
``hi == lo``), entry ``min(255, floor(256 * t))`` for ``0 <= t <= 1``; below
and above the range use ``below_color``/``above_color`` or the end entries;
NaN uses ``nan_color`` (default mid grey). Everything except the vectorized
helpers is standard-library only; NumPy is imported lazily.
"""
import math

__all__ = [
    "ALIASES", "BUILTIN", "CATEGORICAL_OPACITY", "CATEGORICAL_PALETTES", "DEFAULT_NAN_COLOR", "DEFAULT_OPACITY",
    "DEFAULT_UNKNOWN_COLOR", "ORIENTATION_HSL", "canonical_name", "categorical_opacity", "category_color",
    "colormap_names", "hsl_to_rgb", "is_builtin", "lut_colors", "lut_index", "lut_rgba8", "lut_rgba8_bytes",
    "map_categories", "map_scalars", "opacity_at", "opacity_lut", "opacity_points", "orientation_hsl",
    "orientation_rgb", "palette_entries", "rgba8", "stk_categorical_color", "to_hex", "transfer_function",
    "transfer_function_rgba8", "volume_color_points",
]

BUILTIN = ("viridis", "cividis", "coolwarm", "turbo", "gray")
ALIASES = {"grey": "gray", "greys": "gray", "grays": "gray"}
ORIENTATION_HSL = "stk:orientation-hsl"
CATEGORICAL_PALETTES = ("stk:categorical", "stk:cubic-26-orientation", "stk-legacy:ferro27")
DEFAULT_NAN_COLOR = (0.5, 0.5, 0.5, 1.0)
DEFAULT_UNKNOWN_COLOR = (0.5, 0.5, 0.5)
RESERVED_COLORS = {-1: (1.0, 1.0, 1.0), 0: (0.75, 0.75, 0.75)}
CUBIC26_LIGHTNESS = (0.2, 0.8)
GOLDEN_ANGLE = 137.50776405003785

# 256 RGB8 entries per map, as hex (768 bytes each).
_LUT_HEX = {
    "viridis": (
        "44015444025645045745055946075a46085c460a5d460b5e470d60470e61471063471164471365481467481668481769"
        "48186a481a6c481b6d481c6e481d6f481f70482071482173482374482475482576482677482878482979472a7a472c7a"
        "472d7b472e7c472f7d46307e46327e46337f463480453581453781453882443983443a83443b84433d84433e85423f85"
        "4240864241864142874144874045884046883f47883f48893e49893e4a893e4c8a3d4d8a3d4e8a3c4f8a3c508b3b518b"
        "3b528b3a538b3a548c39558c39568c38588c38598c375a8c375b8d365c8d365d8d355e8d355f8d34608d34618d33628d"
        "33638d32648e32658e31668e31678e31688e30698e306a8e2f6b8e2f6c8e2e6d8e2e6e8e2e6f8e2d708e2d718e2c718e"
        "2c728e2c738e2b748e2b758e2a768e2a778e2a788e29798e297a8e297b8e287c8e287d8e277e8e277f8e27808e26818e"
        "26828e26828e25838e25848e25858e24868e24878e23888e23898e238a8d228b8d228c8d228d8d218e8d218f8d21908d"
        "21918c20928c20928c20938c1f948c1f958b1f968b1f978b1f988b1f998a1f9a8a1e9b8a1e9c891e9d891f9e891f9f88"
        "1fa0881fa1881fa1871fa28720a38620a48621a58521a68522a78522a88423a98324aa8325ab8225ac8226ad8127ad81"
        "28ae8029af7f2ab07f2cb17e2db27d2eb37c2fb47c31b57b32b67a34b67935b77937b87838b9773aba763bbb753dbc74"
        "3fbc7340bd7242be7144bf7046c06f48c16e4ac16d4cc26c4ec36b50c46a52c56954c56856c66758c7655ac8645cc863"
        "5ec96260ca6063cb5f65cb5e67cc5c69cd5b6ccd5a6ece5870cf5773d05675d05477d1537ad1517cd2507fd34e81d34d"
        "84d44b86d54989d5488bd6468ed64590d74393d74195d84098d83e9bd93c9dd93ba0da39a2da37a5db36a8db34aadc32"
        "addc30b0dd2fb2dd2db5de2bb8de29bade28bddf26c0df25c2df23c5e021c8e020cae11fcde11dd0e11cd2e21bd5e21a"
        "d8e219dae319dde318dfe318e2e418e5e419e7e419eae51aece51befe51cf1e51df4e61ef6e620f8e621fbe723fde725"
    ),
    "cividis": (
        "00224e00234f00245100255300255400265600275800285900285b00295d002a5f002a61002b62002c64002c66002d68"
        "002e6a002e6c002f6d00306f0030700031700031710132710533710833700c34700f357012357014367016377018376f"
        "1a386f1c396f1e3a6f203a6f213b6e233c6e243c6e263d6e273e6e293f6e2a3f6d2b406d2d416d2e416d2f426d31436d"
        "32436d33446d34456c35456c36466c38476c39486c3a486c3b496c3c4a6c3d4a6c3e4b6c3f4c6c404c6c414d6c424e6c"
        "434e6c444f6c45506c46516c47516c48526c49536c4a536c4b546c4c556c4d556c4e566c4f576c50576c51586d52596d"
        "535a6d545a6d555b6d555c6d565c6d575d6d585e6d595e6e5a5f6e5b606e5c616e5d616e5e626e5e636f5f636f60646f"
        "61656f62656f636670646770656870656870666970676a71686a71696b716a6c716b6d726c6d726c6e726d6f726e6f73"
        "6f70737071737172747272747273747374757474757575757676767777767777777878777979777a7a787b7a787c7b78"
        "7d7c787e7c787e7d787f7e78807f78817f788280798381798482798582798683798784788885788985788a86788b8778"
        "8c88788d88788e89788f8a78908b78918b78928c78928d78938e78948e77958f779690779791779892779992779a9376"
        "9b94769c95769d95769e96769f9775a09875a19975a29975a39a74a49b74a59c74a69c74a79d73a89e73a99f73aaa073"
        "aba072aca172ada272aea371afa471b0a571b1a570b3a670b4a76fb5a86fb6a96fb7a96eb8aa6eb9ab6dbaac6dbbad6d"
        "bcae6cbdae6cbeaf6bbfb06bc0b16ac1b26ac2b369c3b369c4b468c5b568c6b667c7b767c8b866c9b965cbb965ccba64"
        "cdbb63cebc63cfbd62d0be62d1bf61d2c060d3c05fd4c15fd5c25ed6c35dd7c45cd9c55cdac65bdbc75adcc859ddc858"
        "dec958dfca57e0cb56e1cc55e2cd54e4ce53e5cf52e6d051e7d150e8d24fe9d34eead34cebd44bedd54aeed649efd748"
        "f0d846f1d945f2da44f3db42f5dc41f6dd3ff7de3ef8df3cf9e03afbe138fce236fde334fee434fee535fee636fee838"
    ),
    "coolwarm": (
        "3b4cc03c4ec23d50c33e51c53f53c64055c84257c94358cb445acc455cce465ecf485fd14961d24a63d34b64d54c66d6"
        "4e68d84f69d9506bda516ddb536edd5470de5572df5673e05875e15977e35a78e45b7ae55d7ce65e7de75f7fe86180e9"
        "6282ea6384eb6485ec6687ed6788ee688aef6a8bef6b8df06c8ff16e90f26f92f37093f37295f47396f57597f67699f6"
        "779af7799cf87a9df87b9ff97da0f97ea1fa80a3fa81a4fb82a6fb84a7fc85a8fc86a9fc88abfd89acfd8badfd8caffe"
        "8db0fe8fb1fe90b2fe92b4fe93b5fe94b6ff96b7ff97b8ff98b9ff9abbff9bbcff9dbdff9ebeff9fbfffa1c0ffa2c1ff"
        "a3c2fea5c3fea6c4fea7c5fea9c6fdaac7fdabc8fdadc9fdaec9fcafcafcb1cbfcb2ccfbb3cdfbb5cdfab6cefab7cff9"
        "b9d0f9bad0f8bbd1f8bcd2f7bed2f6bfd3f6c0d4f5c1d4f4c3d5f4c4d5f3c5d6f2c6d6f1c7d7f0c9d7f0cad8efcbd8ee"
        "ccd9edcdd9eccedaebcfdaead1dae9d2dbe8d3dbe7d4dbe6d5dbe5d6dce4d7dce3d8dce2d9dce1dadce0dbdcdedcdddd"
        "dddcdcdedcdbdfdbd9e0dbd8e1dad6e2dad5e3d9d3e4d9d2e5d8d1e6d7cfe7d7cee8d6cce9d5cbead5c9ead4c8ebd3c6"
        "ecd3c5edd2c3edd1c2eed0c0efcfbfefcebdf0cdbbf1cdbaf1ccb8f2cbb7f2cab5f2c9b4f3c8b2f3c7b1f4c6aff4c5ad"
        "f5c4acf5c2aaf5c1a9f5c0a7f6bfa6f6bea4f6bda2f7bca1f7ba9ff7b99ef7b89cf7b79bf7b599f7b497f7b396f7b194"
        "f7b093f7af91f7ad90f7ac8ef7aa8cf7a98bf7a889f7a688f6a586f6a385f6a283f5a081f59f80f59d7ef59c7df49a7b"
        "f4987af39778f39577f39475f29274f29072f18f71f18d6ff08b6ef08a6cef886bee8669ee8468ed8366ec8165ec7f63"
        "eb7d62ea7b60e97a5fe9785de8765ce7745be67259e57058e46e56e36c55e36b54e26952e16751e0654fdf634ede614d"
        "dd5f4bdc5d4ada5a49d95847d85646d75445d65244d55042d44e41d24b40d1493fd0473dcf453ccd423bcc403acb3e38"
        "ca3b37c83836c73635c53334c43032c32e31c12b30c0282fbe242ebd1f2dbb1b2cba162bb8122ab70d28b50927b40426"
    ),
    "turbo": (
        "30123b32154333184a341b51351e5836215f37246638276d392a733a2d793b2f803c32863d358b3e38913f3b973f3e9c"
        "4040a24143a74146ac4249b1424bb5434eba4451bf4454c34456c74559cb455ccf455ed34661d64664da4666dd4669e0"
        "466be3476ee64771e94773eb4776ee4778f0477bf2467df44680f64682f84685fa4687fb458afc458cfd448ffe4391fe"
        "4294ff4196ff4099ff3e9bfe3d9efe3ba0fd3aa3fc38a5fb37a8fa35abf833adf731aff52fb2f42eb4f22cb7f02ab9ee"
        "28bceb27bee925c0e723c3e422c5e220c7df1fc9dd1ecbda1ccdd81bd0d51ad2d21ad4d019d5cd18d7ca18d9c818dbc5"
        "18ddc218dec018e0bd19e2bb19e3b91ae4b61ce6b41de7b21fe9af20eaac22ebaa25eca727eea42aefa12cf09e2ff19b"
        "32f29835f39438f4913cf58e3ff68a43f78746f8844af8804ef97d52fa7a55fa7659fb735dfc6f61fc6c65fd6969fd66"
        "6dfe6271fe5f75fe5c79fe597dff5680ff5384ff5188ff4e8bff4b8fff4992ff4796fe4499fe429cfe409ffd3fa1fd3d"
        "a4fc3ca7fc3aa9fb39acfb38affa37b1f936b4f836b7f735b9f635bcf534bef434c1f334c3f134c6f034c8ef34cbed34"
        "cdec34d0ea34d2e935d4e735d7e535d9e436dbe236dde037dfdf37e1dd37e3db38e5d938e7d739e9d539ebd339ecd13a"
        "eecf3aefcd3af1cb3af2c93af4c73af5c53af6c33af7c13af8be39f9bc39faba39fbb838fbb637fcb336fcb136fdae35"
        "fdac34fea933fea732fea431fea130fe9e2ffe9b2dfe992cfe962bfe932afe9029fd8d27fd8a26fc8725fc8423fb8122"
        "fb7e21fa7b1ff9781ef9751df8721cf76f1af66c19f56918f46617f36315f26014f15d13f05b12ef5811ed5510ec530f"
        "eb500eea4e0de84b0ce7490ce5470be4450ae2430ae14109df3f08dd3d08dc3b07da3907d83706d63506d43305d23105"
        "d02f05ce2d04cc2b04ca2a04c82803c52603c32503c12302be2102bc2002b91e02b71d02b41b01b21a01af1801ac1701"
        "a91601a71401a41301a112019e10019b0f01980e01950d01920b018e0a018b09028808028507028106027e05027a0403"
    ),
}


def _np():
    import numpy
    return numpy


def colormap_names():
    """Built-in continuous colormap names (payload ``colormaps[].name``)."""
    return BUILTIN


def canonical_name(name):
    """``"grey"`` -> ``"gray"``; raises ``KeyError`` for unknown continuous colormaps."""
    if not isinstance(name, str):
        raise KeyError(f"Colormap name must be a string, got {name!r}")
    key = ALIASES.get(name.lower(), name.lower())
    if key not in BUILTIN:
        raise KeyError(f"Unknown colormap {name!r}; built-in: {', '.join(BUILTIN)}")
    return key


def is_builtin(name):
    try:
        canonical_name(name)
    except KeyError:
        return False
    return True


def lut_rgba8_bytes(name):
    """The 256 x RGBA8 lookup table of a built-in colormap as 1024 bytes (alpha 255)."""
    key = canonical_name(name)
    if key == "gray":
        rgb = bytes(v for k in range(256) for v in (k, k, k))
    else:
        rgb = bytes.fromhex("".join(_LUT_HEX[key]))
    return b"".join(rgb[3 * k:3 * k + 3] + b"\xff" for k in range(256))


def lut_colors(name):
    """256 ``(r, g, b, a)`` float tuples (byte / 255)."""
    data = lut_rgba8_bytes(name)
    return [tuple(data[4 * k + c] / 255 for c in range(4)) for k in range(256)]


def lut_rgba8(name):
    """``(256, 4)`` uint8 array of a built-in colormap."""
    np = _np()
    return np.frombuffer(lut_rgba8_bytes(name), dtype=np.uint8).reshape(256, 4).copy()


def rgba8(color):
    """Float RGB(A) in [0, 1] -> RGBA8 tuple (``floor(255 * c + 0.5)``, alpha 255 when absent)."""
    values = [float(c) for c in color]
    if len(values) == 3:
        values.append(1.0)
    return tuple(int(math.floor(255 * min(max(c, 0.0), 1.0) + 0.5)) for c in values)


def to_hex(color):
    """``'#rrggbb'`` of a float RGB(A) colour."""
    r, g, b, _ = rgba8(color)
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# Scalar mapping


def lut_index(values, value_range):
    """LUT entry per value: 0..255 inside the range, -1 below, 256 above, -2 for NaN (NumPy array)."""
    np = _np()
    values = np.asarray(values, dtype=np.float64)
    lo, hi = float(value_range[0]), float(value_range[1])
    with np.errstate(invalid="ignore", divide="ignore"):
        t = np.full(values.shape, 0.5) if hi == lo else (values - lo) / (hi - lo)
        t = np.where(np.isnan(values), np.nan, t)
        index = np.floor(np.nan_to_num(t, nan=0.0, posinf=2.0, neginf=-1.0) * 256)
    index = np.minimum(index, 255).astype(np.int64)
    index = np.where(t < 0, -1, np.where(t > 1, 256, index))
    return np.where(np.isnan(t), -2, index)


def map_scalars(values, lut, value_range, *, nan_color=None, below_color=None, above_color=None):
    """Float RGBA ``(n, 4)`` of scalar values through a ``(256, 4)`` uint8 LUT (spec §5)."""
    np = _np()
    lut = np.asarray(lut)
    if lut.shape != (256, 4):
        raise ValueError("A lookup table must be 256 x RGBA8")
    table = np.concatenate([lut.astype(np.float64) / 255.0,
                            [_rgba(below_color, lut[0]), _rgba(above_color, lut[255]),
                             _rgba(nan_color, None, DEFAULT_NAN_COLOR)]])
    index = lut_index(values, value_range).ravel()
    index = np.where(index == -1, 256, np.where(index == 256, 257, np.where(index == -2, 258, index)))
    return table[index]


def _rgba(color, lut_entry, default=None):
    np = _np()
    if color is None:
        return (np.asarray(lut_entry, dtype=np.float64) / 255.0) if lut_entry is not None else list(default)
    color = [float(c) for c in color]
    return color + [1.0] if len(color) == 3 else color


def map_categories(values, entries, *, unknown_color=None):
    """Float RGBA ``(n, 4)`` for integer label values by exact match with palette ``entries``."""
    np = _np()
    values = np.asarray(values).ravel()
    unknown = list(unknown_color or DEFAULT_UNKNOWN_COLOR)
    unknown = unknown + [1.0] if len(unknown) == 3 else unknown
    result = np.tile(np.asarray(unknown, dtype=np.float64), (len(values), 1))
    finite = np.isfinite(values) if values.dtype.kind == "f" else np.ones(len(values), dtype=bool)
    for entry in entries:
        color = [float(c) for c in entry["color"]]
        color = color + [1.0] if len(color) == 3 else color
        result[finite & (values == entry["value"])] = color
    return result


# ---------------------------------------------------------------------------
# HSL and stk:orientation-hsl


def hsl_to_rgb(h, s, l):
    """CSS Color 4 HSL -> RGB (floats in [0, 1]); scalars or NumPy arrays of the same shape."""
    if all(isinstance(v, (int, float)) for v in (h, s, l)):
        c = (1 - abs(2 * l - 1)) * s
        hp = (h % 360.0) / 60.0
        x = c * (1 - abs(hp % 2 - 1))
        r1, g1, b1 = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(hp) % 6]
        m = l - c / 2
        return (r1 + m, g1 + m, b1 + m)
    np = _np()
    h, s, l = (np.asarray(v, dtype=np.float64) for v in (h, s, l))
    c = (1 - np.abs(2 * l - 1)) * s
    hp = np.mod(h, 360.0) / 60.0
    x = c * (1 - np.abs(np.mod(hp, 2) - 1))
    sector = np.floor(hp).astype(np.int64) % 6
    zero = np.zeros_like(c)
    r1 = np.choose(sector, [c, x, zero, zero, x, c])
    g1 = np.choose(sector, [x, c, c, x, zero, zero])
    b1 = np.choose(sector, [zero, zero, x, c, c, x])
    m = l - c / 2
    return np.stack([r1 + m, g1 + m, b1 + m], axis=-1)


def orientation_rgb(p, max_magnitude, lightness_range=(0.0, 1.0)):
    """``stk:orientation-hsl`` of one vector (domain-classifiers.md §6.2) -> ``(r, g, b)`` floats."""
    l0, l1 = (float(v) for v in lightness_range)
    px, py, pz = (float(v) for v in p)
    big = float(max_magnitude)
    m = math.sqrt(px * px + py * py + pz * pz)
    if not (big > 0) or not (m > 0) or not math.isfinite(m):
        return hsl_to_rgb(0.0, 0.0, l0 + (l1 - l0) * 0.5)
    if math.hypot(px, py) < 1e-5 * big:
        t = min(max((pz + big) / (2 * big), 0.0), 1.0)
        return hsl_to_rgb(0.0, 0.0, l0 + (l1 - l0) * t)
    h = math.degrees(math.atan2(py, px)) % 360.0
    return hsl_to_rgb(h, min(m / big, 1.0), l0 + (l1 - l0) * (pz / m + 1) / 2)


def orientation_hsl(vectors, max_magnitude=None, lightness_range=(0.0, 1.0)):
    """Vectorized ``stk:orientation-hsl``: ``(n, 3)`` vectors -> ``(n, 3)`` RGB floats.

    ``max_magnitude`` defaults to the largest finite magnitude of ``vectors``.
    Non-finite vectors are treated as zero (mid grey).
    """
    np = _np()
    p = np.asarray(vectors, dtype=np.float64).reshape(-1, 3)
    p = np.where(np.isfinite(p).all(axis=1, keepdims=True), p, 0.0)
    m = np.linalg.norm(p, axis=1)
    big = float(m.max()) if max_magnitude is None and len(m) else float(max_magnitude or 0.0)
    l0, l1 = (float(v) for v in lightness_range)
    mxy = np.hypot(p[:, 0], p[:, 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        hue = np.mod(np.degrees(np.arctan2(p[:, 1], p[:, 0])), 360.0)
        sat = np.minimum(m / big, 1.0) if big > 0 else np.zeros_like(m)
        light = l0 + (l1 - l0) * (np.where(m > 0, p[:, 2] / np.where(m > 0, m, 1.0), 0.0) + 1) / 2
        axial = l0 + (l1 - l0) * np.clip((p[:, 2] + big) / (2 * big), 0.0, 1.0) if big > 0 else np.zeros_like(m)
    grey_mid = (big <= 0) | (m <= 0)
    grey_axis = ~grey_mid & (mxy < 1e-5 * big)
    sat = np.where(grey_mid | grey_axis, 0.0, sat)
    light = np.where(grey_mid, l0 + (l1 - l0) * 0.5, np.where(grey_axis, axial, light))
    hue = np.where(grey_mid | grey_axis, 0.0, hue)
    return hsl_to_rgb(hue, sat, light)


# ---------------------------------------------------------------------------
# Categorical palettes


def stk_categorical_color(value):
    """``stk:categorical`` colour of a label value (domain-classifiers.md §6.5).

    Labels are integers: a non-integer (or non-finite) value gets the unknown grey, as in every client
    (render payload spec §5); it is never truncated to a neighbouring label.
    """
    value = float(value)
    if not (math.isfinite(value) and value.is_integer()):
        return DEFAULT_UNKNOWN_COLOR
    value = int(value)
    if value in RESERVED_COLORS:
        return RESERVED_COLORS[value]
    if value < -1:
        return (0.5, 0.5, 0.5)
    i = value - 1
    return hsl_to_rgb((i * GOLDEN_ANGLE) % 360.0, 0.65, (0.50, 0.38, 0.62)[i % 3])


def category_color(category, palette=None):
    """Colour of one category (a dict or ``suan.data.model.Category``).

    The category's own ``color`` wins; otherwise ``stk:cubic-26-orientation``
    colours a variant by its ``direction`` (lightness [0.2, 0.8]) and every other
    palette falls back to ``stk:categorical``.
    """
    get = category.get if isinstance(category, dict) else (lambda key, default=None: getattr(category, key, default))
    color = get("color")
    if color is not None:
        return tuple(float(c) for c in color)
    value = int(get("value"))
    if value in RESERVED_COLORS:
        return RESERVED_COLORS[value]
    direction = get("direction")
    if palette == "stk:cubic-26-orientation" and direction is not None:
        return orientation_rgb(direction, 1.0, CUBIC26_LIGHTNESS)
    return stk_categorical_color(value)


def palette_entries(categories, palette=None, values=None):
    """Payload palette entries ``[{value, name, color, family?, direction?, aliases?}]`` sorted by value.

    ``values`` adds entries (named ``unknown(<v>)``) for values without a category.
    """
    entries = {}
    for category in categories or ():
        get = category.get if isinstance(category, dict) else (lambda key, c=category: getattr(c, key, None))
        value = int(get("value"))
        entry = {"value": value, "name": str(get("name")),
                 "color": [round(float(c), 6) for c in category_color(category, palette)]}
        if get("family"):
            entry["family"] = str(get("family"))
        if get("direction") is not None:
            entry["direction"] = [round(float(c), 12) for c in get("direction")]
        if get("aliases"):
            entry["aliases"] = [str(a) for a in get("aliases")]
        entries[value] = entry
    for value in values or ():
        value = int(value)
        if value not in entries:
            entries[value] = {"value": value, "name": f"unknown({value})",
                              "color": [round(c, 6) for c in stk_categorical_color(value)]}
    return [entries[key] for key in sorted(entries)]


# ---------------------------------------------------------------------------
# Transfer functions (volume)


def opacity_points(points, value_range):
    """Normalized ``[[x, alpha], ...]`` (x in [0, 1] over ``value_range``) -> physical ``[[value, alpha], ...]``."""
    lo, hi = float(value_range[0]), float(value_range[1])
    result = [[lo + float(x) * (hi - lo), float(a)] for x, a in points]
    return sorted(result, key=lambda pair: pair[0])


# Automatic volume opacity (stk.render.volume@1 ``opacity: null``): a ramp over the colour range for scalars;
# one alpha for every label of a categorical volume, 0 for the reserved negative labels (-1 = unclassified,
# no data or air), so no present category disappears (render payload spec §6.6).
DEFAULT_OPACITY = ((0.0, 0.0), (1.0, 0.8))
CATEGORICAL_OPACITY = 0.8


def categorical_opacity(value_range, alpha=CATEGORICAL_OPACITY):
    """Physical ``[[value, alpha], ...]`` of a categorical volume over integer labels ``value_range``.

    Labels >= 0 get ``alpha``, negative labels 0 (the step sits at -0.5, like the colour steps at +-0.499).
    """
    lo, hi = float(value_range[0]), float(value_range[1])
    alpha = float(alpha)
    if hi < 0:
        return [[lo, 0.0], [hi, 0.0]]
    if lo >= 0:
        return [[lo, alpha], [hi, alpha]]
    return [[lo, 0.0], [-0.5, 0.0], [-0.499, alpha], [hi, alpha]]


def volume_color_points(colormap, lut, value_range):
    """Colour transfer points ``[[physical value, r, g, b], ...]`` of a volume (render payload spec §6.6).

    ``colormap`` is the payload ``colormaps[]`` entry and ``lut`` its ``(256, 4)`` uint8 table (``None`` for a
    categorical palette). A continuous LUT is spread over ``value_range`` at the bin centres
    ``lo + (k + 0.5) / 256 * (hi - lo)``; a degenerate range (``hi <= lo``) is one point, LUT entry 128, at
    ``lo``. A categorical palette holds each entry's colour, quantized to RGBA8 like every payload colour,
    over ``value - 0.499 .. value + 0.499``.
    """
    lo, hi = float(value_range[0]), float(value_range[1])
    if colormap.get("categorical"):
        points = []
        for entry in colormap.get("entries") or ():
            r, g, b = (c / 255 for c in rgba8(entry["color"])[:3])
            points += [[entry["value"] - 0.499, r, g, b], [entry["value"] + 0.499, r, g, b]]
        return points
    table = [[int(v) for v in row] for row in lut]
    if not hi > lo:
        return [[lo] + [c / 255 for c in table[128][:3]]]
    return [[lo + ((k + 0.5) / 256) * (hi - lo)] + [c / 255 for c in table[k][:3]] for k in range(256)]


def opacity_at(values, points):
    """Piecewise-linear opacity at physical ``values``; constant beyond the end points.

    Of points with the same value the last one wins, as VTK/vtk.js ``AddPoint`` replace a point
    (render payload spec §6.6).
    """
    np = _np()
    last = {}
    for v, a in points:
        last[float(v)] = float(a)
    points = sorted(last.items())
    xs, alphas = [p[0] for p in points], [p[1] for p in points]
    return np.interp(np.asarray(values, dtype=np.float64), xs, alphas)


def opacity_lut(points, value_range, size=256):
    """Opacity sampled at the centres of the ``size`` LUT bins spanning ``value_range``."""
    np = _np()
    lo, hi = float(value_range[0]), float(value_range[1])
    centres = lo + (np.arange(size) + 0.5) / size * (hi - lo)
    return opacity_at(centres, points)


def transfer_function(colormap, value_range, opacity):
    """Payload ``transfer_function`` from normalized opacity points (``stk.render.volume@1`` params)."""
    lo, hi = float(value_range[0]), float(value_range[1])
    return {"colormap": colormap, "range": [lo, hi], "opacity": opacity_points(opacity, (lo, hi))}


def transfer_function_rgba8(name, value_range, points):
    """``(256, 4)`` uint8: a built-in LUT whose alpha is the opacity at each bin centre."""
    np = _np()
    lut = lut_rgba8(name)
    lut[:, 3] = np.floor(np.clip(opacity_lut(points, value_range), 0, 1) * 255 + 0.5).astype(np.uint8)
    return lut
