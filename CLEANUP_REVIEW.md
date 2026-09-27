# Isolated local files for deletion review

Optional and duplicate items from this workstation were moved to `_review_for_deletion/`. Nothing in that folder is used by the current launcher. The folder is ignored by Git; it remains on this computer for the project owner to inspect and delete when ready.

| Isolated path | Why it was moved | Recreate if needed |
|---|---|---|
| `.venv/`, `.venv314/`, `.offline-check-20260925/`, `.offline-test-venv/` | Duplicate or temporary Python environments | `py -3.12 -m venv .app-venv` then `pip install -r requirements.txt` |
| `.pytest_cache/` | Test cache | Next `pytest` run |
| `setup-staging/`, `models/.cache/`, `models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf.parts/` | Installer/cache and download fragments; completed model assets remain in `models/` | Redownload if needed |
| `llama.cpp/` | Upstream source checkout; the app uses `runtime/llama-b11132/` and the built UI | Clone upstream if rebuilding; license preserved in `licenses/llama.cpp-LICENSE` |
| `offline/wheels/` | Local offline wheel cache; one `requirements.txt` drives normal installation | `pip download -r requirements.txt -d offline/wheels` |
| `frontend/app.js`, `frontend/index.html`, `frontend/style.css` | Superseded interface; backend serves `frontend/llama-ui/dist/` | Historical only |
| `Launch SovereignAI.bat` | Replaced by `Start SovereignAI.bat` and `Stop SovereignAI.bat` | Current launchers at project root |
| `requirements-phase2*.txt`, `requirements-runtime*.txt` | Replaced by the single pinned `requirements.txt` | Current file at project root |
| `frontend/llama-ui/node_modules/`, `frontend/llama-ui/.svelte-kit/` | npm dependency tree and Svelte build cache | `npm ci`, then `npm run build` in `frontend/llama-ui/` |
| `benchmarks/` generated reports, screenshots, logs, backup indexes and PDFs | Historical validation output; benchmark scripts and held-out text fixtures remain in the project | Rerun the relevant benchmark when needed |
| `docs/` historical plans, reports and screenshots, plus the vendored frontend README | Not needed for setup or operation; root README and two essential docs remain | Restore from this review folder if you want the development history |
| `offline-manifest.json` | Generated inventory of locally installed binaries and built files | `python scripts/create_offline_manifest.py` after installing local assets |

**Keep** `.app-venv/`, `models/` (apart from the moved fragments/cache), `runtime/`, `frontend/llama-ui/dist/`, `data/`, `outputs/`, `offline/Dockerfile.workbench`, source directories, and the two current launchers. `data/` and `outputs/` contain local user state and generated work; back them up independently. The review folder may be large because it contains old environments and download fragments.
