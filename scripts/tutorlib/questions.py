"""Graded questions — the port of the `quiz` / `explain` tools.

The integrity rule from both originals: the correct answer is COMMITTED before
the learner sees the question, and grading runs against that commitment.

  quiz    tutor.py quiz  → stores key, prints the AskUserQuestion payload
          PreToolUse(AskUserQuestion) hook  → question block into the note
          PostToolUse(AskUserQuestion) hook → deterministic grading, answer
                                              block, verdict back to Claude
  recall  tutor.py recall → stores the committed answer, question block
          UserPromptSubmit hook → each learner message becomes a CANDIDATE
                                  answer (it may be an aside instead)
          tutor.py grade  → verdict on the chosen candidate + committed
                            answer revealed

Teach-phase questions also declare `uses` (see terms.py), and a check needs a
`tutor explain` block for its node since the last answer.
"""

from __future__ import annotations

import json
import random
import re

from . import blocks
from . import terms as termslib
from .unimath import to_unicode
from . import plan as planlib
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
            raise TutorError("Probe questions do not take `type` or `nodeId`. The session has no plan yet.")
        return {"phase": "probe", "type": None, "nodeId": None}
    qtype = spec.get("type")
    if qtype not in ("predict", "check"):
        raise TutorError(
            f"{tool}: `type` is missing. Use \"predict\" before you teach the step. Use \"check\" after you teach the step."
        )
    node = spec.get("nodeId")
    plan = rec.get("plan")
    if plan:
        ids = [n["id"] for n in plan["nodes"]]
        if node not in ids:
            raise TutorError(
                f"{tool}: `nodeId` must be a node id from the plan: {', '.join(ids)}. "
                "For a question that is not about a plan node, use AskUserQuestion directly."
            )
    elif node:
        raise TutorError(
            f"{tool}: the session has no plan yet. To ask now, remove `nodeId`. "
            "To tag the question, write the plan with `tutor.py plan` first."
        )
    return {"phase": rec["phase"], "type": qtype, "nodeId": node}


def _require_prediction(rec: dict, fields: dict, tool: str) -> None:
    """Every plan node opens with a prediction: no check on a node before one."""
    if fields["type"] != "check":
        return
    node = fields["nodeId"]
    if not any(q.get("nodeId") == node and q.get("type") == "predict" for q in rec["questions"]):
        raise TutorError(
            f"{tool}: node `{node}` has no prediction yet. Every node starts with a prediction. "
            f"Ask a predict question on `{node}` first. After the answer, write the explanation, then ask the check."
        )


def _passed(q: dict) -> bool:
    r = q.get("result") or {}
    return r.get("status") == "correct" or r.get("verdict") in ("correct", "partial")


def _require_explanation(rec: dict, fields: dict, tool: str, min_chars: int) -> None:
    """A check needs a `tutor explain` block for its node since the last answer.
    Chat prose does not count: in past sessions the "explanation" existed only in
    the model's thinking, and nothing reached the learner. Exception: a follow-up
    check right after a passed check on the same node (two checks on one node).
    After a failed check, the repair is an explanation, so the gate applies."""
    if fields["type"] != "check":
        return
    graded = [q for q in rec["questions"] if q["status"] == "graded"]
    last = graded[-1] if graded else None
    if last and last.get("type") == "check" and last.get("nodeId") == fields["nodeId"] and _passed(last):
        return
    if fields["nodeId"] in (rec.get("explained_since_answer") or []):
        return
    raise TutorError(
        f"{tool}: no `tutor explain` block for node `{fields['nodeId']}` since the last answer. "
        "The explanation is always required; its length depends on the answer.\n"
        "Text in the chat or in your thinking does not count, and the learner may not have seen it: "
        "if you believe you already explained, you most likely wrote it only in your thinking.\n"
        "Next:\n1. Write the explanation (or the repair, after a wrong check) with "
        f"`tutor.py explain --node {fields['nodeId']}`.\n"
        "2. Run this command again, in the same turn. Never end the turn to wait for the learner to say ready.\n"
        "Never write to the note or to .tutor/ yourself to get past this check."
    )


