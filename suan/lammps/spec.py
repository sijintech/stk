"""Client-side TaskSpec builder for LAMMPS runs; safe on any client OS."""

from suan.runtime.launch import LAUNCHERS
from suan.runtime.models import BACKENDS, relative_path


def lammps_spec(workspace_id, *, case_dir="case", inputs=None, ranks=1, threads_per_rank=1, nodes=1, backend="local",
                program=None, launcher="auto", walltime_seconds=None, memory_mb=None, queue=None, account=None, name=""):
    """Return TaskSpec keyword arguments; the Runtime validates them on submission.

    The script and its parameters are read from ``<case_dir>/stk-lammps-input.json`` (written when the run is
    prepared), so no case text reaches the command line. ``program`` is a LAMMPS executable name or path on the
    compute node; by default the launcher uses the STK module registry there, then ``lmp``/``lmp_mpi``/``lmp_serial``."""
    for key, value in (("ranks", ranks), ("threads_per_rank", threads_per_rank), ("nodes", nodes)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{key} must be a positive integer")
    case_dir = "." if case_dir == "." else relative_path(case_dir)
    if backend not in BACKENDS:
        raise ValueError("backend must be local, pbs or slurm")
    if backend == "local" and nodes > 1:
        raise ValueError("Local LAMMPS jobs run on one node")
    # Cluster time is billed in core-hours, so every job needs a limit.
    if backend != "local" and walltime_seconds is None:
        raise ValueError("Cluster LAMMPS jobs require walltime_seconds")
    if launcher not in LAUNCHERS:
        raise ValueError("launcher must be auto, none, mpiexec or srun")
    if program is not None and (not isinstance(program, str) or not 1 <= len(program) <= 1024 or "\x00" in program):
        raise ValueError("program must be a LAMMPS executable name or path")
    argv = ["{python}", "-m", "suan.lammps", "run", "--case-dir", case_dir,
            "--ranks", "{ranks}", "--threads-per-rank", "{threads_per_rank}"]
    if program:
        argv += ["--program", program]
    if launcher != "auto":
        argv += ["--launcher", launcher]
    resources = {"ranks": ranks, "threads_per_rank": threads_per_rank}
    if nodes > 1:
        resources["nodes"] = nodes
    for key, value in (("walltime_seconds", walltime_seconds), ("memory_mb", memory_mb),
                       ("queue", queue), ("account", account)):
        if value is not None:
            resources[key] = value
    return {"workspace_id": workspace_id, "argv": argv, "backend": backend, "name": name,
            "inputs": None if inputs is None else list(inputs), "outputs": ["stk-lammps.json"], "env": {},
            "resources": resources}
