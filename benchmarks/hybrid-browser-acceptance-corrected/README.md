# Built frontend browser acceptance

Run `node benchmarks/hybrid-browser-acceptance.cjs` from the repository root. The script starts its own Workbench/FastAPI instance with isolated temporary data/projects and an inference-disabled model. It uses the existing built frontend and installed headless Chrome through Playwright. It stops only its own Python process. The final run used the application's actual permitted loopback origin `http://127.0.0.1:8088`; no network interception or origin-header adapter was used.

Final result: three checks passed, no browser page exceptions. Evidence is `results.json`, `staged-review.png`, and `public-progress.png`. Built `dist/index.html` SHA-256 is recorded in JSON.

Checks:

1. Selecting the isolated first workspace displays `demo.py`, without the second workspace's `other.py` in its explorer.
2. A fixture draft created through the actual staging/persistence implementation and served through the actual task API renders inline review and Accept controls. Canonical source remains `return 1`; draft source contains `return 2`. Publication stays staged, `target_committed=false`, `container_executed=false`. Accept was not clicked.
3. An actual in-process Job fixture exposes public stage and bounded source preview through the actual Job API. The built UI displays the stage and `Draft code - not yet verified`. Canonical source remains unchanged. The visible page does not contain private reasoning field names.

This is a UI/API fixture acceptance, not a live generation or Docker execution result. Model calls and Docker calls are zero. Draft source and preview text are authored fixtures, explicitly marked unverified, not invented inference evidence. Absence of private field names in this fixture does not independently prove filtering of all provider-private reasoning; dedicated backend/unit coverage supplies that separate evidence.

The browser context deliberately blocks service workers to avoid stale builds. Console logs consequently include a PWA service-worker registration warning; it is retained in results rather than reported as a clean PWA test. In-flight `/workbench/info` requests were aborted during reload. PWA behavior is outside these three checks.

During harness preparation the initial disposable port8091 was rejected by the existing Origin policy, which permits 8088. A temporary test-only header adapter explored that cause; the final run switched to free8088 and removed the adapter. A preliminary nonexistent `.generation-preview` selector was replaced by the actual visible label. These were harness issues, not changes to production behavior. The retained `failure.png` is preliminary diagnostic evidence and is not a passing screenshot.

Temporary backend fixture directories were created under system temp, outside user projects. No user workspace, production model, sandbox policy or frontend source was changed.

This separate corrected-build rerun passed all three fixture checks. Results retain model-status 503 responses from the deliberately inference-disabled fixture. See results.json for exact built index hash and console/network observations. Original evidence is preserved in its original directory.
