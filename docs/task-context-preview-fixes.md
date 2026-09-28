# Task context, code creation, and preview fixes

The current request determines the action. Completed document tasks no longer supply a new task's workflow or output format. Explicit `document_ids: []` never expands to the whole library. An omitted selection remains compatible with legacy API callers; the UI always sends its resolved selection.

Chat code generation produces a fenced code answer without opening or writing a coding workspace. Agent creation uses the selected project, including empty projects, and validates generated source in the pinned Docker sandbox before saving. Its real files appear in the IDE and the project's Documents directory. New standalone programs cannot rewrite unrelated source files or binary assets.

Coding intent requires a target field. Workspace plans and generated source use JSON grammar from the first token, preventing unconstrained hidden reasoning before the result. Existing scope, path, output, cancellation, conflict, and validation checks remain in place. Removed unused project source prefetching before editing.

Knowledge has a visible On/Off track and theme green checkboxes. Scope is fixed while a request is running, with an explanatory tooltip; switch it before the next request. Status starts fresh for each Agent task. Historical stage events are no longer presented as completed validation checks. Sources appear in one collapsed disclosure, retaining individual citations and original-file actions.

The IDE image viewer supports zoom buttons, wheel zoom, drag to pan, Fit, Actual size, and Reset. SVG uses an image preview that does not execute SVG scripts, with a Source switch. Knowledge has a compact preview toolbar, a Manage menu, and a resizable library pane.

The deployed browser checks also exposed a Windows race between Explorer metadata reads and project migration. Both now share the migration lock. The single failed, verified empty suite fixture was recovered without changing user projects.

## Verification

- Backend full suite: 390 tests passed, 6 skipped; one existing dependency deprecation warning.
- Svelte: 0 errors and 0 warnings. Production build succeeded; existing large-chunk warnings remain.
- Frontend unit suite: 701 tests passed in 55 files.
- Installed Chrome preview acceptance: 6 checks passed, no page errors (SVG rendering/script isolation, zoom/pan/reset, Source preservation, PNG controls, library resizing, Manage actions).
- Installed Chrome context acceptance: 7 checks passed, no page errors (visible Off track and persistence, theme green checks, scope locked during generation, rendered Chat inline code without project writes, collapsed real citations, sequential Agent file creation visible in IDE, Agent Off persisting after completed history and reload). The IDE check waits for the actual source text to render.
- Actual model/API/Docker sequence: document summary 15.8s, Chat division code 8.7s, Agent division file 32.5s, next independent multiplication file 13.8s, Code-panel subtraction file 11.7s. Previous files remained unchanged; disconnected code tasks emitted no document retrieval stages. Separate browser Agent creation completed in 19.6s.

These are observations on this laptop, not latency guarantees. A loaded machine can be slower; one earlier run encountered a Docker availability timeout during the production build. The final sequence passed. The broader routing optimization/resource-peak release gate remains as documented in `final-routing-system-integration.md`; this patch does not claim that gate passed.

Evidence: `benchmarks/task-mode-sequential-results.json`, `benchmarks/context-request-ui-acceptance/results.json`, and `benchmarks/preview-navigation-acceptance/results.json`. Suite-owned projects/documents are retained; user projects were not edited by acceptance tests.
