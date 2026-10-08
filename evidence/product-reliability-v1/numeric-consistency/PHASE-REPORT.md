# Product repair: numeric consistency in structured answers

Status: isolated candidate verified; not deployed.

## Observed facts

The select/comparison path accepted Python int/float cells but ignored equivalent numeric text. Numeric filters converted values with float() without excluding booleans or nonfinite numbers. These are deterministic computation inconsistencies, independent of model generation quality.

Before: 4 failed / 2 passed across six new deterministic cases. Numeric-string comparison failed, and Infinity, float infinity and boolean True were incorrectly counted as numeric measurements. Native numeric and mixed representation controls passed.

After: 6/6 passed against the isolated candidate. The 21 existing document-table and interaction checks also passed, with one existing Starlette deprecation warning. These suites overlap conceptually and are reported separately.

The candidate applies one finite-number interpretation to comparison fields, maxima, pass counts and numeric predicates. Source records remain unchanged. The request, schemas, renderer, expected outcomes and frozen model benchmark were not modified.

## Inference

This inconsistency can affect CSV and other string-valued structured sources. Fixing it improves a specific path from retrieved/parsed data to computed answers; it does not guarantee selection of the right table, interpretation of a request, or every generated conclusion.

## Evidence

- `registration.json`: pre-execution registration and original-source hashes.
- `before.txt`: original-source failures.
- `after.txt`: candidate results.
- `compatibility.txt`: existing comparison/table tests run against the candidate in a separate process.
- Candidate: `experiments/product_reliability_v1/candidate_tables.py`.
- New tests: `experiments/product_reliability_v1/test_numeric_consistency.py`.

## Remaining work

Apply the reviewed diff only when product repair deployment is authorized under the current experiment freeze, then run integration acceptance. No production or frozen benchmark result is replaced by this candidate. Other failures require independent reproductions; this is not a complete product repair.
