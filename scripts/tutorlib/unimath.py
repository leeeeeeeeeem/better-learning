"""LaTeX → Unicode for text shown where LaTeX doesn't render.

AskUserQuestion dialogs (terminal, and the Claude app over remote control)
show plain text, so quiz questions and options are converted there. The note
keeps the LaTeX. Only math segments ($…$, $$…$$, \\(…\\), \\[…\\]) change.
Unknown commands degrade to their name, so nothing is lost silently.
"""

from __future__ import annotations

import re

SYMBOLS = {
    # Greek
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "varpi": "ϖ", "rho": "ρ",
    "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    # operators and relations
    "cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓", "ast": "∗", "star": "⋆",
    "circ": "∘", "bullet": "•", "oplus": "⊕", "otimes": "⊗", "odot": "⊙",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "approx": "≈",
    "equiv": "≡", "sim": "∼", "simeq": "≃", "cong": "≅", "propto": "∝", "ll": "≪", "gg": "≫",
    "prec": "≺", "succ": "≻", "preceq": "⪯", "succeq": "⪰",
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆", "supset": "⊃",
    "supseteq": "⊇", "cup": "∪", "cap": "∩", "setminus": "∖", "emptyset": "∅", "varnothing": "∅",
    "forall": "∀", "exists": "∃", "nexists": "∄", "neg": "¬", "lnot": "¬", "land": "∧", "wedge": "∧",
    "lor": "∨", "vee": "∨", "top": "⊤", "bot": "⊥", "vdash": "⊢", "models": "⊨", "perp": "⊥",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "gets": "←", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "implies": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔", "iff": "⇔",
    "mapsto": "↦", "longrightarrow": "⟶", "longmapsto": "⟼", "uparrow": "↑", "downarrow": "↓",
    "infty": "∞", "partial": "∂", "nabla": "∇", "sum": "∑", "prod": "∏", "int": "∫", "oint": "∮",
    "iint": "∬", "sqrt": "√", "angle": "∠", "triangle": "△", "prime": "′", "ell": "ℓ", "hbar": "ℏ",
    "aleph": "ℵ", "Re": "ℜ", "Im": "ℑ", "wp": "℘",
    "langle": "⟨", "rangle": "⟩", "lceil": "⌈", "rceil": "⌉", "lfloor": "⌊", "rfloor": "⌋",
    "mid": "∣", "parallel": "∥", "vert": "|", "Vert": "‖", "lvert": "|", "rvert": "|",
    "lVert": "‖", "rVert": "‖",
    "dots": "…", "ldots": "…", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱",
    "quad": "  ", "qquad": "    ",
    # function names keep their name
    "log": "log", "ln": "ln", "exp": "exp", "sin": "sin", "cos": "cos", "tan": "tan",
    "max": "max", "min": "min", "arg": "arg", "argmax": "argmax", "argmin": "argmin",
    "lim": "lim", "sup": "sup", "inf": "inf", "det": "det", "dim": "dim", "deg": "deg",
    "ker": "ker", "gcd": "gcd", "Pr": "Pr", "tanh": "tanh", "sigmoid": "sigmoid",
}
DROP = {"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr",
        "displaystyle", "textstyle", "limits", "nolimits", "middle"}
TEXT_LIKE = {"text", "textrm", "textit", "textbf", "mathrm", "mathit", "mathbf", "mathsf",
             "mathtt", "operatorname", "boldsymbol", "bm", "mathcal", "mathscr", "mathfrak", "emph"}
BLACKBOARD = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ", "E": "𝔼", "1": "𝟙"}
ACCENTS = {"hat": "̂", "widehat": "̂", "bar": "̄", "overline": "̅",
           "tilde": "̃", "widetilde": "̃", "vec": "⃗", "dot": "̇", "ddot": "̈"}
SUP = dict(zip("0123456789+-=()niTtkxyabcdefghjlmoprsuvwz′",
               "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵀᵗᵏˣʸᵃᵇᶜᵈᵉᶠᵍʰʲˡᵐᵒᵖʳˢᵘᵛʷᶻ′"))