def _check_terms(rec: dict, spec: dict, fields: dict, tool: str, prior) -> list[str] | None:
    """Teach-phase questions declare `uses`; every term must be known."""
    if fields["phase"] == "probe" or rec.get("kind") != "teach" or prior is None:
        return None
    return termslib.check_question(rec, prior, spec, tool)


def commit_quiz(rec: dict, spec: dict, min_chars: int = 400, prior: list | None = None) -> tuple[dict, dict]:
    if (q := open_question(rec)) is not None:
        raise TutorError(f"Question {q['qid']} is open. Ask one question per turn. Wait for the answer of the learner.")
    for field in ("question", "options", "correct", "explanation"):
        if not spec.get(field):
            raise TutorError(f"quiz: `{field}` is missing.")
    options = [str(o).strip() for o in spec["options"]]
    if not 2 <= len(options) <= 3:
        raise TutorError(
            "quiz: give 2 or 3 options. AskUserQuestion holds 4 options, and the fourth option is always \"I don't know\"."
        )
    if len(set(options)) != len(options):
        raise TutorError("quiz: two options have the same text. Make each option different.")
    correct = spec["correct"] if isinstance(spec["correct"], list) else [spec["correct"]]
    correct = [str(c).strip() for c in correct]
    missing = [c for c in correct if c not in options]
    if missing:
        raise TutorError(f"quiz: each correct answer must be the exact text of one option. These do not match: {missing}.")
    multi = bool(spec.get("multiSelect")) or len(correct) > 1
    fields = _phase_fields(rec, spec, "quiz")
    _require_prediction(rec, fields, "quiz")
    _require_explanation(rec, fields, "quiz", min_chars)
    uses = _check_terms(rec, spec, fields, "quiz", prior)

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
        "uses": uses,
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
    """The exact AskUserQuestion input. The dialog (terminal, or the Claude app
    over remote control) doesn't render LaTeX, so its math is converted to
    Unicode; the note keeps the LaTeX. Option labels are letters."""
    options = [{"label": o["letter"], "description": to_unicode(o["text"])} for o in q["options"]]
    options.append({"label": DONT_KNOW, "description": "A genuine gap. Better than guessing."})
    question = to_unicode(q["question"] + ("\n\n" + q["details"] if q.get("details") else ""))
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
        lines.append("Answer: I don't know. This is a gap, not a wrong answer. There is no confidence value.")
    elif st == "other":
        lines.append(f"The learner typed text and did not select an option: {result['text']!r}. Use this text as their answer.")
    else:
        lines.append(f"Verdict: {'CORRECT' if st == 'correct' else 'INCORRECT'}.")
        lines.append("Picked: " + "; ".join(f"{l}. {letters[l]}" for l in result["picked"]))
        lines.append("Correct: " + "; ".join(f"{l}. {letters[l]}" for l in q["correct"]))
        conf = result.get("confidence")
        lines.append(f"Confidence: {conf}%" if conf is not None else "Confidence: not given")
    lines.append(f"Thinking: {thinking}" if thinking else "Thinking: (none)")
    lines.append("The note already shows the learner the verdict, the correct answer, and your explanation. "
                 "Do not repeat the explanation.")
    return "\n".join(lines)


# ─── check advice ────────────────────────────────────────────────────────────
#
# The doctrine leaves the check mix to the teacher, but a long session drifts
# into one closed check per node. So the verdict that reaches the teacher also
# carries the evidence for this node and a suggestion, at the moment the
# decision is made.


def _weak(q: dict) -> str | None:
    r = q.get("result") or {}
    if r.get("status") in ("incorrect", "dontknow", "other") or r.get("verdict") in ("incorrect", "dontknow"):
        return "the prediction was wrong or unknown" if q.get("type") == "predict" else None
    if r.get("verdict") == "partial":
        return "the answer was only partly right"
    conf = r.get("confidence")
    if isinstance(conf, (int, float)) and conf <= 50:
        return f"the answer was right, but at {int(conf)}% confidence"
    return None


