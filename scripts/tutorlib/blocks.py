"""Markdown blocks written into session notes.

The note is meant to be read rendered in Obsidian while the session runs, so a
question block NEVER contains the correct answer or explanation; those are
appended only once the learner has answered.
"""

from __future__ import annotations

import re

from .vault import callout

LABEL_ASSISTANT = "CLAUDE"
LABEL_USER = "YOU"


def user_block(text: str) -> str:
    return f"> [!quote] {LABEL_USER}\n\n{text.strip()}"


def assistant_block(text: str, anchor: str | None) -> str:
    head = f"> [!abstract] {LABEL_ASSISTANT}"
    if anchor:
        # A block id on its own line after the callout → linkable as [[note#^t12]].
        head += f"\n\n^{anchor}"
    return f"{head}\n\n{text.strip()}"


def note_block(text: str) -> str:
    return callout("note", text)


_COMMAND_RE = re.compile(r"<command-name>(.*?)</command-name>", re.S)
_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_NOISE_RE = re.compile(
    r"<(system-reminder|command-message|command-name|command-args|local-command-stdout|local-command-caveat|task-notification)>.*?</\1>",
    re.S,
)


def clean_user_text(text: str) -> str | None:
    """Turn a raw user prompt into reading prose. Slash commands become a note."""
    m = _COMMAND_RE.search(text)
    if m:
        args = _ARGS_RE.search(text)
        cmd = m.group(1).strip()
        arg = args.group(1).strip() if args else ""
        return note_block(f"{cmd} {arg}".strip())
    stripped = _NOISE_RE.sub("", text).strip()
    return stripped or None


# ─── questions ───────────────────────────────────────────────────────────────


def _q_title(q: dict) -> tuple[str, bool]:
    """Title + collapsed flag. Checks arrive collapsed (read the teaching first);
    predictions and probe questions arrive open."""
    node = f" · `{q['nodeId']}`" if q.get("nodeId") else ""
    kind = "Recall" if q["tool"] == "recall" else "Quiz"
    if q.get("type") == "check":
        return f"Check your understanding ({kind.lower()}){node}", True
    if q.get("type") == "predict":
        return f"Predict ({kind.lower()}){node}", False
    if q.get("phase") == "probe":
        return f"Probe ({kind.lower()})", False
    return f"{kind}{node}", False


def quiz_question_block(q: dict) -> str:
    title, collapsed = _q_title(q)
    body: list[str] = q["question"].split("\n")
    if q.get("details"):
        body += [""] + q["details"].split("\n")
    if q["tool"] == "quiz":
        body.append("")
        if q.get("multiSelect"):
            body.append("*Select all that apply.*")
            body.append("")
        for o in q["options"]:
            text = o["text"].split("\n")
            body.append(f"**{o['letter']}.** {text[0]}")
            body += [f"   {t}" for t in text[1:]]
        body.append("**?** I don't know")
    else:
        body += ["", "*Answer in your own words, in the chat.*"]
    return callout("question", title, body, collapsed=collapsed)


def _confidence_line(conf) -> str | None:
    return f"Confidence: {conf}%" if isinstance(conf, (int, float)) else None


def _thinking_lines(label: str, text: str | None) -> list[str]:
    if not text:
        return []
    lines = text.strip().split("\n")
    return ["", f"*{label}:* {lines[0]}", *lines[1:]]


def quiz_answer_block(q: dict) -> str:
    r = q.get("result") or {}
    status = r.get("status")
    if status == "cancelled":
        return callout("warning", "Quiz skipped", ["(no answer)"])
    letters = {o["letter"]: o["text"] for o in q["options"]}
    body: list[str] = []
    if status == "dontknow":
        kind, title = "question", "I don't know"
        body.append("Your answer: I don't know")
    elif status == "other":
        kind, title = "info", "Answered in free text"
        body.append(f"Your answer: {r.get('text', '')}")
    else:
        correct = status == "correct"
        kind = "success" if correct else "failure"
        title = "Correct ✓" if correct else "Incorrect ✗"
        picked = ", ".join(f"{l}. {letters.get(l, '?')}" for l in r.get("picked", [])) or "(none)"
        body.append(f"Your answer: {picked}")
    body.append("Correct answer: " + ", ".join(f"{l}. {letters[l]}" for l in q["correct"]))
    conf = _confidence_line(r.get("confidence"))
    if conf and status in ("correct", "incorrect"):
        body.append(conf)
    body += _thinking_lines("Your thinking", r.get("thinking"))
    if q.get("explanation"):
        body += [""] + q["explanation"].split("\n")
    return callout(kind, title, body)


