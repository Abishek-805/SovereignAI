# Upfront strategy failure diagnostic

Read-only inspection on 2026-10-02 while the main comparison is frozen. No production, fixtures, evaluator or runtime changes; no model or Docker calls; heldout untouched.

## Observations and uncertainty

All five B and all five C architecture tasks fail before a candidate is produced, after one inference, with `generation_format: The implementation strategy was incomplete`. `backend/model.py` `plan_code_strategy` requests an unconstrained prose plan with `max_tokens=512`, temperature zero and `enable_thinking=False`. It requires `finish_reason == stop` and nonempty string `message.content`. Any length stop, different finish reason, malformed response or empty content becomes the same error.

The saved errors do not distinguish these causes. `observe_completion` retains token counts when available but does not retain finish reason or public-content length. Therefore token truncation is plausible, not established. Do not retrospectively label these failures as truncation. There is no direct unit coverage of `plan_code_strategy`; service tests replace it with a completed fixed string.

The streaming adapter accumulates only `delta.content` and preserves the final finish reason; a missing final finish is already rejected. It does not promote `reasoning_content` to the actionable plan. That separation should remain: private reasoning is not a complete implementation proposal. The streaming path is selected under cancellation context; otherwise the same endpoint is called synchronously. A cause-specific test must cover both.

The [official llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) distinguishes response reasoning fields and reasoning-format controls, and documents template variables such as enabling thinking. Current upstream documentation is not proof of the behavior of installed build b11132. A finish-reason spelling mismatch or ineffective template option must be verified against an actual response before changing the parser.

## Minimal testable correction after the frozen run

1. Add safe failure diagnostics first: final finish reason, requested token cap, completion-token count and nonempty-public-content flag/length. Retain no raw private reasoning. Preserve incomplete-output rejection and original task failure. This makes the next disposable live probe discriminate truncation, empty public output and unsupported response shape.
2. Use the existing actual-context accounting for the strategy call and a bounded proposal format: a small number of concise steps covering interfaces, exact scope and executable checks. Reserve a larger but finite output budget only when context allows it; for example a configured ceiling of 1024 instead of an unconditional 512. This is a hypothesis to measure, not an assurance that more tokens improve correctness. Do not claim a `length` result is complete or silently skip the requested upfront strategy.
3. If a live probe establishes length exhaustion, either tighten the bounded format or allow at most one explicit strategy regeneration using concrete failure metadata and remaining supervisor budget. Do not introduce unbounded continuations or switch to another worker merely because a response is incomplete. Any extra inference must be counted. A one-call policy with an adequate measured budget is preferable when it works.
4. Add transport-level tests: completed nonempty plan accepted; nonempty `length` rejected; empty `stop` rejected; missing/unsupported finish reason rejected; reasoning-only result rejected; streaming stop retained and premature stream termination rejected; context exhaustion blocks generation; cancellation prevents persistence or worker handoff. Service tests should assert only a completed public proposal is persisted before Coder acquisition.
5. Run an explicitly versioned disposable complex task with safe metadata before the untouched heldout. Keep the frozen main failures unchanged. Report plan completion, interfaces and final independent artifact acceptance separately; a complete prose proposal is not proof of software correctness.

Do not broaden accepted finish reasons without verified installed-runtime evidence, expose reasoning text, or turn a malformed plan into an authority-bearing mutation. Existing workspace, sandbox and publication gates remain authoritative.
