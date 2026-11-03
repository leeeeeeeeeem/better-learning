# better-learning — a learning system for Claude Code + Obsidian

> **Scope.** This project exists to give **Claude subscription users (Pro / Max) who don't have an API key** access to a learning system similar to [LearnHarness](https://learnharness.ai). It runs entirely inside Claude Code, so it uses your subscription instead of pay-per-token API billing.
>
> **If you have an API key, use [LearnHarness](https://github.com/amosblomqvist/learnharness) instead.** It's the original, purpose-built app — a dedicated UI, a graph canvas, dictation, and the full experience this plugin only approximates. This port is a workaround for people who can't use it, not a replacement.

A Claude Code plugin that ports two systems into Claude Code:

- **[learn](https://github.com/amosblomqvist/learn)** — the pi config: the `teach` philosophy, `visualize`, the `quiz` / `ask-user-question` / `md-log` extensions, and the researcher / svg-maker agents.
- **[LearnHarness](https://github.com/amosblomqvist/learnharness)** — the full harness: probe → plan → teach with predict/check questions and a live plan map, confidence + thinking channels, practice sessions, the knowledge graph (extraction + identity linking), research / PDF / visual / demo background agents.

Claude Code is the control panel. **Obsidian is where you read the session**: every turn, question, graded answer, plan map, figure and demo link is mirrored into a note as it happens, rendered with LaTeX, mermaid, and callouts.

## Install

```bash
# inside Claude Code
/plugin marketplace add leeeeeeeeeem/better-learning
/plugin install better-learning@better-learning
```

(For hacking on it: clone the repo and run `claude --plugin-dir /path/to/better-learning` to load it for one session without installing; edits apply on the next launch.)

Then, **inside your Obsidian vault** (launch `claude` from the vault folder — the mirror hooks find the vault by walking up from Claude's working directory):

```bash
python3 <plugin>/scripts/tutor.py init .     # or just start /better-learning:teach — it offers to set this up
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

Answering questions: graded questions pop up as AskUserQuestion with options **A/B/C** + *I don't know* (read the rendered options in Obsidian, pick the letter in the terminal), then your confidence. Add your thinking as a note on your selection — it's the most valuable thing you can give the tutor. Free-recall questions and practice problems are answered by just typing in the chat.

## How the pieces map

| Original | Here |
|---|---|
| `teach` skill (pi) + LearnHarness system prompts (base, prober, teacher, shared) | `skills/teach/` — SKILL.md + phase references loaded as each phase starts |
| `quiz` extension / harness `quiz`+`probe` tools | `tutor.py quiz` commits the key and shuffles → AskUserQuestion → a PostToolUse hook grades deterministically against the commitment and returns verdict, confidence, thinking |
| harness `explain` / `recall` (free recall) | `tutor.py recall` (commit) → your chat reply (hook) → `tutor.py grade` |
| `ask-user-question` extension | Claude Code's AskUserQuestion, mirrored into the note |
| `md-log` extension | Hooks (UserPromptSubmit / PreToolUse / PostToolUse / Stop) that flush the transcript into the note, in order, with `^t12` block anchors |
| `plan_init` + derived plan statuses | `tutor.py plan` → `Learning/Plans/<session> — plan.md` (mermaid, current/visited highlighting), embedded in the session note |
| `probe_done` | `tutor.py probe-done` |
| Practice `problem` / `conclude` + doctrine | `skills/practice/` + `tutor.py problem` / `conclude` / `practice-status`; results written onto proposition notes |
| Knowledge graph (extractor → auditor → merger) | `graph-extractor` agent → `tutor.py graph merge`; `.tutor/graph.json` rendered as one note per proposition, so Obsidian's graph view shows it |
| researcher / pdf-reader / visual-maker (svg-maker) / demo-builder | `agents/` — background subagents; SVG via `rsvg-convert`, demos tested with `scripts/run_demo.py` (headless Chromium + screenshot) |
| mermaid-maker | Dropped in favour of inline mermaid (as LearnHarness did) — Obsidian renders it natively |
| `learnharness` data skill | `skills/history/` (unchanged readers) |

Not ported: the Electron/Next.js app shell, BYOK provider settings and cost meter (not needed — Claude Code handles auth and billing), dictation (use macOS dictation into the terminal), and the graph canvas UI (Obsidian's graph view replaces it).

## Files

- `scripts/tutor.py` — the CLI; `scripts/hook.py` — hook entry point; `scripts/tutorlib/` — vault/state, mirror, questions, plan, graph; `scripts/run_demo.py` — headless demo tester.
- State lives in the vault's `.tutor/` (Obsidian ignores dot-folders): `state.json` (which conversation is bound to which session), `sessions/*.json` (questions with answer keys, plan, probe, problems), `graph.json`.
- Set `TUTOR_DEBUG=1` to log raw hook payloads to `.tutor/hook-debug.jsonl`; hook failures go to `.tutor/hook-errors.log` and never interrupt the session.

## Credits

All of the teaching design — the prompts, the probe/plan/teach method, the practice doctrine, the knowledge-graph pipeline — comes from [LearnHarness](https://github.com/amosblomqvist/learnharness) and [learn](https://github.com/amosblomqvist/learn) by Amos Blomqvist. This repo only adapts them to run on Claude Code + Obsidian. Not affiliated with or endorsed by the LearnHarness project or Anthropic.

## License

AGPL-3.0 (inherits LearnHarness's prompts). See [LICENSE](LICENSE).
