"""Compute-side muFerro launcher, per-run verifier and node check.

`python -m suan.mupro run` executes inside the task work dir (its CWD). It stages
the case, prepares the Intel MPI/compiler environment, launches muFerro and then
checks the run against MuPRO's output contract, writing stk-mupro.json. Exit 0
from the solver alone never means success: muFerro's NaN path exits 0 without a
completion file (apps/muFerro/src/output.f90:187-190).

One rank runs as an MPI singleton, which opens no PMI listener. Several ranks use
mpiexec, which Intel MPI's Hydra also uses inside a Slurm/PBS allocation. srun is
only used with --launcher srun inside a Slurm allocation; Intel MPI then needs the
site's I_MPI_PMI_LIBRARY.
Outside an allocation, Hydra listens on 0.0.0.0, so local mpiexec is refused
unless the operator sets STK_MUPRO_ALLOW_LOCAL_MPI=1 in the Runtime environment.
That guards against accidental local runs; it is not an access control, since
Runtime clients can run any command.

Under the STK Runtime ($STK_MONITOR_PATH set) the launcher also writes monitoring events
while the solver runs (suan/mupro/monitor.py, adapt mode); outcomes and exit codes are
the same either way.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from suan.monitor.events import ENV_PATH as MONITOR_ENV
from suan.runtime.common import atomic_json, now, sha256
from suan.runtime.models import relative_path
from .spec import LAUNCHERS

RESULT = "stk-mupro.json"
VERIFIER = "stk-mupro-1"
ENVIRONMENT = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "MUPROROOT", "SRUN_CPUS_PER_TASK")
EXAMPLES = Path("share/mupro/skills/mupro-muferro/examples")
# muFerro's 8-character field stems and component counts (muprosdk tools/mupro/mupro/worker.py:40-44).
COMPONENTS = {"Charges": 1, "Displace": 3, "Eigen_St": 6, "Elas_For": 3, "Elast_En": 1, "Elast_St": 6,
              "Elec_For": 3, "Elec_Phi": 1, "Elect_En": 1, "Elefield": 3, "LandPFor": 3, "LandP_En": 1,
              "Strain": 6, "Stress": 6}
FRAME = re.compile(r"(?:^|/)([A-Za-z][A-Za-z0-9_]{0,7})\.(\d{8})\.dat$")
ENERGY_ROW = re.compile(r"^\s*kt:\s*(\d+)\s+energy:\s*(.*?)\s*$")
# Fortran Ew.d output drops the exponent letter when |exponent| > 99: 0.15E+102 is written 0.1500000000+102.
_FORTRAN_EXPONENT = re.compile(r"(?<=[0-9.])([+-]\d{3})$")
# muFerro appends to an existing energy trace and progress log (output.f90:31-43, 85-86).
RUN_OUTPUTS = ("energy_out.dat", "mupro_progress.jsonl", "mupro_completion.json")
MAX_INCLUDE_DEPTH = 16  # muprosdk library/L0_Base/toml.f90 max_include_depth


class MuproError(ValueError):
    def __init__(self, message, classification="configuration"):
        super().__init__(message)
        self.classification = classification


def fortran_float(token):
    """A Fortran real as written by muFerro: ``D`` exponents and the three-digit exponent without a
    letter (``0.1500000000+102`` = 1.5e101) are accepted; raises ``ValueError`` otherwise."""
    text = token.strip().replace("D", "E").replace("d", "e")
    return float(_FORTRAN_EXPONENT.sub(r"E\1", text))


def _integer(value, minimum):
    return type(value) is int and value >= minimum


def _merge_under(destination, included):
    """The including file wins; sub-tables merge per key (toml.f90 merge_under)."""
    for key, value in included.items():
        if key not in destination:
            destination[key] = value
        elif isinstance(destination[key], dict) and isinstance(value, dict):
            _merge_under(destination[key], value)


def _toml_document(path, root, active=(), label="input.toml"):
    """Read a TOML file and merge its `include` files as MuPRO's reader does (muprosdk
    library/L0_Base/toml.f90:125-238, tools/mupro/mupro/contract.py:90-125): a path or a
    list of paths relative to the naming file, earlier includes winning, at most 16 deep.
    Included files must resolve inside root. Include strings are POSIX paths on every
    platform, as the Linux node and muFerro read them."""
    try:
        with open(path, "rb") as stream:
            data = tomllib.load(stream)
    except (OSError, ValueError, RecursionError) as exc:
        raise MuproError(f"Cannot read {label}: {exc}") from exc
    chain = (*active, path.resolve())
    includes = data.pop("include", [])
    if isinstance(includes, str):
        includes = [includes]
    if not isinstance(includes, list) or not all(isinstance(item, str) and item for item in includes):
        raise MuproError(f"include in {label} requires a path or a list of paths")
    if includes and len(active) >= MAX_INCLUDE_DEPTH:
        raise MuproError(f"TOML includes are nested more than {MAX_INCLUDE_DEPTH} deep")
    for include in includes:
        parts = PurePosixPath(include).parts
        # A Windows client would otherwise accept separators and drives the node reads literally.
        if "\\" in include or "\x00" in include or include.startswith("/") \
                or any(PureWindowsPath(part).drive for part in parts):
            raise MuproError(f"TOML include {include!r} in {label} must be a relative POSIX path")
        target = path.parent.joinpath(*parts)
        resolved = target.resolve()
        if resolved != root and root not in resolved.parents:
            raise MuproError(f"TOML include {include} must stay inside {root}")
        if resolved in chain:
            raise MuproError(f"Cyclic TOML include: {include}")
        _merge_under(data, _toml_document(target, root, chain, resolved.relative_to(root).as_posix()))
    return data


def read_case(case_dir, root=None):
    """Read the run layout from input.toml and its includes, with muFerro's own defaults
    (apps/muFerro/src/input.f90:57, 85-86 and 113; interval has no default). Includes may
    name files anywhere inside root, the task work dir (default: the case dir)."""
    try:
        data = _toml_document(Path(case_dir) / "input.toml", Path(root or case_dir).resolve())
    except MuproError:
        raise
    except (ValueError, RecursionError) as exc:  # e.g. tables nested too deep to merge
        raise MuproError(f"Cannot read input.toml: {exc}") from exc
    system, output = data.get("system"), data.get("output")
    if not isinstance(system, dict) or not isinstance(output, dict):
        raise MuproError("input.toml requires [system] and [output] tables")
    grid = system.get("simulation_grid")
    if not isinstance(grid, list) or len(grid) != 3 or not all(_integer(n, 1) for n in grid):
        raise MuproError("[system].simulation_grid requires three positive integers")
    case = {"grid": grid, "start_step": system.get("timestep_start", 0),
            "steps": system.get("timestep_total", 1000), "output_interval": output.get("interval")}
    if case["output_interval"] is None:
        raise MuproError("[output].interval is required; muFerro has no default")
    for key, name, minimum in (("start_step", "[system].timestep_start", 0), ("steps", "[system].timestep_total", 1),
                               ("output_interval", "[output].interval", 1)):
        if not _integer(case[key], minimum):
            raise MuproError(f"{name} must be an integer of at least {minimum}")
    # The energy trace prints kt as i6 (output.f90:104; muprosdk tools/mupro/mupro/contract.py:160-161).
    if case["start_step"] + case["steps"] > 999999:
        raise MuproError("timestep_start + timestep_total must be at most 999999 (muFerro's energy trace column)")
    return case


def check_case(case, folder, ranks):
    """Checks before launch that need no SDK; `suan mupro submit --input` makes them before uploading."""
    # MuPRO decomposes x/y slabs across ranks (muprosdk tools/mupro/mupro/client.py:65-66).
    if ranks > min(case["grid"][:2]):
        raise MuproError(f"ranks must be at most min(nx, ny) = {min(case['grid'][:2])} for this grid")
    # A rerun in place appends to the old trace and fails verification after using its allocation.
    # Polar.in is a restart input, not an output.
    names = [path.name for path in Path(folder).iterdir()]
    stale = [name for name in RUN_OUTPUTS if name in names] + sorted(name for name in names if FRAME.search(name))
    if stale:
        raise MuproError("The case directory already holds muFerro outputs (" + ", ".join(stale[:5])
                         + "); submit a clean case directory")


def expected_frames(case):
    """Frame names and component counts, as muprosdk tools/mupro/mupro/worker.py:40-50.

    muFerro writes the initial Polar frame with the main-loop step still unset,
    so it is always Polar.00000000.dat (apps/muFerro/src/output.f90:24).
    """
    start, interval = case["start_step"], case["output_interval"]
    expected = {"Polar.00000000.dat": 3}
    for step in range(start + 1, start + case["steps"] + 1):
        remainder = (step - start) % interval
        if remainder == 0:
            expected[f"Polar.{step:08d}.dat"] = 3
        if remainder == 1 or interval == 1:
            expected.update({f"{stem}.{step:08d}.dat": count for stem, count in COMPONENTS.items()})
    return expected


def _header(path):
    """Grid and component count from a DAT file's first line; values are never parsed."""
    try:
        with open(path, "rb") as stream:
            values = [int(v) for v in stream.readline(4096).split()]
    except (OSError, ValueError):
        return None
    return (values[:3], values[3] if len(values) == 4 else 1) if len(values) in (3, 4) else None


