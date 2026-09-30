# Original previews, table answers, and deletion review — 2026-09-30

## Causes and changes

Uploads previously became library entries only after extraction and indexing. Background uploads now publish a receipt and verified source snapshot first. Pending/failed entries remain previewable, have explicit indexing status, and cannot silently reappear after deletion during indexing. Cancelling indexing retains the uploaded original and publishes no incomplete index. An interrupted indexing receipt is marked incomplete on restart; reimport resumes indexing. Existing indexed versions remain readable during replacement.

XLSX preview now reads original stored cells separately from RAG passages. It provides sheet tabs, row/column coordinates, merged cells, stored colours and font emphasis, number formats, scrollable rows, and a row jump control. CSV/TSV and JSON record collections have table previews. The rendering is bounded and is not a complete Excel implementation: charts, conditional formatting, formula recalculation, and print layout remain available in the original download. Extracted passages have a separate styled page control and direct page selection.

The old filename filter treated an entity ID such as a student number as an exclusive document reference. Explicit file references still narrow the library; a bare entity ID no longer discards other documents. XLSX record indexing detects the populated header row rather than using a one-cell title as the schema.

Document questions now have a read-only table-query step. The local model selects a supplied table, exact columns, filters, and one supported operation: lookup, count, sum, average, minimum, or maximum. The application validates the plan and executes it over complete records, without Python/SQL execution. The answer model receives the verified result, scan count, and truncation information with citations. It must not invent a pass threshold. Ambiguous questions can still require clarification. Numeric and citation checks remain enforced; copied shorthand measurement labels trigger one bounded readability rewrite.

Code and Agent now discover staged tasks through the same persisted changes contract, including file-organization drafts. Pending file/folder removals appear in their review lists and are marked in Explorer. Acceptance and discard remain explicit; staging does not mutate canonical files. The transcript no longer calls unpublished operation results completed changes.

## Live read-only evidence

Using the existing local Qwen3-4B model and a disposable index of the reported workbook, without writing user projects or the user library:

- “How many students passed in CAT 1 of PST?” selected the CAT 1 sheet, scanned 1,894 records, and returned 1,038 rows whose Result is PASS.
- “What is the mark of 24ALR001 in CAT 1 of PST?” returned 36.5 without needing the filename. A subsequent planner refinement selected the detailed CAT 1 sheet and its Total (50M) column rather than the summary sheet.
- The final wording run returned 36.5 out of 50 marks with [S1] after one citation repair, in 24.2 seconds. The model inserted an underscore in the student identifier; exact-query identifier presentation now restores case/separator variants from trusted filter values, tested without changing different IDs. This is not a guarantee against other model mistakes.
- Imports in these concurrent development runs took 17–40 seconds; the earlier 6.7-second result is not a universal guarantee. The upload receipt and preview no longer depend on finishing this work. Local model query/answer generation still took roughly 34–52 seconds in these runs.

`benchmarks/structured-query-audit.py` reproduces the checks against a temporary index with the real local model. `benchmarks/audit-import-server.py` and the browser acceptance script use disposable projects and library data. No benchmark needs to delete or recreate user projects.

## Verification

- Final backend suite: 588 passed, 7 skipped; targeted answer/repair/table tests: 31 passed. The skips do not establish runtime isolation or GPU compatibility.
- Svelte check: zero errors and warnings; production Vite build passed.
- Staged-task frontend contract: two tests passed.
- Browser acceptance passed for immediate receipt, original workbook grid and sheet tabs, cancelled indexing, passage pagination, named pending deletion, unchanged canonical files before acceptance, and removal after acceptance. This uses a clearly identified disposable backend with model and sandbox stubs, so it verifies the UI/publication contract, not Docker isolation or model reasoning.
- Regression tests cover title/header detection, complete-record aggregation, CSV numeric text, pending-document retrieval, deletion during indexing, and an answer repair that changes “50M” to “50 marks” while retaining the verified score.
