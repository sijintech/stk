"""Parameter sweeps: plan the rows of a scan as ordinary project commands.

``plan_sweep(snapshot, table_id, axes, base_record_id=None, mode="product")`` turns per-field value
lists or ranges into ``add_record`` + ``set_cell`` commands for new rows of one table. With a base
row, every other cell of that row is copied into each new row: literals as values, references and
expressions as definitions, with bindings that point at the base row itself moved onto the new row
(so ``T + 10 K`` keeps meaning "this row's T"). Applying the commands is an ordinary ``apply`` at the
snapshot's revision: one revision and one undo, so a plan holds at most 1000 commands (one
``add_record`` per row plus one command per swept or copied cell). Planning reads only the given snapshot; it never
writes, evaluates formulas, prepares runs or starts anything. The tables the project manages itself
(saved analyses, the file index) cannot be swept.

An axis is ``{"field_id", "values": [...]}`` or a range ``{"field_id", "start", "stop", "count"}``
(inclusive, evenly spaced) or ``{"field_id", "start", "stop", "step"}`` (inclusive of ``stop`` when it
falls on a step). Values must match the field type exactly: integers for ``integer`` fields, finite
numbers for ``number``, strings for ``text``, booleans for ``boolean``; ``json`` fields take listed
values only. Computed floats are rounded to 12 significant digits so ``0.1`` steps stay readable.
``mode`` ``"product"`` combines every value of every axis (the first axis varies slowest);
``"zip"`` pairs the i-th values of equally long axes.
"""
import itertools
import math
import uuid

from .analyses import TABLE_ID as ANALYSES_TABLE
from .files import TABLE_ID as FILES_TABLE
from .store import ProjectError

__all__ = ["MAX_AXES", "MAX_COMMANDS", "MAX_ROWS", "MAX_VALUES", "axis_values", "plan_sweep"]

MAX_AXES = 8
MAX_VALUES = 1000
MAX_ROWS = 1000
MAX_COMMANDS = 1000  # ProjectStore.apply: one edit holds at most 1000 commands.


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ProjectError(f"{name} must be a finite number")
    return value


def _round(value):
    return float(f"{value:.12g}")


def _check(value, kind, field_name):
    ok = {"integer": type(value) is int, "number": type(value) in (int, float) and math.isfinite(value),
          "text": type(value) is str, "boolean": type(value) is bool, "json": True}.get(kind)
    if ok is None:
        raise ProjectError(f"Field {field_name!r} has type {kind!r}, which cannot be swept")
    if not ok:
        raise ProjectError(f"Value {value!r} does not fit the {kind} field {field_name!r}")
    if kind == "integer" and not -(2**63) <= value < 2**63:
        raise ProjectError(f"Value {value!r} is outside the 64-bit integer range of {field_name!r}")
    return value


