# Live hybrid acceptance

`verify-hybrid-live.py` is an opt-in executable acceptance driver. Preparation does not execute models or Docker. Run only after production/harness freeze and after other live evaluators stop:

Resource sampling is always enabled.

```powershell
.app-venv/Scripts/python.exe benchmarks/verify-hybrid-live.py --live --output benchmarks/hybrid-live-acceptance.json
```

A fresh output path is required. The shared evaluator kernel lock and existing idle check are used. Installed model registry, actual Workbench request path, real Docker verifier and existing independent trusted-test proxy are reused. No model downloads, worker overrides or synthetic failures are injected. Outcome history is disabled for this fixed-policy observation.

The eight cases are explanation, variable rename, generated candidate repair, multi-file architecture, consecutive warm Coder edit, two scoped follow-ups, cancellation at a real generation progress boundary, and stale-revision Accept rejection. The repair fixture starts with genuinely broken source. An actual generated candidate must then fail and recover under independent tests before automatic repair is PASS. First-pass correctness is NOT_VERIFIED for that mechanism. Explanation is UNKNOWN pending independent semantic review.

Cancellation is at a generation boundary, not a claim of mid-token cancellation. Process PIDs and command hashes are recorded before/after; existing one-second RAM/VRAM/process sampling cannot prove every instant. Qwen-to-Coder handoff derives from actual route stages. Warm affinity requires identical before/after server identity and zero recorded switches.

Only temporary workspaces created by this driver are edited or accepted. Endpoint tests call actual FastAPI ASGI routing via TestClient on that isolated Workbench, not a deployed UI backend. One stale candidate is rejected and a separate independently validated candidate may be accepted with exact-byte hashes. No automatic publication occurs in candidate requests. Temporary directories are cleaned after reporting; detailed results, supervisor observations, routes, candidate hashes and validation trajectories remain in the requested report.

No held-out dataset is read. This driver is operational acceptance evidence, not a statistical quality comparison or proof of universal model understanding. Failed or unavailable prerequisites remain FAIL/NOT_VERIFIED; the driver does not fake a successful candidate.
