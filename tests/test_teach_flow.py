"""End-to-end checks of the teach loop against the failures seen in real sessions.

Run: python3 -m unittest discover -s tests   (from the plugin root)

Each test drives the real CLI and hook in a throwaway vault, with no Claude
transcript (so CLI blocks are appended immediately).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "tutor.py"
HOOK = ROOT / "scripts" / "hook.py"
sys.path.insert(0, str(ROOT / "scripts"))

from tutorlib import questions, terms  # noqa: E402

SID = "test-sid"


class Vault:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = {**os.environ, "CLAUDE_CODE_SESSION_ID": SID, "TUTOR_VAULT": str(self.dir)}
        self.cli("init", str(self.dir))

    def cli(self, *args, stdin: str | dict | None = None, ok: bool = True) -> subprocess.CompletedProcess:
        if isinstance(stdin, dict):
            stdin = json.dumps(stdin)
        p = subprocess.run([sys.executable, str(CLI), *args], input=stdin or "", capture_output=True, text=True,
                           env=self.env, cwd=self.dir)
        if ok and p.returncode != 0:
            raise AssertionError(f"tutor {args} failed:\n{p.stderr}")
        if not ok and p.returncode == 0:
            raise AssertionError(f"tutor {args} should have been refused:\n{p.stdout}")
        return p

    def hook(self, payload: dict) -> str:
        payload = {"session_id": SID, "cwd": str(self.dir), **payload}
        p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                           env=self.env, cwd=self.dir)
        return p.stdout

    def record(self) -> dict:
        d = self.dir / ".tutor" / "sessions"
        return json.loads(next(d.iterdir()).read_text())

    def note(self) -> str:
        return (self.dir / self.record()["note"]).read_text()

    def answer_quiz(self, letter_of_text: str | None = None, pick: str = "A") -> str:
        """Simulate AskUserQuestion on the open quiz; returns the hook's context."""
        q = questions.open_question(self.record())
        payload = questions.ask_payload(q)
        if letter_of_text is not None:
            pick = next(o["letter"] for o in q["options"] if o["text"] == letter_of_text)
        qtext = payload["questions"][0]["question"]
        self.hook({"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_use_id": q["qid"],
                   "tool_input": payload})
        out = self.hook({"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion", "tool_use_id": q["qid"],
                         "tool_input": payload,
                         "tool_response": {"answers": {qtext: pick, questions.CONFIDENCE_QUESTION: "75%"}}})
        return out

    def to_teach_phase(self):
        self.cli("session", "start", "--kind", "teach", "--title", "LoRA test")
        self.cli("quiz", stdin={"question": "For $h = Wx$, what is the gradient with respect to $W$?",
                                "options": ["$g x^\\top$", "$W^\\top g$"], "correct": "$g x^\\top$",
                                "explanation": "Outer product."})
        self.answer_quiz("$g x^\\top$")
        self.cli("probe-done", stdin={"goal": "g", "strands": [{"strand": "grad", "assessment": "ok"}],
                                      "held": [{"term": "gradient", "evidence": "q1"}, "$W$"]})
        self.cli("plan", "--mermaid", 'graph TD\n  lora["LoRA update"] --> count["Parameter count"]')


EXPLAIN_LORA = """terms:
- LoRA :: low-rank adaptation: a trainable update $BA$ added to a frozen matrix $W$
- $W_{up}$ :: the up-projection of the update, a $768 \\times 8$ matrix
uses: gradient
---
## LoRA

**LoRA** adds $BA$ to the frozen $W$. Here $W_{up}$ starts at zero, so the layer starts as the pretrained one.
"""

PREDICT = {"type": "predict", "nodeId": "lora", "uses": ["gradient"],
           "question": "A frozen layer gets a trainable update that starts at zero. What does the layer compute at step $0$?",
           "options": ["The pretrained function", "A random function"], "correct": "The pretrained function",
           "explanation": "The update is zero."}


