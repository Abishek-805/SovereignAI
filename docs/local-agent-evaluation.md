# Local coding agent evaluation

On the tested Windows laptop (16 GB RAM, RTX 3050 A with 4 GB VRAM), SovereignAI serves Qwen3-4B-Instruct-2507 Q4_K_M locally. An agent wrapper can improve how edits are presented and applied, but it cannot make a small model consistently preserve unrelated code.

| Candidate | Local fit | Finding |
| --- | --- | --- |
| [Aider](https://aider.chat/docs/llms.html) | Runs on Windows and accepts the app's OpenAI-compatible local endpoint. | Tested in an isolated disposable project. It created linked `index.html` and `style.css` in one pass. On a follow-up edit, it also changed an unrelated valid CSS color to an invalid value. Do not adopt it as the default editor on this model. |
| [Continue Agent](https://docs.continue.dev/ide-extensions/agent/model-setup) | Can use local models, but Agent mode needs reliable tool use. | No evidence that the current 4B model would improve its tool decisions. Not installed. |
| [Goose](https://block.github.io/goose/) | Windows desktop/CLI/API and local model providers are available. | It would add a second agent runtime, but still depend on the same local model. Not installed or benchmarked here. |
| [OpenHands](https://github.com/OpenHands/docs/blob/main/openhands/usage/llms/local-llms.mdx) | Its recommended local coding model requires much more VRAM than this laptop has. | Not a suitable local default for this hardware. |

The Aider trial used `aider-chat 0.86.2` with `openai/sovereign-text`, no Git commits, and the local model endpoint. It was a small functional check, not a benchmark across languages or repositories. The production Agent remains on the app's bounded project workflow. This evaluation led to targeted fixes for new-project routing, paired HTML/CSS generation, and duplicate execution of multi-file edits. Docker execution remains separately isolated.
