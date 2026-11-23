#!/usr/bin/env python3
"""Hook entry point for the tutor plugin (SessionStart, UserPromptSubmit,
PreToolUse/PostToolUse on AskUserQuestion, Stop).

Inert outside a tutor vault, and inert in a vault while no session is bound.
Never fails the session: any error is logged to .tutor/hook-errors.log and
swallowed. It blocks on purpose in one case: a turn ending right after an
explanation, with no question asked (Stop).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tutorlib import blocks, mirror, questions  # noqa: E402
from tutorlib.vault import (  # noqa: E402
    STATE_DIR,
    append_note,
    bound_record_id,
    find_vault,
    load_config,
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


GUARDED_TOOLS = ("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit")
_PROT = r"(?:\.tutor/|/Sessions/|/Plans/)"
# A path-like string literal (no spaces before the protected part), optionally
# built by concatenation, used as open()/Path() target or assigned to a variable.
_PATHLIT = r"(?:\w+\s*\+\s*)?[frb]?['\"][^'\"\s]*" + _PROT
_TARGET_RE = re.compile(r"(?:open|Path)\(\s*(?:[^)]*\+\s*)?[frb]?['\"][^'\"\s]*" + _PROT
                        + r"|\b\w+\s*=\s*" + _PATHLIT)
_WRITE_HINTS = re.compile(r"json\.dump\(|\.write\(|write_text|write_bytes|open\([^)]*['\"][wax]\+?['\"]|shutil\.(copy|move)|os\.(remove|rename|replace)|unlink\(")


def protected_paths(vault: Path) -> list[str]:
    folder = load_config(vault).get("folder", "Learning")
    return [str(vault / ".tutor"), str(vault / folder / "Sessions"), str(vault / folder / "Plans")]


def guard_reason(vault: Path, tool: str, tin: dict) -> str | None:
    """Session notes, plans and .tutor/ are written by the tutor CLI and hooks
    only. A direct write bypasses the checks (in one session the model patched
    the record to defeat the explanation gate) and breaks the note's order."""
    prot = protected_paths(vault)
    folder = load_config(vault).get("folder", "Learning")
    rel_markers = [".tutor/", f"{folder}/Sessions/", f"{folder}/Plans/", f"{folder}/Sessions\"", f"{folder}/Plans\""]
    msg = ("[tutor guard] Blocked: session notes, plans and .tutor/ are written only by the tutor CLI and its hooks. "
           "Use `tutor.py explain`, `quiz`, `recall`, `grade`, `terms add`, `flush`. If a CLI check refuses you, fix what "
           "it names; if you believe the tool is broken, tell the learner. Never work around it.")
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        fp = tin.get("file_path") or tin.get("notebook_path") or ""
        if not fp:
            return None
        try:
            full = str(Path(fp).expanduser().resolve())
        except OSError:
            return None
        return msg if any(full == p or full.startswith(p + os.sep) for p in prot) else None
    cmd = tin.get("command") or ""
    hits = [m for m in rel_markers + prot if m in cmd]
    if not hits:
        return None
    # Only the CLI and read-only commands may touch these paths.
    stripped = re.sub(r"tutor\.py[^\n]*<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\1[ \t]*(?=\n|$)", " ", cmd, flags=re.S)
    stripped = re.sub(r"python3?\s+\S*tutor\.py[^;&|\n]*", " ", stripped)
    if not any(m in stripped for m in rel_markers + prot):
        return None
    redirect = re.search(r">>?\s*['\"]?[^\s;|&'\"]*(\.tutor/|/Sessions/|/Plans/)", stripped)
    tools = re.search(r"\b(tee|sed\s+-i|perl\s+-p?i|mv|cp|rm|truncate|dd|touch|install|rsync)\b[^;|&\n]*(\.tutor/|/Sessions/|/Plans/|Sessions\"|Plans\")", stripped)
    # A script write counts only when a protected path is its target: inside an
    # open()/Path() call, or a string assigned to a variable. A protected path
    # merely mentioned in text (a doc edit, a message) is not a write.
    target = _TARGET_RE.search(stripped)
    script = bool(target) and bool(_WRITE_HINTS.search(stripped))
    return msg if (redirect or tools or script) else None


