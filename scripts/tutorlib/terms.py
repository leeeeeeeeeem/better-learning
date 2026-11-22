"""The term registry: nothing reaches the learner undefined.

Every term or symbol a teach-phase explanation or question relies on must have
one of three sources:

  taught  defined in a `tutor explain` block (this session or an earlier one)
  probe   shown held in this session's probe (`probe-done` "held", or `terms add`)
  prior   registered in an earlier session's record

Two checks enforce it:

  uses    every explanation and teach-phase question declares the terms it relies
          on; each must be known (or, for an explanation, defined in its own
          `terms`).
  lint    symbols that can be found mechanically (subscripted or Greek math
          symbols, named functions in math, `code` identifiers) must be known
          too, so an undeclared $W_{up}$ cannot slip through.
"""

from __future__ import annotations

import re

from .vault import TutorError, now_iso

SOURCES = ("taught", "probe")

# ─── normalisation ───────────────────────────────────────────────────────────

_WRAP_RE = re.compile(r"\\(?:mathrm|text|operatorname|mathbf|mathit|mathcal|boldsymbol|textrm|textit)\s*\{([^{}]*)\}")


def norm(term: str) -> str:
    s = str(term).strip()
    s = s.strip("$`*").strip()
    for _ in range(3):
        s = _WRAP_RE.sub(r"\1", s)
    s = s.replace("\\", "").replace("{", "").replace("}", "")
    s = re.sub(r"\s+", " ", s).strip()
    if s.endswith("()"):
        s = s[:-2]
    if re.fullmatch(r"[A-Za-z][A-Za-z \-']*", s):
        s = s.lower()
    return s


def _variants(key: str) -> set[str]:
    out = {key, key.replace(" ", "")}
    if re.fullmatch(r"[a-z][a-z \-']*", key):
        for suf in ("es", "s"):
            if key.endswith(suf) and len(key) > len(suf) + 2:
                out.add(key[: -len(suf)])
        out.add(key + "s")
    return out


# ─── registry ────────────────────────────────────────────────────────────────


def known_index(rec: dict, prior_records: list[dict]) -> dict[str, dict]:
    """normalised key → entry, from this session and earlier sessions."""
    idx: dict[str, dict] = {}
    for r in prior_records:
        if r.get("id") == rec.get("id"):
            continue
        for t in r.get("terms") or []:
            idx.setdefault(t["key"], {**t, "source": "prior", "session": r.get("title")})
    for t in rec.get("terms") or []:
        idx[t["key"]] = t
    return idx


def is_known(idx: dict, term: str) -> bool:
    return any(v in idx for v in _variants(norm(term)))


def register(rec: dict, entries: list[dict], source: str, node: str | None = None, evidence: str | None = None) -> list[str]:
    """Add or update terms. entries: [{"term", "definition"?}]. Returns the keys."""
    if source not in SOURCES:
        raise TutorError(f"terms: source must be one of {SOURCES}.")
    terms = rec.setdefault("terms", [])
    by_key = {t["key"]: t for t in terms}
    keys = []
    for e in entries:
        term = str(e.get("term") or "").strip()
        if not term:
            raise TutorError("terms: every entry needs a `term`.")
        definition = (e.get("definition") or "").strip() or None
        if source == "taught" and not definition:
            raise TutorError(f"terms: `{term}` has no definition. A taught term needs a one-line definition: "
                             "what it is and its role (and its shape, for a matrix or tensor).")
        key = norm(term)
        entry = {"term": term, "key": key, "definition": definition, "source": source,
                 "node": node, "evidence": evidence, "at": now_iso()}
        if key in by_key:
            by_key[key].update({k: v for k, v in entry.items() if v is not None})
        else:
            terms.append(entry)
            by_key[key] = entry
        keys.append(key)
    return keys


# ─── mechanical lint ─────────────────────────────────────────────────────────

