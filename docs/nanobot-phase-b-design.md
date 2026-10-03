# Phase B design: bounded repair with validated operation-plan reuse

Status: design only. Baseline `89fb7fe` remains frozen during its live evaluation. No production, evaluator, settings or Git HEAD change is proposed until that evidence is preserved. This is a narrow candidate F experiment, not a claim of architectural optimality.

## Goal and boundary

Avoid asking the model to rediscover the same authorized file-operation plan on each actual Docker failure. Keep generating fresh candidate source and independently executing it. Share stop policy and feedback formatting between the current project and single-file executors without introducing a second runtime owner or automatic publication.

Keep the public service signatures, worker broker, global budgets, selected workspace, test provenance, artifact IDs, staging and Accept transaction. Do not add upstream Nanobot as a dependency for this experiment. Its bounded runner and feedback patterns can be implemented behind the existing interfaces.

## Minimal interfaces

Add a pure policy module, provisionally `router/coding_repair.py`:

```python
@dataclass(frozen=True)
class RepairObservation:
    attempt: int                 # one-based candidate validation attempt
    executed: bool
    exit_code: int | None
    error_text: str              # existing bounded actual output
    source_issue: str | None     # observed source constraint, if any

@dataclass(frozen=True)
class RepairDecision:
    retry: bool
    stop_reason: str | None
    fingerprint: str | None

def decide_repair(observation, *, seen_fingerprints, max_attempts=3): ...
def repair_reference(*, original_request, workspace_id, target,
                     previous_changes, observation, task_state): ...
```

`decide_repair` is deterministic. It handles validation success, unavailable execution, missing diagnostic, repeated fingerprint and attempt budget. Cancellation, revision conflict and authorization remain authoritative executor/service checks before generation and staging. The pure helper must not execute tools, acquire a lease, persist results or declare task completion. Reuse `router.validation_feedback.failure_fingerprint` rather than creating another hashing policy.

Keep `repair_reference` at the current shared 10,000-character candidate budget, eight changes and bounded diagnostic size, preserving `content_complete`. It returns a structured object serialized once as untrusted reference data. It does not promote stderr or prior candidate text into system instructions.

Extend the existing internal workflow method with an optional, keyword-only argument:

```python
CodingWorkspace.run_project(..., history=None, *, reusable_plan=None)
```

When absent, behavior follows the existing path. A returned result gains an internal `operation_plan` envelope for the supervising service. Persisting that envelope is optional for the first experiment; in-process reuse is sufficient, and avoids treating editable disk data as authoritative. The result continues to carry the existing `changes`, validation observations and publication state.

```python
@dataclass(frozen=True)
class ValidatedOperationPlan:
    version: int
    workspace_id: str
    target: str
    request_sha256: str
    revision_sha256: str
    scope: str | None
    operations: tuple[Operation, ...]
    plan_sha256: str
```

The revision digest covers the immutable original raw file map (sorted relative paths plus byte hashes) and original folders. Request digest covers the resolved controlling request, not abbreviated follow-up text. Operations are copied into immutable, strictly validated values. The envelope is application-produced after schema, containment, existence, scope and budget checks; a model claiming `validated=True` cannot create it.

## Validation and reuse

Extract current operation preflight from `run_project` into one internal helper, provisionally `_validate_project_plan(plan, original_files, assets, folders, instruction)`. Both fresh and reused plans call it. Do not maintain a weaker cache validation branch.

Preflight preserves existing checks for supported actions/languages, bounded operation count, duplicate paths, containment, binary assets, explicit deletion, requested named targets, new-file versus existing-file authority, create/edit existence and exact literal spans. Validate all operations against a virtual sequential file/folder map before starting generation. This extraction must preserve current ordered dependency behavior and implicit parent folder counting.

Source generation still starts from the original files on every candidate attempt. Do not seed generated edits into the actual workspace or append previous generated source as the new original. The previous candidate remains feedback; unrelated source and trusted tests retain their original hashes.

Initially reuse only structurally valid plans whose scope, operations, original revisions and literal replacements remain unchanged. After each candidate failure, the service supplies the envelope to the next `run_project`. Reuse skips only `model.plan_workspace_edit`; code generation, source checks, actual Docker validation, revision checks, staging and review execute normally.

The first experiment regenerates all planned source files. Selective generation of just a diagnostic-named file is outside this minimal change: a traceback path does not prove cross-file independence, and using it as a mutation selector could silently miss dependency repairs.

## Stale and faulty plan behavior

