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

from tutorlib import graph, questions, terms  # noqa: E402

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
        t, u, body, reply = terms.parse_explain(EXPLAIN_LORA)
        self.assertIsNone(reply)
        t, u, body, reply = terms.parse_explain("reply: Correct at 75%.\n  The update is zero.\n" + EXPLAIN_LORA)
        self.assertEqual(reply, "Correct at 75%. The update is zero.")
        self.assertEqual([x["term"] for x in t], ["LoRA", "$W_{up}$"])
        self.assertEqual(u, ["gradient"])
        self.assertTrue(body.startswith("## LoRA"))


class GraphCandidateTests(unittest.TestCase):
    def test_paraphrase_ranks_first_and_unrelated_gets_none(self):
        def node(nid, name, statement, aliases=()):
            return {"id": nid, "name": name, "statement": statement, "aliases": list(aliases), "provenance": []}
        g = {"nodes": {n["id"]: n for n in [
            node("n_1", "Chain rule", "For differentiable $f, g$: $(g \\circ f)'(a) = g'(f(a)) f'(a)$.", ["derivative of a composition"]),
            node("n_2", "Freezing keeps layers in the chain rule",
                 "A frozen layer is not updated, but backpropagation still passes the gradient through it."),
        ]}, "sources": {}}
        findings = {"propositions": [
            {"id": "p1", "name": "Frozen layers stay in backpropagation",
             "statement": "Gradients still flow through frozen layers; their weights are just not updated."},
            {"id": "p2", "name": "Sourdough", "statement": "Wild yeast leavens sourdough bread."},
            {"id": "p3", "name": "x", "statement": "y", "linkTo": "n_1"}]}
        rows = graph.candidates(g, findings)
        self.assertEqual([p["id"] for p, _ in rows], ["p1", "p2"])  # linked findings are skipped
        self.assertEqual(rows[0][1][0][1]["id"], "n_2")
        self.assertEqual(rows[1][1], [])


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
        p = self.v.cli("explain", "--node", "lora", stdin=EXPLAIN_LORA, ok=False)
        self.assertIn("reply:", p.stderr)
        self.v.cli("explain", "--node", "lora", stdin="reply: Correct at 75%: the update starts at zero.\n" + EXPLAIN_LORA)
        note = self.v.note()
        verdict, reply, heading, box = (note.index("Correct ✓"), note.index("Correct at 75%"),
                                        note.index("## LoRA"), note.index("[!abstract] New terms"))
        self.assertTrue(verdict < reply < heading < box)
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
        self.v.cli("explain", "--node", "lora", stdin="reply: Correct.\n" + EXPLAIN_LORA)
        out = self.v.hook({"hook_event_name": "Stop", "stop_hook_active": False})
        self.assertIn('"decision": "block"', out)
        out = self.v.hook({"hook_event_name": "Stop", "stop_hook_active": True})
        self.assertNotIn("block", out)

    def test_setup_before_prediction_is_short_and_not_the_explanation(self):
        setup = ("terms:\n- frozen layer :: a layer whose weights training does not update\nuses: gradient\n---\n"
                 "## A frozen layer with a trainable update\n\n{}")
        long_body = "The question asks what such a layer computes at the first step. " * 20
        p = self.v.cli("explain", "--node", "lora", stdin=setup.format(long_body), ok=False)
        self.assertIn("setup", p.stderr)
        self.v.cli("explain", "--node", "lora",
                   stdin=setup.format("The question asks what such a layer computes at the first training step."))
        self.assertEqual(self.v.record()["explained_since_answer"] or [], [])
        out = self.v.hook({"hook_event_name": "Stop", "stop_hook_active": False})
        self.assertIn('"decision": "block"', out)  # a setup must be followed by its prediction
        self.v.cli("quiz", stdin=PREDICT)
        self.v.answer_quiz("The pretrained function")
        # A later setup on the same node (--setup) does not satisfy the check gate either.
        self.v.cli("explain", "--node", "lora", "--setup",
                   stdin="reply: Correct.\n" + setup.format("The next question asks about the parameter count."))
        check = {"type": "check", "nodeId": "lora", "uses": ["frozen layer"], "question": "What does a frozen layer keep?",
                 "options": ["Its weights", "Its inputs"], "correct": "Its weights", "explanation": "x"}
        self.assertIn("tutor explain", self.v.cli("quiz", stdin=check, ok=False).stderr)
        self.v.cli("explain", "--node", "lora", stdin=EXPLAIN_LORA)  # the detailed explanation: no cap
        self.v.cli("quiz", stdin=check)

    def test_recall_aside_is_not_the_answer(self):
        self.v.cli("quiz", stdin=PREDICT)
        self.v.answer_quiz("The pretrained function")
        self.v.cli("explain", "--node", "lora", stdin="reply: Correct.\n" + EXPLAIN_LORA)
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
        self.v.cli("explain", "--node", "lora", stdin="reply: Correct.\n" + EXPLAIN_LORA)
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


    def test_explain_lands_after_prose_written_before_it(self):
        v = Vault()
        v.to_teach_phase()
        v.cli("quiz", stdin=PREDICT)
        v.answer_quiz("The pretrained function")
        transcript = v.dir / "transcript.jsonl"
        transcript.write_text("")
        v.hook({"hook_event_name": "Stop", "transcript_path": str(transcript)})
        out = v.cli("explain", "--node", "lora", stdin="reply: Correct.\n" + EXPLAIN_LORA).stdout
        marker = out[out.index("⟦"):out.index("⟧") + 1]
        # Claude Code writes the step (its prose, then the tool result) only after the command ran.
        with open(transcript, "a") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"id": "m2", "role": "assistant", "content": [
                {"type": "text", "text": "Prose written before the explain call."}]}}) + "\n")
            fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "x", "content": f"(note markers, ignore: {marker})"}]}}) + "\n")
        v.cli("flush")
        note = v.note()
        self.assertLess(note.index("Prose written before"), note.index("## LoRA"))
        self.assertEqual(note.count("## LoRA"), 1)


    def _transcript(self, v):
        transcript = v.dir / "transcript.jsonl"
        transcript.write_text("")
        v.hook({"hook_event_name": "Stop", "transcript_path": str(transcript)})

        def add(entry):
            with open(transcript, "a") as fh:
                fh.write(json.dumps(entry) + "\n")
        return add

    def test_prose_in_the_same_step_as_a_question_lands_above_it(self):
        # The resume case: "Session resumed ..." and the re-asked question in one step.
        v = Vault()
        v.to_teach_phase()
        add = self._transcript(v)
        v.cli("quiz", stdin=PREDICT)
        q = questions.open_question(v.record())
        v.answer_quiz("The pretrained function")  # PreToolUse writes the question, PostToolUse the verdict
        add({"type": "assistant", "message": {"id": "m9", "role": "assistant", "content": [
            {"type": "text", "text": "Session resumed at the open prediction."},
            {"type": "tool_use", "id": q["qid"], "name": "AskUserQuestion", "input": questions.ask_payload(q)}]}})
        v.cli("flush")
        note = v.note()
        self.assertLess(note.index("Session resumed at the open prediction."), note.index("[!question] Predict"))
        self.assertLess(note.index("[!question] Predict"), note.rindex("Correct ✓"))

    def test_intro_line_before_an_open_question_lands_above_it(self):
        # "Correct at 95%. Here's a follow-up:" + the chat copy of the open question.
        v = Vault()
        v.to_teach_phase()
        add = self._transcript(v)
        v.cli("quiz", stdin=PREDICT)
        v.answer_quiz("The pretrained function")
        v.cli("explain", "--node", "lora", stdin="reply: Correct.\n" + EXPLAIN_LORA)
        question = "Why does LoRA start as the pretrained layer?"
        out = v.cli("recall", stdin={"type": "check", "nodeId": "lora", "uses": ["LoRA"], "question": question,
                                     "answer": "Because $BA = 0$ at initialisation."}).stdout
        markers = " ".join(m for m in out.split() if m.startswith("\u27e6"))
        add({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "r1", "content": f"(note markers, ignore: {markers})"}]}})
        v.cli("flush")  # places the queued check block
        add({"type": "assistant", "message": {"id": "m10", "role": "assistant", "content": [
            {"type": "text", "text": f"Correct at 95%. Here's a follow-up to answer in the chat:\n\n{question}"}]}})
        v.cli("flush")
        note = v.note()
        self.assertLess(note.index("Here's a follow-up"), note.index("[!question] Check"))
        self.assertEqual(note.count(question), 1)  # the chat copy is not repeated in the note


