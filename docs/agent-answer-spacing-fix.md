Agent composer and evidence-answer correction

Removed inherited conversation-details margin from collapsed composer documents; reduced input minimum height while preserving content growth.

Outcome query compilation now discards an unsupported model-proposed threshold when explicit source outcome labels can answer the requested measure. Requested population, scope and operation are preserved. Numeric-only sources still require an evidenced rule; no customary passing score is assumed. This applies to record counts and rates across supported tables, not one cohort or assessment.

Shared answer instructions require synthesis and supported partial answers rather than verbatim retrieval or blanket refusal. This is an inference-time correction, not model retraining or a guarantee of correctness for every task.

Validation: 44 answer/outcome/workspace-query tests passed; Svelte check returned zero errors and warnings. Historical benchmark evidence untouched and stopped tests remain stopped.
