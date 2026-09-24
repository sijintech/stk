"""Orientation classification and orientation colours (clean room: docs/specs/domain-classifiers.md §2, §3, §6).

The cubic-26 direction set is generated: the 26 nonzero vectors of {-1, 0, 1}^3,
normalized. Families by the number of nonzero components: T (6 <100>), O (12
<110>), R (8 <111>). ``numbering="stk"`` (default) emits each representative
(first nonzero component +1, sorted by family) followed by its negation:
T 1-6, O 7-18, R 19-26. ``numbering="stk-legacy"`` reproduces the order already
published by STK (R 1-8, O 9-20, T 21-26), for ``stk:cubic-26`` only.

A point with vector p (float64) gets label -1 when a component is non-finite
or |p| <= ``min_magnitude``; otherwise k* = the first index of the largest
cosine c_k = p.d_k / |p| in the active numbering, accepted when
``max_angle_deg`` = 180 or c_k* > cos(max_angle). Labels are int16.

NumPy is imported when an array function is called; the direction tables and
names need only the standard library.
"""
from dataclasses import dataclass
import itertools
import math
import os

from . import palettes

__all__ = [
    "DIRECTION_SETS", "LEGACY_ORDER", "NUMBERINGS", "OrientationError", "Variant",
    "classify", "classify_image", "cubic26", "direction_set", "direction_variants", "hsl_to_rgb_array",
    "label_categories", "orientation_classify", "orientation_rgb", "palette_for", "rgb8", "select_vector_field",
]

