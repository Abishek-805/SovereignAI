# DEV-055 routing-context audit

Read-only, 2026-10-03. Source and the requested DEV row only; no held-out cases, models or Docker were used. No production, harness, settings or frozen results changed.

## Observed result

`benchmarks/hybrid-code-agent/main.json`, case `hybrid-dev-055`, asks: `Implment even_position_sum in solution.py. Sum items at zero-based even positions; empty returns zero.` Its selected active file is `solution.py`, with source `def even_position_sum(values):\n    return None\n`; its scope is that one existing file. The typo is in the imperative verb, not the symbol/path. The fixture requests implementation, not a document calculation.

`benchmarks/hybrid-code-agent-results.json`, matching row, records fixture SHA256 `1d793a2b79b8a497374fd4b93fef0a5f42a4549344bb13a9c65e6e16df7a4373`, advisory `CLARIFICATION`, Coder worker, two model calls, zero tool calls, no validation trajectory, and `needs_input: Use Agent for document questions and calculations`. Normalized text preserves `Implment`. The telemetry's original context contains workspace ID and target; its final code-task context has `context_scope: null`. There are no recorded semantic-review stages.

## Source-backed failure path

1. `router/request_normalization.py:5-6` contains a small correction map which does not correct this verb. Identifier/path protection is appropriate and should remain.
2. `router/coding_router.py:56-65` recognizes a finite set of imperative verbs including `implement`, not this misspelling. Active-file/workspace context makes this a coding context (`:70-74`), but an unknown task family falls back to `CLARIFICATION` (`:83-87`). Thus the advisory classifier misses the requested implementation; this does not itself establish document intent.
3. `router/tool_registry.py:15-65` similarly checks explicit mutation authority through normalized, unquoted ordinary verbs. Here `file_edit` is not recognized. `backend/service.py:924-927` therefore cannot use direct coding intent and falls back to `self.model.plan_task(instruction, [], [], [])`.
4. That fallback supplies empty documents, empty workspace files and empty history, despite the service already possessing workspace/target scope. `LocalModel.plan_task` exposes those lists to the model (`backend/model.py:825, 852`), and restricts its grammar to exclude the code branch when `explicit_operation_requested(goal, 'file_edit')` fails (`:885-889`). Consequently `edit_code` is unavailable to this interpretation attempt even if the model understands the typo. This is a deterministic authority/grammar limitation before source generation.
5. A non-answer, non-inspect, non-edit result reaches `backend/service.py:954`, whose generic error text is `Use Agent for document questions and calculations`. The model's exact action is not recorded, so this trace does **not** prove it selected `calculate` rather than `search_documents`, `create_report`, or another excluded action. The error message groups several actions and cannot identify the precise semantic decision.

The failure is before workspace planning/source generation and sandbox validation. Coder was selected; swapping workers alone cannot override a grammar which excludes the necessary action. The two model calls are compatible with interpretation/planning, but their exact candidate/action contents are not retained, so no stronger attribution is justified.

## General improvement proposal

Preserve the distinction between advisory task classification and authorization. For uncertain wording in an explicitly selected coding workspace, provide a bounded application-owned context envelope to semantic interpretation: mode, selected workspace/active file, permitted target paths, original request, and relevant safe metadata. Do not pass empty project context or fabricate available files. Do not make selected workspace alone authorize mutation.

Replace the ambiguous fallback error with a typed interpretation result that retains selected action and evidence of user intent. A semantic authorization proposal can identify the request span expressing the desired mutation and requested scope. Application validation must reject quoted/source-derived commands, scope expansion and destructive/execution requests without authorization. If intent cannot be established, ask an accurate clarification; never imply document intent solely because the code branch was unavailable. Any authorized implementation still requires normal plan preflight, fresh source generation, Docker validation and reviewed publication.

This needs a designed authority contract, not adding one misspelling or forcing code for any workspace question. Regression cases should cover varied misspelled imperatives, intact identifiers, explanations mentioning edits, quoted malicious commands, document calculations while a workspace is selected, ambiguous follow-ups, and unauthorized target changes. Record grammar identity and interpreted action in bounded telemetry to distinguish semantic misclassification from grammar denial. Unit checks can verify context and authority flow; later live evaluation must measure actual understanding and correctness separately. No fix or verified-success claim is made here.
