# Better Learning: a learning system for Claude Code + Obsidian

> **Use [LearnHarness](https://github.com/amosblomqvist/learnharness) instead.** This project started because LearnHarness needed an API key, so Claude subscription users (Pro / Max) without one had no way to use it. LearnHarness now supports the Claude Code CLI, which removes that reason. It's the original, purpose-built app: a dedicated UI, a graph canvas, dictation, and the full experience this plugin only approximates.
>
> **Why this repo still exists.** I keep using and developing it because it is adapted to my own learning style (see [Changes from the originals](#changes-from-the-originals)). It's a personal project, shared as-is: it follows my preferences, and changes whenever they do.

This started as a Claude Code port of two systems:

- **[learn](https://github.com/amosblomqvist/learn)**: the pi config: the `teach` philosophy, `visualize`, the `quiz` / `ask-user-question` / `md-log` extensions, and the researcher / svg-maker agents.
- **[LearnHarness](https://github.com/amosblomqvist/learnharness)**: the full harness: probe → plan → teach with predict/check questions and a live plan map, confidence + thinking channels, practice sessions, the knowledge graph (extraction + identity linking), research / PDF / visual / demo background agents.

It has since evolved to fit my own learning style, so it is no longer a straight port. The method and most of the doctrine are still theirs; the teaching loop, the question mix, the writing rules, and the presentation have changed. See [Changes from the originals](#changes-from-the-originals).

Claude Code is the control panel. **Obsidian is where you read the session**: every turn, question, graded answer, plan map, figure and demo link is mirrored into a note as it happens, rendered with LaTeX, mermaid, and callouts.

## Install

```bash
# inside Claude Code
/plugin marketplace add leeeeeeeeeem/better-learning
/plugin install better-learning@better-learning
```

(For hacking on it: clone the repo and run `claude --plugin-dir /path/to/better-learning` to load it for one session without installing; edits apply on the next launch.)

Then, **inside your Obsidian vault** (launch `claude` from the vault folder: the mirror hooks find the vault by walking up from Claude's working directory):

```bash
python3 <plugin>/scripts/tutor.py init .     # or just start /better-learning:teach. It offers to set this up
```

This creates `.tutor/` (hidden state) and `Learning/` (Sessions, Practice, Plans, Graph, Research, viz, demos). To use a vault from elsewhere, set `TUTOR_VAULT=/path/to/vault` (e.g. in `~/.claude/settings.json` → `"env"`).

Requirements: Claude Code logged in with a Claude subscription (or any other auth), [Obsidian](https://obsidian.md), Python 3.9+ (stdlib only). Optional: `rsvg-convert` or ImageMagick (figures), Chrome/Chromium or Playwright's chromium (demo testing), `pdftotext`/`pdfinfo` (PDF triage).

## Use

| Command | What it does |
|---|---|
| `/better-learning:teach <topic>` | A full tutoring session: probe → plan → teach |
| `/better-learning:teach resume <session>` | Pick a session back up |
| `/better-learning:practice [topic]` | Practice session over what you've learned |
| `/better-learning:graph` | Extract a session or import notes into the knowledge graph; explore it |
| `/better-learning:visualize`, `/better-learning:demo` | A verified figure or a tested interactive demo, on their own |
| `/better-learning:log <note>` / `/better-learning:log off` | Mirror any conversation into an existing note (the md-log port) |
| `/better-learning:history` | Read your old LearnHarness app data (sessions, graph) |

Answering questions: graded questions pop up as AskUserQuestion with options **A/B/C** + *I don't know* (read the rendered options in Obsidian, pick the letter in the terminal), then your confidence. Add your thinking as a note on your selection: it's the most valuable thing you can give the tutor. Free-recall questions and practice problems are answered by just typing in the chat.

## How the pieces map

| Original | Here |
|---|---|
| `teach` skill (pi) + LearnHarness system prompts (base, prober, teacher, shared) | `skills/teach/`: SKILL.md + phase references loaded as each phase starts |
| `quiz` extension / harness `quiz`+`probe` tools | `tutor.py quiz` commits the key and shuffles → AskUserQuestion → a PostToolUse hook grades deterministically against the commitment and returns verdict, confidence, thinking |
| harness `explain` / `recall` (free recall) | `tutor.py recall` (commit) → your chat reply (hook) → `tutor.py grade` |
| `ask-user-question` extension | Claude Code's AskUserQuestion, mirrored into the note |
| `md-log` extension | Hooks (UserPromptSubmit / PreToolUse / PostToolUse / Stop) that flush the transcript into the note, in order, with `^t12` block anchors |
| `plan_init` + derived plan statuses | `tutor.py plan` → `Learning/Plans/<session> plan.md` (mermaid, current/visited highlighting), embedded in the session note |
| `probe_done` | `tutor.py probe-done` |
| Practice `problem` / `conclude` + doctrine | `skills/practice/` + `tutor.py problem` / `conclude` / `practice-status`; results written onto proposition notes |
| Knowledge graph (extractor → auditor → merger) | `graph-extractor` agent → `tutor.py graph merge`; `.tutor/graph.json` rendered as one note per proposition, so Obsidian's graph view shows it |
| researcher / pdf-reader / visual-maker (svg-maker) / demo-builder | `agents/`: background subagents; SVG via `rsvg-convert`, demos tested with `scripts/run_demo.py` (headless Chromium + screenshot) |
| mermaid-maker | Dropped in favour of inline mermaid (as LearnHarness did): Obsidian renders it natively |
| `learnharness` data skill | `skills/history/` (unchanged readers) |

Not ported: the Electron/Next.js app shell, BYOK provider settings and cost meter (not needed: Claude Code handles auth and billing), dictation (use macOS dictation into the terminal), and the graph canvas UI (Obsidian's graph view replaces it).

Limits of the port: a multiple-choice question has at most 3 options plus *I don't know* (AskUserQuestion holds 4), and confidence is one of four buckets (25/50/75/95%) instead of a slider.

## Changes from the originals

These go beyond porting. They reflect how I learn best, and you may want to change them back.

**Teaching loop**

- Every node of the plan runs predict → explanation → check. The prediction is never skipped, and there is always an explanation between the prediction and the check. Its length depends on the prediction: a compact but complete revision when it was right and confident, a detailed explanation built from the learner's attempt when it was wrong or "I don't know".
- The CLI enforces the order. It refuses a check on a node that had no prediction, and a check with no explanation since the last answer.
- In the originals, the learner picks one quizzing mechanic (multiple choice or free recall) for the session. Here the agent picks per question: closed (multiple choice, to test recognition) or open (a short question answered in your own words, to test production). A node gets one or two checks, depending on the answer, the stated confidence, the learner's thinking, and how much of the plan depends on the node. Examples: closed then open for an important node; open then closed when the open answer showed a specific gap.

**Writing**

- Clarity rules for explanations: name a concept before explaining it, use one name per concept, say explicitly when two names mean the same thing (or don't), define terms at first use, and make every "this" and "it" point at exactly one thing.
- No LLM tells: no em dashes, no stock phrases ("the key difference is", "it's worth noting", "crucially"), no self-answered rhetorical questions. Em dashes that still appear in Claude's text are replaced before they reach the note.
- Text written for agents (subagent definitions, CLI messages, hook messages) follows [ASD-STE100 Simplified Technical English](https://github.com/danyuchn/asd-ste100-skill) rules. Dispatches to background agents use a fixed brief template (task, purpose, context, known, unsure, deliverable, out of scope), so that no agent works without the context it needs.

**Presentation in Obsidian**

- Questions are titled by their role (**Probe**, **Predict**, **Check**) and always shown expanded.
- Claude's text appears without a label; your messages appear inside a **YOU** box.
- Prose written right before a question always appears above it in the note (Claude Code writes each step to the transcript only after its tool finishes; the mirror accounts for this).

**Phone use (Claude app over remote control)**

- The question dialog doesn't render LaTeX, so quiz questions and options are converted to Unicode there (`√dₖ`, `αᵢⱼ`, `ℝⁿ`). The note keeps the LaTeX.
- Open questions and practice problems are also sent as chat messages, so they are visible without the note. The note doesn't get a second copy.

## Files

- `scripts/tutor.py`: the CLI; `scripts/hook.py`: hook entry point; `scripts/tutorlib/`: vault/state, mirror, questions, plan, graph; `scripts/run_demo.py`: headless demo tester.
- State lives in the vault's `.tutor/` (Obsidian ignores dot-folders): `state.json` (which conversation is bound to which session), `sessions/*.json` (questions with answer keys, plan, probe, problems), `graph.json`.
- Set `TUTOR_DEBUG=1` to log raw hook payloads to `.tutor/hook-debug.jsonl`; hook failures go to `.tutor/hook-errors.log` and never interrupt the session.

## Credits

The teaching design (the prompts, the probe/plan/teach method, the practice doctrine, the knowledge-graph pipeline) comes from [LearnHarness](https://github.com/amosblomqvist/learnharness) and [learn](https://github.com/amosblomqvist/learn) by Amos Blomqvist. This repo adapts them to Claude Code + Obsidian and changes parts of them, as listed in [Changes from the originals](#changes-from-the-originals). Not affiliated with or endorsed by the LearnHarness project or Anthropic.

## License

AGPL-3.0 (inherits LearnHarness's prompts). See [LICENSE](LICENSE).
