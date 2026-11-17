#!/usr/bin/env python3
"""tutor: the CLI behind the tutor plugin's skills.

Every command that writes into a session note first flushes the conversation
mirror, so blocks land in reading order. Refusals print a message and exit 1:
read it, fix the call, retry.

JSON inputs come from --json, --file, or stdin (use a quoted heredoc so LaTeX
backslashes survive the shell; inside JSON a LaTeX backslash is written \\\\).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tutorlib import blocks, graph, mirror, plan, questions  # noqa: E402
from tutorlib.vault import (  # noqa: E402
    TutorError,
    load_state,
    save_state,
    all_records,
    append_note,
    bind,
    bound_record_id,
    current_sid,
    find_vault,
    folder,
    init_vault,
    load_config,
    load_record,
    locked,
    new_record,
    note_abspath,
    now_iso,
    rel,
    require_bound,
    require_vault,
    safe_filename,
    save_record,
    today,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REFS = PLUGIN_ROOT / "skills"


def ref(skill: str, name: str) -> str:
    return str(REFS / skill / "references" / name)


def read_spec(args) -> dict:
    if getattr(args, "json", None):
        raw = args.json
    elif getattr(args, "file", None):
        raw = Path(args.file).read_text()
    else:
        raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except ValueError as e:
        raise TutorError(
            f"The input is not valid JSON ({e}). In a JSON string, write a LaTeX backslash as \\\\ and a newline as \\n."
        )


def read_text(args, field: str) -> str:
    val = getattr(args, field, None)
    if val:
        return val
    if getattr(args, "file", None):
        return Path(args.file).read_text()
    return sys.stdin.read()


class Session:
    """Locked, flushed access to the bound record for a writing command."""

    def __init__(self):
        self.vault = require_vault()

    def __enter__(self):
        self._lock = locked(self.vault)
        self._lock.__enter__()
        self.rec = require_bound(self.vault)
        self.sid = current_sid()
        self.tokens: list[str] = []
        mirror.flush(self.vault, self.rec, self.sid)
        return self

    def append(self, block: str):
        """Queue the block behind the prose written before this command (see
        mirror.MARKER_RE). Outside Claude Code there is no transcript: append now."""
        if self.sid and mirror.transcript_path(self.vault, self.sid):
            self.tokens.append(mirror.queue_block(self.rec, block))
        else:
            append_note(note_abspath(self.vault, self.rec), block)

    def __exit__(self, *exc):
        try:
            if exc[0] is None:
                save_record(self.vault, self.rec)
                if self.tokens:
                    print("(note markers, ignore: " + " ".join(f"⟦{t}⟧" for t in self.tokens) + ")")
        finally:
            self._lock.__exit__(*exc)


# ─── setup ───────────────────────────────────────────────────────────────────


def cmd_init(args):
    root = init_vault(Path(args.dir or "."), args.folder)
    print(f"Tutor vault ready at {root}. Content folder: {load_config(root)['folder']}/.")
    if not (root / ".obsidian").exists():
        print("No .obsidian/ folder exists here yet. Open this folder as a vault in Obsidian to read the sessions.")


def cmd_status(args):
    vault = find_vault()
    if vault is None:
        print("No tutor vault found from the current directory. Run `tutor.py init <vault-dir>` first.")
        return
    cfg = load_config(vault)
    print(f"vault: {vault}\ncontent folder: {cfg['folder']}/")
    rid = bound_record_id(vault, current_sid())
    if rid:
        rec = load_record(vault, rid)
        print(f"bound session: {rec['title']} ({rec['kind']}, phase {rec['phase']})\nnote: {vault / rec['note']}")
        q = questions.open_question(rec)
        if q:
            print(f"open question: {q['qid']} ({q['tool']}, {q['status']})")
        p = active_problem(rec)
        if p:
            print(f"active problem: {p['n']} ({p['mode']})")
        if rec.get("plan"):
            st = plan.statuses(rec)
            print("plan: " + ", ".join(f"{n['id']}={st[n['id']]}" for n in rec["plan"]["nodes"]))
    else:
        print("bound session: none")
    g = graph.load(vault)
    print(f"graph: {len(g['nodes'])} propositions, {len(g['chains'])} chains")


def print_paths(vault: Path):
    for sub in ("Sessions", "Practice", "Plans", "Graph", "Research", "viz", "demos"):
        print(f"  {sub}: {folder(vault, sub)}")
    print(f"  CLI: python3 {Path(__file__).resolve()}")
    print(f"  render/test helpers: {PLUGIN_ROOT / 'scripts'}")


def cmd_paths(args):
    vault = require_vault()
    print(f"vault: {vault}")
    print_paths(vault)


def _hand_off(vault: Path, sid: str, prev: dict) -> None:
    """Remember where a conversation's mirror stopped, so the next session
    bound in the same conversation starts there instead of re-backfilling."""
    st = load_state(vault)
    st.setdefault("mirrored", {})[sid] = prev.get("offsets", {}).get(sid, 0)
    save_state(vault, st)


def _start_mirror(vault: Path, sid: str, rec: dict) -> int:
    """Backfill a newly bound record from where this conversation's last
    session left off (the conversation's start if it never had one)."""
    offsets = rec.setdefault("offsets", {})
    offsets[sid] = max(offsets.get(sid, 0), load_state(vault).get("mirrored", {}).get(sid, 0))
    return mirror.flush(vault, rec, sid, include_user=True)


# ─── sessions ────────────────────────────────────────────────────────────────


def _new_note_path(dirpath: Path, title: str) -> Path:
    base = f"{today()} {safe_filename(title, 80)}"
    p = dirpath / f"{base}.md"
    n = 2
    while p.exists():
        p = dirpath / f"{base} ({n}).md"
        n += 1
    return p


def cmd_session_start(args):
    vault = require_vault()
    sid = current_sid()
    if not sid:
        raise TutorError("CLAUDE_CODE_SESSION_ID is not set. Run this command from the Bash tool of Claude Code.")
    kind = args.kind
    with locked(vault):
        old = bound_record_id(vault, sid)
        if old:
            prev = load_record(vault, old)
            mirror.flush(vault, prev, sid)
            save_record(vault, prev)
            _hand_off(vault, sid, prev)
        d = folder(vault, "Practice" if kind == "practice" else "Sessions")
        note = _new_note_path(d, args.title)
        g = graph.load(vault)
        targets = []
        for t in args.targets or []:
            nid = graph.resolve_node(g, t)
            if nid is None:
                raise TutorError(f"Unknown proposition {t!r}. To find proposition ids, run `tutor.py graph find <term>`.")
            targets.append(nid)
        rec = new_record(vault, kind, args.title, note, sid)
        rec["targets"] = targets
        note.write_text(
            "\n".join([
                "---",
                "tutor: session",
                f"kind: {kind}",
                f"created: {now_iso()}",
                f"record: {rec['id']}",
                f"tags: [tutor-{kind}]",
                "---",
                f"# {args.title}",
                "",
            ]),
            encoding="utf-8",
        )
        bind(vault, sid, rec["id"])
        _start_mirror(vault, sid, rec)
        save_record(vault, rec)
    print(f"Started {kind} session {rec['id']}: {args.title}")
    print(f"note: {note}")
    print("Tell the learner to open the note in Obsidian. The note shows the session live.")
    print_paths(vault)
    if kind == "teach":
        print(f"\nPhase: probe. Read {ref('teach', 'probe.md')} before your first question.")
    else:
        if targets:
            print("\nPicked propositions (ids for `problem` targets):")
            for nid in targets:
                n = g["nodes"][nid]
                print(f"  [{nid}] {n['name']}: {n['statement']}")
                for c in graph.chains_of(g, nid):
                    nm = lambda i: g["nodes"].get(i, {}).get("name", i)  # noqa: E731
                    print(f"      chain: {' + '.join(nm(p) for p in c['premises'])} ⇒ {nm(c['conclusion'])}")
        print(f"\nRead {ref('practice', 'doctrine.md')} before you pose the first problem.")


def _find_record(vault: Path, ref_: str) -> dict:
    for r in all_records(vault):
        if ref_ in (r["id"], r["note"], Path(r["note"]).stem, r["title"]) or r["note"].endswith(ref_):
            return r
    raise TutorError(f"No session matches {ref_!r}. To list the sessions, run `tutor.py session list`.")


def cmd_session_resume(args):
    vault = require_vault()
    sid = current_sid()
    with locked(vault):
        rec = _find_record(vault, args.ref)
        old = bound_record_id(vault, sid)
        if old and old != rec["id"]:
            prev = load_record(vault, old)
            mirror.flush(vault, prev, sid)
            save_record(vault, prev)
            _hand_off(vault, sid, prev)
        if sid not in rec["claude_sessions"]:
            rec["claude_sessions"].append(sid)
        bind(vault, sid, rec["id"])
        append_note(note_abspath(vault, rec), blocks.note_block(f"Resumed {now_iso()[:16].replace('T', ' ')}"))
        _start_mirror(vault, sid, rec)
        save_record(vault, rec)
    print(f"Resumed {rec['kind']} session {rec['id']} ({rec['title']}), phase {rec['phase']}.")
    print(f"note: {vault / rec['note']}")
    if rec.get("probe"):
        print("\nProbe assessment:\n" + json.dumps(rec["probe"], indent=2, ensure_ascii=False))
    if rec.get("plan"):
        st = plan.statuses(rec)
        print("\nPlan (node: status):")
        for n in rec["plan"]["nodes"]:
            print(f"  {n['id']} [{st[n['id']]}] {n['title']}")
        print("edges: " + ", ".join(f"{a}->{b}" for a, b in rec["plan"]["edges"]))
    recent = rec["questions"][-6:]
    if recent:
        print("\nRecent questions:")
        for q in recent:
            r = q.get("result") or {}
            print(f"  {q['qid']} {q['tool']} {q.get('type') or ''} {q.get('nodeId') or ''}: "
                  f"{q['question'][:90]!r} → {r.get('status') or r.get('verdict') or q['status']}")
    print("\nThe full history is in the note. Read the note before you continue, to update your model of the learner.")


def cmd_session_end(args):
    vault = require_vault()
    sid = current_sid()
    with locked(vault):
        rid = bound_record_id(vault, sid)
        if not rid:
            print("No session is bound to this conversation.")
            return
        rec = load_record(vault, rid)
        mirror.flush(vault, rec, sid)
        mirror.place_pending(vault, rec)
        append_note(note_abspath(vault, rec), blocks.note_block(f"Session paused/ended {now_iso()[:16].replace('T', ' ')}"))
        save_record(vault, rec)
        _hand_off(vault, sid, rec)
        bind(vault, sid, None)
    print(f"Ended {rec['title']}. The note mirror is stopped.")
    if rec["kind"] in ("teach", "log"):
        print(f"To add the taught material to the knowledge graph, dispatch the graph-extractor agent on {vault / rec['note']}.")


def cmd_session_list(args):
    vault = require_vault()
    for r in all_records(vault):
        qs = [q for q in r["questions"] if q["status"] == "graded"]
        right = sum(1 for q in qs if (q.get("result") or {}).get("status") == "correct"
                    or (q.get("result") or {}).get("verdict") == "correct")
        extra = f" · {right}/{len(qs)} correct" if qs else ""
        probs = f" · {len(r['problems'])} problems" if r["problems"] else ""
        print(f"{r['id']} · {r['kind']} · {r['phase']} · {r['title']}{extra}{probs}\n    {r['note']}")


def cmd_log_link(args):
    """md-log port: mirror this conversation into an existing note (backfills)."""
    vault = require_vault()
    sid = current_sid()
    path = Path(args.file).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path) if (Path.cwd() / path).exists() else vault / path
    if not path.is_file():
        raise TutorError(f"File does not exist: {path}. /log links to an existing note. It does not create notes.")
    with locked(vault):
        old = bound_record_id(vault, sid)
        if old:
            prev = load_record(vault, old)
            mirror.flush(vault, prev, sid)
            save_record(vault, prev)
            _hand_off(vault, sid, prev)
        rec = new_record(vault, "log", path.stem, path.resolve(), sid)
        bind(vault, sid, rec["id"])
        n = _start_mirror(vault, sid, rec)
        save_record(vault, rec)
    print(f"Linked {path}. Backfilled {n} blocks. New turns of this conversation go into this note.")