def axis_values(axis, field):
    """The values of one axis for ``field`` (``{"id", "name", "type"}``), checked against its type."""
    name, kind = field.get("name", field["id"]), field["type"]
    keys = set(axis) - {"field_id"}
    if keys == {"values"}:
        values = axis["values"]
        if not isinstance(values, list) or not 1 <= len(values) <= MAX_VALUES:
            raise ProjectError(f"An axis lists 1 to {MAX_VALUES} values")
        return [_check(value, kind, name) for value in values]
    if keys not in ({"start", "stop", "count"}, {"start", "stop", "step"}):
        raise ProjectError("An axis is {values} or a range {start, stop, count} or {start, stop, step}")
    if kind not in ("integer", "number"):
        raise ProjectError(f"Ranges need a number or integer field; {name!r} is {kind}")
    start, stop = _number(axis["start"], "start"), _number(axis["stop"], "stop")
    if kind == "integer" and (type(start) is not int or type(stop) is not int):
        raise ProjectError(f"Integer field {name!r} needs integer range ends")
    if "count" in keys:
        count = axis["count"]
        if type(count) is not int or not 1 <= count <= MAX_VALUES:
            raise ProjectError(f"count must be an integer from 1 to {MAX_VALUES}")
        if count == 1:
            values = [start]
        elif kind == "integer":
            if (stop - start) % (count - 1):
                raise ProjectError(f"{count} evenly spaced integers cannot span {start}..{stop}")
            values = [start + i * ((stop - start) // (count - 1)) for i in range(count)]
        else:
            values = [start] + [_round(start + i * (stop - start) / (count - 1)) for i in range(1, count - 1)] + [stop]
    else:
        step = _number(axis["step"], "step")
        if kind == "integer" and type(step) is not int:
            raise ProjectError(f"Integer field {name!r} needs an integer step")
        if step == 0 or (stop - start) * step < 0:
            raise ProjectError("step must be nonzero and point from start towards stop")
        span = (stop - start) / step
        count = math.floor(span + 1e-9) + 1
        if count > MAX_VALUES:
            raise ProjectError(f"The range has more than {MAX_VALUES} values")
        values = [start + i * step if kind == "integer" else _round(start + i * step) for i in range(count)]
        if kind != "integer" and count > 1 and math.isclose(values[-1], stop, rel_tol=1e-9, abs_tol=0.0):
            values[-1] = stop
    return [_check(value, kind, name) for value in values]


def _rebase(binding, base, record):
    if isinstance(binding, dict) and binding.get("record_id") == base:
        return {**binding, "record_id": record}
    return binding


def plan_sweep(snapshot, table_id, axes, base_record_id=None, mode="product"):
    """``{"table_id", "rows", "record_ids", "commands"}`` that add one row per combination."""
    tables = {table["id"]: table for table in snapshot.get("tables") or ()}
    if table_id not in tables:
        raise ProjectError("Unknown table")
    if table_id in (ANALYSES_TABLE, FILES_TABLE):
        raise ProjectError("The project manages this table itself; sweep a parameter table instead")
    table = tables[table_id]
    fields = {field["id"]: field for field in table.get("fields") or ()}
    if not isinstance(axes, list) or not 1 <= len(axes) <= MAX_AXES:
        raise ProjectError(f"A sweep has 1 to {MAX_AXES} axes")
    if mode not in ("product", "zip"):
        raise ProjectError("mode is 'product' or 'zip'")
    columns = []
    for axis in axes:
        if not isinstance(axis, dict) or axis.get("field_id") not in fields:
            raise ProjectError("Every axis names a field of the table")
        columns.append((axis["field_id"], axis_values(axis, fields[axis["field_id"]])))
    if len({field_id for field_id, _ in columns}) != len(columns):
        raise ProjectError("A field can be swept by one axis only")
    lengths = [len(values) for _, values in columns]
    if mode == "zip":
        if len(set(lengths)) != 1:
            raise ProjectError("Zipped axes need the same number of values")
        combos = list(zip(*(values for _, values in columns)))
    else:
        if math.prod(lengths) > MAX_ROWS:
            raise ProjectError(f"The sweep makes {math.prod(lengths)} rows; at most {MAX_ROWS} are allowed at once")
        combos = list(itertools.product(*(values for _, values in columns)))
    if len(combos) > MAX_ROWS:
        raise ProjectError(f"The sweep makes {len(combos)} rows; at most {MAX_ROWS} are allowed at once")
    base = None
    if base_record_id is not None:
        base = next((record for record in table.get("records") or () if record["id"] == base_record_id), None)
        if base is None:
            raise ProjectError("The base row is not in this table")
    swept = {field_id for field_id, _ in columns}
    commands, record_ids = [], []
    for combo in combos:
        record = str(uuid.uuid4())
        record_ids.append(record)
        commands.append({"op": "add_record", "id": record, "table_id": table_id})
        if base is not None:
            definitions = base.get("definitions") or {}
            for field_id in fields:
                if field_id in swept:
                    continue
                definition = definitions.get(field_id)
                cell = {"table_id": table_id, "record_id": record, "field_id": field_id}
                if definition and definition.get("kind") == "expression":
                    commands.append({"op": "set_expression", **cell, "expression": definition["expression"],
                                     "bindings": {name: _rebase(target, base["id"], record)
                                                  for name, target in (definition.get("bindings") or {}).items()}})
                elif definition and definition.get("kind") == "reference":
                    commands.append({"op": "set_reference", **cell,
                                     "source": _rebase(definition["source"], base["id"], record)})
                elif field_id in (base.get("values") or {}):
                    commands.append({"op": "set_cell", **cell, "value": base["values"][field_id]})
        for (field_id, _), value in zip(columns, combo):
            commands.append({"op": "set_cell", "table_id": table_id, "record_id": record, "field_id": field_id,
                             "value": value})
    if len(commands) > MAX_COMMANDS:
        per_row = len(commands) // len(combos)
        raise ProjectError(f"The sweep needs {len(commands)} edit commands ({per_row} per row); one edit holds at most "
                           f"{MAX_COMMANDS}, so add at most {MAX_COMMANDS // per_row} rows at a time")
    return {"table_id": table_id, "rows": len(combos), "record_ids": record_ids, "commands": commands}