SUB = dict(zip("0123456789+-=()aehijklmnoprstuvx",
               "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))


class _Parser:
    def __init__(self, s: str):
        self.s, self.i = s, 0

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def group(self) -> str:
        """Read one argument: {…}, a command, or a single character (raw LaTeX)."""
        while self.peek() == " ":
            self.i += 1
        c = self.peek()
        if c == "{":
            depth, start = 0, self.i
            while self.i < len(self.s):
                ch = self.s[self.i]
                if ch == "\\":
                    self.i += 2
                    continue
                depth += ch == "{"
                depth -= ch == "}"
                self.i += 1
                if depth == 0:
                    return self.s[start + 1:self.i - 1]
            return self.s[start + 1:]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", self.s[self.i:])
            self.i += len(m.group(0))
            return m.group(0)
        self.i += 1
        return c

    def optional(self) -> str | None:
        if self.peek() == "[":
            end = self.s.find("]", self.i)
            if end > 0:
                val = self.s[self.i + 1:end]
                self.i = end + 1
                return val
        return None


# Relations and binary operators get spaces around them, as LaTeX typesets them.
SPACED = {"cdot", "times", "div", "pm", "mp", "circ", "oplus", "otimes", "leq", "le", "geq", "ge",
          "neq", "ne", "approx", "equiv", "sim", "simeq", "cong", "propto", "in", "notin", "subset",
          "subseteq", "supset", "supseteq", "cup", "cap", "setminus", "land", "wedge", "lor", "vee",
          "vdash", "models", "to", "rightarrow", "leftarrow", "gets", "leftrightarrow", "Rightarrow",
          "implies", "Leftarrow", "Leftrightarrow", "iff", "mapsto", "longrightarrow", "mid"}


def _script(text: str, table: dict, mark: str) -> str:
    if mark == "^" and text in ("⊤", "T", "\\intercal"):
        return "ᵀ"
    if text and all(ch in table for ch in text):
        return "".join(table[ch] for ch in text)
    if re.fullmatch(r"\w+", text):
        return f"{mark}{text}"
    return f"{mark}({text})"


def _wrap(text: str) -> str:
    """Parenthesize a fraction part only if it has a top-level space or operator."""
    depth = 0
    for ch in text:
        depth += ch in "([{"
        depth -= ch in ")]}"
        if depth == 0 and ch in " +-−×·/=<>≤≥,±∓":
            return f"({text})"
    return text


def convert_math(s: str) -> str:
    p, out = _Parser(s), []
    while p.i < len(s):
        c = s[p.i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[p.i:])
            p.i += len(m.group(0))
            name = m.group(1)
            if name.isalpha():  # LaTeX swallows the space after a command name
                while p.peek() == " ":
                    p.i += 1
            if name in ("frac", "dfrac", "tfrac"):
                a, b = convert_math(p.group()), convert_math(p.group())
                out.append(f"{_wrap(a)}/{_wrap(b)}")
            elif name == "sqrt":
                n = p.optional()
                root = {"3": "∛", "4": "∜"}.get(n or "", "√")
                out.append(root + _wrap(convert_math(p.group())))
            elif name == "mathbb":
                arg = p.group()
                out.append("".join(BLACKBOARD.get(ch, ch) for ch in arg))
            elif name in TEXT_LIKE:
                arg = p.group()
                out.append(arg if name.startswith("text") else convert_math(arg))
            elif name in ACCENTS:
                arg = convert_math(p.group())
                out.append(arg + ACCENTS[name] if len(arg) == 1 else f"{arg}{ACCENTS[name]}")
            elif name in DROP:
                pass
            elif name in ("begin", "end"):
                p.group()
            elif name in SPACED:
                out.append(f" {SYMBOLS[name]} ")
            elif name in SYMBOLS:
                out.append(SYMBOLS[name])
            elif name in (",", ":", ";", " ", "!"):
                out.append("" if name == "!" else " ")
            elif name == "\\":
                out.append("; ")
            elif len(name) == 1:
                out.append(name)  # \{ \} \| \$ \% \_ …
            else:
                out.append(name)
        elif c in "^_":
            p.i += 1
            arg = convert_math(p.group())
            out.append(_script(arg, SUP if c == "^" else SUB, c))
        elif c == "{":
            out.append(convert_math(p.group()))
        elif c == "&":
            p.i += 1
            out.append(", ")
        elif c == "~":
            p.i += 1
            out.append(" ")
        else:
            p.i += 1
            out.append(c)
    return re.sub(r" {2,}", " ", "".join(out)).strip() if "\n" not in s else "".join(out)


_MATH_RE = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<![\\$])\$(?!\s)(.+?)(?<!\s)\$", re.S)


def to_unicode(text: str) -> str:
    """Replace every math segment in `text` with its Unicode rendering."""
    def repl(m: re.Match) -> str:
        display = m.group(1) or m.group(2)
        inner = display or m.group(3) or m.group(4)
        rendered = convert_math(inner.strip())
        return f"\n{rendered}\n" if display else rendered
    return _MATH_RE.sub(repl, text).replace("\\$", "$")
