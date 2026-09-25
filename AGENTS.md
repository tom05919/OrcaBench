# Project rules

This benchmark compares different LLM orchestrators using the same fixed learned
policies and harness. Preserve that distinction in code, experiments, and claims.

- All project work and caches belong under this project root.
- No artificial disturbances, scripted manipulation replacements, or training.
- A diagnostic hand-authored supervisor can read simulator predicates, but its
  results must never be mixed with model benchmark scores.
- Never expose reward, task success, object coordinates, subtask annotations,
  evaluator artifacts, or corrective advice to a model adapter.
- Unknown skill performance is null / untested, never zero or an invented estimate.
- Source inspection and mock tests do not qualify an actual robot policy.
- Preserve every attempted episode, including failures and infrastructure errors.
- Run `python -m unittest discover -s tests -v` after runner changes.
- Keep compatibility fixes surgical and record changes to the evaluation contract.