def cmd_flush(args):
    with Session():
        pass


# ─── probe / plan ────────────────────────────────────────────────────────────


def cmd_probe_done(args):
    spec = read_spec(args)
    with Session() as s:
        rec = s.rec
        if rec["kind"] != "teach":
            raise TutorError("probe-done is for teaching sessions only.")
        if rec.get("probe"):
            raise TutorError("The probe is already concluded. Run probe-done one time only.")
        if (q := questions.open_question(rec)) is not None:
            raise TutorError(f"Question {q['qid']} is open. Wait for the answer before you conclude the probe.")
        strands = spec.get("strands")
        if not isinstance(strands, list) or not strands or not all(
            isinstance(x, dict) and x.get("strand") and x.get("assessment") for x in strands
        ):
            raise TutorError('probe-done needs {"goal": ..., "strands": [{"strand": ..., "assessment": ...}, ...]}.')
        rec["probe"] = {"goal": spec.get("goal"), "summary": spec.get("summary"), "strands": strands, "at": now_iso()}
        rec["phase"] = "plan"
        s.append(blocks.probe_block(rec["probe"]))
    print("Probe concluded. The note shows the assessment.")
    print(f"Next:\n1. Read {ref('teach', 'planning.md')} and {ref('teach', 'method.md')}.\n"
          "2. Plan carefully. This is the step with the most effect on the session.\n"
          "3. Write the approach in prose.\n"
          "4. Write the plan map with `tutor.py plan`.")


