# Pre-model environment admission correction

After external interruption, the Docker Linux engine was stopped. The harness had checked the pinned verification record but not live Docker readiness before starting each pair. This produced 31 zero-model-call sandbox-unavailable rows. They are not 31 model failures.

Original results.json is archived as results-before-environment-adjudication.json. Every affected pair has an explicit environment-adjudication.json binding the original row SHA-256, original FAIL status, corrected BLOCKED disposition and reason. On authorized environment rerun, row.environment-blocked.json preserves the original record. Both raw attempt directories remain intact. The 14 terminal validated pairs are not rerun.

Harness-only changes: perform the existing CodeSandbox._ready check before execution, stop an affected arm on environment blocks, require all runner pairs to have no unresolved environment blocks before the model phase, and distinguish a genuine cancellation from a model failure in a cancellation scenario. No task, fixture, prompt, tool schema, native kernel, model, budget, Docker policy or oracle changed.

Reruns are justified only for this diagnosed pre-model environment failure. Completed valid model failures are never rerun merely to raise PASS counts.
