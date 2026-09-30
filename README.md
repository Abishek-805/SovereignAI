# SovereignAI

SovereignAI is a local Windows AI workbench with Chat, Agent, Code, Knowledge, and Control Center. The backend serves the built Svelte interface on `http://127.0.0.1:8088`; a local llama.cpp server listens on `127.0.0.1:8087`. Indexed documents stay in `data/` and support cited answers. Code execution uses a separately verified Docker sandbox.

Code projects use live files under `Documents\SovereignAI\Projects` on the default installation. Existing projects migrate without deleting their initial internal snapshots. Set `SOVEREIGN_PROJECT_DIR` before starting the backend to choose another managed project root. Code's File menu opens the current project in File Explorer or an installed Visual Studio Code; external changes appear through Refresh while unsaved editor drafts are preserved. Docker terminal paths refer to an isolated execution copy, rather than the Windows host path. Embedded Git, debugger adapters, extensions and persistent PTY sessions remain outside the internal editor's implemented feature set.

Chat and Agent default to Knowledge connected with all documents available. Switching Knowledge off persists; the model decides whether a connected question requires evidence retrieval. Availability does not force greetings and unrelated questions to search files. The library exposes Rename, Move, Copy and Delete; Move organizes the library and Delete removes its indexed records, leaving original files/source snapshots on disk.

## Quick start on Windows

1. Install **Python 3.12**, **Node.js with npm**, and (for code execution) **Docker Desktop with a Linux engine**. A CUDA-capable Windows GPU is recommended for the bundled llama.cpp build. Python and Node must be on `PATH` (`py -3.12`, `npm`).
2. Clone this repository. Binary model weights, the llama.cpp executable/DLLs, generated data, and local virtual environments are deliberately not stored in Git. Install the assets listed below at their exact paths. The app can show the interface without Docker, but model requests need the text GGUF and runtime.
3. Double-click **`Start SovereignAI.bat`**. On the first start it creates `.app-venv`, installs the one Python dependency set from `requirements.txt`, runs `npm ci` and builds the frontend if needed. It then starts the model and backend, waits for health checks, and opens the app. Later starts reuse those installations. To stop owned services, double-click **`Stop SovereignAI.bat`**.

For a manual install or an agent setting up the project:

```powershell
py -3.12 -m venv .app-venv
.\.app-venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend\llama-ui
npm ci
npm run build
cd ..\..
.\.app-venv\Scripts\python.exe setup-embeddings.py
.\'Start SovereignAI.bat'
```

`setup-embeddings.py` verifies pinned BGE assets and downloads missing files through the `hf` CLI (installed by `requirements.txt`). This one-time setup needs internet. The project makes local model requests after setup. The frontend build is generated from source and can be repeated after UI changes.

## Required local assets

