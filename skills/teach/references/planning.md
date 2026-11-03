# The plan

## Planning — think hard here

This is the highest-leverage step; don't rush it. With their level and their goal in hand, stop and genuinely reason out the best way to teach *this thing* to *this person*. Re-read [method.md](method.md) and plan against it:

- **Scope the field.** Its core concepts, the real first principles, standard framings, common gotchas — and where your picture of the field is less than clear, dispatch the `researcher` agent to check it: planning is the natural moment for verification.
- What are the unconditional truths this rests on? Is there a clean atomic unit ("ALL X is done through {____}")?
- Which of those do they already hold (from the probe)? Build from there — not below it, not above it. The plan is the **minimal tree**: nothing they already hold is re-taught, nothing off the path to their goal is taught however interesting, and the derivation to the goal is as short as the subject allows.
- What's the motivated discovery path from those truths to their goal? Where does each step come from — why would anyone reach for it?
- Socratic or expository for each stretch, given the topic and their energy?

A good plan is what makes the teaching feel inevitable instead of arbitrary.

## The plan map — `tutor plan`

The session has a live dependency map the learner sees in Obsidian — where they are, what they've passed, what's coming — and it updates itself from your questions. Your part is two things: writing the map, and telling it which node each question is about.

```bash
tutor plan <<'EOF'
graph TD
  limits["Limits"] --> derivative["Derivative = local scaling"]
  derivative --> composition["Composition composes scalings"]
  composition --> chain-rule["Chain rule"]
EOF
```

It is a **map, not a syllabus**: nodes are structural landmarks — the unconditional truths at the roots, the major stations, their goal at the sink — not turns of teaching. A single node may take one reasoning step or five.

- Node ids are the one strict part: lowercase slugs (a-z 0-9, hyphens/underscores), chosen once, permanent. Titles are free text. No subgraphs, styles, or classes.
- `-->` means *requires*: from = must be understood before to. The map must be acyclic.
- No size ceiling: as many nodes as the subject genuinely needs — elaborate is fine, wrong is not. What keeps a map readable is correct structure: find the unconditional truths underneath and hang everything off those.
- The CLI writes the map to its own note (`Learning/Plans/…`) and embeds it in the session note; the current node is highlighted, visited nodes are marked. Statuses derive from your questions' `nodeId` tags — you never set them.

## The map moves with them

The map is a hypothesis about them, and the probe is only its first sketch — the revealing data arrives during teaching, in their thinking. Their understanding as actually expressed outranks whatever the plan assumed; when they differ, the map moves — re-run `tutor plan` to restructure, add a foundation they turn out to lack, prune what they already hold, detour for a question worth exploring. Rewriting is normal.

And when the ground shifts mid-lesson — a missing foundation, a confusion deeper than the map assumed — never rush the repair: no wall of text that "covers" the missing ground in one turn to get back on plan. The plan serves their understanding, never the reverse. Update the map if the structure changed, then build the missing ground the only way anything is built here — one reasoning step at a time, each step landing and verified. Detours are not interruptions to get through; they are the teaching.

**Every teach-phase quiz/recall carries `nodeId` AND `type`** (both required; a call missing either is refused). `type` is the question's role: `predict` before you teach the step, `check` after. The live position is simply the latest tagged node, so asking about the next node *is* how the lesson gets there. A tag is a position, not a verdict — nodes are never marked finished. Stay on one node as long as the understanding needs. Off-map questions use AskUserQuestion directly.

## Presenting the plan — always, before any teaching

1. **The approach, in prose.** What you'll cover, in what order, and why this way — given where their edge sits and what they're reaching for. A few freeform sentences.
2. **The map.** `tutor plan` is itself the presentation — it embeds the live diagram in the note right after your prose. Never draw the plan again in your prose: no second mermaid block, no outline restating the map.

**Stress-test the roots before presenting.** For every node you're treating as foundational, ask: is this genuinely an unconditional truth *for them*, or a disguised theorem that itself derives from something simpler they'd accept at face value? If it derives, push it down and extend the map. A wrong root corrupts everything hung off it, and roots are far easier to audit in a drawn map than mid-flow.

**Presenting ends your turn.** Ask them to confirm the plan before teaching begins (AskUserQuestion works well: approve / change something). If they ask for changes, revise (`tutor plan` again) and present again; once they're on board, read [teaching.md](teaching.md) and begin the first node. Never teach in the presenting turn. Mid-lesson rewrites carry on without re-presenting.
