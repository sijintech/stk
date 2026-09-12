---
name: scientific-workbench
description: Configure STK analytic-field jobs and inspect scientific result versions through registered tools.
version: 1
---
# STK scientific workbench

Use `stk.configuration.save` to prepare the fixed analytic-field template and
`stk.submit` with the saved resource ID and exact version to propose execution.
The host handles confirmation, authorization, idempotency, and receipts.
Use `stk.scene` / `stk.probe` on immutable result versions for visualization.
Report physical units and distinguish the deterministic I/O check from solver validation.
Never infer scientific validity from a successful job exit or a rendered image.
