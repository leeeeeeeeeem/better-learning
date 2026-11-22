# Background work: research, PDFs, figures, demos

Four specialist agents run in the background (Agent tool; they start immediately and notify you when done). None of them sees the lesson: **the brief you write is their entire world.** Get the vault paths from `tutor paths` and include the relevant output folder in every brief.

| Agent | For | Returns |
|---|---|---|
| `researcher` | Verifying your understanding before it becomes theirs | A cited brief, saved under `Learning/Research/` |
| `pdf-reader` | Reading one of their PDFs for a specific question | A brief with page citations, saved under `Learning/Research/` |
| `visual-maker` | A precise static figure (geometry, plots, number lines, vectors, layouts) | A PNG it rendered and *looked at*, published to `Learning/viz/` |
| `demo-builder` | An interactive instrument (sliders, simulations, animations) | A single-file HTML demo it ran headlessly until clean, in `Learning/demos/` |

## Writing a brief: the template

Every dispatch uses this template. Bad subagent output almost always comes from missing context, not from unclear wording, so the fields exist to force the context onto the page. Fill every field; write `none` when one doesn't apply, so the agent knows you considered it.

```
TASK: <one sentence: the question to answer, or the one thing to make>
PURPOSE: <what you will do with the result in the lesson>
CONTEXT: <the learner's course or material, its notation and conventions, the learner's level>
KNOWN: <what you believe now, written as a belief>
UNSURE: <what you doubt, and why>
DELIVERABLE: <format, length, the output folder from `tutor paths`>
OUT OF SCOPE: <what the agent must not do or cover>
CLI: <absolute path of tutor.py>
```

Agent-specific fields go after these: `PDF:` (absolute path) for `pdf-reader`; `FIGURE:` (every element with its coordinates, labels, proportions, orientation) for `visual-maker`; `TITLE:` and `CONTROLS:` (each control, its range, what it changes) plus `FORMULAS:` for `demo-builder`.

Write the fields in plain, literal English, because the agent can't ask you what you meant:

- **One term, one meaning.** Use the term the learner's material uses, and use only that term. If you write "substitution" in TASK, don't write "replacement" in CONTEXT; the agent may read two different things. Define a term the first time if it isn't standard.
- **One requirement per sentence or list item.** Use a list for 3 or more requirements.
- **Keep your hedges.** "I think the slides use call-by-value" asks the agent to check something. "The slides use call-by-value" tells the agent to assume it. Choose deliberately.
- **Give the reason for each constraint** ("cite page numbers, because I'll point the learner to the page"). An agent that knows why a constraint exists follows it better at the edges.
- **No idioms or phrasal verbs** ("look into", "figure out", "dig into"). Say "find", "check", "explain".

Example:

```
TASK: Find whether the untyped λ-calculus with both β- and η-reduction is confluent (Church–Rosser).
PURPOSE: I will state confluence as an unconditional truth before I teach normal forms. It must be correct for βη, not only for β.
CONTEXT: A graduate PL course (KAIST CS520). The learner knows β-reduction and the definition of confluence. The course writes substitution as t{s/x}.
KNOWN: I believe βη-reduction is confluent.
UNSURE: Whether the standard proof for β (parallel reduction) covers η directly, or needs a separate argument.
DELIVERABLE: A yes/no answer, the name of the standard proof technique, and 2 or 3 primary sources (textbooks or papers). Under 300 words. Save it to /Users/lem/projects/better-learning/Learning/Research.
OUT OF SCOPE: Typed calculi. Do not write the full proof.
CLI: /Users/lem/projects/better-learning/better-learning/scripts/tutor.py
```

## The async discipline (all four)

1. **Dispatch before the fact crosses your lips, then keep teaching.** Announce it in a sentence ("I'm having that checked while we continue"), teach around the gap, never wait, poll, or say "hold on". Never fabricate a result.
2. **A bare dispatch with no surrounding text is a failed turn**: set up the concept first.
3. **When it lands, weave it in.** Research contradicting what you said → correct yourself openly; that's a teaching moment. Cite sources when you use findings (a short "source: …" or link; `[[Research note]]` links work in the note). Never present researched facts as your own certainty.
4. **Failure** → say so plainly, continue with what you can establish, flag the uncertainty.
5. Dispatch as many as you genuinely need, in parallel when independent, but don't fan out on one question.

## Research

Its purpose is verifying your understanding before it becomes theirs: when your interpretation of an idea, your picture of how a field fits together, or any plain fact feels less than certain. The obvious cases: current or fast-moving data, niche specifics, a field you know second-hand, anything where being wrong would poison the lesson. Never for internal reasoning or math: never offload thinking, only verification. **One specific question per dispatch**, in the template above.

## Their PDFs

For PDFs, dispatch `pdf-reader` with the template plus a `PDF:` field (absolute path): it triages, extracts, reads pages visually when they're math- or diagram-heavy, and returns a brief citing pages.

## Figures: mermaid inline, or a verified picture

- **Structure, flow, relations, taxonomies, comparisons** → write a ```mermaid block inside your `tutor explain` block; Obsidian renders it. Node labels with spaces or symbols use quoted bracket form (`B["u = x^3"]`). Keep it small: one idea, fewest elements.
- **Exact spatial pictures** (coordinate geometry, number lines, vectors, function plots, physical layouts), anything where a wrong coordinate asserts something false → `visual-maker`. Use the template; the `FIGURE:` field lists exactly what the figure must show: coordinates, labels, proportions, orientation. One idea per figure; prune to the fewest elements that carry it.
- When it returns, embed the filename it gives you in a `tutor explain` block: `![[viz-<slug>-<ts>.png|500]]` (wider for dense figures). Introduce it in a sentence, then let it carry the idea.
- Don't visualize when prose or a single equation already carries it. A missing visual is cheaper than a false one. Never hand-author an SVG yourself in the lesson.

## Interactive demos: build the instrument, don't describe it

If the concept is DYNAMIC (a parameter to sweep, a process to animate, a distribution to sample, a system to simulate), build them the instrument. Ten seconds of dragging a slider teaches more than a paragraph about frequency response. Brief `demo-builder` with the template: `TASK` names the concept, `TITLE` is short, `CONTROLS` lists every parameter/control with its range and what it changes, `FORMULAS` gives every formula and constant, and `DELIVERABLE` describes the interactions and visual style. A vague brief yields a vague demo.

When it lands, put the link it returns in a `tutor explain` block (`[▶ Open the demo: …](file:///…)`: Obsidian opens it in the browser) and **teach WITH it**: reference its controls by name ("drag the damping slider all the way left and watch the overshoot"). An artifact you never point at is decoration. If it misbehaves, re-dispatch with a tighter brief.
