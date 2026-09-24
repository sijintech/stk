"""Public JSON contracts shared by desktop, CLI, MCP and workers."""

from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Dict, List, Optional
import re

TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
BACKENDS = frozenset({"local", "pbs", "slurm"})
RESOURCES = frozenset({"cpus", "nodes", "memory_mb", "walltime_seconds", "gpus", "queue", "account",
                       "ranks", "threads_per_rank"})
MPI_RESOURCES = frozenset({"ranks", "threads_per_rank"})
# Scheduler allocation markers and the operator's local-MPI opt-in come only from the
# Runtime service or scheduler environment (docs/runtime-mupro.md); the worker sets the
# monitoring events path and task ID (docs/specs/stk-events-v1.md).
RESERVED_ENV = ("SLURM_JOB_ID", "PBS_JOBID", "STK_MUPRO_ALLOW_LOCAL_MPI", "STK_MONITOR_PATH", "STK_TASK_ID")


def layout(resources):
    """Process layout implied by validated resources.

    Legacy specs (no ranks/threads_per_rank) run one process per node with
    `cpus` threads. MPI specs run `ranks` processes spread evenly over `nodes`,
    each with `threads_per_rank` threads (default 1).
    """
    nodes = resources.get("nodes", 1)
    if MPI_RESOURCES & set(resources):
        ranks = resources.get("ranks", 1)
        threads = resources.get("threads_per_rank", 1)
        return {"mpi": True, "nodes": nodes, "ranks": ranks, "ranks_per_node": ranks // nodes,
                "threads_per_rank": threads, "cpus_per_node": ranks // nodes * threads}
    cpus = resources.get("cpus", 1)
    return {"mpi": False, "nodes": nodes, "ranks": 1, "ranks_per_node": 1,
            "threads_per_rank": cpus, "cpus_per_node": cpus}


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("A nonempty POSIX relative path is required")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in value or value == ".":
        raise ValueError("Path must stay inside the workspace")
    return str(path)


@dataclass
class Workspace:
    id: str
    name: str
    created_at: str


@dataclass
class TaskSpec:
    workspace_id: str
    argv: List[str]
    backend: str = "local"
    name: str = ""
    inputs: Optional[List[str]] = None
    outputs: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    resources: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.workspace_id, str) or not re.fullmatch(r"[a-f0-9]{32}", self.workspace_id):
            raise ValueError("Invalid workspace ID")
        if not isinstance(self.argv, list) or not self.argv or any(
            not isinstance(s, str) or "\x00" in s for s in self.argv
        ) or not self.argv[0]:
            raise ValueError("argv must be a nonempty list of strings, not a shell command")
        if self.backend not in BACKENDS:
            raise ValueError("backend must be local, pbs or slurm")
        if not isinstance(self.name, str) or len(self.name) > 200:
            raise ValueError("Task name must be at most 200 characters")
        for key in ("inputs", "outputs"):
            paths = getattr(self, key)
            if paths is None and key == "inputs":
                continue
            if not isinstance(paths, list):
                raise ValueError(f"{key} must be a list of relative file paths")
            setattr(self, key, list(dict.fromkeys(relative_path(p) for p in paths)))
        if not isinstance(self.env, dict) or any(
            not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", k)
            or not isinstance(v, str) or "\x00" in v for k, v in self.env.items()
        ):
            raise ValueError("env must map environment variable names to strings")
        if set(RESERVED_ENV) & set(self.env):
            raise ValueError("env must not set " + ", ".join(k for k in RESERVED_ENV if k in self.env)
                             + "; they come from the Runtime service or scheduler environment")
        if not isinstance(self.resources, dict) or set(self.resources) - RESOURCES:
            raise ValueError("Unknown resource option")
        for key, value in self.resources.items():
            if key in {"queue", "account"}:
                if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.@/-]+", value):
                    raise ValueError(f"Invalid {key}")
            elif isinstance(value, bool) or not isinstance(value, int) or not (0 if key == "gpus" else 1) <= value <= 2147483647:
                raise ValueError(f"{key} must be a positive integer")
        # Never write defaults into resources: to_dict() feeds the idempotency hash.
        if MPI_RESOURCES & set(self.resources):
            if "cpus" in self.resources:
                raise ValueError("Use cpus for one process per node, or ranks/threads_per_rank for MPI, not both")
            if self.resources.get("ranks", 1) % self.resources.get("nodes", 1):
                raise ValueError("ranks must be a multiple of nodes (equal ranks per node)")
        if self.backend == "local" and (self.resources.get("nodes", 1) != 1 or self.resources.get("gpus", 0) or "queue" in self.resources or "account" in self.resources):
            raise ValueError("Local tasks do not allocate nodes, GPUs, queues or accounts")

    def to_dict(self):
        return asdict(self)


@dataclass
class TaskRecord:
    id: str
    spec: Dict
    state: str
    created_at: str
    updated_at: str
    backend_id: Optional[str] = None
    exit_code: Optional[int] = None
    reason: str = ""
    cancel_requested: bool = False


@dataclass
class Artifact:
    path: str
    size: int
    sha256: str
    media_type: str