class ChatCopyTests(unittest.TestCase):
    """The learner may read only the chat (terminal, or a phone over remote
    control): explanations go to the note AND the chat, without duplicates."""

    def setUp(self):
        self.v = Vault()
        self.v.to_teach_phase()
        transcript = self.v.dir / "transcript.jsonl"
        transcript.write_text("")
        self.v.hook({"hook_event_name": "Stop", "transcript_path": str(transcript)})
        self.transcript = transcript
        self.v.cli("quiz", stdin=PREDICT)
        self.v.answer_quiz("The pretrained function")
        out = self.v.cli("explain", "--node", "lora", stdin="reply: Correct.\n" + EXPLAIN_LORA).stdout
        marker = out[out.index("\u27e6"):out.index("\u27e7") + 1]
        with open(transcript, "a") as fh:  # Claude Code writes the tool result, with its marker
            fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e1", "content": f"(note markers, ignore: {marker})"}]}}) + "\n")
        self.v.cli("flush")
        self.check = {"type": "check", "nodeId": "lora", "uses": ["LoRA"], "question": "How many parameters does LoRA add?",
                      "options": ["$2dr$", "$d^2$"], "correct": "$2dr$", "explanation": "x"}

    def say(self, text):
        with open(self.transcript, "a") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"id": f"m{text[:8]}", "role": "assistant",
                                                                  "content": [{"type": "text", "text": text}]}}) + "\n")

    def pre_ask(self):
        q = questions.open_question(self.v.record())
        return self.v.hook({"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_use_id": "ask1",
                            "tool_input": questions.ask_payload(q)})

    def test_chat_copy_is_kept_out_of_the_note(self):
        self.say("Correct.\n\nNew terms: LoRA: low-rank adaptation, a trainable update $BA$ added to a frozen matrix $W$. "
                 "$W_{up}$: the up-projection of the update, a $768 \\times 8$ matrix.\n\n## LoRA\n\n**LoRA** adds $BA$ "
                 "to the frozen $W$. Here $W_{up}$ starts at zero, so the layer starts as the pretrained one.")
        self.v.cli("quiz", stdin=self.check)
        self.assertNotIn('"deny"', self.pre_ask())
        note = self.v.note()
        self.assertEqual(note.count("so the layer starts as the pretrained one"), 1)

    def test_question_refused_once_while_the_copy_is_missing(self):
        self.say("The note has the LoRA section.")
        self.v.cli("quiz", stdin=self.check)
        self.assertIn('"deny"', self.pre_ask())
        self.assertNotIn('"deny"', self.pre_ask())  # once only: never a loop

    def test_next_message_reminds_when_the_copy_was_never_written(self):
        out = self.v.hook({"hook_event_name": "UserPromptSubmit", "prompt": "where is the explanation?"})
        self.assertIn("never appeared in the chat", out)

    def test_declined_dialog_leaves_the_question_open(self):
        self.say("Correct. New terms: LoRA: low-rank adaptation, a trainable update BA added to a frozen matrix W. "
                 "W_up: the up-projection. LoRA adds BA to the frozen W. Here W_up starts at zero, so the layer "
                 "starts as the pretrained one.")
        self.v.cli("quiz", stdin=self.check)
        q = questions.open_question(self.v.record())
        payload = questions.ask_payload(q)
        self.v.hook({"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_use_id": "d1",
                     "tool_input": payload})
        out = self.v.hook({"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion", "tool_use_id": "d1",
                           "tool_input": payload, "tool_response": "The user doesn't want to proceed with this tool use."})
        self.assertIn("still open", out)
        self.assertEqual(questions.open_question(self.v.record())["qid"], q["qid"])
        self.assertIn("Correct ✓", self.v.answer_quiz("$2dr$") and self.v.note())  # the re-asked dialog grades


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
        # reading state and printing it is not a write
        self.assertFalse(self.deny("Bash", {"command": f"python3 -c \"import json;g=json.load(open('{d}/.tutor/graph.json'));"
                                                      "print(json.dumps(g))\""}))
        # editing docs that merely mention a protected path is not a write to it
        self.assertFalse(self.deny("Bash", {"command": "python3 - <<'X'\nfrom pathlib import Path\n"
                                                      "p=Path('skills/teach/references/questions.md'); s=p.read_text()\n"
                                                      "s=s.replace('a', 'cap in `.tutor/config.json`')\np.write_text(s)\nX"}))
        self.assertTrue(self.deny("Bash", {"command": f"python3 -c \"open('{d}/Learning/Sessions/a.md','a').write('x')\""}))
        self.assertTrue(self.deny("Bash", {"command": "python3 - <<'X'\nimport json\np = vault + '/.tutor/sessions/a.json'\n"
                                                      "json.dump({}, open(p, 'w'))\nX"}))
        self.assertFalse(self.deny("Bash", {"command": "python3 tutor.py explain --node a <<'EOF'\nterms:\n- x :: y\n"
                                                      "uses: none\n---\nwrite( Learning/Sessions/ is fine here\nEOF"}))


if __name__ == "__main__":
    unittest.main()
