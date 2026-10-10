# SovereignAI

SovereignAI is a local Windows AI workbench with Chat, Agent, Code, Knowledge, and Control Center. The backend serves the built Svelte interface on `http://127.0.0.1:8088`; a local llama.cpp server listens on `127.0.0.1:8087`. Indexed documents stay in `data/` and support cited answers. Code execution uses a separately verified Docker sandbox.

Production uses a direct-first hot local model. Ordinary chat goes straight to generation; project runs use an evidence-based project map; code changes reuse bounded Docker validation and repair. Historical reports and benchmark results are preserved; comparisons remain stopped. Staged changes still require Docker validation and user Accept before publication.

Code projects use live files under `Documents\SovereignAI\Projects` on the default installation. Existing projects migrate without deleting their initial internal snapshots. Set `SOVEREIGN_PROJECT_DIR` before starting the backend to choose another managed project root. Code's File menu opens the current project in File Explorer or an installed Visual Studio Code; external changes appear through Refresh while unsaved editor drafts are preserved. Docker terminal paths refer to an isolated execution copy, rather than the Windows host path. Embedded Git, debugger adapters, extensions and persistent PTY sessions remain outside the internal editor's implemented feature set.

Chat and Agent default to Knowledge connected with all documents available. Switching Knowledge off persists; ordinary conversation bypasses retrieval, while document requests use the existing evidence path. Availability does not force greetings and unrelated questions to search files. The library exposes Rename, Move, Copy and Delete; Move organizes the library and Delete removes its indexed records, leaving original files/source snapshots on disk.

Knowledge uploads appear before background indexing finishes. Spreadsheet previews show original sheets and stored cell formatting; extracted passages remain a separate view. Document questions can query complete tables for lookups and aggregates. Code and Agent show named pending changes before acceptance. See [implementation evidence and preview limits](docs/table-preview-and-query-results.md).

## Quick start on Windows

