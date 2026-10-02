# Frozen independent coding fixtures

`main.json` contains 100 cases: 20 explain, 20 edit, 20 debug, 15 implement,
15 refactor/multifile, 5 architecture, and 5 vision. `heldout.json` contains
24 additional cases based on eight different contracts. The independent audit
agent authored these after reading the master requirements and existing
harnesses, before inspecting subsequent router implementation. No model,
product workflow, or Docker execution contributed labels.

Keep heldout prompts and assertions unavailable during tuning. Freeze production
policy/code hashes before a heldout run. Do not tune against heldout failures
and reuse that set as independent confirmation.

Each executable case declares fixture-owned Python files, allowed change paths,
and trusted assertions. Trusted test files belong outside the editable project:
inject them only for sandbox validation and verify their hashes. Preserve
`initial_files` exactly at the beginning of every strategy/case. Six main cases
use explicit fixture conversation history; do not strip it from follow-up input.

The benchmark endpoint is validated `READY_FOR_REVIEW`, not publication.
Explicit accept/publish requires a separate disposable publication test. Rubric
cases need independent semantic review; keyword matching is insufficient.
Architecture assertions validate function behavior and a narrow service shape;
the complete CLI/service design still needs review. Five vision cases have no
screenshot/project assets and must remain `NOT_VERIFIED`, with coverage reported.

The suite has 100 task fixtures, not 100 independent algorithms. Main contracts
are reused across task modes; report clustered uncertainty and per-category
results. Trusted assertion examples do not prove exhaustive correctness.

`provenance.json` records file and canonical SHA-256 hashes. Canonical bytes are
UTF-8 encoding of `json.dumps(dataset, sort_keys=True, separators=(',', ':'),
ensure_ascii=False)`. Hash the entire dataset; do not omit fields. The offline
`author_fixtures.py` documents authorship and regenerates the exact frozen files;
changing it or regenerating modified files constitutes a new dataset version.
