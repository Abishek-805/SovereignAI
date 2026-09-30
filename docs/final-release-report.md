# Final engineering release assessment — 2026-09-30

**Engineering completion is not established.** CPU-first classifier promotion fails the frozen quality/coverage gates. Windows external-writer TOCTOU remains unresolved, configured model peak RAM/VRAM profiles are unmeasured, and the broad clean browser acceptance matrix is not verified. The final backend regression completed successfully; the corrected full routing comparison completed 93 workflow executions. Successful targeted tests and sandbox probes do not turn those missing gates into passes.

## Architecture and changes

The existing workbench, Knowledge ingestion, Agent, IDE and local llama.cpp runtime remain in place. The request-owned telemetry and model selector provide explicit candidate rejection reasons, compatibility/context checks and observed resource admission. Deterministic arithmetic executes locally. Structured table plans execute against complete records through validated application operations. The default registry holds the existing Qwen text and vision models; it has no measured alternative-model oracle.

Production CPU classification abstains and falls back to the bounded generative planner. This preserves the closed promotion gate but fails the requested CPU-first first-stage routing objective. The fixed legacy routing adapter remains used on identified paths; it must not be described as a fully consolidated selector-only implementation. Default resource admission is conditional where peak/context/KV requirements are unknown. Unknown telemetry remains null rather than fabricated.

Generated source and file organization stage outside canonical files, require verified Docker execution, and publish only through explicit Accept and revision rechecks. Publication now records flushed backups and journal state before canonical writes, commits before result metadata, and recovers interrupted transactions. Recovery preserves unexpected external changes; affected project mutation is blocked. Malformed/orphan recovery metadata quarantines only its workspace, preserving evidence and healthy-workspace availability. Undo uses the same durable transaction controller.

See [router architecture](router-architecture.md), [router evaluation](router-evaluation.md), [publication architecture](publication-architecture.md), [sandbox architecture](sandbox-architecture.md), [sandbox threat model](sandbox-threat-model.md), and [Knowledge architecture](knowledge-architecture.md). These documents distinguish implemented behavior from remaining gates.

## Evidence at this checkpoint

| Evidence | Observed result | Boundary |
|---|---|---|
| [Fresh classifier evaluation](../benchmarks/release-classifier.log) | Every candidate fails heldout accuracy and accepted coverage | Failed artifacts remain disabled; accepted predictions do not authorize mutation |
| Journal/publication tests | 37 passed; journal suite independently 24 passed; final journal suite 25 passed | Temporary fixtures, simulated process interruption and corruption; no forced power loss |
| [Final generated source live probe](../benchmarks/release-source-final.log) | Staged substantive HTML/CSS, Docker execution, canonical unchanged before Accept, publication, restart persistence and undo reported true | Exact temporary project case, not every language/request |
| [Live table case](../benchmarks/release-table-live.log) | Exact two-record result: 36.5 and 20, from 1,894 scanned rows | Generated prose failed verification; application returned verified record presentation rather than accepting fabricated 10 |
| [Report replay](../benchmarks/release-report-replay.log) | e24 succeeds in all three policy arms | One report case; not universal citation/semantic correctness |
| [Fresh Docker verifier](../benchmarks/release-docker-verification.log) | All 18 probes true after memory/no-swap correction | Tested runner/image/policy only; not container-escape certification |
| [Additional live isolation](../benchmarks/release-isolation-extra.log) | Cross-project input/output isolation, memory allocation denial, process creation denial and output fill denial true | Specific negative probes; output/PID test programs report denial through successful bounded test execution |
| Frontend verification reported by release runner | 720 unit tests pass; Svelte check reports zero errors/warnings; production build passes | Frontend unchanged since these checks; does not establish end-to-end browser acceptance |
| Targeted browser verification reported by release runner | Targeted workflow passed | Broad Chat/Knowledge/Agent/IDE matrix remains unverified |
| [Earlier backend regression](../benchmarks/release-regression.log) | 643 passed, seven skipped, one deprecation warning | Historical checkpoint preceding final availability fixes |
| [Final backend regression](../benchmarks/release-backend-final.log) | 648 passed, seven skipped, one Starlette deprecation warning in 143.70 seconds | Fresh complete backend run; skipped cases remain unverified |
| [Final live routing comparison](../benchmarks/release-routing-verified.log) | Current mapping 31/31; proposed 31/31; always-text 30/31 | Unsupported image correctly rejected by text-only baseline; one pass is not a speedup or semantic-quality oracle |

