# SovereignAI presentation reconstruction

**Architecture update:** see [Knowledge context redesign](knowledge-context-redesign.md). Knowledge is now a standalone document library consumed by Chat and Agent; references to its former Read/Ask modes below describe the previous checkpoint.

Workstream: UI, interaction, and browser cost. Backend routing/model evaluation is a separate workstream in [workbench-upgrade-plan.md](workbench-upgrade-plan.md). The two 2026-09-28 briefs are applied at those boundaries; the UI brief does not authorize replacing the sandbox or inventing routing telemetry.

## Audit and decision

The presentation layer warranted reconstruction, while the functioning Svelte/API workflows warranted preservation. Knowledge had several generations of contradictory three-column, stacked, and full-width rules, plus imperative viewport sizing. Agent had duplicated typography/composer sizing. The shell's broad descendant-header selector changed nested dialog headers. Code mixed fixed dark values with Monaco's theme. The model control used expensive decorative blur. The app forced all JavaScript into one initial bundle, including Monaco.

Decision: one presentation authority per workspace, shared semantic tokens, existing Svelte/Monaco/theme/icons, four primary modes, and contextual documents. No UI framework, animation library, font, image, or icon dependency is added.

## Reference patterns

References were reviewed as interaction guidance, not copied branding or an official design-system implementation:

- [Fluent layout](https://fluent2.microsoft.design/layout): consistent spacing, proximity, adaptive density.
- [VS Code terminal](https://code.visualstudio.com/docs/terminal/basics): output and input share a terminal surface; editor receives priority. SovereignAI remains a bounded Docker execution surface, not host PowerShell.
- [Cursor Agent](https://cursor.com/docs/agent/overview): task outcomes, observable tools, reviewable changes.
- [Claude interactive mode](https://code.claude.com/docs/en/interactive-mode): keyboard input and interruption patterns.
- [LM Studio](https://lmstudio.ai/docs/app): local model lifecycle separated from ordinary conversation.
- [Apple layout](https://developer.apple.com/design/human-interface-guidelines/layout): stable hierarchy and adaptive layout; the retrieved page did not expose its full text, so no detailed claim is based on it.
- [SvelteKit output](https://svelte.dev/docs/kit/configuration#output): supported split output makes dynamic imports effective; hash routing and static local hosting remain.
- The user's Codex/VS Code reference screenshots guide explorer/editor/assistant/terminal hierarchy. SovereignAI does not clone either product.

## Screen and API map

| Surface | Purpose / component | API and state | New location / design |
|---|---|---|---|
| Chat | ChatScreen, ChatForm | Existing completion stream, attachments, conversation store | Primary mode; compact entry actions and shared composer treatment |
| Agent | AgentChat | `/agent/jobs`, `/coding/jobs`, vision request; actual stages, history | Primary mode; task transcript, bounded work details, compact composer |
| Code | CodingWorkspacePanel, SourceEditor | CodingWorkspaceService, Docker jobs/input, saved/draft buffers | Primary mode; explorer/editor/assistant, contextual terminal/changes |
| Documents | DocumentLibrary | `/documents`, content/import, question/report jobs, sources | Contextual Read/Ask workspace reached from Chat or Control Center |
| Evidence | source details | Existing cited source labels, page and original URL | Expandable source rows in the answer; no fabricated validation badge |
| Artifacts | Downloads | `/workbench/artifacts`, real downloads/deletion | Control Center/contextual results; file-based presentation |
| Model control | ModelRoutingBar | `/status`, `/workbench/info`, real route events | Global compact control; expanded registry/reason details |
| Control Center | DocumentsPanel | Existing runtime/model/system endpoints | Secondary section below primary work modes |

## Presentation system

`workbench-system.css` defines surface, raised surface, focus, success/warning, radius, reading width and restrained shadow tokens. Light/dark reuse the existing theme system. The light background is slightly off-white. UI uses locally available Segoe UI/system fonts; code retains Monaco/Consolas. Accent is a restrained blue used for focus and operational information. Status remains textual, not color alone.

`knowledge-workspace.css` owns Knowledge layout. The shell and composer do not scroll. Ask has one flexible conversation surface; Read has one document surface and a compact horizontal file ribbon. The manager is a bounded dialog with search/selection/import/rename/remove, keyboard focus containment and Escape. No fixed desktop minimum height or JavaScript resize loop remains.

`agent-workspace.css` owns Agent layout. History and project selection are secondary popovers. User requests stay in the transcript. Observable stages and elapsed time remain real; no percentage or hidden reasoning is invented. Evidence and machine details are disclosed on demand.

Code retains Monaco and the existing resizers, explorer, changes review, applied/accept/undo semantics, direct terminal input and controls. Its chrome uses the shared theme and removes decorative gradients/shadows. Enter sends; Shift+Enter inserts a line; composition events are respected in Agent and Knowledge. Unsaved draft conflict protection remains intact.

## Performance evidence

Machine observation: 16,873,545,728 bytes physical RAM, NVIDIA RTX 3050 A Laptop GPU with 4,094 MiB total VRAM. Sampled GPU usage was 1,109 MiB before generation; this is total GPU use, not attributable model memory.

Before reconstruction, three fresh-context headless Chrome runs against production, 1366×768, service workers blocked: 13,286,706 decoded script bytes per run, ready times 3506/3463/3499 ms, approximately 44.6 MB JavaScript heap. After the final build, the same script measured 5,639,636 decoded script bytes, ready times 1440/915/1296 ms and heaps 31,147,942/31,044,451/31,172,651 bytes. These are three browser observations, not percentiles, model timings or OS browser RSS. The final measurements did not overlap build, unit tests or inference.

Split SvelteKit output and documented Lucide per-icon entry points reduced eager loading. SSR module count fell from 5344 to 1836; client modules from 9612 to 6104. The final production build took 5m18s; this single run does not establish a build-time benchmark. Total precached assets remain approximately 23.3 MB across 238 entries, including deferred editor/math functionality. Initial loading still produced long tasks: 164/201, 244/143 and 181/253 ms in the three runs. Further optimization remains possible.

## Verification and limits

Final checks: 189 Python tests passed, 6 skipped; Svelte check 0 errors and 0 warnings; 677 frontend unit tests passed across 51 files; production build succeeded. Production browser acceptance passed 17 layout/theme/terminal checks and 10 integration records. Browser-only offline cache verification passed after waiting for worker activation and reloading; it proves frontend assets, not offline inference or the OS-enforced release gate. See [integration report](ui-integration-report.md) and [verification record](workbench-upgrade-verification.md).

Known engineering limits are preserved truthfully: generative intent planner, text/vision keyed model registry, code uses the text baseline, Docker shell commands use separate sessions, cancellation of current model inference may wait for its bounded generation step, and final CPU routing/model/resource/offline evaluations remain separate work. No UI pass proves those complete.
