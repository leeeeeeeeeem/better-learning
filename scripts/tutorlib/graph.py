"""The knowledge graph — port of LearnHarness's Library system.

Source of truth: `.tutor/graph.json`. Propositions (true, self-contained ideas)
and reasoning chains (premises that JOINTLY entail a conclusion), each with
provenance back to the session passage (`[[note#^t12]]`) or notes file they
came from. Every proposition is rendered as an Obsidian note whose links
(premises ⇄ conclusions ⇄ sources) make Obsidian's graph view the graph.

The merge is deterministic: the extractor agent submits NEW propositions and
chains, plus identity links (`linkTo`) for propositions that ARE an existing
node — paraphrases merge into the existing node's aliases + provenance.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
from pathlib import Path

from .vault import (
    STATE_DIR,
    TutorError,
    folder,
    now_iso,
    read_json,
    safe_filename,
    write_json,
)

USER_MARKER = "%% tutor: anything below this line is yours and survives regeneration %%"


def graph_path(vault: Path) -> Path:
    return vault / STATE_DIR / "graph.json"


def load(vault: Path) -> dict:
    g = read_json(graph_path(vault), {})
    g.setdefault("version", 1)
    g.setdefault("nodes", {})
    g.setdefault("chains", [])
    g.setdefault("sources", {})
    g.setdefault("practice", [])
    return g


def save(vault: Path, g: dict) -> None:
    write_json(graph_path(vault), g)


def _new_id(name: str, statement: str, taken) -> str:
    seed = f"{name}|{statement}|{now_iso()}"
    for salt in range(100):
        nid = "n_" + hashlib.sha1(f"{seed}|{salt}".encode()).hexdigest()[:8]
        if nid not in taken:
            return nid
    raise RuntimeError("id space exhausted")


def source_key(vault: Path, source: str) -> tuple[str, Path]:
    p = Path(source).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p) if (Path.cwd() / p).exists() else (vault / p)
    p = p.resolve()
    if not p.exists():
        raise TutorError(f"Source note not found: {source}")
    try:
        key = str(p.relative_to(vault))
    except ValueError:
        key = str(p)
    return key, p


# ─── merge ───────────────────────────────────────────────────────────────────


def merge(vault: Path, g: dict, source: str, findings: dict, title: str | None = None) -> dict:
    key, path = source_key(vault, source)
    props = findings.get("propositions")
    chains = findings.get("chains")
    if props is None or chains is None:
        raise TutorError('Findings must include "propositions" and "chains". Use [] for an empty list.')
    local_ids = set()
    problems: list[str] = []
    for p in props:
        for f in ("id", "name", "statement"):
            if not str(p.get(f, "")).strip():
                problems.append(f"proposition {p.get('id', '?')}: `{f}` is missing")
        if p.get("id") in local_ids:
            problems.append(f"local id {p.get('id')} is used more than one time")
        local_ids.add(p.get("id"))
        if p.get("linkTo") and p["linkTo"] not in g["nodes"]:
            problems.append(f"proposition {p['id']}: linkTo {p['linkTo']} is not an existing node id")
    for c in chains:
        prem, concl = c.get("premises") or [], c.get("conclusion")
        if not prem:
            problems.append("a chain needs at least one premise. Put an idea with no argument in the propositions list only")
        for x in [*prem, concl]:
            if x not in local_ids and x not in g["nodes"]:
                problems.append(f'chain endpoint "{x}" is not a submitted id and not an existing node id')
        if concl in prem:
            problems.append(f"chain: conclusion {concl} is also a premise. Remove it from the premises")
    if problems:
        raise TutorError("findings rejected:\n- " + "\n- ".join(sorted(set(problems))))

    at = now_iso()
    g["sources"].setdefault(key, {"title": title or path.stem, "added": at})
    if title:
        g["sources"][key]["title"] = title
    resolved: dict[str, str] = {}
    created = linked = 0
    for p in props:
        point = {"source": key, "at": at}
        if p.get("anchor"):
            point["anchor"] = str(p["anchor"]).lstrip("^")
        if p.get("linkTo"):
            node = g["nodes"][p["linkTo"]]
            for alias in [p["name"], *(p.get("aliases") or [])]:
                if alias != node["name"] and alias not in node["aliases"]:
                    node["aliases"].append(alias)
            node["provenance"].append(point)
            resolved[p["id"]] = node["id"]
            linked += 1
        else:
            nid = _new_id(p["name"], p["statement"], g["nodes"])
            g["nodes"][nid] = {
                "id": nid,
                "name": p["name"].strip(),
                "statement": p["statement"].strip(),
                "aliases": [a for a in (p.get("aliases") or []) if a != p["name"]],
                "provenance": [point],
                "created": at,
            }
            resolved[p["id"]] = nid
            created += 1
    new_chains = 0
    for c in chains:
        prem = sorted({resolved.get(x, x) for x in c["premises"]})
        concl = resolved.get(c["conclusion"], c["conclusion"])
        if concl in prem:
            continue
        existing = next((x for x in g["chains"] if x["conclusion"] == concl and sorted(x["premises"]) == prem), None)
        if existing:
            existing["provenance"].append({"source": key, "at": at})
        else:
            g["chains"].append({"premises": prem, "conclusion": concl, "provenance": [{"source": key, "at": at}]})
            new_chains += 1
    return {"source": key, "created": created, "linked": linked, "chains": new_chains, "ids": resolved}


def delete_node(g: dict, nid: str) -> int:
    if nid not in g["nodes"]:
        raise TutorError(f"No node matches {nid!r}.")
    del g["nodes"][nid]
    before = len(g["chains"])
    g["chains"] = [c for c in g["chains"] if nid != c["conclusion"] and nid not in c["premises"]]
    return before - len(g["chains"])


# ─── queries ─────────────────────────────────────────────────────────────────


def birth_source(node: dict) -> str | None:
    return node["provenance"][0]["source"] if node["provenance"] else None


def sessions(g: dict) -> list[tuple[str, str, int]]:
    counts: dict[str, int] = {}
    for n in g["nodes"].values():
        b = birth_source(n)
        if b:
            counts[b] = counts.get(b, 0) + 1
    return [(k, g["sources"].get(k, {}).get("title", k), c) for k, c in sorted(counts.items())]


def resolve_source(g: dict, ref: str) -> str | None:
    if ref in g["sources"]:
        return ref
    for k, v in g["sources"].items():
        if ref in (Path(k).stem, v.get("title")) or k.endswith(ref):
            return k
    return None


def by_source(g: dict, ref: str) -> list[dict]:
    key = resolve_source(g, ref)
    if key is None:
        raise TutorError(f"No graph source matches {ref!r}. To list the sources, run `tutor.py graph sessions`.")
    return [n for n in g["nodes"].values() if birth_source(n) == key]


def find(g: dict, pattern: str) -> list[dict]:
    pat = pattern.lower()
    if "*" not in pat:
        pat = f"*{pat}*"
    out = []
    for n in g["nodes"].values():
        hay = [n["name"], n["statement"], *n["aliases"]]
        if any(fnmatch.fnmatchcase(h.lower(), pat) for h in hay):
            out.append(n)
    return out


def resolve_node(g: dict, ref: str) -> str | None:
    if ref in g["nodes"]:
        return ref
    low = ref.strip().lower()
    for n in g["nodes"].values():
        if low == n["name"].lower() or low in (a.lower() for a in n["aliases"]):
            return n["id"]
    return None


def chains_of(g: dict, nid: str | None = None) -> list[dict]:
    if nid is None:
        return g["chains"]
    return [c for c in g["chains"] if c["conclusion"] == nid or nid in c["premises"]]


def digest(g: dict, ref: str) -> str:
    key = resolve_source(g, ref)
    if key is None:
        return ""
    ours = [n for n in g["nodes"].values() if any(p["source"] == key for p in n["provenance"])]
    our_chains = [c for c in g["chains"] if any(p["source"] == key for p in c["provenance"])]
    if not ours and not our_chains:
        return ""
    name = lambda i: g["nodes"].get(i, {}).get("name", i)  # noqa: E731
    lines = ["THE GRAPH SO FAR — everything already extracted from this source (reference these ids verbatim):"]
    lines += [f"  {n['id']} | {n['name']} | {' '.join(n['statement'].split())}" for n in ours]
    if our_chains:
        lines.append("DERIVATIONS ALREADY RECORDED (build on these; do not re-derive them):")
        for c in our_chains:
            lines.append(
                f"  [{' + '.join(c['premises'])} ⇒ {c['conclusion']}]  "
                f"{' ∧ '.join(name(p) for p in c['premises'])} ⇒ {name(c['conclusion'])}"
            )
    return "\n".join(lines)


def practice_history(g: dict, nid: str) -> list[dict]:
    return [p for p in g["practice"] if nid in (p.get("targets") or [])]


# ─── notes ───────────────────────────────────────────────────────────────────


def _note_names(g: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    used: dict[str, int] = {}
    for nid, n in sorted(g["nodes"].items(), key=lambda kv: kv[1]["created"]):
        base = safe_filename(n["name"])
        if base.lower() in used:
            base = f"{base} ({nid})"
        used[base.lower()] = 1
        names[nid] = base
    return names


def _yaml_list(items: list[str]) -> str:
    import json as _json

    return "[" + ", ".join(_json.dumps(i, ensure_ascii=False) for i in items) + "]"


def render_notes(vault: Path, g: dict) -> int:
    gdir = folder(vault, "Graph")
    names = _note_names(g)
    link = lambda nid: f"[[{names[nid]}]]" if nid in names else f"`{nid}`"  # noqa: E731
    written = set()
    for nid, n in g["nodes"].items():
        path = gdir / f"{names[nid]}.md"
        user_tail = ""
        old_path = _existing_note_for(gdir, nid)
        if old_path is not None:
            old = old_path.read_text(encoding="utf-8")
            if USER_MARKER in old:
                user_tail = old.split(USER_MARKER, 1)[1].lstrip("\n")
            if old_path != path:
                old_path.unlink()
        derived = [c for c in g["chains"] if c["conclusion"] == nid]
        leads = [c for c in g["chains"] if nid in c["premises"]]
        out = [
            "---",
            "tutor: proposition",
            f"id: {nid}",
            f"aliases: {_yaml_list(n['aliases'])}",
            f"created: {n['created'][:10]}",
            "tags: [proposition]",
            "---",
            f"# {n['name']}",
            "",
            f"> {n['statement']}",
            "",
        ]
        if derived:
            out.append("## Derived from")
            for c in derived:
                out.append("- " + " **+** ".join(link(p) for p in c["premises"]))
            out.append("")
        if leads:
            out.append("## Leads to")
            for c in leads:
                others = [p for p in c["premises"] if p != nid]
                w = f" (together with {', '.join(link(p) for p in others)})" if others else ""
                out.append(f"- {link(c['conclusion'])}{w}")
            out.append("")
        out.append("## Sources")
        seen = set()
        for pt in n["provenance"]:
            src = g["sources"].get(pt["source"], {})
            stem = Path(pt["source"]).stem
            anchor = f"#^{pt['anchor']}" if pt.get("anchor") else ""
            item = f"- [[{stem}{anchor}|{src.get('title', stem)}]] · {pt['at'][:10]}"
            if item not in seen:
                seen.add(item)
                out.append(item)
        hist = practice_history(g, nid)
        if hist:
            out += ["", "## Practice"]
            for h in hist:
                bits = [h["at"][:10], h.get("mode", ""), h.get("outcome", "")]
                if h.get("rung"):
                    bits.append(h["rung"])
                if h.get("missClass"):
                    bits.append(f"miss: {h['missClass']}")
                note = f" · [[{Path(h['note']).stem}]]" if h.get("note") else ""
                out.append("- " + " · ".join(b for b in bits if b) + note)
        out += ["", USER_MARKER, user_tail]
        path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
        written.add(path.name)
    # drop notes for deleted nodes (only generated ones, never user notes)
    for p in gdir.glob("*.md"):
        if p.name not in written and p.name != "_Index.md" and _note_id(p):
            p.unlink()
    _write_index(gdir, g, names)
    return len(written)


def _note_id(p: Path) -> str | None:
    try:
        head = p.read_text(encoding="utf-8")[:400]
    except OSError:
        return None
    if "tutor: proposition" not in head:
        return None
    m = re.search(r"^id: (n_[0-9a-f]+)$", head, re.M)
    return m.group(1) if m else None


def _existing_note_for(gdir: Path, nid: str) -> Path | None:
    for p in gdir.glob("*.md"):
        if _note_id(p) == nid:
            return p
    return None


def _write_index(gdir: Path, g: dict, names: dict[str, str]) -> None:
    out = ["---", "tutor: graph-index", "---", "# Knowledge graph", "",
           f"{len(g['nodes'])} propositions · {len(g['chains'])} reasoning chains. "
           "Open Obsidian's graph view (filter `tag:#proposition`) to see the structure.", ""]
    by: dict[str, list[str]] = {}
    for nid, n in g["nodes"].items():
        by.setdefault(birth_source(n) or "?", []).append(nid)
    for key, ids in sorted(by.items()):
        title = g["sources"].get(key, {}).get("title", key)
        out.append(f"## [[{Path(key).stem}|{title}]]")
        out += [f"- [[{names[i]}]]" for i in sorted(ids, key=lambda i: names[i].lower())]
        out.append("")
    (gdir / "_Index.md").write_text("\n".join(out), encoding="utf-8")