def _reject_constant(value):
    raise ValueError(f"JSON constant {value} is not allowed")


def _case_folder(work, case_dir):
    """Normalize a case dir and resolve it inside the task work dir."""
    try:
        case_dir = "." if case_dir == "." else relative_path(case_dir)
    except ValueError as exc:
        raise MuproError(f"Invalid case directory: {exc}") from exc
    folder = (work / case_dir).resolve()
    if folder != work and work not in folder.parents:
        raise MuproError("The case directory must stay inside the task work directory")
    return case_dir, folder


def verify_run(work_dir=".", case_dir="."):
    """Check a finished run against MuPRO's output contract without parsing field values.

    Checks and classifications mirror collect_result in muprosdk
    tools/mupro/mupro/worker.py:17-52. A missing or unreadable completion manifest
    is invalid_result (contract.py:50-54), and so is any other read or parse error
    (worker.py:132). A wrong energy value count or a non-finite value is
    numerical_failure (worker.py:30-31). Instead of loading fields with NumPy
    (worker.py:53-63), frames are checked by their header line. Every check runs,
    and the first failure in worker order classifies the run.
    """
    work = Path(work_dir).resolve()
    result = {"classification": None, "reason": "", "qoi": None, "frames": [],
              "verification": {"verifier": VERIFIER, "status": "failed", "checks": []}}
    try:
        case_dir, folder = _case_folder(work, case_dir)
        case = read_case(folder, work)
    except MuproError as exc:
        return {**result, "classification": "configuration", "reason": str(exc)}
    checks = result["verification"]["checks"]
    failures = []

    def add(check_id, message, classification=None):
        checks.append({"id": check_id, "status": "fail" if classification else "pass", "message": message})
        if classification:
            failures.append((classification, message))

    final = case["start_step"] + case["steps"]
    try:
        completion = json.loads((folder / "mupro_completion.json").read_text(encoding="utf-8"),
                                parse_constant=_reject_constant)
        if completion == {"app": "muFerro", "completed_steps": case["steps"], "final_step": final}:
            add("completion", f"muFerro completed {case['steps']} steps")
        else:
            add("completion", "Native completion does not match the requested case", "incomplete_result")
    except (OSError, ValueError) as exc:
        add("completion", f"Cannot read mupro_completion.json: {exc}", "invalid_result")

    rows = []
    try:
        for line in (folder / "energy_out.dat").read_text(encoding="utf-8").splitlines()[1:]:
            match = ENERGY_ROW.fullmatch(line)
            if not match:
                raise MuproError("Malformed energy row", "invalid_result")
            values = [fortran_float(v) for v in match[2].split()]
            if len(values) != 5 or not all(math.isfinite(v) for v in values):
                raise MuproError("Missing or non-finite energy values", "numerical_failure")
            rows.append((int(match[1]), values))
        if [row[0] for row in rows] != list(range(case["start_step"] + 1, final + 1)):
            raise MuproError("Energy trace steps are incomplete, duplicated or stale", "incomplete_result")
        add("energy", f"{len(rows)} finite energy rows")
    except MuproError as exc:
        add("energy", str(exc), exc.classification)
    except (OSError, ValueError) as exc:
        add("energy", f"Cannot read energy_out.dat: {exc}", "invalid_result")

    expected = [{"step": case["start_step"] + step, "completed_steps": step, "total_steps": case["steps"]}
                for step in range(1, case["steps"] + 1)]
    try:
        text = (folder / "mupro_progress.jsonl").read_text(encoding="utf-8")
        if [json.loads(line) for line in text.splitlines()] == expected:
            add("progress", f"{len(expected)} progress records")
        else:
            add("progress", "Native progress is incomplete or stale", "incomplete_result")
    except (OSError, ValueError) as exc:
        add("progress", f"Cannot read mupro_progress.jsonl: {exc}", "invalid_result")

    headers, prefix = {}, "" if case_dir == "." else case_dir + "/"
    for path in folder.glob("*.dat"):
        match = FRAME.search(path.name)
        if match:
            headers[path.name] = header = _header(path)
            result["frames"].append({"stem": match[1], "step": int(match[2]),
                                     "components": header[1] if header else None, "path": prefix + path.name})
    result["frames"].sort(key=lambda frame: (frame["stem"], frame["step"]))
    wanted = expected_frames(case)
    missing = sorted(set(wanted) - set(headers))
    wrong_grid = sorted(name for name, header in headers.items() if header is None or header[0] != case["grid"])
    wrong_components = sorted(name for name, count in wanted.items()
                              if headers.get(name) and headers[name][1] != count)
    if missing:
        add("frames", "Required field frames are missing: " + ", ".join(missing[:5]), "incomplete_result")
    elif wrong_grid:
        add("frames", "Field grid mismatch: " + ", ".join(wrong_grid[:5]), "invalid_result")
    elif wrong_components:
        add("frames", "Field component mismatch: " + ", ".join(wrong_components[:5]), "invalid_result")
    else:
        add("frames", f"{len(wanted)} required frames with grid {case['grid']}")

    if failures:
        result.update(classification=failures[0][0], reason=failures[0][1])
    else:
        result["verification"]["status"] = "passed"
        result["qoi"] = {"total_energy": rows[-1][1][-1], "step": final}
    return result


