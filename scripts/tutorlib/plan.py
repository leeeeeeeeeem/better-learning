"""The plan map — port of LearnHarness's plan_init.

The teacher writes the dependency map once as a mermaid `graph` block and
rewrites it whenever it is wrong. Statuses are never declared: they derive
from the nodeIds that quiz/recall calls tag (current = latest tag, visited =
any earlier tag). The map lives in its own note, embedded in the session note,
so Obsidian shows the live state wherever it is embedded.
"""

from __future__ import annotations

import re
from pathlib import Path

from .vault import TutorError

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
NODE_RE = re.compile(
    r"""^\s*([A-Za-z0-9_-]+)\s*(?:
        \[\s*"(?P<q1>[^"]*)"\s*\] | \[(?P<b>[^\]]*)\] |
        \(\s*"(?P<q2>[^"]*)"\s*\) | \((?P<p>[^)]*)\) |
        \{\s*"(?P<q3>[^"]*)"\s*\} | \{(?P<c>[^}]*)\}
    )""",
    re.X,
)
EDGE_SPLIT = re.compile(r"\s*-{2,}>\s*|\s*-\.->\s*|\s*==>\s*")
HEADER_RE = re.compile(r"^\s*(graph|flowchart)\b", re.I)


def _node_token(tok: str) -> tuple[str, str | None]:
    m = NODE_RE.match(tok)
    if m:
        title = next((m.group(g) for g in ("q1", "b", "q2", "p", "q3", "c") if m.group(g) is not None), None)
        return m.group(1), (title.strip() if title is not None else None)
    return tok.strip(), None


def parse(mermaid: str) -> dict:
    text = mermaid.strip()
    text = re.sub(r"^```(?:mermaid)?\s*|\s*```$", "", text)
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("%%")]
    problems: list[str] = []
    if not lines or not HEADER_RE.match(lines[0]):
        problems.append("The block must start with `graph TD` (or another graph/flowchart direction).")
    else:
        lines = lines[1:]
    nodes: dict[str, str] = {}
    order: list[str] = []
    edges: list[list[str]] = []
    for line in lines:
        s = line.strip().rstrip(";")
        if re.match(r"^(subgraph|end|style|classDef|class|linkStyle|click)\b", s):
            problems.append(f"Unsupported line (no subgraphs/styles/classes): {s}")
            continue
        parts = [p for p in EDGE_SPLIT.split(s) if p.strip()]
        ids = []
        for part in parts:
            part = re.sub(r"^\|[^|]*\|\s*", "", part.strip())  # drop edge labels -->|x|
            nid, title = _node_token(part)
            if not SLUG_RE.match(nid):
                problems.append(f"Invalid node id `{nid}` — ids are lowercase slugs (a-z, 0-9, -, _).")
                continue
            if nid not in nodes:
                order.append(nid)
                nodes[nid] = title or nid
            elif title:
                nodes[nid] = title
            ids.append(nid)
        for a, b in zip(ids, ids[1:]):
            if a == b:
                problems.append(f"Self-loop on `{a}`.")
            elif [a, b] not in edges:
                edges.append([a, b])
    if not nodes:
        problems.append("The map has no nodes.")
    cyc = _find_cycle(order, edges)
    if cyc:
        problems.append("Cycle: " + " → ".join(cyc) + " (edges mean 'prerequisite of'; the map must be a DAG).")
    if problems:
        raise TutorError("plan rejected:\n- " + "\n- ".join(problems))
    return {"nodes": [{"id": n, "title": nodes[n]} for n in order], "edges": edges}


def _find_cycle(order: list[str], edges: list[list[str]]) -> list[str] | None:
    adj: dict[str, list[str]] = {n: [] for n in order}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(n: str):
        color[n] = 1
        stack.append(n)
        for m in adj.get(n, []):
            if color.get(m) == 1:
                return stack[stack.index(m):] + [m]
            if not color.get(m):
                found = dfs(m)
                if found:
                    return found
        stack.pop()
        color[n] = 2
        return None

    for n in order:
        if not color.get(n):
            found = dfs(n)
            if found:
                return found
    return None


def statuses(rec: dict) -> dict[str, str]:
    plan = rec.get("plan") or {"nodes": []}
    ids = {n["id"] for n in plan["nodes"]}
    tags = [t for t in rec.get("tags", []) if t in ids]
    out = {n["id"]: "upcoming" for n in plan["nodes"]}
    for t in tags:
        out[t] = "visited"
    if tags:
        out[tags[-1]] = "current"
    return out


def _label(title: str) -> str:
    return title.replace('"', "'")


def render_note(rec: dict, session_note_name: str) -> str:
    plan = rec["plan"]
    st = statuses(rec)
    # Slugs can collide with mermaid keywords (`end`) or edge syntax (`a--b`),
    # so the rendered diagram uses positional ids.
    mid = {n["id"]: f"n{i}" for i, n in enumerate(plan["nodes"])}
    lines = ["graph TD"]
    for n in plan["nodes"]:
        lines.append(f'  {mid[n["id"]]}["{_label(n["title"])}"]')
    for a, b in plan["edges"]:
        lines.append(f"  {mid[a]} --> {mid[b]}")
    lines.append("  classDef current fill:#f6c453,stroke:#9a6b00,stroke-width:3px,color:#1a1a1a")
    lines.append("  classDef visited fill:#b9e4c0,stroke:#2f7d3e,color:#1a1a1a")
    lines.append("  classDef upcoming fill:#eef0f3,stroke:#9aa3ad,color:#1a1a1a")
    for kind in ("current", "visited", "upcoming"):
        members = [mid[n] for n, s in st.items() if s == kind]
        if members:
            lines.append(f"  class {','.join(members)} {kind}")
    current = next((n["title"] for n in plan["nodes"] if st[n["id"]] == "current"), None)
    where = f"**Now:** {current}" if current else "**Now:** not started"
    return "\n".join([
        "---",
        "tutor: plan",
        f'session: "[[{session_note_name}]]"',
        "---",
        "```mermaid",
        *lines,
        "```",
        f"{where} · 🟨 current · 🟩 visited · ⬜ upcoming",
        "",
    ])


def write_note(path: Path, rec: dict, session_note_name: str) -> None:
    path.write_text(render_note(rec, session_note_name), encoding="utf-8")