def cmd_plan(args):
    text = read_text(args, "mermaid")
    with Session() as s:
        rec = s.rec
        if rec["kind"] != "teach":
            raise TutorError("plan is for teaching sessions only.")
        parsed = plan.parse(text)
        revised = rec.get("plan") is not None
        rec["plan"] = parsed
        if rec["phase"] == "probe":
            rec["phase"] = "plan"
        note = note_abspath(s.vault, rec)
        # Keep an existing plan note's name: older session notes embed it.
        plan_path = (s.vault / rec["plan_note"]) if rec.get("plan_note") else folder(s.vault, "Plans") / f"{note.stem} plan.md"
        rec["plan_note"] = rel(s.vault, plan_path)
        plan.write_note(plan_path, rec, note.stem)
        s.append(blocks.plan_embed_block(plan_path.stem, revised))
    print(json.dumps({"ok": True, "nodeIds": [n["id"] for n in parsed["nodes"]]}))
    print("These are the node ids of the plan. From now on, every quiz and recall must use one of them as `nodeId`.")
    if not revised:
        print("The note now shows the map. Do not draw the plan again in your prose.\n"
              "Next:\n1. Ask the learner to confirm the plan.\n2. End your turn.\n"
              f"3. Before you teach, read {ref('teach', 'teaching.md')}.")


