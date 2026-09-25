# STK monitoring events v1

> 中文摘要：本文档定义监控事件 v1：模拟程序（或旧程序的适配器）向 `$STK_MONITOR_PATH`（由 Runtime worker 设为
> `<task_dir>/events.jsonl`，位于 work/ 之外、不可被任务规格覆盖）逐行追加 JSON 事件；信封为 `{v, seq, ts, type, src, data}`，
> 每行 ≤ 16 KiB，非有限数写成字符串；单写者、仅 MPI rank 0 写、写失败绝不影响计算；Runtime 以 `GET /v1/tasks/{id}/events` 增量读取。

Status: frozen for Milestone 1 (Phase A). Schema: `suan/contracts/schemas/event-1.schema.json`.
Implementation (Phase B4): `suan/monitor/{events,emit,reader}.py` (standard library only), the
Runtime worker/service/server/client, and the muFerro adapter `suan/mupro/monitor.py`. The C,
Fortran and standalone Python SDK is Milestone 7.

## 1. File transport

- **Location.** The Runtime worker sets `STK_MONITOR_PATH=<task_dir>/events.jsonl` (and
  `STK_TASK_ID`) **after** applying the TaskSpec `env`, and `STK_MONITOR_PATH` joins
  `suan.runtime.models.RESERVED_ENV`, so a TaskSpec can neither set nor spoof it. The file is outside
  `work/` (never an artifact), next to `stdout.log`, on the shared storage batch workers already use.
- **One writer per file.** Exactly one producer owns the path. A wrapper either *delegates* (passes
  the variable to the solver and does not write) or *adapts* (removes it from the solver's
  environment and writes adapter events itself). A delegating wrapper may write only after the child
  exits.
- **MPI rank 0 only.** Emitters detect the rank from `PMI_RANK`, `PMIX_RANK`,
  `OMPI_COMM_WORLD_RANK`, `SLURM_PROCID`, `MV2_COMM_WORLD_RANK` (first set wins) or an explicit
  argument; other ranks are no-ops.
- **Writing.** Open once with `O_APPEND`; each event is one `write()` of one complete line ending in
  `\n`. No fsync (optionally on `run.completed`).
- **Unset path** → every call is a no-op; programs behave the same outside STK.
- **Never fatal.** An I/O error disables the emitter (reported once on stderr and by return value);
  it never raises into or aborts the simulation.
- **Reading.** Readers consume only complete `\n`-terminated lines, skip invalid or oversized lines
  (reporting their byte offsets) and reopen the file on every poll (NFS only guarantees fresh data on
  open/close). Ordering is by file offset; `ts` is advisory (clock skew on compute nodes).

## 2. Envelope

```json
{"v": 1, "seq": 42, "ts": 1790000000.125, "type": "metrics", "src": "program",
 "data": {"step": 120, "time": null, "values": {"total_energy": -1.23e-3, "elastic_energy": "NaN"}}}
```

| key | meaning |
|---|---|
| `v` | `1` |
| `seq` | integer ≥ 0, strictly increasing per file; an emitter that reopens an existing file continues after the last complete line's `seq` |
| `ts` | Unix seconds (UTC) as a float |
| `type` | one of §3, or a custom `x.<name>` |
| `src` | `program` (the solver through the SDK), `adapter` (a legacy adapter such as the muFerro tail), `launcher`, `runtime` |
| `data` | object, per type |

- One JSON object per line, UTF-8, at most **16 KiB** including the newline. Emitters truncate
  `message.text` to fit and drop (with a stderr note) any other event that would not fit.
- Non-finite numbers are written as the strings `"NaN"`, `"Inf"`, `"-Inf"` (NaN detection is a
  first-class feature). Optional numbers may be `null`.
- Consumers ignore unknown types and unknown `data` keys.

## 3. Event types

| type | `data` | notes |
|---|---|---|
| `run.started` | `app` (req), `version?`, `total_steps?`, `ranks?`, `host?`, `pid?` | once |
| `run.phase` | `name`, `state` (`begin`/`end`), `elapsed_s?` | phase timing |
| `progress` | `step?`, `completed_steps?`, `total_steps?`, `fraction?` (0–1), `time?`, `time_end?`, `time_unit?`, `phase?`, `eta_s?`, `indeterminate?` | coalesced to ≤ 1/s; the final value is always written |
| `metric.declare` | `name`, `unit`, `quantity?`, `label?`, `group?` | once per series, before its first value |
| `metrics` | `step?`, `time?`, `values {name: number \| "NaN" \| "Inf" \| "-Inf"}` | never dropped |
| `frame` | `dataset`, `step`, `path` (relative to `work/`), `time?`, `selector?`, `fields?`, `reader?`, `components?`, `size?`, `sha256?` | the frame is **published**: complete and immutable |
| `checkpoint` | `step`, `path`, `restartable?` | |
| `artifact` | `path`, `role`, `media_type?` | |
| `message` | `level` (`debug`/`info`/`warning`/`error`), `text` (≤ 8192 chars), `code?` | |
| `usage` | `cpu_s?`, `rss_peak_bytes?`, `gpu?` | |
| `verification` | `verifier`, `status` (`passed`/`failed`/`pending`/`skipped`/`unknown`), `failed_checks[]` | written by the launcher |
| `run.completed` | `status` (`succeeded`/`failed`/`cancelled`), `classification?`, `reason?` | the program's own claim; the Runtime's `finished.json` and verification decide |