DIRECTION_SETS = ("stk:cubic-26", "stk:cubic-100", "stk:cubic-110", "stk:cubic-111", "custom")
NUMBERINGS = ("stk", "stk-legacy")
FAMILIES = {1: "T", 2: "O", 3: "R"}
SUBSETS = {"stk:cubic-100": "T", "stk:cubic-110": "O", "stk:cubic-111": "R"}
# stk-legacy label -> sign vector (domain-classifiers.md §2.3): R 1-8, O 9-20, T 21-26, '+' then '-'.
LEGACY_ORDER = (
    (1, 1, 1), (-1, -1, -1), (-1, 1, 1), (1, -1, -1), (-1, -1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, -1),
    (1, 1, 0), (-1, -1, 0), (1, -1, 0), (-1, 1, 0), (1, 0, 1), (-1, 0, -1), (1, 0, -1), (-1, 0, 1),
    (0, 1, 1), (0, -1, -1), (0, 1, -1), (0, -1, 1),
    (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
)
_LEGACY_OFFSET = {"R": 0, "O": 8, "T": 20}
_T_SHORT = {(1, 0, 0): "a1+", (-1, 0, 0): "a1-", (0, 1, 0): "a2+", (0, -1, 0): "a2-", (0, 0, 1): "c+",
            (0, 0, -1): "c-"}
DEFAULT_CHUNK = 1 << 16


class OrientationError(ValueError):
    """Invalid classifier input; ``code`` is ``invalid_direction``, ``numbering_unsupported`` or ``invalid_param``."""

    def __init__(self, message, code="invalid_param"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Variant:
    """One label of a direction set: ``direction`` is a unit vector; ``vector`` the {-1,0,1} vector (cubic sets)."""

    label: int
    direction: tuple
    vector: tuple | None
    family: str | None
    name: str
    aliases: tuple
    color: tuple

    def category(self):
        from suan.data.model import Category
        return Category(self.label, self.name, direction=self.direction, color=self.color, family=self.family,
                        aliases=self.aliases)


def _unit(vector):
    norm = math.sqrt(sum(float(c) * float(c) for c in vector))
    return tuple(float(c) / norm for c in vector)


def _stk_name(vector):
    return FAMILIES[sum(1 for c in vector if c)] + "[" + "".join(str(c) for c in vector) + "]"


def _legacy_label(vector):
    return LEGACY_ORDER.index(tuple(vector)) + 1


def _legacy_name(vector, short=False):
    family = FAMILIES[sum(1 for c in vector if c)]
    position = _legacy_label(vector) - _LEGACY_OFFSET[family]
    head = f"{family}{(position - 1) // 2 + 1}{'+' if position % 2 else '-'}"
    if short:
        return head
    return head + "(" + ",".join("+" if c > 0 else "-" if c < 0 else "0" for c in vector) + ")"


def _stk_vectors():
    representatives = [v for v in itertools.product((1, 0, -1), repeat=3)
                       if any(v) and next(c for c in v if c) == 1]
    representatives.sort(key=lambda v: sum(1 for c in v if c))  # stable: product order within a family
    return [w for v in representatives for w in (v, tuple(-c for c in v))]


def cubic26(numbering="stk"):
    """The 26 variants of ``stk:cubic-26`` in the given numbering."""
    if numbering not in NUMBERINGS:
        raise OrientationError(f"Unknown numbering {numbering!r}; known: {', '.join(NUMBERINGS)}")
    vectors = _stk_vectors() if numbering == "stk" else list(LEGACY_ORDER)
    variants = []
    for label, vector in enumerate(vectors, start=1):
        direction = _unit(vector)
        family = FAMILIES[sum(1 for c in vector if c)]
        stk, legacy, short = _stk_name(vector), _legacy_name(vector), _legacy_name(vector, short=True)
        extra = (_T_SHORT[vector],) if vector in _T_SHORT else ()
        if numbering == "stk":
            name, aliases, color = stk, (legacy, short, *extra), palettes.cubic26_color(direction)
        else:
            name, aliases, color = legacy, (stk, short, *extra), palettes.ferro27_color(label)
        variants.append(Variant(label, direction, vector, family, name, aliases, color))
    return variants


def direction_variants(set_id="stk:cubic-26", *, numbering="stk", directions=None):
    """Variants of a direction set: ``stk:cubic-26|100|110|111`` or ``custom`` (``directions`` = nonzero 3-vectors)."""
    if set_id not in DIRECTION_SETS:
        raise OrientationError(f"Unknown direction set {set_id!r}; known: {', '.join(DIRECTION_SETS)}")
    if numbering not in NUMBERINGS:
        raise OrientationError(f"Unknown numbering {numbering!r}; known: {', '.join(NUMBERINGS)}")
    if set_id == "stk:cubic-26":
        return cubic26(numbering)
    if numbering == "stk-legacy":
        raise OrientationError(f"Numbering 'stk-legacy' is only defined for stk:cubic-26, not {set_id}",
                               "numbering_unsupported")
    if set_id in SUBSETS:
        family = SUBSETS[set_id]
        chosen = [v for v in cubic26("stk") if v.family == family]
        return [Variant(label, v.direction, v.vector, v.family, v.name, v.aliases, v.color)
                for label, v in enumerate(chosen, start=1)]
    if not directions:
        raise OrientationError("Direction set 'custom' needs a non-empty list of directions")
    variants = []
    for label, vector in enumerate(directions, start=1):
        try:
            values = tuple(float(c) for c in vector)
        except (TypeError, ValueError):
            raise OrientationError(f"Direction {label} must be three numbers", "invalid_direction") from None
        if len(values) != 3 or not all(math.isfinite(c) for c in values) or not any(values):
            raise OrientationError(f"Direction {label} must be a finite nonzero 3-vector", "invalid_direction")
        variants.append(Variant(label, _unit(values), None, None, f"d{label}", (),
                                palettes.categorical_color(label)))
    return variants


direction_set = direction_variants  # the name used by the graph parameter


def palette_for(set_id="stk:cubic-26", numbering="stk"):
    """Palette id of a classification's label field (§1)."""
    if set_id == "custom":
        return palettes.CATEGORICAL
    return palettes.LEGACY_FERRO27 if numbering == "stk-legacy" else palettes.CUBIC26_ORIENTATION


def label_categories(variants, palette, *, substrate=False):
    """Categories of a label field: ``-1`` unclassified, ``0`` substrate (film detection only), then the variants."""
    from suan.data.model import Category
    result = [Category(-1, "unclassified", color=palettes.UNCLASSIFIED,
                       description="magnitude at or below the threshold, outside the angle, no data or air")]
    if substrate:
        result.append(Category(0, "substrate", color=palettes.palette_color(palette, 0)))
    return result + [v.category() for v in variants]


def _check_thresholds(min_magnitude, max_angle_deg):
    if not (isinstance(min_magnitude, (int, float)) and math.isfinite(min_magnitude) and min_magnitude >= 0):
        raise OrientationError("min_magnitude must be a finite number >= 0")
    if not (isinstance(max_angle_deg, (int, float)) and 0 < max_angle_deg <= 180):
        raise OrientationError("max_angle_deg must be in (0, 180]")


def _classify_chunk(vectors, start, stop, transposed, min_magnitude, limit, out):
    np = _np()
    p = np.asarray(vectors[start:stop], dtype=np.float64)
    # Scale each vector by its largest component before the norm: |p|^2 would overflow for |p| > 1.3e154
    # (and underflow for tiny vectors), which made huge vectors classify as the first direction.
    finite = np.isfinite(p).all(axis=1)
    with np.errstate(invalid="ignore"):
        scale = np.abs(p).max(axis=1) if len(p) else np.zeros(0)
    scale = np.where(finite & (scale > 0), scale, 1.0)
    p = p / scale[:, None]
    norm = np.sqrt(np.einsum("ij,ij->i", p, p))
    with np.errstate(over="ignore"):
        magnitude = norm * scale
    valid = finite & (magnitude > min_magnitude)
    if not valid.all():
        p = np.where(valid[:, None], p, 0.0)
        norm = np.where(valid, norm, 1.0)
    cosine = p @ transposed
    cosine /= norm[:, None]
    best = cosine.argmax(axis=1)  # first maximum: ties go to the lower label
    labels = best.astype(np.int16)
    labels += 1
    if limit is not None:
        valid &= np.take_along_axis(cosine, best[:, None], axis=1)[:, 0] > limit
    labels[~valid] = -1
    out[start:stop] = labels


def classify(vectors, directions, *, min_magnitude=0.1, max_angle_deg=180.0, chunk=DEFAULT_CHUNK, out=None,
             check=None, threads=None):
    """Labels (int16, 1-based, -1 unclassified) of ``vectors`` (n, 3) against unit ``directions`` (k, 3).

    Chunks of ``chunk`` points are classified by up to ``threads`` worker
    threads (default ``min(8, cpu_count)``; NumPy releases the GIL); ``check``
    is called between chunks.
    """
    np = _np()
    _check_thresholds(min_magnitude, max_angle_deg)
    vectors = np.asarray(vectors)
    if vectors.ndim != 2 or vectors.shape[1] != 3:
        raise OrientationError("vectors must be an (n, 3) array")
    table = np.asarray([v.direction if isinstance(v, Variant) else v for v in directions], dtype=np.float64)
    if table.ndim != 2 or table.shape[1] != 3 or not len(table):
        raise OrientationError("directions must be a non-empty (k, 3) array")
    if len(table) > 32767:
        raise OrientationError("At most 32767 directions")
    n = len(vectors)
    out = np.empty(n, dtype=np.int16) if out is None else out
    limit = None if max_angle_deg >= 180 else math.cos(math.radians(max_angle_deg))
    transposed = np.ascontiguousarray(table.T)
    spans = [(start, min(start + chunk, n)) for start in range(0, n, chunk)]
    workers = max(1, min(int(threads) if threads is not None else min(8, os.cpu_count() or 1), len(spans)))
    if workers == 1:
        for start, stop in spans:
            if check is not None:
                check()
            _classify_chunk(vectors, start, stop, transposed, min_magnitude, limit, out)
        return out
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(workers, thread_name_prefix="stk-classify") as pool:
        pending = []
        try:
            for start, stop in spans:
                if check is not None:
                    check()
                pending.append(pool.submit(_classify_chunk, vectors, start, stop, transposed, min_magnitude, limit,
                                           out))
                if len(pending) >= 2 * workers:
                    pending.pop(0).result()
            for future in pending:
                future.result()
        except BaseException:
            for future in pending:
                future.cancel()
            raise
    return out


def orientation_classify(vectors, *, direction_set="stk:cubic-26", directions=None, numbering="stk",
                         min_magnitude=0.1, max_angle_deg=180.0, chunk=DEFAULT_CHUNK, check=None, threads=None):
    """Classify an ``(..., 3)`` vector array. Returns ``(labels int16 (...), variants)``."""
    np = _np()
    variants = direction_variants(direction_set, numbering=numbering, directions=directions)
    vectors = np.asarray(vectors)
    if vectors.shape[-1:] != (3,):
        raise OrientationError("vectors must have 3 components in the last axis")
    flat = vectors.reshape(-1, 3)
    labels = classify(flat, variants, min_magnitude=min_magnitude, max_angle_deg=max_angle_deg, chunk=chunk,
                      check=check, threads=threads)
    return labels.reshape(vectors.shape[:-1]), variants


def select_vector_field(dataset, field=None, component_offset=0):
    """``(Field, values (..., 3) view)`` of the triplet at ``component_offset`` of ``field``
    (``None`` = the first field with at least 3 components)."""
    if isinstance(field, dict):
        field = field.get("name")
    if field is None:
        chosen = next((f for f in dataset.fields.values() if f.components >= 3 and f.values is not None
                       and f.dtype != "string"), None)
        if chosen is None:
            raise OrientationError("The dataset has no field with at least 3 components")
    else:
        try:
            chosen = dataset.field(field)
        except KeyError as exc:
            raise OrientationError(str(exc.args[0])) from None
    if isinstance(component_offset, bool) or not isinstance(component_offset, int) or component_offset < 0 \
            or component_offset + 3 > chosen.components:
        raise OrientationError(f"Field {chosen.name!r} has {chosen.components} components; components "
                               f"{component_offset}..{component_offset + 2} do not exist")
    if chosen.values is None:
        raise OrientationError(f"Field {chosen.name!r} has no values")
    return chosen, chosen.values[..., component_offset:component_offset + 3]


def classify_image(image, *, field=None, component_offset=0, direction_set="stk:cubic-26", directions=None,
                   numbering="stk", min_magnitude=0.1, max_angle_deg=180.0, film_detection=False,
                   film_epsilon=1e-6, output="domain", check=None, threads=None):
    """``stk.analysis.orientation_classify@1`` on an :class:`~suan.data.model.ImageData` (§3).

    Returns a shallow copy of ``image`` (input fields kept, zero copy) plus the
    int16 label field ``output`` (categories, palette, quantity ``domain_variant``,
    unit ``"1"``). With ``film_detection`` the substrate becomes 0 and the air
    above the film -1; the film info is ``attrs["film"]``. The thresholds and
    the source unit are recorded in ``attrs["orientation"]``.
    """
    from .labels import apply_film, film_info
    np = _np()
    source, vectors = select_vector_field(image, field, component_offset)
    variants = direction_variants(direction_set, numbering=numbering, directions=directions)
    labels = np.empty(vectors.shape[:-1], dtype=np.int16)
    # A strided (n, 3) view of the triplet: chunks are copied one at a time, never the whole field.
    flat = source.values.reshape(-1, source.components)[:, component_offset:component_offset + 3]
    classify(flat, variants, min_magnitude=min_magnitude, max_angle_deg=max_angle_deg, out=labels.reshape(-1),
             check=check, threads=threads)
    result = image.copy()
    info = None
    if film_detection:
        info = film_info(vectors, epsilon=film_epsilon)
        apply_film(labels, info)
        result.attrs["film"] = info
    palette = palette_for(direction_set, numbering)
    result.add_field(output, labels, association=source.association, tensor="label",
                     categories=label_categories(variants, palette, substrate=film_detection), palette=palette,
                     quantity="domain_variant", unit="1")
    result.attrs["orientation"] = {
        "field": source.name, "component_offset": component_offset, "unit": source.unit,
        "direction_set": direction_set, "numbering": numbering, "min_magnitude": min_magnitude,
        "max_angle_deg": max_angle_deg, "film_detection": bool(film_detection),
    }
    return result


# ---------------------------------------------------------------------------
# Orientation colours (§6.1, §6.2), vectorized


def _np():
    import numpy
    return numpy


def hsl_to_rgb_array(h, s, l):  # noqa: E741
    """Vectorized CSS Color 4 HSL -> RGB: arrays of hue (degrees), saturation, lightness -> (..., 3)."""
    np = _np()
    h, s, l = (np.asarray(v, dtype=np.float64) for v in (h, s, l))  # noqa: E741
    c = (1 - np.abs(2 * l - 1)) * s
    hp = np.mod(h, 360) / 60
    x = c * (1 - np.abs(np.mod(hp, 2) - 1))
    zero = np.zeros_like(c)
    sector = np.floor(hp).astype(np.int64) % 6
    r = np.choose(sector, [c, x, zero, zero, x, c])
    g = np.choose(sector, [x, c, c, x, zero, zero])
    b = np.choose(sector, [zero, zero, x, c, c, x])
    m = l - c / 2
    return np.stack([r + m, g + m, b + m], axis=-1)


def orientation_rgb(vectors, *, max_magnitude=None, lightness_range=(0.0, 1.0)):
    """``stk:orientation-hsl`` colours (..., 3) in [0, 1] of vectors (..., 3) (§6.2).

    ``max_magnitude`` M defaults to the largest finite |p| of the input. Non-finite vectors are grey.
    """
    np = _np()
    p = np.asarray(vectors, dtype=np.float64)
    if p.shape[-1:] != (3,):
        raise OrientationError("vectors must have 3 components in the last axis")
    finite = np.isfinite(p).all(axis=-1)
    p = np.where(finite[..., None], p, 0.0)
    m = np.sqrt((p * p).sum(axis=-1))
    big = float(np.max(m)) if max_magnitude is None and m.size else float(max_magnitude or 0.0)
    l0, l1 = (float(v) for v in lightness_range)
    mxy = np.hypot(p[..., 0], p[..., 1])
    if big <= 0:
        grey = np.full(m.shape, l0 + (l1 - l0) / 2)
        return hsl_to_rgb_array(np.zeros_like(grey), np.zeros_like(grey), grey)
    safe = np.where(m > 0, m, 1.0)
    hue = np.mod(np.degrees(np.arctan2(p[..., 1], p[..., 0])), 360)
    saturation = np.minimum(m / big, 1.0)
    lightness = l0 + (l1 - l0) * (p[..., 2] / safe + 1) / 2
    polar = mxy < 1e-5 * big
    lightness = np.where(polar, l0 + (l1 - l0) * np.clip((p[..., 2] + big) / (2 * big), 0, 1), lightness)
    zero = m == 0
    lightness = np.where(zero, l0 + (l1 - l0) / 2, lightness)
    saturation = np.where(polar | zero, 0.0, saturation)
    return hsl_to_rgb_array(np.where(polar | zero, 0.0, hue), saturation, lightness)


def rgb8(rgb):
    """8-bit colours: ``floor(255 c + 0.5)`` (§6.1)."""
    np = _np()
    return np.floor(255 * np.asarray(rgb, dtype=np.float64) + 0.5).astype(np.uint8)
