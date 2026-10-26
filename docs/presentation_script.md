# OrcaBench: presentation script

About **11 minutes** of speaking, plus questions. Text in quotes is what to say; the notes under it are for you. Every
number comes from our runs (`docs/final_results.md` has the sources). A glossary of every term is at the end; read it
once before you present.

---

## 0. The one-sentence version (memorize this)

"We built a benchmark that asks whether an AI language model can supervise a robot well enough to make it finish
kitchen tasks faster and more reliably, and in our tests, three different models all did worse than a simple rule that
just waits a fixed time and then says 'done'."

---

## 1. Opening (30 s)

"Robots are now often controlled by two AI systems working together. One is a *robot policy*: a neural network that
looks at camera images and directly moves the arm. It is fast, but it makes mistakes and has no idea when it has
failed. The other is a large language model, like Claude, which is smart and can reason about what it sees, but is
slow. A popular idea is to put the language model in charge as a supervisor. Our question is simple: **does that
actually help?**"

## 2. What inspired us (1 min)

"Most published evaluations of these supervisor setups test them on tasks where the robot policy fails on its own. On
those tasks, the supervisor can only help, so stepping in is never punished. But a real supervisor also has to know
when to stay out of the way.

We saw this in our own early experiments. When we let Claude Opus supervise a robot on tasks the robot could already
do alone, the pair failed 14 of 34 times, against a 3% failure rate for the robot alone. And when we looked at why, it
almost never broke the robot. It said 'done' too early, between 12 and 48 steps before the task was actually
finished.

So we decided to measure the skills that matter for a supervisor: **when to interrupt, how often to check in, and
when to declare the task finished**, and to make speed count, because a slow supervisor wastes time."

Notes: the course asked for a benchmark of a capability that current benchmarks measure poorly. Ours scores both
directions, helping and hurting, and charges for time.

## 3. The setup (2 min)

**The world.** "Everything runs in RoboCasa, a realistic kitchen simulator built on the MuJoCo physics engine. Each
*episode* is one attempt at one task, in one kitchen layout. We used four kitchen layouts, which we call scenes."

**The tasks.** "We chose seven tasks. Three are tasks the robot policies were trained on and usually manage alone:
open a cabinet, close the fridge, and move an item from the counter to the stove. On these, the right move for a
supervisor is mostly to leave the robot alone and declare 'done' at the right moment. The other four are harder,
multi-step tasks the policies never trained on, like making iced lemonade or moving a pan of vegetables from the stove
to a plate. One of them has a hidden timer: the vegetables cool once the pan leaves the stove, so the task fails if
the supervisor takes more than 30 seconds after that."

**The robot policies.** "We did not train anything. We used three official, publicly released robot policies of
different ability, so the supervisor has to figure out which one it is dealing with:
- GR00T, NVIDIA's robot model, the version trained on all tasks. It's good on the trained tasks and almost never
  solves the new ones.
- A GR00T version trained on only part of the data. It's weaker on trained tasks, but the only one that occasionally
  solves a new task.
- π0.5, from a different company with a different architecture. It's about as good as GR00T on the trained tasks and
  almost never solves the new ones either."

**The supervisor.** "The language model sees what a human supervisor would see: three camera images, a few snapshots
from since it last looked, the robot's joint positions and the task description. Each time, it makes one of three
choices:
- **let the robot keep going** for a number of steps it picks, which is also how long until it looks again;
- **restart the robot** with a new or repeated instruction;
- **declare the task done.**

It never moves the arm itself."

**Sessions.** "Each supervisor runs a *session* of 21 episodes: every task with every robot, in one continuous
conversation. The robots are hidden behind letters like K, R and T, shuffled each session, and after each episode the
model learns whether it succeeded. So a good supervisor could learn that 'robot K is reliable, so leave it alone'."

## 4. Making time count: the score (1 min)

"In the simulator, the world pauses while the model thinks, so being slow would be free. To make speed matter, we
charge every model response a fixed number of seconds on the task clock. That's the model's real measured median
response time: 4.7 seconds for Claude Opus, 1.8 for Claude Sonnet. Each task also has a deadline.

The score for an episode is: **zero if the task wasn't actually done; otherwise, the fraction of the deadline left
over.** Declaring 'done' when the task isn't done scores zero, so guessing early never pays."

Notes: value = success × max(0, 1 − charged seconds / deadline). The charge is measured once and frozen, so a model
can't look faster by thinking less during the run.

## 5. The baselines: what we compare against (1 min)

"We compare each model against simple, mechanical supervisors that never look at anything:
- **Always-defer:** let the robot run and never interrupt. Every single model episode has an always-defer 'twin' on
  the same computer, in exactly the same starting state. We check that with a fingerprint of the simulator state, so
  the comparison is apples to apples.
