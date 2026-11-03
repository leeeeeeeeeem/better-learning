#!/usr/bin/env python3
"""Hook entry point for the tutor plugin (SessionStart, UserPromptSubmit,
PreToolUse/PostToolUse on AskUserQuestion, Stop).

Inert outside a tutor vault, and inert in a vault while no session is bound.
Never blocks: any failure is logged to .tutor/hook-errors.log and swallowed.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tutorlib import blocks, mirror, questions  # noqa: E402
from tutorlib.vault import (  # noqa: E402
    STATE_DIR,
    append_note,
    bound_record_id,
    find_vault,
    load_record,
    load_state,
    locked,
    note_abspath,
    save_record,
    save_state,
)

CLI = Path(__file__).resolve().parent / "tutor.py"


def emit(event: str, context: str | None):
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


def remember_transcript(vault: Path, sid: str, path: str | None):
    if not path:
        return
    st = load_state(vault)
    if st["transcripts"].get(sid) != path:
        st["transcripts"][sid] = path
        save_state(vault, st)


def handle(payload: dict):
    event = payload.get("hook_event_name", "")
    sid = payload.get("session_id", "")
    vault = find_vault(payload.get("cwd") or os.getcwd())
    if vault is None:
        return
    if os.environ.get("TUTOR_DEBUG"):
        with open(vault / STATE_DIR / "hook-debug.jsonl", "a") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False)[:20000] + "\n")

    with locked(vault):
        remember_transcript(vault, sid, payload.get("transcript_path"))
        rid = bound_record_id(vault, sid)

        if event == "SessionStart":
            ctx = f"Tutor vault detected at {vault}. Tutor CLI: `python3 {CLI}`."
            if rid:
                rec = load_record(vault, rid)
                ctx += (f" This conversation is bound to the {rec['kind']} session \"{rec['title']}\" "
                        f"(phase {rec['phase']}, note {rec['note']}); `tutor.py session resume {rec['id']}` "
                        "prints its state.")
            emit(event, ctx)
            return

        if not rid:
            return
        rec = load_record(vault, rid)
        note = note_abspath(vault, rec)

        if event == "UserPromptSubmit":
            mirror.flush(vault, rec, sid)
            prompt = payload.get("prompt") or ""
            cleaned = blocks.clean_user_text(prompt)
            ctx = None
            recall = questions.recall_awaiting_answer(rec)
            problem = next((p for p in rec.get("problems", []) if p["status"] == "active"), None)
            if cleaned and recall and not cleaned.startswith("> [!note]"):
                append_note(note, blocks.recall_answer_block(cleaned))
                ctx = questions.record_recall_answer(recall, cleaned)
            elif cleaned and problem and not cleaned.startswith("> [!note]"):
                append_note(note, blocks.thinking_block(cleaned))
                problem["submissions"].append({"at": payload.get("timestamp"), "text": cleaned})
                ctx = (f"[tutor] Thinking submission #{len(problem['submissions'])} on active problem {problem['n']} "
                       f"(mode {problem['mode']}). Your committed solution: {problem['solution']}\n"
                       "Read the text: a working trace → one hint rung, minimal; a claimed answer → extract the moves "
                       "and give the verdict. Conclude only when solved or the learner asks to end it.")
            elif cleaned:
                append_note(note, cleaned if cleaned.startswith("> [!note]") else blocks.user_block(cleaned))
            save_record(vault, rec)
            emit(event, ctx)
            return

        if event == "PreToolUse" and payload.get("tool_name") == mirror.ASK_TOOL:
            mirror.flush(vault, rec, sid)
            block = mirror.log_ask_question(rec, payload.get("tool_use_id", ""), payload.get("tool_input") or {})
            if block:
                append_note(note, block)
            save_record(vault, rec)
            return

        if event == "PostToolUse" and payload.get("tool_name") == mirror.ASK_TOOL:
            tid = payload.get("tool_use_id", "")
            tin = payload.get("tool_input") or {}
            if tid not in rec["logged_tool_ids"]:
                mirror.flush(vault, rec, sid)
                block = mirror.log_ask_question(rec, tid, tin)
                if block:
                    append_note(note, block)
            block, ctx = mirror.log_ask_answer(rec, tid, tin, payload.get("tool_response"))
            if block:
                append_note(note, block)
            if ctx and rec.get("plan_note"):
                from tutorlib import plan

                plan.write_note(vault / rec["plan_note"], rec, Path(rec["note"]).stem)
            save_record(vault, rec)
            emit(event, ctx)
            return

        if event == "Stop":
            mirror.flush(vault, rec, sid)
            save_record(vault, rec)


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    try:
        handle(payload)
    except Exception:  # never break the session because of the mirror
        vault = find_vault(payload.get("cwd") or os.getcwd())
        if vault:
            with open(vault / STATE_DIR / "hook-errors.log", "a") as fh:
                fh.write(traceback.format_exc() + "\n")


if __name__ == "__main__":
    main()
