"""A recorded string holding U+0085, U+2028 or U+2029 keeps its record readable (BL-039).

The YAML subset every recovery record, relation file and entity frontmatter is written in puts a string
that could be misread in double quotes, as JSON. JSON keeps NEL, LINE SEPARATOR and PARAGRAPH SEPARATOR as
they are when it keeps non-ASCII text, but the reader took lines as ``str.splitlines`` does, and that ends a
line at each of the three - inside the string. A record holding one could be written and never read again:
``cannot read recovery record``, ``reconcile required``. Every operation reads every record in the runtime
area first, so one such record - a result message, a Work name, a Related target, even a request its own
validation refused - stopped every operation of the Project, and the resume of the one it belonged to,
while validation stayed silent. The event log had the same writer and reader shape.

The writer now escapes the three inside the string, so a value stays on its one physical line. The reader
still takes lines as before, except that it does not end one at such a character inside a double-quoted
scalar, so a record written before the fix reads back exactly, and the next save of that record writes the
escaped form. The event log ends a record at LF alone. The characters stay legal text: nothing refuses them.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase, git, launcher_command, run_python
from test_bootstrap_backfill_resume import REFUSE_PUSH_FLAG, REFUSE_PUSH_HOOK
from test_cancel_decision_resume import DECISION, CancelCase, cancel_windows
from workline import bootstrap as bs
from workline import create as cr
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import Mutation, MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import Event, ProjectStore, render_event_line
from workline.validate import validate_project

NEL = "\x85"
LS = "\N{LINE SEPARATOR}"
PS = "\N{PARAGRAPH SEPARATOR}"
SEPARATORS = {"NEL": NEL, "LS": LS, "PS": PS}
CHILD = Path(__file__).resolve().parent / "lock_child.py"


def escape_of(separator: str) -> str:
    return "\\u%04x" % ord(separator)


def raw_in(data: bytes) -> list[str]:
    """The separators ``data`` holds as raw characters."""
    return [name for name, separator in SEPARATORS.items() if separator.encode("utf-8") in data]


def as_written_before_the_fix(text: str) -> str:
    """``text`` with each escaped separator written raw again, as the writer wrote it before BL-039."""
    for separator in SEPARATORS.values():
        text = text.replace(escape_of(separator), separator)
    return text


# --------------------------------------------------------------------------- the YAML subset
class WriterTests(unittest.TestCase):
    def test_each_separator_round_trips_wherever_a_string_is_written(self) -> None:
        for name, separator in SEPARATORS.items():
            with self.subTest(name):
                doc = {
                    "message": f"docs: record the W1 result\n\nline one{separator}line two",
                    f"key{separator}": "value",
                    "items": [f"item{separator}", {"name": f"fix{separator}name", "content": f"---\nid: w_x\n---\n\n# note{separator}name\n"}],
                    "nested": {"to": f"docs/a{separator}b.md"},
                }
                text = yamlish.dump(doc)
                self.assertEqual(yamlish.load(text), doc)
                self.assertEqual(raw_in(text.encode("utf-8")), [])
                self.assertIn(escape_of(separator), text)
                # one value, one physical line, even for a reader that ends lines where str.splitlines does
                self.assertEqual(len(text.splitlines()), text.count("\n"))
                meta, body = yamlish.load_frontmatter(yamlish.dump_frontmatter({"id": "w_x", "note": f"x{separator}y"}, "# t\n"))
                self.assertEqual((meta, body), ({"id": "w_x", "note": f"x{separator}y"}, "# t\n"))

    def test_every_other_string_is_written_exactly_as_before(self) -> None:
        written = {
            "a\nb": 'm: "a\\nb"\n',
            "a\rb": 'm: "a\\rb"\n',
            "a\r\nb": 'm: "a\\r\\nb"\n',
            "a\x0bb\x0cc\x1cd": 'm: "a\\u000bb\\fc\\u001cd"\n',
            "日本語": "m: 日本語\n",
            "日本語: 値 # 注記": 'm: "日本語: 値 # 注記"\n',
            'quote " and \\ backslash': 'm: "quote \\" and \\\\ backslash"\n',
            "\\u2028 as text": 'm: "\\\\u2028 as text"\n',
        }
        for value, expected in written.items():
            with self.subTest(value=value):
                self.assertEqual(yamlish.dump({"m": value}), expected)
                self.assertEqual(yamlish.load(expected), {"m": value})


class ReaderTests(unittest.TestCase):
    def test_a_separator_written_raw_inside_a_double_quoted_scalar_reads_back(self) -> None:
        for name, separator in SEPARATORS.items():
            with self.subTest(name):
                doc = {
                    "effects": [{"seq": 1, "payload": {"message": f"docs: result\n\nline one{separator}line two", "paths": ["a.txt"]}}],
                    f"reserved{separator}key": "w_x",
                    "list": [f"{separator}item{separator}", "plain"],
                    "invocation": {"request": {"name": f"note{separator}name", "related": [{"type": "must_read", "to": f"a{separator}b"}]}},
                }
                legacy = as_written_before_the_fix(yamlish.dump(doc))
                self.assertGreater(len(legacy.splitlines()), legacy.count("\n"))
                self.assertEqual(yamlish.load(legacy), doc)

    def test_text_that_holds_no_such_string_reads_as_it_always_did(self) -> None:
        for name, separator in SEPARATORS.items():
            with self.subTest(name):
                # The separator ends the line anywhere outside a double-quoted scalar the writer would write.
                self.assertEqual(yamlish.load(f"a: 1{separator}b: 2\n"), {"a": 1, "b": 2})
                self.assertEqual(yamlish.load(f"a: 1{separator}\nb: 2\n"), {"a": 1, "b": 2})
                self.assertEqual(yamlish.load(f'a: say "hi{separator}b: 2\n'), {"a": 'say "hi', "b": 2})
                self.assertEqual(yamlish.load(f'# note: "x{separator}a: 1\n'), {"a": 1})
                self.assertEqual(yamlish.load(f'a: "x"{separator}b: 2\n'), {"a": "x", "b": 2})
                for refused in (f'- \xa0"v{separator}k: "v"\n', f'a:  "x{separator}y"\n', f'a: "x{separator}'):
                    with self.assertRaises(yamlish.YamlishError):
                        yamlish.load(refused)
                # The one change: inside a double-quoted scalar it is the text it always was.
                self.assertEqual(yamlish.load(f'a: "x{separator}y"\n'), {"a": f"x{separator}y"})
        for boundary in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\r", "\r\n"):
            with self.subTest(boundary=boundary):
                self.assertEqual(yamlish.load(f"a: 1{boundary}b: 2\n"), {"a": 1, "b": 2})
                with self.assertRaises(yamlish.YamlishError):
                    yamlish.load(f'a: "x{boundary}y"\n')


# --------------------------------------------------------------------------- the event log
class EventLogTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = ProjectStore(self.new_dir("events"))
        self.store.events_jsonl.parent.mkdir(parents=True)
        self.store.tmp.mkdir(parents=True)
        self.events = [Event(f"evt_{index}", "work_started", "w_1", f"at{separator}{index}") for index, separator in enumerate(SEPARATORS.values())]

    def test_an_event_line_holds_no_raw_separator_and_reads_back(self) -> None:
        lines = "".join(render_event_line(event) + "\n" for event in self.events)
        self.store.events_jsonl.write_bytes(lines.encode("utf-8"))
        self.assertEqual(raw_in(self.store.events_jsonl.read_bytes()), [])
        self.assertEqual(self.store.read_events(), self.events)

    def test_the_mutation_controller_appends_an_escaped_line(self) -> None:
        controller = MutationController(self.store)
        for event in self.events:
            controller.apply_effect({"kind": "append_event", "payload": {"record": event.to_record()}})
        data = self.store.events_jsonl.read_bytes()
        self.assertEqual(raw_in(data), [])
        self.assertEqual(data.count(b"\n"), len(self.events))
        self.assertEqual(self.store.read_events(), self.events)

    def test_a_line_written_before_the_fix_reads_back(self) -> None:
        raw = "".join(json.dumps(event.to_record(), ensure_ascii=False, separators=(",", ":")) + "\n" for event in self.events)
        self.store.events_jsonl.write_bytes(raw.encode("utf-8"))
        self.assertEqual(sorted(raw_in(self.store.events_jsonl.read_bytes())), sorted(SEPARATORS))
        self.assertEqual(self.store.read_events(), self.events)

    def test_a_record_ends_at_a_line_end_and_only_there(self) -> None:
        lines = [render_event_line(event) for event in self.events]
        self.store.events_jsonl.write_bytes(("\r\n".join(lines) + "\r\n\n").encode("utf-8"))
        self.assertEqual(self.store.read_events(), self.events)
        for name, separator in SEPARATORS.items():
            with self.subTest(name):
                self.store.events_jsonl.write_bytes((lines[0] + separator + lines[1] + "\n").encode("utf-8"))
                with self.assertRaises(ValidationError) as refused:
                    self.store.read_events()
                self.assertEqual(refused.exception.code, "events_invalid")


# --------------------------------------------------------------------------- operations
class SeparatorCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project("proj", remote=True)
        self.root = self.store.root
        self.remote = self.remote_path("proj")
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A が成立する"), "b": ("Phase B", "B が成立する")})
        self.phase_b = roadmap.phase_ids["b"]
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"})
        self.w1, self.w2 = entry.work_ids["w1"], entry.work_ids["w2"]
        (self.remote / "hooks" / "pre-receive").write_text(REFUSE_PUSH_HOOK, encoding="utf-8", newline="\n")

    # helpers ------------------------------------------------------------------------
    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote, "rev-parse", "refs/heads/main").strip()

    def refuse_pushes(self, refuse: bool) -> None:
        flag = self.remote / REFUSE_PUSH_FLAG
        if refuse:
            flag.write_text("refuse\n", encoding="utf-8")
        elif flag.exists():
            flag.unlink()

    def record_path(self, mutation_id: str) -> Path:
        return MutationController(self.store).intent_path(mutation_id)

    def only_record(self, status: str) -> dict:
        (record,) = [r for r in MutationController(self.store).list_records() if r["status"] == status]
        return record

    def rewrite_as_before_the_fix(self, path: Path) -> None:
        """Hold ``path`` as the writer before BL-039 wrote it: every escaped separator raw."""
        text = path.read_bytes().decode("utf-8")
        legacy = as_written_before_the_fix(text)
        self.assertNotEqual(legacy, text)
        self.assertGreater(len(legacy.splitlines()), legacy.count("\n"), "the pre-fix reader could not read it")
        path.write_bytes(legacy.encode("utf-8"))

    def question_after_w1(self, message: str):
        asked: list[str] = []

        def execute(ctx):
            own = f"result_{ctx.work.display}.txt"
            if ctx.work.id == self.w2 and not asked:
                asked.append(ctx.work.id)
                return st.QuestionWait("which way?")
            (self.root / own).write_text(f"{ctx.work.name}\n", encoding="utf-8")
            return st.Completed((own,), message if ctx.work.id == self.w1 else None)

        return execute

    def completing(self):
        def execute(ctx):
            own = f"result_{ctx.work.display}.txt"
            (self.root / own).write_text(f"{ctx.work.name}\n", encoding="utf-8")
            return st.Completed((own,))

        return execute

    def resume_in_another_process(self, work_id: str, mode: str) -> dict:
        signals = self.tmp / "signals"
        signals.mkdir(exist_ok=True)
        spec = self.tmp / "resume.json"
        spec.write_text(json.dumps({"scenario": "start_complete", "root": str(self.root), "name": "resume",
                                    "signal_dir": str(signals), "work_id": work_id, "mode": mode}), encoding="utf-8")
        done = subprocess.run([sys.executable, str(CHILD), str(spec)], capture_output=True, text=True, encoding="utf-8",
                              cwd=str(self.root), timeout=600)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def assertNothingLeftOver(self) -> None:
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.head(), self.remote_head())
        status = git(self.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        self.assertEqual([line for line in status if ".workline/runtime/" not in line], [])


class OperationTests(SeparatorCase):
    def test_a_question_wait_resumes_in_another_process_with_a_separator_in_the_result_message(self) -> None:
        message = f"docs: record the W1 result\n\nline one{LS}line two"
        waiting = st.start(self.store, self.w1, "outer", self.question_after_w1(message))
        self.assertEqual(waiting.status, "question_wait")
        record = self.only_record("pending")
        self.assertEqual(raw_in(self.record_path(record["mutation_id"]).read_bytes()), [])
        (commit,) = [e for e in record["effects"] if e["kind"] == "git_commit" and e["stage"].startswith(f"{self.w1}:results")]
        self.assertEqual(commit["payload"]["message"], message)
        stored = subprocess.run(["git", "-C", str(self.root), "cat-file", "commit", commit["commit_id"]], capture_output=True, check=True).stdout
        self.assertIn(f"line one{LS}line two".encode("utf-8"), stored)
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(bs.backfill_bootstrap(self.root).status, "already_present")

        resumed = self.resume_in_another_process(self.w1, "outer")

        self.assertEqual((resumed["outcome"], resumed["mutation_id"]), ("phase_complete", waiting.mutation_id))
        self.assertNothingLeftOver()

    def test_a_record_written_before_the_fix_recovers_and_its_first_save_writes_it_escaped(self) -> None:
        message = f"docs: record the W1 result\n\nline one{LS}line two"
        waiting = st.start(self.store, self.w1, "outer", self.question_after_w1(message))
        path = self.record_path(waiting.mutation_id)
        self.rewrite_as_before_the_fix(path)

        # Readable again: the unfinished record blocks what overlaps it the ordinary way, and nothing else.
        (record,) = MutationController(self.store).list_pending()
        self.assertIn(message, [e["payload"].get("message") for e in record["effects"] if e["kind"] == "git_commit"])
        with self.assertRaises(ReconcileRequired) as overlapping:
            rm.hold_phase(self.store, self.phase_b)
        self.assertIn("overlaps the planned write scope", overlapping.exception.message)
        self.assertEqual(bs.backfill_bootstrap(self.root).status, "already_present")
        self.assertEqual(validate_project(self.store), [])

        saved: list[bytes] = []
        real_save = Mutation._save

        def keep_first_save(mutation):
            real_save(mutation)
            if not saved:
                saved.append(mutation.path.read_bytes())

        with mock.patch.object(Mutation, "_save", keep_first_save):
            resumed = st.start(self.store, self.w1, "outer", self.completing())

        self.assertEqual((resumed.status, resumed.mutation_id), ("phase_complete", waiting.mutation_id))
        self.assertEqual(raw_in(saved[0]), [])
        self.assertIn(escape_of(LS).encode("ascii"), saved[0])
        self.assertEqual(raw_in(path.read_bytes()), [])
        self.assertNothingLeftOver()

    def test_an_interrupted_record_written_before_the_fix_blocks_no_unrelated_operation_and_resumes(self) -> None:
        spec = cr.WorkSpec(f"note{NEL}name", "メモが残っている")
        self.refuse_pushes(True)
        with self.assertRaises(StopError) as interrupted:
            cr.create_standalone_work(self.store, spec)
        self.assertEqual(interrupted.exception.code, "git_error")
        self.refuse_pushes(False)
        record = self.only_record("pending")
        self.assertEqual(record["invocation"]["name"], spec.name)
        self.rewrite_as_before_the_fix(self.record_path(record["mutation_id"]))

        self.assertEqual(rm.hold_phase(self.store, self.phase_b).status, "phase_held")
        created = cr.create_standalone_work(self.store, spec)

        self.assertTrue(created.resumed)
        self.assertEqual(created.mutation_id, record["mutation_id"])
        self.assertEqual(raw_in(self.record_path(record["mutation_id"]).read_bytes()), [])
        self.assertNothingLeftOver()

    def test_a_request_its_own_validation_refused_leaves_a_record_nothing_is_blocked_by(self) -> None:
        refused = cr.WorkSpec(f"note{PS}name", "メモが残っている", related=(cr.RelatedSpec("not_a_related_type", "docs/x.md"),))
        with self.assertRaises(ValidationError):
            cr.create_standalone_work(self.store, refused)
        record = self.only_record("abandoned")
        self.assertEqual(record["invocation"]["name"], refused.name)
        # An abandoned record is never saved again: it has to stay readable as it was written before the fix.
        self.rewrite_as_before_the_fix(self.record_path(record["mutation_id"]))

        self.assertEqual(rm.hold_phase(self.store, self.phase_b).status, "phase_held")
        self.assertFalse(cr.create_standalone_work(self.store, cr.WorkSpec("Other note", "別のメモが残っている")).resumed)
        self.assertEqual(self.only_record("abandoned")["invocation"]["name"], refused.name)
        self.assertNothingLeftOver()

    def test_a_related_target_holding_a_separator_is_written_escaped_and_an_older_file_still_reads(self) -> None:
        target = f"docs/a{LS}b.md"
        created = cr.create_standalone_work(self.store, cr.WorkSpec("Related note", "メモが残っている", related=(cr.RelatedSpec("must_read", target),)))
        related = self.store.related_yaml
        self.assertEqual(raw_in(related.read_bytes()), [])
        self.assertIn((created.work_id, "must_read", target), {(r.from_id, r.type, r.to) for r in ProjectView.load(self.store).related})
        self.assertNothingLeftOver()

        # A related.yaml the writer before BL-039 committed: read as it is, and rewritten by nothing but its own writes.
        self.rewrite_as_before_the_fix(related)
        git(self.root, "commit", "-q", "-m", "chore: related.yaml as written before the fix", "--", ".workline/relations/related.yaml")
        legacy = related.read_bytes()
        self.assertIn((created.work_id, "must_read", target), {(r.from_id, r.type, r.to) for r in ProjectView.load(self.store).related})
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(rm.hold_phase(self.store, self.phase_b).status, "phase_held")
        self.assertEqual(related.read_bytes(), legacy)

        rm.maintain_work_related(self.store, self.w2, add=(cr.RelatedSpec("must_read", "docs/plain.md"),))

        self.assertEqual(raw_in(related.read_bytes()), [])
        self.assertEqual(
            {(r.from_id, r.to) for r in ProjectView.load(self.store).related},
            {(created.work_id, target), (self.w2, "docs/plain.md")},
        )
        self.assertNothingLeftOver()

    def test_create_work_on_the_command_line_takes_a_name_holding_a_separator(self) -> None:
        command = launcher_command(WORKLINE_ROOT, "create-work", ".", "--name", f"note{LS}name", "--desired-state", "メモが残っている")
        self.refuse_pushes(True)
        interrupted = run_python(command, cwd=self.root)
        self.assertEqual(interrupted.returncode, 1, interrupted.stdout + interrupted.stderr)
        self.assertIn("STOP [git_error]", interrupted.stdout)
        self.refuse_pushes(False)

        created = run_python(command, cwd=self.root)
        checked = run_python(launcher_command(WORKLINE_ROOT, "validate-project", "."), cwd=self.root)

        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        self.assertIn("create-work: w_", created.stdout)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("project validation: PASS", checked.stdout)
        self.assertEqual(self.only_record("completed")["invocation"]["name"], f"note{LS}name")
        self.assertNothingLeftOver()


class CancelDecisionTests(CancelCase):
    """A START cancel records its decision only when the record keeps every part of it exactly (BL-030): these texts are kept."""

    def test_a_cancel_decided_with_separators_in_its_reason_and_new_work_is_recorded_and_carried_on(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        rid, pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, pa, {"w1": "W1", "w2": "W2"})
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        reason = f"superseded{NEL}by R{LS}for good{PS}"
        name, desired, detail, target = f"置き換え{LS}R", f"replaces W1{PS}entirely", f"W1 was{NEL}the wrong cut", f"docs/a{LS}b.md"
        replan = Replan(
            remove_relation_ids=(self.rel("requires_completion", w1, i1),),
            add_relations=(cr.RelationSpec("requires_completion", "r", i1),),
            new_works={"r": cr.WorkSpec(name, desired, phase_id=pa, roadmap_id=rid,
                                        related=(cr.RelatedSpec("must_read", target),), derivation_detail=detail)},
        )
        call = lambda: st.start(self.store, w1, "single-work", self.executor({w1: st.Cancel(replan, reason)}))  # noqa: E731
        pending = self.interrupt(cancel_windows(w1)["cancel applied"], call)
        decision = self.cancel_effect(pending, w1)["payload"][DECISION]
        (work,) = decision["new_works"]
        self.assertEqual(decision["reason"], reason)
        self.assertEqual((work["name"], work["desired_state"], work["derivation_detail"], work["related"][0]["to"]), (name, desired, detail, target))
        self.assertEqual(raw_in(MutationController(self.store).intent_path(pending["mutation_id"]).read_bytes()), [])

        result = call()

        self.assertEqual((result.status, result.detail, result.mutation_id), ("cancelled", reason, pending["mutation_id"]))
        replacement = self.record_of(pending["mutation_id"])["reserved_ids"][f"{w1}:cancel:0:works:work:r"]
        view = ProjectView.load(self.store)
        self.assertIn(f"# {name}\n", view.works[replacement].body)
        self.assertIn(desired, view.works[replacement].body)
        self.assertEqual([(r.type, r.to) for r in view.related_from(replacement)], [("must_read", target)])
        (derivation,) = sorted((self.store.root / ".workline" / "derivations").glob("*.md"))
        self.assertIn(detail, derivation.read_text(encoding="utf-8"))
        self.assertEqual(self.ran, [w1])
        self.assertCancelled(w1)


if __name__ == "__main__":
    unittest.main()
