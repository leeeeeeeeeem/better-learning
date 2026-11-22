---
name: demo
description: Build an interactive teaching instrument (a single-file HTML demo with sliders, simulations, or animations) via the demo-builder agent, which tests it headlessly (and screenshots it) until it runs clean, then link it from the Obsidian note. Use when a concept is dynamic (a parameter to sweep, a process to animate, a distribution to sample, a system to simulate) and the learner should operate it rather than read about it.
---

# Demo: build the instrument, don't describe it

Ten seconds of dragging a slider teaches more than a paragraph about frequency response. Use this when the learner should *operate* the idea: sweep it, watch it evolve, break it.

## Brief

Dispatch the **`demo-builder`** agent in the background. It never sees the conversation: the brief is its whole world. Use the brief template in [the teach skill's background reference](../teach/references/background.md), with these demo fields:

- `TITLE`: short.
- `TASK`: the concept, precisely.
- `CONTROLS`: every parameter/control, its range, and what it changes.
- `FORMULAS`: every formula and constant, in plain math the builder can implement.
- `DELIVERABLE`: the interactions, what should be visible, the visual style.
- `CLI`: the path from `tutor paths`.

A vague brief yields a vague demo. Announce it in a sentence and keep explaining while it builds.

## When it lands

It returns a markdown link (`[▶ Open the demo: …](file:///…)`) and notes on its controls. Put the link in a `tutor explain` block (it opens in the browser from Obsidian) and **teach with it**: point at its controls by name ("drag damping all the way left and watch the overshoot"). An artifact you never point at is decoration. If it misbehaves, re-dispatch with a tighter brief; on failure, say so and explain in prose.