def _refresh_plan(vault: Path, rec: dict):
    if rec.get("plan") and rec.get("plan_note"):
        plan.write_note(vault / rec["plan_note"], rec, Path(rec["note"]).stem)


# ─── questions ───────────────────────────────────────────────────────────────


def _min_chars(vault: Path) -> int:
    return int(load_config(vault).get("min_explanation_chars", 400))


def cmd_quiz(args):
    spec = read_spec(args)
    with Session() as s:
        q, payload = questions.commit_quiz(s.rec, spec, _min_chars(s.vault))
        _refresh_plan(s.vault, s.rec)
    print(f"Committed {q['qid']}. The answer key is stored and the options are shuffled.\n"
          "Next:\n1. Call AskUserQuestion with the input below. Do not change it.\n"
          "2. Read the verdict that the hook returns. Then continue the session.")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_recall(args):
    spec = read_spec(args)
    with Session() as s:
        q = questions.commit_recall(s.rec, spec, _min_chars(s.vault))
        s.append(blocks.quiz_question_block(q))
        _refresh_plan(s.vault, s.rec)
    print(f"Committed {q['qid']}. The note shows the question.\n"
          "Next:\n1. Write one short line. Ask the learner to answer in their own words.\n"
          "2. Do not repeat the question. The note shows it.\n"
          "3. End your turn.\n"
          "The next message from the learner is the answer.")


def cmd_grade(args):
    with Session() as s:
        q = questions.grade_recall(s.rec, args.qid, args.verdict, args.feedback)
        s.append(blocks.recall_grade_block(q))
    print(f"Graded {q['qid']}: {args.verdict}. The note now shows the learner your committed answer.")


