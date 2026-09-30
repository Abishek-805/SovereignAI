# Execution architecture

`AgentChat` and the Code workspace call the backend coding task API. `CodingWorkspace.run_project` constructs a bounded project snapshot and asks `CodeSandbox.execute` to run generated validation code. The sandbox creates a disposable Docker Linux container from the pinned workbench image; project inputs are read-only and common secret paths are omitted. Output is held in a bounded tmpfs and a small set of artifacts is copied back through the Docker CLI. The container is then removed.

The task result and generated source are stored in workspace metadata staging, not the canonical project. The UI presents the diff. A separate Accept endpoint calls `CodingWorkspace.accept`, which checks validation, staged content hashes, path scope, and expected canonical revisions. It writes the listed paths and records publication state. Discard removes the staged files. The canonical project is under `Documents/SovereignAI/Projects` by default, while task metadata is under the app data directory.

This flow is limited to AI code edits. Manual IDE actions, terminal synchronization, Knowledge operations, and project administration use other paths. See [boundary details](sandbox-boundary.md) for their guarantees and current limitations.
