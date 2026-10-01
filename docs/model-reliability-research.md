# Local model reliability: research and evaluation

Research reviewed on 2026-10-01. This document distinguishes research findings, application observations, and proposed evaluation. Prompting, context management, verification, and routing changes improve the inference workflow; they do **not** train or improve the installed model weights. No small model can be promised perfect performance on arbitrary tasks.

## Evidence and practical implications

| Primary source | Finding | Application implication and limit |
| --- | --- | --- |
| [ReAct, ICLR 2023](https://arxiv.org/abs/2210.03629) | Interleaving planning with actions and observations supports task execution and recovery. | Feed actual tool results back into a bounded repair step. This is not evidence that longer free-form reasoning guarantees correctness on these installed checkpoints. |
| [Reflexion](https://arxiv.org/abs/2303.11366) | Agents can use feedback and episodic text memory to improve later attempts without changing weights. | Preserve relevant accepted task state and execution feedback. Keep untrusted source text separate from user instructions; do not retain erroneous conclusions as facts. |
| [Self-Refine](https://arxiv.org/abs/2303.17651) | Iterative feedback and refinement improved several evaluated tasks. | A separate review can help, but published gains on larger models cannot be assumed for local 2B/3B models. Measure each checkpoint. |
| [Large Language Models Cannot Self-Correct Reasoning Yet, ICLR 2024](https://arxiv.org/abs/2310.01798) | Intrinsic correction without external feedback can fail or degrade answers. | Do not repeatedly ask a model to "think again" and call the result verified. Ground repair in source records, schema violations, compiler/runtime diagnostics, or explicit user constraints. |
| [Lost in the Middle](https://arxiv.org/abs/2307.03172) | Relevant information placement affects performance in long contexts. | Supply compact relevant task state near the current request, rather than indiscriminately appending all history and documents. Applicability to a specific checkpoint still requires measurement. |
| [JSONSchemaBench](https://arxiv.org/abs/2501.10868) | Structured decoding must be evaluated for efficiency, constraint coverage, and output quality. | Valid JSON is a format guarantee, not a semantic correctness guarantee. Check plan meaning and executed results separately. |
| [Least-to-Most Prompting, ICLR 2023](https://arxiv.org/abs/2205.10625) | Decomposing a complex problem into simpler sequential subproblems improved the evaluated reasoning tasks. | Separate natural-language task interpretation from constrained contract generation. This application adaptation is not identical to the paper's protocol, and its results do not establish gains for Gemma, Qwen Coder, or Qwen Vision. |
| [Berkeley Function Calling Leaderboard: multi-turn evaluation](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html) | Multi-turn and multi-step tool use require distinct evaluation cases. | Test corrections, changed requirements, missing information, and tool observations; single-turn success does not establish context continuity. |

## Application observations

At the start of this audit, `backend/model.py` reconstructed `active_measure` by planning only the immediately preceding user request with empty history. A threshold-only correction could therefore lose an earlier operation or requested outcome. The planner also combined interpretation, source selection, outcome polarity, and execution instructions in dense prompts. These are code observations, not benchmark claims about model weights.

The reported screenshot counts numeric scores below 25 while labeling the column "Passed". Correct arithmetic alone cannot validate a report when the requested outcome and applied predicate disagree. Verification must cover both the mathematical rule and the meaning of the heading.

An independent audit of the proposed inference wrapper identified important checks before release: retain the natural interpretation during repair rather than dropping it; preserve original instructions as authoritative; expose a clean current request to interpretation rather than only serialized task payloads; test whether a constrained reviewer can detect the same semantic mistakes as the original constrained planner; and measure truncation and latency when interpretation enables a thinking prelude. A second call to the same model is a separate prompt, not an independent correctness oracle.

## Recommended inference workflow

1. Resolve the current request against compact conversation state: task, requested output, entities, scope, user-supplied rules, and actual prior results. Keep the requested outcome separate from the outcome described by a rule.
2. Produce a bounded structured plan using actual available tools, source fields, and workspace ownership.
3. Review the plan independently for contradictions, missing requirements, unsupported assumptions, and unwanted side effects. A reviewer must be allowed to accept the original plan or request clarification; it must not be prompted to invent a defect.
4. Execute through tools. Numerical aggregation uses full matching records; generated code is checked with available execution or static diagnostics; image extraction retains source provenance and uncertainty.
5. Repair using concrete feedback with a fixed attempt budget. If evidence remains missing or interpretation unresolved, ask a focused clarification instead of publishing an unsupported answer.
6. Render verified results with headings that accurately describe the applied rule, denominator, and absence policy. Distinguish an inspected source result from an independently validated result.

All model calls must remain sequential under the existing single-resident-model lifecycle. A reviewer using the same checkpoint consumes additional inference time but does not require a second resident model. Specialist switching must unload the prior heavy model before loading the next one.

## Applicability to installed model roles

| Installed role | Primary documentation | Recommended checks | Limits |
| --- | --- | --- | --- |
| Qwen3.5 4B, preferred general text/calculation when installed | [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-4B) | Multi-turn task contracts, source-bound plans, corrections and changed outcomes. | The limited local tests below support this choice for the reported workflow, not a universal model ranking. |
| Gemma 4 E2B, alternative general text and task interpretation | [Google model card](https://huggingface.co/google/gemma-4-E2B-it) | Multi-turn semantic interpretation, requested output versus supplied rules, source selection, ambiguity handling. | A small local quantized deployment may differ from upstream evaluations. General instruction capability does not establish reliable tool planning or arithmetic. |
| Qwen2.5-Coder 3B, code generation | [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct), [technical report](https://arxiv.org/abs/2409.12186) | Complete requested files, correct existing-workspace targets, dependency declarations, compiler/runtime diagnostics, preserved unrelated code. | Code specialization does not guarantee working integrations, available hardware access, or installed dependencies. Test the deployed quantization and runtime. |
| Qwen3.5 2B, vision tasks | [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-2B) | Image-to-field fidelity, ambiguous text, chart/table coordinates, grounding in the supplied image. | Small text and visual ambiguities can remain unresolved. Vision output should not replace direct spreadsheet parsing when original structured data is available. |

Upstream capability descriptions inform role choice; no upstream score is reported here as a measurement of this laptop. Routing should be evaluated using the actual complete workflow, including specialist transitions and unavailable-capability behavior.

## Evaluation methodology

Use a held-out suite spanning chat, retrieval, tables, code, vision, and routing. Include paraphrases and spelling errors, explicit and implicit follow-ups, opposite outcomes, inclusive/exclusive threshold boundaries, new-task topic changes, workspace selection, unavailable dependencies, and conflicting or missing source evidence. Avoid evaluating only the wording used to design prompts.

Compare the prior workflow and revised workflow on identical fixtures and model/runtime configurations. Record checkpoint identity, quantization, context budget, decoding settings, model role, tool plan, repair count, actual source/tool result, final answer, latency, and peak memory where available. Run models sequentially. Distinguish mocked regression tests from real-model evaluations.

Report semantic task success, source correctness, calculation correctness, valid structured output, unauthorized/unrequested actions, clarification appropriateness, and latency separately. For numerical tasks, use an independent reference calculation and exact boundary fixtures. For code, evaluate behavior rather than merely successful file creation. For vision, compare against known image annotations. For routing, inspect both selected capability and downstream success.

## Implementation and local evidence (2026-10-01)

Application inference now performs task interpretation, a proposal, semantic review and at most one repair using the same resident model. Source-validation errors can trigger one table-plan repair. Literal rules and requested outcomes are separate fields: execution complements a failure rule only when passes are requested. This is a general task contract, not a branch matching the reported sentence. No weights were trained or changed. The raw compatibility streaming API remains a passthrough; application chat, agent, coding and vision service calls use reviewed inference.

Independent calculation from the supplied 64 records gives pass counts at scores >=25 of **23, 1, 1, 6, 34, 28, 31** for WAT 1–6 and CAT 1, and percentages **35.94, 1.56, 1.56, 9.38, 53.12, 43.75, 48.44**. Numeric failure counts below 25 are **41, 56, 60, 46, 20, 23, 32**; absences/non-numeric values are **0, 7, 3, 12, 10, 13, 1**. The screenshot used failure counts under a pass heading. All cohort records remain in the denominator; non-numeric values do not satisfy a numeric predicate.

Gemma and the coder failed some context-change trials despite extra review and thinking. Already-installed Qwen3.5 4B correctly interpreted three small context-delta trials: add a failure rule while retaining requested passes; explicitly switch to failures; repeat the previous report. This narrow comparison is not a general quality benchmark. The registry now prefers Qwen3.5 4B for general text/calculation, retaining Gemma as an available alternative. Specialist code and vision routes remain separate. Comparable measured routing quality precedes latency; missing measurements are not fabricated. Resource admission and unload-before-load still apply.

The regression suite passed **694 tests**, with **7 skipped** and one existing Starlette deprecation warning. Mocked test success does not establish model accuracy; end-to-end model results, including failures, must be recorded separately. More computation is an accuracy budget to test, not proof of perfect performance on arbitrary tasks.

The literal-rule resolver is decomposed further: requested outcome and the threshold definition are decoded separately from source selection, using contrasting generic examples. Only user requests establish those facts; erroneous assistant reports do not redefine them. The same-model review remains fallible. Non-thinking interpretation and a bounded five-minute local call timeout are used after a long thinking prelude timed out without resolving the semantic error.

End-to-end Qwen3.5 4B follow-up tests against the actual workbook passed: repeating the requested passing report returned all seven independently computed pass counts; explicitly switching to failures returned the seven numeric failure counts with a Failed heading. Earlier attempts failed (wrong polarity, timeout, and truncated review); they were not accepted as success. The passing result followed task decomposition, contrasting generic examples, independent literal-rule extraction and source-bound calculation. It does not establish that either checkpoint alone always understands arbitrary tasks.

The final shared review path also passed a coding smoke test: generated median code matched Python statistics.median for 100 deterministic unsorted inputs, preserved inputs, and rejected an empty list. Qwen3.5 2B vision correctly read Apples=12 and Pears=7 from a synthetic image through the application endpoint. Exactly one llama-server process was observed after code, vision and restored text loads. These are narrow smoke tests, not broad coding/vision benchmarks.

Important remaining limitation: direct tests of rule-only follow-up wording still sometimes interpreted a definition of failure as a request for failure statistics. Shorter schemas, incremental state decoding and extra thinking were not consistently successful; those experimental variants were not shipped. The final path rejects disagreements between the full task plan and the focused outcome interpretation with a clarification request. Agreement between prompts is still not proof of correctness. A missing threshold was also guessed during an initial request but blocked by source validation. Broad accuracy across arbitrary tasks remains unestablished.

Final ambiguity test: the original rule-only follow-up returned needs_input asking whether the report should count passes or failures, because independent interpretations disagreed. An explicit clarification retaining passing percentages then returned all seven correct pass counts. The application therefore avoids that previously observed wrong report, at the cost of a clarification; automatic understanding of every paraphrase remains unresolved. Report headings now say Calculated results rather than implying that computation certifies prompt interpretation.

The official coder model card lists qwen-research, not Apache-2.0; registry metadata and inventory were corrected to match the upstream card. This records provenance, not a new licensing opinion or distribution approval.
