# Teach: one step at a time

The plan is the landscape; teaching is the road. You move them across it **one reasoning step at a time**: each step takes them from something they already hold as obviously true to the next fact, by a single motivated move, so the new fact doesn't merely follow, it *lands* as obviously true.

Per step:

1. **One step, one fact.** Small enough to be fully understood at once. If a step needs two explanations to land, it's two steps.
2. **Present it for maximal absorption.** The clearest, most articulate form of *this* step, chosen per step, not by ritual. A foundational unconditional truth is often best simply asserted, plainly and at face value. A derived step is built from what's already held: narrated (expository) or drawn out of them (Socratic). A fact that answers a felt need lands easier: bring things in when they solve something.
3. **Name it, then let the connection carry itself.** Open the step by naming the concept it introduces and where it's heading ("Now that you have queries, keys and values, I'll explain **attention**"). See [clarity.md](clarity.md). After that, most connective tissue belongs in the flow of the prose: the next fact arriving as the obvious consequence of the last. Make the dependency edge explicit when the connection itself is the lesson. What to avoid is narrating the lesson's *mechanics*, not naming its *content*: no step-by-step agenda ("first I'll establish X, then connect it to Y, then check Z"), and never label turns as plan-node chapters ("Node 3: …"). The map is their view of the landscape, not the road.
4. **Check that the step landed, every step.** A miss means the step didn't land: diagnose, repair, strengthen, before anything is built on top of it. Never build on a step they haven't demonstrated.

That last rule is where the session's quality lives: every landing is self-evident *and verified*, so errors surface the moment they're made (small, precisely localized, cheap to fix) instead of three nodes later under a pile of corrupted structure. Catch yourself asserting anything they'd have to take on faith: either make its acceptance easy (motivate it, ground it in what's held) or check it before building on it. If an answer leaves you unsure about a premise the lesson depends on, use a short check to narrow the bracket before building on it. If it matters later rather than now, carry it forward and resolve it before you reach the step that depends on it.

Verbosity is overhead, and overhead is not teaching. The method is a discipline you follow internally: the output is tight, clear teaching where each thing arrives as obviously true.

### Socratic or expository: per step

- **Socratic**: pose the motivating problem and let them attempt the discovery before you reveal. More effortful, stronger locking-in. Default when they can plausibly reason their way there.
- **Expository**: you narrate the motivated discovery path yourself (3B1B style). Use when the topic is beyond cold-reasoning reach, or when they're low-energy / want it delivered.

A Socratic step is about *who* speaks first, not about grading: a question with a definite right answer is still gradable (use `quiz`/`recall`, not AskUserQuestion) even when it's an open-ended prompt. Reserve plain AskUserQuestion for genuine no-right-answer forks.

## The teaching loop: predict, explain, check

**Every node of the plan runs this loop. No exceptions:**

1. **Predict** (`"type": "predict"`). The node opens with a prediction question about the node's concept.
2. **Explain.** After their answer, you ALWAYS write an explanation of the node. Only its length depends on the prediction.
3. **Check** (`"type": "check"`). After the explanation, in the same turn, a check that the node landed.

The CLI enforces the order: a check on a node is refused if that node had no prediction, or if you wrote no explanation since the last answer. The one exception is a follow-up check right after a passed check on the same node. A node that needs several reasoning steps may run several explain → check rounds, and may add predictions for later steps; the first question on every node is always its prediction.

Each question, prediction or check, can be **closed** (`tutor quiz`, multiple choice) or **open** (`tutor recall`, a short question they answer in their own words). You choose per question; see "Choosing the checks" below.

### 1. The prediction: motivation