# ─── practice ────────────────────────────────────────────────────────────────

MODES = ("recall", "discrimination", "composition")
OUTCOMES = ("solved", "solvedWithHints", "movedOn", "surrendered", "dismissed")
RUNGS = ("R0", "R1", "R2", "R3", "R4", "R5")
MISSES = ("cue", "discrimination", "execution", "careless", "structural")


def active_problem(rec: dict) -> dict | None:
    return next((p for p in rec.get("problems", []) if p["status"] == "active"), None)


def cmd_problem(args):
    spec = read_spec(args)
    with Session() as s:
        rec = s.rec
        if (p := active_problem(rec)) is not None:
            raise TutorError(f"Problem {p['n']} is active. Conclude it before you pose the next problem.")
        for f in ("statement", "mode", "solution"):
            if not spec.get(f):
                raise TutorError(f"problem: `{f}` is missing.")
        if spec["mode"] not in MODES:
            raise TutorError(f"problem: `mode` must be one of: {', '.join(MODES)}.")
        targets = []
        if spec.get("target"):
            g = graph.load(s.vault)
            for t in spec["target"]:
                nid = graph.resolve_node(g, t)
                if nid is None:
                    raise TutorError(f"Target {t!r} is not a known proposition. Use ids from the session context. "
                                     "If the material is not in the graph, remove `target`.")
                targets.append(nid)
        p = {
            "n": len(rec["problems"]) + 1,
            "statement": spec["statement"].strip(),
            "mode": spec["mode"],
            "targets": targets,
            "solution": spec["solution"].strip(),
            "status": "active",
            "posed": now_iso(),
            "submissions": [],
        }
        rec["problems"].append(p)
        s.append(blocks.problem_block(p))
    print(f"Posed problem {p['n']}. The solution is committed and hidden.\n"
          "Next: end your turn. Each message from the learner is a submission on this problem.")


def cmd_conclude(args):
    spec = read_spec(args)
    with Session() as s:
        rec = s.rec
        p = active_problem(rec)
        if p is None:
            raise TutorError("No problem is active. Pose a problem first.")
        if spec.get("outcome") not in OUTCOMES:
            raise TutorError(f"conclude: `outcome` must be one of: {', '.join(OUTCOMES)}.")
        if not spec.get("verdict"):
            raise TutorError("conclude: `verdict` is missing.")
        if spec.get("rung") not in (None, *RUNGS):
            raise TutorError("conclude: `rung` must be R0–R5 or null.")
        if spec.get("missClass") not in (None, *MISSES):
            raise TutorError(f"conclude: `missClass` must be one of: {', '.join(MISSES)}, or null.")
        if not isinstance(spec.get("retest"), bool):
            raise TutorError("conclude: `retest` is missing. Use true or false.")
        p["conclusion"] = {k: spec.get(k) for k in ("outcome", "verdict", "rung", "missClass", "retest")}
        p["status"] = "concluded"
        p["concluded"] = now_iso()
        s.append(blocks.conclude_block(p))
        if p["targets"]:
            g = graph.load(s.vault)
            g["practice"].append({
                "at": now_iso(), "record": rec["id"], "note": rec["note"], "problem": p["n"],
                "targets": p["targets"], "mode": p["mode"], **p["conclusion"],
            })
            graph.save(s.vault, g)
            graph.render_notes(s.vault, g)
    print(f"Concluded problem {p['n']}. The note now shows the model solution.\n"
          "Next:\n1. If useful, write your closing words on the work of the learner.\n2. End your turn.\n"
          "Pose the next problem only when the learner asks for it.")


