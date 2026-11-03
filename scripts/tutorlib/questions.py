"""Graded questions — the port of the `quiz` / `explain` tools.

The integrity rule from both originals: the correct answer is COMMITTED before
the learner sees the question, and grading runs against that commitment.

  quiz    tutor.py quiz  → stores key, prints the AskUserQuestion payload
          PreToolUse(AskUserQuestion) hook  → question block into the note
          PostToolUse(AskUserQuestion) hook → deterministic grading, answer
                                              block, verdict back to Claude
  recall  tutor.py recall → stores the committed answer, question block
          UserPromptSubmit hook → the learner's reply becomes the answer
          tutor.py grade  → verdict + committed answer revealed
"""

from __future__ import annotations

import json
import random
import re

from . import blocks
from .vault import TutorError, now_iso

LETTERS = "ABC"
DONT_KNOW = "I don't know"
CONFIDENCE_HEADER = "Confidence"
CONFIDENCE_QUESTION = "How confident are you that your answer is correct?"
CONFIDENCE_OPTIONS = [
    ("25%", "Mostly guessing"),
    ("50%", "Coin flip"),
    ("75%", "Fairly sure"),
    ("95%", "Certain"),
]
OPEN_STATUSES = ("committed", "asked", "answered")


def open_question(rec: dict) -> dict | None:
    for q in reversed(rec["questions"]):
        if q["status"] in OPEN_STATUSES:
            return q
    return None


def _next_qid(rec: dict) -> str:
    return f"q{len(rec['questions']) + 1}"


def _phase_fields(rec: dict, spec: dict, tool: str) -> dict:
    """Probe questions carry no plan metadata; teach questions must carry both
    `type` and a valid `nodeId` (that tag is what moves the live plan map)."""
    if rec["phase"] == "probe":
        if spec.get("type") or spec.get("nodeId"):
            raise TutorError("Probe-phase questions take no `type`/`nodeId` — there is no plan yet.")
        return {"phase": "probe", "type": None, "nodeId": None}
    qtype = spec.get("type")
    if qtype not in ("predict", "check"):
        raise TutorError(f"{tool}: `type` is required — \"predict\" (before teaching the step) or \"check\" (after).")
    node = spec.get("nodeId")
    plan = rec.get("plan")
    if plan:
        ids = [n["id"] for n in plan["nodes"]]
        if node not in ids:
            raise TutorError(
                f"{tool}: `nodeId` must be one of the plan's node ids: {', '.join(ids)}. "
                "For an off-map question use AskUserQuestion directly."
            )
    elif node:
        raise TutorError(f"{tool}: there is no plan yet — call `tutor.py plan` first, or omit nodeId.")
    return {"phase": rec["phase"], "type": qtype, "nodeId": node}


def commit_quiz(rec: dict, spec: dict) -> tuple[dict, dict]:
    if (q := open_question(rec)) is not None:
        raise TutorError(f"Question {q['qid']} is still open — one question per turn. Let the learner answer it first.")
    for field in ("question", "options", "correct", "explanation"):
        if not spec.get(field):
            raise TutorError(f"quiz: `{field}` is required.")
    options = [str(o).strip() for o in spec["options"]]
    if not 2 <= len(options) <= 3:
        raise TutorError(
            "quiz: give 2–3 options (AskUserQuestion holds 4 slots; the fourth is always \"I don't know\")."
        )
    if len(set(options)) != len(options):
        raise TutorError("quiz: options must be distinct.")
    correct = spec["correct"] if isinstance(spec["correct"], list) else [spec["correct"]]
    correct = [str(c).strip() for c in correct]
    missing = [c for c in correct if c not in options]
    if missing:
        raise TutorError(f"quiz: correct answer(s) {missing} must match an option's text exactly.")
    multi = bool(spec.get("multiSelect")) or len(correct) > 1
    fields = _phase_fields(rec, spec, "quiz")

    order = options[:]
    if spec.get("shuffle", True):
        random.shuffle(order)
    opts = [{"letter": LETTERS[i], "text": t} for i, t in enumerate(order)]
    q = {
        "qid": _next_qid(rec),
        "tool": "quiz",
        **fields,
        "question": spec["question"].strip(),
        "details": (spec.get("details") or "").strip() or None,
        "options": opts,
        "correct": [o["letter"] for o in opts if o["text"] in correct],
        "multiSelect": multi,
        "explanation": spec["explanation"].strip(),
        "status": "committed",
        "created": now_iso(),
    }
    rec["questions"].append(q)
    if fields["nodeId"]:
        rec["tags"].append(fields["nodeId"])
        rec["phase"] = "teach"
    return q, ask_payload(q)


