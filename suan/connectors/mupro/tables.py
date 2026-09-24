"""muFerro tables: ``energy_out.dat`` (reader ``mupro.energy@1``) and ``mupro_progress.jsonl`` (``mupro.progress@1``).

``energy_out.dat`` is a header line (``step`` and five names) followed by rows
``kt: <step> energy: e1 e2 e3 e4 e5`` (``suan.mupro.run.ENERGY_ROW``). Values
are solver-normalized (unit ``normalized``, quantity ``energy``); ``NaN`` is
kept. Without a header the columns are ``energy_1..5``. An unterminated last
line (a live run) is skipped. Progress records are
``{"step", "completed_steps", "total_steps"}`` per line.
"""
import re

from suan.mupro.run import ENERGY_ROW

from ..api import ConnectorError
from ..builtin.tables import columns_table, read_jsonl

__all__ = ["ENERGY_COLUMNS", "energy_columns", "read_energy", "read_progress"]

ENERGY_COLUMNS = tuple(f"energy_{i}" for i in range(1, 6))
PROGRESS_COLUMNS = ("step", "completed_steps", "total_steps")


def _np():
    import numpy
    return numpy


def energy_columns(header_line):
    """The five energy column names of a header line, or ``None`` if it is not a header."""
    body = header_line.rstrip()
    names = re.split(r"\s{2,}", body.strip())
    if not (len(names) == 6 and names[0] == "step") and len(body) > 90:
        # muFerro right-aligns each name in 18 characters, so two names may be one blank apart.
        names = [body[:len(body) - 90].strip()] + [body[len(body) - 18 * (5 - i):len(body) - 18 * (4 - i)].strip()
                                                   for i in range(5)]
    if len(names) == 6 and names[0] == "step" and all(re.match(r"^[^/.]{1,128}$", n) for n in names[1:]):
        return tuple(names[1:])
    return None


def _complete_lines(text):
    lines = text.split("\n")
    return lines[:-1] if lines and lines[-1] else lines


def read_energy(text, *, id="energy", keep=None):
    """``energy_out.dat`` text -> Table ``step`` (int64, index) + five float64 energy columns."""
    np = _np()
    lines = _complete_lines(text)
    names = ENERGY_COLUMNS
    steps, values = [], []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        match = ENERGY_ROW.fullmatch(line)
        if not match:
            header = energy_columns(line) if number == 1 else None
            if header is None and number == 1 and line.split()[:1] == ["step"]:
                continue  # a header in another layout: keep the default names
            if header is None:
                raise ConnectorError(f"energy_out.dat line {number} is not 'kt: N energy: e1..e5'", "invalid_data")
            names = header
            continue
        row = [float(v.replace("D", "E").replace("d", "e")) for v in match[2].split()]
        if len(row) != 5:
            raise ConnectorError(f"energy_out.dat line {number} has {len(row)} values; expected 5", "invalid_data")
        steps.append(int(match[1]))
        values.append(row)
    table_values = np.array(values, dtype=np.float64).reshape(-1, 5)
    columns = {"step": np.array(steps, dtype=np.int64)}
    columns.update({name: table_values[:, i].copy() for i, name in enumerate(names)})
    units = {name: "normalized" for name in names}
    units["step"] = "1"
    return columns_table(columns, id=id, units=units, keep=keep, index="step",
                         quantities={**{name: "energy" for name in names}, "step": "step"})


def read_progress(text, *, id="progress", keep=None):
    """``mupro_progress.jsonl`` text -> Table ``step``, ``completed_steps``, ``total_steps`` (int64)."""
    np = _np()
    table = read_jsonl(text, id=id)
    columns = {}
    for name in PROGRESS_COLUMNS:
        values = table.column(name) if name in table else np.zeros(table.n_rows, dtype=np.int64)
        if values.dtype.kind == "f":
            if not np.isfinite(values).all() or (values != np.round(values)).any():
                raise ConnectorError(f"mupro_progress.jsonl column {name} is not integral", "invalid_data")
            values = values.astype(np.int64)
        columns[name] = values
    units = {name: "1" for name in PROGRESS_COLUMNS}
    return columns_table(columns, id=id, units=units, keep=keep, index="step",
                         quantities={"step": "step"})