def cmd_practice_status(args):
    vault = require_vault()
    rec = require_bound(vault)
    g = graph.load(vault)
    for p in rec["problems"]:
        c = p.get("conclusion") or {}
        tnames = ", ".join(g["nodes"].get(t, {}).get("name", t) for t in p["targets"]) or "untagged"
        print(f"P{p['n']} [{p['mode']}] {tnames}: {p['status']}"
              + (f" · {c['outcome']} · {c.get('rung') or 'no hints'} · miss={c.get('missClass')}"
                 f"{' · RETEST' if c.get('retest') else ''}" if c else ""))
    pending = [p for p in rec["problems"] if (p.get("conclusion") or {}).get("retest")]
    if pending:
        print("Retest these problems in a new surface before the session ends: " + ", ".join(f"P{p['n']}" for p in pending))
    for nid in rec.get("targets", []):
        hist = graph.practice_history(g, nid)
        if hist:
            print(f"history {g['nodes'][nid]['name']}: " + "; ".join(
                f"{h['at'][:10]} {h['mode']} {h['outcome']}" for h in hist[-5:]))


# ─── graph ───────────────────────────────────────────────────────────────────


def _print_nodes(nodes, g):
    for n in nodes:
        born = g["sources"].get(graph.birth_source(n) or "", {}).get("title", graph.birth_source(n))
        al = f" (aka {', '.join(n['aliases'])})" if n["aliases"] else ""
        print(f"[{n['id']}] {n['name']}{al}: {n['statement']}  ⟨born: {born}⟩")


def cmd_graph(args):
    vault = require_vault()
    if args.gcmd in ("merge", "delete", "render"):
        with locked(vault):
            g = graph.load(vault)
            if args.gcmd == "merge":
                findings = json.loads(Path(args.file).read_text()) if args.file else json.loads(sys.stdin.read())
                res = graph.merge(vault, g, args.source, findings, args.title)
                graph.save(vault, g)
                n = graph.render_notes(vault, g)
                print(f"Merged from {res['source']}: {res['created']} new propositions, {res['linked']} linked to "
                      f"existing nodes, {res['chains']} new chains. {n} notes rendered in {folder(vault, 'Graph')}.")
                print("ids: " + json.dumps(res["ids"]))
            elif args.gcmd == "delete":
                removed = graph.delete_node(g, args.id)
                graph.save(vault, g)
                graph.render_notes(vault, g)
                print(f"Deleted {args.id} and {removed} chains through it.")
            else:
                print(f"Rendered {graph.render_notes(vault, g)} notes.")
        return
    g = graph.load(vault)
    if args.gcmd == "sessions":
        rows = graph.sessions(g)
        if not rows:
            print("The graph is empty.")
        for key, title, count in rows:
            print(f"{count:4d}  {title}  ({key})")
    elif args.gcmd == "list":
        nodes = graph.by_source(g, args.source) if args.source else list(g["nodes"].values())
        _print_nodes(nodes, g)
    elif args.gcmd == "find":
        hits = graph.find(g, args.pattern)
        _print_nodes(hits, g) if hits else print("No matches.")
    elif args.gcmd == "chains":
        nid = graph.resolve_node(g, args.node) if args.node else None
        if args.node and nid is None:
            raise TutorError(f"No node matches {args.node!r}.")
        nm = lambda i: g["nodes"].get(i, {}).get("name", i)  # noqa: E731
        for c in graph.chains_of(g, nid):
            print(f"{' + '.join(c['premises'])} ⇒ {c['conclusion']}   "
                  f"{' ∧ '.join(nm(p) for p in c['premises'])} ⇒ {nm(c['conclusion'])}")
    elif args.gcmd == "show":
        nid = graph.resolve_node(g, args.id)
        if nid is None:
            raise TutorError(f"No node matches {args.id!r}.")
        print(json.dumps({**g["nodes"][nid], "chains": graph.chains_of(g, nid),
                          "practice": graph.practice_history(g, nid)}, indent=2, ensure_ascii=False))
    elif args.gcmd == "digest":
        print(graph.digest(g, args.source) or "(nothing extracted from this source yet)")


# ─── figures and demos ───────────────────────────────────────────────────────


def cmd_render_svg(args):
    src = Path(args.svg)
    out = Path(args.out) if args.out else src.with_suffix(".png")
    last = "neither rsvg-convert nor magick is installed (brew install librsvg)"
    for cmd in (["rsvg-convert", "-z", "2", str(src), "-o", str(out)],
                ["magick", "-density", "192", "-background", "white", str(src), str(out)]):
        exe = shutil.which(cmd[0]) or next((p for p in (f"/opt/homebrew/bin/{cmd[0]}", f"/usr/local/bin/{cmd[0]}")
                                            if Path(p).exists()), None)
        if not exe:
            continue
        res = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=60)
        if res.returncode == 0 and out.exists():
            print(f"Rendered {out}. Now look at it with the Read tool.")
            return
        last = res.stderr or res.stdout
    raise TutorError(f"SVG render failed. Fix the source and render again.\n{last}")


