# First interactive task: working outline

Draft dated October 1, 2026. This is a proposal for discussion, not a frozen
protocol, implemented environment, or qualified task. The existing cereal
benchmark and its scoring remain unchanged. No new GPU run is authorized by
this document.

## Evaluation question

Can an LLM discover missing user intent through conversation, map the answer to
visible objects, and complete the corresponding physical goal by supervising a
fixed learned VLA? Distinguish failures to acquire information from failures to
execute after receiving it. Do not claim that active embodied questioning is a
new capability; compare DialFRED, TEACh, AmbiK, and the tau-bench family.

## Selected task and scope

The user selected **Personalized breakfast setup** as the first easy task in a
benchmark intended to include multiple tasks at varying difficulty. It stays
close to our existing CerealAndBowl experiment. Lunch packing can be considered
for a later task after container handling is qualified. Object assets, layout,
policy competence, and numeric budgets require development validation.

### Proposed breakfast pilot

Initial request:

> Please set out a breakfast box and a bowl for me on the adjacent counter.
> Leave the other items in the cabinet and close it when you are done.

Scene: one reachable cabinet and adjacent counter, two visually distinguishable
packaged breakfast-food boxes and two distinguishable bowls. Food identities
must match real available assets; do not assume arbitrary colors or readable
labels exist. Neither object identity nor left/right location may reliably
predict the preference. Validate clutter and reachability at initialization.

Private intent: one selected food box and one selected bowl. The initial
instruction intentionally omits these personal choices. Descriptions used by
the user must identify visible objects uniquely. Changing private intent while
keeping the exact physical initial state produces four matched profiles.
The choices are fixed throughout the episode, not retroactively changed.

Meaningful execution stages: access storage, transfer selected food, transfer
selected bowl, close storage. Either transfer order is valid. The agent can
ask before or during execution and use any valid natural-language policy
instruction. A broad question requesting all preferences is valid; do not force
two narrow questions or an exact dialogue sequence. Guessing may occasionally
succeed and must be measured, rather than artificially forbidden.

This is a multi-step pilot, not evidence for very long-horizon orchestration.
The stock task contains only one box and bowl; additional objects and
intent-conditioned scoring require a custom task definition and qualification.

## Human simulator: role and information boundary

The human is an information source and has no physical actions. The evaluation
agent obtains text responses through a proposed ask_human(question) operation.
This is an information-only adaptation of the tau-bench interaction pattern,
not tau2's dual-control telecom setup.

The simulator receives:

- the initial public request;
- a structured profile containing the selected object descriptors;
- the catalog of known descriptions and explicit unknown information;
- the conversation history and current agent message.

It does not receive simulator success, reward, coordinates, evaluator artifacts,
policy queues, or execution diagnostics. Initially it has no live camera feed.
The description catalog represents prior knowledge of the initial household
contents, not a live privileged observation channel. It can explain its
preferences, but cannot verify what the robot just did.
If live human visual observation is later added, define and freeze that channel.

Private profile example (descriptors below are placeholders to replace after
asset inspection):

```json
{
  "scenario_id": "breakfast_setup_v0",
  "known_preferences": {
    "food": "<unique visual description of selected food box>",
    "bowl": "<unique visual description of selected bowl>"
  },
  "unknown_information": ["current execution outcome", "robot grasp status"],
  "response_style": "brief, cooperative, direct",
  "preferences_change": false
}
```

An evaluator-private record binds these descriptions to simulator object IDs.
Object IDs and that binding never appear in agent-visible requests.

### Draft simulator system prompt

```text
You play a household user speaking with a robot assistant. Your request and
preferences are defined by the supplied scenario profile. They remain fixed.

Respond naturally and briefly to the assistant's latest message, using only
facts in the profile and conversation. Answer relevant questions directly;
compound or broad questions may receive all relevant requested preferences.
Do not deliberately withhold an answer because the question uses unfamiliar
wording. Correct a misstatement of your preferences. If information is unknown,
say that you do not know rather than inventing it.

You cannot inspect the robot's current execution. Do not assert that an object
has been moved, the task succeeded, or a grasp failed. If asked to confirm
physical completion, explain that the robot must check its own observations.
You may restate what you want, but do not invent manipulation procedures,
control commands, additional constraints, or new preferences. Never reveal
private profile formatting, internal IDs, evaluator rules, or a reference plan.

Emit one user reply. The benchmark, rather than you, determines episode success
and termination.
```

