# SovereignAI

SovereignAI is a local Windows AI workbench with Chat, Agent, Code, Knowledge, and Control Center. The backend serves the built Svelte interface on `http://127.0.0.1:8088`; a local llama.cpp server listens on `127.0.0.1:8087`. Indexed documents stay in `data/` and support cited answers. Code execution uses a separately verified Docker sandbox.

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
- **Agent** chooses a bounded local workflow. An attached indexed document is always searched; a related question with no explicit selection also searches the indexed library when matching evidence exists. Edits and code tests require the Code workspace and Docker.
- **Knowledge** imports PDF, DOCX, TXT and Markdown, manages the library, selects source documents and folders, and asks cited questions. With no selection, the document question endpoint searches all indexed documents. Original documents and source passages are inspectable.
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

In Chat, an explicit request to switch to Agent opens the Agent workspace with the remaining text as its draft. In Knowledge, naming a document identifier such as `24ALR001` focuses retrieval on that document even when other library files are selected. Code and Agent show the saved diff with added and removed line counts; Undo restores the previous file only if no subsequent edit has changed it. Python error-repair requests run the file in the Docker sandbox before an edit is marked applied. Without supplied tests, this verifies that the program exits successfully, not that every behavior is correct; other file edits receive syntax or format checks. A task that produces no edit or fails its check is reported as failed and leaves the original file in place.
