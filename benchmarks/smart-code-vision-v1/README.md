Five supplemental vision-assisted Code fixtures, independently authored from schema context only. No production/router implementation, existing heldout cases, model outputs or Docker execution were used. This dataset is supplemental engineer-authored evidence, not a frozen independent heldout benchmark.

Each task includes a small broken `index.html` in `context.initial_files` and a genuine Chromium-rendered `target.png` in `context.image_path`. The screenshot is the intended final UI. `original.html` preserves the supplied source; `reference.html` is private oracle material and must never enter the model prompt. Expected stage order is vision then code, with task type VISION_ASSISTED_CODE.

Trusted Python stdlib tests narrowly verify retained IDs/tags, label associations and explicit essential CSS declarations. They cannot establish screenshot fidelity or reject every cascade trick. Consequently every case requires semantic review. Do not report their passing as visual fidelity evidence.

`validate.mjs check cards /absolute/path/to/index.html` is a supplemental browser oracle: it compares rendered element bounds within four pixels, selected computed colors/radii, visible text and label associations. It uses the workspace's installed Playwright and Chromium; it is not part of Docker grading. Fixture names are cards, navigation, form, table and empty-state.

Reproduction: run `python benchmarks/smart-code-vision-v1/build.py`, then `node benchmarks/smart-code-vision-v1/validate.mjs render NAME` for each fixture. Targets use Chromium 141.0.7390.37, viewport 960x600 and device scale 1. No external assets or network requests are required. The provenance manifest hashes the JSON dataset; generated screenshot hashes are recorded in verification.json after rendering.
