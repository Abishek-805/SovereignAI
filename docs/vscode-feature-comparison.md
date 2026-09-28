# Code workspace comparison with Visual Studio Code

Audited 28 September 2026 against the official VS Code documentation and the actual SovereignAI implementation. This is a Svelte/Monaco workbench inspired by the supplied reference, not a distribution of VS Code and not feature-complete VS Code parity.

| Workflow | SovereignAI support | Remaining difference |
|---|---|---|
| Explorer and file management | Imported workspace tree; create files/folders; rename, copy, cut, paste, move, delete; relative-path clipboard; folder disclosure arrows; native drag move and Ctrl-copy with collision/dirty-draft/cycle guards | Imported local copies rather than a native host-filesystem workspace |
| Open editors and tabs | Open Editors list, dirty indicators, next/previous editor, close/close others/close right/close all, reopen closed editor; native tab drag reorder | Single editor group; no arbitrary split grids or dragged editor groups |
| Unsaved changes | Save/Discard/Cancel on tab and multi-tab closure; drafts retained while switching tabs; workspace switching rejects unsaved changes | Unsaved drafts are not restored after a full application restart |
| Save concurrency | Reads track SHA-256; Save, Save All and Save & close require the opened revision; conflicts keep drafts and offer compare, explicit disk version or explicit save-my-version | External modification detection occurs on save, not through a filesystem watcher |
| Quick Open / Command Palette | Ctrl+P, Ctrl+Shift+P/F1; searchable real commands/files; arrow selection, Enter, Escape; Ctrl+G line navigation | No installed extension commands or symbol-provider catalog |
| Workspace search | File-name and content search; case, whole-word, regular-expression toggles; clickable matching lines; live unsaved text | Explicit first-100-file content index and 200-result cap; no workspace replace-all |
| Editing | Monaco syntax highlighting, folding, indentation, selections, native find/replace and undo/redo, language workers, diagnostics; functional Edit/Selection/Go menus dispatch installed native actions | Full language-server/refactoring support depends on language; Python/Java etc. do not gain VS Code extensions |
| Editor isolation | Each workspace/file has its own Monaco model, undo stack and restored cursor/view state; drafts remain available | Workspace-scoped Monaco cache retains up to 24 editor models and cursor/view positions; least-recently-used inactive entries are disposed |
| Layout | Resizable Explorer, Assistant and terminal boundaries, keyboard resizing, remembered widths, visibility toggles, fullscreen and narrow-window overlays; minimap and word-wrap preferences persist across tabs/reloads | No floating editor windows or arbitrary view docking |
| Problems | Actual Monaco diagnostics and counts | Not a complete project build/language-server diagnostics index |
| Run and terminal | Isolated Docker execution, direct line input for running programs, shell commands, command history, Stop; scoped cd working directory supplied to subsequent Docker commands; host project path and native File Explorer reveal | Job-backed Docker command input, not a persistent host PTY; no terminal profiles, ANSI interactive TUI or parallel terminal groups |
| Changes and AI | Automatic inline red/green diffs after applied tasks; Accept clears diff/badge/baseline and keeps actual disk edits; Undo, project chat, task history and Stop | These are SovereignAI task changes, not a Git Source Control implementation |
| Git source control | Not implemented as a workbench UI | No staging/commits/branch graph/merge editor; do not display fake Git controls |
| Debugging and tests | Run output and editor diagnostics | No debugger adapters, breakpoints/step controls, variable inspection or test-discovery UI |
| Extensions and remote development | Not implemented | No VSIX marketplace/runtime, SSH/WSL/Codespaces or VS Code settings sync |

## Changes in this pass

- Expanded the functional command palette and added keyboard selection and go-to-line.
- Added Open Editors and tab context actions, reopening closed editors, and safe multi-tab closure.
- Added explicit case/word/regex workspace search with invalid-regex feedback and scope limits.
- Added revision-aware saves and an explicit disk-versus-draft comparison path, including Save All and Save & close.
- Prevented cross-file Monaco undo and asynchronous saves from associating the saved revision with a different active tab.
- Added functional Edit (Undo/Redo/Find/Replace/Comment/Format), Selection (select all/multi-cursor/next occurrence), Go (file/line/bracket) and View (word wrap/minimap) menus. Formatting is enabled only for bundled provider languages; missing debugger/definition/extension functionality is not advertised.
- Kept existing program input, Docker commands, resizing, file CRUD, task review and assistant mechanics intact.

