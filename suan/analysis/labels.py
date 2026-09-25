"""Film detection and label statistics (clean room: docs/specs/domain-classifiers.md §4, §5). NumPy only.

Film detection works along z (grid index k; with the (z, y, x, c) layout a
layer is ``array[k]``): layer k is polarized iff the largest L1 norm
|p_x| + |p_y| + |p_z| of its finite vectors exceeds ``epsilon``. The film spans
the lowest to the highest polarized layer; below is substrate, above is air.

Label fractions count samples per label value; the denominator excludes
``exclude`` (default -1 and 0), whose rows get a NaN fraction.
"""
import math

from . import palettes

__all__ = [
    "apply_film", "film_categories", "film_detect_image", "film_info", "film_layer_labels", "fractions_tables",
    "label_counts", "label_fractions",
]


def _np():
    import numpy
    return numpy


def film_categories():
    """Categories of ``film_detect``'s label field: -1 air, 0 substrate, 1 film."""
    from suan.data.model import Category
    return (Category(-1, "air", color=palettes.UNCLASSIFIED, description="above the film (or no film)"),
            Category(0, "substrate", color=palettes.SUBSTRATE),
            Category(1, "film", color=palettes.categorical_color(1)))


def film_info(vectors, *, epsilon=1e-6):
    """Film layers of a (nz, ny, nx, 3) vector array (any trailing layout per layer works).

    ``{"detected", "axis": "z", "epsilon", "substrate_top", "film_bottom", "film_top",
    "substrate_layers", "film_layers", "air_layers"}``; indices are ``None`` when no
    layer is polarized.
    """
    np = _np()
    if not (isinstance(epsilon, (int, float)) and math.isfinite(epsilon) and epsilon >= 0):
        raise ValueError("epsilon must be a finite number >= 0")
    nz = vectors.shape[0]
    polarized = np.zeros(nz, dtype=bool)
    for k in range(nz):
        layer = np.asarray(vectors[k], dtype=np.float64).reshape(-1, vectors.shape[-1])
        l1 = np.abs(layer).sum(axis=1)
        finite = np.isfinite(l1)
        polarized[k] = bool(finite.any() and l1[finite].max() > epsilon)
    info = {"detected": bool(polarized.any()), "axis": "z", "epsilon": float(epsilon), "substrate_top": None,
            "film_bottom": None, "film_top": None, "substrate_layers": 0, "film_layers": 0, "air_layers": nz}
    if info["detected"]:
        layers = np.flatnonzero(polarized)
        bottom, top = int(layers[0]), int(layers[-1])
        info.update(substrate_top=bottom - 1, film_bottom=bottom, film_top=top, substrate_layers=bottom,
                    film_layers=top - bottom + 1, air_layers=nz - 1 - top)
    return info


def film_layer_labels(info, nz):
    """int8 label per layer: 0 substrate, 1 film, -1 air (all -1 when no film was detected)."""
    np = _np()
    labels = np.full(nz, -1, dtype=np.int8)
    if info["detected"]:
        labels[:info["film_bottom"]] = 0
        labels[info["film_bottom"]:info["film_top"] + 1] = 1
    return labels


def apply_film(labels, info):
    """Classifier step 7 (§3): layers at or below ``substrate_top`` become 0, above ``film_top`` -1 (in place)."""
    if info["detected"]:
        labels[:info["substrate_top"] + 1] = 0
        labels[info["film_top"] + 1:] = -1
    return labels


def film_detect_image(image, *, field=None, component_offset=0, epsilon=1e-6, output="film"):
    """``stk.analysis.film_detect@1``: ``(image + int8 label field, info)``."""
    from .orientation import select_vector_field
    np = _np()
    source, vectors = select_vector_field(image, field, component_offset)
    info = film_info(vectors, epsilon=epsilon)
    per_layer = film_layer_labels(info, vectors.shape[0])
    labels = np.ascontiguousarray(np.broadcast_to(per_layer.reshape((-1,) + (1,) * (vectors.ndim - 2)),
                                                  vectors.shape[:-1]))
    result = image.copy()
    result.add_field(output, labels, association=source.association, tensor="label",
                     categories=film_categories(), palette=palettes.CATEGORICAL, quantity="label", unit="1")
    result.attrs["film"] = info
    return result, info


def label_counts(values):
    """``{value: count}`` of an integer array (bincount when the value range is small)."""
    np = _np()
    values = np.asarray(values).reshape(-1)
    if not values.size:
        return {}
    if values.dtype.kind not in "iu":
        raise ValueError("Label values must be integers")
    low, high = int(values.min()), int(values.max())
    if high - low <= 1 << 20:
        counts = np.bincount((values.astype(np.int64) - low), minlength=high - low + 1)
        present = np.flatnonzero(counts)
        return {int(v) + low: int(counts[v]) for v in present}
    unique, counts = np.unique(values, return_counts=True)
    return {int(v): int(c) for v, c in zip(unique, counts)}


