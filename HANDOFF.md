# STK development handoff

Updated 2026-09-26. This is the shared development record; machine-specific operations notes and
credentials do not belong in this file. Check GitHub for current PR and CI status before continuing.

## Current state

- Desktop D1 is complete. STK has its own C++ application and widget toolkit built on vendored
  Blender GHOST, GPU and BLF. It is not a Blender add-on. The desktop is GPL-2.0-or-later;
  the Python core remains MIT and runs in a separate process.
- [PR #51](https://github.com/sijintech/stk/pull/51) merged the desktop, viewer refinements and local
  graph worker into `main` as `8f07f71`.
- [PR #52](https://github.com/sijintech/stk/pull/52) merged the volume opacity editor and native
  setup scripts into `main` as `f076982`. All 20 checks passed before merge.
- [PR #53](https://github.com/sijintech/stk/pull/53), `fix/desktop-transfer-resume` at `c9f1399`, is
  still open. It fixes retries arriving after a terminal transfer event but before worker cleanup.
  Repeated retries coalesce, and pending retries support cancellation and shutdown recovery.
  Keep this branch until its PR is resolved. At the cleanup audit, Windows push-CI jobs had failed
  in `test_worker_exits_when_the_bridge_is_killed` with a process-exit race; corresponding PR jobs
  passed. Investigate those failures before merging; do not assume all checks are green.
- The Runtime server is Linux-only; Windows and macOS are clients. STK remains independent of
  Synorder, whose plugin is optional. Do not copy proprietary SDK code into STK.

## Compile and open the main window

See [desktop/QUICKSTART.md](desktop/QUICKSTART.md) for complete Chinese and English instructions.
From the repository root:

```bash
# macOS: full Xcode 16+, Git and Python 3.12 recommended.
# Supports native Apple Silicon and Intel; uses Metal.
bash desktop/setup-macos.sh --demo

# Reopen an existing build without installing or compiling again.
bash desktop/setup-macos.sh --launch-only --demo
```

```powershell
# Windows x64: VS2022/Build Tools with C++ and Windows SDK, Git and x64 Python.
powershell -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --demo
```

The scripts create a private Python environment, install pinned vcpkg dependencies, build only
`stk-desktop`, and launch the main window with the prepared Python bridge. Omit `--demo` for an
ordinary empty window. Use `--no-launch`, `--jobs N`, `--work-dir PATH`, or `--dry-run` as needed.
Caches live under ignored `desktop/build-dev-*`; setup output is also saved to `setup.log`.
This is a source-build workflow, not a standalone installer or a bundled-Python distribution.

## D2 work already implemented

- Persistent local graph worker with serialized evaluation, reusable caches, progress and typed
  errors, cooperative cancellation followed by termination of unresponsive workers, and restart
  after crashes. The public bridge protocol remains version 1.
- Volume opacity editor: normalized curve preview, 2–64 control points, numeric position/alpha
  editing, automatic mode and reset. Edits retain double precision. Imported invalid JSON remains
  available for repair. Nullable numeric range endpoints preserve `null` through the form.
- Viewer improvements: source-specific Hub budgets, candidate-only picking, shared scalar/range
  and smooth-normal helpers. Camera and appearance-only edits preserve data-node cache reuse.
- macOS and Windows setup entry points with a shared Python orchestration script and eight tests.

## Next development

1. Resolve outstanding CI failures on PR #53 and obtain merge approval for that PR.
2. Implement per-isosurface colours and the multi-isosurface editor. Preserve the `iso` preset's
   existing defaults (`iso_value` and scalar bar). Colour edits belong to the client stage so they
   reuse contour geometry, and must agree across desktop, browser and exported images. Existing
   categorical attributes, palettes and legends may be reusable; the design is not yet committed.
   Any new node parameter must update live declarations and the frozen catalog generator
   `docs/specs/catalog/m1_nodes.py`, regenerate the catalog, and verify schema/cache/UI behavior.
3. Add colour control points and the plots panel.
4. Finish Windows installer/bundled Python and native hardware acceptance. Keep the Qt application
   and its dependencies/tests until D2 acceptance is complete.

Later milestones: CLI command forms and chat (D3), graph node editor (D4), standalone Cycles (D6).
See [viewer parity](desktop/docs/parity-viewer.md), [Jobs parity](desktop/docs/parity-jobs.md),
[desktop development](desktop/README.md), and [user guide](docs/desktop.md) for remaining details.

Other known gaps include gradient volume shading, per-triangle transparent sorting, oblique slices,
ROI, persisting camera/parameters with layouts, native Mac/Windows file dialogs, JPEG previews and
an in-app Python interpreter picker. Native IME, Cocoa/Win32 window/GPU behavior, real-cluster MPI,
signing/notarization and release packaging still need acceptance on the appropriate systems.

## Verification record

These are completed runs, not guarantees about later commits:

- PR #52: Linux desktop CTest **412/412 passed**, including all **15** required Python-backed and
  package checks; macOS Metal and Windows MSVC CI passed. Opacity edits recomputed no data nodes.
- PR #53: non-desktop Python **1,140 passed, 7 skipped, 2 deselected**. Two cancellation/shutdown
  cases were added after collection; the focused **26/26** run includes all four new regressions
  and the real Runtime/Hub upload-resume tests. The initial regressions fail before the fix.
- Cleanup audit: `bash -n desktop/setup-macos.sh`, **8/8** setup orchestration tests, and arm64/Intel
  macOS dry-runs passed. Actual native setup and interactive window/IME acceptance remain pending.

Use the build and test commands in `desktop/README.md`. Set `STK_BRIDGE_TEST_PYTHON` and
`STK_APP_TEST_PYTHON` to an interpreter with the required extras when running desktop tests; verify
that required Python-backed cases ran rather than skipped. Do not check build outputs, caches,
credentials or machine-local configuration into Git.

## Repository cleanup

On 2026-09-26, 16 completed agent worktrees and 35 obsolete local branches were removed after
checking their status. None contained uncommitted source changes; ignored files were Python caches
and old build outputs. The merged remote `feature/desktop-engine` branch was also deleted.

Five historical branch tips not directly reachable from `main` were pushed as annotated tags
before deletion, preserving their exact commits even where work had been cherry-picked or rebased:

| Archive tag | Original commit |
|---|---|
| `archive/2026-09-26/wip/payload-reconcile` | `e9c596a` |
| `archive/2026-09-26/wip/wp10-viewer` | `023faca` |
| `archive/2026-09-26/wip/wp45-io-model` | `ccd47e4` |
| `archive/2026-09-26/wip/wp6-viewer` | `9e30cad` |
| `archive/2026-09-26/wip/wp7-bridge` | `e98b985` |

Active unmerged PR branches are retained. Branch cleanup does not authorize merging a new PR.