def stop_reason(rec: dict, payload: dict) -> str | None:
    """Block the end of a turn that explained a node and asked nothing: the
    learner would have to type "ready" to get the question."""
    if payload.get("stop_hook_active") or rec.get("kind") != "teach":
        return None
    explained = (rec.get("explained_since_answer") or []) + (rec.get("setup_since_answer") or [])
    if not explained or questions.open_question(rec) is not None:
        return None
    node = explained[-1]
    return (f"[tutor] You wrote a `tutor explain` block for node `{node}` and are ending the turn without a question. "
            "The note already shows the explanation, and the question dialog waits while the learner reads: ask the "
            "next question now (the check after an explanation, or the prediction a setup prepares). Never end a turn "
            "to wait for the learner to say ready. If the learner asked to pause, run `tutor.py session end` instead.")


EXPLAIN_NOT_IN_CHAT = (
    "[tutor] Your last `tutor explain` block is in the note but not in the chat. The learner may be reading the "
    "terminal or a phone, where the note is not visible. Write the same text as a chat message first (the reply "
    "line, the new terms, then the body), then call AskUserQuestion again with the same input. If you already wrote "
    "it in the same message as this AskUserQuestion call, do not write it again: just call AskUserQuestion again. "
    "Next time, write the copy before `tutor quiz`, not next to the dialog."
)


def explain_copy_reason(rec: dict, payload: dict) -> str | None:
    """At the end of a turn: the explanation must also be in the chat. Checked
    only when Claude Code passes the last message (the transcript can lag)."""
    ex = rec.get("explain_echo")
    last = payload.get("last_assistant_message")
    if payload.get("stop_hook_active") or not ex or not isinstance(last, str):
        return None
    if mirror.is_explain_copy(last, ex.get("text", "")):
        rec["explain_echo"] = None
        return None
    return ("[tutor] Your last `tutor explain` block is not in the chat, so a learner reading the terminal or a phone "
            "has not seen it. Write it now as a chat message (the reply line, the new terms, then the body), then end "
            "the turn as you meant to.")


def spawn_delayed_flush(vault: Path, sid: str) -> None:
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--delayed-flush", str(vault), sid],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def delayed_flush(vault: Path, sid: str, delays=(1.5, 4.0)) -> None:
    for d in delays:
        time.sleep(d)
        with locked(vault):
            rid = bound_record_id(vault, sid)
            if not rid:
                return
            rec = load_record(vault, rid)
            mirror.flush(vault, rec, sid)
            save_record(vault, rec)