| Observation | Action |
|---|---|
| Workspace bytes/folders changed | Stop `workspace_conflict` before any model request; require a new task on the new revision. Do not silently replan. |
| Workspace, target or controlling request digest differs | Reject reuse. Fresh planning is allowed only through the normal request admission with that current authority. Never inherit another task's plan. |
| Envelope/schema/hash malformed | Discard the cache and use normal fresh planning once within the current budget; record `PLAN_REUSE_REJECTED` with a bounded reason. Invalid cache content never authorizes operations. |
| Fresh or reused operation violates current scope/containment/policy | Terminal policy/input error. Do not ask a model to bypass the check. |
| Docker unavailable or execution not observed | Stop; unavailable infrastructure is not a candidate repair. |
| Actual source or execution failure with valid plan | Reuse on the next candidate attempt; preserve actual feedback. |
| Model explicitly requests a different plan during repair | No direct authority change. Optionally allow one fresh planning pass through the original preflight and unchanged original request. New paths still require original authorization. |
| Same actual failure repeats after one reuse | One bounded fresh replan may replace the next attempt only if an attempt remains; otherwise stop. It must produce a different valid plan hash to earn an execution attempt. Unchanged plan/hash stops as `repeated_failure`. |
| Budget, cancellation or revision conflict | Stop using existing terminal outcome; no synthetic success/finalization call. |

The repeated-failure replan is an experimental option, not a default relaxation: baseline-compatible configuration initially stops repeated failure as today. Evaluate plan reuse first with that policy unchanged. If a later experiment enables one replan, freeze and label it separately; it must not be silently merged into the cost comparison.

A valid plan can still be semantically faulty. Structural validation does not prove that it covers the user's task. Reuse must therefore not be reported as independent goal validation. Model strategy prose cannot replace the executable operation plan; only the validated operation schema can be reused.

## Ownership and events

The service owns the project candidate loop; the legacy single-file executor continues owning its candidate loop while both use the same pure stop/feedback helpers. This avoids moving persistence or transaction behavior in the same patch. The outer `TaskSupervisor` still owns real model-call, tool, time and switch budgets.

Add operational events `PLAN_CREATED`, `PLAN_REUSED`, `PLAN_REUSE_REJECTED`, `CANDIDATE_VALIDATED` and `REPAIR_STOPPED` with task ID, attempt, plan/candidate hashes and reason. Reuse events contain no prompt/source dump. Retain separate stage labels for semantic-review retries, source-shape retries and Docker repairs so the displayed repair counter is not mistaken for total model requests.

## Required tests before live comparison

1. Fake planner counts: actual executed first failure, second independent success; unchanged scope and revision produce one operation-planner call, two candidate generations, two executions and staged exact repaired bytes.
2. Fresh and reused preflight parity for traversal, absolute paths, duplicate paths, binary assets, unsupported action/type, unauthorized deletion, named-target escape and new-file scope attempting edits.
3. Reuse request/workspace/target mismatch cannot execute cached operations; stale revision stops before any planner/generator/executor request.
4. Original supplied tests remain byte-identical across repair; generated or edited tests cannot be counted as independent goal checks. Preserve candidate and staging hashes.
5. Missing execution, missing feedback, repeated failure, third attempt, cancellation before generation/after execution and external revision change preserve stop reasons and zero publication.
6. Literal replacements apply once against the original source on every attempt. A changed/missing/duplicated original span cannot reuse the plan. Folder-only and delete-only operations preserve existing results.
7. Nested decorated calls consume one outer budget. Source-shape and semantic-review requests still consume actual model-call slots. A plan cache cannot bypass global limits.
8. Legacy single-file helper migration preserves baseline reproduction, exact selected target, protected tests and its current three-attempt limit.
9. Explicit Accept rechecks revision and execution and publishes the staged repaired bytes; neither successful repair nor plan reuse publishes automatically.

Fake tests establish contract behavior, not live model quality. Run a real generated candidate failure → actual Docker diagnostic → Coder repair → independent supplied test pass before claiming automatic recovery. Do not inject fake failure to satisfy that demonstration.

## Experiment and adoption gate

Preserve completed E baseline evidence first. Freeze candidate F code/settings/harness and evaluate the same development cases serially with the same actual model files, context limits, Docker image, maximum attempts, source/review policy and independent oracles. Hold global residency policy constant. Do not read final held-out tasks while designing or tuning.

Expected mechanism: valid-plan repair rows should reduce operation-planner requests while retaining independent success rate. Measure actual per-stage requests, reused/rejected plans, validation trajectories, total latency, time to first public output, switches and sampled RAM/VRAM. Report rows with no executed repair separately; they cannot demonstrate the mechanism.

Adopt only if scoped regressions pass, no new scope/publication/cancellation failures occur, and paired development evidence supports lower measured cost without worsening validated outcomes. One sample or unreviewed model final text is insufficient. A decrease in call count with lower goal completion is a failed tradeoff. Report inconclusive intervals and semantic outcomes as UNKNOWN where appropriate.

An independent final evaluation follows candidate freeze. Full backend and frontend checks and actual Docker verification remain required gates. Documentation-only Phase B design itself supplies no measured runtime or quality gain.