GREEK = {
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "vartheta", "iota",
    "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi",
    "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega", "ell",
}
# Named functions that are part of ordinary math, not session vocabulary.
PLAIN_FUNCS = {"log", "ln", "exp", "sin", "cos", "tan", "max", "min", "argmax", "argmin", "lim", "sup", "inf",
               "det", "dim", "rank", "tr", "if", "otherwise", "and", "or", "for", "where", "s", "ms", "kHz", "Hz",
               "Var", "E", "Pr", "P", "sign", "abs", "mod"}

_MATH_RE = re.compile(r"\$\$(.+?)\$\$|\$([^$\n]+?)\$", re.S)
_FENCE_RE = re.compile(r"```.*?```", re.S)
_CODE_RE = re.compile(r"`([^`\n]+)`")
_SUBSCRIPT_RE = re.compile(r"(?<![A-Za-z\\])(\\?[A-Za-z]+)_(\{(?:[^{}]|\{[^{}]*\})*\}|\\[A-Za-z]+|[A-Za-z0-9])")
_GREEK_RE = re.compile(r"\\([A-Za-z]+)(?![A-Za-z])")
_NAMED_RE = re.compile(r"\\(?:mathrm|operatorname|text)\s*\{([A-Za-z][A-Za-z\-]{1,})\}")


def _symbol_candidates(text: str) -> list[str]:
    text = _FENCE_RE.sub(" ", text or "")
    found: list[str] = []
    for m in _MATH_RE.finditer(text):
        seg = m.group(1) or m.group(2) or ""
        for base, sub in _SUBSCRIPT_RE.findall(seg):
            b = base.lstrip("\\")
            if base.startswith("\\") and b not in GREEK:
                continue  # \sum_{...}, \mathbb_..., operators
            found.append(f"{base}_{sub}")
        stripped = _SUBSCRIPT_RE.sub(" ", seg)
        for name in _GREEK_RE.findall(stripped):
            if name in GREEK:
                found.append("\\" + name)
        for name in _NAMED_RE.findall(seg):
            if name not in PLAIN_FUNCS and len(name) > 1:
                found.append(name)
    for m in _CODE_RE.finditer(_MATH_RE.sub(" ", text)):
        span = m.group(1).strip()
        if " " in span or not span or re.fullmatch(r"[\d.,%x×*+\-/]+", span):
            continue  # commands and literal numbers are not vocabulary
        found.append(f"`{span}`")
    out, seen = [], set()
    for f in found:
        k = norm(f)
        if k and k not in seen:
            seen.add(k)
            out.append(f)
    return out


def undefined(idx: dict, texts: list[str], extra_known: list[str] = ()) -> list[str]:
    """Mechanically found symbols in `texts` that are neither known nor in extra_known."""
    extra = set()
    for t in extra_known:
        extra |= _variants(norm(t))
    missing = []
    for cand in _symbol_candidates("\n".join(t for t in texts if t)):
        vs = _variants(norm(cand))
        if not (vs & extra) and not any(v in idx for v in vs):
            missing.append(cand)
    return missing


def _uses_list(spec_uses, where: str) -> list[str]:
    if spec_uses is None:
        raise TutorError(
            f"{where}: `uses` is missing. List every term and symbol this relies on that the learner must already "
            "hold (an empty list is allowed only when it relies on nothing). Each one must have been taught in an "
            "explanation, or shown held in the probe."
        )
    if isinstance(spec_uses, str):
        spec_uses = [u for u in re.split(r",\s*", spec_uses) if u.strip()]
    if not isinstance(spec_uses, list):
        raise TutorError(f"{where}: `uses` must be a list of terms.")
    return [str(u).strip() for u in spec_uses if str(u).strip() and str(u).strip().lower() != "none"]