def source_env(scripts, env):
    """Source bash scripts and return the resulting environment; it is never printed."""
    # The marker shows every script returned: one that calls `exit 0` ends bash before `env -0`.
    command = ["bash", "-c", 'for f in "$@"; do . "$f" >/dev/null 2>&1 || '
               '{ rc=$?; printf "stk-fail\\0%s\\0%s\\0" "$f" "$rc"; exit 97; }; done; printf "stk-env\\0"; env -0',
               "stk-env", *scripts]
    try:
        completed = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MuproError(f"Cannot source the MuPRO environment scripts: {exc}") from exc
    items = os.fsdecode(completed.stdout).split("\0")
    if completed.returncode == 97 and items[0] == "stk-fail" and len(items) > 2:
        raise MuproError(f"MuPRO environment script {items[1]} returned {items[2]}")
    if completed.returncode:
        raise MuproError(f"Sourcing the MuPRO environment scripts failed (exit {completed.returncode}): "
                         + ", ".join(scripts))
    if items[0] != "stk-env":
        raise MuproError("A MuPRO environment script called exit instead of returning: " + ", ".join(scripts))
    return dict(item.split("=", 1) for item in items[1:] if "=" in item)


def resolve_program(program, prefix, env):
    if os.sep in program:
        path = Path(os.path.abspath(program))
    elif prefix and (Path(prefix) / "bin" / program).is_file():
        path = Path(prefix) / "bin" / program
    else:
        found = shutil.which(program, path=env.get("PATH", ""))
        if not found:
            raise MuproError(f"MuPRO program {program} not found; pass --sdk-prefix or set MUPRO_SDK_PREFIX")
        path = Path(found)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise MuproError(f"MuPRO program is not an executable file: {path}")
    return path.absolute()


