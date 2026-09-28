# SovereignAI design comparison

Reading this as a professional local AI workbench for engineers, with a dark-first, restrained language and task-specific canvases. Design variance 5, motion intensity 2, visual density 6. The taste skill supplies audit, contrast and anti-template discipline; its landing-page patterns are not appropriate for a code editor or dense application.

The fresh concept is [workbench-concept.html](design/workbench-concept.html). It is an isolated visual prototype with clearly labelled sample data, not a substitute for the functioning Svelte application. Navigation, theme switching, sidebar collapse and library filtering operate locally. Report generation, model state, source actions and terminal content are illustrative. No backend requests, model jobs, builds or runtime restarts were made by this prototype.

## Decision

Adopt the concept's navigation hierarchy, page proportions and task-specific composition. Keep the existing production components and backend integrations. Reconstruct the shell and layouts rather than changing frameworks or replacing functional controls with prototype markup.

Do not mistake its polished sample state for a backend acceptance result. Resolve request validation and relevance routing before shipping the visual changes.

## Comparison with the supplied screenshots

| Area | Current screenshots | Fresh concept | Recommendation |
|---|---|---|---|
| Navigation | Collapsed symbols provide little explanation of each destination. Chat and Agent choices are also repeated at the composer. | A 216 px labelled navigation spine establishes Chat, Agent, Code, Knowledge and Control Center. It can collapse to 66 px. | Keep expandable sidebar behaviour. Label destinations by default; use real project icon family instead of prototype numeric placeholders. Remove redundant mode explanation where navigation already explains the destination. |
| Global model control | A large upper-right model box competes with task content. Friendly model name and routing state are already an improvement. | A 64 px shell header contains a compact routing action, readable model name and theme action. | Preserve real runtime state, technical ID in details and stop controls; reduce visual weight. Never show a loaded model when no model is loaded. |
| Chat | Empty state floats in a large black field; composer includes duplicated Chat/Agent selection and capability copy. | Conversation occupies a deliberate central reading column. Optional evidence rail gives citations a stable home; chips retain connected context. | Use a concise empty-state introduction, then give the transcript priority. Do not turn the evidence rail into a compulsory permanent column on small screens. |
| Knowledge | Earlier screenshots show three simultaneous scrolling areas and a separate assistant inside the document workspace. | A library and preview replace the assistant. A restrained preview toolbar and metadata footer remain fixed. The shell itself does not scroll. | Adopt library plus preview. Each long-content area may scroll locally, but no outer page scroller. Connect is a context action, not a Knowledge chat mode. |
| Agent | Large centered welcome message and deep composer dominate the page. Planning cards hide the result and repeat generic stages. | A task title, truthful state, action ledger and artifact output form a clear hierarchy. Context is secondary. | Replace the landing hero with outcome-oriented task composition. Only render steps returned by actual execution, never the three sample steps as a hard-coded workflow. |
| Code assistant | Large intro/result boxes take space away from messages. | A compact review block contains one file-change summary and Review / Accept / Undo. | Keep real applied-before-accept semantics and compact controls; preserve Monaco and existing edits. |
| Terminal | Screenshot input requires a separate bottom input; previous reports say it cannot be typed into. | Input appears at the active prompt with a caret. | Integrate the real terminal's input focus and transport. This prototype does not prove PTY operation; direct keystroke and shell-command acceptance must pass in production. |
| Control Center | Settings are presented through many existing utility panels. | A section navigation groups routing, runtime, indexing, sandbox, appearance and privacy. | Group existing real controls. Expose route details without inventing telemetry or model capabilities. |

## Design rules to carry into production

