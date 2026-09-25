---
name: stk-monitor
description: Follow a running STK Runtime task through its monitoring events (progress, metrics, frames, messages, completion) and report status without over-claiming success.
---

# Monitoring STK tasks

Programs that use the STK monitoring SDK, or launchers with an adapter such as `python -m suan.mupro run`
for muFerro, append events to the task's `events.jsonl` (`docs/specs/stk-events-v1.md`). Each event is
`{"v": 1, "seq", "ts" (Unix seconds), "type", "src", "data"}`.

## Reading events

- MCP: `get_task_events(task_id, offset=0)` returns `{"events": [...], "offset", "next_offset", "size",
  "terminal", "invalid"}`. Call again with `offset = next_offset` to continue; only whole lines are returned.
  `terminal: true` means the task has ended and everything was read. Through the STK hub the same read is the
  action `task.events` with payload `{"task_id": "…", "offset": 0}`.
- A Runtime without the `events` feature, or a program without the SDK, has no events: say "no monitoring
  events" and fall back to `get_task` (state) and `get_task_logs`.
- Poll gently (every 10 s or more) and stop once `terminal` is true.

## Event types

| type | meaning |
|---|---|
| `run.started` | the program started (`app`, `total_steps`, ranks) |
| `run.phase` | a named phase began/ended |
| `progress` | `step`, `completed_steps`, `total_steps`, `fraction` (0–1), optional `eta_s` |
| `metric.declare` / `metrics` | named series (unit, label) and their values per step (e.g. muFerro energies, unit `normalized`) |
| `frame` | a published, immutable output frame (`dataset`, `step`, `path`) — safe to visualize |
| `checkpoint`, `artifact` | restart files and other outputs |
| `message` | `level` info/warning/error with `text` and `code` (e.g. `nonfinite_energy`) |
| `usage` | resource usage |
| `verification` | checks of the result record |
| `run.completed` | the program's own `status`, `classification`, `reason` |

Non-finite numbers arrive as the strings `"NaN"`, `"Inf"`, `"-Inf"`.

## Reporting rules

- Progress is not success. A task has succeeded only when its Runtime state is `succeeded` **and** the
  program's verification passed (for muFerro: `stk-mupro.json` → `verification.status == "passed"`).
- Quote progress as `completed_steps / total_steps` and the time of the last event; an ETA is an estimate.
- Report warnings and errors from `message` events verbatim (with their codes); never hide a
  `nonfinite_energy` or a failed verification.
- Metric units are never guessed: `normalized` stays normalized, `unspecified` stays unspecified.
- To look at a frame while the run continues, use the `stk-visualize` skill once the task has finished
  (published files are listed after the task ends).
