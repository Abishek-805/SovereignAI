# Smart Router V2 independent fixtures

`main.json` is the development set: 20 explanation, 20 edit, 20 debug,
15 implementation, 15 multi-file refactor, 5 planning/architecture, and
5 image-guided code cases. It includes typo and conversation follow-up
variants, a deliberately ambiguous edit, and failing initial sources.

These are **100 tasks, not 100 independent algorithms**: 35 new computational
contracts recur across modes. Use `contract_id` to cluster uncertainty estimates.
No old heldout JSON or old benchmark outputs were opened during authoring.
Initial schema inspection of the old authoring script exposed its embedded legacy
contract definitions. These V2 contracts are distinct; authorship is not claimed
to have been blind to every old contract definition.

`heldout.json` was written in a separate authoring pass with 24 distinct new
contracts. Its author script is separate. Tuning agents must not inspect either
file until production, harness, and configuration hashes freeze. It covers
debugging, implementation, and refactoring; no heldout claim about explanation,
architecture, or vision quality is justified.

Every executable oracle supplies independent `trusted_files`, withheld from
generation. Architecture checks actually exercise a CLI payload and service
delegation. They are bounded examples, not complete correctness proofs.
Explanation and ambiguous cases require exact-answer independent semantic review.

Five actual PNG assets accompany independently authored HTML interfaces. They
are interface reference bitmaps authored using Pillow, **not browser screenshots**.
Structure/color assertions are executable; independent visual comparison is
still required for a visual-quality success claim. The reference HTML is an
authoring asset, not model input.

`provenance.json` records the frozen exact and canonical dataset hashes.
`validate_authoring.py` checks fixture reference solutions and broken baselines
offline without production models or Docker. This sanity check is not a model
benchmark. Do not rerun author scripts after freezing during policy tuning.
