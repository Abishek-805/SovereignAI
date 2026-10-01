# Laptop model comparison, 2026-10-01

The selected production roles are Gemma 4 E2B for conversation, task planning and document answers, Qwen2.5 Coder 3B for generated code and project edit planning, and the already installed Qwen3.5 2B vision model for image understanding. Gemma's image/audio encoders are not enabled in this text-only route. Exactly one owned llama.cpp server serves these roles, with one inference slot. Models remain on disk when unloaded.

The machine has 16 GB RAM and an NVIDIA RTX 3050 A Laptop GPU with 4 GB VRAM. During the initial inspection, other applications left only about 2.1 GiB system memory and 782 MiB VRAM available with the old model resident. Available memory changes with desktop usage; total hardware capacity is not free capacity.

## Primary-source research

| Candidate | Assessment for this machine |
|---|---|
| [Current Qwen3 4B](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Retained on disk. Publisher reports IFEval 83.4 and MMLU-Pro 69.6. Local baseline below. |
| [Qwen3.5 4B](https://huggingface.co/Qwen/Qwen3.5-4B) | Publisher reports IFEval 89.8 and MMLU-Pro 79.1. Downloaded and tested, but local table planning was slower and project inspection failed in this sample. Not enabled as a production route. |
| [Gemma 4 E2B/E4B](https://ai.google.dev/gemma/docs/core/model_card_4) | E2B has 2.3B effective parameters but 5.1B including embeddings; E4B has 8B total. The label is not a memory estimate. E2B Q4 passed the targeted tests with more VRAM headroom; E4B was not tested. |
| [Qwen2.5 Coder 3B](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct) | Specialized code model, 3.09B parameters. Fastest valid code output in this local sample. Selected for code. |
| [Qwen2.5 Coder 7B](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) | Larger coding candidate; not tested here. Weight, context and workspace overhead make full GPU residency unlikely on 4 GB; partial CPU offload needs a separate memory/latency evaluation. |
| [Phi-4 mini](https://huggingface.co/microsoft/Phi-4-mini-instruct) | Microsoft describes a 3.8B model targeting constrained memory, reasoning and instruction following. Not locally benchmarked, so not ranked above tested models. |
| [Llama 3.2 3B](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) | Small text assistant alternative. Not locally tested; distribution uses Meta's separate community license. |
| [Nanbeige 4.2 3B](https://huggingface.co/Nanbeige/Nanbeige4.2-3B) | The official card confirms looped layers and 4B total / 3B non-embedding parameters. Promising agent candidate, but the pasted claim of a fixed 2 GB footprint is not established. Runtime support and local latency remain untested. |

Publisher scores use different evaluation protocols and are not interchangeable with local application tests. They did not decide the installed defaults alone. No image-generation checkpoint or ComfyUI stack was installed: the current routes understand images and generate text/code, not diffusion images.

## Measured local smoke comparison

All four candidates used Q4_K_M, 16,384 context, q8_0 KV, one inference slot, six CPU threads, and llama.cpp b11132's GPU fit with a 1 GiB margin. The application backend was stopped while the models were tested sequentially; the previous owned server was terminated and waited for before each launch. It was restored afterward.

Each model received five checks: brainstorming with a selected project, explicit code creation routing, project inspection routing, complete OpenCV source, and a two-identifier comparison across all supplied assessment columns. Inputs and outputs are recorded in [the local results](../benchmarks/model-comparison-local.json); the reproducible script is [compare-local-models.py](../benchmarks/compare-local-models.py). The table fixture uses synthetic measurements; identifiers in the public script/results have been anonymized consistently. It does not prove correct retrieval of every real workbook.

| Model | Checks passed | OpenCV generation | Table planning | Model load/switch | Resident process RSS | Total GPU free after test |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3 4B Instruct 2507 | 4/5 | 31.3 s | 6.7 s | 7.5 s | 3591 MiB | 614 MiB |
| Qwen2.5 Coder 3B | 5/5 | 7.1 s | 1.9 s | 3.3 s | 2355 MiB | 647 MiB |
| Qwen3.5 4B | 4/5 | 26.1 s | 20.4 s | 10.9 s | 3856 MiB | 713 MiB |
| Gemma 4 E2B | 5/5 | 13.3 s | 4.2 s | 7.5 s | 2292 MiB | 1281 MiB |

These are single-run wall-clock samples, not statistically established quality scores, peak-memory measurements or end-to-end service speed guarantees. GPU totals include the desktop and other processes. The OpenCV check parses Python and checks required API names; it does not exercise the laptop camera. Docker validation remains required before publishing a generated draft and does not establish device/GUI behavior.

## Application corrections

- Planning demonstrations now precede the live request and its full connected context. A selected workspace does not authorize edits; the grammar excludes mutation actions without current-request authority.
- General conversation, source inspection, table queries and code generation have distinct routes. Chat code requests also acquire the specialist. Execution details identify the model that performed the action, alongside planning stages.
- Generic Python syntax diagnostics feed the existing three-attempt generation repair loop. Invalid syntax and comment-only placeholders cannot be staged as substantive code. Docker validation is still performed afterward; files remain unchanged until Accept.
- Table planning projects the available measurement columns for broad comparisons and combines alternative identifiers in one filter. Answer generation presents the supported comparison with its actual coverage rather than requiring a prewritten total/comparison.
- A resource rejection caused by the old resident model is retried only after unloading the owned process and resampling actual free memory. Registry instances share a switch lock. Unowned processes are never terminated.

The baseline-only installation still works. The pinned downloader verifies complete file size and SHA-256, including files already present. Asset revisions and license sources are recorded in [model notices](model-and-runtime-notices.md). Generated responses remain fallible; passing this sample is not a claim of perfect routing in every environment.

## Running-application checks

The actual `/agent/auto` endpoint answered brainstorming with an existing selected workspace in about 9 seconds and staged an OpenCV program through `sovereign-code` in about 31 seconds including planning, switching and Docker validation. The test workspace was removed afterward; no user workspace was changed. Only one owned model process remained when switching back to general text.

The actual `/ask` endpoint returned both requested identifiers' values across WAT 1–6 and CAT 1 from the user's already imported workbook, with its source citation. Private workbook results remain in ignored local benchmark files rather than the source repository.

The native `/v1/chat/completions` path also semantically routes potential code requests to the specialist without executing tools or mutating files. Its focused regression suite passed 35 tests. The final combined backend suite passed 659 tests, with 7 skipped. The actual native Chat endpoint also returned working inline Python through `sovereign-code`, then switched back to the general model.
