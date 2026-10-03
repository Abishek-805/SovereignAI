# Prototype recovery — 3 October 2026

The latest user request authorizes concrete prototype fixes. No models, supervisors, agents, router architecture, or review loops were added. Model weights are unchanged. No heldout cases were read or tuned against.

## Fixes

- Removed a synthetic receipt-parsing example from the semantic reviewer. The screenshot's unrelated rejection repeated that example instead of evaluating the current AI/ML/DL request. Review now receives the current stage contract, evidence, and candidate only.
- Source generation returns an unverified candidate directly. Redundant interpretation and same-model source vetoes no longer precede execution. Structured output, output/context budgets, bounded repair, Docker isolation, revision checks, and explicit acceptance remain. Passing a syntax check does not establish functional correctness.
- Connected document chips start collapsed behind a caret in both Chat and Agent. Expand to open or disconnect documents.
- HTML previews wait for bundled project assets rather than briefly rendering raw HTML with blocked relative CSS. Loading and bundling errors are visible. The opaque iframe and restrictive CSP remain.

## Verification

- Backend: 1,146 passed, seven skipped. Frontend unit: 728 passed across 61 files. Svelte check: zero errors/warnings. Production build passed.
- Real Chromium: document collapse/expand/disconnect passed; three HTML bundling and opaque-sandbox CSS/JavaScript checks passed. The initial caret test used bounding rectangles, which do not establish visibility inside closed native details; it was corrected to test actual browser visibility.
- Isolated live Knowledge creation completed despite receipt-parsing history. The requested TXT was actually stored and indexed. Final run: five model calls, zero switches, 144.91 seconds. Earlier diagnostic run: seven calls, 157.81 seconds. These are individual observations, not a controlled latency comparison.
- Independent reading of the stored document confirms the requested AI/ML/DL hierarchy and examples. Semantic quality is partial: its statements about human-like thinking, brain simulation, and uniformly high data requirements overgeneralize. Successful creation does not mean factual perfection.

## Evidence limits

The historical six-arm comparison stopped at 163 executions (F=100, E=63); its raw snapshot is preserved separately. It is incomplete. The new behavior must not be mixed into or resumed as that frozen comparison. No overall architecture-superiority claim is justified. Historical automatic repair had zero independently verified recoveries; a first-candidate success is not a repair recovery.

Raw recovery evidence: `benchmarks/prototype-document-live-20261003.json`, `benchmarks/prototype-document-live-final-20261003.json`, `benchmarks/prototype-code-live-20261003.json`, and `benchmarks/prototype-code-live-review-20261003.json`.

The eight-case code run completed. Independent answer-bound review resolves the explanation as PASS; rename, batching fix, warm Coder, follow-up scope, cancellation, and stale revision passed. Explicit acceptance separately returned 200 and saved exact candidate bytes. Batching took 10.01 seconds and warm Coder 12.66 seconds, each one model call and zero switches. Sampled model-server count never exceeded one; this is not proof about every instant.

The architecture case is FAIL despite the transport harness marking it UNKNOWN. First candidate returned a KeyError object rather than raising it; a later repair removed the requested invoice function. All three independent Docker checks failed. The original goal and candidate feedback are present in repair context: missing context is not established. Failure implicates model implementation and repair handoff fidelity. It took 76.68 seconds, ten model calls, two switches; originals were preserved. Removing source vetoes enabled actual candidates and validation, but did not solve this task. No architecture change or task-specific patch was made to disguise the failure.

This is a tested recovery patch, not a claim that the entire prototype now handles every task correctly. Complex coding fidelity, document factual precision, and long-form document latency remain unresolved. Further architecture decisions require the incomplete comparison to be reviewed or a separately labeled evaluation of the changed variant.