class TermTests(unittest.TestCase):
    def test_symbols_are_found(self):
        found = terms._symbol_candidates("With $W_{up} = 0$ and $\\alpha / r$, call `input_register_device()` on `ls -l`.")
        keys = {terms.norm(f) for f in found}
        self.assertIn("W_up", keys)
        self.assertIn("alpha", keys)
        self.assertIn("input_register_device", keys)
        self.assertNotIn("ls -l", keys)

    def test_plural_and_case_match(self):
        idx = {"adapter": {}}
        self.assertTrue(terms.is_known(idx, "Adapters"))

    def test_parse_explain_header(self):
        t, u, body = terms.parse_explain(EXPLAIN_LORA)
        self.assertEqual([x["term"] for x in t], ["LoRA", "$W_{up}$"])
        self.assertEqual(u, ["gradient"])
        self.assertTrue(body.startswith("## LoRA"))


class TeachFlowTests(unittest.TestCase):
    def setUp(self):
        self.v = Vault()
        self.v.to_teach_phase()

    def test_probe_done_requires_held(self):
        v = Vault()
        v.cli("session", "start", "--kind", "teach", "--title", "t")
        p = v.cli("probe-done", stdin={"goal": "g", "strands": [{"strand": "s", "assessment": "a"}]}, ok=False)
        self.assertIn("held", p.stderr)

    def test_question_needs_uses_and_known_terms(self):
        spec = {**PREDICT}
        del spec["uses"]
        self.assertIn("`uses` is missing", self.v.cli("quiz", stdin=spec, ok=False).stderr)
        spec = {**PREDICT, "uses": ["gradient", "adapter"]}
        self.assertIn("adapter", self.v.cli("quiz", stdin=spec, ok=False).stderr)
        spec = {**PREDICT, "question": "With $W_{up} = 0$, what does the layer compute?"}
        self.assertIn("W_{up}", self.v.cli("quiz", stdin=spec, ok=False).stderr)

    def test_check_needs_explain_not_chat_prose(self):
        self.v.cli("quiz", stdin=PREDICT)
        self.v.answer_quiz("The pretrained function")
        check = {"type": "check", "nodeId": "lora", "uses": ["LoRA"], "question": "How many parameters does LoRA add?",
                 "options": ["$2dr$", "$d^2$"], "correct": "$2dr$", "explanation": "x"}
        p = self.v.cli("quiz", stdin=check, ok=False)
        self.assertIn("tutor explain", p.stderr)
        self.v.cli("explain", "--node", "lora", stdin=EXPLAIN_LORA)
        note = self.v.note()
        self.assertIn("[!abstract] New terms", note)
        self.assertIn("**LoRA**: low-rank adaptation", note)
        self.v.cli("quiz", stdin=check)

    def test_explain_refuses_undefined_symbol(self):
        bad = "terms:\n- LoRA :: an update\nuses: gradient\n---\nThe update uses $W_{down}$ and `lora_alpha`, both new here.\n"
        p = self.v.cli("explain", "--node", "lora", stdin=bad, ok=False)
        self.assertIn("W_{down}", p.stderr)
        self.assertIn("lora_alpha", p.stderr)
        p = self.v.cli("explain", "--node", "lora", stdin="Just prose about $W_{down}$ with no header at all here.", ok=False)
        self.assertIn("`uses:`", p.stderr)

    def test_stop_blocked_after_explain_without_question(self):
        self.v.cli("quiz", stdin=PREDICT)
        self.v.answer_quiz("The pretrained function")
        self.v.cli("explain", "--node", "lora", stdin=EXPLAIN_LORA)
        out = self.v.hook({"hook_event_name": "Stop", "stop_hook_active": False})
        self.assertIn('"decision": "block"', out)
        out = self.v.hook({"hook_event_name": "Stop", "stop_hook_active": True})
        self.assertNotIn("block", out)

    def test_recall_aside_is_not_the_answer(self):
        self.v.cli("quiz", stdin=PREDICT)
        self.v.answer_quiz("The pretrained function")
        self.v.cli("explain", "--node", "lora", stdin=EXPLAIN_LORA)
        self.v.cli("recall", stdin={"type": "check", "nodeId": "lora", "uses": ["LoRA"],
                                    "question": "Why does LoRA start as the pretrained layer?",
                                    "answer": "Because $BA = 0$ at initialisation."})
        ctx = self.v.hook({"hook_event_name": "UserPromptSubmit", "prompt": "wait, what does frozen mean?"})
        self.assertIn("candidate #1", ctx)
        q = self.v.record()["questions"][-1]
        self.assertEqual(q["status"], "asked")  # still open: an aside is not an answer
        # an aside explanation is allowed while the question is open
        self.v.cli("explain", stdin="terms:\n- frozen :: not updated by training\nuses: gradient\n---\n"
                                    "A **frozen** weight keeps its pretrained value during training.")
        self.v.hook({"hook_event_name": "UserPromptSubmit", "prompt": "because B starts at zero"})
        self.v.hook({"hook_event_name": "UserPromptSubmit", "prompt": "because B starts at zero, so BA = 0"})
        self.v.cli("grade", q["qid"], "--verdict", "correct", "--feedback", "Right.")
        r = self.v.record()["questions"][-1]["result"]
        self.assertEqual(r["text"], "because B starts at zero, so BA = 0")
        self.assertIn("*Graded answer:*", self.v.note())

    def test_terms_carry_over_to_next_session(self):
        self.v.cli("quiz", stdin=PREDICT)
        self.v.answer_quiz("The pretrained function")
        self.v.cli("explain", "--node", "lora", stdin=EXPLAIN_LORA)
        self.v.cli("session", "end")
        self.v.cli("session", "start", "--kind", "teach", "--title", "second")
        listing = self.v.cli("terms", "list", "--all").stdout
        self.assertIn("LoRA [prior", listing)


