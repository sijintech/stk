"""How an engine launcher starts its program on a compute node: directly for one rank, else through MPI.

Shared by the MuPRO and LAMMPS launchers. MPICH's and Intel MPI's Hydra (``mpiexec``) listens on 0.0.0.0 while a job
runs, so local mpiexec outside a Slurm/PBS allocation is refused unless the operator sets ``STK_ALLOW_LOCAL_MPI=1``
(or the older ``STK_MUPRO_ALLOW_LOCAL_MPI=1``) in the Runtime environment. That guards against accidental local runs;
it is not an access control, since Runtime clients can run any command.
"""
import shutil

LAUNCHERS = ("auto", "none", "mpiexec", "srun")


def mpi_command(program, ranks, threads, launcher, env, *, error, mpi="MPI's Hydra",
                missing_hint="put the MPI launcher on PATH"):
    """(launcher, argv) for ``ranks`` copies of ``program``; ``error`` is the launcher's configuration error class.
    ``env`` gains SRUN_CPUS_PER_TASK for srun."""
    if launcher == "auto":
        # A single rank runs as an MPI singleton (no PMI listener). Several ranks use mpiexec, also inside a
        # Slurm/PBS allocation, which Hydra detects. srun is an explicit choice.
        launcher = "none" if ranks == 1 else "mpiexec"
    if launcher == "none":
        if ranks > 1:
            raise error("--launcher none runs a single rank; use mpiexec or srun for several ranks")
        return launcher, [str(program)]
    # Hydra opens its listener for any rank count, so an explicit one-rank mpiexec is guarded too.
    if launcher == "mpiexec" and not env.get("SLURM_JOB_ID") and not env.get("PBS_JOBID") \
            and "1" not in (env.get("STK_ALLOW_LOCAL_MPI"), env.get("STK_MUPRO_ALLOW_LOCAL_MPI")):
        raise error(f"Refusing local mpiexec outside a Slurm/PBS allocation: {mpi} listens on "
                    "0.0.0.0 while the job runs. Run one rank directly (--launcher auto) or submit to a "
                    "scheduler. On a host that is not externally reachable, the operator may set "
                    "STK_ALLOW_LOCAL_MPI=1 in the Runtime service environment; tasks cannot set it.")
    # Outside an allocation srun would queue a separate Slurm job, billed apart from this task.
    if launcher == "srun" and not env.get("SLURM_JOB_ID"):
        raise error("--launcher srun runs inside a Slurm allocation; submit with --backend slurm")
    path = shutil.which(launcher, path=env.get("PATH", ""))
    if not path:
        raise error(f"{launcher} not found on PATH; {missing_hint}")
    if launcher == "srun":
        env["SRUN_CPUS_PER_TASK"] = str(threads)
        return launcher, [path, f"--ntasks={ranks}", f"--cpus-per-task={threads}", str(program)]
    return launcher, [path, "-n", str(ranks), str(program)]
