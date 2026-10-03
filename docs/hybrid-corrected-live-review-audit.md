# Corrected live review audit

Read-only audit of `benchmarks/hybrid-live-acceptance-corrected-20261003.json`, rename and architecture rows, 2026-10-03. No model calls, Docker runs, held-out reads or production changes.

## What improved

Rename records status `PASS`, an accepted workspace plan, generated source renaming both assignment and return to `subtotal`, and independent trusted tests with `artifact_verified: true`, `container_executed: true`, exit code zero. Its plan has empty replacements, correctly delegating implementation. The workspace candidate SHA is `50828a6b9cb7b428cbee4c5b39934b03460b716de64a27acce04f6f638b7733d`; bounded operation fields retain the intended rename. This case no longer stops on the earlier impossible nonempty-replacement demand.

Architecture also passes the **workspace-operation-plan review**: its candidate SHA is `a118b3bbc009d5ea3a70099bfefad1d45f2bda052a1b8b12cf88c0444183b038`, scope `existing_files`, and two edits: `catalog.py` (“Define Catalog class with get_price method”) and `billing.py` (“Refactor to use Catalog class”), both with zero replacements. The next semantic-review event is no longer evaluating this plan. The trace has no `review_contract_correction` event for either case, so this run supports correct normal-path plan acceptance; it does not live-exercise the new bounded correction branch.

## Architecture's remaining failure

After accepting the workspace plan, four source-generation reviews return `revise`. Attempts 1, 2 and 4 say `Catalog.__init__` fails to initialize `prices` with the provided mapping. Attempt 3 says `get_price` does not preserve missing-name `KeyError`. It terminates with `semantic_uncertainty`; independent validation trajectory is empty, code-task current candidate is null, status is `FAIL`, failure layer `MODEL_FAILURE`, and handoff success is `NOT_VERIFIED`.

The source-stage contract in `backend/model.py:818-820` correctly requires complete generated source and checks requested behavior while leaving execution to the sandbox. Constructor initialization and missing-name behavior belong to this stage, unlike the previous demand for implementation inside an operation plan. Thus these reviews are **not evidence of the same plan-stage/schema mismatch**.

The generated source candidates rejected by these reviews are not retained. Their claimed constructor/lookup defects cannot be independently confirmed; this could be actual source-generation failure, erroneous source review, or both. No trusted tests ran, so it is not a verified runtime defect or verified correct implementation rejected by the reviewer. Do not claim the model simply needs more retries, or loosen acceptance based on this incomplete evidence.

The recorded upstream reasoning strategy still proposes an `Invoice` class with `total()` instead of the explicitly requested `invoice(names, catalog)` function. This is an observed intent error in the strategic proposal. The operation-plan reasons do not resolve whether later generation corrected that interface. It remains a separate concern from review-stage adherence.

## Decision

The general workspace-plan contract is functioning on the normal path in these two cases, and rename has real independent success evidence. Architecture progressed beyond the previous plan-review blocker but is still unverified and failed. This trace does not justify another production patch to plan review or an endless repair loop. Preserve the failure. A future narrowly scoped investigation would need privacy-controlled source-candidate evidence and an independent check to distinguish actual implementation defects from reviewer false positives, while keeping scope, one-heavy-model admission, Docker validation and reviewed publication gates intact.

Resource telemetry sampled at most one llama-server process in both cases (rename 6 model calls/1 switch; architecture 13 calls/2 switches). This is sampled concurrency evidence, not continuous proof between samples or proof that the architecture task succeeded.