def _env_scripts(args):
    return args.env_scripts or [p for p in os.environ.get("STK_MUPRO_ENV_SCRIPTS", "").split(os.pathsep) if p]


def _prepare_env(args):
    scripts = _env_scripts(args)
    env = source_env(scripts, os.environ.copy()) if scripts else os.environ.copy()
    if args.license_dir:
        env["MUPROROOT"] = os.path.abspath(args.license_dir)
    return scripts, env


def _launch_command(program, ranks, threads, launcher, env):
    if launcher == "auto":
        # A single rank runs as an MPI singleton (no PMI listener). Several ranks use
        # mpiexec, also inside a Slurm/PBS allocation, which Hydra detects. srun is an
        # explicit choice: Intel MPI then needs I_MPI_PMI_LIBRARY from the site.
        launcher = "none" if ranks == 1 else "mpiexec"
    if launcher == "none":
        if ranks > 1:
            raise MuproError("--launcher none runs a single rank; use mpiexec or srun for several ranks")
        return launcher, [str(program)]
    # Hydra opens its listener for any rank count, so an explicit one-rank mpiexec is guarded too.
    if launcher == "mpiexec" and not env.get("SLURM_JOB_ID") and not env.get("PBS_JOBID") \
            and env.get("STK_MUPRO_ALLOW_LOCAL_MPI") != "1":
        raise MuproError("Refusing local mpiexec outside a Slurm/PBS allocation: Intel MPI's Hydra listens on "
                         "0.0.0.0 while the job runs. Run one rank directly (--launcher auto) or submit to a "
                         "scheduler. On a host that is not externally reachable, the operator may set "
                         "STK_MUPRO_ALLOW_LOCAL_MPI=1 in the Runtime service environment; tasks cannot set it.")
    # Outside an allocation srun would queue a separate Slurm job, billed apart from this task.
    if launcher == "srun" and not env.get("SLURM_JOB_ID"):
        raise MuproError("--launcher srun runs inside a Slurm allocation; submit with --backend slurm")
    path = shutil.which(launcher, path=env.get("PATH", ""))
    if not path:
        raise MuproError(f"{launcher} not found on PATH; source the Intel MPI environment with --env-script")
    if launcher == "srun":
        env["SRUN_CPUS_PER_TASK"] = str(threads)
        return launcher, [path, f"--ntasks={ranks}", f"--cpus-per-task={threads}", str(program)]
    return launcher, [path, "-n", str(ranks), str(program)]


