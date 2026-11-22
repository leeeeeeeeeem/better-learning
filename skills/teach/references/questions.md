# Graded questions: the craft, the mechanics, the reading

## Mechanics

### `tutor quiz` (multiple choice)

```bash
tutor quiz <<'EOF'
{"type": "check", "nodeId": "chain-rule",
 "question": "If $f$ scales small changes by $3$ near $a$, and $g$ scales by $2$ near $f(a)$, how does $g \\circ f$ scale near $a$?",
 "details": "optional extra context",
 "options": ["$6$", "$5$", "$\\tfrac{3}{2}$"],
 "correct": "$6$",
 "explanation": "Each scaling applies to the output of the previous one, so they multiply: $2 \\cdot 3 = 6$."}
EOF
```

- 2–3 options (AskUserQuestion has 4 slots; the fourth is always "I don't know"). `correct` is the exact text of the correct option, or a list for multi-select (`"multiSelect": true`).
- Write `explanation` BEFORE `correct` in your head: reason it out first, then commit.
- Probe phase: omit `type`, `nodeId` and `uses`. Teach phase: all three required. `uses` lists every term and symbol the question, its details and its options rely on, e.g. `"uses": ["LoRA", "$W_{up}$", "gradient"]`. Each must be registered (taught in a `tutor explain` block, or shown held in the probe); the CLI also scans the text for symbols ($W_{up}$, $\alpha$, `code_names`) and refuses any that were never defined.
- The CLI stores the key, shuffles, and prints an AskUserQuestion payload: **call AskUserQuestion with exactly that input.** Options are labelled A/B/C. Write the question and options in LaTeX as usual: the note shows the LaTeX, and the CLI converts the math to Unicode for the dialog, which doesn't render LaTeX (the terminal, and the Claude app over remote control). A second question asks their confidence. They can attach their thinking as a note on their selection, or type in "Other".
- A hook grades the answer against the key and returns: verdict, what they picked, the correct answer, confidence, thinking. The note shows them the verdict, the correct answer and your explanation. Never repeat the explanation verbatim; build on it.

### `tutor recall` (free recall)

```bash
tutor recall <<'EOF'
{"type": "check", "nodeId": "chain-rule",
 "question": "Explain why the derivative of a composition is a product.",
 "answer": "THE FULL committed answer in your own words, reasoning included."}
EOF
```

Then end your turn with the question as your message, copied exactly from the CLI output (one short line before it is fine). The learner may be on a phone, where the note isn't visible; the note mirror drops this copy, since the note already shows the question.

Each message they send while it is open is a **candidate**; the hook reminds you of your commitment and lists earlier candidates. Decide what the message is:

- **The answer**, or a corrected or completed version of an earlier one: grade strictly against the commitment (**never revise it after seeing their words**) with `tutor grade q7 --verdict correct|partial|incorrect|dontknow --feedback "..."`. The grade records the latest candidate; when the answer is spread over several messages, pass `--answer "<their full answer>"`. Then write your reaction. A near-miss is `partial`: name exactly what they got and what they missed. If they genuinely don't know, that's `dontknow`: a gap, not a wrong answer.
- **An aside** (a question, "resend", a complaint, logistics): don't grade. Answer it, then repeat the open question.
- **"Skip it"**: `--verdict skipped`.

### Plain AskUserQuestion

For everything with no right answer. They can always pick "Other" and type. If you recommend an option, list it first with "(Recommended)". It's mirrored into the note automatically. You write this payload yourself, so write any math in it in Unicode (`√dₖ`, `α`, `x²`), not LaTeX: the dialog doesn't render LaTeX.

### `tutor explain`: every explanation

```bash
tutor explain --node lora <<'EOF'
terms:
- LoRA :: low-rank adaptation: a trainable update $BA$ added to a frozen weight matrix $W$
- $A$ :: the down-projection of the update, an $r \times d$ matrix, initialised random
- $B$ :: the up-projection of the update, a $d \times r$ matrix, initialised to zero
uses: gradient, frozen, linear layer
---
## LoRA

**LoRA** adds a trainable product $BA$ to a frozen $W$ ...

> [!IMPORTANT]
> ...
EOF
```

