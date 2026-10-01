# Isolated controller experiment

SmolLM2-360M-Instruct Q4_K_M is an optional offline experiment. It has no routing,
mutation or publication authority in production. Its verified download manifest is
stored here; weights remain ignored under `models/experimental-controller/`.

The frozen pilot is in `../benchmark/`; measured SmolLM2 and Gemma baseline outputs
are in `../results/`. Neither baseline passed its promotion gate. These results
describe one zero-shot contract, not the production multi-pass task workflow.

No fine-tuning dataset or independent held-out evaluation has been produced.
