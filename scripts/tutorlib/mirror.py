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
import re
from pathlib import Path

from . import blocks, questions
from .vault import append_note, load_state, note_abspath

ASK_TOOL = "AskUserQuestion"

# Claude Code writes a response (its text and its tool call) to the transcript
# only AFTER that tool finishes. So a CLI command can't see the prose written
# just before it, and a block it appended directly would land above that prose.
# Instead the CLI queues its block and prints a marker; the block is placed when
# a flush reaches the tool result carrying the marker — right after the prose.
MARKER_RE = re.compile(r"⟦(b\d+)⟧")


def queue_block(rec: dict, block: str, echo: str | None = None) -> str:
    """`echo`: text Claude will repeat in the chat (an open question or a problem
    statement, so it's visible on a phone). The note already shows it in the
    block, so the repeated copy is dropped from the prose that follows."""
    rec["block_seq"] = rec.get("block_seq", 0) + 1
    token = f"b{rec['block_seq']}"
    rec.setdefault("pending_blocks", []).append({"token": token, "block": block, "echo": echo})
    return token


def place_pending(vault: Path, rec: dict) -> int:
    """Fallback: append queued blocks whose marker never showed up (e.g. the
    turn ended). Called at end of turn and before a new user message."""
    pending = rec.get("pending_blocks") or []
    for item in pending:
        append_note(note_abspath(vault, rec), item["block"])
        if item.get("echo"):
            rec["echo"] = item["echo"]
    rec["pending_blocks"] = []
    return len(pending)


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
            text = "\n\n".join(pending_text)
            echo = rec.get("echo")
            if echo and echo.strip() in text:
                text = text.replace(echo.strip(), "", 1).strip()
                rec["echo"] = None
            pending_text.clear()
            if not text:
                return
            out.append(blocks.assistant_block(text, _next_anchor(rec)))
            # Explanation written since the last answered question (gates checks).
            rec["prose_since_answer"] = rec.get("prose_since_answer", 0) + len(text)

    def emit_queued(content) -> None:
        tokens = set(MARKER_RE.findall(json.dumps(content, ensure_ascii=False)))
        if not tokens:
            return
        keep = []
        for item in rec.get("pending_blocks") or []:
            if item["token"] in tokens:
                emit_text()
                out.append(item["block"])
                if item.get("echo"):
                    rec["echo"] = item["echo"]
            else:
                keep.append(item)
        rec["pending_blocks"] = keep

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
                        emit_queued(c.get("content"))
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
