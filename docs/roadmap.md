# Roadmap to the October 16, 2026 pilot

The target is a clean, reproducible pilot with at least two LLM orchestrator
results by October 16, contingent on a learned-policy backend passing the
published feasibility gates. The schedule does not imply that GPU rollouts or
model results already exist.

| Dates (2026) | Work | Exit criteria |
|---|---|---|
| September 25–28 | Foundation: pin and verify sources; finalize the protocol, research comparison, feasibility gates, records, runner contract, and runtime split | Documentation and source locks agree; mock/unit checks pass; no learned-rollout claim is made |
| September 29–October 3 | Feasibility: provision Prime Intellect GPU worker; build isolated RoboCasa coordinator and policy worker; run GR00T qualification, then π0.5 only under the fallback rule | One fixed backend passes every skill-entry 8/10 gate, the 16/20 full-task gate, and the matched-continuation relevance gate, or feasibility is reported as incomplete/failed with preserved evidence |
| October 4–9 | Runner integration and model adapters: finish HTTP worker boundary, manifests, replayable records, adapter parity, and dry runs | End-to-end traces are complete; model payload audit shows RGB/proprio only; adapters emit the same operation schema and share budgets/prompts |
| October 10–13 | Multiple-model evaluation | At least two orchestrators complete the same prespecified seed set with the same locked policy, environment, instructions, budgets, and scoring; infrastructure errors are resolved or separately reported |
| October 14–16 | Clean reproduction and release candidate | Rebuild from locks, rerun the reported configuration, reconcile every aggregate with episode records, publish limitations and feasibility evidence, and freeze the pilot artifacts |

## Decision points

- Do not start scored model runs before policy qualification passes.
- Do not mix GR00T and π0.5 results. If fallback is necessary, rerun all model
  evaluations against the single selected backend.
- Do not substitute scripted actions when a learned skill fails.
- Do not add artificial disturbances to create recovery examples. Exercise only
  naturally occurring execution failures and handoffs.
- Treat missing and infrastructure-incomplete trials as pending, not as pass or
  fail. Preserve them in the artifact set.
- If qualification or GPU provisioning slips, reduce the deliverable to the
  verified foundation and feasibility report rather than presenting mock or
  partial execution as benchmark results.

## October 16 release checklist

- exact source, checkpoint, environment, model, prompt, and seed identities;
- qualified-policy evidence for eight skill-entry conditions, twenty diagnostic full tasks, and matched continuations;
- at least two comparable model result sets, if feasibility passed in time;
- episode-level decisions, observations, action attempts, evaluator traces,
  timings, usage, errors, and videos;
- primary success and required diagnostic metrics computed from preserved runs;
- explicit separation of diagnostic-oracle and model results;
- a reproduction run from the frozen locks and a documented list of limitations.