- Markdown body after the header, LaTeX written plainly (the quoted heredoc keeps single backslashes; this is not JSON).
- `terms:` defines everything new the body uses, one line each: `- term :: definition`, with the name, its role in words, and its shape for a matrix or tensor. The note shows these first, in a **New terms** box. A symbol defined only by its shape is not defined.
- `uses:` lists what the body relies on that the learner already holds. Each must be registered; `uses: none` only if it relies on nothing.
- The CLI scans the body for symbols and code names and refuses any that are neither registered nor in `terms:`.
- `--node <id>` for setups, explanations and repairs (it satisfies the check gate). Without `--node`, it is an aside (a clarification), allowed while a question is open.
- It writes into the note immediately, after anything queued before it. Prose in the chat or in your thinking does not count for the check gate.

A check is refused when no `tutor explain` block for its node exists since the last answer, except for a follow-up right after a passed check on the same node.

### The term registry

`tutor terms list [--all]` shows what is registered (`--all` adds earlier sessions). `probe-done` registers what the probe showed held (`held`). To register terms after the fact (a resumed session that predates the registry, or a held term the probe showed but you didn't list), use:

```bash
tutor terms add <<'EOF'
{"source": "probe", "evidence": "q3, q7", "terms": [{"term": "system call"}, {"term": "evdev"}]}
EOF
```

`source` is `probe` (shown held: cite the question) or `taught` (cite where it was taught, with a definition per term). Register only what the record shows.

### Order

- **Before a question:** `tutor explain` (setup or explanation), then `tutor quiz`/`tutor recall`, then for a closed question AskUserQuestion, all in one turn. Don't write prose between `tutor quiz` and AskUserQuestion.
- **Plain AskUserQuestion:** if the learner must read something first, put it in a `tutor explain` block.
- **CLI blocks** (recall question, grades, plan map, problem, probe assessment) are placed automatically after the prose that preceded the command. The command prints a `⟦b3⟧` marker for this; ignore it.

### One question per turn

Ask, then end your turn. Their answer determines the next. A second question while one is open is refused.

## Terms in questions

A question uses exactly the terms the teaching used ([clarity.md](clarity.md)). A check that says "coefficients" when the explanation said "weights" tests whether they can map the synonym, not whether they understood. The same holds for every option and for the explanation shown after answering.

## The option craft

The giveaway is never the distractors' wrongness, it's **asymmetry**: the correct option carrying its reasoning while the others are bare, or key-term bolding that flags it. Don't audit afterwards. Build evenness in by construction:

1. **Every option is a bare claim: zero "why" in any of them.** All reasoning goes in `explanation`, shown only after they answer.
2. **Write the correct claim first, then mutate it into each distractor.** Take one specific misconception or easily-confused neighbour and state what someone holding it would claim: same skeleton, same grain, same register. Every option is "the claim under some belief"; the correct one is the claim under the correct belief.
3. **Each distractor is a real, BELIEVABLE error**: the answer they would actually give under a specific wrong model, never obviously wrong on sight. An option a cold reader eliminates instantly is wasted: their pick is diagnostic only when the wrong model is what selects it.
4. **No asymmetric bolding.** Bold nothing, or bold the parallel term in every option.

If, reading the finished set cold, you can tell which is right without knowing the material, regenerate, don't patch.

**LaTeX everywhere**: the question, every option, every explanation. Anything expressible as math goes in math, even single variables (`$x$`).

## Reading the answer

### Thinking: their understanding, out loud

Every instrument carries a thinking channel (the note on their selection, the "Other" text, their free-recall words, any message). These are the session's **primary data**: their framing, their mental models, the nuances, where their picture differs from the real one. Read every word and measure what it reveals, not just the answer it carries. One answer is one bit; the thinking is the picture. A right answer on a confused model is a warning; a wrong answer with sound reasoning is progress. Your model of them updates on every submission: what to ask next, how to phrase it, whether the plan itself is wrong about them. Their thinking is often dictated speech: read it leniently for transcription noise.

### Confidence

Every quiz answer carries their stated probability (25/50/75/95%) that their pick is correct. Read it against the verdict:

- 50 is a coin flip. 95 claims certainty; 25 claims real doubt. For an n-option question chance is 1/n: confidence at or below chance means they believe their pick is wrong: a forced choice they distrust. Treat it as honesty, not error.
- **Correct + high:** solid. Move on.
- **Correct + low:** fragile knowledge or a lucky guess. One reinforcing touch, not celebration.
- **Wrong + high:** the strongest signal you can receive: a committed misconception. Name the crack, probe it, re-teach around it.
- **Wrong + low:** a shaky near-miss or an honest gap. A small correction usually suffices.
- **"I don't know":** no confidence; they declined to guess. A genuine gap, never a wrong answer.
