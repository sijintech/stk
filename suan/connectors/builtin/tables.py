"""Generic table readers: whitespace columns, CSV and JSON lines (``stk.source.table@1``). NumPy only.

Integer-only numeric columns become int64, other numeric columns float64 and
anything else strings. Units are never guessed: every column is
``unspecified`` unless ``units`` names it.
"""
import csv
import io
import json
import math
import re

from ..api import ConnectorError

__all__ = ["columns_table", "read_columns", "read_csv", "read_jsonl"]

_COMMENT = ("#", "!")


def _np():
    import numpy
    return numpy


def _number(text):
    try:
        return int(text)
    except ValueError:
        return float(text.replace("D", "E").replace("d", "e"))


def _column(values):
    """int64, float64 or string array of Python values (None = missing)."""
    np = _np()
    present = [v for v in values if v is not None]
    if all(isinstance(v, bool) for v in present) and present:
        return np.array([int(v) if v is not None else 0 for v in values], dtype=np.uint8)
    if all(isinstance(v, int) and not isinstance(v, bool) for v in present) and len(present) == len(values):
        return np.array(values, dtype=np.int64)
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in present):
        return np.array([math.nan if v is None else float(v) for v in values], dtype=np.float64)
    return np.array(["" if v is None else (v if isinstance(v, str) else json.dumps(v)) for v in values], dtype=str)


def columns_table(columns, *, id="table", units=None, keep=None, index=None, quantities=None):
    """A :class:`~suan.data.model.Table` from ``{name: [values]}`` (``keep`` selects and orders columns)."""
    from suan.data.model import Table
    units = dict(units or {})
    unknown = set(units) - set(columns)
    if unknown:
        raise ConnectorError(f"Units given for unknown column(s) {', '.join(sorted(unknown))}", "invalid_param")
    if keep is not None:
        missing = [name for name in keep if name not in columns]
        if missing:
            raise ConnectorError(f"No column(s) {', '.join(missing)}; columns: {', '.join(columns)}", "invalid_param")
        columns = {name: columns[name] for name in keep}
    table = Table(id=id, index=index if index in columns else None)
    for name, values in columns.items():
        array = values if hasattr(values, "dtype") else _column(list(values))
        table.add_column(_safe(name), array, unit=units.get(name, "unspecified"),
                         quantity=(quantities or {}).get(name), role="index" if name == index else None)
    return table


def _safe(name):
    name = str(name).strip() or "column"
    return re.sub(r"[/.]", "_", name)[:128]


def read_columns(text, *, id="table", units=None, keep=None):
    """Whitespace-separated columns; ``#``/``!`` comments; an optional header row of names."""
    rows = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].split("!", 1)[0].strip() if line.lstrip()[:1] not in _COMMENT else ""
        if stripped:
            rows.append(stripped.split())
    if not rows:
        return columns_table({}, id=id, units=units, keep=keep)
    header = None
    try:
        [_number(token) for token in rows[0]]
    except ValueError:
        header, rows = rows[0], rows[1:]
    width = len(header) if header else len(rows[0])
    if any(len(row) != width for row in rows):
        raise ConnectorError("Rows have different numbers of columns", "invalid_data")
    names = header or [f"column_{i + 1}" for i in range(width)]
    try:
        values = [[_number(token) for token in row] for row in rows]
    except ValueError as exc:
        raise ConnectorError(f"Non-numeric value in a column table: {exc}", "invalid_data") from None
    return columns_table({name: [row[i] for row in values] for i, name in enumerate(names)}, id=id, units=units,
                         keep=keep)


def read_csv(text, *, id="table", units=None, keep=None):
    """CSV with a header row; numeric columns are converted, others stay strings."""
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        raise ConnectorError("CSV needs a header row", "invalid_data")
    header, body = [name.strip() for name in rows[0]], rows[1:]
    if any(len(row) != len(header) for row in body):
        raise ConnectorError("CSV rows have different numbers of columns", "invalid_data")
    columns = {}
    for i, name in enumerate(header):
        cells = [row[i].strip() for row in body]
        try:
            columns[name] = [_number(cell) if cell else None for cell in cells]
        except ValueError:
            columns[name] = cells
    return columns_table(columns, id=id, units=units, keep=keep)


def read_jsonl(text, *, id="table", units=None, keep=None, complete_lines_only=True):
    """One JSON object per line; columns = the union of keys in order of first appearance.

    An unterminated last line (a writer still appending) is skipped when ``complete_lines_only``.
    """
    lines = text.split("\n")
    if complete_lines_only and lines and lines[-1].strip():
        lines = lines[:-1]
    records = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise ConnectorError(f"Line {number} is not JSON: {exc}", "invalid_data") from None
        if not isinstance(record, dict):
            raise ConnectorError(f"Line {number} is not a JSON object", "invalid_data")
        records.append(record)
    names = []
    for record in records:
        names += [key for key in record if key not in names]
    columns = {name: [record.get(name) for record in records] for name in names}
    return columns_table(columns, id=id, units=units, keep=keep)
