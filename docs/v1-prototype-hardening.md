# Prototype hardening verification

Historical benchmarks remain stopped and their raw evidence is preserved. This is a product workflow verification, not a new model comparison or a universal accuracy claim.

## Changes

Native streaming now receives the same bounded task skills as other model requests. Artifact content mentioning a Documents section no longer gets mistaken for a request to search existing documents. Deterministic table results remain authoritative.

Source generation receives a clear file-content request and the coding procedure; the original request and untrusted reference fields are preserved. New-file generation excludes unrelated workspace content. Omission of an explicitly requested file fails the request contract rather than passing syntax validation. A checked contract failure can consume an existing repair attempt. Eligible new Python CLI projects also execute their mapped entrypoint in Docker; syntax alone is insufficient.

Complex or multi-file code fidelity failures can escalate once to the existing Qwen3.5-4B worker at the second-attempt checkpoint. The original request, workspace revision, project map, candidate diff, exact error and action history are saved before switching. This uses the existing task budget, keeps one heavy model active, and adds no planning layer, model or retry. Set SOVEREIGN_CODE_ESCALATION=0 to disable it. Routing telemetry identifies the worker that completed the task. Ordinary simple repairs and dependency blockers do not automatically trigger this escalation.

The batch launcher forwards arguments, including -NoBrowser. Workspace identity/revision checks, staged review/Accept, cancellation and Docker security policy remain in place.

## Observed workflows

Fresh streaming chat, browser chat, document upload/indexing and cited RAG passed. Warm chat completed in 5.85 seconds in one observed run; this is not a latency distribution.

Python cross-file imports, Node execution and Java execution passed inside Docker. An actual ZeroDivisionError was captured, repaired, accepted and independently rerun; unrelated helpers and README were preserved.

Markdown staging/Accept/readback passed. DOCX sections/tables and XLSX formula/cached value 50 were downloaded and independently inspected. Deterministic spreadsheet analysis returned 50 with a source citation. Artifact bytes persisted after model unload/reload and backend restart.

Fresh natural-language creation requested main.py, helpers.py and README.md. Earlier Coder candidates omitted a helper or returned a filename as code; those raw failures were preserved and never accepted. The final workflow produced all three files, passed Docker runtime validation, was accepted, and ran through the project map. A separate Docker oracle asserted helpers.answer() == 42 and imported main successfully. The checkpoint escalation path demonstrated completion within two attempts; this is a narrow workflow result, not evidence of general model superiority.

346 focused regression tests passed; 2 skipped. Frontend type checking reported zero errors/warnings; production build and browser chat smoke passed. Both PowerShell and batch -NoBrowser startup, backend restart and model unload/reload passed.

## Remaining limitation

React/Vite offline dependency provisioning is BLOCKED: npm reported ENOTCACHED for @types/react. The current sandbox lacks the complete project dependencies. No network was enabled, generated code was not run on the host, and a build success was not fabricated. Frameworks with unavailable dependencies can still block; model-generated code still needs independent validation.

## Evidence and startup

Raw product evidence and machine-readable summary are in outputs/v1-hardening/. Original failed attempts are retained alongside final-project-generation.json, final-project-accept.json, final-project-run.json and final-project-oracle.json.

Run `.\start-sovereign.ps1 -NoBrowser`, or `"Start SovereignAI.bat" -NoBrowser`.