1. Install **Python 3.12**, **Node.js 22 LTS with npm**, and a compatible **NVIDIA driver**. Put Python and npm on PATH (`py -3.12`, `npm`). The supplied Windows x64 llama.cpp runtime uses CUDA 12.4; other operating systems and non-NVIDIA runtime profiles are not provisioned by this launcher.
2. Clone this repository and allow approximately **35 GB of free disk space** for models, download cache, runtime and dependencies. First setup needs internet. Model files alone total about 12.4 GB; setup time depends on the connection. Docker Desktop with its Linux engine is additionally required for generated-code execution.
3. Double-click **`Start SovereignAI.bat`**, or run the following from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-sovereign.ps1
```

The launcher creates `.app-venv`, installs the pinned `requirements.txt` when its recorded hash changes, and runs **`setup-assets.py`**. Setup verifies existing model hashes and downloads missing or mismatched registered assets at their pinned revisions. It prepares BGE embeddings and downloads the pinned llama.cpp runtime archives when required runtime files are missing. It then runs `npm ci` and builds the frontend if no build exists, starts owned services, checks readiness, and opens **http://127.0.0.1:8088/**. Model inference stays on **127.0.0.1:8087**. Models are loaded individually by the existing router, not simultaneously.

Later starts reuse installed dependencies, runtime and valid model files; model checksum checks still run. Interrupted Hugging Face downloads can resume on retry. A failed checksum, inaccessible model, missing prerequisite or occupied unowned port stops setup with an error; the launcher does not substitute another model or stop unrelated services. Use **`Stop SovereignAI.bat`** to stop owned services.

### Instructions for an agent asked to run this project

Run the normal launcher above with `-NoBrowser` when no browser window is needed. Do not stop after starting a download: wait for setup and frontend build to finish, then verify `/health` on ports 8088 and 8087. Report the actual model/runtime and any blocked prerequisite. Do not report successful startup from a running process alone. The first setup may take much longer than model inference.

To prepare assets separately without launching or restarting any service:

```powershell
py -3.12 -m venv .app-venv
.\.app-venv\Scripts\python.exe -m pip install -r requirements.txt
.\.app-venv\Scripts\python.exe setup-assets.py
```

All inference assets are pinned in **[model-assets.json](model-assets.json)**; BGE's per-file manifest is **[embedding-manifest.json](embedding-manifest.json)**. The setup script installs:

| Role | Local asset |
|---|---|
| Primary reasoning/chat | `models/Qwen3.5-4B-Q4_K_M.gguf` |
| RAG/lightweight worker | `models/gemma-4-E2B-it-Q4_K_M.gguf` |
| Coding | `models/qwen2.5-coder-3b-instruct-q4_k_m.gguf` |
| Vision | `models/vision-qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf` and `mmproj-F16.gguf` |
| Legacy registered text fallback | `models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf` |
| Document embeddings | `models/bge-small-en-v1.5/` |
| Inference runtime | `runtime/llama-b11132/llama-server.exe` and release DLLs |

GGUF/projector downloads and newly downloaded runtime archives are SHA-256 checked. An already installed complete runtime is reused; presence checks do not independently attest existing runtime binaries. Source revisions, model licenses and official links are in [model notices](docs/model-and-runtime-notices.md). Honor upstream access/license requirements; if a repository requires authentication, configure the Hugging Face CLI on the setup machine and retry. Do not commit weights, runtime binaries, credentials or user documents. This setup downloads inference assets only; it does not train, merge or deploy adapters.

### Docker for code execution

Chat and document questions can run without Docker. For Code/Agent execution, start Docker Desktop and wait for its Linux engine. On a fresh machine, build the project's image and run its isolation verification:

```powershell
docker build -f offline/Dockerfile.workbench -t sovereign-workbench:latest .
$sandboxImage = (docker image inspect sovereign-workbench:latest --format '{{.Id}}').Trim()
.\.app-venv\Scripts\python.exe scripts/verify_docker_sandbox.py $sandboxImage
```

Building the image needs internet. Generated code subsequently runs in the verified sandbox with networking disabled. Use the application's Docker verification action to renew an expired verification. If Docker or isolation checks fail, code execution remains blocked; no host execution fallback is allowed. Creating the environment does not establish production acceptance: live RAG, code generation, previews and stability must be checked on the actual installation.

## Direct-first prototype workflows

The launcher reads the installed text entry in the backend model registry; startup and backend requests use the same local model. The asset manifest provisions every registered inference model, including the legacy Qwen3 fallback.

- Run this project uses package, README and entrypoint evidence, including a uniquely nested npm project. Ambiguous entrypoints require selection.
- Word/Excel creation produces structured data, then python-docx/openpyxl writes and reopens the file. Generated documents are indexed and downloadable in Knowledge. SUM formulas over numeric ranges are independently calculated and saved with cached values for offline readers. Unsupported formulas are rejected with the actual diagnostic.
- React/Vite source can be created and JSX/TSX syntax checked. Full builds require locally provisioned project dependencies in Docker. Missing Vite returns BLOCKED with the real exit code; there is no sandbox network or host execution fallback.
- Python tests now live in the existing `_review_for_deletion/tests/` folder. `pytest.ini` points there. Benchmark evidence, models and user documents remain intact.

## Using the workbench

- **Chat** handles ordinary conversation. When the prompt is clearly about indexed knowledge, the backend retrieves matching passages and provides bounded source context with `[S1]` citations. The read-only `search_documents` tool is also available. Chat citations are model output, so use Knowledge for source-checked answers.
- **Agent** chooses a bounded local workflow. Connected documents are references available to the current request, not an instruction to retrieve them. Knowledge Off supplies no library documents; Knowledge On allows focused retrieval when evidence is needed. Agent code changes are staged outside the canonical project. **Accept changes** validates the saved draft in Docker if needed, checks the project revisions again, and saves it to the local project. If Docker is offline, the draft stays available for review; start Docker and choose Accept again.

Optional application operation selection uses the current request, up to eight recent conversation exchanges, selected project files and folders, and the available Knowledge names. Code tasks use the same hot model with selected project context and bounded execution feedback; the project name is not repeated as a directory inside its own workspace. Agent file move/copy/delete and folder creation produce reviewed drafts; an existing folder is reused, and a destination-name collision becomes a reviewed replacement with revision checks. Docker validation and explicit Accept are required to publish these drafts. The task input limit is 8,000 characters. The text model keeps its measured 24,576-token context and quantized KV cache on the tested 4 GB GPU; its runtime generation ceiling is 8,192 tokens, with individual workflows using smaller context-aware budgets. Longer context consumes more KV memory, so the context limit is not raised beyond the measured laptop profile.

Agent requests to delete every file in a selected project use one scoped, reviewed draft rather than an eight-file plan. A named existing folder can be preserved with its contents; the proposed file and folder removals appear in review before Accept. If the model lists only some files for an “all files except” request without identifying the preserved folder, no partial deletion is staged. A created Knowledge document has an **Open in Knowledge** action in its Agent result.
- **Knowledge** imports PDF, DOCX, XLSX and PPTX plus UTF-8 or BOM-marked UTF-16 text: TXT/Markdown, CSV/TSV, JSON/JSONL, logs, XML/HTML, YAML/TOML/INI, and common source-code extensions. Imports report extraction and passage-indexing progress and offer **Stop import**. Stop waits for the current parser/embedding call and prevents subsequent publication. XLSX reads stored cells without expanding empty worksheet dimensions; formulas use cached values and numeric dates retain stored numbers. Legacy binary XLS/DOC files need an XLSX/DOCX or text export. The library manages documents, selects source documents and folders, and asks cited questions. The legacy document-question endpoint can search all indexed documents when its document scope is omitted; an explicit empty scope searches none. Original documents and source passages are inspectable.
- **Code** offers an explorer, editor, file operations, assistant, and terminal with resizable panels and Windows shortcuts. Its execution is sandboxed. The UI is a bounded workspace, not access to the host's whole disk.
- **Control Center → Models & routing / Runtimes / System & downloads / Appearance** shows current model, runtime and sandbox state, artifacts, and theme controls. It does not start Docker or a model simply by opening the page.

## Project layout

| Path | Role |
|---|---|
| `backend/`, `rag/`, `router/`, `workflows/` | API, indexing/retrieval, model routing, and bounded tasks |
| `frontend/llama-ui/` | Svelte application source and generated `dist/` served by the API |
| `scripts/`, `setup-embeddings.py` | Setup, validation, offline and operational utilities |
| `models/`, `runtime/` | Local model assets and llama.cpp runtime (ignored by Git) |
| `offline/Dockerfile.workbench` | Reproducible Linux code sandbox recipe |
| `data/`, `outputs/` | Local document index, tasks, user files and generated artifacts (ignored by Git; back up separately) |
| `_review_for_deletion/tests/`, `benchmarks/`, `samples/` | Archived runnable checks, historical benchmark evidence, and examples |
| `docs/` | Essential Windows shortcuts and model/runtime notices |
| `_review_for_deletion/` | Isolated optional local copies and caches; see its inventory before removing |

Only the two root `.bat` files are intended as user launchers. Supporting `.ps1` scripts are implementation files. `start-sovereign.ps1 -NoBrowser` and `stop-sovereign.ps1` are available to automation. The launchers manage only their own listeners on ports 8087 and 8088 and reject unrelated services on those ports. Stop also recognizes this project's workbench when its PID file is missing, including an older `.venv` instance. Start replaces such an older instance with the current `.app-venv` workbench.

## Verification and troubleshooting

```powershell
.\.app-venv\Scripts\python.exe -m pytest tests _review_for_deletion/tests -q
cd frontend\llama-ui
npm run check
npm run build
```

If startup fails, read `benchmarks/server.stderr.log` and `benchmarks/workbench.stderr.log`. Verify asset checksums and the Python/Node commands above. The model and Docker are intentionally not launched by `pytest`, `npm run check`, or `npm run build`. The first launch can take time to install dependencies; later launches reuse `.app-venv` and the built UI. Port and model status are visible in Control Center.

If port 8088 is occupied, run `Stop SovereignAI.bat` and try again. The launcher will leave an unrelated process on that port untouched; close that application separately if the warning persists. After replacing an older workbench, refresh the browser tab to discard its stale API errors.

See [Windows shortcuts](docs/WINDOWS_SHORTCUTS.md), [runtime and model notices](docs/model-and-runtime-notices.md), and [cleanup inventory](CLEANUP_REVIEW.md) for more detail.

In Chat, an explicit request to switch to Agent opens the Agent workspace with the remaining text as its draft. In Knowledge, naming a document identifier such as `24ALR001` focuses retrieval on that document even when other library files are selected. General conversation is answered by the local text model before document retrieval or project inspection. Greetings and identity questions do not run Docker or edit code; their answers are generated rather than canned. Enter sends a Code request and Shift+Enter adds a line. Submitted requests remain visible while they run. Code and Agent inspect the selected workspace tree and can plan up to eight changes per task. Generated changes are staged outside the project and reviewed before Accept. Docker validation is required for publication; a syntax or format check does not prove functional correctness. If Docker is unavailable, the draft cannot be published. Undo restores published files only if they have not changed since publication. Failed checks leave the project unchanged. A brief “try again” after a failed Agent turn retries that specific request. The Control Center's **Reset chat tokens · New chat** action starts an empty Chat context while retaining earlier conversations; it does not increase the model's fixed context window. Knowledge is the document library; Chat and Agent consume its connected context.

The current UI and routing/model engineering workstreams are tracked in [the workbench upgrade plan](docs/workbench-upgrade-plan.md). It distinguishes implemented intent handling from the pending CPU classifier, resource-aware model selection, and local model comparisons.

Knowledge source snapshots are stored in `Documents/SovereignAI/Knowledge` by default alongside `Projects`. Existing snapshots are copied there without deleting the earlier data snapshot. Filenames are content hashes so citations retain their original versions; manage display names and folders through Knowledge. `SOVEREIGN_KNOWLEDGE_DIR` overrides this location. Backups include the live Knowledge folder.

New XLSX, CSV/TSV, JSON/JSONL, YAML, XML, TOML and INI/CFG imports use a hybrid structured index: rows/records and field or cell references remain searchable in SQLite FTS, while compact table descriptions receive semantic embeddings. This avoids embedding thousands of numeric rows. Exact record matches rank ahead of table descriptions; semantic search identifies table context. Retrieved excerpts do not compute exhaustive totals over a whole table. Existing unchanged indexed versions are retained. Import has its own bounded background job slot and can run alongside one Agent/Code/document job; two imports or two execution jobs remain serialized. Indexing uses the local CPU embedding model, without loading another chat model. Document rename/move/delete does not wait for the full embedding process, and a changed or deleted target blocks stale publication. Large previews show 100 passages at a time with navigation and direct citation access. See [structured import measurements](docs/structured-import-results.md).

The latest routing implementation, measurements and unresolved release gates are recorded in [the final routing integration report](docs/final-routing-system-integration.md). Candidate/resource/context filtering and request-owned routing telemetry are implemented; the evaluated CPU classifier remains disabled until its quality gates pass.

## Code language setup

HTML/HTM uses **Preview** beside Save; CSS belongs in an HTML preview. Program Run supports the language adapters listed in [coding compatibility](docs/coding-language-compatibility.md). Python dependencies in `requirements.txt` do not install compilers: those live only in the Docker image. No host-language SDK installation is required for sandbox programs.

With Docker Desktop's Linux engine running, build and verify the image before enabling execution:

```powershell
.\scripts\prepare-workbench-sandbox.ps1
```

The sandbox verifier records the pinned image only after its isolation probes pass. The language verifier checks compilation and execution and records the actual results. First-time Docker builds download compilers and can take time; subsequent builds reuse layers. Third-party package downloads are blocked during execution, and standalone adapters do not imply full framework, GUI, debugger or package-project support.

Chat and Agent have separate behavior: Chat returns requested code/file contents inline and never automatically submits them to Agent. Use the Agent button explicitly to work on files. Agent creates ordinary text/code files in its selected project; explicit Knowledge text updates retain document identity and earlier source snapshots. The default Code sandbox has 11 program adapters; C#, Ruby, R, Lua and Perl were removed to reduce its footprint. See the current compatibility table before using Run.

The 2026-10-01 laptop comparison selects Gemma 4 E2B Q4_K_M for general tasks and Qwen2.5 Coder 3B Q4_K_M for code when their verified assets are installed. Qwen3 remains the default on a baseline-only installation. Run `.\.app-venv\Scripts\python.exe benchmarks/download-model-candidates.py` to download the pinned, checksum-verified candidates. Only one owned llama.cpp model runs at a time; code requests switch to the specialist and general requests switch back. Each selected model uses a bounded context and the runtime keeps a GPU margin for the desktop. See [the measured comparison](docs/laptop-model-comparison.md) for timings and limitations.

To remove a local coding project, select it in Code and choose the trash button beside the project picker. Confirming permanently removes only that managed project and its files. Save or discard open edits first; Knowledge documents are managed separately.