Paths are POSIX, relative, without `..`. Metric names match `^[A-Za-z0-9_.:-]{1,128}$`; units follow
`stk-data-format-v1.md` §4 (`unspecified`, `normalized`, UCUM).

Invariant: *stk.result/1 = fold(events) + files + verification*.

## 4. Python emitter and reader (Phase B4, standard library only)

Recommended shape (the exact module is owned by B4):

```python
from suan.monitor.emit import Emitter
with Emitter(src="adapter") as mon:            # path from $STK_MONITOR_PATH; no-op when unset
    mon.started("muFerro", total_steps=1000, ranks=4)
    mon.declare("total_energy", "normalized", label="Total Energy")
    mon.progress(step=120, total_steps=1000)
    mon.metrics({"total_energy": -1.4}, step=120)
    mon.frame("Polar", 1000, "Polar.00001000.dat", reader="mupro.dat@1", components=3)
    mon.completed("succeeded")
```

`STK_MONITOR_FAKE_TIME` (float seconds) fixes `ts` for golden tests.
`suan.monitor.reader.read_events(path, offset=0, limit=1048576)` returns the structure of §5.

## 5. Runtime exposure (additive to Runtime API v1)

- `GET /v1/tasks/{id}/events?offset=0&limit=1048576` → `{"events": [...], "offset", "next_offset",
  "size", "terminal", "invalid": [{"offset", "reason"}]}`. `limit` is in bytes (1 … 1 MiB); only
  whole lines are returned (`next_offset` is the byte after the last whole line consumed); an offset
  beyond the file size is an error; a missing file returns no events. Follows the `service.logs()`
  offset pattern.
- `GET /v1/health` gains `"features": ["events"]`.
- `RuntimeClient.events(task_id, offset=0, limit=1048576) -> dict` (same structure).
- Control action `task.events {task_id, offset, limit}` and MCP tool `get_task_events` return the
  same structure (Phase C2).
- Tasks queued before an upgrade run the old worker and simply produce no events.

## 6. muFerro legacy adapter (adapt mode, a thread in `python -m suan.mupro run`)

The launcher removes `$STK_MONITOR_PATH` from the solver's environment (one writer per file) and a
thread polls the case directory every 2 s. Lifecycle events (`run.started`, `verification`,
`run.completed`) have `src: "launcher"`; the events derived from native outputs have
`src: "adapter"`.

| native source | trigger | event |
|---|---|---|
| launch | before exec | `run.started {app: "muFerro", total_steps, ranks, host, pid}` (`src: "launcher"`) |
| `mupro_progress.jsonl` line `{step, completed_steps, total_steps}` | new complete line (the latest of each poll) | `progress {step, completed_steps, total_steps, fraction}`; an unreadable line → `message {warning, code: "malformed_progress"}` |
| `energy_out.dat` header, or its first row without a header | first read | `metric.declare` ×5 (`elastic_energy`, `electric_energy`, `landau_energy`, `gradient_energy`, `total_energy`; `label` from the header's right-aligned 18-character columns, else muFerro's names `Elastic Energy` … `Total Energy`; unit `normalized`, group `energy`), once |
| `energy_out.dat` row `kt: N energy: e1..e5` | new complete line | `metrics {step: N, values}`; a non-finite or unreadable value is written as `"NaN"`/`"Inf"`/`"-Inf"` plus `message {warning, code: "nonfinite_energy"}`; a row without five values → `message {warning, code: "malformed_energy_row"}` |
| `<Stem>.<step:08d>.dat` | size **and mtime** unchanged over 2 polls and progress has reached its step; after the solver exits with code 0, every remaining frame; after a non-zero exit only frames at or before the last progress step (later ones may be cut off mid-write) | `frame {dataset: Stem, step, path, reader: "mupro.dat@1", components, size}` (`path` includes the case directory) |
| `mupro_completion.json` | appears and parses (at the final pass also when unreadable) | `message {info, code: "native_completion"}`, once |
| child exit + `verify_run` | after exit (or a failure before launch) | `verification {verifier, status, failed_checks}` only when the solver was launched (the launcher's `not_run` → `skipped`); then always `run.completed {status, classification, reason}` (`src: "launcher"`) |

Warnings of one code are written at most 5 times, then one "further … suppressed" message.

The adapter never fails the run (errors go to stderr); exit codes and records of the launcher stay
identical. The same rules can replay a finished directory (`suan.mupro.monitor.replay`: every frame is
published and every event carries the emitter's own `src`). If muFerro later links the SDK itself,
the launcher switches to delegate mode and the adapter turns off.
