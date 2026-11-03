"""The md-log port: mirror the conversation into the session note.

Claude Code writes every conversation to a JSONL transcript. We keep a byte
offset per (record, Claude session) and, whenever something needs to land in
the note in order (end of turn, before a question pops up, before a CLI block),
we flush everything new: assistant prose, plus AskUserQuestion Q&A that the
hooks didn't already log. User prompts are written live by the
UserPromptSubmit hook, so flushes only include them when backfilling.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import blocks, questions
from .vault import append_note, load_state, note_abspath

ASK_TOOL = "AskUserQuestion"


def transcript_path(vault: Path, sid: str) -> Path | None:
    st = load_state(vault)
    p = st["transcripts"].get(sid)
    if p and Path(p).exists():
        return Path(p)
    # Fallback: ~/.claude/projects/<escaped cwd>/<sid>.jsonl — search all projects.
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
    for cand in base.glob(f"*/{sid}.jsonl"):
        return cand
    return None


def _next_anchor(rec: dict) -> str:
    rec["block_counter"] = rec.get("block_counter", 0) + 1
    return f"t{rec['block_counter']}"


def log_ask_question(rec: dict, tool_use_id: str, tool_input: dict) -> str | None:
    """Block for an AskUserQuestion about to be shown (quiz or plain question)."""
    if tool_use_id in rec["logged_tool_ids"]:
        return None
    rec["logged_tool_ids"].append(tool_use_id)
    qs = tool_input.get("questions") or []
    quiz = questions.match_quiz(rec, qs)
    if quiz is not None:
        quiz["status"] = "asked"
        quiz["tool_use_id"] = tool_use_id
        return blocks.quiz_question_block(quiz)
    return blocks.ask_question_block(qs)


def log_ask_answer(rec: dict, tool_use_id: str, tool_input: dict, tool_response) -> tuple[str | None, str | None]:
    """(block for the note, context for Claude) once the learner has answered."""
    key = f"{tool_use_id}:answer"
    if key in rec["logged_tool_ids"]:
        return None, None
    rec["logged_tool_ids"].append(key)
    quiz = next((q for q in rec["questions"] if q.get("tool_use_id") == tool_use_id), None)
    if quiz is None:
        quiz = questions.match_quiz(rec, tool_input.get("questions") or [])
    if quiz is not None and quiz["status"] in ("committed", "asked"):
        quiz["tool_use_id"] = tool_use_id
        verdict = questions.grade_quiz(quiz, tool_input, tool_response)
        return blocks.quiz_answer_block(quiz), verdict
    answers, notes = questions.extract_answers(tool_input, tool_response)
    return blocks.ask_answer_block(answers, notes), None


def flush(vault: Path, rec: dict, sid: str, include_user: bool = False, from_start: bool = False) -> int:
    """Append every new transcript entry to the note. Returns blocks written.
    Mutates `rec` (offsets, anchors, logged ids) — caller saves it."""
    tpath = transcript_path(vault, sid)
    if tpath is None:
        return 0
    offsets = rec.setdefault("offsets", {})
    offset = 0 if from_start else offsets.get(sid, 0)
    try:
        with open(tpath, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
    except OSError:
        return 0
    end = data.rfind(b"\n")
    if end < 0:
        return 0
    chunk = data[: end + 1]
    offsets[sid] = offset + len(chunk)

    note = note_abspath(vault, rec)
    out: list[str] = []
    pending_text: list[str] = []
    seen_msg_text: set = set()

    def emit_text():
        if pending_text:
            out.append(blocks.assistant_block("\n\n".join(pending_text), _next_anchor(rec)))
            pending_text.clear()

    for raw in chunk.decode("utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if entry.get("isSidechain") or entry.get("isMeta"):
            continue
        etype = entry.get("type")
        msg = entry.get("message") or {}
        content = msg.get("content")
        if etype == "assistant":
            if msg.get("model") == "<synthetic>":
                continue
            for c in content or []:
                if c.get("type") == "text" and c.get("text", "").strip():
                    key = (msg.get("id"), c["text"])
                    if key in seen_msg_text:
                        continue
                    seen_msg_text.add(key)
                    pending_text.append(c["text"].strip())
                elif c.get("type") == "tool_use" and c.get("name") == ASK_TOOL:
                    emit_text()
                    block = log_ask_question(rec, c.get("id", ""), c.get("input") or {})
                    if block:
                        out.append(block)
        elif etype == "user":
            if isinstance(content, list):
                for c in content:
                    if c.get("type") == "tool_result":
                        tid = c.get("tool_use_id", "")
                        if tid in rec["logged_tool_ids"] and f"{tid}:answer" not in rec["logged_tool_ids"]:
                            emit_text()
                            block, _ = log_ask_answer(
                                rec, tid, _ask_input_for(chunk, tid), entry.get("toolUseResult") or c.get("content")
                            )
                            if block:
                                out.append(block)
                    elif c.get("type") == "text" and include_user:
                        cleaned = blocks.clean_user_text(c.get("text", ""))
                        if cleaned:
                            emit_text()
                            out.append(cleaned if cleaned.startswith("> [!note]") else blocks.user_block(cleaned))
            elif isinstance(content, str) and include_user:
                cleaned = blocks.clean_user_text(content)
                if cleaned:
                    emit_text()
                    out.append(cleaned if cleaned.startswith("> [!note]") else blocks.user_block(cleaned))
    emit_text()
    for block in out:
        append_note(note, block)
    return len(out)


def _ask_input_for(chunk: bytes, tool_use_id: str) -> dict:
    for raw in chunk.decode("utf-8", errors="replace").splitlines():
        if tool_use_id not in raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        for c in (entry.get("message") or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("id") == tool_use_id:
                return c.get("input") or {}
    return {}
