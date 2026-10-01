# Frozen Universal Task Agent comparison

The 128 engineer-authored tasks cover 16 categories with eight distinct requests
each. They are realistic fixtures, not independent held-out user measurements.
The fixture source documents and coding projects are synthetic and isolated.

Strategies use the same existing Workbench flows and runtime settings:

- A: `fixed` routing, reasoning text worker and coding specialist.
- B: `always_reasoning`, reasoning worker for nonvisual model work.
- C: `universal`, software task agent and role broker.

The strategy affects worker selection; no second model is preloaded. Tool-only
calculations remain tool-only. All three use the same supervisor, completion gate,
tools, and Workbench orchestration. This primarily compares worker policies, not
an unsupervised architecture against a supervised architecture.

`worker_correct` means configured strategy worker adherence, not a common oracle
of task suitability. B changes every nonvision/non-tool-only worker expectation
to reasoning; A changes nonvision/noncode/non-tool-only expectations to reasoning;
C retains the fixture expectation. Thus B using its reasoning worker for coding
can pass this metric while the fixture's original expectation is a code specialist.
Task intent and mathematical expectations remain common. Inspect selected model
identities and independent output checks before interpreting adherence as quality.

```powershell
# Run only when the application's inference runtime is idle/stopped and the
# coordinating parent has authorized the model lifecycle.
.app-venv/Scripts/python.exe benchmarks/evaluate-universal-agent.py --mode live --allow-model-lifecycle --sample-resources --strategies A B C --timeout 300 --output benchmarks/universal-live-comparison.json

# Quick actual arithmetic acceptance; incomplete-suite coverage is explicit.
.app-venv/Scripts/python.exe benchmarks/evaluate-universal-agent.py --mode live --allow-model-lifecycle --strategies C --categories calculator --timeout 120 --output benchmarks/universal-live-calculator.json

# Replay existing capture lists; replay does not execute models or tools.
.app-venv/Scripts/python.exe benchmarks/evaluate-universal-agent.py --mode replay --captures A=path/to/A-captures.json --captures B=path/to/B-captures.json --captures C=path/to/C-captures.json --output benchmarks/universal-replay.json
```

Unset `SOVEREIGN_KNOWLEDGE_DIR` before live runs. An environment override that could
write to user Knowledge is rejected. Each strategy uses a temporary data/project
root; each coding case gets a fresh workspace. Sources are imported from the
fixture. The runner never Accepts or publishes generated changes. The existing
broker may load/switch installed models only with the explicit CLI opt-in.

The timer sets the real cancellation event at the deadline; interruption depends
on existing cooperative model/tool checkpoints. Environment errors, cancellation
and execution errors are reported separately. Partial reports are saved after
every case, retaining failures rather than retrying the entire benchmark blindly.

Reports flush and fsync a temporary file before atomic replacement. Transient
Windows `PermissionError` during replacement gets up to six attempts with bounded
backoff; only the file commit is retried, never task execution. Exhausted retries
raise while preserving the old report and fsynced temporary result.

Run provenance records UTC start, Git HEAD, production Python hashes, model
profiles and launch arguments, generation/settings budgets, timeout, and scope.
Ordinary `--resume FILE` requires strict matching provenance. An explicit
`--resume-harness-repair` permits only changes to the evaluator hash and Git HEAD:
all production module hashes, dataset, model profiles/context/KV, settings, and
strategies/category/ID/limit/resource scope must remain identical. Every saved
fixture hash is also validated. Prior provenance and the reason `harness-only
repair` are preserved. Resumption creates new isolated data/workspace roots and
does not establish uninterrupted warm-runtime continuity.

Success is checked only where a narrow independent fixture oracle exists:
arithmetic values, source-backed facts, structured table results, cancellation,
and unchanged fixture-owned unit tests. Generated model assertions cannot certify
success. Validated staged code is recorded as an artifact check and does not count
as published task completion. General and visual semantic judgments remain unknown
until independently reviewed. Missing security/proposal telemetry also remains
unknown; zero observed unsafe proposals is never inferred from absent data.

The full fixture set has 82 cases without a task-success oracle and 46 with one:
eight source-fact, six table-value, eight calculation, sixteen fixture-test, and
eight cancellation cases. A task-success percentage uses only observed oracle
outcomes; display its numerator, measured denominator, and unknown count. It is
not a correctness rate for all 128 tasks. The eight cancellation requests have
their cancellation event set before execution: success establishes correct stop
handling at entry/checkpoints, not completion of the original work, interruption
mid-generation, or rollback. Excluding cancellation leaves at most 38 measurable
work-result cases. Unsupported or missing capture evidence can reduce actual
measured coverage further.

The source-fact oracle checks required case-insensitive literal terms in both the
top-level answer and actual returned source text. It does not establish term
relationships, negation, units, complete semantics, or correct citation-to-claim
attribution. Table and calculation checks likewise establish their specified
structured/value contract rather than every interpretation of the request.

Follow-up fixtures supply user-history strings but do not execute prior turns or
restore prior operational state. Every case requiring a workspace gets a fresh
one populated only by its explicit `initial_files`. For example, `followups-05`
mentions a previous `main.py` SyntaxError but has no file or prior test result;
`typo_noisy-07` requests a syntax fix in an empty workspace. Clarification can be
appropriate even though the fixture expects code intent. `task_changes-06` asks
for `main.py` without specifying its behavior. `task_changes-07` lists files, for
which an application-management route is plausible but excluded by its expected
code intent.

Docker fixtures seed a syntax-invalid function and an unconditional failing test,
but several requests name a different error: missing import/package or an
assertion in `main.py`. They do not supply an actual preceding Docker failure.
`repair_tasks-02` asks to repair syntax although its seeded `value()` function is
syntactically valid and returns 6 instead of the test's required 7. These fixture
mismatches limit interpretation of wrong-intent and repair outcomes. Preserve the
frozen observations and disclose such limitations instead of changing fixtures
after seeing results. A natural clarification returned as general answer can also
miss the adapter's clarification classification; `clarification_correct` is not
an independent judgment of clarification text.

Optional resources are sampled approximately once per second. RAM is the sum of
benchmark Python and all llama-server resident-set sizes, not exclusive private
allocation. VRAM is total device memory reported by `nvidia-smi`, not exclusive
model attribution. Process counts are conservative observations of all llama
servers. Very short tasks may be missed between samples. Unavailable observations
stay null. Counters preserve the existing supervisor's definitions.

Resource aggregate values are medians of per-case peaks with p95, not whole-run
maxima. Use the maximum actual recorded process count when describing residency
observations. Execution order is sequential A, then B, then C in fixture order,
without randomization or repeated trials. Warm starts, prior worker residency,
thermal conditions, OS/background load, and time can therefore confound latency
and resource comparisons. Resume sessions add another runtime discontinuity.

This harness reports separate metrics and coverage. It does not manufacture a
single quality score, claim C is superior, certify a release, or replace live
publication/browser/resource-pressure acceptance tests.
