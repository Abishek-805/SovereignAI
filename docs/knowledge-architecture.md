# Knowledge ingestion and structured answers

Original receipt, extraction/indexing, preview and answering are separate operations. `backend/app.py` receives bounded uploads; `Workbench.receive_import` saves the original and document metadata before background extraction. The library can preview retained originals while extraction/indexing is pending. An accepted upload does not imply an indexed document. Extraction progress, failure and cancellation are persisted; cancellation retains the original and does not publish an incomplete index.

`rag/ingest.py` handles the documented text/source formats and PDF, DOCX, XLSX and PPTX. UTF-8 and BOM-marked UTF-16 text are supported; binary content disguised as text is rejected. XLSX extraction reads bounded stored OOXML cells, avoiding a huge empty worksheet rectangle. Legacy XLS and arbitrary proprietary structured formats are not supported; export them to a supported format. PDF OCR requires the configured local runtime. Parsing is bounded but runs in the backend, not an isolated parser container; cancellation of an active native/parser call is cooperative.

Imports use their own job lane and `import_lock`, independently of the model task lock. Embedding batches and SQLite publication are bounded. This permits importing alongside unrelated work; it does not promise simultaneous GPU-heavy generation or instantaneous extraction on arbitrary files. Selected documents are capped at 256 references, and model prompt context has a separate budget.

## Original preview and Find

`rag/tables.py` loads bounded snapshots for XLSX, CSV, TSV, JSON and JSONL. XLSX previews retain sheet names, stored cell values, merges, widths and supported formatting. Formula values use saved workbook results; formulas are not recalculated. Charts, conditional formatting and full Excel behavior require the original file. The UI virtualizes rows. Find searches original cell values across the workbook or a selected sheet, supports case and whole-cell matching, returns coordinates and paginates matches. It does not search only the visible viewport or indexed passages.

## Read-only structured query

The model chooses a table, columns, filters and an operation from a constrained JSON schema. The application validates the plan and computes lookup, count, sum, average, minimum or maximum over all parsed records. It executes no model-generated Python or SQL. Alternative IDs use one membership filter; independent filters combine with AND. Invalid contradictory equality filters trigger bounded replanning, not an empty-result claim. Numeric aggregations exclude nonnumeric cells and expose numeric/matched/scanned row counts. Select output is capped at 40 records and explicitly reports truncation.

`Workbench.ask` scopes permitted documents, builds a table catalog with names, title rows, columns and samples, then tries this route before passage retrieval. Table choice remains a model decision and is not generally proven semantically correct. There is no permission to search an unconnected document or mutate data in a query plan.

## Grounding and presentation

Answers carry source labels. Numeric validation preserves signs and checks sentences using their own citations or paragraph citations; identifier fragments are excluded. One bounded regeneration may repair an invalid answer. If prose for a verified table query still fails, the application renders the computed records/aggregate directly with a source citation, preserving original column labels and values. It never changes a score to make prose pass. Checks explicitly record `presentation=verified_query_result` and `generated_prose_accepted=false`; the rejected model draft checks remain visible. This fallback is not a claim of successful natural-language generation or semantic proof of the selected table.

Unstructured evidence still fails closed when citation/numeric verification fails. These narrow checks do not prove every sentence's meaning, identifier-to-value assignment or arbitrary derived arithmetic. Calculations belong to the validated calculator/query executor.

## Evidence

`tests/test_document_tables.py`, `tests/test_answer.py`, `tests/test_answer_repair.py`, ingestion/API/import-concurrency tests cover the contracts. The disposable Chrome acceptance script tests import, cancellation, preview, passage pagination and cross-sheet Find. The live workbook comparison scanned 1,894 CAT 1 records and returned 24ALR001=36.5 and 24ALR051=20; its generated rewrite failed, so the verified table was shown. No user workbook was modified. See [release report](final-release-report.md) for current gate status and limitations.
