---
name: graph
description: Build, query, and use the learner's persistent knowledge graph: propositions and reasoning chains extracted from teaching sessions or imported notes, rendered as linked Obsidian notes (Learning/Graph/). Use after a teaching session ends ("add this to my graph"), to import existing notes, or to explore what has been learned across sessions (/better-learning:graph).
argument-hint: "[extract <session> | import <note> | find <term> | show]"
---

# The knowledge graph

What gets taught accumulates as **propositions** (true, self-contained ideas) and **reasoning chains** (premises that *jointly* entail a conclusion), each with provenance back to the exact passage that taught it (`[[Session#^t12]]`). `.tutor/graph.json` is the source of truth; every proposition is rendered as an Obsidian note (`Learning/Graph/<Name>.md`) linking its premises, its conclusions, its sources, and its practice history, so Obsidian's graph view *is* the graph (filter `tag:#proposition`). Anything the learner writes below the `%% tutor: … %%` line in a proposition note survives regeneration.

The graph is a map of domain knowledge encountered, not a mastery score. A proposition being present doesn't mean it was understood or retained; check the session (and practice history) for that.

`tutor` = `python3 <this skill's base directory>/../../scripts/tutor.py`.

## Extract a session (or import notes)

Dispatch the **`graph-extractor`** agent in the background with:
- the absolute path of the source note (a session note, or any markdown notes file the learner wants imported),
- the CLI path (`tutor paths` prints it),
- a title for the source.

It reads the source, checks what the graph already holds from it (`tutor graph digest`), explores the graph for identity matches, and merges its findings (`tutor graph merge`). It's safe to re-run on a session that grew: it builds on what's already extracted. For long notes it works in stretches.

Extract after `tutor session end`, or whenever the learner asks. Tell them in one line when it's done and how many propositions/chains were added.

## Query

```bash
tutor graph sessions                 # sources and how many propositions each gave birth to
tutor graph list [--source <title>]  # propositions, full statements
tutor graph find "*chain rule*"      # glob over names, statements, aliases
tutor graph candidates --file f.json # for each new finding, the existing nodes most likely to state the same claim
tutor graph chains [--node <id>]     # reasoning chains (premises ⇒ conclusion)
tutor graph show <id|name>           # one node, its chains, its practice history
tutor graph delete <id>              # remove a wrong node (and chains through it), only when asked
tutor graph render                   # regenerate all proposition notes
```

## Use it

- **Before teaching**, the probe reads it to see which strands earlier sessions covered.
- **Practice** draws its material from it (`/better-learning:practice` with picked propositions) and writes results back onto the proposition notes.
- **When explaining anything**, link a proposition the learner already has: `[[Proposition name]]`: new material lands better hung on something they've already built.