def _importance(rec: dict, nid: str) -> list[str]:
    plan = rec.get("plan")
    if not plan:
        return []
    st = planlib.node_stats(plan, nid)
    out = []
    if st["descendants"] / st["others"] >= 0.4:
        out.append(f"foundation node ({st['descendants']} of {st['others']} other nodes depend on it)")
    if st["in_degree"] >= 3 or (st["in_degree"] >= 2 and st["ancestors"] / st["others"] >= 0.5):
        out.append(f"synthesis node (builds on {st['ancestors']} of {st['others']} other nodes)")
    if st["feeds_goal"]:
        out.append("it feeds the goal directly")
    return out


def check_advice(rec: dict, q: dict) -> str:
    """Next-step advice after a graded teach-phase question (prediction or check)."""
    node = q.get("nodeId")
    if not node or q.get("phase") == "probe":
        return ""
    if q.get("type") == "predict":
        reasons = _importance(rec, node)
        # Low confidence is normal on a prediction (it's a guess about something
        # not taught yet), so only a wrong or unknown prediction counts here.
        r = q.get("result") or {}
        if r.get("status") in ("incorrect", "dontknow") or r.get("verdict") in ("incorrect", "dontknow"):
            reasons.append("the prediction was wrong or unknown")
        q["advice_checks"] = 2 if reasons else 1
        lines = [f"[tutor] Next for node `{node}`: write the explanation with `tutor.py explain --node {node}` "
                 "(its length depends on this prediction), then ask the check in this same turn. "
                 "Do not end the turn in between, and never ask the learner to say ready."]
        if reasons:
            lines.append("Suggested checks: two, at least one open (`tutor.py recall`). Reasons: " + "; ".join(reasons) + ".")
        else:
            lines.append("Suggested checks: one. A closed check is enough, unless the node is a definition or "
                         "mechanism the learner must state in their own words. Then use an open check.")
        lines.append("This is a suggestion. Decide from the evidence (teaching.md, \"Choosing the checks\").")
        return "\n".join(lines)
    # a check
    r = q.get("result") or {}
    passed = r.get("status") == "correct" or r.get("verdict") in ("correct", "partial")
    if not passed:
        return (f"[tutor] Next for node `{node}`: repair. Write a new explanation for this miss with "
                f"`tutor.py explain --node {node}`, then check again in this same turn. If the miss is a committed belief "
                "about a derivation, repair it on the smallest concrete case (scalars, small numbers) the learner computes, "
                "before the general form. Use the other instrument (open or closed) if it shows the gap better.")
    last_predict = max((i for i, x in enumerate(rec["questions"]) if x.get("nodeId") == node and x.get("type") == "predict"),
                       default=-1)
    checks = [x for x in rec["questions"][last_predict + 1:] if x.get("nodeId") == node and x.get("type") == "check"]
    suggested = rec["questions"][last_predict].get("advice_checks", 1) if last_predict >= 0 else 1
    weak = _weak(q)
    if len(checks) >= 2:
        if weak:
            return (f"[tutor] Node `{node}` had {len(checks)} checks and {weak}. Do not add another check. "
                    "If you are still unsure, repair the node, then check again.")
        return f"[tutor] Next: the prediction for the next node."
    if len(checks) < suggested or weak:
        why = weak or "the suggestion for this node was two checks"
        other = ("make it open (`tutor.py recall`), so the learner states the idea in their own words"
                 if q["tool"] == "quiz" else
                 "make it closed, with the confusion you saw as a distractor, or open on a different angle")
        return f"[tutor] Next for node `{node}`: a follow-up check ({why}). The first check was {'closed' if q['tool'] == 'quiz' else 'open'}: {other}."
    return "[tutor] Next: the prediction for the next node."


# ─── free recall ─────────────────────────────────────────────────────────────


