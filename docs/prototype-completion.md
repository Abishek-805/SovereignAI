# Prototype completion evidence

The direct-first production prototype is running at http://127.0.0.1:8088. The launcher and backend use the same installed text-model registry. Historical benchmarks remain stopped and preserved.

Verified through the application: chat; upload, indexing and cited retrieval; sourced Word report download; workspace edits; Python project creation; Docker execution; actual failure feedback and repair; independent function/output checks; acceptance; README readback; Word sections/tables; Excel layout, formula and cached-value checks; stored artifact retrieval; and a full backend/model restart.

Focused checks: 196 passed, one skipped. Frontend typecheck: zero errors/warnings. Production frontend build succeeded.

React/Vite generation and JSX syntax checks passed. The actual full Docker build is BLOCKED: exit 127, `vite: not found`. Project dependencies must be locally provisioned inside the sandbox. No network-policy or host-execution bypass was added. Spreadsheet calculation currently supports SUM over numeric ranges; other formulas are rejected explicitly.

106 original Python test modules/helpers were inspected and moved to the existing `_review_for_deletion/tests/` archive, preserving structure without permanent deletion. Pytest and compatibility imports point there.

Raw verification responses, failed attempts, downloaded artifacts and independent checks are preserved in `outputs/prototype-verification/`. Machine-readable status: `outputs/prototype-verification/summary.json`.

Start from the project root:

```powershell
.\start-sovereign.ps1 -NoBrowser
```

Then open http://127.0.0.1:8088. `Start SovereignAI.bat` starts the same services and opens the window.
