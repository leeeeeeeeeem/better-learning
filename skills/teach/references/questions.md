# Graded questions — the craft, the mechanics, the reading

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
- Probe phase: omit `type` and `nodeId`. Teach phase: both required.
- The CLI stores the key, shuffles, and prints an AskUserQuestion payload: **call AskUserQuestion with exactly that input.** Options are labelled A/B/C; the full (LaTeX) text is in the descriptions and rendered in the note. A second question asks their confidence. They can attach their thinking as a note on their selection, or type in "Other".
- A hook grades the answer against the key and returns: verdict, what they picked, the correct answer, confidence, thinking. The note shows them the verdict, the correct answer and your explanation — never repeat the explanation verbatim; build on it.

### `tutor recall` (free recall)

```bash
tutor recall <<'EOF'
{"type": "check", "nodeId": "chain-rule",
 "question": "Explain why the derivative of a composition is a product.",
 "answer": "THE FULL committed answer in your own words, reasoning included."}
EOF
```

Then end your turn with one short line (the question is already in the note). Their next message is the answer; the hook reminds you of your commitment. Grade strictly against it — **never revise it after seeing their words** — with `tutor grade q7 --verdict correct|partial|incorrect|dontknow --feedback "..."`, then write your reaction. A near-miss is `partial`: name exactly what they got and what they missed. If they genuinely don't know, that's `dontknow` — a gap, not a wrong answer.

### Plain AskUserQuestion

For everything with no right answer. They can always pick "Other" and type. If you recommend an option, list it first with "(Recommended)". It's mirrored into the note automatically.

### One question per turn

Ask, then end your turn — their answer determines the next. A second question while one is open is refused.

## The option craft

The giveaway is never the distractors' wrongness, it's **asymmetry**: the correct option carrying its reasoning while the others are bare, or key-term bolding that flags it. Don't audit afterwards — build evenness in by construction:

1. **Every option is a bare claim — zero "why" in any of them.** All reasoning goes in `explanation`, shown only after they answer.
2. **Write the correct claim first, then mutate it into each distractor.** Take one specific misconception or easily-confused neighbour and state what someone holding it would claim — same skeleton, same grain, same register. Every option is "the claim under some belief"; the correct one is the claim under the correct belief.
3. **Each distractor is a real, BELIEVABLE error** — the answer they would actually give under a specific wrong model, never obviously wrong on sight. An option a cold reader eliminates instantly is wasted: their pick is diagnostic only when the wrong model is what selects it.
4. **No asymmetric bolding.** Bold nothing, or bold the parallel term in every option.

If, reading the finished set cold, you can tell which is right without knowing the material, regenerate — don't patch.

**LaTeX everywhere** — the question, every option, every explanation. Anything expressible as math goes in math, even single variables (`$x$`).

## Reading the answer

### Thinking — their understanding, out loud

Every instrument carries a thinking channel (the note on their selection, the "Other" text, their free-recall words, any message). These are the session's **primary data**: their framing, their mental models, the nuances, where their picture differs from the real one. Read every word and measure what it reveals, not just the answer it carries. One answer is one bit; the thinking is the picture. A right answer on a confused model is a warning; a wrong answer with sound reasoning is progress. Your model of them updates on every submission — what to ask next, how to phrase it, whether the plan itself is wrong about them. Their thinking is often dictated speech: read it leniently for transcription noise.

### Confidence

Every quiz answer carries their stated probability (25/50/75/95%) that their pick is correct. Read it against the verdict:

- 50 is a coin flip. 95 claims certainty; 25 claims real doubt. For an n-option question chance is 1/n — confidence at or below chance means they believe their pick is wrong: a forced choice they distrust. Treat it as honesty, not error.
- **Correct + high:** solid — move on.
- **Correct + low:** fragile knowledge or a lucky guess — one reinforcing touch, not celebration.
- **Wrong + high:** the strongest signal you can receive — a committed misconception. Name the crack, probe it, re-teach around it.
- **Wrong + low:** a shaky near-miss or an honest gap — a small correction usually suffices.
- **"I don't know":** no confidence; they declined to guess. A genuine gap, never a wrong answer.
