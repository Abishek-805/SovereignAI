# Knowledge management, Agent conversation layout and IDE workflows

28 September 2026. This supplements the previous context/routing report with the latest requested changes. The existing Svelte, Bits UI, Monaco, local model and Docker integrations remain in use.

## Knowledge

- Add documents now contains Upload files and Import folder. The sidebar import action is removed. Folder imports transmit simple filenames and preserve the selected directory hierarchy as library metadata.
- Selected files expose Rename, Move, Update file and Delete above the preview. Dialogs retain errors and explain destructive operations.
- Move stores a logical library folder in SQLite; it does not move the original file on the computer. Folder filtering and organization survive reloads.
- Update replaces the indexed content under the same document ID, preserves its displayed name/folder, and retains earlier source snapshots for existing citations. Actual source type controls preview even when the display name is renamed.
- Version checks reject stale updates and mutations. Delete removes indexed versions/citations; original computer files and stored source snapshots remain, as the dialog explains.
- Escape closes Add documents and restores focus without returning to Chat. Browser acceptance caught and corrected the previous conflicting page shortcut. The original backend filename boundary remains enforced.

## Agent

Agent now uses Chat's centered conversation measure and rounded composer: a compact welcome and task shortcuts before the first turn, then a transcript with an anchored composer. History, New chat, Knowledge connection, workspace selection, uploads, Stop, task events, sources, downloads and review are retained. Following the latest answer respects scrolling up.

## Code

- Edit, Selection and Go menus use actual Monaco commands. Native find/replace, undo/redo, line comments, selections, multiple cursors and bracket navigation are available; formatting is limited to languages with installed providers.
- Quick Open and Command Palette support arrow selection, Enter and Escape. Go to line, Open Editors, reopen closed editor and tab context operations use real handlers.
- Closing dirty editors offers Save, Discard or Cancel, including multiple-tab closure. Drafts remain during tab switches.
- Saves carry the opened SHA-256 revision. Stale saves preserve the draft and offer comparison, disk version or explicit save of the draft. Backend publication is serialized; two editors cannot publish against the same revision simultaneously.
- Monaco models retain separate undo stacks and view positions, scoped by workspace/file with a 24-model retention limit. Theme changes update editors and diffs. Word wrap/minimap preferences persist.
- Search includes case, whole-word and regular-expression options, invalid-pattern feedback and clickable lines. Indexing/search caps remain visible.
- Existing terminal program input, isolated shell commands, resizing, Stop and applied-before-Accept review remain functional.

This is not a complete VS Code distribution. Git staging/commits, debugger adapters, an extension host/marketplace, persistent PTY terminal groups and arbitrary split editor grids remain unsupported. See the [feature comparison](vscode-feature-comparison.md); these capabilities are not represented by fake controls.

## Verification

Backend regression: **248 passed, six skipped**, including isolated document-management/version tests and concurrent editor-save tests. The existing Starlette deprecation warning remains. Svelte checks pass with zero errors/warnings; the production build succeeds.

Final production browser acceptance passes four document-management workflow groups plus desktop/mobile menu and viewport checks, four Agent viewport/theme combinations, and 14 IDE checks. No page errors were recorded in these suites. IDE checks include real Monaco comment/Undo/Find commands, persisted preferences, keyboard palette focus, multi-dirty tab closure, workspace search, revision conflict comparison and explicit save. Document replacement content is visible after reload, and earlier original-source snapshots remain retrievable.

The cached frontend shell also starts with browser networking disabled. This does not establish offline inference or OS network isolation. Chrome still intermittently reports a cross-world service-worker preload mismatch warning; that console issue remains unresolved. The build also retains its existing chunk-size/import warnings.

Acceptance uses actual imports, indexed content, original-source downloads, dialogs and editor commands. Only suite-owned documents and an isolated Markdown workspace are saved/deleted. Existing Summa files are exercised as unsaved drafts and compared by hash within each run. Generated captures are ignored by Git. No random Python program is created to stand in for UI acceptance.
