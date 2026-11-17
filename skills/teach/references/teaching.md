# Teach: one step at a time

The plan is the landscape; teaching is the road. You move them across it **one reasoning step at a time**: each step takes them from something they already hold as obviously true to the next fact, by a single motivated move, so the new fact doesn't merely follow, it *lands* as obviously true.

Per step:

1. **One step, one fact.** Small enough to be fully understood at once. If a step needs two explanations to land, it's two steps.
2. **Present it for maximal absorption.** The clearest, most articulate form of *this* step, chosen per step, not by ritual. A foundational unconditional truth is often best simply asserted, plainly and at face value. A derived step is built from what's already held: narrated (expository) or drawn out of them (Socratic). A fact that answers a felt need lands easier: bring things in when they solve something.
3. **Name it, then let the connection carry itself.** Open the step by naming the concept it introduces and where it's heading ("Now that you have queries, keys and values, I'll explain **attention**"). See [clarity.md](clarity.md). After that, most connective tissue belongs in the flow of the prose: the next fact arriving as the obvious consequence of the last. Make the dependency edge explicit when the connection itself is the lesson. What to avoid is narrating the lesson's *mechanics*, not naming its *content*: no step-by-step agenda ("first I'll establish X, then connect it to Y, then check Z"), and never label turns as plan-node chapters ("Node 3: …"). The map is their view of the landscape, not the road.
4. **Check that the step landed, every step.** A miss means the step didn't land: diagnose, repair, strengthen, before anything is built on top of it. Never build on a step they haven't demonstrated.

That last rule is where the session's quality lives: every landing is self-evident *and verified*, so errors surface the moment they're made (small, precisely localized, cheap to fix) instead of three nodes later under a pile of corrupted structure. Catch yourself asserting anything they'd have to take on faith: either make its acceptance easy (motivate it, ground it in what's held) or check it before building on it. If an answer leaves you unsure where their edge sits on a strand, re-bracket it with a short run of questions before choosing the next step.

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

The CLI enforces the order: a check on a node is refused if that node had no prediction, or if you wrote no explanation since the last question. A node that needs several reasoning steps may run several explain → check rounds, and may add predictions for later steps; the first question on every node is always its prediction.

### 1. The prediction: motivation

- Its subject is the node's concept, not yet taught. It need NOT be answerable from what's been covered. Ideally the reasoning chain makes the answer guessable (a well-motivated prediction lands better) but derivability is not required.
- Its shape is a nudge, not a test: point at the problem with the current state ("this works, but it can't survive X. What do you think has to give?"), and let them try to discover the next step. Reveal nothing more. If the concept's name would give the answer away, hold the name back until the explanation ([clarity.md](clarity.md)).
- Write the prose the prediction needs (the setup, the problem) before it, in the same turn.

### 2. The explanation: always, sized by the prediction

Open by resolving the prediction explicitly: what they predicted, what is actually true, and why. Name the concept in the first sentences ([clarity.md](clarity.md)). The note already showed them the verdict and the short explanation attached to the question. Your explanation is the real one; make it land on their attempt. Then teach the node.

Size it from the prediction's verdict, confidence, and thinking:

| Their prediction | The explanation |
|---|---|
| Correct and confident | A **revision**: compact, but a complete statement of the node, every fact the check will rely on, stated. Not a three-sentence summary. |
| Correct but unsure (low confidence, thin or shaky thinking) | **Medium**: the full statement, plus the part their thinking shows is shaky. |
| Wrong, or "I don't know" | **Detailed**: start from their attempt (where their model goes wrong and why) then build the node step by step, with a worked example. |

End with the node's conclusion stated, usually as the `> [!IMPORTANT]` callout.

### 3. The check: data for you

Posed AFTER the explanation, in the same turn, right below it. **Don't end the turn and wait for "ready".** The learner reads in Obsidian, where your explanation sits above the question; the terminal dialog waits while they read. In the note, checks arrive **collapsed** ("Check your understanding") so they don't distract from the reading; predictions arrive open.

Its verdict is your continuation data: continue, repair, or reclarify. **A wrong answer means resume teaching**: diagnose, repair, re-teach (that's a new explanation, sized to the miss), then check again. A correct answer moves on to the next node's prediction.

### The rhythm

**predict → their answer → explanation + check → their answer → (repair + check)* → the next node's predict.** One question per turn. Never call a question mid-explanation: finish the thought, then fire.

## What a check must be

Every check exists to answer one question: did the idea actually **take**, not whether they can read it back.

- **Answerable by reasoning from the session.** Never require anything they couldn't have gotten from the lesson itself. A check they have no route to is a coin flip.
- **Never just reciting your words back.** A check that only asks them to parrot the sentence above is copywork, not evidence.
- **Prefer problems that apply the knowledge.** The strongest evidence that an idea took is seeing it USED: applied to a new case, used to predict something, extended somewhere it hasn't been. When the idea genuinely can't be applied, an honest recall check is fine: the fallback, not the habit.
- **Catch confusion early, and make it nameable.** Design checks so a miss TELLS you which wrong model they hold: each wrong option is the answer they'd give under a specific wrong model; in free recall their own words reveal it.
- **Their answer is signal, not verdict.** A lucky right answer is nothing; a wrong answer on an honest check is gold: confusion caught early is cheap to fix.

(Predictions deliberately violate the first two rules: they are about the untaught next step, and guessing is the point.)

## Ending

When the goal is reached (it feels obviously true because it is seen to follow), say so plainly, revisit anything you flagged as uncertain during the session, then `tutor session end` and offer to extract the session into the knowledge graph (`/better-learning:graph`) and to set up a practice session later (`/better-learning:practice`).
