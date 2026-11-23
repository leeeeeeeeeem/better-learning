# Better Learning: a learning system for Claude Code + Obsidian

> **Use [LearnHarness](https://github.com/amosblomqvist/learnharness) instead.** This project started because LearnHarness needed an API key, so Claude subscription users (Pro / Max) without one had no way to use it. LearnHarness now supports the Claude Code CLI, which removes that reason. 
>
> **Why this repo still exists.** It is no longer just a port: it has features the originals don't have (spaced review questions, a term registry that keeps anything undefined out of a lesson, sessions that work the same in the terminal, on a phone and in Obsidian) and it follows my own learning style. See [Changes from the originals](#changes-from-the-originals). It's a personal project, it follows my preferences and changes whenever they do.

This started as a Claude Code port of two systems:

- **[learn](https://github.com/amosblomqvist/learn)**: the pi config: the `teach` philosophy, `visualize`, the `quiz` / `ask-user-question` / `md-log` extensions, and the researcher / svg-maker agents.
- **[LearnHarness](https://github.com/amosblomqvist/learnharness)**: the full harness: probe → plan → teach with predict/check questions and a live plan map, confidence + thinking channels, practice sessions, the knowledge graph (extraction + identity linking), research / PDF / visual / demo background agents.

It has since grown into its own system. The method (probe → plan → teach, predict → explain → check) and most of the doctrine are still theirs. What changed:

- **Review questions.** Long sessions teach more than you can hold at once, so earlier nodes come back as spaced review questions: every 2 completed nodes, after every resume, and before the session ends, chosen by importance, weakness and time since you last retrieved them.
- **Nothing undefined.** Every term and symbol in an explanation or question must have been taught, shown in the probe, or defined on the spot; the CLI enforces it.
- **A stricter teaching loop**: a short setup before each prediction, explanations that always reach you, no "ready" turns, asides that never count as answers, repairs on the smallest concrete case.
- **Anywhere**: the same session in the terminal, in the Claude app on a phone, and in Obsidian, without telling the tutor where you are.
- **Kept in sync with upstream**: later LearnHarness improvements (the probe doctrine, notes import, faster graph linking) are ported in.

Details in [Changes from the originals](#changes-from-the-originals).

**Obsidian is where you read the session in full**: every turn, question, graded answer, plan map, figure and demo link is mirrored into a note as it happens, rendered with LaTeX, mermaid, and callouts. The explanations and questions also appear in Claude Code's chat, so you can follow along in the terminal or on your phone.

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

Every 2 completed nodes, after a resume and before the end of a session, the tutor asks a **review question** on an earlier node before moving on (see [Changes from the originals](#changes-from-the-originals)).

Answering questions: graded questions pop up as AskUserQuestion with options **A/B/C** + *I don't know* (read the rendered options in Obsidian, pick the letter in the terminal), then your confidence. Add your thinking as a note on your selection: it's the most valuable thing you can give the tutor. Free-recall questions and practice problems are answered by just typing in the chat. While an open question is waiting you can still ask something else ("what does frozen mean?", "resend that block"): the tutor answers the aside and asks the question again, without grading your aside as the answer. If you send a corrected answer, the latest one is graded.

## How the pieces map

| Original | Here |
|---|---|
| `teach` skill (pi) + LearnHarness system prompts (base, prober, teacher, shared) | `skills/teach/`: SKILL.md + phase references loaded as each phase starts |
| `quiz` extension / harness `quiz`+`probe` tools | `tutor.py quiz` commits the key and shuffles → AskUserQuestion → a PostToolUse hook grades deterministically against the commitment and returns verdict, confidence, thinking |
| harness `explain` / `recall` (free recall) | `tutor.py recall` (commit) → your chat replies, each a candidate answer (hook) → `tutor.py grade` on the one that is the answer |
| Teacher explanations (prose in the originals) | `tutor.py explain`: markdown with a `reply:` / `terms:` / `uses:` header, written into the note in reading order; term definitions kept in a registry across sessions |
| `ask-user-question` extension | Claude Code's AskUserQuestion, mirrored into the note |
| `md-log` extension | Hooks (UserPromptSubmit / PreToolUse / PostToolUse / Stop) that flush the transcript into the note, in order, with `^t12` block anchors. The Stop hook flushes again shortly after the turn ends, so the last text of a turn shows up without you typing anything |
| (none: new here) | Review questions: `"type": "review"` on quiz/recall, scheduled by `tutorlib/review.py`; `tutor.py reask` re-sends a question that was interrupted, after the resume review |
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

**Review questions (spaced retrieval)**

A long session teaches many concepts, and the ones from the start can be gone by the end. So earlier nodes come back as **review questions**:

- **When:** one every 2 completed nodes (a node is completed by its first passed check), one as the first question after a resume, and one or two before the session ends. The CLI enforces it: the next node, and `session end`, are refused until the review is done (`session end --pause` when only pausing).
- **Which node:** the CLI ranks the completed nodes by time since each was last retrieved, against a spacing interval that doubles after each confident pass and resets after a miss; by how much of the plan depends on the node; and by weak answers on it. The agent picks from the top candidates.
- **How:** open or closed, at the agent's discretion; no setup before it; always a new angle (a new case, or a combination with a later node), never the original check reworded.
- **After the answer:** a pass is acknowledged and the session moves on; a miss is repaired on the smallest concrete case and re-checked before anything new.
- **On resume:** a question left unanswered when the session was interrupted waits until after the review; then `tutor.py reask` re-sends the reaction to the review, the question's setup and the same question (same answer key).
- In the note, reviews are titled **Review**, and they don't move the "you are here" marker on the plan map. The interval is `review_every_nodes` in `.tutor/config.json`.

**Teaching loop**

- Every node of the plan runs predict → explanation → check. The prediction is never skipped, and there is always an explanation between the prediction and the check. Its length depends on the prediction: a compact but complete revision when it was right and confident, a detailed explanation built from the learner's attempt when it was wrong or "I don't know".
- Before each prediction comes a short **setup**: a New terms box with every term the question uses, and a few sentences on what the question asks, never the answer. The CLI caps a setup's prose and doesn't count it as the node's explanation, so the explanation after your answer (sized by your prediction, as before) is still required.
- Explanations are written with `tutor explain`, not as chat prose. The CLI refuses a check on a node that had no prediction, and a check with no `tutor explain` block for the node since the last answer. Chat prose and the model's thinking don't count (in early sessions, whole explanations existed only in the model's thinking and never reached the learner).
- No "ready" turns: the explanation and its check come in the same turn. The Stop hook refuses a turn that ends right after an explanation with no question asked; the question dialog waits while you read the note.
- Nothing undefined: every term and symbol in an explanation or a teach-phase question must be (a) taught in an explanation, in this session or an earlier one, (b) shown held in the probe (`probe-done` takes a `held` list), or (c) defined in the explanation's `terms:` header. Questions declare the terms they rely on in `uses`; the CLI checks them against a term registry and also scans the text for symbols ($W_{up}$, $\alpha$, `code_names`), and refuses anything undefined. `tutor.py terms list` shows the registry.
- One step per explanation block: a block that needs many new terms or covers two ideas is split, with a check between. A symbol is never defined only in a table cell or only by its shape.
- A wrong answer given with high confidence, or a miss that repeats, is repaired on the smallest concrete case (scalars, small numbers) that you compute, before the general form.
- Asides are not answers: a clarifying question, a "resend that" or a complaint sent while an open question is waiting is answered, and the question stays open.
- The tutor can't work around its own checks: a guard hook refuses direct writes (Write/Edit, scripts, redirects) to session notes, plan notes and `.tutor/`. Only the CLI and the hooks write there.
- In the originals, the learner picks one quizzing mechanic (multiple choice or free recall) for the session. Here the agent picks per question: closed (multiple choice, to test recognition) or open (a short question answered in your own words, to test production). A node gets one or two checks, depending on the answer, the stated confidence, the learner's thinking, and how much of the plan depends on the node. Examples: closed then open for an important node; open then closed when the open answer showed a specific gap.

**Ported from later LearnHarness versions (0.7.0, Nov 2026)**

The original port was taken from LearnHarness 0.3.8. These later upstream changes were ported in, adapted to the changes above:

- The probe looks for what would change the plan: short questions where different mental models give different answers, a miss drilled only when the distinction matters for the lesson, and no escalating once the lesson's needs are shown. Untested boundaries are reported as untested and checked during teaching.
- Confidence is read alongside the reasoning, never as proof on its own.
- An aside answered while a question is open never gives that question's answer away.
- Imported notes keep definitions and facts as plain propositions; chains only where the notes actually reason.
- The graph extractor links findings from a ranked candidate list (`tutor.py graph candidates`) instead of browsing the whole graph.

**Writing**

- Clarity rules for explanations: name a concept before explaining it, use one name per concept, say explicitly when two names mean the same thing (or don't), define terms at first use, and make every "this" and "it" point at exactly one thing.
- No LLM tells: no em dashes, no stock phrases ("the key difference is", "it's worth noting", "crucially"), no self-answered rhetorical questions. Em dashes that still appear in Claude's text are replaced before they reach the note.
- Text written for agents (subagent definitions, CLI messages, hook messages) follows [ASD-STE100 Simplified Technical English](https://github.com/danyuchn/asd-ste100-skill) rules. Dispatches to background agents use a fixed brief template (task, purpose, context, known, unsure, deliverable, out of scope), so that no agent works without the context it needs.

**Presentation in Obsidian**

- Questions are titled by their role (**Probe**, **Predict**, **Check**, **Review**) and always shown expanded.
- Claude's text appears without a label; your messages appear inside a **YOU** box.
- After each answer the note reads in order: the verdict, the tutor's reaction to your answer (the explanation's `reply:` line), the next section's heading, a **New terms** box with every term the section introduces, then the explanation and the next question.
- Every block the CLI writes (explanations, questions, grades, the plan) lands right after whatever came before it. Claude Code writes each step to the transcript only after its tool finishes, so the CLI queues its blocks and the mirror places them behind the prose that preceded them.

**Terminal and phone use (Claude app over remote control)**

- The question dialog doesn't render LaTeX, so quiz questions and options are converted to Unicode there (`√dₖ`, `αᵢⱼ`, `ℝⁿ`). The note keeps the LaTeX.
- Open questions and practice problems are also sent as chat messages, so they are visible without the note. The note doesn't get a second copy.
- Explanations and setups are written into the note and then repeated as a chat message, so the session can be followed from the terminal or the phone without telling the tutor where you are. The mirror recognises the copy and keeps it out of the note; a question dialog is refused once while the copy is missing.
- Closing a question dialog without answering (easy on a phone) leaves the question open; it is asked again, not recorded as cancelled.

## Files

- `scripts/tutor.py`: the CLI; `scripts/hook.py`: hook entry point (mirror, recall candidates, Stop check, write guard); `scripts/tutorlib/`: vault/state, mirror, questions, terms (registry and define-before-use checks), review (review scheduling), plan, graph; `scripts/run_demo.py`: headless demo tester.
- `tests/test_teach_flow.py`: end-to-end tests of the teach loop, the term checks, setups, review questions and resume, recall asides, chat copies, note ordering and the write guard. Run `python3 -m unittest discover -s tests` from the plugin root.
- State lives in the vault's `.tutor/` (Obsidian ignores dot-folders): `state.json` (which conversation is bound to which session), `sessions/*.json` (questions with answer keys and candidate answers, plan, probe, term registry, explanations, problems), `graph.json`.
- Set `TUTOR_DEBUG=1` to log raw hook payloads to `.tutor/hook-debug.jsonl`. Hook failures go to `.tutor/hook-errors.log` and never interrupt the session. The hooks block on purpose only in these cases: a turn that ends after an explanation with no question (Stop), a question dialog while the last explanation is missing from the chat (once), and a direct write to the note or `.tutor/` (PreToolUse).
- Sessions started before 0.3.0 have an empty term registry. On resume, the tutor registers what the note shows was probed or taught (`tutor.py terms add`) before it asks anything.

## Credits

The teaching design (the prompts, the probe/plan/teach method, the practice doctrine, the knowledge-graph pipeline) comes from [LearnHarness](https://github.com/amosblomqvist/learnharness) and [learn](https://github.com/amosblomqvist/learn) by Amos Blomqvist. This repo adapts them to Claude Code + Obsidian, changes parts of them and adds its own features, as listed in [Changes from the originals](#changes-from-the-originals). Not affiliated with or endorsed by the LearnHarness project or Anthropic.

## License

AGPL-3.0 (inherits LearnHarness's prompts). See [LICENSE](LICENSE).
