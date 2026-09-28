# Integrated project validation — 28 September 2026

This pass addresses the latest Knowledge, host-project, change-review, drag/drop, terminal and routing requests. It builds on the earlier implementation; the actual feature boundaries remain explicit.

## Knowledge and interface

Chat and Agent default to a connected all-document scope. The switch can turn context off without removing the library or the remembered selected scope. A whole-library scope refreshes references when sending, so later imports join it; references are capped at 256 with an explicit scope error rather than silent truncation. The model chooses retrieval only when the question needs evidence. General questions and greetings use actual model answers.

Update file was removed from the interface as requested. Existing backend version compatibility remains available to older clients. The library exposes Rename, Move, Copy and Delete, supports operating-system file/folder drops, and moves/copies documents into library folders by dragging. Copy has a new document/chunk identity but reuses immutable source snapshots and indexed vectors without extra embedding work. Move organizes library folders; it does not move original computer files. Delete removes library indexes, leaving originals and snapshots on disk.

Shared dialog inputs now use explicit theme colors, addressing the dark-theme white-input/white-text screenshots. Agent uses the Chat-like conversation layout with context and attachment controls.

## Live project files and Code

Default production projects live under `C:\Users\ashek\Documents\SovereignAI\Projects`. Metadata/task history stays in the workbench data directory. Initial migration copies files and retains the earlier internal snapshot; subsequent reads, writes, file operations and AI edits use the canonical live project. External edits participate in SHA-256 conflict checks. Portable backups take current live files and normalize project metadata for restoration on another location/machine; they refuse to archive a stale snapshot if the live project is missing.

The File menu reveals the project in File Explorer or opens the installed Visual Studio Code using a verified executable and fixed arguments. Refresh updates the tree and clean editors/revisions, while preserving unsaved drafts. The native editor is the practical route to its Git/debugger/extensions; SovereignAI does not pretend those systems are embedded.

Applied AI edits automatically open inline review. Accept keeps the files and clears the current review/badge; historical results remain available. Folder disclosure arrows, Explorer drag move/Ctrl-copy, tab reorder and guards for collisions, cycles and dirty drafts are implemented. Terminal `cd` changes a validated relative working directory for subsequent Docker commands. The terminal distinguishes the isolated Docker path from the canonical Windows host path. Commands remain bounded, separate Docker jobs; this is not a persistent host PTY or a full interactive TUI terminal.

Standalone creation uses a model-declared `new_files` scope. The backend rejects attempts to edit/delete existing files in that scope before generation, and does not send unrelated file contents to the generator. This addresses collateral edits and repeated generation/validation work without a greeting dictionary.

## Router, tasks and latency

See [the real model audit](final-router-performance.md). Six serialized API workflows were verified: greeting, identity, unrelated connected-context question, grounded fact, calculator and downloadable cited Word report. An actual unsupported factual answer exposed a routing failure, and the corrected planner retrieves evidence for that case.

Observed samples: warm short conversation 2.9–3.5 seconds; sourced fact 5.8 seconds; report 10.2 seconds; sleeping-model greeting 8.7 seconds. A detailed answer took approximately 37 seconds. These heterogeneous samples do not establish p95, energy efficiency or universal accuracy. There is one installed text/code candidate and one vision candidate, rather than a measured candidate optimizer or architectural mixture-of-experts. No unmeasured coding model was installed.

Jobs use request-local streamed completion aggregation so Stop closes that generation's response when cancellation is observed between stream events. A live Stop probe observed 81 decoded tokens before cancellation: the job canceled in 0.119 seconds and the runtime appeared idle in 0.225 seconds, with no partial result published. Initial prefill/loading can still delay a cancellation checkpoint; this is not a claim of immediate cancellation under every condition.

Agent can perform registered evidence/report/calculator/vision/coding tasks. Arbitrary navigation and every application-management action are not registered model tools. Full embedded Git, debugger adapters, extensions, arbitrary split-editor grids, persistent terminal groups and autonomous application-wide operation remain unfinished capabilities.

## Verification

Final backend regression: **279 passed, 6 skipped** (one existing Starlette deprecation warning). Frontend unit regression: **695 passed across 54 files**. Svelte checking completed with **0 errors and 0 warnings**, and the production build succeeded. The rebuilt cached frontend shell started with browser networking disabled and reported no preload mismatch warnings; this does not establish offline inference. Strict rebuilt Knowledge browser acceptance: **10/10 passed**, no page errors or model requests, with pending-chat persistence checked (not skipped). It exercised default all-document context, Off/subset persistence, later imports, actual file import/drop, Copy/Move/Ctrl-copy, Agent drop/removal, dark/light contrast and 1366/390-pixel bounds. Strict rebuilt IDE browser acceptance: **12/12 passed**, no page errors. The installed model changed exactly the named file/line, preserved its heading and left the duplicate file hash unchanged. Automatic inline review and Accept cleanup passed, together with Explorer move/Ctrl-copy/collision guards, tab reorder, folder arrows, actual Bash stdin, validated cwd, host paths and external Refresh/conflict handling. The observed complete model edit took 27.6 seconds; it is not instant. Root visually inspected steady-state dialog/mobile screenshots and both inline-review/accepted editor states. Local services and Docker had stopped during earlier attempts; those interrupted runs were not counted. The project launcher and Docker Desktop were restarted before the successful run. Acceptance saves/deletes only suite-owned documents and isolated Markdown workspaces. It preserves existing user project files and uses real imports, API operations, installed-model output, Docker commands and UI actions.


## Knowledge storage folder follow-up

Production source snapshots now live in `Documents/SovereignAI/Knowledge`, alongside Projects. Startup copies existing supported snapshots without removing the older copies and rejects conflicting contents instead of overwriting. Imports, original-file previews and PDF evidence use the new source location; portable backups archive its live contents. A read-only production check returned HTTP 200 for an existing original source after migration, with 28 stored snapshots present. Content-hash filenames preserve source versions; display-name/folder management remains in the library. Custom data directories keep their existing `sources` location unless `SOVEREIGN_KNOWLEDGE_DIR` is set.