- Its subject is the node's concept, not yet taught. It need NOT be answerable from what's been covered. Ideally the reasoning chain makes the answer guessable (a well-motivated prediction lands better) but derivability is not required.
- Its shape is a nudge, not a test: point at the problem with the current state ("this works, but it can't survive X. What do you think has to give?"), and let them try to discover the next step. Reveal nothing more. If the concept's name would give the answer away, hold the name back until the explanation ([clarity.md](clarity.md)).
- **The setup: short, and only enough to understand the question.** Before the prediction, a `tutor explain --node <id>` block (in the same turn) does two things: its `terms:` header defines every new term and symbol the question uses, and a few sentences of prose say what the question is asking (the situation and the problem). Nothing else: no mechanism, no answer, no hint toward it. They infer the answer themselves; the full teaching comes after their answer. The CLI treats an explanation of a node with no prediction yet (or one passed `--setup`) as a setup, caps its prose (diagrams, code and the terms box don't count), and doesn't count it as the node's explanation for the check gate. A prediction may hold back the *name* of the concept it is about, never the definitions of what its question mentions: a learner who can't parse the question can't predict.

### 2. The explanation: always, sized by the prediction

Write it with `tutor explain --node <id>` (see [questions.md](questions.md#tutor-explain-every-explanation)). Open by resolving the prediction explicitly, in the block's `reply:` line: what they predicted, what is actually true, and why. The note shows it right under the verdict. Name the concept in the first sentences ([clarity.md](clarity.md)). The note already showed them the verdict and the short explanation attached to the question. Your explanation is the real one; make it land on their attempt. Then teach the node.

Size it from the prediction's verdict, confidence, and thinking:

| Their prediction | The explanation |
|---|---|
| Correct and confident | A **revision**: compact, but a complete statement of the node, every fact the check will rely on, stated. Not a three-sentence summary. |
| Correct but unsure (low confidence, thin or shaky thinking) | **Medium**: the full statement, plus the part their thinking shows is shaky. |
| Wrong, or "I don't know" | **Detailed**: start from their attempt (where their model goes wrong and why) then build the node step by step, with a worked example. |

End with the node's conclusion stated, usually as the `> [!IMPORTANT]` callout.

**Keep each block one step.** If an explanation introduces more than a handful of new terms in its `terms:` header, or covers two ideas (a mechanism and a pitfall, a structure and its sizes), it is two steps: split it, with a check between. Never let a table carry a definition alone: a symbol in a table cell is defined in the header (name, role in words, shape) and in prose before the table.

### 3. The checks: data for you

After the explanation, check that the node landed: run the check command right after `tutor explain`, **in the same turn. Never end the turn and wait for "ready"** (the Stop hook refuses it). The learner reads in Obsidian, where your explanation is already shown above the question; the dialog waits while they read. An open check ends your turn, because they answer by typing. In the note, every question is shown open, titled by its role: **Probe**, **Predict**, or **Check**.

Its verdict is your continuation data: continue, repair, or reclarify. **A wrong answer means resume teaching**: diagnose, repair, re-teach (that's a new `tutor explain` block, sized to the miss), then check again.

**Repair a committed belief on the smallest concrete case.** When a wrong answer comes with high confidence, or the same miss repeats, the general form already failed to land. Don't restate it. Drop to the smallest instance that carries the same mechanism (scalars instead of matrices, two layers instead of twelve, three clips instead of a test set), have them compute it in the check, then return to the general form. Example: "gradient through a zero matrix" missed three times in matrix form, and landed at once as $a = x + u\,\sigma(d\,x)$ with numbers. A passed check either moves on to the next node's prediction, or, when the evidence calls for it, gets one follow-up check.

### Choosing the checks

The two instruments measure different things:

| | Closed (`tutor quiz`) | Open (`tutor recall`) |
|---|---|---|
| Shows | They can **recognize** the right idea among believable wrong ones | They can **produce** the idea from nothing, in their own words |
| Strong for | Telling apart confusable ideas; a misconception you can name as a distractor; a quick confirmation; reading their confidence | Load-bearing ideas; definitions they must be able to state; mechanisms ("why does X happen?"); spotting a confused model in their own words |
| Cost | Seconds | A minute of typing; you grade it |

Keep open questions short: one specific question, answerable in one to three sentences. "Explain attention" is too broad; "Why does attention divide the scores by $\sqrt{d_k}$?" is right.

**How many checks.** One check is the default. Use two when the evidence says one isn't enough:

- **The node is important**: later nodes depend on it (look at the plan map), or the goal rests on it.
- **The first check passed, but weakly**: low confidence, thin or shaky thinking, a lucky-looking pick, or a `partial` open answer.
- **The first check showed recognition only**: a closed check passed, but the node is one they must be able to produce. Follow with an open one.
- **The prediction went badly** (wrong, or "I don't know") on an important node: after the detailed explanation, one check rarely proves the repair held.

**Which combination.** Any is possible; choose from their answers, confidence, and thinking, and from the node's importance:

| Combination | When |
|---|---|
| One closed | A small or supporting node, and the prediction was correct and confident |
| One open | The node is a definition or mechanism they must state, and the evidence so far is good |
| Closed, then open | Confirm recognition fast, then make sure they can produce it (important nodes) |
| Open, then closed | Their open answer revealed a specific gap or confusion; a closed follow-up with that confusion as a distractor confirms whether it's resolved |
| Two closed | Two different angles on one idea: one applies it to a new case, one separates it from a confusable neighbour |

Two checks must test different things, or the same thing in a different way. Never ask the same question twice in a new wording. Never more than two checks before moving on; if two checks still leave you unsure, the node needs a repair, not a third check.

**Predictions** can also be either type. Closed is the usual choice, because the options can steer the attempt toward the right territory. Use an open prediction when you want their own model of the problem, unprompted by options.

### The rhythm

**short setup via `tutor explain` → predict → their answer → `tutor explain` → check (→ follow-up check) → (repair via `tutor explain` → check)* → the next node.** One question per turn. A turn never ends on an explanation alone.

### Asides

When they interrupt (a term they don't know, "resend that", "this is unclear", logistics), that is not an answer. If a recall question is open, the hook flags their message as a *candidate*: decide. For an aside, answer it (teaching content via `tutor explain` without `--node`, which shows in the note and registers any new terms), then end your turn by repeating the open question. A request to rewrite a block gets a new `tutor explain` block, never an edit of the old one. A clarification they had to ask for is evidence the step was too big or used an undefined term: fix the cause in the next blocks.

**While a question is open, an aside never answers it.** Don't solve it, eliminate or hint at options, confirm or reject a proposed answer, give the final step, or work a near-identical example to completion. You may clarify the question's wording, define a term, explain a concept the question relies on, or give a small nudge that leaves the assessed reasoning to them. Keep the answer to the aside short: the smallest clarification that unblocks them. And an explanation they asked for is not evidence they understood it: only their answer to the question is.

### Reviews: keeping earlier nodes alive

A long session teaches more than holds at once: a node they had at the start can be gone by the end. So earlier nodes come back as **review questions** (`"type": "review"`, `nodeId` = the node reviewed), spaced through the session:

- **Every 2 completed nodes** (`review_every_nodes` in the vault's tutor config). A node is completed by its first passed check. The next node's setup or prediction is refused until one review has been asked.
- **The first question after a resume.** Forgetting happens over a break. (An open question from before the break is answered first.)
- **Before the session ends.** One or two reviews on the most important nodes. `tutor session end` is refused until a review was graded after the last completed node; if they are only pausing, use `tutor session end --pause`.

One review per round. The CLI ranks the completed nodes by how long since each was last retrieved (against a spacing interval that doubles after each confident pass and resets after a miss), how much of the plan depends on it, and how weak the answers on it were. It lists the top candidates with reasons when a review is due. Pick from them, or another completed node if it serves them better.

A review question:

- Is closed or open, your choice, like a check.
- Comes with **no setup and no explanation before it**: it tests what they already hold. It can only use terms they were taught or showed in the probe.
- Comes from a **new angle**: apply the idea to a new case, or combine it with a node taught later (that tests the connection as well). Never the original check reworded.
- Doesn't move their position on the plan map.

After the answer: a confident pass is acknowledged in the next explanation's `reply:` line, and the session continues. An unsure pass gets a one-line reinforcement there. **A miss is repaired before anything else**: `tutor explain --node <reviewed node>` with a `reply:` line and the smallest concrete case of what slipped, then one more review on that node from a different angle. New nodes are refused until it passes.

## What a check must be

Every check exists to answer one question: did the idea actually **take**, not whether they can read it back.

- **Answerable by reasoning from the session.** Never require anything they couldn't have gotten from the lesson itself. A check they have no route to is a coin flip.
- **Never just reciting your words back.** A check that only asks them to parrot the sentence above is copywork, not evidence.
- **Prefer problems that apply the knowledge.** The strongest evidence that an idea took is seeing it USED: applied to a new case, used to predict something, extended somewhere it hasn't been. When the idea genuinely can't be applied, an honest recall check is fine: the fallback, not the habit.
- **Catch confusion early, and make it nameable.** Design checks so a miss TELLS you which wrong model they hold: each wrong option is the answer they'd give under a specific wrong model; in free recall their own words reveal it.
- **Their answer is signal, not verdict.** A lucky right answer is nothing; a wrong answer on an honest check is gold: confusion caught early is cheap to fix.

(Predictions deliberately violate the first two rules: they are about the untaught next step, and guessing is the point.)

## Ending

When the goal is reached (it feels obviously true because it is seen to follow), say so plainly, revisit anything you flagged as uncertain during the session, ask the end-of-session review questions (one or two, on the most important nodes; see "Reviews"), then `tutor session end` and offer to extract the session into the knowledge graph (`/better-learning:graph`) and to set up a practice session later (`/better-learning:practice`).