def _header(q: dict) -> str:
    if q["phase"] == "probe":
        return "Probe"
    return "Predict" if q["type"] == "predict" else "Check"


def ask_payload(q: dict) -> dict:
    """The exact AskUserQuestion input. Option labels are letters: the learner
    reads the rendered (LaTeX) options in Obsidian and picks a letter."""
    options = [{"label": o["letter"], "description": o["text"]} for o in q["options"]]
    options.append({"label": DONT_KNOW, "description": "A genuine gap — better than guessing"})
    question = q["question"] + ("\n\n" + q["details"] if q.get("details") else "")
    return {
        "questions": [
            {"question": question, "header": _header(q), "multiSelect": q["multiSelect"], "options": options},
            {
                "question": CONFIDENCE_QUESTION,
                "header": CONFIDENCE_HEADER,
                "multiSelect": False,
                "options": [{"label": l, "description": d} for l, d in CONFIDENCE_OPTIONS],
            },
        ]
    }


# ─── reading AskUserQuestion results ─────────────────────────────────────────


_PAIR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"')


def extract_answers(tool_input: dict, tool_response) -> tuple[dict, dict]:
    """(answers, notes) keyed by question text — tolerant of the shapes the
    tool result has taken across Claude Code versions."""
    answers: dict = {}
    notes: dict = {}
    sources = []
    if isinstance(tool_response, dict):
        sources.append(tool_response)
        if isinstance(tool_response.get("data"), dict):
            sources.append(tool_response["data"])
    if isinstance(tool_input, dict):
        sources.append(tool_input)
    for src in sources:
        if not answers and isinstance(src.get("answers"), dict):
            answers = dict(src["answers"])
        ann = src.get("annotations")
        if not notes and isinstance(ann, dict):
            for k, v in ann.items():
                if isinstance(v, dict) and v.get("notes"):
                    notes[k] = v["notes"]
    if not answers:
        text = tool_response if isinstance(tool_response, str) else json.dumps(tool_response or "")
        for k, v in _PAIR_RE.findall(text):
            answers[k.replace('\\"', '"')] = v.replace('\\"', '"')
    return answers, notes


def _lookup(d: dict, question: str):
    if question in d:
        return d[question]
    q0 = question.strip()
    for k, v in d.items():
        if k.strip() == q0 or k.strip().startswith(q0[:60]):
            return v
    return None


def match_quiz(rec: dict, questions: list[dict]) -> dict | None:
    if not questions:
        return None
    first = questions[0]
    for q in reversed(rec["questions"]):
        if q["tool"] == "quiz" and q["status"] in ("committed", "asked"):
            payload_q = ask_payload(q)["questions"][0]["question"]
            if first.get("question", "").strip() == payload_q.strip():
                return q
            if first.get("header") in ("Probe", "Predict", "Check", "Quiz"):
                return q
    return None


def _parse_confidence(value) -> int | None:
    if value is None:
        return None
    m = re.search(r"(\d{1,3})", str(value))
    return max(0, min(100, int(m.group(1)))) if m else None