## Verification

Svelte check passed with 0 errors and 0 warnings after these edits. Integrated production browser acceptance and the backend concurrency checks are recorded by the root integration task; this document does not label unexecuted browser steps as verified.

Acceptance focus: open two files with Quick Open using ArrowDown/Enter; navigate to a line; change a draft and close it (Cancel, then Discard or Save); reopen it; close multiple dirty files; search literal punctuation and regex patterns; trigger a stale-revision save and compare without losing the draft; rerun direct program input and shell command checks.

## Official references

- [VS Code user interface: layout, groups, palette and tabs](https://code.visualstudio.com/docs/editing/getting-started/userinterface)
- [VS Code basic editing: multi-cursor, find/replace and editing mechanics](https://code.visualstudio.com/docs/editing/codebasics)
- [VS Code integrated terminal: shells, terminal groups and shell integration](https://code.visualstudio.com/docs/terminal/basics)
- [VS Code source control](https://code.visualstudio.com/docs/sourcecontrol/overview)
- [VS Code debugging](https://code.visualstudio.com/docs/debugtest/debugging)
- [VS Code Extension Marketplace](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace)

Production browser acceptance script: `benchmarks/ide-navigation-acceptance.mjs`. It tests existing Summa files as unsaved drafts and uses a separate temporary Markdown workspace for revision conflicts, deleting its Markdown file afterward. Final production run passed 14 real-browser checks with no page errors, including native Edit comment/Undo/Find, persisted word-wrap/minimap settings, palette focus after the prior Go-to-Line/workspace-switch race, multi-dirty tab closure, revision conflict comparison/explicit save, desktop/mobile visual inspection, and unchanged original-file snapshots captured at the start of that run. Earlier exploratory runs exposed an editor reveal-focus race (fixed) and intermittent Monaco disposal cancellation exceptions; none occurred in the final rebuilt run.

## Latest applied-change and navigation pass

The Code workspace now automatically opens inline review after a completed applied edit. Accept retains edited files while removing the current review model and changed-file badge; historical task results remain available. Whitespace-only edits and deleted files are included in review. Explorer folders have visible disclosure arrows; native drag operations move files/folders or copy with Ctrl/Command, reject overwrites and folder cycles, and protect unsaved drafts. Tabs can be reordered by dragging. Standalone `cd` updates a validated project-relative folder used by later isolated Docker commands; the terminal distinguishes that container path from the canonical host project location and exposes a native File Explorer action.

Check: Svelte diagnostics 0 errors/0 warnings at source freeze. The final production run of `benchmarks/ide-review-drag-acceptance.mjs --model` passed twelve real browser checks with no page errors: folder disclosure, native Explorer move/Ctrl-copy/collision protection, tab reorder, project-relative cwd, actual Bash interactive stdin, host paths, external file Refresh preserving drafts and detecting revision conflicts, real-model automatic review/acceptance, and exact named-file edit scope. The model changed only the requested line, preserved the heading, and left the unrelated file hash unchanged. Inline red/green review and the clean accepted state were personally inspected in screenshots. User Summa files are not mutated by this suite; its separate Markdown workspace is emptied afterward. Earlier attempts exposed overbroad model edits and a Monaco disposal cancellation; backend literal replacement/scope enforcement and diff-model detachment were applied before this successful rebuilt run. Docker or backend outages interrupted two intermediate attempts before inference; those test workspaces were also cleaned up.

The File menu also provides **Open project in VS Code**, targeting the same canonical host project files through the backend's fixed installed-executable endpoint. Git, debugging, remote development and extension workflows remain external VS Code capabilities; this handoff does not imply those runtimes are embedded in SovereignAI. Native window launch is user initiated and is not performed by the headless browser suite.


Final rebuilt strict run: **12 production browser checks passed with no page errors**. The real installed model edited only `docs/notes.md`, preserved the exact heading and requested replacement, and left `copies/notes.md` SHA-256 unchanged. Inline review appeared automatically; Accept removed review/card/badge and retained disk content. The rebuilt disposal path emitted no Monaco cancellation errors in this run. Actual Bash stdin, validated cwd, host paths, native drag/copy/reorder and external Refresh/conflict checks also passed. Screenshots were inspected by the root and IDE agents. This supersedes the pending strict check above; it does not establish universal model correctness or full VS Code parity.
