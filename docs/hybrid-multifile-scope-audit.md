# Frozen hybrid multi-file scope audit

Read-only audit of F hybrid-dev-061/062/063 in benchmarks/hybrid-code-agent-results.json and development main.json. No production/harness/config edits, no model/Docker calls, no heldout inspection. This finding is retained for a later separately versioned fix; the running frozen comparison must remain unchanged.

## Confirmed generic target parsing defect

All three requests contain the structure `... into solution.py and leave a backward-compatible import in legacy.py. Implement ...`. Both files already exist. The selected active file is solution.py (currently `from legacy import <function>`); legacy.py contains the original stub. Requested changes therefore necessarily include implementation in solution.py and import re-export in legacy.py. Both paths are explicitly in the fixture's allowed_change_paths.

workflows/coding_workspace.py:1061 calculates named_paths using `(?<![\w./-])` + escaped existing filename + `(?![\w./-])`. The right boundary includes a period. Consequently sentence punctuation immediately following `legacy.py` prevents its recognition: `legacy.py.` is treated as a longer path token. Plain offline regex reproduction on the literal development requests produces **{'solution.py'} for all three cases**. Replacing only the sentence period after legacy.py with a space recognizes legacy.py. This reproduction evaluates text matching only; no candidate/program/provider execution occurs.

At lines1060–1063 the existing_files guard rejects any edit/delete whose path is absent from that erroneously narrowed set. Thus a correctly scoped edit of legacy.py can trigger exactly the observed generation_format error: “The plan changes a file outside the explicitly named targets; the project was left unchanged.” The guard runs before `_preflight_operation_plan` at1072 and before Docker candidate validation. Restrictive matching is an understandable path-safety intent, but sentence punctuation here creates a false negative rather than evidence of unauthorized scope.

## What the recorded evidence proves and does not prove

| Trial | Persisted planner strategy | Observed outcome | Attribution |
|---|---|---|---|
| 061 unique_sorted | Explicitly names solution.py implementation and legacy.py wrapper, no other files. Contains unnecessary try/except fallback and commit wording; this is untrusted model reference text, not publication authority. | generation_format, no validation trajectory | Confirmed parser defect can reject an authorized legacy.py edit. Actual generated operation list not persisted; whether it additionally named a third file remains UNKNOWN. |
| 062 reverse_chunks | Names solution.py and legacy.py, but introduces reverse_pairs and aliases it as reverse_chunks. That naming change could later violate required solution API; no generated source available. | same generation_format, no validation trajectory | Parser false negative confirmed; candidate scope and functional compliance UNKNOWN. |
| 063 nonzero_runs | Names solution.py implementation and legacy.py `from solution import nonzero_runs`, retains external signature. | same generation_format, no validation trajectory | Parser false negative confirmed; candidate operation list absent, so final responsibility remains partially UNKNOWN. |

Only PLAN_CREATED strategy is recorded (backend/service.py:915–917); operational_result.operation_plan and supervisor.task_state.plan are absent because guard rejection happens before validated operation-plan construction. A strategy is not the Coder's operation list. Do not infer that the Coder violated scope solely from the rejection message, and do not infer that correcting the parser guarantees these tasks pass. Independent Docker checks never ran in these rows.

The two observed switches establish planner/handoff cost, not necessity or benefit. No repair sequence exists for these three trials because generation/plan rejection precedes candidate validation. This is a generic punctuation-boundary issue, not a cohort/fixture-specific missing condition. Any later fix should preserve rejection of genuinely extended paths such as legacy.py.bak and subpaths, retain exact selected workspace and preflight checks, and receive new versioned measurements after the frozen run.