- **The fixed rule:** wait exactly T steps, then declare 'done'. We pick the best T for each robot and task, using the
  *other* kitchens' results, never the one being tested. This is our main yardstick: if a smart supervisor can't beat
  'wait T steps, then say done', it isn't adding value.
- **Restart schedules:** restart the robot every 50 or 100 steps. This tests whether the model's interruptions are
  better timed than mechanical ones."

**Our main number** is the *regret*: the fixed rule's score minus the model's score, on the same episode. "Positive
regret means the simple rule did better. Zero means the model matched it. Negative means the model beat it."

## 6. How the trials were run (1 min)

"We wanted this to be a fair, honest test, so:
- **We wrote down every rule before seeing any results:** which tasks, which robots, the time charges, the hidden-timer
  limits and how to handle problems. All of it is in a public decision log.
- **We froze the code.** The final runs used one tagged version, and every episode records a fingerprint of the code,
  so nothing changed mid-experiment.
- **Each model got its own GPU computer in the cloud:** 84 episodes for the model plus its 84 always-defer twins, on
  the same machine, because starting states differ slightly between machines.
- **Three of us split the work:** I did scoring and analysis, Ranveer ran the robot policies and Opus's machine, and Ty
  built the supervisor sessions and ran Sonnet's machine.
- **After the main runs,** we added an open-weight model, Kimi K3, through an inference service called Sail, as a
  bonus comparison."

Notes: the final experiment cost about $46 of GPU time and about $14 of model API calls.

## 7. Results (2 min)

"Here is the main result."

| Supervisor | Regret (positive = simple rule better) | 95% confidence interval | Episodes |
|---|---|---|---|
| Claude Opus 5.5 | **0.053** | 0.007 to 0.105 | 63 |
| Claude Sonnet 5.5 | **0.071** | 0.028 to 0.119 | 83 |
| Kimi K3 (open-weight, add-on) | **0.070** | 0.014 to 0.134 | 42 |

"All three numbers are positive, and none of the confidence intervals reaches zero. So **every model did measurably
worse than the simple 'wait T steps, then declare' rule.** The intervals overlap, so we can't say which model is
best."

"What did the models actually do?
- **Opus declared 'done' in every single episode,** and was right only 8 times out of 63. On the same episodes, the
  robot left alone finished the task 22 times.
- On the three easy tasks, the robot alone finished **21 of 27**; with Opus supervising, **8 of 27**. Opus kept
  stopping the robot before it had finished.
- **Sonnet failed differently.** It was right only 2 times out of 84. In about half the episodes it never declared
  'done' before time ran out, and in most of the rest it declared too early.
- **Kimi K3** was right 7 times out of 42, against 15 for the robot alone, and checked in almost twice as often as
  Opus: 8.4 times per episode against 4.7.
- **The restart schedules did no better than leaving the robot alone:** 22 and 23 successes against 22. Restarting
  doesn't rescue these failures."

## 8. Whose fault is it, the models' or our design's? (2 min)

"This is the most important question. We think the honest answer is: **mostly the models, but our design makes the
gap look bigger than it is.**

**Evidence it's the models:**
- The main failure is judgment: saying 'done' when the task isn't done. Nothing in our design forces that. The models
  were told that a wrong 'done' scores zero, and the fixed rule shows that simply waiting longer would have worked.
- It's the same failure we saw in our first experiments, with a different setup, before any time charge existed. Opus
  then failed only by declaring early.
- For Kimi K3, the one model we've analyzed for learning, there was no consistent improvement across a session. It
  got slightly better with two of the robots and worse with the third, over just 7 episodes each.

**Evidence it's partly our design:**
- **The time charge is harsh on short tasks.** The tasks where the robot succeeds are also the shortest. Four Opus
  responses use up 63% of the 30-second deadline on the stove task. For Kimi K3, we rescored without any time charge:
  the gap shrinks from 0.070 to 0.018 (an average, without its own confidence interval). So a lot of the gap is about speed, not just judgment.
- **The yardstick is strong.** The fixed rule's waiting time is tuned on our own data from other kitchens. A real
  deployment wouldn't have that tuning data.
- **Seeing 'done' is genuinely hard here.** The simulator's success check can lag what the camera shows by about 20
  steps. In our first experiments, the models never recognized from images when hidden-state tasks, like rinsing or
  the microwave, were finished. The cameras are also small, 256 by 256 pixels.
- **The hard tasks gave the supervisors nothing to win.** We tested whether perfect step-by-step instructions could
  rescue the policies on the new tasks, and they didn't help: 3 successes with the instructions against 4 without,
  over 76 paired tries. So on four of seven tasks every
  supervisor scores zero, and the benchmark ends up measuring patience and declaring, not rescuing."

