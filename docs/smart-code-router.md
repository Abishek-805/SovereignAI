# Smart Code Router: measured evidence

Updated 2026-10-03. This work improves orchestration, context and verification; it does not train model weights or establish perfect task accuracy.

## Frozen version1 comparison

Independent main100 and untouched heldout24 ran serially across five arms. D uses prior routing policy within shared current workflows, not a historical binary. Reused contracts require clustered uncertainty; five original vision cases lack images and remain unverified.

| Arm | Main PASS/PARTIAL/FAIL/UNKNOWN | Heldout PASS/FAIL | p50/p95 seconds | Calls/switches |
|---|---|---|---|---|
| A: Gemma4 E2B | 59/1/35/5 | 14/10 | 20.51/50.83 | 312/1 |
| B: Qwen3.5 4B | 57/5/33/5 | 9/15 | 30.05/96.15 | 313/4 |
| C: Qwen2.5-Coder3B | 41/16/38/5 | 11/13 | 12.84/29.93 | 265/1 |
| D: Previous routing policy | 46/3/46/5 | 11/13 | 17.43/32.36 | 511/0 |
| E: Smart routing | 58/1/36/5 | 11/13 | 13.66/44.55 | 290/11 |

E exceeds D on main passes and uses fewer calls, but ties D on heldout and does not exceed A. These results do not establish universal superiority or statistically proven improvement. Narrow tests passed a broken service and incorrect CLI delegation in A/main094; independent semantic review counts that goal as failed.

Offline analysis corrects the fixture coder/code role alias, preserving raw results. E actual model-role suitability81/90 (10unknown); task type70/90, complexity45/90, joint27/90. Suitability is not task quality. Missing broker task-quality/cost remains UNKNOWN.

Peak sampled Python-plus-server RSS / total-device VRAM MiB: A3620/2936, B8343/3330, C8163/3327, D3271/3396, E4582/3348. RSS excludes other system use; VRAM includes unrelated device use. Maximum sampled server count1 does not prove every instant. Cold/warm state and interrupted recovery affect switch counts. The interrupted Docker STOP is separate evidence, not a model failure.

## Requested22-point assessment

| Item | Status | Evidence/limit |
|---|---|---|
| 1. Architecture | PASS | Reuses registry/broker/supervisor/lease/staging/sandbox; no parallel GPU router. |
| 2. Features | PARTIAL | Protected normalization, coding/file/workspace/history/modality features; some timings unknown. |
| 3. Selection | PARTIAL | Admission/compatibility before role/residency/affinity; measured superiority unproved. |
| 4. Roles | PASS | Installed lightweight/reasoning/code/vision; no new downloads. |
| 5. Residency | PASS | Exclusive heavy-worker lease; sampled maximum1 server. |
| 6. Affinity | PASS | Ordinary repair stays with Coder; upfront complex plan persists before handoff. |
| 7. Code Assist | PARTIAL | Direct clear-file path and one-call simple explanation; native autocomplete not demonstrated. |
| 8. Sandbox | PASS | Unavailable verified Docker stops generation; actual18 isolation checks passed. |
| 9. Repair | PARTIAL | Bounded feedback/repeated-error stop; actual broken-baseline → Coder correction → independent tests passed; automatic repair of a failed generated candidate remains unproved. |
| 10. Benchmark design | PASS | Frozen main100 + heldout24, five arms, same tools/budgets. |
| 11. Results | PASS | All620 attempts saved; semantic partials/failures separate. |
| 12. Task success | PARTIAL | Failures remain; trusted tests do not prove arbitrary application correctness. |
| 13. Routing accuracy | PARTIAL | Known/unknown label and actual/advisory role denominators separated. |
| 14. Latency | PASS | Measured p50/p95 above; no historical-binary speed claim. |
| 15. Switches | PASS | E11 versus D0, not an improvement in this metric. |
| 16. Calls | PASS | E290 versus D511 on main; no general minimum claim. |
| 17. RAM/VRAM | PASS | Measured sampled scope above. |
| 18. Security | PASS | Existing network/root/input/privilege/resource/secret/cleanup restrictions retained. |
| 19. Publication | PASS | Disposable proof preserved original bytes until Accept, then saved the exact independently validated source. Benchmark candidates were never implicitly accepted. |
| 20. Docker | PASS | Existing startup recovered engine without reset; pinned image verification preserved. |
| 21. Limitations | PASS | Unsupported images, reused contracts, narrow tests, host/camera dependencies and model failures disclosed. |
| 22. Remaining blockers | PARTIAL | Vision tasks still fail; automatic generated-candidate repair and overall reliability remain incomplete. New versions have not repeated the full comparison. |

## Versioned follow-ups

V3 uses concise finite1536-token upfront planning and safe finish/content diagnostics; incomplete outputs still fail. A live complex plan completed, then its generated source failed. Direct complex execution now skips redundant intent inference after planning. Image mutation shares explicit authority guards; explanatory/negative text cannot authorize writes.

EvaluatorV3 exposes bounded actual exception categories/candidate-bound symbols, withholding oracle code/paths/assertion values. Its main034/main023 attempts still failed; no candidate-repair success is claimed. V2 supplemental vision5 all failed incomplete proposals. V4 supplies application-authored source-generation/image-observation review contracts and a bounded larger vision response allowance. All five V4 supplemental vision tasks failed; some reached the Coder handoff, but no successful interface implementation was independently verified. The final vision-stage alignment is covered by a regression test, not a repeated live benchmark. New versions have NOT repeated the full frozen comparison and must not inherit its performance claims.

Raw evidence: benchmarks/smart-code-router-results.json, smart-code-router-analysis.json, smart-code-router-heldout-results.json, smart-code-router-heldout-analysis.json; exact-hash semantic reviews and fixture provenance alongside them. The interrupted attempt and versioned follow-ups are preserved separately. Primary papers and official verification references are in code-verification-research.md.

## Final verification

Backend: 978 passed, 7 skipped before the final vision-stage alignment; 84 relevant model/service/vision tests passed afterward. Frontend build and type checks passed; routing telemetry tests passed. Final full regression after alignment: 979 backend tests passed, 7 skipped; 728 frontend unit tests passed across 61 files. The disposable live proof is smart-code-repair-publication-proof.json: actual Docker baseline failure, Coder correction, independent validation, and explicit Accept all passed. This demonstrates correction of a broken baseline, not reliable automatic repair of every generated candidate.

Evidence archives: smart-code-router-results.json.gz, smart-code-router-heldout-results.json.gz and smart-code-router-interruption-docker-stop.json.gz. smart-code-evidence-manifest.json records both archive and decompressed SHA-256 hashes.