| Purpose | Required location | Source and verification |
|---|---|---|
| Text model | `models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf` | [LM Studio Community Qwen3-4B-Instruct-2507 GGUF](https://huggingface.co/lmstudio-community/Qwen3-4B-Instruct-2507-GGUF), revision `4edb920b6f14e3b9284d4502a6485103d72cde05`; SHA-256 `8cdb57cbb880d313736a9bc4e3d3d2485f145b5e19cf33783746e753e82641fc`. |
| Embeddings for RAG | `models/bge-small-en-v1.5/` | Run `setup-embeddings.py`; it checks every pinned file in `embedding-manifest.json`. |
| llama.cpp runtime | `runtime/llama-b11132/llama-server.exe` and its release DLLs | [llama.cpp b11132 Windows x64 CUDA 12.4 release](https://github.com/ggml-org/llama.cpp/releases/tag/b11132). Keep the release files together. |
| Vision (optional) | `models/vision-qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf` and `mmproj-F16.gguf` | [Unsloth Qwen3.5-2B GGUF](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF), revision and hashes in [model notices](docs/model-and-runtime-notices.md). |

The launcher checks the required text model and runtime and reports missing paths. The model file is over GitHub's normal file limit, so install it locally; do not commit it. `requirements.txt` pins the full Python environment, including tests, OCR, document exports, and the Hugging Face setup CLI. `frontend/llama-ui/package-lock.json` pins npm dependencies. For Docker Code mode, use **Control Center → Runtimes** or **Start Docker** in Code to prepare the sandbox; Docker is not needed for Chat or document questions.

For the pinned text model, after installing `requirements.txt` run:

```powershell
.\.app-venv\Scripts\hf.exe download lmstudio-community/Qwen3-4B-Instruct-2507-GGUF Qwen3-4B-Instruct-2507-Q4_K_M.gguf --revision 4edb920b6f14e3b9284d4502a6485103d72cde05 --local-dir models
Get-FileHash .\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf -Algorithm SHA256
```

For the runtime, download the [b11132 Windows CUDA 12.4 archive](https://github.com/ggml-org/llama.cpp/releases/download/b11132/llama-b11132-bin-win-cuda-12.4-x64.zip) and its [CUDA 12.4 DLL archive](https://github.com/ggml-org/llama.cpp/releases/download/b11132/cudart-llama-bin-win-cuda-12.4-x64.zip). Extract both into `runtime/llama-b11132/` so that `llama-server.exe` is directly in that folder. An agent should check the required paths and hashes before attempting to launch. The runtime archive may require a compatible NVIDIA driver/CUDA environment on another Windows machine.

## Using the workbench

- **Chat** handles ordinary conversation. When the prompt is clearly about indexed knowledge, the backend retrieves matching passages and provides bounded source context with `[S1]` citations. The read-only `search_documents` tool is also available. Chat citations are model output, so use Knowledge for source-checked answers.
- **Agent** chooses a bounded local workflow. Connected documents are references available to the current request, not an instruction to retrieve them. Knowledge Off supplies no library documents; Knowledge On allows focused retrieval when evidence is needed. Agent code changes are staged outside the canonical project. **Accept changes** validates the saved draft in Docker if needed, checks the project revisions again, and saves it to the local project. If Docker is offline, the draft stays available for review; start Docker and choose Accept again.

Agent planning uses the current request, up to eight recent conversation exchanges, selected project files and folders, and the available Knowledge names. Code tasks use a project-wide model plan to choose files and relationships; the project name is not repeated as a directory inside its own workspace. Agent file move/copy/delete and folder creation produce reviewed drafts; an existing folder is reused, and a destination-name collision becomes a reviewed replacement with revision checks. Docker validation and explicit Accept are required to publish these drafts. The task input limit is 8,000 characters. The text model keeps its measured 24,576-token context and quantized KV cache on the tested 4 GB GPU; its runtime generation ceiling is 8,192 tokens, with individual workflows using smaller context-aware budgets. Longer context consumes more KV memory, so the context limit is not raised beyond the measured laptop profile.

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
| `tests/`, `benchmarks/`, `samples/` | Checks, benchmark scripts and examples |
| `docs/` | Essential Windows shortcuts and model/runtime notices |
| `_review_for_deletion/` | Isolated optional local copies and caches; see its inventory before removing |

Only the two root `.bat` files are intended as user launchers. Supporting `.ps1` scripts are implementation files. `start-sovereign.ps1 -NoBrowser` and `stop-sovereign.ps1` are available to automation. The launchers manage only their own listeners on ports 8087 and 8088 and reject unrelated services on those ports. Stop also recognizes this project's workbench when its PID file is missing, including an older `.venv` instance. Start replaces such an older instance with the current `.app-venv` workbench.

## Verification and troubleshooting

```powershell
.\.app-venv\Scripts\python.exe -m pytest -q
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

On the tested 16 GB RAM / 4 GB RTX 3050 A laptop, the existing Qwen3-4B model passed isolated project TXT creation and Knowledge document revision checks. Qwen3.5-4B Q4_K_M was identified as a candidate, but its download failed at the CDN; it has not been evaluated or enabled. Installing a larger model alone does not fix application routing or file publication. Model downloads must pass checksum and live task checks before activation. A functional comparison of local coding agent tools is recorded in [the local agent evaluation](docs/local-agent-evaluation.md).

To remove a local coding project, select it in Code and choose the trash button beside the project picker. Confirming permanently removes only that managed project and its files. Save or discard open edits first; Knowledge documents are managed separately.
