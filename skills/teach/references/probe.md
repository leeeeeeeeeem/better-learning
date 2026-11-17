# The probe

Your whole job in this phase is two measurements: **what they need to learn** (their goal: AskUserQuestion) and **what they already know** (a detailed map of their exact understanding, graded questions: `tutor quiz` (closed), or `tutor recall` (open) when their own words will show more than a choice would). Probe questions carry no `type` and no `nodeId`: there is no plan yet. The whole lesson will be planned from your map; it must be precise.

Work strictly one question at a time: ask, wait for the answer, then choose the next question from what it told you.

## 1. Read their persistent map

`tutor graph sessions` and `tutor graph list --source <session>` (or `tutor graph find "<term>"`) show what earlier sessions extracted into the knowledge graph. That is what was *taught*, not proof it was retained, but a strand covered in a past session is a strong hint where to enter. If the graph is empty, just probe.

## 2. Make the goal concrete: AskUserQuestion

"I want to understand LLMs" can mean ten different things; which one changes everything. Interrogate until it's concrete. Questions, not orientation: if they don't know the terrain, record that the goal starts with orientation. Never draw the map yourself in this phase.

## 3. Reason out the strands

From the goal, what will the lesson depend on? Where would the teaching start, and what must it build on? Each dependency is a strand, bounded by relevance to the goal, nothing more.

## 4. Binary-search every strand

The edge of a strand is found by bracketing: something they reliably get **right** (a floor) and something they get **wrong** or don't know (a ceiling). Choose every next question from the evidence: the verdict, their confidence, and their thinking together set where the next question should sit:

- **Enter near the top, not the bottom.** Their goal and how they talk calibrate the strand: an adult reaching for advanced material almost always holds the school-level basics. Open near the hardest thing the goal needs and let a miss walk you down. Opening a strand at textbook basics to "warm up" wastes the question that could have moved an edge.
- **Strands inform each other.** A strand crushed at height says its neighbors start high too. Never open below what the session has already demonstrated.
- Correct + confident → jump the difficulty up *sharply*: the bigger the jump, the fewer the questions.
- Correct but hesitant (low confidence, thin thinking) → fragile: step up gently and characterize the shakiness.
- Wrong → the ceiling drops; narrow back in to pin exactly where it sits.
- A miss is one coordinate, not a verdict: slip, gap, or misconception look identical. Probe around it. Misconceptions matter most: a confidently held wrong model has to be dislodged, not topped up. Dig into its extent before moving on.
- **All-correct is not done**: it means the questions were too easy. A strand that never breaks is not done: escalate until it does.

Every question should move an edge somewhere: no filler, no re-asking what their last answer showed, never descending into already-bracketed territory. Every wasted question is resolution the final map doesn't get.

## 5. Conclude: `tutor probe-done`

When every strand is bracketed and the goal is concrete:

```bash
tutor probe-done <<'EOF'
{"goal": "…concrete goal…",
 "summary": "optional synthesis: where teaching should enter",
 "strands": [{"strand": "the derivative as a limit",
              "assessment": "Floor: … Ceiling: … Misconceptions: … Build from: …"}]}
EOF
```

One entry per strand, written from the evidence. Exactly once; refused while a question is open. It appears in the note as their assessment. Then move straight on to planning (same turn is fine). Read [planning.md](planning.md).

## Grounding: their material, not their description of it

If they reference a local file, find and read it yourself (Glob/Grep/Read; paths resolve against their home directory). Never ask them to paste contents. PDFs go to the `pdf-reader` agent. Research sparingly here: probing is measurement, not exploration.