def _stage_example(prefix, folder):
    if not prefix:
        raise MuproError("--example needs the SDK prefix; pass --sdk-prefix or set MUPRO_SDK_PREFIX")
    if (folder / "input.toml").exists():
        raise MuproError("--example would overwrite the case's input.toml")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("input.toml", "material.toml"):
            shutil.copyfile(Path(prefix) / EXAMPLES / name, folder / name)
    except OSError as exc:
        raise MuproError(f"Cannot stage the SDK example case: {exc}") from exc


def _run_solver(command, folder, env, monitor):
    """Run the solver to completion while the monitor tails its outputs; returns its exit code.

    Like subprocess.run, the child is killed if anything interrupts the wait.
    """
    try:
        process = subprocess.Popen(command, cwd=folder, env=env, stdin=subprocess.DEVNULL)
    except OSError as exc:
        raise MuproError(f"Cannot start {command[0]}: {exc}", "launch_failed") from exc
    try:
        monitor.watch()
        return process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        monitor.stop(process.returncode)


def run(args):
    from .monitor import MuferroMonitor
    work = Path.cwd().resolve()
    record = {"schema_version": 1, "app": "muFerro", "state": "running", "classification": None, "reason": "",
              "case_dir": args.case_dir, "case": None,
              "layout": {"ranks": args.ranks, "threads_per_rank": args.threads_per_rank, "launcher": None},
              "command": [], "program": {"path": None, "sha256": None}, "sdk_prefix": None, "env_scripts": [],
              "environment": {key: None for key in ENVIRONMENT}, "exit_code": None,
              "started_at": now(), "finished_at": None,
              "verification": {"verifier": VERIFIER, "status": "not_run", "checks": []}, "qoi": None, "frames": []}
    # Adapt mode (docs/specs/stk-events-v1.md): this launcher is the only writer of
    # $STK_MONITOR_PATH; a no-op outside the STK Runtime. It never changes the outcome.
    monitor = MuferroMonitor()
    try:
        case_dir, folder = _case_folder(work, args.case_dir)
        record["case_dir"] = case_dir
        record["env_scripts"], env = _prepare_env(args)
        env.pop(MONITOR_ENV, None)  # one writer per events file: the solver never gets the path
        # MuPRO keeps the licence directory in a character(len=256); its contents are never read here.
        if len(os.fsencode(env.get("MUPROROOT", ""))) > 256:
            raise MuproError("MUPROROOT must be at most 256 characters")
        prefix = args.sdk_prefix or env.get("MUPRO_SDK_PREFIX")
        prefix = record["sdk_prefix"] = os.path.abspath(prefix) if prefix else None
        if args.example:
            _stage_example(prefix, folder)
        elif not folder.is_dir():
            raise MuproError(f"Case directory not found: {case_dir}")
        case = record["case"] = read_case(folder, work)
        check_case(case, folder, args.ranks)
        env["OMP_NUM_THREADS"] = env["MKL_NUM_THREADS"] = str(args.threads_per_rank)
        program = resolve_program(args.program, prefix, env)
        launcher, command = _launch_command(program, args.ranks, args.threads_per_rank, args.launcher, env)
        try:
            digest = sha256(program)
        except OSError as exc:
            raise MuproError(f"Cannot read the MuPRO program: {exc}") from exc
        record["layout"]["launcher"] = launcher
        record.update(command=command, program={"path": str(program), "sha256": digest},
                      environment={key: env.get(key) for key in ENVIRONMENT})
        atomic_json(work / RESULT, record)
        monitor.started(folder, case_dir, case, args.ranks)
        record["exit_code"] = _run_solver(command, folder, env, monitor)
        if record["exit_code"]:
            raise MuproError(f"muFerro exited with code {record['exit_code']}; inspect stdout.log and stderr.log",
                             "solver_failed")
        record.update(verify_run(work, case_dir))
        record["state"] = "succeeded" if record["verification"]["status"] == "passed" else "failed"
    except MuproError as exc:
        record.update(state="failed", classification=exc.classification, reason=str(exc))
    except Exception as exc:  # Last resort: the task must still get its stk-mupro.json.
        record.update(state="failed", classification="configuration", reason=f"{type(exc).__name__}: {exc}")
    record["finished_at"] = now()
    atomic_json(work / RESULT, record)
    monitor.finish(record)
    if record["state"] == "succeeded":
        print(f"MuPRO muFerro succeeded: verification passed, total_energy {record['qoi']['total_energy']} "
              f"at step {record['qoi']['step']}")
        return 0
    print(f"MuPRO muFerro failed ({record['classification']}): {record['reason']}", file=sys.stderr)
    # 2: configuration or launch failure, the solver did not run; 3: it ran and failed or did not verify.
    return 2 if record["exit_code"] is None else 3


