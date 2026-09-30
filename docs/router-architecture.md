# Router architecture and current release boundary

The application uses structured model planning and model admission/selection. The evaluated CPU classifier is **not promoted**: `Workbench` constructs `ConservativeCapabilityClassifier`, which defers nonempty requests to the planner. This is an implemented fallback architecture, not a completed CPU-first release.

## Request flow

1. Request-owned telemetry records classifier output and routing stages. Empty classifier input requests clarification; ordinary nonempty input defers without loading an embedding runtime or reading user files.
2. Deterministic arithmetic has a dedicated path that can avoid a generative model. Other general tasks acquire an admitted text runtime and use `LocalModel.plan_task` when `_cpu_readonly_plan` has no released decision.
3. The bounded planner chooses an action from a schema: answer, search documents, create report, inspect/edit code, calculate, analyze image, or application tools. Connected document names and project filenames are routing metadata; their availability alone does not authorize retrieval, execution, or mutation.
4. The selected workflow resolves the required evidence or project context and performs its own validation. Source generation is checked for substantive language content as well as Docker validation. Generated project changes remain staged until accepted; routing is not publication authority.
5. `_lease` selects a compatible model before acquiring its runtime lease. Workflow calls can select again for a different modality or larger required context.

The planner has a finite action vocabulary, bounded output and structured validation. Invalid plans raise a generation-format error. Calling it a fallback does not imply that a failed CPU label is accepted, or that a model-generated plan is sufficient permission to execute arbitrary actions. Application tool contracts and explicit-operation checks remain separate.

Source: [service](../backend/service.py), [planner](../backend/model.py), [classifier](../router/capability_classifier.py), [tool contracts](../router/tool_registry.py), [coding workspace](../workflows/coding_workspace.py).

## Model selector versus legacy adapter

`CapabilityRouter.select_model` delegates to `ModelSelector`. It checks enabled state, reviewed license metadata, installed assets, runtime availability, supported capability, modality, context limit, and resource admission. An explicitly configured quality floor rejects missing or insufficient quality measurements. No admissible model yields a visible candidate/resource failure, with no implicit fallback.

If every admissible candidate has comparable measured quality, latency and switching cost, the selector minimizes measured latency plus the required switch cost, in seconds. If comparable measurements are incomplete, it retains an admissible resident model or uses stable registry priority. That branch explicitly reports incomplete evidence. The default policy has no configured quality floor, and default specs do not populate comparable benchmark metrics. Current source therefore does not establish an optimized quality/latency tradeoff.

`route_request` is a separate legacy adapter mapping text to text, vision to vision, and code/calculation to text. `Workbench._lease` uses the selector when the registry exposes the required interface; its compatibility fallback calls the adapter. Legacy agent entry points also contain direct `route_request` calls. Those calls must not be presented as evidence that candidate ranking ran. A request trace's `model_selection` stage is the evidence of selector execution.

Default registered generators are Qwen3 4B text (also declaring code/calculation support) and Qwen3.5 2B vision. A registry key is a runtime handle; model identity, supported capabilities, and runtime alias are separate fields. No independently measured competing generator for the same capability is implied by this registry.

Source: [router](../router/router.py), [selector](../router/model_selection.py), [registry](../router/model_registry.py), [service](../backend/service.py).

## Resources, lifecycle and telemetry

Resource observations use available system RAM and, when available, GPU-zero free/total memory. Admission rejects observed reserve or measured requirement failures. Missing model peaks, context/KV profiles, or incremental resident allocation yield **conditional** admission, not a proven capacity fit. Resident low GPU headroom has an explicit conditional exception because resident weights already occupy memory; it does not guarantee further allocation or loading headroom.

Selection is separate from runtime acquisition. The registry serializes its lease transitions and records readiness, loading and switching outcomes. Source lifecycle guards do not prove a measured peak RAM/VRAM envelope. Those peaks remain unverified unless a matching context and KV profile has independent measurements.

Telemetry stores candidate rejections, admission, selected identity, residency, fallback, evidence requirements, validation and timing facts. Runtime prompt/generation timings are recorded when supplied; absent measurements remain null. Request wall time, lease/load time, classifier time and runtime inference time are different quantities. The normalized switch timing is currently null; a switch-required boolean alone is not a switch-duration measurement.

Source: [resource admission](../router/resource_admission.py), [runtime registry](../router/model_registry.py), [telemetry](../router/telemetry.py).

See [router evaluation](router-evaluation.md) for the failed CPU promotion gate and the limits of the available performance evidence.
