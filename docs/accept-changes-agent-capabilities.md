# Accepted code persistence and Agent operations

Accepting an applied edit previously could display an empty cached draft even though review displayed the generated `after` content. Hidden-editor autosave could then write that stale draft to disk. Accept now reloads persisted content and updates the editor, draft, revision, search, and saved baseline before leaving review; it performs no file write. Read failure keeps review open. Autosave runs only in the active source editor, excluding review, preview and conflict comparison.

The actual Summa `duvusion.py` was empty. It was restored using the recorded completed task `57a4f3d56cc34f13b6f8eab146e95c82`, guarded by the empty file's current SHA256. Its recovered SHA256 matches the task's applied hash: `0d44897f99d516b8527ab05205c0d59ca77e003ad10fad29eac5a1c10d05f609`. Division and zero-divisor behavior passed. No other Summa files were changed by this repair.

Knowledge management now includes finding and deleting exact indexed source-content duplicates. It compares SHA256 rather than names or extracted-text similarity, keeps one deterministic library entry per group, and preserves source files. Cleanup is one database transaction and rolls back if deletion fails. Explicit duplicate-cleanup intent is required; discovery and explanatory requests cannot authorize deletion. A real Agent request matching the screenshot passed against an isolated test library with earlier code-task history. The user's actual library was not cleaned as part of testing.

Successful Docker terminal commands now return file deltas to the host project, checking the unchanged original snapshot, paths, assets and byte budgets before applying them. Failed commands do not apply file changes. The IDE refreshes the tree and clean open buffers after terminal changes while preserving unsaved drafts. Terminal synchronization has a 999 KB transfer budget; empty-directory-only changes use the explicit folder-create operation. Inspection now skips binary assets rather than failing before reaching source files. Code operation instructions retain the original request without an appended hint exceeding the public 1,000-character limit.

The Agent supports bounded ordered application operations: Knowledge create/import/rename/move/copy/delete and exact duplicate cleanup; project code creation/editing, file move/copy/delete, folder creation, execution with stdin, scoped Docker terminal commands, and recurring application task management. These are real tools rather than promises of completion. This does not establish unrestricted control over every application setting or arbitrary host operations; unsupported or ambiguous requests still need clarification.

## Verification

- Backend: 496 passed, 7 skipped. Frontend: 827 passed across 77 files. Svelte: zero errors and warnings. Production build passed.
- `benchmarks/accept-generated-code-regression/results.json`: actual model generation, review with autosave enabled, Accept, Save and reload all passed; persisted SHA256 remained unchanged and no browser errors occurred.
- `benchmarks/terminal-ui-sync-regression/results.json`: terminal-created file appears in Explorer, terminal edits update the open editor, and deletion removes the file from Explorer and host project.
- `benchmarks/terminal-project-sync-acceptance/52cbd3c4ff04476d919d951695a07832/results.json`: seven actual Docker checks passed, including nested file edits, a binary asset over 1 MB, and failed-command isolation.
- `benchmarks/agent-duplicate-live/7e57c389bd8a4967817fa2a7645a0023/results.json`: genuine Agent planning and duplicate cleanup passed with source files unchanged.

The updated frontend was built and the backend restarted. Existing conversations can retain historical error messages; those messages describe earlier requests, not new execution results.
