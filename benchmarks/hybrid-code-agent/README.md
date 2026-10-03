# Hybrid CodeAgent development fixtures

100 development cases, 25 contract clusters: 20 new computational behavior contracts repeated across task modes and five related synthetic visual-board layouts. Cases are distinct tasks, not 100 independent algorithms. Mode counts: 15 explanations, 15 edits, 15 debugging repairs, 15 implementations, 10 refactor/multifile, 10 architectural CLI/service tasks, 10 context-heavy edits, five explicit scoped follow-ups and five vision tasks. Selected requests include spelling noise.

The author inspected V2 development schema and examples. No held-out fixtures or outputs were read. Contracts are newly authored, but task templates, basic programming patterns and cross-mode repetitions are correlated with prior development tasks. Comparisons require paired cases and clustering by contract. Five visual contracts also share one layout family, so their apparent cluster count overstates visual independence.

`author_development.py` contains author-only reference implementations and assertions. Models receive only case request, initial workspace, public scope and optional image; references and trusted external tests must stay outside editable/model context. `validate_authoring.py` checks references pass and unfinished baselines fail. This verifies oracle discrimination on authored examples, not oracle completeness or product correctness.

Fifteen explanations require independent semantic review bound to actual answer hashes. Vision checks verify labels, button markup and specified style text, not rendered visual fidelity; independent image review is additionally required. The five PNGs are Pillow-authored references, not browser screenshots. Public request text deliberately specifies labels/colors; images contribute layout evidence.

Follow-ups include the complete current contract and named target, plus bounded previous conversation. They do not rely on fabricated persisted operational state or an ambiguous bare “fix that.” Context-heavy tasks contain unrelated modules whose hashes should be preserved. Supplied runtime tests remain external, immutable and unavailable to the model.

`main.json` and `provenance.json` use the existing evaluator's frozen canonical/file SHA-256 schema. Existing `baseline-*` preservation artifacts are unrelated and must not be overwritten. Freeze candidate code/settings before final evaluation; do not tune on untouched held-out data. No model, Docker or production operation is performed by authoring validation.

Offline commands:

```powershell
.app-venv/Scripts/python.exe benchmarks/hybrid-code-agent/author_development.py
.app-venv/Scripts/python.exe benchmarks/hybrid-code-agent/validate_authoring.py
```
