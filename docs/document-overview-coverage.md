# Connected document overview coverage

The structured task planner chooses `document_scope: focused` or `overview`. The service does not infer this decision from a greeting/summary keyword table. Connecting documents still permits an ordinary model answer without reading indexed content.

Focused questions retain filename/referent-aware retrieval. Collection overviews offer one complete indexed passage per connected document before additional passages, with at most three passages per document. This avoids a top-six relevance search dropping most of a sixteen-document collection, and it does not load the embedding runtime for an overview.

Every proposed evidence prompt is counted by the actual model tokenizer against the existing configured context, output, and safety allowance. Oversized passages are omitted rather than silently cut and presented as complete. The response and inference prompt receive `coverage`, including requested/covered documents, indexed/included passage counts per document, and whether all documents/all indexed passages are represented. Indexed passages are not a claim of complete original-file interpretation.

The model is instructed to synthesize the excerpts itself, including separate entries for unrelated documents. A summary need not already exist in the input files. Claims retain the existing citation and numerical checks; these checks do not prove semantic support. Overview Word requests use the same synthesis and existing validated artifact publication. Word artifacts also contain a deterministic evidence-coverage appendix listing represented document/passage counts, omitted documents, partial evidence, and the original-file interpretation limitation. The legacy direct generic report endpoint retains its explicitly labeled excerpt inventory when no planner scope was supplied.

Validation: 81 tests passed across service, API, grounded answers, Agent context dispatch, and the new collection overview suite. The collection tests cover sixteen connected documents plus an excluded unconnected document, fair passage ordering, measured context omissions, scope propagation, and actual Word publication. These are controlled-model regression tests, not live model quality or latency measurements.

Remaining limitation: this bounded implementation summarizes excerpts. Large-file/full-collection synthesis requiring all source content needs a separately budgeted multi-stage document summarization workflow. Coverage flags disclose that limitation; increasing the context or claiming complete-file reading would not resolve it.