## Release gate matrix

Statuses are scoped to the stated evidence. `VERIFIED PASS` means the named behavior was observed in the bounded test; it is not a universal guarantee. `NOT VERIFIED` includes pending runs and missing required acceptance. No gate is waived merely because the environment is difficult.

| Area | Required gate(s) | Status | Evidence or remaining work |
|---|---|---|---|
| Router | Capability classifier evaluated; heldout evaluation; safety evaluation | VERIFIED PASS | Frozen v3 evaluation executed; evaluation itself completed |
| Router | CPU-first production classifier quality/promotion | VERIFIED FAIL | All four candidates miss heldout accuracy and coverage gates |
| Router | Evidence gate; Knowledge scope logic; tool routing | VERIFIED PASS | Fresh backend scope, planner, permission and tool contracts; broad interactive request matrix remains separate |
| Router | Table-query route | VERIFIED PASS | Live exact complete-record query with verified fallback presentation |
| Router | Model-centric registry; candidate filtering; model selection; runtime broker; telemetry | VERIFIED PASS | Fresh backend contract tests establish behavior; final live workflow comparison completed; legacy adapter remains live and optimization is not established |
| Router | Resource admission | NOT VERIFIED | Actual observations used, but configured peak RAM/VRAM/KV envelopes and quality profiles unknown |
| Router | Full supplied workflow comparison | VERIFIED PASS | 93 executions completed; observed workflow validity: 31/31 current and proposed, 30/31 text-only; no alternative-model oracle or broad semantic-quality proof |
| Router | Routing UI | NOT VERIFIED | Broad clean UI acceptance not established |
| Publication | No canonical mutation before Accept; Docker validation required; successful exact publication | VERIFIED PASS | Publication tests and live generated-source case |
| Publication | Docker unavailable blocks; validation failure blocks; cancellation blocks; revision conflict blocks | VERIFIED PASS | Fresh backend publication/workspace regression covers corresponding unchanged-canonical cases |
| Publication | Durable journal; process-crash recovery; recovery consistency; durable undo | VERIFIED PASS | Journal/publication tests, including interrupted publish, metadata reconstruction and retry |
| Publication | External-writer behavior tested/documented | VERIFIED PASS | Injected external edit preserved; project blocked; limitations documented |
| Publication | Full exclusion of uncooperative external filesystem races | VERIFIED FAIL | Repeated checks are not Windows handle-based CAS; parent swaps can race OS calls |
| Publication | Atomic simultaneous visibility across files; unconditional power-loss durability | NOT VERIFIED | Not supplied by this implementation; intermediate visibility and Windows directory-flush limitation documented |
| Publication | Corrupt/orphan metadata recovery availability | VERIFIED PASS | Eight committed/publishing damage scenarios quarantine only affected workspace |
| Sandbox | Live filesystem isolation; process isolation; network negative probe | VERIFIED PASS | Fresh 18-probe verifier, scoped to inspected isolation and denied connection |
| Sandbox | Privilege controls; resource enforcement; output bound | VERIFIED PASS | Verifier plus memory/PID/output denial probes; CPU bound inspected, not benchmarked exhaustively |
| Sandbox | Timeout; cancellation; cleanup; Docker socket absent | VERIFIED PASS | Fresh live verifier |
| Sandbox | Cross-project isolation; secret policy | VERIFIED PASS | Selected project isolation and dummy environment/known secret exclusion probes |
| Sandbox | Attestation freshness/source binding | VERIFIED PASS | Fresh verification produced matching version/fingerprint/image-bound attestation; reverify on source/policy changes |
| Knowledge | Structured query; exact aggregation/records; citation | VERIFIED PASS | Fresh document-table aggregate/citation tests and live exact record presentation; table selection semantic correctness is not universal |
| Knowledge | Preview; cancellation; concurrency | VERIFIED PASS | Fresh backend preview/import/cancellation/concurrency contracts; broad browser matrix remains separate |
| Knowledge | Agent-created document navigation | NOT VERIFIED | Required interactive correct-document acceptance not established |
| IDE | Code editing; staged AI edits; review; Accept; Discard; conflicts | VERIFIED PASS | Focused publication/code tests; successful staged generated-source live case |
| IDE | Docker validation | VERIFIED PASS | Live staged source validated and published |
| IDE | Terminal; Agent organization staging | VERIFIED PASS | Fresh backend terminal synchronization and staged organization tests; broad interactive workflows remain separate |
| Release | Backend regression | VERIFIED PASS | Final run: 648 passed, seven skipped, one deprecation warning |
| Release | Frontend regression; Svelte check; production build | VERIFIED PASS | Release runner reported 720 unit tests, zero check errors/warnings, successful build on unchanged frontend |
| Release | Clean browser acceptance | NOT VERIFIED | Targeted pass does not satisfy broad master matrix |
| Release | Docker live verification | VERIFIED PASS | Fresh verifier plus additional isolation/denial probes |
| Release | Router workflow benchmark | VERIFIED PASS | Full 93 executions completed on final production/harness source; text-only image unsupported |
| Release | Resource benchmark | NOT VERIFIED | Configured model peaks unmeasured |
| Release | Documentation; final repository audit | VERIFIED PASS | Final documentation reconciled; independent code review completed; remaining gates are listed explicitly |