def grade_quiz(q: dict, tool_input: dict, tool_response) -> str:
    """Grade from the AskUserQuestion result; returns the verdict text for Claude."""
    answers, notes = extract_answers(tool_input, tool_response)
    asked = tool_input.get("questions") or []
    main_q = asked[0]["question"] if asked else ask_payload(q)["questions"][0]["question"]
    raw = _lookup(answers, main_q)
    conf_raw = _lookup(answers, CONFIDENCE_QUESTION)
    thinking = "\n".join(
        t for t in (_lookup(notes, main_q), _lookup(notes, CONFIDENCE_QUESTION)) if t
    ) or None

    result: dict = {"answered": now_iso(), "raw": raw, "thinking": thinking}
    if raw is None:
        result["status"] = "cancelled"
    elif DONT_KNOW.lower() in str(raw).lower():
        result["status"] = "dontknow"
    else:
        tokens = [t.strip().rstrip(".") for t in re.split(r"[,;]", str(raw))]
        picked = sorted({t.upper() for t in tokens if t.upper() in [o["letter"] for o in q["options"]]})
        if not picked:
            result.update(status="other", text=str(raw))
        else:
            result["picked"] = picked
            result["status"] = "correct" if picked == sorted(q["correct"]) else "incorrect"
            result["confidence"] = _parse_confidence(conf_raw)
    q["result"] = result
    q["status"] = "graded"

    letters = {o["letter"]: o["text"] for o in q["options"]}
    lines = [f"[tutor] Graded {q['qid']} ({q.get('type') or q['phase']}"
             + (f", node {q['nodeId']}" if q.get("nodeId") else "") + ")."]
    st = result["status"]
    if st == "cancelled":
        lines.append("The learner skipped the question.")
    elif st == "dontknow":
        lines.append("Answer: I don't know — a genuine gap, not a wrong answer (no confidence).")
    elif st == "other":
        lines.append(f"The learner typed instead of choosing: {result['text']!r}. Read it as their answer and respond.")
    else:
        lines.append(f"Verdict: {'CORRECT' if st == 'correct' else 'INCORRECT'}.")
        lines.append("Picked: " + "; ".join(f"{l}. {letters[l]}" for l in result["picked"]))
        lines.append("Correct: " + "; ".join(f"{l}. {letters[l]}" for l in q["correct"]))
        conf = result.get("confidence")
        lines.append(f"Confidence: {conf}%" if conf is not None else "Confidence: not given")
    lines.append(f"Thinking: {thinking}" if thinking else "Thinking: (none)")
    lines.append("The learner has already seen the verdict, correct answer and explanation in the note.")
    return "\n".join(lines)


# ─── free recall ─────────────────────────────────────────────────────────────


def commit_recall(rec: dict, spec: dict) -> dict:
    if (q := open_question(rec)) is not None:
        raise TutorError(f"Question {q['qid']} is still open — one question per turn.")
    for field in ("question", "answer"):
        if not spec.get(field):
            raise TutorError(f"recall: `{field}` is required (answer = your full committed answer, reasoning included).")
    fields = _phase_fields(rec, spec, "recall")
    q = {
        "qid": _next_qid(rec),
        "tool": "recall",
        **fields,
        "question": spec["question"].strip(),
        "details": (spec.get("details") or "").strip() or None,
        "answer_key": spec["answer"].strip(),
        "status": "asked",
        "created": now_iso(),
    }
    rec["questions"].append(q)
    if fields["nodeId"]:
        rec["tags"].append(fields["nodeId"])
        rec["phase"] = "teach"
    return q


def recall_awaiting_answer(rec: dict) -> dict | None:
    q = open_question(rec)
    return q if q and q["tool"] == "recall" and q["status"] == "asked" else None


def record_recall_answer(q: dict, text: str) -> str:
    q["status"] = "answered"
    q["result"] = {"text": text, "answered": now_iso()}
    return (
        f"[tutor] This message is the learner's answer to recall question {q['qid']}: {q['question']!r}.\n"
        f"Your COMMITTED answer (grade strictly against it — never revise it now): {q['answer_key']}\n"
        "Grade it with `tutor.py grade " + q["qid"] + " --verdict correct|partial|incorrect|dontknow "
        "--feedback \"...\"` BEFORE writing your reaction. A near-miss is partial: name exactly what they "
        "got and what they missed. Their text may be dictated speech — read it leniently for transcription noise."
    )


def grade_recall(rec: dict, qid: str, verdict: str, feedback: str | None) -> dict:
    q = next((x for x in rec["questions"] if x["qid"] == qid), None)
    if q is None or q["tool"] != "recall":
        raise TutorError(f"No recall question {qid} in this session.")
    if q["status"] == "asked":
        raise TutorError(f"{qid} has no answer yet — wait for the learner.")
    if q["status"] == "graded":
        raise TutorError(f"{qid} is already graded.")
    if verdict not in ("correct", "partial", "incorrect", "dontknow"):
        raise TutorError("--verdict must be correct, partial, incorrect, or dontknow.")
    q["result"] = {**(q.get("result") or {}), "verdict": verdict, "feedback": feedback, "graded": now_iso()}
    q["status"] = "graded"
    return q


def question_block(q: dict) -> str:
    return blocks.quiz_question_block(q)