- Neutral charcoal surfaces: background `#131719`, surface `#191e21`, raised `#22292d`, separator `#344047`. Main text `#edf1f3`, secondary text `#a8b3ba`. One restrained action accent `#9fd5ca`, dark action text `#14342e`.
- Keep semantic warning, failure and cancellation colours from the existing system. The single-accent rule does not erase important error states.
- Light theme uses background `#f7f9fa`, surface `#eef2f4`, raised `#e1e8ec`, text `#202d35`, secondary `#536773`, action `#276c5e` with white text.
- Use the existing locally served font or system sans; do not add a remote font dependency. Body 14 px, chat answers 15 px with 1.75 line height, page title 22 px. Code remains a proper monospace editor.
- Radius rules: 7 px controls and small panels, 10 px composer, 4 px context chips. Avoid pill styling for every rectangle.
- Compact 64 px global header, 216 px expanded navigation, 290 px Knowledge list, 266 px optional evidence rail. At 1100 px hide the optional rail; show sources inline. At 700 px use an explicit library/preview toggle and preserve access to every destination.
- Mobile adaptation is not feature removal. The prototype hides the desktop code assistant to demonstrate spacing; production must expose a switcher or drawer for Explorer / Editor / Assistant / Terminal. Do not copy that omission.
- Add context opens an accessible menu and searchable Knowledge picker. Connecting document IDs gives read context. Unrelated questions still go to the model; the connection does not force retrieval.
- Long documents and conversation history need local scrolling. Fitting the page means fixed shell boundaries and accessible content, not clipping long content or shrinking text.
- Source highlighting is permitted only when the exact passage is returned. The sample paper is a design artifact, not a document preview implementation.
- All mock buttons must be replaced by current real handlers. Retain original document downloads, extracted passage inspection, rename/delete, actual indexing warnings, folder actions, history and Stop.

## Visual inspection and checks

Chrome screenshots were generated at 1440 × 900 for all five destinations and 390 × 844 for Chat, Knowledge, Agent and Control Center. After fixing the small-screen preview-toolbar overflow, every tested viewport had document scroll width equal to viewport width and document scroll height equal to viewport height. The document preview and task content use local overflow.

Personally inspected desktop Chat, desktop Knowledge, desktop Code, mobile Knowledge, mobile Agent and light-theme Knowledge images. A light-theme transition initially captured intermediate colours; capture now waits for the 120 ms transition before taking the light screenshot. Reduced-motion disables transitions through a media query.

This is visual concept verification only. It does not claim production interaction, WCAG certification, performance acceptance, terminal functionality or model accuracy.

- [Chat, desktop](design/chat-desktop.png)
- [Knowledge, desktop](design/knowledge-desktop.png)
- [Agent, desktop](design/agent-desktop.png)
- [Code, desktop](design/code-desktop.png)
- [Control Center, desktop](design/control-desktop.png)
- [Knowledge, mobile](design/knowledge-mobile.png)
- [Agent, mobile](design/agent-mobile.png)
- [Knowledge, light](design/knowledge-light.png)

## Implementation sequence

1. Make the backend request contracts and relevance decisions reliable. Verify greetings, ordinary unrelated questions with connected documents, document questions, reports, edits, cancellation and terminal input.
2. Establish shell tokens, sidebar labels and compact runtime controls while retaining current events and state stores.
3. Make Knowledge solely library and preview; attach document IDs through shared context controls.
4. Give Chat a readable conversation canvas and optional evidence view. Give Agent an outcome/action/result canvas.
5. Compact Code review controls and use the real interactive terminal; retain all file operations and applied-change decisions.
6. Verify actual workflows across themes and widths before measuring and accepting the redesign.

## Production presentation implementation

The selected visual language has now been applied to the shared semantic theme tokens, primary navigation, Chat empty state, Agent presentation and Knowledge presentation. Agent markup changes affect only the welcome copy and example prompts; its real request transport, history, cancellation, downloads, citations and change review handlers remain in place.

The production navigation uses the existing Lucide icon family, not the concept's numeric placeholders. Both themes retain semantic destructive, success and warning colours. The page shell is compact at 56 px on desktop and 48 px on mobile. Knowledge retains its real original preview and extracted passages rather than the prototype paper.

Direct Svelte compiler checks of WorkbenchNavigation, ChatScreenGreeting and AgentChat reported no warnings. Production browser verification remains the parent task's responsibility after the coordinated shell/sidebar dimensions and backend fixes are assembled. The earlier prototype screenshots do not certify the production presentation.
