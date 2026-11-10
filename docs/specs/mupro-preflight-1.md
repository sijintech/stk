# MuPRO local preflight observation v1

`suan mupro check --json` emits `stk.mupro-preflight/1`, a point-in-time observation of
the calling process's configured prerequisites. Run it on the machine whose environment
is being inspected. It does not query a Runtime, select a node or authorize execution.

The observer reuses the checks behind `python -m suan.mupro check`. That existing command,
its `{ok, checks}` diagnostic JSON, messages and exit codes retain their meaning. Its
`ok` means that no diagnostic was classified as `fail`; it is not a successful solver run.

## Command

```text
suan mupro check [--sdk-prefix PATH] [--program NAME_OR_PATH]
                 [--env-script PATH ...] [--license-dir PATH] [--json]
```

Options describe this local process, rather than paths on a selected Runtime. Defaults
and environment-script precedence match the existing module command:
`MUPRO_SDK_PREFIX`, `STK_MUPRO_ENV_SCRIPTS` and `MUPROROOT`. Repeated `--env-script`
options replace the configured script list. Configured trusted bash scripts are sourced,
so this command is an explicit local diagnostic, not a passive metadata read that can be
inserted into `graph.meta`. Script effects belong to that trusted local configuration.

The checker itself does not invoke MuPRO, an MPI launcher, a case or a licence checkout.
It locates configured paths, sources the configured scripts, and may run the local `ldd`
to inspect a located program. It does not inspect licence directory contents or install
dependencies. It does not audit what a configured script does or query past runs.

## JSON

The object has exactly these fields:

| Field | Meaning |
|---|---|
| `schema` | Exactly `stk.mupro-preflight/1`. |
| `scope` | Exactly `local_process`; never a remote-node capability or heartbeat. |
| `producer` | `{component: "suan.mupro", distribution_version: string|null}`. The installed STK package version, or null when unavailable. It is not a MuPRO version. |
| `process_id` | Positive integer PID of the process collecting this observation. |
| `started_at`, `observed_at` | Time before collection and time after collection, from the local UTC clock in ISO 8601 form. |
| `summary` | `checks_failed`, `checks_incomplete` or `checks_passed`, as defined below. |
| `checks` | The seven ordered `{id, status}` records below. No diagnostic messages. |
| `unverified` | Exactly `{program_version: "unobserved", license_checkout: "not_checked", solver_execution: "not_run"}`. These activities are not performed by the checker. |

The projected object includes no program paths, script paths, licence paths, host names,
environment values, raw errors or command output. Detailed paths and diagnostics remain
available through the original local module command.

| Ordered check ID | What a `pass` establishes | Other status |
|---|---|---|
| `env_scripts` | The configured environment scripts returned successfully. | `not_configured` if none; `fail` on sourcing failure. |
| `sdk_prefix` | The configured prefix resolves to a directory. | `fail` if absent or not a directory. |
| `program` | An executable file was located by the existing resolver. | `fail` if it cannot be located. It is not identified or executed as MuPRO. |
| `shared_libraries` | The selected `ldd` invocation found no missing libraries. | `skip` if no program/ldd or not inspectable; `fail` for missing libraries or diagnostic failure. |
| `mpi_launcher` | `mpiexec` was found on the prepared environment's PATH. | `warn` if not found; no launcher is started. |
| `license_dir` | The configured licence path resolves to a directory and passes the existing path-length check. | `warn` if unset; `fail` if invalid. No file presence, contents or licence validity is established. |
| `example_case` | All expected example paths resolve to files. | `warn` for missing files; contents and scientific validity are not checked. |

Statuses are fixed strings: `pass`, `fail`, `warn`, `skip`, plus `not_configured` only
for `env_scripts`. `summary` is `checks_failed` when any check fails. Otherwise it is
`checks_incomplete` when any check warns or skips, and `checks_passed` otherwise.
An unconfigured optional script list alone does not make the checks incomplete.

All three summaries retain the `unverified` object. Finding an executable or an empty
licence directory never establishes a software version, a valid licence, or a runnable
case. Actual execution is evidenced separately by a task and its verified result.

Exit status is 1 for `checks_failed`, and 0 for either other summary. A zero exit status
does not imply every check passed. Argument errors use the CLI's usual nonzero status.
Without `--json`, the same observation is printed as fixed status lines.

## Compatibility and scope

This is a new local CLI observation. Existing submit/result/verify commands, task
identity, environment setup and per-run verification contracts are unchanged. There is
no new Runtime, Hub, desktop RPC, placement rule or Agent permission. Consumers must
not label a desktop-side observation as a selected remote machine's readiness.

Implementation: [collector](../../suan/mupro/run.py), [CLI](../../suan/mupro/cli.py).
Node setup and the existing detailed diagnostic are described in the
[MuPRO Runtime guide](../runtime-mupro.md).
