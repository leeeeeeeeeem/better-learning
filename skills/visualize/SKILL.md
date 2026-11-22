---
name: visualize
description: Add one correct, minimal visual to an explanation, rendered in the Obsidian note: inline mermaid for structure (dependencies, flows, sequences, trees, comparisons) or a verified PNG figure for spatial/geometric ideas (coordinate geometry, number lines, vectors, plots, physical layouts) made by the visual-maker agent, which renders and looks at its own output. Use when an idea is genuinely clearer as a picture.
---

# Visualize

A picture earns its place only when it shows something words can't: shape, structure, direction, relationship, geometry. This produces ONE such picture and guarantees it is **correct**.

You are the **creative director**: decide the exact idea and distill it to its fewest carrying elements. A decorative diagram that restates the sentence next to it adds noise and a chance to be wrong. When in doubt, don't. A missing visual is cheaper than a false one.

## Choose the form

- **Nodes and edges / relationships**: dependency graphs, flows, sequences, state machines, trees, comparisons → write a ```mermaid block inline. Obsidian renders it. Quote labels with spaces or symbols (`B["u = x^3"]`). Keep it to ~7 nodes.
- **Positions and shapes / geometry** → dispatch the **`visual-maker`** agent. It hand-authors SVG, renders it, looks at the PNG, iterates until correct, and publishes it into the vault's `viz/` folder.

## Brief the maker: one idea, fewest elements

The most common failure is cramming. Before briefing, prune: for each element ask *"if I delete this, is the idea still clear?"* If yes, delete it. Give the concept AND the concrete elements (coordinates, labels, proportions, orientation), not a vague topic.

- BAD: "a picture about vectors"
- GOOD: "Axes from −1 to 5 on both. Vector **u** = (3,1) from the origin in blue, **v** = (1,2) drawn tip-to-tail from (3,1), their sum (4,3) from the origin dashed. Label u, v, u+v near their midpoints. No grid."

Use the brief template in [the teach skill's background reference](../teach/references/background.md): the elements go in its `FIGURE:` field, and `CLI` comes from `tutor paths`. It returns `filename: viz-…png` (or `NONE` with a reason: simplify, rethink, or drop the visual).

## Embed

`![[viz-<slug>-<ts>.png|500]]` in your next `tutor explain` block (wider for dense figures). Introduce it in a sentence, then let it carry the idea. Don't narrate every element back in prose.
