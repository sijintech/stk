"""Explicit frozen-log aggregation for PET study analyses; no simulation."""
import hashlib
import json
import math

from suan.graph.registry import (NodeExecutionError, Port, binding, node, string,
                                 string_list)
from suan.runtime.models import relative_path

MAX_BYTES = 256 * 1024 * 1024
MAX_LOGS = 98  # leave room for a receipt and the human-readable CSV


def _paths(params):
    paths = params["paths"]
    if (type(paths) is not list or not 1 <= len(paths) <= MAX_LOGS
            or any(type(path) is not str for path in paths) or len(set(paths)) != len(paths)):
        raise NodeExecutionError("Density series requires 1–98 distinct log paths", code="invalid_param")
    try:
        paths = [relative_path(path) for path in paths]
        receipt = params.get("receipt_path")
        if receipt is not None:
            receipt = relative_path(receipt)
            if receipt in paths:
                raise ValueError("receipt cannot be a log")
        return paths, receipt
    except (TypeError, ValueError):
        raise NodeExecutionError("Density-series paths must stay inside the file binding", code="invalid_param") from None


def _receipt(raw):
    if len(raw) > 2 * 1024 * 1024:
        raise NodeExecutionError("Density-series receipt exceeds 2 MiB", code="budget_exceeded")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate density-series receipt key")
            result[key] = value
        return result
    def finite(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("Density-series receipt must be finite JSON")
        return value
    def invalid(_):
        raise ValueError("Density-series receipt must be finite JSON")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_float=finite, parse_constant=invalid)


def fingerprint(ctx, inputs, params):
    from suan.connectors.api import ConnectorError
    paths, receipt = _paths(params)
    source = ctx.resolve(params["binding"])
    try:
        return {path: source.sha256(path) for path in [*paths, *([receipt] if receipt else [])]}
    except ConnectorError as error:
        raise NodeExecutionError(str(error), code=error.code) from None


@node("stk.source.lammps_density_series", title={"en": "LAMMPS density series", "zh": "LAMMPS 多温密度"},
      description={"en": "Read explicit real-unit logs, preserving every raw digest and optional frozen study receipt."},
      outputs=[Port("out", "table")],
      params={"binding": binding(), "paths": string_list([], max_items=MAX_LOGS),
              "receipt_path": string(None, nullable=True)}, fingerprint=fingerprint)
def density_source(ctx, inputs, params):
    from suan.connectors.api import ConnectorError
    from suan.data.model import Provenance
    from suan.lammps.analysis import AnalysisError, density_series
    paths, receipt_path = _paths(params)
    source = ctx.resolve(params["binding"])
    logs, used, total = {}, [], 0
    try:
        for path in [*paths, *([receipt_path] if receipt_path else [])]:
            ctx.check()
            with source.open(path) as stream:
                raw = stream.read(MAX_BYTES - total + 1)
            total += len(raw)
            if total > MAX_BYTES:
                raise NodeExecutionError("Density-series inputs exceed 256 MiB", code="budget_exceeded")
            digest = hashlib.sha256(raw).hexdigest()
            used.append({"path": path, "sha256": digest, "role": "input"})
            if path != receipt_path:
                logs[path] = raw.decode("utf-8")
            else:
                receipt = _receipt(raw)
        if receipt_path:
            if (type(receipt) is not dict or receipt.get("format") != "stk.pet-density-series/1"
                    or type(receipt.get("logs")) is not list
                    or len(receipt["logs"]) != len(paths)):
                raise AnalysisError("Unsupported or incomplete frozen density-series receipt")
            recorded = {entry["path"]: entry["sha256"] for entry in receipt["logs"]}
            if recorded != {entry["path"]: entry["sha256"] for entry in used if entry["path"] in paths}:
                raise AnalysisError("Density-series receipt does not match every original log")
        table = density_series(logs)
        table.provenance = Provenance(activity={"kind": "convert", "id": None},
            agent={"reader": "stk.lammps-density-series@1", "node": ctx.node_id}, used=used)
        table.attrs["source"] = table.provenance.to_json()
        if receipt_path:
            table.attrs["study_receipt"] = receipt
        return table
    except ConnectorError as error:
        raise NodeExecutionError(str(error), code=error.code) from None
    except (AnalysisError, UnicodeError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise NodeExecutionError(str(error) or "Invalid density-series receipt", code="invalid_result") from None


__all__ = ["density_source", "fingerprint"]
