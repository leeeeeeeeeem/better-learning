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


def _remember_anchor_block(rec: dict, key: str, block: str) -> None:
    """Blocks that prose written in the same step can only reach the note after:
    an AskUserQuestion (logged by PreToolUse before the step is in the
    transcript) and an open question whose chat copy carries an intro line.
    Kept so that late prose can be inserted above them (insert_before)."""
    anchors = rec.setdefault("anchor_blocks", {})
    anchors[key] = block
    for k in list(anchors)[:-8]:
        del anchors[k]


def insert_before(note: Path, anchor_block: str | None, text: str, out: list[str]) -> None:
    """Put `text` right above `anchor_block`: in this flush's pending output if
    the block is there, else in the note file. Falls back to appending."""
    if anchor_block:
        if anchor_block in out:
            out.insert(out.index(anchor_block), text)
            return
        try:
            current = note.read_text()
        except OSError:
            current = ""
        i = current.rfind(anchor_block.rstrip("\n"))
        if i >= 0:
            note.write_text(current[:i] + text.rstrip("\n") + "\n\n" + current[i:])
            return
    out.append(text)


def place_pending(vault: Path, rec: dict) -> int:
    """Fallback: append queued blocks whose marker never showed up (e.g. the
    turn ended). Called at end of turn and before a new user message."""
    pending = rec.get("pending_blocks") or []
    for item in pending:
        append_note(note_abspath(vault, rec), item["block"])
        if item.get("echo"):
            rec["echo"] = item["echo"]
            _remember_anchor_block(rec, "echo", item["block"])
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
        block = blocks.quiz_question_block(quiz)
    else:
        block = blocks.ask_question_block(qs)
    _remember_anchor_block(rec, tool_use_id, block)
    return block


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
        advice = questions.check_advice(rec, quiz)
        return blocks.quiz_answer_block(quiz), verdict + ("\n" + advice if advice else "")
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

    def emit_text(before: str | None = None):
        """`before`: a block already written that this prose was meant to precede."""
        if pending_text:
            text = "\n\n".join(pending_text)
            pending_text.clear()
            echo = rec.get("echo")
            if echo and echo.strip() in text:
                # The chat copy of an open question: drop it, and put the line
                # that introduced it above the question block, where it belongs.
                intro, _, rest = text.partition(echo.strip())
                rec["echo"] = None
                intro, rest = intro.strip(), rest.strip()
                if intro:
                    insert_before(note, (rec.get("anchor_blocks") or {}).get("echo"),
                                  blocks.assistant_block(intro, _next_anchor(rec)), out)
                    rec["prose_since_answer"] = rec.get("prose_since_answer", 0) + len(intro)
                text = rest
            if not text:
                return
            block = blocks.assistant_block(text, _next_anchor(rec))
            if before:
                insert_before(note, before, block, out)
            else:
                out.append(block)
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
                    _remember_anchor_block(rec, "echo", item["block"])
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
                    tid = c.get("id", "")
                    if tid in rec["logged_tool_ids"]:
                        # PreToolUse already wrote this question (and maybe its
                        # verdict): prose from the same step goes above it.
                        emit_text(before=(rec.get("anchor_blocks") or {}).get(tid))
                        continue
                    emit_text()
                    block = log_ask_question(rec, tid, c.get("input") or {})
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
