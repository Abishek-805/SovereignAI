# Architecture verification audit

Read-only independent audit, 2026-10-02. Production, benchmark fixtures and harness remain unchanged during the live comparison. No candidate code, Docker or models were executed. Heldout fixtures were not inspected.

## Confirmed false positive

The hash-bound review in `benchmarks/smart-code-explanation-review.json`, A/main-094, is justified by the complete staged sources. `service.py` calls `solution.rotate` without importing or defining `solution`. A nonempty `values` payload reaches that unresolved reference; an empty payload bypasses it. `cli.py` implements its own `rotate` and `execute` and calls the local implementation, bypassing the requested service boundary.

The trusted test pass remains valid for its narrow assertions: core rotation, a callable service entry point, and no interactive input. It cannot establish a working service or delegation. Syntax compilation likewise cannot resolve names inside an unexecuted function. This is not evidence that another prompt or model reviewer would reliably catch the defect.

## Minimum generic improvement

Use the existing shared validation and failure-driven repair path; do not add another agent or task-specific branch. Changed-source checks should supplement supplied tests rather than be replaced by them. A pinned Python undefined-name analyzer inside the verified image can provide an actionable file/line diagnostic for this defect. Analyzer absence must be reported as unavailable validation, never silently accepted or installed on the host. Apply the same policy during generation and Accept to the same candidate bytes.

This addresses the unresolved name, but not delegation. Before generation, record acceptance obligations supported by the request: a working exported service, representative service invocation, CLI input/output contract, and required delegation. Trusted tests or independent review must support each obligation. Unsupported obligations stay unverified even when other tests pass. Avoid treating model-generated assertions or a model approval vote as authoritative.

Keep syntax/static/test/runtime/architecture evidence distinct. Feed concrete bounded diagnostics into the existing repair budget and repeated-error stop; preserve the original instruction, workspace scope, single-heavy lease and publication review. A stronger validation policy is a new experimental version: preserve the frozen results and do not describe evaluator improvements as baseline model gains.

The primary research and official analyzer references are collected in `docs/code-verification-research.md`. Static checking alone does not prove arbitrary task correctness.