"So the takeaway is: **today's language models don't reliably know when a robot has finished a task, and they're
worse at it than a timer.** That's a real limitation worth measuring. But we shouldn't claim that supervision is
useless in general."

## 9. Limitations and what we'd do next (45 s)

"Some honest limits:
- **Small samples:** three kitchen layouts per model.
- **One scene dropped:** in one layout, one task's starting state came out randomly different between runs, so we
  excluded that layout for every model, by a rule we fixed in advance.
- **The open-weight model is a bonus:** it ran after the main experiment, on a different computer, and for only two
  kitchens.
- **One restart baseline didn't run,** because no GPU was available at the end.

Next, we'd want:
- tasks where intervention can actually help;
- a 'look closer' action for checking whether a task is really done;
- more kitchens and repeats;
- a direct statistical comparison between models on the same kitchens."

## 10. Close (20 s)

"To sum up: we built a benchmark that charges a supervisor for its time, rewards it only for real success, and
compares it against a simple timer on exactly the same episodes. Three state-of-the-art models all lost to the timer,
mainly by saying 'done' too early. Thank you, and we're happy to take questions."

---

## Likely questions, with answers

- **"Is the simple rule cheating?"** "It's tuned on other kitchens, never the one being tested, and it never sees the
  episode. But yes, it benefits from our data. That's one reason we call the result a lower bound on how useful
  supervision is in this setting, not a final verdict."
- **"Why charge for time at all?"** "Because in the simulator the world freezes while the model thinks. On a real
  robot, a slow supervisor wastes real time. Without a charge, slowness would be free. We measured each model's actual
  speed and froze it before the runs."
- **"Would the result change without the time charge?"** "For Kimi K3, the average gap shrinks from 0.07 to 0.02. In our early
  Opus experiment, without a charge, Opus was statistically tied with the rule. So speed is a big part of it, but not
  all of it: the models still say 'done' wrongly most of the time."
- **"Which model is best?"** "We can't say. The confidence intervals overlap, and the models ran on different
  computers. We compare them only through each one's own paired twins, never raw scores."
- **"Why not fine-tune or train the models?"** "The benchmark is about supervisors as they come, and the project rules
  forbid training, so the robot policies are the official public versions, unchanged."
- **"What's a confidence interval here?"** "We resampled the task-and-kitchen groups thousands of times. 95% of the
  resampled averages fell in that range. Because the range doesn't include zero, the gap is unlikely to be luck."
- **"Why did one kitchen get dropped?"** "In layout 1003, the pan-transfer task sometimes builds into one of two
  slightly different starting states. Our software then can't pair the model's episode with its twin, and stops the
  session after two such mismatches. We had fixed in advance that only complete sessions count, so we dropped that
  layout for every model."
- **"What did it cost?"** "The final runs cost about $46 of cloud GPU time and about $14 of model API calls."

---

## Glossary (read before presenting)

- **Robot policy / VLA (vision-language-action model):** a neural network that takes camera images and an instruction
  and outputs arm movements. Ours: GR00T N1.5 (NVIDIA), two versions, and π0.5 (Physical Intelligence).
- **Checkpoint:** a saved, trained version of a model. We used official released checkpoints.
- **Supervisor / orchestrator:** the language model that watches and decides. Ours: Claude Opus 5.5, Claude Sonnet
  5.5, Kimi K3.
- **RoboCasa / MuJoCo:** the kitchen simulator, and the physics engine underneath it.
- **Episode:** one attempt at one task. **Step:** one control tick; 20 steps = 1 second of robot time.
- **Scene (seed):** a kitchen layout, set by a number (1000-1003).
- **Trained ("leave-alone") vs unseen tasks:** tasks the policies were trained on, where leaving them alone is usually
  right, vs new multi-step tasks.
- **Call charge:** seconds added to the task clock for each model response (Opus 4.74 s, Sonnet 1.76 s, Kimi 5.92 s),
  measured by replaying 27 recorded situations and taking the median.
- **Deadline:** each task's time budget (30 s for the stove task, 202 s for reheating a waffle).
- **Value (score):** zero for failure, otherwise the share of the deadline left.
- **Always-defer twin:** the same episode run with no supervisor, from the identical starting state.
- **Fixed rule ("declare at step T"):** a timer; T is chosen on the other kitchens (that's what "held-out" means).
- **Regret:** the fixed rule's score minus the model's. Positive = the model did worse. **Paired** means compared on
  the same episode.
- **False completion:** the model said "done", but the task wasn't done.
- **Bootstrap 95% interval:** a range for the average, from resampling the data; if it excludes 0, the difference is
  unlikely to be chance.
- **Freeze / tag:** locking the code and settings before the final runs, so nothing can be tuned after the fact.
- **Pod:** a rented cloud computer with a GPU.
- **Story timer:** a hidden time limit tied to a story (the vegetables cooling).