def commit_recall(rec: dict, spec: dict, min_chars: int = 400, prior: list | None = None) -> dict:
    if (q := open_question(rec)) is not None:
        raise TutorError(f"Question {q['qid']} is open. Ask one question per turn. Wait for the answer of the learner.")
    for field in ("question", "answer"):
        if not spec.get(field):
            raise TutorError(f"recall: `{field}` is missing. `answer` is your full committed answer, with the reasoning.")
    fields = _phase_fields(rec, spec, "recall")
    _require_prediction(rec, fields, "recall")
    _require_explanation(rec, fields, "recall", min_chars)
    uses = _check_terms(rec, spec, fields, "recall", prior)
    q = {
        "qid": _next_qid(rec),
        "tool": "recall",
        **fields,
        "question": spec["question"].strip(),
        "details": (spec.get("details") or "").strip() or None,
        "answer_key": spec["answer"].strip(),
        "uses": uses,
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


def record_recall_candidate(q: dict, text: str) -> str:
    """A learner message while a recall question is open. It is only a candidate:
    it may be the answer, an addition or correction to an earlier candidate, or an
    aside (a question about the material, a request, logistics)."""
    cands = q.setdefault("candidates", [])
    cands.append({"n": len(cands) + 1, "text": text, "at": now_iso()})
    earlier = ""
    if len(cands) > 1:
        earlier = ("\nEarlier candidates for this question (not graded): "
                   + " | ".join(f"#{c['n']}: {c['text'][:200]!r}" for c in cands[:-1]))
    return (
        f"[tutor] Recall question {q['qid']} is open: {q['question']!r}.\n"
        f"This message is candidate #{cands[-1]['n']}. Decide what it is before you act:\n"
        "- The answer (or a corrected or completed version of an earlier candidate): grade it against your "
        f"committed answer with `tutor.py grade {q['qid']} --verdict correct|partial|incorrect|dontknow --feedback \"...\"`. "
        "The grade uses the latest candidate. If the answer is spread over several candidates, add "
        "`--answer \"<the learner's full answer, combined>\"`. Then write your reaction.\n"
        "- An aside (a question about the material, a request to clarify or resend, logistics, a complaint): do NOT grade. "
        "Answer it (for teaching content, `tutor.py explain` without --node), then end your turn by repeating the open "
        "question. It stays open, and nothing is recorded as the answer.\n"
        "- A request to skip the question: `tutor.py grade "
        f"{q['qid']} --verdict skipped --feedback \"...\"`.\n"
        f"Your committed answer: {q['answer_key']}\n"
        "Do not change the committed answer. A partly correct answer is `partial`: in the feedback, state what the learner "
        "got and what they missed. The learner may dictate answers. Ignore transcription errors."
        + earlier
    )


VERDICTS = ("correct", "partial", "incorrect", "dontknow", "skipped")


def grade_recall(rec: dict, qid: str, verdict: str, feedback: str | None, answer: str | None = None) -> dict:
    q = next((x for x in rec["questions"] if x["qid"] == qid), None)
    if q is None or q["tool"] != "recall":
        raise TutorError(f"Recall question {qid} does not exist in this session.")
    if q["status"] == "graded":
        raise TutorError(f"{qid} is already graded. Do not grade it again.")
    if verdict not in VERDICTS:
        raise TutorError("--verdict must be one of: " + ", ".join(VERDICTS) + ".")
    cands = q.get("candidates") or []
    legacy = (q.get("result") or {}).get("text") if q["status"] == "answered" else None
    if verdict == "skipped":
        text = None
    elif answer:
        text = answer.strip()
    elif cands:
        text = cands[-1]["text"]
    elif legacy:
        text = legacy
    else:
        raise TutorError(f"{qid} has no answer yet. Wait for the answer of the learner.")
    q["result"] = {**(q.get("result") or {}), "text": text, "verdict": verdict, "feedback": feedback,
                   "answered": (cands[-1]["at"] if cands else (q.get("result") or {}).get("answered")),
                   "graded": now_iso()}
    q["status"] = "graded"
    rec["prose_since_answer"] = 0
    rec["explained_since_answer"] = []
    return q


def question_block(q: dict) -> str:
    return blocks.quiz_question_block(q)
