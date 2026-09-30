# Structured import performance and concurrency — 2026-09-30

## Root causes

The reported XLSX source contains seven sheets, 96,675 stored cells, 221 blank cells and 19,723 formulas. The previous extractor/tokenizer produced 2,765 dense embedding passages from its cell text. Extraction and tokenization took 3.478 seconds in the local measurement; the screenshot shows embedding had only reached passages 73–80 at 76.2 seconds. No completed old-import duration was measured.

`Jobs.start` admitted only one job of any kind, including imports. Thus an import rejected unrelated Agent/Code requests. `Workbench.import_file` also held the document-management lock throughout extraction and embedding, delaying rename/move/delete. These restrictions were implementation choices, not a requirement of using the local chat model.

## Changes

- XLSX streams stored cells and groups them into rows, skipping empty values while preserving coordinates and cached formula values.
- Structured records use exact FTS indexing. Compact descriptions use the existing pinned semantic embedding model. Lexical-only records have explicitly marked zero vectors; they never enter dense ranking or masquerade as semantic embeddings. Exact record matches precede schema overviews.
- CSV/TSV, JSON/JSONL, YAML, XML, TOML and INI/CFG retain field paths and record boundaries. Input, nesting, expanded-text and collection limits remain enforced. YAML aliases and XML document types are rejected; no formula execution or database execution is introduced.
- One import can run alongside one execution/model workspace job. Both lanes remain bounded. Active jobs survive history pruning.
- The indexing lock serializes imports; the document-management lock is held only for final publication. Revision rechecks prevent a concurrent deletion or replacement from being undone by stale indexing, and concurrent renames persist in citations.
- SQLite WAL permits readers alongside index writes. Large previews return bounded passage pages, and source links locate their passage page.

## Measured result

The same saved 709,351-byte workbook was imported into a temporary index with the real local ONNX embedding model in **6.723 seconds**, including loading the embedder, extraction, tokenization, seven semantic descriptions and index publication. The index retained **13,269 exact records** plus seven semantic descriptions. The source file was read only; existing library entries and projects were not modified. This is one local measurement, not a performance guarantee for every workbook or machine.

The structured index trades per-row semantic embeddings for fast exact-record search and table-level semantic context. Natural-language paraphrases of arbitrary individual record values are not guaranteed to match. General RAG excerpts are not an exhaustive aggregation engine. Legacy binary XLS/XLSB, Parquet, arbitrary databases and every possible proprietary format are not claimed as supported; export to a supported structured format first. Previously indexed unchanged versions are not silently rewritten.

## Verification

Regression tests cover exact value retrieval across formats, a 1,000-row workbook embedding one description, bounded hostile expansion, structured dates, independent job admission, Agent completion during paused indexing, concurrent deletion blocking stale publication, concurrent rename persistence, paged content and citation navigation. The full Python suite passed (579 passed, 7 skipped). Frontend type checks and the production build passed. A disposable browser test passed import progress, cancellation, publication, and large-preview pagination, then shut down its test server.
