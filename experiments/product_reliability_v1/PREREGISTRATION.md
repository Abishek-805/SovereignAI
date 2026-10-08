# Structured answer numeric consistency repair

Registered 2026-10-07 before running the new cases. This is a product regression experiment, not a model benchmark or a T10 intervention.

Hypothesis: select-comparison ignores finite numeric strings although aggregate operations accept them; numeric filters admit nonfinite input. A shared finite-number interpretation will preserve computed numeric semantics across imported representations.

Independent variable: isolated candidate implementation of numeric comparison/filter handling in rag/tables.py. Production remains unchanged while the frozen worker comparison runs.

Frozen variables: table records, source strings, selected columns, identities, request, existing schemas, renderer, original production module, expected independently calculated results.

Controls: native numeric values; numeric strings with whitespace and decimals; booleans; nonnumeric values; NaN and infinity; mixed representation; source preservation. No model generation or generated-code execution.

Success: equal numeric values produce equal maxima and threshold counts regardless of numeric/string storage; nonfinite/boolean input is excluded from numeric predicates/comparisons; original source records remain unchanged; existing interaction comparison cases retain their outcomes.

Disproof: incorrect extrema/counts, changed source records, or regression in existing comparison cases.

Sample size: six deterministic new cases, plus the existing interaction repair tests. One before/after execution per implementation, except harness errors must be disclosed. No selected retries.

Temperature/seeds: not applicable; no LLM inference.

Stopping rule: stop this repair after tests pass or if it requires changing frozen benchmark/production inputs. Do not deploy automatically. Other product defects require separately recorded reproductions.

Evidence: evidence/product-reliability-v1/numeric-consistency/. Candidate: experiments/product_reliability_v1/candidate_tables.py. Existing source SHA and registration SHA recorded before execution. No prior benchmark outcome is replaced.
