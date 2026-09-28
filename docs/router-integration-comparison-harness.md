# Router integration comparison

`benchmarks/routing-strategy-comparison.py` contains 31 representative cases: greetings, identity, general answers, grounded retrieval, reports, calculations, project inspection and edits, and vision. It compares always-text, legacy fixed mapping, and current candidate selection. Every arm retains the same production license, runtime, capability, modality, context and resource admission guards; fixed policies cannot bypass them or fall through to another candidate. The learned CPU classifier remains disabled in every arm because its independent safety and quality release gates failed. This is not evidence that enabled CPU routing improves performance.

Dry validation (no model, runtime or Docker calls):

```powershell
.app-venv\Scripts\python.exe benchmarks/routing-strategy-comparison.py --manifest-out benchmarks/router-integration-comparison-manifest.json
.app-venv\Scripts\python.exe -m pytest tests/test_routing_strategy_harness.py -q
```

Run actual comparisons only in an exclusive runtime window:

```powershell
.app-venv\Scripts\python.exe benchmarks/routing-strategy-comparison.py --execute --deadline 240
```

Execution is serial and rotates policy order. Every policy owns isolated project/document fixtures beneath a new `benchmarks/routing-strategy-artifacts/<run-id>` directory. The harness preserves fixture artifacts, exact binary asset hashes, source versions, citations, code checks, resource observations and routing traces. It never edits or removes existing user projects or documents. It uses the configured local registry and runtime; normal requests may switch the existing runtime between text and vision. Do not run alongside application generation, runtime profile changes, or another benchmark.

Timing covers direct Workbench workflows; fixture setup, API transport and separate validation are excluded. Partial runs are explicitly reported. Open answer meaning, report support and image correctness still require human review. No alternative eligible model has been independently run for the same capability, so oracle latency is unavailable. One pass does not establish tail latency, speedup, quality superiority or classifier promotion. A deadline requests cancellation and aborts the suite; it never advances while the timed-out request unwinds.
