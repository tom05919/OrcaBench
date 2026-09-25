# Decision log

This log records protocol choices separately from experimental findings. A
decision may be revised when GPU evidence warrants it; revisions must retain the
old entry and explain the effect on comparability.

| Date | Decision | Basis and consequence |
|---|---|---|
| 2026-09-25 | Use `CerealAndBowl` as the first feasibility candidate. | It has an automatic physical predicate and a 4,350-step horizon. Qualification remains pending; selecting it is not a claim that it tests orchestration. |
| 2026-09-25 | Score cereal/counter contact, bowl/counter contact, and a closed cabinet. | This is exactly the pinned upstream `_check_success`. The upstream phrase “next to the milk” is not enforced, so the benchmark goal omits that relation. |
| 2026-09-25 | Expose three RGB views, listed proprioception, skill/history state, and budgets. | Object state, reward, success, predicates, subtask labels, and evaluator advice stay private. Current-frame access is the development default. |
| 2026-09-25 | Use six high-level operations and agent-selected intervals of 1–100 steps. | The runner owns synchronous physics and queue semantics. Switch, retry, and interrupt discard queued actions; only `continue` preserves them. |
| 2026-09-25 | Require a correct completion declaration for primary success. | Physical completion without declaration and a false declaration are failures. Physical completion is retained as a diagnostic. |
| 2026-09-25 | Start with the official GR00T N1.5 checkpoint and reserve official π0.5 as fallback. | The backends are never mixed in a comparison. π0.5 begins only after a completed GR00T failure or documented incompatibility. |
| 2026-09-25 | Isolate simulator and policy dependencies behind a loopback HTTP worker. | Pinned RoboCasa and GR00T require incompatible Tianshou versions. The worker verifies checkpoint identity and returns learned action chunks only. |
| 2026-09-25 | Require both nominal and naturally encountered intermediate entry conditions for every fixed skill. | Each condition needs at least 8/10 valid trials. This prevents a nominal-only aggregate from hiding unreliable handoffs. |
| 2026-09-25 | Add a matched-continuation relevance gate. | Qualification cannot pass from skill and full-task rates alone; retained traces must show a naturally reached state where supervision choices can change the outcome. No artificial disturbance is allowed. |
| 2026-09-25 | Keep development, diagnostic, and official model artifacts distinct. | Official runs require a frozen release manifest bound to the qualified checkpoint, contract hashes, trace evidence, and evaluation seeds. |
| 2026-09-25 | Defer exact LLM identifiers and GPU instance selection. | Both must be recorded before evaluation and then remain fixed. No suitable Prime Intellect worker is provisioned yet. |

Open decisions after the first real rollouts are the final observation interval
defaults, whether current-frame image history is sufficient, the exact paired
continuation cases, the evaluation sample size beyond the 20-seed pilot, and the
two model identifiers. Resolve them on development seeds before freezing the
release contract.
