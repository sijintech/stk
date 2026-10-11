"""Reading ``log.lammps``: the thermodynamic output of each run or minimization, and whether LAMMPS finished.

LAMMPS (default ``thermo_style one``/``custom``, ``thermo_modify line one``) prints, for each run, a line
``Per MPI rank memory allocation ...``, a header of column names (``Step Temp Press ...``), one row per thermo
step, then ``Loop time of ...``. A normal end prints ``Total wall time: h:mm:ss``; errors print lines that start
with ``ERROR``. Other thermo layouts (``line multi``, ``yaml``) are not read.
"""
import math

VERIFIER = "stk-lammps-1"
MAX_LOG_BYTES = 256 * 1024 * 1024
MAX_WARNINGS = 20
# Named results, from the thermo keywords LAMMPS prints.
QUANTITIES = {"density": "Density", "temperature": "Temp", "pressure": "Press", "potential_energy": "PotEng",
              "total_energy": "TotEng", "volume": "Volume"}


def _number(word):
    try:
        return float(word)
    except ValueError:
        return None


def read_log(text):
    """{version, units, blocks: [{columns, rows, closed}], warnings, errors, finished}."""
    lines = text.splitlines()
    result = {"version": None, "units": None, "blocks": [], "warnings": [], "warning_count": 0, "errors": [],
              "finished": False}
    index = 0
    while index < len(lines):
        line = lines[index]
        if result["version"] is None and line.startswith("LAMMPS ("):
            result["version"] = line[len("LAMMPS ("):].rstrip(")").strip()[:100]
        elif line.split()[:1] == ["units"] and len(line.split()) > 1:
            result["units"] = line.split()[1][:20]
        elif line.startswith("ERROR"):
            result["errors"].append(line[:500])
        elif line.startswith("WARNING"):
            result["warning_count"] += 1
            if len(result["warnings"]) < MAX_WARNINGS:
                result["warnings"].append(line[:500])
        elif line.startswith("Total wall time:"):
            result["finished"] = True
        elif line.startswith("Per MPI rank memory allocation") and index + 1 < len(lines):
            columns = lines[index + 1].split()
            # thermo_style multi prints "---------------- Step ... -----", yaml prints "---" and "keywords: [...]".
            unsupported = not columns or columns[0].startswith("-") or columns[0] == "keywords:" \
                or not all(word[:1].isalpha() for word in columns)
            block = {"columns": columns, "rows": [], "closed": False, "unsupported": unsupported}
            index += 2
            while index < len(lines):
                line = lines[index]
                if line.startswith("Loop time of"):
                    block["closed"] = True
                    break
                if line.startswith("ERROR"):
                    result["errors"].append(line[:500])
                elif line.startswith("WARNING"):
                    result["warning_count"] += 1
                    if len(result["warnings"]) < MAX_WARNINGS:
                        result["warnings"].append(line[:500])
                else:
                    values = [_number(word) for word in line.split()]
                    if len(values) == len(columns) and None not in values:
                        block["rows"].append(values)
                index += 1
            result["blocks"].append(block)
        index += 1
    return result


def _mean(values):
    return math.fsum(values) / len(values)


def summary(block):
    """The last block's means over its second half (equilibrated part), final values and final step."""
    rows = block["rows"]
    tail = rows[len(rows) // 2:] if len(rows) > 1 else rows
    columns = block["columns"]
    means = {name: _mean([row[i] for row in tail]) for i, name in enumerate(columns)}
    final = dict(zip(columns, rows[-1]))
    qoi = {key: means.get(column) for key, column in QUANTITIES.items()}
    step = final.get("Step")
    return {**qoi, "step": int(step) if step is not None else None, "samples": len(tail),
            "columns": columns, "means": means, "final": final}


def verify_log(text, exit_code=0):
    """Check a finished run's log; the result has the shape of the MuPRO verifier's (classification, reason,
    qoi, verification.checks). Classifications: invalid_result, incomplete_result, numerical_failure."""
    result = {"classification": None, "reason": "", "qoi": None, "units": None, "version": None, "warnings": [],
              "verification": {"verifier": VERIFIER, "status": "failed", "checks": []}}
    checks, failures = result["verification"]["checks"], []

    def add(check_id, message, classification=None):
        checks.append({"id": check_id, "status": "fail" if classification else "pass", "message": message})
        if classification:
            failures.append((classification, message))

    log = read_log(text)
    result.update(units=log["units"], version=log["version"], warnings=log["warnings"])
    if log["errors"]:
        add("errors", "LAMMPS reported an error: " + log["errors"][0], "invalid_result")
    else:
        add("errors", "No ERROR lines")
    if log["finished"] and exit_code == 0:
        add("finished", "LAMMPS ended normally (Total wall time)")
    else:
        add("finished", "LAMMPS did not reach its normal end (no Total wall time)", "incomplete_result")
    blocks = log["blocks"]
    if not blocks:
        add("thermo", "No thermodynamic output (one or custom thermo style) was found", "invalid_result")
    elif any(block["unsupported"] for block in blocks):
        add("thermo", "Unsupported thermo layout (thermo_style multi or yaml, or thermo_modify line multi); "
                      "use thermo_style one or custom", "invalid_result")
    elif not all(block["closed"] and block["rows"] for block in blocks):
        add("thermo", "A run's thermodynamic output is empty or was cut off", "incomplete_result")
    elif any(not math.isfinite(value) for block in blocks for row in block["rows"] for value in row):
        add("thermo", "Thermodynamic output has NaN or infinite values", "numerical_failure")
    else:
        add("thermo", f"{len(blocks)} run(s), {sum(len(b['rows']) for b in blocks)} finite thermo rows")
    if failures:
        result.update(classification=failures[0][0], reason=failures[0][1])
    else:
        result["verification"]["status"] = "passed"
        result["qoi"] = summary(blocks[-1])
        result["qoi"]["runs"] = len(blocks)
    return result
