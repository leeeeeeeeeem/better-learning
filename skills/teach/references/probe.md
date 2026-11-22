# The probe

Your whole job in this phase is two measurements: **what they need to learn** (their goal: AskUserQuestion) and **how they already understand the ideas it depends on** (graded questions: `tutor quiz` (closed), or `tutor recall` (open) when their own words will show more than a choice would). Probe questions carry no `type` and no `nodeId`: there is no plan yet.

The plan is built from your assessment, so it must tell the teacher what it can build on, what needs to be connected or rebuilt, and where to begin. Look for the ideas they reason from, the connections they make, and where their intuition leads them when the answer is not obvious. Knowing the right words or picking the right answer is not the same as seeing why. A topic request tells you what they want to learn, not what they already understand: if you have no evidence about their understanding yet, gather it before you conclude.

Work strictly one question at a time: ask, wait for the answer, then choose the next question from what it told you.

## 1. Read their persistent map

`tutor graph sessions` and `tutor graph list --source <session>` (or `tutor graph find "<term>"`) show what earlier sessions extracted into the knowledge graph. That is what was *taught*, not proof it was retained, but a strand covered in a past session is a strong hint where to enter. A strand already known to be solid needs no re-probing. If the graph is empty, just probe.

## 2. Make the goal concrete: AskUserQuestion

"I want to understand LLMs" can mean ten different things; which one changes everything. Interrogate until it's concrete. Questions, not orientation: if they don't know the terrain, record that the goal starts with orientation. Never draw the map yourself in this phase.

## 3. Reason out the strands, and choose questions that reveal how they think

From the goal, what will the lesson depend on? Where would the teaching start, and what must it build on? Each dependency is a strand, bounded by relevance to the goal, nothing more. Focus on the uncertainties that matter for this lesson.

Get as much insight into their understanding as you can for the time and effort they spend answering:

- Prefer a short, concrete question where **different mental models lead to different answers** (predictions, explanations, or choices). That is what makes an answer diagnostic.
- One question can reveal several strands; it need not ask several things.
- Avoid trivia, long calculations and elaborate setups when a simpler question would reveal the same reasoning.
- Their reasoning (the thinking note on a closed question, or the words of an open answer) is your primary evidence. A correct pick can be a guess; a wrong answer can still show sound reasoning.

## 4. Bracket their edge on each strand

Use the logic of binary search: find what they can reliably reason from (the **floor**) and where their reasoning runs out (the **ceiling**). Let the evidence (the verdict, their confidence, and their reasoning together) set the order and size of each jump:

- **Enter near the top, not the bottom.** Start near the high end of what the goal and the evidence suggest is within reach. An adult reaching for advanced material almost always holds the school-level basics; warming up with them wastes a question.
- **Strands inform each other.** Evidence on one strand tells you where to start on its neighbors. Never open below what the session has already demonstrated.
- A well-reasoned answer can justify a **big jump** in difficulty. A tentative one warrants a smaller step.
- A miss tells you where to narrow back toward what they can reason through. It is one coordinate, not a verdict: a slip, a gap and a misconception look the same.
- **Go deeper only when the distinction would change the lesson.** A miss is not by itself a reason to drill the detail: if knowing exactly where it sits would not change what you teach, record it and test a more consequential uncertainty. A confidently held wrong model on a strand the lesson builds on is the exception: find its extent, because it has to be dislodged, not topped up.
- **Stop a strand when the lesson has what it needs.** If they demonstrated what the lesson depends on, there is no reason to keep escalating until they miss.

Every question should move an edge that matters: no filler, no re-asking what their last answer showed, never descending into already-bracketed territory.

## 5. Conclude: `tutor probe-done`

When the goal is clear and the evidence gives the teacher enough to choose a starting point and plan a path:

```bash
tutor probe-done <<'EOF'
{"goal": "…concrete goal…",
 "summary": "optional synthesis: where teaching should enter",
 "strands": [{"strand": "the derivative as a limit",
              "assessment": "Floor: … Ceiling: … Misconceptions: … Build from: …"}],
 "held": [{"term": "limit", "evidence": "q2"}, {"term": "$f'(x)$", "evidence": "q4"}]}
EOF
```

One entry per strand the lesson depends on, written from the evidence: what they can reason from, how they connect the important ideas, where their reasoning ran out, and what still needs checking. **Don't present an untested boundary as a finding**: name it as untested. Add `"held"`: the terms and symbols the probe showed they hold, each with the question that showed it (`{"term": "system call", "evidence": "q2"}`). These, plus terms taught in explanations, are the only ones you may use without defining them; list them generously but honestly (a term that appeared in a question they got wrong is not held). Exactly once; refused while a question is open. It appears in the note as their assessment. Then move straight on to planning (same turn is fine). Read [planning.md](planning.md).

## Grounding: their material, not their description of it

If they reference a local file, find and read it yourself (Glob/Grep/Read; paths resolve against their home directory). Never ask them to paste contents. PDFs go to the `pdf-reader` agent. Research sparingly here: probing is measurement, not exploration.
