"""Review questions: spaced retrieval of earlier nodes during a long session.

Every `review_every` completed nodes (a node is completed by its first passed
check), the next node cannot start until one review question has been asked
on an earlier node. A review is also due as the first question after a resume
and before the session ends. A failed review is repaired and re-checked before
the session moves on.

Everything here is derived from the question history, so it never drifts:

  completed nodes   nodes with a passed check, in the order they were completed
  interval          per node, in completed nodes: starts at 2, doubles after a
                    confident passed review, stays after an unsure pass, and
                    drops to 1 after a miss
  age               completed nodes since the node was last retrieved (taught
                    or reviewed)
  priority          age / interval + importance (plan map) + weakness (misses,
                    partials and low-confidence answers on the node)
"""

from __future__ import annotations

from . import plan as planlib

DEFAULT_EVERY = 2


def _passed(q: dict) -> bool:
    r = q.get("result") or {}
    return r.get("status") == "correct" or r.get("verdict") in ("correct", "partial")


def _clean_pass(q: dict) -> bool:
    """A review that counts as retrieved: right, and not a partial."""
    r = q.get("result") or {}
    return r.get("status") == "correct" or r.get("verdict") == "correct"


def _confident(q: dict) -> bool:
    r = q.get("result") or {}
    if r.get("verdict") == "correct":
        return True
    conf = r.get("confidence")
    return isinstance(conf, (int, float)) and conf >= 75


def _weak(q: dict) -> bool:
    r = q.get("result") or {}
    if r.get("status") in ("incorrect", "dontknow") or r.get("verdict") in ("incorrect", "dontknow", "partial"):
        return True
    conf = r.get("confidence")
    return isinstance(conf, (int, float)) and conf <= 50


def completed(rec: dict) -> list[str]:
    """Nodes with a passed check, in completion order."""
    out: list[str] = []
    for q in rec["questions"]:
        if q.get("type") == "check" and q.get("status") == "graded" and _passed(q) and q.get("nodeId") not in out:
            out.append(q["nodeId"])
    return out


def _history(rec: dict) -> tuple[dict, dict, int]:
    """(interval per node, completed-count at last retrieval per node,
    completed-count at the last graded review)."""
    done: list[str] = []
    interval: dict[str, int] = {}
    last: dict[str, int] = {}
    at_last_review = 0
    for q in rec["questions"]:
        if q.get("status") != "graded" or not q.get("nodeId"):
            continue
        n = q["nodeId"]
        if q.get("type") == "check" and _passed(q) and n not in done:
            done.append(n)
            interval.setdefault(n, DEFAULT_EVERY)
            last[n] = len(done)
        elif q.get("type") == "review":
            at_last_review = len(done)
            if _clean_pass(q):
                last[n] = len(done)
                interval[n] = interval.get(n, DEFAULT_EVERY) * (2 if _confident(q) else 1)
            else:
                interval[n] = 1
    return interval, last, at_last_review


def open_recheck(rec: dict) -> str | None:
    """The node of the latest review, if it failed and has not been passed since."""
    for q in reversed(rec["questions"]):
        if q.get("type") == "review" and q.get("status") == "graded":
            return None if _clean_pass(q) else q["nodeId"]
    return None


def due(rec: dict) -> str | None:
    """Why a review is due now: "resume", "recheck", "every", or None."""
    if rec.get("kind") != "teach" or not rec.get("plan"):
        return None
    done = completed(rec)
    if not done:
        return None
    if open_recheck(rec):
        return "recheck"
    if rec.get("review_resume_due"):
        return "resume"
    every = int(rec.get("review_every") or DEFAULT_EVERY)
    _, _, at_last = _history(rec)
    if len(done) >= 2 and len(done) - at_last >= every:
        return "every"
    return None


