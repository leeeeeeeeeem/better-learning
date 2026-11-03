"""Vault location, config, persistent state, session records, note appends.

Layout inside the vault (the directory that holds `.tutor/`):

    .tutor/                 hidden state (Obsidian ignores dot-folders)
      config.json           {"folder": "Learning"}
      state.json            Claude session id -> bound record, transcript offsets
      sessions/<rid>.json   one structured record per learning session
      graph.json            the knowledge graph (source of truth)
    <folder>/Sessions/      teaching session notes (the md-log mirror)
    <folder>/Practice/      practice session notes
    <folder>/Plans/         live plan maps (embedded in session notes)
    <folder>/Graph/         one note per proposition (generated from graph.json)
    <folder>/Research/      research / PDF briefs
    <folder>/viz/           verified figures (PNG)
    <folder>/demos/         verified interactive demos (HTML)
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import fcntl
import json
import os
import re
import secrets
from pathlib import Path

STATE_DIR = ".tutor"
DEFAULT_CONFIG = {"folder": "Learning"}
SUBFOLDERS = ("Sessions", "Practice", "Plans", "Graph", "Research", "viz", "demos")


class TutorError(Exception):
    """A refusal the agent should read and correct (printed, exit 1)."""


# ─── locating the vault ──────────────────────────────────────────────────────


def find_vault(start: str | os.PathLike | None = None) -> Path | None:
    env = os.environ.get("TUTOR_VAULT")
    if env:
        p = Path(env).expanduser()
        return p if (p / STATE_DIR).is_dir() else None
    cur = Path(start or os.getcwd()).resolve()
    for d in (cur, *cur.parents):
        if (d / STATE_DIR).is_dir():
            return d
    return None


def require_vault() -> Path:
    v = find_vault()
    if v is None:
        raise TutorError(
            "No tutor vault found (no .tutor/ directory here or in any parent). "
            "Ask the learner where their Obsidian vault is, then run `tutor.py init <vault-dir>`."
        )
    return v


def init_vault(root: Path, folder: str = "Learning") -> Path:
    root = root.expanduser().resolve()
    (root / STATE_DIR / "sessions").mkdir(parents=True, exist_ok=True)
    cfg_path = root / STATE_DIR / "config.json"
    if not cfg_path.exists():
        cfg_path.write_text(json.dumps({**DEFAULT_CONFIG, "folder": folder}, indent=2) + "\n")
    cfg = load_config(root)
    for sub in SUBFOLDERS:
        (root / cfg["folder"] / sub).mkdir(parents=True, exist_ok=True)
    return root


def load_config(vault: Path) -> dict:
    try:
        cfg = json.loads((vault / STATE_DIR / "config.json").read_text())
    except (OSError, ValueError):
        cfg = {}
    return {**DEFAULT_CONFIG, **cfg}


def folder(vault: Path, sub: str = "") -> Path:
    base = vault / load_config(vault)["folder"]
    p = base / sub if sub else base
    p.mkdir(parents=True, exist_ok=True)
    return p


def rel(vault: Path, path: Path) -> str:
    return str(Path(path).resolve().relative_to(vault))


# ─── JSON files with a lock ──────────────────────────────────────────────────


@contextlib.contextmanager
def locked(vault: Path):
    """Serialize every read-modify-write across hooks and CLI calls."""
    lock_path = vault / STATE_DIR / ".lock"
    with open(lock_path, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def state_path(vault: Path) -> Path:
    return vault / STATE_DIR / "state.json"


def load_state(vault: Path) -> dict:
    st = read_json(state_path(vault), {})
    st.setdefault("bindings", {})  # claude session id -> record id
    st.setdefault("transcripts", {})  # claude session id -> transcript path
    return st


def save_state(vault: Path, st: dict) -> None:
    write_json(state_path(vault), st)


# ─── session records ─────────────────────────────────────────────────────────


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return _dt.date.today().isoformat()


def record_path(vault: Path, rid: str) -> Path:
    return vault / STATE_DIR / "sessions" / f"{rid}.json"


def load_record(vault: Path, rid: str) -> dict:
    rec = read_json(record_path(vault, rid), None)
    if rec is None:
        raise TutorError(f"Session record not found: {rid}")
    return rec


def save_record(vault: Path, rec: dict) -> None:
    write_json(record_path(vault, rec["id"]), rec)


def all_records(vault: Path) -> list[dict]:
    out = []
    for p in sorted((vault / STATE_DIR / "sessions").glob("*.json")):
        r = read_json(p, None)
        if r:
            out.append(r)
    return out


def safe_filename(name: str, limit: int = 90) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned[:limit].rstrip(" .") or "untitled")


def new_record(vault: Path, kind: str, title: str, note: Path, claude_sid: str | None) -> dict:
    rid = f"{today()}-{secrets.token_hex(3)}"
    rec = {
        "id": rid,
        "kind": kind,  # teach | practice | log
        "title": title,
        "note": rel(vault, note),
        "created": now_iso(),
        "phase": {"teach": "probe", "practice": "practice", "log": "log"}[kind],
        "claude_sessions": [claude_sid] if claude_sid else [],
        "plan": None,  # {"nodes": [{id,title}], "edges": [[from,to]]}
        "plan_note": None,
        "tags": [],  # plan nodeIds in the order checks named them
        "probe": None,
        "questions": [],
        "problems": [],
        "logged_tool_ids": [],
        "block_counter": 0,
        "targets": [],  # practice: proposition ids picked for this session
    }
    save_record(vault, rec)
    return rec


def bind(vault: Path, claude_sid: str, rid: str | None) -> None:
    st = load_state(vault)
    if rid is None:
        st["bindings"].pop(claude_sid, None)
    else:
        st["bindings"][claude_sid] = rid
    save_state(vault, st)


def bound_record_id(vault: Path, claude_sid: str | None) -> str | None:
    if not claude_sid:
        return None
    return load_state(vault)["bindings"].get(claude_sid)


def current_sid() -> str | None:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")


def require_bound(vault: Path) -> dict:
    sid = current_sid()
    rid = bound_record_id(vault, sid)
    if not rid:
        raise TutorError(
            "This Claude session is not bound to a tutor session. Start one with "
            "`tutor.py session start --kind teach --title ...` (or `session resume <note>`)."
        )
    return load_record(vault, rid)


# ─── notes ───────────────────────────────────────────────────────────────────


def note_abspath(vault: Path, rec: dict) -> Path:
    return vault / rec["note"]


def append_note(path: Path, text: str) -> None:
    """md-log semantics: append-only, blank line between blocks."""
    try:
        current = path.read_text() if path.exists() else ""
    except OSError:
        current = ""
    if not current.strip():
        prefix = ""
    elif current.endswith("\n\n"):
        prefix = ""
    elif current.endswith("\n"):
        prefix = "\n"
    else:
        prefix = "\n\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(prefix + text.rstrip("\n") + "\n")


def callout(kind: str, title: str, body: str | list[str] = "", collapsed: bool = False) -> str:
    fold = "-" if collapsed else ""
    lines = [f"> [!{kind}]{fold} {title}".rstrip()]
    body_lines = body.split("\n") if isinstance(body, str) else body
    if isinstance(body, str) and not body:
        body_lines = []
    for line in body_lines:
        lines.append(">" if not line else f"> {line}")
    return "\n".join(lines)


def wikilink(vault: Path, path: Path | str, alias: str | None = None, anchor: str | None = None) -> str:
    target = Path(path)
    name = target.stem if target.suffix == ".md" else target.name
    a = f"#^{anchor}" if anchor else ""
    return f"[[{name}{a}|{alias}]]" if alias else f"[[{name}{a}]]"