def cmd_publish(args):
    vault = require_vault()
    src = Path(args.path)
    if not src.is_file():
        raise TutorError(f"File not found: {src}.")
    sub = "viz" if args.kind == "viz" else "demos"
    slug = "".join(c if c.isalnum() else "-" for c in args.slug.lower()).strip("-") or args.kind
    name = f"{args.kind}-{slug}-{int(time.time())}{src.suffix}"
    dest = folder(vault, sub) / name
    shutil.copyfile(src, dest)
    print(f"filename: {name}\npath: {dest}")
    if args.kind == "viz":
        print(f"embed: ![[{name}|500]]")
    else:
        print(f"link: [▶ Open the demo: {args.slug}]({dest.as_uri()})")


# ─── argparse ────────────────────────────────────────────────────────────────


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tutor.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create .tutor/ and the content folders in a vault")
    p.add_argument("dir", nargs="?")
    p.add_argument("--folder", default="Learning")
    p.set_defaults(fn=cmd_init)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("paths").set_defaults(fn=cmd_paths)
    sub.add_parser("flush", help="mirror new conversation turns into the note now").set_defaults(fn=cmd_flush)

    ps = sub.add_parser("session").add_subparsers(dest="scmd", required=True)
    p = ps.add_parser("start")
    p.add_argument("--kind", choices=("teach", "practice"), required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--targets", nargs="*", help="practice: proposition ids/names")
    p.set_defaults(fn=cmd_session_start)
    p = ps.add_parser("resume")
    p.add_argument("ref")
    p.set_defaults(fn=cmd_session_resume)
    ps.add_parser("end").set_defaults(fn=cmd_session_end)
    ps.add_parser("list").set_defaults(fn=cmd_session_list)

    pl = sub.add_parser("log").add_subparsers(dest="lcmd", required=True)
    p = pl.add_parser("link")
    p.add_argument("file")
    p.set_defaults(fn=cmd_log_link)
    pl.add_parser("off").set_defaults(fn=cmd_session_end)

    for name, fn in (("probe-done", cmd_probe_done), ("quiz", cmd_quiz), ("recall", cmd_recall),
                     ("problem", cmd_problem), ("conclude", cmd_conclude)):
        p = sub.add_parser(name)
        p.add_argument("--json")
        p.add_argument("--file")
        p.set_defaults(fn=fn)
    p = sub.add_parser("plan")
    p.add_argument("--mermaid")
    p.add_argument("--file")
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("grade")
    p.add_argument("qid")
    p.add_argument("--verdict", required=True)
    p.add_argument("--feedback")
    p.set_defaults(fn=cmd_grade)
    sub.add_parser("practice-status").set_defaults(fn=cmd_practice_status)

    pg = sub.add_parser("graph").add_subparsers(dest="gcmd", required=True)
    pg.add_parser("sessions")
    p = pg.add_parser("list")
    p.add_argument("--source")
    p = pg.add_parser("find")
    p.add_argument("pattern")
    p = pg.add_parser("chains")
    p.add_argument("--node")
    p = pg.add_parser("show")
    p.add_argument("id")
    p = pg.add_parser("digest")
    p.add_argument("--source", required=True)
    p = pg.add_parser("merge")
    p.add_argument("--source", required=True)
    p.add_argument("--file")
    p.add_argument("--title")
    p = pg.add_parser("delete")
    p.add_argument("id")
    pg.add_parser("render")
    for sp in pg.choices.values():
        sp.set_defaults(fn=cmd_graph)

    p = sub.add_parser("render-svg")
    p.add_argument("svg")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_render_svg)
    p = sub.add_parser("publish", help="copy a verified figure/demo into the vault with a unique name")
    p.add_argument("path")
    p.add_argument("--kind", choices=("viz", "demo"), required=True)
    p.add_argument("--slug", required=True)
    p.set_defaults(fn=cmd_publish)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except TutorError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