def recall_answer_block(text: str) -> str:
    return callout("quote", "Your answer", text.strip().split("\n"))


def recall_grade_block(q: dict) -> str:
    r = q.get("result") or {}
    verdict = r.get("verdict")
    kind, title = {
        "correct": ("success", "Correct ✓"),
        "partial": ("warning", "Partly right"),
        "incorrect": ("failure", "Incorrect ✗"),
        "dontknow": ("question", "I don't know"),
    }.get(verdict, ("info", str(verdict)))
    body: list[str] = []
    if r.get("feedback"):
        body += r["feedback"].split("\n") + [""]
    body.append("*Committed answer:*")
    body += q["answer_key"].split("\n")
    return callout(kind, f"Recall: {title}", body)


def ask_question_block(questions: list[dict]) -> str:
    blocks = []
    for item in questions:
        body = item.get("question", "").split("\n")
        opts = item.get("options") or []
        if opts:
            body.append("")
            for i, o in enumerate(opts, 1):
                desc = f": {o['description']}" if o.get("description") else ""
                body.append(f"{i}. {o.get('label', '')}{desc}")
        blocks.append(callout("question", item.get("header") or "Question", body))
    return "\n\n".join(blocks)


def ask_answer_block(answers: dict, notes: dict) -> str:
    if not answers:
        return callout("warning", "Question skipped", ["(no answer)"])
    body: list[str] = []
    for question, answer in answers.items():
        if len(answers) > 1:
            body.append(f"*{question.strip()[:80]}*")
        body.append(str(answer))
        if notes.get(question):
            body += _thinking_lines("Note", notes[question])
        if len(answers) > 1:
            body.append("")
    return callout("example", "Answer", body)


# ─── probe / plan / practice ─────────────────────────────────────────────────


def probe_block(assessment: dict) -> str:
    body: list[str] = []
    if assessment.get("goal"):
        body += [f"**Goal:** {assessment['goal']}", ""]
    if assessment.get("summary"):
        body += assessment["summary"].split("\n") + [""]
    for s in assessment["strands"]:
        body.append(f"- **{s['strand']}**: {s['assessment']}")
    return callout("abstract", "Where you stand: probe assessment", body)


def plan_embed_block(plan_note_name: str, revised: bool) -> str:
    title = "Plan revised" if revised else "Plan"
    return callout("tip", title, [f"![[{plan_note_name}]]"])


def problem_block(p: dict) -> str:
    title = f"Problem {p['n']}"
    return callout("question", title, p["statement"].split("\n"))


def thinking_block(text: str) -> str:
    return callout("quote", "Your thinking", text.strip().split("\n"))


def conclude_block(p: dict) -> str:
    c = p["conclusion"]
    kind = {"solved": "success", "solvedWithHints": "success", "movedOn": "warning",
            "surrendered": "failure", "dismissed": "warning"}.get(c["outcome"], "info")
    label = {"solved": "Solved", "solvedWithHints": "Solved with hints", "movedOn": "Moved on",
             "surrendered": "Surrendered", "dismissed": "Dismissed"}.get(c["outcome"], c["outcome"])
    body = c["verdict"].split("\n")
    meta = []
    if c.get("rung"):
        meta.append(f"hint rung {c['rung']}")
    if c.get("missClass"):
        meta.append(f"miss: {c['missClass']}")
    if c.get("retest"):
        meta.append("marked for retest")
    if meta:
        body += ["", "*" + " · ".join(meta) + "*"]
    out = callout(kind, f"Problem {p['n']}: {label}", body)
    return out + "\n\n" + callout("example", "Model solution", p["solution"].split("\n"), collapsed=True)
