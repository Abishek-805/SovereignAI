# Upgrade verification, 2026-09-28

This records checks actually performed. It is not a claim that every model, workflow, or performance experiment in the upgrade plan is complete.

## Automated checks

- Python regression: 189 passed, 6 skipped. One dependency deprecation warning from Starlette/httpx remains.
- Frontend Svelte/TypeScript: 0 errors and 0 warnings.
- Production build: final split build succeeded in 5m18s. Existing database-service static/dynamic import warning remains; no new UI framework was added.
- Frontend unit suite: 677 passed across 51 files. Seven old single-bundle PWA assertions were replaced with split-bootstrap and complete asset-cache integrity checks. Five local-storage migration tests now isolate browser IndexedDB work from their Node environment.
- Browser cache smoke check: cached split frontend and Code shell loaded with browser networking disabled. This does not claim offline inference or the OS-enforced Gate A.

## Real local workflows

- `What is your name?`, with a coding project selected: generated a SovereignAI identity answer. Task trace contained only planning; it did not inspect or edit project files. The initial cold request took 23.3 seconds. This is a single observation, not a latency percentile.
- `hay`, with Summa selected: generated a clarification answer instead of executing a project task.
- `whats up?`, with Summa selected: generated a conversational answer with no project task. The observed warm request took 2.47 seconds; this is not a performance benchmark.
- Agent browser: submitted user text remained visible during generation; a Stop control was visible; New chat cleared current turns and History retained the previous conversation.
- Existing Summa `addition_operation.py`: browser typed `3` and `5` directly on the terminal surface using Enter. Docker returned `The sum of 3.0 and 5.0 is 8.0`.
- Terminal browser: `pwd` executed in the isolated Docker project copy and returned `/output/project`. Shell commands currently use separate isolated sessions, not a persistent host shell.
- `generate me a report`, with all 16 existing documents selected: completed as a cited overview with 16 source entries. Word download returned HTTP 200 and 38,951 bytes. This does not prove that all narrower report questions will succeed.
- Docker Desktop was started from its installed local executable. Sandbox status reported ready with the pinned image and existing no-network, non-root, read-only-root policy.

## Browser verification

Use `node benchmarks/workbench-ui-acceptance.mjs` against the running production backend. It captures screenshots and writes `benchmarks/ui-acceptance/results.json`. Generated images and results stay local; the test source is versioned.

The acceptance script covers 1920×1080, 1600×900, 1366×768, 800×700, and 390×844. It uses real navigation and Control Center appearance controls, and asserts the document theme class before recording each light/dark check. Checks include page overflow, composer visibility, Agent bounds, existing-program input, and a Docker shell command.

Visual inspection found and corrected the document component's inherited negative margins, duplicate outer scrolling, and Code's fixed dark surfaces conflicting with a light Monaco editor. Final captures were visually inspected for desktop documents, narrow documents, Agent, and terminal input. The acceptance run passed 17 checks across the five viewport sizes, including both document themes and real terminal interaction. The Code composer was also corrected to use its shared semantic theme surface.

## Remaining engineering work

The production intent step is still generative. CPU prototype screening completed and failed a safety probe, so no classifier was enabled; see [screening evidence](intent-router-screening.md). Model-centric candidate scoring, conservative resource admission, controlled context/KV/cache tests, persistent llama.cpp router A/B, alternative model tests, and independently reviewed held-out/oracle comparisons remain planned in [workbench-upgrade-plan.md](workbench-upgrade-plan.md). No unmeasured coding specialist was enabled and no inference performance target is claimed as achieved.

Final reconstruction integration script passed 10 records covering actual model identity/no-file-read behavior, Stop cancellation, history restoration, Word report download, manager focus/search, model panel and narrow Code layout. See [UI report](ui-integration-report.md) for measurements and boundaries.
