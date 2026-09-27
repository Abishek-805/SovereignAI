# Local model and runtime inventory

Recorded 2026-09-24 and updated for the source release. This file lists the project's direct model/runtime assets and source license references. The local Python wheel cache is isolated in `_review_for_deletion/offline/wheels/`; it is not part of the GitHub source release.

| Asset | Source and pinned identity | License reference | Local check |
|---|---|---|---|
| Text GGUF, Qwen3-4B-Instruct-2507 Q4_K_M | [LM Studio Community quantization](https://huggingface.co/lmstudio-community/Qwen3-4B-Instruct-2507-GGUF), revision `4edb920b6f14e3b9284d4502a6485103d72cde05` | [Qwen original model](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), Apache-2.0 | SHA-256 `8cdb57cbb880d313736a9bc4e3d3d2485f145b5e19cf33783746e753e82641fc` |
| Embeddings, BGE-small-en-v1.5 ONNX | [BAAI model](https://huggingface.co/BAAI/bge-small-en-v1.5), revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` | MIT on model card | Per-file hashes in `models/bge-small-en-v1.5/manifest.json` |
| Vision GGUF, Qwen3.5-2B Q4_K_M and F16 projector | [Unsloth quantization](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF), revision `f6d5376be1edb4d416d56da11e5397a961aca8ae` | Apache-2.0 on model card | Model SHA-256 `aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223`; projector SHA-256 `7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7` |
| llama.cpp runtime, b11132 CUDA 12.4 | [llama.cpp project](https://github.com/ggml-org/llama.cpp) | [MIT license](../licenses/llama.cpp-LICENSE) plus bundled OpenMP notice in `runtime/llama-b11132/LICENSE-LLVM-OpenMP` | A local `offline-manifest.json` can be generated with `scripts/create_offline_manifest.py` |

A locally generated `offline-manifest.json` checks integrity of files on that machine. It is not part of the source repository and does not establish ownership, distribution rights, model accuracy, or isolation. Review all dependency notices before sharing a packaged release.

The workbench now includes Monaco Editor 0.55.1 (MIT; dependency license in frontend/llama-ui/node_modules/monaco-editor/LICENSE). The locally built sovereign-workbench Docker image adds language runtimes and TypeScript 5.9.3; the recipe is offline/Dockerfile.workbench and the tested image digest is in data/sandbox-validation.json. This image must be exported separately for offline transfer to another machine.
