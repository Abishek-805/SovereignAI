# UI reconstruction integration report

**Earlier checkpoint:** the Read/Ask Knowledge design below was superseded by [Knowledge context redesign](knowledge-context-redesign.md). Current Knowledge has no assistant or composer. Its latest browser workflows and test counts are in that report.

2026-09-28. Presentation and interaction milestone complete; final model-routing architecture and release gates are not complete. The taste skill was installed into `C:/Users/ashek/.codex/skills/design-taste-frontend` and applied as audit/design guidance, with its landing-page defaults adapted to a dense local workbench.

| # | Requested report item | Delivered / verified |
|---|---|---|
| 1 | Research | Audited existing Svelte surfaces, contradictory layout authorities, state/API flows and eager bundle loading. |
| 2 | Professional references | Fluent spacing, VS Code terminal hierarchy, Cursor task review, Claude keyboard interruption and LM Studio lifecycle patterns; links in `ui-reconstruction.md`. |
| 3 | Information architecture | Chat, Agent, Code and Control Center; documents/evidence contextual without removing management or artifacts. |
| 4 | Existing UI audit | Removed Knowledge imperative resizing and old CSS, duplicate Agent styles, nested-header collision, mixed Code themes and decorative model-control blur. |
| 5 | Visual direction | Compact product workspace, restrained blue focus, semantic surfaces, system typography and modest borders/radii. |
| 6 | Design tokens | Shared `workbench-system.css`; existing light/dark state drives surfaces, focus and textual status. |
| 7 | Components | Existing Svelte controls, Monaco and Lucide retained; composers and task surfaces share visual rules. |
| 8 | Sidebar | Four task destinations, Control Center separated; narrow navigation remains accessible. |
| 9 | Top bar | Bounded global model control and compact workspace headings; no duplicate Knowledge heading. |
| 10 | Model/router UI | Actual model/status/events retained; no fabricated CPU-router confidence or switch latency. |
| 11 | Chat | Compact task entry, composer styling, attachment path and existing streaming retained. |
| 12 | Agent | Compact transcript/history/new-chat controls, persistent submitted prompt, real stages/results and Stop. Actual identity answer caused no file reads. |
| 13 | Code | Theme-aligned editor chrome, compact assistant/review, narrow panel overlays; real terminal program input and isolated `pwd` verified. Monaco preserved. |
| 14 | Control Center | Existing runtime/models/documents/artifacts/appearance retained, contextual Knowledge entry and corrected heading boundaries. |
| 15 | Knowledge | Read/Ask modes, horizontal file context, bounded reader or conversation, fixed composer, expandable sources and searchable management dialog. Real 16-source Word overview downloaded. |
| 16 | Responsive | Actual production checks at 1920×1080, 1600×900, 1366×768, 800×700 and 390×844; no outer Knowledge overflow, composer visible. |
| 17 | Accessibility | Focus tokens, textual statuses, manager focus containment/Escape/return focus, Enter/Shift+Enter and IME guards. No external accessibility certification claimed. |
| 18 | Browser performance | Initial decoded script 13.29→5.64 MB; fresh-context ready observations 3506/3463/3499→1440/915/1296 ms, heap about 44.6→31.1 MB. Not inference speed or percentiles. |
| 19 | Hardware | 16.87 GB physical RAM, RTX 3050 A Laptop GPU 4094 MiB. No attribution of total GPU usage to model memory. |
| 20 | Dependencies | No new frontend framework, font, image, icon package or animation dependency. Supported split output and existing public Lucide per-icon exports. |
| 21 | Changed files | Core components: DocumentLibrary, AgentChat, DocumentsPanel, CodingWorkspacePanel, WorkbenchNavigation, ModelRoutingBar, ChatForm and ChatScreenGreeting. Shared/Knowledge/Agent/Code CSS; layout/app theme and Svelte config. 112 icon-import files changed only to preserve bindings while reducing eager package traversal. Backend intent/stage/terminal fixes and tests are recorded separately. |
| 22 | Automated checks | Svelte 0 errors/0 warnings; production build passed; frontend 677 tests/51 files passed; Python 189 passed/6 skipped. Remaining dependency warning disclosed. |
| 23 | Personal browser checks | Production scripts passed 17 acceptance checks and 10 integration records, including real inference, history, cancellation, report download, terminal input and dialog focus. Screenshots visually inspected. |
| 24 | Resource/cache evidence | Split asset integrity assertions pass. Browser-only cached shell/Code navigation works without network after worker activation. Total precache approximately 23.3 MB; long tasks remain. No OS-offline or inference gate claim. |
| 25 | Limitations / next work | Generative planner and text/vision registry remain; code uses text baseline. CPU prototype failed a safety probe and stays disabled. Model-centric selection, resource admission, context/KV experiments, alternative coding model and independent release evaluation remain open. |

Reproduce against the running production backend:

```powershell
node benchmarks/workbench-ui-acceptance.mjs
node benchmarks/workbench-integration-acceptance.mjs
node benchmarks/profile-workbench-browser.mjs after-reconstruction
node benchmarks/workbench-pwa-acceptance.mjs
```

Generated captures/results stay in ignored `benchmarks/ui-acceptance/`. The scripts are versioned. Do not run latency profiling concurrently with builds, inference or unit suites. The browser-only offline check verifies cached presentation; disconnected backend controls show disconnected status rather than fake readiness.

Suggested next UI improvement after the routing contracts are implemented: a small per-response route detail showing the actual intent, selected candidate, fallback reason and measured timings. It should consume backend evidence, not infer these values from the active page or display synthetic confidence.