## Performance, quality and remaining limitations

Classifier timings in the router evaluation are CPU prediction measurements, excluding model generation, retrieval, tools and application transport. Setup RSS deltas are not generator peak RAM or attributable VRAM. Routing comparison measurements must separate policy/workflow timing and state the exact completed cases. A repeated heldout replay is reproducibility evidence, not fresh independent ground truth. Vision interpretation and report semantic support still require human review where automated validity checks cannot establish meaning. Model self-confidence is not ground truth.

Sandbox negative probes establish the tested policy behavior. They do not prove immunity to Docker, Linux kernel or backend compromise, every covert network channel, or all credential filenames. Generated and third-party code remains untrusted. The trusted backend owns validation and publication; the container cannot directly publish canonical changes.

Journal recovery addresses process interruption but does not make multiple file replacements one atomic reader-visible operation. Windows file `fsync()` plus replacement does not establish unconditional directory-entry/device power-loss durability. Cooperating locks do not constrain VS Code or PowerShell; repeated checks retain a TOCTOU interval. Recovery-required workspaces need user comparison/intervention; no force-overwrite recovery wizard is implemented.

New models, a coding specialist, arbitrary learned selector weights, additional UI redesign, container/kernel vulnerability certification, and deployment/publishing are **OUT OF SCOPE** for this cycle. These exclusions do not waive CPU-first routing, required acceptance, resource measurements or external-writer release blockers.

## Completion decision and reproduction

Remain in engineering/verification mode. The project cannot be declared complete while the classifier promotion gate fails and required browser/resource/race evidence is absent. Retain the completed comparison evidence and remaining failed/unverified gates. Successful build, model output or Docker execution alone does not meet the master release criteria.

```powershell
.app-venv\Scripts\python.exe -m pytest tests/test_publication_journal.py tests/test_publication_boundary.py -q
.app-venv\Scripts\python.exe benchmarks/evaluate-capability-classifiers.py --version v3
.app-venv\Scripts\python.exe benchmarks/routing-strategy-comparison.py --execute --deadline 240
.app-venv\Scripts\python.exe scripts/verify_docker_sandbox.py <existing-pinned-image-id>
```

Run live model comparison only in an exclusive runtime window. These reproduction commands do not waive unverified gates. The master demo cases are covered only where corresponding exact evidence above exists; document navigation, broad browser workflows, representative resource profiles and stronger host-race guarantees remain outstanding.