class MirrorTests(unittest.TestCase):
    def test_refused_command_does_not_duplicate_note_blocks(self):
        v = Vault()
        v.to_teach_phase()
        transcript = v.dir / "transcript.jsonl"
        transcript.write_text("")
        v.hook({"hook_event_name": "Stop", "transcript_path": str(transcript)})
        entry = {"type": "assistant", "message": {"id": "m1", "role": "assistant",
                                                  "content": [{"type": "text", "text": "A sentence the learner reads once."}]}}
        with open(transcript, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
        for _ in range(3):  # refused: no `uses`
            v.cli("quiz", stdin={k: x for k, x in PREDICT.items() if k != "uses"}, ok=False)
        self.assertEqual(v.note().count("A sentence the learner reads once."), 1)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.v = Vault()

    def deny(self, tool, tin) -> bool:
        out = self.v.hook({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tin})
        return '"deny"' in out

    def test_guard(self):
        d = self.v.dir
        self.assertTrue(self.deny("Write", {"file_path": str(d / "Learning/Sessions/x.md")}))
        self.assertTrue(self.deny("Edit", {"file_path": str(d / ".tutor/state.json")}))
        self.assertFalse(self.deny("Write", {"file_path": str(d / "Learning/Sheets/x.md")}))
        self.assertTrue(self.deny("Bash", {"command": f"python3 - <<'EOF'\nimport json\np='{d}/.tutor/sessions/a.json'\n"
                                                      "r=json.load(open(p))\njson.dump(r,open(p,'w'))\nEOF"}))
        self.assertFalse(self.deny("Bash", {"command": "grep -n x Learning/Sessions/a.md"}))
        self.assertFalse(self.deny("Bash", {"command": "python3 tutor.py explain --node a <<'EOF'\nterms:\n- x :: y\n"
                                                      "uses: none\n---\nwrite( Learning/Sessions/ is fine here\nEOF"}))


if __name__ == "__main__":
    unittest.main()