def label_fractions(values, categories, *, exclude=(-1, 0), include_empty=True, field=None):
    """Rows of ``stk.analysis.label_fractions@1`` (§5).

    Returns ``(rows, families, attrs, warnings)``: ``rows`` are dicts ``{value,
    name, family, count, fraction, color}`` sorted by value; ``families`` dicts
    ``{family, count, fraction}``; ``attrs`` ``{field, denominator, total,
    excluded}``; ``warnings`` dicts ``{code, message}`` (``unknown_label``,
    ``empty_denominator``).
    """
    counts = label_counts(values)
    exclude = {int(v) for v in exclude}
    by_value = {c.value: c for c in categories or ()}
    warnings = []
    unknown = sorted(set(counts) - set(by_value))
    if unknown:
        warnings.append({"code": "unknown_label",
                         "message": f"Label values without a category: {', '.join(map(str, unknown[:10]))}"})
    denominator = sum(n for v, n in counts.items() if v not in exclude)
    total = sum(counts.values())
    if denominator == 0:
        warnings.append({"code": "empty_denominator",
                         "message": "No samples outside the excluded labels; fractions are NaN"})
    values_listed = sorted(set(counts) | (set(by_value) if include_empty else set()))
    rows = []
    for value in values_listed:
        category = by_value.get(value)
        count = counts.get(value, 0)
        fraction = count / denominator if value not in exclude and denominator else math.nan
        rows.append({"value": value, "name": category.name if category else f"unknown({value})",
                     "family": (category.family or "") if category else "", "count": count,
                     "fraction": fraction, "color": palettes.to_hex(category.color if category else None)})
    families = {}
    for category in categories or ():
        if category.family and category.family not in families:
            families[category.family] = 0
    for row in rows:
        if row["family"] in families and row["value"] not in exclude:
            families[row["family"]] += row["count"]
    family_rows = [{"family": name, "count": count, "fraction": count / denominator if denominator else math.nan}
                   for name, count in families.items()]
    attrs = {"field": field, "denominator": denominator, "total": total,
             "excluded": {str(v): counts.get(v, 0) for v in sorted(exclude)}}
    return rows, family_rows, attrs, warnings


def _table_id(field, suffix):
    """``<field><suffix>`` as a dataset id (``^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$``): field names may hold any
    character but ``/`` and ``.``, e.g. blanks or CJK text."""
    import re
    stem = re.sub(r"[^A-Za-z0-9_.:-]", "_", field)[:128 - len(suffix)] or "labels"
    if not re.match(r"[A-Za-z0-9_]", stem):
        stem = "_" + stem[:127 - len(suffix)]
    return stem + suffix


def fractions_tables(dataset, *, field=None, exclude=(-1, 0), include_empty=True):
    """``(out Table, families Table, warnings)`` for a dataset's label field (``None`` = the first one)."""
    from suan.data.model import Table
    np = _np()
    if field is None:
        labels = dataset.label_fields()
        if not labels:
            raise ValueError(f"Dataset {dataset.id!r} has no label field")
        chosen = labels[0]
    else:
        chosen = dataset.field(field)
        if not chosen.is_label:
            raise ValueError(f"Field {chosen.name!r} is not a label field")
    rows, families, attrs, warnings = label_fractions(chosen.values, chosen.categories, exclude=exclude,
                                                      include_empty=include_empty, field=chosen.name)
    out = Table(id=_table_id(chosen.name, "_fractions"), attrs=attrs)
    out.add_column("value", np.array([r["value"] for r in rows], dtype=np.int64), role="label")
    out.add_column("name", np.array([r["name"] for r in rows], dtype=str))
    out.add_column("family", np.array([r["family"] for r in rows], dtype=str))
    out.add_column("count", np.array([r["count"] for r in rows], dtype=np.int64))
    out.add_column("fraction", np.array([r["fraction"] for r in rows], dtype=np.float64), unit="1")
    out.add_column("color", np.array([r["color"] for r in rows], dtype=str))
    table = Table(id=_table_id(chosen.name, "_families"), attrs=dict(attrs))
    table.add_column("family", np.array([r["family"] for r in families], dtype=str))
    table.add_column("count", np.array([r["count"] for r in families], dtype=np.int64))
    table.add_column("fraction", np.array([r["fraction"] for r in families], dtype=np.float64), unit="1")
    return out, table, warnings
