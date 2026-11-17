---
name: log
description: Mirror the current conversation into an existing markdown note (e.g. in Obsidian) so it can be read rendered (LaTeX, mermaid, code) instead of in the terminal. Backfills the conversation so far, then appends each new turn and every AskUserQuestion Q&A live. Use when the user asks to log/mirror/link the conversation to a note (/better-learning:log <file>, /better-learning:log off).
argument-hint: "<path/to/note.md> | off"
disable-model-invocation: true
---

# Log: link this conversation to a note

`tutor` = `python3 <this skill's base directory>/../../scripts/tutor.py`.

- `/better-learning:log <file>` → `tutor log link "<file>"`. The file must already exist (this never creates notes: a typo'd path shouldn't scatter files around the vault). It backfills the conversation so far, then hooks append every new user message, your prose, and AskUserQuestion questions/answers as callouts. Report the one-line result.
- `/better-learning:log off` → `tutor log off`.

Requires a tutor vault (`tutor status`; `tutor init <vault>` if missing: ask first). Teaching and practice sessions log automatically; this is for any other conversation.