def _refusal(where: str, missing_uses: list[str], missing_syms: list[str], own_terms: bool) -> str:
    lines = [f"{where}: these are not defined for the learner yet:"]
    if missing_uses:
        lines.append("  declared in `uses` but never taught or probed: " + ", ".join(missing_uses))
    if missing_syms:
        lines.append("  used in the text but never defined: " + ", ".join(missing_syms))
    lines.append("Every term and symbol must be (a) taught: defined in a `tutor explain` block, "
                 "(b) shown held in the probe: `tutor terms add` with source `probe` and the question as evidence, "
                 "or (c) defined right now.")
    if own_terms:
        lines.append("For this explanation, (c) means: add each one to its `terms:` header with a one-line "
                     "definition (name, role in words, shape for a matrix).")
    else:
        lines.append("For a question, (c) means: run `tutor explain` first with these in its `terms:` header, "
                     "then ask the question again. Never define a term inside the question itself.")
    lines.append("Do not drop a term from `uses` to pass this check: list what the learner actually needs.")
    return "\n".join(lines)


def check_question(rec: dict, prior: list[dict], spec: dict, where: str) -> list[str]:
    """Teach-phase questions only. Returns the normalised uses."""
    uses = _uses_list(spec.get("uses"), where)
    idx = known_index(rec, prior)
    missing_uses = [u for u in uses if not is_known(idx, u)]
    texts = [spec.get("question"), spec.get("details")] + [str(o) for o in (spec.get("options") or [])]
    missing_syms = undefined(idx, texts)
    if missing_uses or missing_syms:
        raise TutorError(_refusal(where, missing_uses, missing_syms, own_terms=False))
    return uses


def check_explanation(rec: dict, prior: list[dict], terms: list[dict], uses: list[str], body: str) -> None:
    idx = known_index(rec, prior)
    own = [t["term"] for t in terms]
    missing_uses = [u for u in uses if not is_known(idx, u) and norm(u) not in {norm(o) for o in own}]
    missing_syms = undefined(idx, [body], extra_known=own)
    if missing_uses or missing_syms:
        raise TutorError(_refusal("explain", missing_uses, missing_syms, own_terms=True))


# ─── `tutor explain` input ───────────────────────────────────────────────────


def parse_explain(text: str) -> tuple[list[dict], list[str] | None, str, str | None]:
    """Markdown on stdin, with an optional header ended by a line `---`:

        reply: Correct at 75%. The HID layer sets every parent ...
        terms:
        - input core :: the kernel subsystem every input driver registers with
        - $W_{up}$ :: the adapter's up-projection, a 768 x 64 matrix
        uses: evdev, system call
        ---
        <markdown body>
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or not re.match(r"^(terms|uses|reply)\s*:", lines[i].strip(), re.I):
        return [], None, text.strip(), None
    try:
        end = next(j for j in range(i, len(lines)) if lines[j].strip() == "---")
    except StopIteration:
        raise TutorError("explain: the header (reply:/terms:/uses:) must end with a line containing only `---`.")
    terms: list[dict] = []
    uses: list[str] | None = None
    reply: list[str] = []
    section = None
    for raw in lines[i:end]:
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(terms|uses|reply)\s*:\s*(.*)$", line, re.I)
        if m:
            section = m.group(1).lower()
            rest = m.group(2).strip()
            if section == "reply":
                if rest:
                    reply.append(rest)
                continue
            if section == "uses":
                uses = [] if uses is None else uses
                if rest and rest.lower() != "none":
                    uses += [u.strip() for u in rest.split(",") if u.strip()]
            continue
        if section == "reply":
            reply.append(line)
            continue
        if not line.startswith("-"):
            raise TutorError(f"explain: header line not understood: {line!r}. Use `- term :: definition` "
                             "under `terms:` and `- term` (or a comma list) under `uses:`.")
        item = line[1:].strip()
        if section == "terms":
            if " :: " in item:
                term, definition = item.split(" :: ", 1)
            elif ": " in item:
                term, definition = item.split(": ", 1)
            else:
                raise TutorError(f"explain: term without a definition: {item!r}. Write `- term :: definition`.")
            terms.append({"term": term.strip(), "definition": definition.strip()})
        elif section == "uses":
            uses = (uses or []) + [item]
    body = "\n".join(lines[end + 1:]).strip()
    return terms, uses, body, (" ".join(reply).strip() or None)