def end_due(rec: dict) -> bool:
    """The session has taught nodes, and no review was graded since the last one completed."""
    if rec.get("kind") != "teach" or not rec.get("plan"):
        return False
    done = completed(rec)
    _, _, at_last = _history(rec)
    return len(done) >= 2 and at_last < len(done)


def candidates(rec: dict, include_latest: bool = False, top: int = 4) -> list[tuple[str, float, list[str]]]:
    """Completed nodes ranked for review, with the reasons."""
    done = completed(rec)
    if not done:
        return []
    interval, last, _ = _history(rec)
    plan = rec.get("plan") or {"nodes": [], "edges": []}
    titles = {n["id"]: n["title"] for n in plan["nodes"]}
    out = []
    for n in done:
        if n == done[-1] and not include_latest and len(done) > 1:
            continue
        age = len(done) - last.get(n, len(done))
        iv = interval.get(n, DEFAULT_EVERY)
        reasons = [f"{age} nodes since last retrieved (interval {iv})"]
        score = age / iv
        if any(x["id"] == n for x in plan["nodes"]):
            st = planlib.node_stats(plan, n)
            imp = st["descendants"] / st["others"] + (0.5 if st["feeds_goal"] else 0)
            score += imp
            if st["descendants"] / st["others"] >= 0.4:
                reasons.append(f"foundation ({st['descendants']} later nodes depend on it)")
            if st["feeds_goal"]:
                reasons.append("feeds the goal")
        weak = sum(1 for q in rec["questions"] if q.get("nodeId") == n and q.get("status") == "graded"
                   and q.get("type") in ("check", "review") and _weak(q))
        if weak:
            score += 0.5 * weak
            reasons.append(f"{weak} weak answer(s) on it")
        out.append((n, score, [titles.get(n, n)] + reasons))
    out.sort(key=lambda x: -x[1])
    return out[:top]


def describe(rec: dict, why: str) -> str:
    """The instruction shown when a review is due."""
    if why == "recheck":
        n = open_recheck(rec)
        return (f"[tutor] The last review, on `{n}`, was missed. Repair it before anything else: "
                f"`tutor.py explain --node {n}` (with a `reply:` line; the smallest concrete case), then one review "
                f"question on `{n}` again (`\"type\": \"review\", \"nodeId\": \"{n}\"`) from a different angle.")
    head = {
        "resume": "[tutor] Review due: the first question after a resume is a review on an earlier node.",
        "every": "[tutor] Review due: two nodes were completed since the last review. Before the next node starts, "
                 "ask one review question on an earlier node.",
        "end": "[tutor] Review due before the session ends: ask one or two review questions on the most important "
               "nodes. If the learner is only pausing, run `tutor.py session end --pause` instead.",
    }[why]
    rows = candidates(rec, include_latest=why in ("resume", "end"))
    lines = [head, "Use `\"type\": \"review\"` and the reviewed node's id as `nodeId` (closed or open, your choice). "
             "No setup or explanation before it: it tests what they already hold. Ask from a new angle: apply the "
             "idea to a new case, or combine it with a later node. Never reword the original check. "
             "Candidates, highest priority first (you may pick another completed node if it serves them better):"]
    for n, score, reasons in rows:
        lines.append(f"  - {n} ({score:.2f}): " + "; ".join(reasons))
    return "\n".join(lines)


def after_grade(rec: dict, q: dict) -> str:
    """Advice after a graded review."""
    n = q["nodeId"]
    if not _clean_pass(q):
        return (f"[tutor] Review on `{n}` missed. Next: repair with `tutor.py explain --node {n}` (a `reply:` line, "
                "then the smallest concrete case of the idea they missed), then one more review question on "
                f"`{n}` from a different angle. New nodes are refused until it passes.")
    if not _confident(q):
        return ("[tutor] Review passed, but unsure. Reinforce it in one line in the next explanation's `reply:`, then "
                "continue where the session was.")
    return "[tutor] Review passed. Continue where the session was (react to it in the next explanation's `reply:`)."
