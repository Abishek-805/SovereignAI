# Agent project execution and application operations

Verified on 2026-09-28 against the installed local model, Docker, production frontend, and API on port 8088.

## Fixed failures

- The project importer allowed 20 MiB assets, but sandbox input validation rejected files above 1,000,000 bytes. Summa's PNG is 1,009,578 bytes. Imports and execution now share finite budgets: 256 files, 20 MiB per input file, 256 MiB total. Docker can copy those assets without silently dropping dependencies. The container remains isolated and input mounts remain read-only.
- The program wrapper previously ignored every file named `program.py`, including nested dependencies. It now excludes only its own root wrapper.
- New-file plan grammar only permits creation/folder operations in the `new_files` scope, preventing invalid creation/edit combinations before parsing.
- Both action and application-operation planners disable hidden thinking, count the actual completion template for admission, and reassert the current request after history. Application planning has a 512-token output budget and its own real progress stage.
- Routing examples distinguish single code creation, creation followed by execution, execution with input, Knowledge management, and grounded report export. Previously completed document tasks do not dictate a new code request with Knowledge Off.
- A tool plan cannot supply implementation text as the authoring instruction. File edits receive the original user request and selected target; the dedicated code workflow generates and validates source.
- The long Chat transcript behind fixed Workbench pages no longer increases document height. Visible panels retain scrolling, and returning to Chat restores transcript scrolling.

## Registered application operations

Agent and Code assistant use the same bounded application registry for ordered operations: create/import/rename/move/copy/delete Knowledge entries; create/edit/delete/move/copy project files; create folders; run files with supplied stdin; execute requested project commands; create/list/pause/delete interval automations. Connecting references grants no mutation command. Explicit management requests can resolve library metadata with reference retrieval Off.

Agent refreshes Knowledge after management operations. Agent and IDE expose the latest completed edit for review. IDE reloads changed clean buffers and project trees while preserving unsaved drafts.

Automations persist their scope and audit result and run while the Workbench API is open. Intervals are at least 60 seconds. Busy inference is skipped rather than queued. This is a finite registered tool set, not arbitrary operating-system control, full VS Code parity, or concurrent GPU inference. External file selection remains through the import UI. Creating Knowledge content currently supports text and Markdown; deletion removes the library entry and preserves original source files.

## Verification

- Full backend suite: **410 passed, 7 skipped**. Skipped opt-in gates are not claimed as passed.
- Installed-Chrome frontend client/unit suite: **819 passed across 76 files**.
- Svelte: **0 errors, 0 warnings**. Production Vite build passed.
- Production browser layout regression: **15 passed**, covering Code, Agent, Knowledge, Control Center and restored Chat scrolling at 1920, 1366 and 390 pixels.
- Real Docker asset validation passed with PNG, nested SVG and a 20 MiB binary asset; all original bytes survived validation and Undo. Nested `helpers/program.py` execution is covered separately.
- Live Agent acceptance used an exact byte clone of Summa, with its PNG and nested files, never mutating Summa. Division creation succeeded in 39.5 seconds on the initial probe. Final sequential probes with prior document-report history and explicit empty document selection: run division with 12/3 **8.6 s**, create and run multiplication producing 42 **32.8 s**, create Knowledge note **9.9 s**, rename note **11.6 s**, delete library note **10.6 s**, list automations **7.6 s**. Original source and asset hashes matched throughout.
- Real Code assistant browser request created the selected project's subtraction file and displayed it in Explorer and the editor in **27.8 s**, with no outer scrollbar.

These are individual observed timings, not latency guarantees or proof of model quality/resource optimization. Broader resource-peak and routing optimization release gates remain incomplete as documented in the earlier integration report.

Evidence: `benchmarks/mixed-project-agent-results.json`, `benchmarks/mixed-project-ide-acceptance/results.json`, `benchmarks/workbench-scroll-acceptance/results.json`. Suite-owned project fixtures and source snapshots are retained for inspection. No actual Summa file was edited or deleted.