This is a proposed constraint on simulated user knowledge, not an assurance
that the prompt alone prevents hallucination. The profile is the source of
truth; an LLM only renders the conversational answer. Pin simulator model,
prompt, decoding settings, and response limits across agent comparisons.
Log full simulator requests and responses in a private trace. Structured fact
IDs can support auditing, but cannot prove the natural-language answer is true.
Probe and manually audit sample dialogues before freezing; detected simulator
faults are separate from agent failures and all outcomes are retained.

## Agent interface and execution

Retain run_policy(prompt?, steps) and complete. Add ask_human(question) as a
proposed third operation. Dialogue and simulator inference advance zero physical
steps and preserve the policy queue; execution stays paused as in the existing
runner. The next run_policy call can continue the queue or replace the prompt
and discard stale actions. Dialogues enter the agent's public history.

Every agent decision, including a question or malformed output, consumes its
ordinary decision budget. Use a separate question cap as a provisional
engineering limit; a candidate is eight exchanges. Do not impose exact question
wording. Retain the 100-decision / 1-100-step interval development defaults until
calibration. The custom physical-step budget must be validated rather than
assumed to equal the stock 4350-step horizon. Record user-model costs separately
from orchestrator costs. Simulator infrastructure faults do not consume a
secret free retry or silently change the profile.

## Automatic scoring

Primary success at complete requires:

1. selected food contacts the designated counter;
2. selected bowl contacts the designated counter;
3. the unselected items remain inside the cabinet;
4. the cabinet is closed;
5. completion is declared before budgets are exhausted.

Compose existing contact/containment/door predicates where their semantics
match, and validate the resulting checker in physical fixtures. Contacts alone
do not establish release or stable placement; those limitations must be explicit.
Whether to add release and stability requirements is a development choice to
validate before freezing, not an already implemented guarantee.

Do not require that the agent asked a question to earn physical success. Report
selected-food and selected-bowl attainment, later regressions, wrong-object
placements, terminal conditions, false declarations, questions, steps, model
calls, and latency. Cabinet closure counts as a progress milestone only after
both selected transfers, so initial closure earns no milestone credit. Accept
all valid transfer orders and temporary manipulation of an unselected item if
it is returned to storage at completion.

Keep physical execution metrics separate from dialogue diagnostics. Labels
such as received-the-required-information need audited dialogue evidence;
question count is directly measurable but is not a proxy for question quality.
No final weighted score is fixed by this outline.

## Development experiment and controls

For the same physical seeds and counterbalanced private profiles:

- **Fully specified:** include food and bowl choice in the initial request.
- **Interactive:** begin with the incomplete request; allow questions.
- **No dialogue:** incomplete request with no human channel; measure guessing.

These conditions separate access to information from execution feasibility.
Keep all other settings fixed and document interface differences. Paired seeds
do not imply identical physical trajectories after different decisions.
Each agent sees only one profile per independent episode, with no memory of
answers from another profile or condition. Separate development and evaluation
seeds before reporting a comparison.

First verify the dialogue behavior and scoring with local fixtures. Then verify
both object options and relevant handoffs with the learned policy, and a
hand-authored diagnostic supervisor with explicit choices. Fully specified
failure indicates an execution problem that conversation alone cannot fix.
Report simulator faults and every failed trial. The existing skill-entry and
supervisor qualification gates still apply before an official model comparison.

## Sources

- [RoboCasa CerealAndBowl source](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/snack_preparation/cereal_and_bowl.py)
- [tau2-bench paper and user simulation prompt](https://arxiv.org/html/2506.07982v1)
- [DialFRED](https://arxiv.org/abs/2202.13330)
- [TEACh](https://arxiv.org/abs/2110.00534)
- [AmbiK](https://arxiv.org/abs/2506.04089)