def _print_checks(checks):
    for item in checks:
        print(f"[{item['status'].upper()}] {item['id']}: {item['message']}")


def verify(args):
    result = verify_run(args.work, args.case_dir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_checks(result["verification"]["checks"])
        print(f"Verification {result['verification']['status']}"
              + (f" ({result['classification']}): {result['reason']}" if result["classification"] else ""))
    return 0 if result["verification"]["status"] == "passed" else 3


def check(args):
    """Diagnose this node's MuPRO toolchain; licence contents are never read."""
    checks = []

    def add(check_id, status, message):
        checks.append({"id": check_id, "status": status, "message": message})

    scripts = _env_scripts(args)
    env = os.environ.copy()
    if scripts:
        try:
            env = source_env(scripts, env)
            add("env_scripts", "pass", f"Sourced {len(scripts)} environment script(s)")
        except MuproError as exc:
            add("env_scripts", "fail", str(exc))
    if args.license_dir:
        env["MUPROROOT"] = os.path.abspath(args.license_dir)
    prefix = args.sdk_prefix or env.get("MUPRO_SDK_PREFIX")
    if not prefix:
        add("sdk_prefix", "fail", "Pass --sdk-prefix or set MUPRO_SDK_PREFIX")
    elif not Path(prefix).is_dir():
        add("sdk_prefix", "fail", f"SDK prefix is not a directory: {prefix}")
    else:
        add("sdk_prefix", "pass", prefix)
    program = None
    try:
        program = resolve_program(args.program, prefix, env)
        add("program", "pass", str(program))
    except MuproError as exc:
        add("program", "fail", str(exc))
    ldd = shutil.which("ldd")
    if program is None or not ldd:
        add("shared_libraries", "skip", "No program to inspect" if program is None else "ldd is not available")
    else:
        try:
            completed = subprocess.run([ldd, str(program)], env=env, stdin=subprocess.DEVNULL,
                                       capture_output=True, text=True, errors="replace", timeout=60)
            missing = [line.split("=>")[0].strip() for line in completed.stdout.splitlines() if "not found" in line]
            if missing:
                add("shared_libraries", "fail", "Missing shared libraries: " + ", ".join(missing))
            elif completed.returncode:
                add("shared_libraries", "skip", "ldd cannot inspect the program (not a dynamic executable)")
            else:
                add("shared_libraries", "pass", "All shared libraries resolve")
        except (OSError, subprocess.TimeoutExpired) as exc:
            add("shared_libraries", "fail", f"ldd failed: {exc}")
    launcher = shutil.which("mpiexec", path=env.get("PATH", ""))
    add("mpi_launcher", "pass" if launcher else "warn",
        launcher or "mpiexec not found on PATH; multi-rank runs need the Intel MPI environment")
    root = env.get("MUPROROOT")
    if not root:
        add("license_dir", "warn", "MUPROROOT is not set. Release builds check a licence on every rank.")
    elif len(os.fsencode(root)) > 256:
        add("license_dir", "fail", "MUPROROOT must be at most 256 characters")
    elif not Path(root).is_dir():
        add("license_dir", "fail", "MUPROROOT is not a directory")
    else:
        add("license_dir", "pass", "MUPROROOT is a directory (contents not read)")
    example = Path(prefix) / EXAMPLES / "input.toml" if prefix else None
    add("example_case", "pass" if example and example.is_file() else "warn",
        str(example) if example and example.is_file() else "The SDK example case is not installed")
    report = {"ok": not any(item["status"] == "fail" for item in checks), "checks": checks}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_checks(checks)
    return 0 if report["ok"] else 1


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m suan.mupro", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    launch = commands.add_parser("run", help="Launch muFerro in the task work dir and verify its outputs.")
    launch.add_argument("--program", default="muFerro", help="Program name under <prefix>/bin or on PATH, or a path.")
    launch.add_argument("--case-dir", default=".", help="Case directory relative to the work dir.")
    launch.add_argument("--example", action="store_true", help="Stage the SDK example case into the case dir.")
    launch.add_argument("--ranks", type=_positive, default=1, help="Total MPI ranks.")
    launch.add_argument("--threads-per-rank", type=_positive, default=1, help="OpenMP/MKL threads per rank.")
    launch.add_argument("--launcher", choices=LAUNCHERS, default="auto",
                        help="auto: direct for 1 rank, else mpiexec. srun with Intel MPI needs I_MPI_PMI_LIBRARY.")
    launch.add_argument("--sdk-prefix", help="MuPRO SDK install prefix (default: MUPRO_SDK_PREFIX).")
    launch.add_argument("--env-script", dest="env_scripts", action="append", default=[],
                        help="Bash script to source first (default: STK_MUPRO_ENV_SCRIPTS).")
    launch.add_argument("--license-dir", help="Licence directory path, exported as MUPROROOT.")
    launch.set_defaults(handler=run)
    audit = commands.add_parser("verify", help="Check a finished run directory against MuPRO's output contract.")
    audit.add_argument("--work", default=".", help="Task work dir.")
    audit.add_argument("--case-dir", default=".", help="Case directory relative to the work dir.")
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(handler=verify)
    doctor = commands.add_parser("check", help="Diagnose this node's MuPRO toolchain.")
    doctor.add_argument("--sdk-prefix")
    doctor.add_argument("--program", default="muFerro")
    doctor.add_argument("--env-script", dest="env_scripts", action="append", default=[])
    doctor.add_argument("--license-dir")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=check)
    args = parser.parse_args(argv)
    return args.handler(args)
