# SovereignAI capability procedures

Skills are procedures, not permissions. The existing workflow stage selects the relevant local instructions; no additional model, router or planning call is required.

| Capability | Skill | Available execution surface |
| --- | --- | --- |
| Chat | [chat](runtime/chat/SKILL.md) | Local conversation answer |
| Evidence answers | [rag](runtime/rag/SKILL.md) | Indexed passages, source citations, verified table results |
| Documents | [documents](runtime/documents/SKILL.md) | Typed Knowledge document operations |
| Structured data | [spreadsheets](runtime/spreadsheets/SKILL.md) | Complete-source table catalog and deterministic query |
| Code | [coding](runtime/coding/SKILL.md) | Related source context, staged changes and validation |
| Run projects | [project-runner](runtime/project-runner/SKILL.md) | Docker file_run, terminal and bounded web preview |
| Artifacts | [artifacts](runtime/artifacts/SKILL.md) | Supported document/file generators and readback |
| Workspace | [workspace](runtime/workspace/SKILL.md) | Identity/revision guards and reviewed organization |

The shared [task contract](runtime/task-core/SKILL.md) accompanies the relevant skills. Only the selected stage's skills are injected, within a 6,500-character bound. Backend authorization, budgets, sandbox and validators remain authoritative. No arbitrary host Python, DuckDB, pandas or openpyxl tool is granted by these documents.

The library is enabled by default after the development diagnostic. SOVEREIGN_TASK_SKILLS=1 explicitly enables it; =0 disables it. Loaded instruction hashes are recorded in model route telemetry and raw diagnostic requests.

File-content generation selects the shared task contract plus coding only; project execution and workspace procedures remain selected at their respective workflow stages.
