# Minimal semantic-review contract correction design

Proposal only, 2026-10-03. This document changes no production, harness, configuration or frozen acceptance results. No models, Docker or held-out cases were consulted. Evidence and its uncertainties are in `docs/hybrid-plan-contract-audit.md`.

## Recommendation

Use a typed current-stage review contract and permit one bounded correction of an invalid reviewer response. Retain the existing planner retry budget, scope checks, fresh generation, Docker validation, revision checks and reviewed publication. Do not reduce review calls as the primary fix: fewer calls reduce latency, but cannot resolve feedback that the active grammar cannot express.

Implement first for workspace-operation planning through an explicit optional argument to `_planned_completion`; preserve the existing path for other artifacts until separately evaluated. This is a general artifact contract, not a test/request keyword classifier. Do not implement during the frozen run.

## Small concrete interface

Application-owned immutable `ReviewContract`:

```python
@dataclass(frozen=True)
class ReviewContract:
    stage: str
    artifact_schema: dict
    obligations: tuple[str, ...]
    deferred_obligations: tuple[str, ...]
    contract_version: str

def _planned_completion(payload, *, review_contract=None, ...): ...
```

For workspace plans, obligations cover authorized scope, exact targets, actions, requested interfaces/intent, and file responsibilities when required by the controlling request. Deferred obligations cover complete source, execution results, and passing runtime checks. The application supplies the actual active schema including whether nonempty replacements are permitted. The planner grammar and reviewer schema must derive from the same authoritative definition; an independently duplicated schema can recreate this defect.

Typed review result:

```json
{"verdict":"revise","issues":[{
  "obligation":"requested_intent",
  "candidate_pointer":"/operations/0/reason",
  "request_evidence":"...",
  "defect":"...",
  "requested_correction":"..."
}]}
```

An omitted required field may use its expected schema path; a missing operation may identify the operations array. Pointer validation must permit legitimate omissions, rather than requiring every rejected field already exist. The strict JSON response schema bounds issue counts/text sizes. Application validation confirms supported obligation identifiers, valid candidate/schema paths, and whether proposed structural fields are expressible. It cannot mechanically prove arbitrary natural-language semantic fidelity; that remains model review plus later executable validation.

## Bounded correction flow

1. Generate candidate under the active grammar and run ordinary syntax/schema validation.
2. Review candidate against controlling request, untrusted reference history, and the application contract.
3. Accept only a valid `accept` with no issues. A valid rejection invokes the existing bounded planner repair path.
4. If review output violates its own contract, run **at most one** review correction on the same candidate. Provide the original candidate, contract and an application-produced structural diagnostic; request a corrected review, not a changed plan. Charge this call to the existing supervisor model/time budget and obey cancellation/resource leases.
5. Invalid corrected review or unresolved uncertainty terminates safely. Never convert invalid rejection into automatic acceptance; never skip scope checks or runtime validation.

Initially, automatic contract invalidation should cover deterministic structural violations only: unknown obligations, invalid field/schema paths and forbidden structural corrections. Requests for downstream code conveyed solely in free text cannot be reliably classified with a generic string search. The typed deferred-obligation identifiers help expose those errors, but model mislabelling remains a limitation. A prose-only rejection can require a typed corrected review; it must not be guessed safe.

## Options and tradeoffs

| Option | Benefit | Main risk | Decision |
|---|---|---|---|
| Typed obligation/field contract | Makes stage/schema expectations explicit and structurally checkable | More tokens; small model may mislabel issues; schema drift if duplicated | Foundation; keep it compact |
| Fewer review calls | Lower latency/resource use | Removes opportunities to catch genuine scope/intent failures; leaves impossible feedback unresolved | Not a correctness fix; measure later |
| One bounded reviewer correction | Repairs malformed or structurally impossible feedback without changing a potentially valid candidate | Additional latency; same-model correlated errors; finite budget exhaustion | Add only for invalid contract responses |
| Another resident reviewer model | Potentially less correlated review | Violates one-heavy-model constraint if concurrent; serial switching costs; no evidence of improvement yet | Not required by minimal proposal |

## Concrete regressions and acceptance

Mocked transport contract tests should assert request payloads and call trajectories, not model quality:

- A delegated edit with omitted replacements is accepted and proceeds to source generation; complete source is deferred.
- A nonempty replacement correction under an empty-only active schema triggers one review correction, never an impossible planner retry.
- A corrected valid rejection for missing authorized file responsibility still repairs the planner candidate.
- Two invalid reviews stop without source generation, sandbox execution, stage publication or acceptance.
- An omitted required operation is a valid rejection even though its candidate pointer does not already exist.
- Unauthorized target/delete remains rejected; invalid reviewer output cannot bypass path/action preflight.
- A reference proposal that changes an explicitly requested interface remains subordinate to the original request.
- Cancellation and exhausted model-call/time budgets stop the correction; all calls remain serial under existing leases.
- Source generation and Docker execution remain fresh after plan acceptance; stale revisions block publication.

Use synthetic artifact variants and phrasing across single/multiple files, functions/classes and existing/new files. Do not encode fixture names, task keywords or expected live answers. Later run a separately versioned live comparison only after the frozen evaluation finishes, recording candidate/review/contract hashes and actual validation outcomes. Report failure/uncertainty honestly; structural contract compliance alone is not verified task completion.

## Scope and remaining uncertainty

This proposal addresses an observed planner/reviewer contract mismatch. It does not claim to improve weights, guarantee all tasks, fix the captured architecture strategy drift by itself, or prove that either rejected live operation candidate was valid. Additional telemetry should preserve privacy-bounded candidates and typed issues to distinguish omission from review error. No acceptance threshold should be loosened without separate evidence.