def handle(payload: dict):
    event = payload.get("hook_event_name", "")
    sid = payload.get("session_id", "")
    vault = find_vault(payload.get("cwd") or os.getcwd())
    if vault is None:
        return
    if os.environ.get("TUTOR_DEBUG"):
        with open(vault / STATE_DIR / "hook-debug.jsonl", "a") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False)[:20000] + "\n")

    if event == "PreToolUse" and payload.get("tool_name") in GUARDED_TOOLS:
        reason = guard_reason(vault, payload["tool_name"], payload.get("tool_input") or {})
        if reason:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": reason}}))
        return

    with locked(vault):
        remember_transcript(vault, sid, payload.get("transcript_path"))
        rid = bound_record_id(vault, sid)

        if event == "SessionStart":
            ctx = f"Tutor vault: {vault}. Tutor CLI: `python3 {CLI}`."
            if rid:
                rec = load_record(vault, rid)
                ctx += (f" This conversation is bound to the {rec['kind']} session \"{rec['title']}\" "
                        f"(phase {rec['phase']}). Note: {rec['note']}. "
                        f"To see the session state, run `tutor.py session resume {rec['id']}`.")
            emit(event, ctx)
            return

        if not rid:
            return
        rec = load_record(vault, rid)
        note = note_abspath(vault, rec)

        if event == "UserPromptSubmit":
            mirror.flush(vault, rec, sid)
            mirror.place_pending(vault, rec)
            prompt = payload.get("prompt") or ""
            cleaned = blocks.clean_user_text(prompt)
            ctx = None
            missed = rec.pop("explain_echo", None)
            if missed:
                ctx = ("[tutor] Your last `tutor explain` block never appeared in the chat, so the learner may not have "
                       "seen it (they may be reading the terminal or a phone). Before anything else, write it in the "
                       "chat: the reply line, the new terms, then the body.")
            recall = questions.recall_awaiting_answer(rec)
            problem = next((p for p in rec.get("problems", []) if p["status"] == "active"), None)
            if cleaned and recall and not cleaned.startswith("> [!note]"):
                # Only a candidate: it may be an aside. The grade marks what was graded.
                append_note(note, blocks.user_block(cleaned))
                ctx = "\n".join(x for x in (ctx, questions.record_recall_candidate(recall, cleaned)) if x)
            elif cleaned and problem and not cleaned.startswith("> [!note]"):
                append_note(note, blocks.thinking_block(cleaned))
                problem["submissions"].append({"at": payload.get("timestamp"), "text": cleaned})
                ctx = (f"[tutor] Submission {len(problem['submissions'])} on active problem {problem['n']} "
                       f"(mode {problem['mode']}). Your committed solution: {problem['solution']}\n"
                       "Read the text and decide what it is:\n"
                       "- A working trace: give one hint rung. Use the smallest hint that helps.\n"
                       "- A claimed answer: identify the moves and give the verdict.\n"
                       "Conclude the problem only when the learner solves it or asks to end it.")
            elif cleaned:
                append_note(note, cleaned if cleaned.startswith("> [!note]") else blocks.user_block(cleaned))
            save_record(vault, rec)
            emit(event, ctx)
            return

        if event == "PreToolUse" and payload.get("tool_name") == mirror.ASK_TOOL:
            mirror.flush(vault, rec, sid)
            ex = rec.get("explain_echo")
            if ex and not ex.get("refused"):
                ex["refused"] = True  # once: never trap the session in a loop
                save_record(vault, rec)
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": EXPLAIN_NOT_IN_CHAT}}))
                return
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
                rec["prose_since_answer"] = 0
                rec["explained_since_answer"] = []
                rec["setup_since_answer"] = []
                graded = next((q for q in reversed(rec["questions"]) if q.get("tool_use_id") == tid), None)
                if ctx and graded and graded.get("phase") != "probe":
                    # a graded teach-phase quiz: the next explanation opens with the reaction to it
                    rec["reply_due"] = graded["qid"]
            if ctx and rec.get("plan_note"):
                from tutorlib import plan

                plan.write_note(vault / rec["plan_note"], rec, Path(rec["note"]).stem)
            save_record(vault, rec)
            emit(event, ctx)
            return

        if event == "Stop":
            mirror.flush(vault, rec, sid)
            mirror.place_pending(vault, rec)
            save_record(vault, rec)
            # The turn's last text can reach the transcript after this hook runs;
            # without a second flush it shows up in the note only once the learner
            # types something. Flush again shortly, in the background.
            spawn_delayed_flush(vault, sid)
            reason = stop_reason(rec, payload) or explain_copy_reason(rec, payload)
            if reason:
                print(json.dumps({"decision": "block", "reason": reason}))


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--delayed-flush":
        try:
            delayed_flush(Path(sys.argv[2]), sys.argv[3])
        except Exception:
            with open(Path(sys.argv[2]) / STATE_DIR / "hook-errors.log", "a") as fh:
                fh.write(traceback.format_exc() + "\n")
        return
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
