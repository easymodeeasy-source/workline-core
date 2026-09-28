"""RAW commit ancestry: the stored object is the only authority (P3 F3 §7.1.8, IP-26, IP26-B1).

Git's revision view and Git's stored objects disagree, and the disagreement is
attacker-controllable: a graft file makes ``merge-base --is-ancestor`` answer FALSE for a
genuine ancestor, ``refs/replace`` makes an oid mean another object, and a shallow clone
makes a commit with two stored parents look like a root. So P3 proofs read the literal
``parent`` headers of the commit object, through Unit 1's class B envelope, as bytes.

The tests below are in three groups. Some drive real Git in disposable repositories,
because the hazards are Git's. Some drive a fake parent reader, because a budget test
should not make four thousand subprocesses. One - the lone-CR object - exists because
reading the object as text silently loses a parent, which fails OPEN.

This is Unit 2 alone: the reader exists and nothing dispatches to it.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline import gitcmd
from workline.errors import StopError
from workline.review import ancestry, hermetic, paths as review_paths
from workline.review.ancestry import NON_LINEAR, UNKNOWN
from workline.store import ProjectStore

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
OID = "0123456789abcdef0123456789abcdef01234567"


def oid_of(number: int, *, width: int = 40) -> str:
    """A synthetic full oid, for tests that never touch a real object store."""
    return f"{number:0{width}x}"


class FakeHermetic:
    """Stands in for the class B authority where only the parent answers matter."""

    def __init__(self, parents: dict[str, tuple[str, ...]]) -> None:
        self.parents = parents
        self.reads: list[str] = []

    def read(self, oid: str):
        self.reads.append(oid)
        return self.parents.get(oid, UNKNOWN)


def fake_reader(fake: FakeHermetic):
    """Patch raw_parents so the scheduler can be tested without a repository."""
    return mock.patch.object(ancestry, "raw_parents", lambda _h, oid: fake.read(oid))


# --------------------------------------------------------------------------- the reader, on real objects


class RealRepositoryCase(WorklineTestCase):
    """A Project with an entered hermetic authority and helpers to write raw objects."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        git(self.store.root, "config", "user.name", "Real Person")
        git(self.store.root, "config", "user.email", "real@proj")
        self.hermetic = hermetic.enter(self.store)

    def clean_env(self) -> dict[str, str]:
        return {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}

    def plain(self, *args: str) -> str:
        found = subprocess.run(
            ["git", "-C", str(self.store.root), *args], capture_output=True, text=True, env=self.clean_env()
        )
        return found.stdout.strip()

    def commit(self, message: str, parents: tuple[str, ...] = ()) -> str:
        arguments = ["commit-tree", "--no-gpg-sign", "-m", message, EMPTY_TREE]
        for parent in parents:
            arguments += ["-p", parent]
        environment = {
            **self.clean_env(),
            "GIT_AUTHOR_NAME": "A", "GIT_AUTHOR_EMAIL": "a@x", "GIT_AUTHOR_DATE": "1700000000 +0000",
            "GIT_COMMITTER_NAME": "A", "GIT_COMMITTER_EMAIL": "a@x", "GIT_COMMITTER_DATE": "1700000000 +0000",
        }
        found = subprocess.run(
            ["git", "-C", str(self.store.root), *arguments],
            capture_output=True, text=True, env=environment, input="",
        )
        return found.stdout.strip()

    def literal_object(self, body: bytes) -> str:
        """Write an exact commit object, bypassing every sanity check commit-tree applies."""
        found = subprocess.run(
            ["git", "-C", str(self.store.root), "hash-object", "-t", "commit", "-w", "--stdin", "--literally"],
            input=body, capture_output=True, env=self.clean_env(),
        )
        return found.stdout.decode().strip()

    def chain(self, length: int) -> list[str]:
        made: list[str] = []
        parent: tuple[str, ...] = ()
        for number in range(length):
            made.append(self.commit(f"c{number}", parent))
            parent = (made[-1],)
        return made


class ParentHeaderTests(RealRepositoryCase):
    """What the stored object says, exactly."""

    def test_a_root_reads_as_a_known_empty_tuple(self) -> None:
        root = self.commit("root")
        self.assertEqual(ancestry.raw_parents(self.hermetic, root), ())

    def test_a_root_is_not_unknown(self) -> None:
        """The two must never be confused: one is an answer, the other is a refusal."""
        self.assertIsNot(ancestry.raw_parents(self.hermetic, self.commit("root")), UNKNOWN)

    def test_one_parent_reads_back(self) -> None:
        first = self.commit("a")
        second = self.commit("b", (first,))
        self.assertEqual(ancestry.raw_parents(self.hermetic, second), (first,))

    def test_a_merge_keeps_every_parent_in_stored_order(self) -> None:
        """M-60: count and order are the object's, and nothing sorts them."""
        left = self.commit("l")
        right = self.commit("r")
        merge = self.commit("m", (left, right))
        self.assertEqual(ancestry.raw_parents(self.hermetic, merge), (left, right))
        other = self.commit("m2", (right, left))
        self.assertEqual(ancestry.raw_parents(self.hermetic, other), (right, left))

    def test_an_octopus_keeps_all_three(self) -> None:
        one, two, three = self.commit("1"), self.commit("2"), self.commit("3")
        merge = self.commit("o", (one, two, three))
        self.assertEqual(ancestry.raw_parents(self.hermetic, merge), (one, two, three))

    def test_a_message_line_that_looks_like_a_header_is_not_one(self) -> None:
        """Only the header block is authoritative; the message is not parsed at all."""
        real = self.commit("a")
        forged = self.commit(f"subject\n\nparent {'b' * 40}\n", (real,))
        self.assertEqual(ancestry.raw_parents(self.hermetic, forged), (real,))


class LoneCarriageReturnTests(RealRepositoryCase):
    """The decisive byte test: text mode loses a parent, and loses it fail-open."""

    def literal_with_lone_cr(self) -> tuple[str, str, str]:
        first, second = "1" * 40, "2" * 40
        body = (
            b"tree " + EMPTY_TREE.encode() + b"\n"
            b"parent " + first.encode() + b"\n"
            b"\r\n"
            b"parent " + second.encode() + b"\n"
            b"author A <a@x> 1700000000 +0000\n"
            b"committer A <a@x> 1700000000 +0000\n"
            b"\nmessage\n"
        )
        return self.literal_object(body), first, second

    def test_both_parents_survive_a_lone_cr_header_line(self) -> None:
        oid, first, second = self.literal_with_lone_cr()
        self.assertEqual(ancestry.raw_parents(self.hermetic, oid), (first, second))

    def test_reading_the_same_object_as_text_would_have_lost_one(self) -> None:
        """Why the reader uses bytes - stated as a measurement, not an assumption."""
        oid, _, _ = self.literal_with_lone_cr()
        as_text = self.hermetic.run("cat-file", "commit", oid, check=False).stdout
        text_parents = [l for l in as_text.split("\n\n", 1)[0].splitlines() if l.startswith("parent ")]
        self.assertEqual(len(text_parents), 1, "text mode should lose a parent here")
        self.assertEqual(len(ancestry.raw_parents(self.hermetic, oid)), 2)


class MalformedObjectTests(RealRepositoryCase):
    """Anything the header block cannot be trusted for is UNKNOWN, never a shorter answer."""

    def body_with(self, parent_line: bytes) -> bytes:
        return (
            b"tree " + EMPTY_TREE.encode() + b"\n"
            b"parent " + ("1" * 40).encode() + b"\n"
            + parent_line +
            b"author A <a@x> 1700000000 +0000\n"
            b"committer A <a@x> 1700000000 +0000\n"
            b"\nmessage\n"
        )

    def test_a_malformed_parent_oid_is_unknown(self) -> None:
        oid = self.literal_object(self.body_with(b"parent notanoid\n"))
        self.assertIs(ancestry.raw_parents(self.hermetic, oid), UNKNOWN)

    def test_an_abbreviated_parent_oid_is_unknown(self) -> None:
        oid = self.literal_object(self.body_with(b"parent " + ("2" * 12).encode() + b"\n"))
        self.assertIs(ancestry.raw_parents(self.hermetic, oid), UNKNOWN)

    def test_an_uppercase_parent_oid_is_unknown(self) -> None:
        oid = self.literal_object(self.body_with(b"parent " + ("A" * 40).encode() + b"\n"))
        self.assertIs(ancestry.raw_parents(self.hermetic, oid), UNKNOWN)

    def test_a_wrong_width_parent_is_unknown(self) -> None:
        """A 40-hex commit citing a 64-hex parent is malformed, not a mixed-format history."""
        oid = self.literal_object(self.body_with(b"parent " + ("3" * 64).encode() + b"\n"))
        self.assertIs(ancestry.raw_parents(self.hermetic, oid), UNKNOWN)

    def test_no_partial_parent_list_is_ever_returned(self) -> None:
        """The valid parent before the malformed line must not be reported on its own."""
        oid = self.literal_object(self.body_with(b"parent notanoid\n"))
        found = ancestry.raw_parents(self.hermetic, oid)
        self.assertIs(found, UNKNOWN)
        self.assertNotEqual(found, ("1" * 40,))


class ObjectIdentityTests(RealRepositoryCase):
    """Only a full oid naming a commit object is an input."""

    def test_a_nonexistent_object_is_unknown(self) -> None:
        self.assertIs(ancestry.raw_parents(self.hermetic, "0" * 40), UNKNOWN)

    def test_a_tree_is_unknown(self) -> None:
        self.assertIs(ancestry.raw_parents(self.hermetic, EMPTY_TREE), UNKNOWN)

    def test_a_blob_is_unknown(self) -> None:
        (self.store.root / "blob.txt").write_text("x", encoding="utf-8", newline="\n")
        blob = self.plain("hash-object", "-w", "blob.txt")
        self.assertIs(ancestry.raw_parents(self.hermetic, blob), UNKNOWN)

    def test_an_annotated_tag_is_unknown_although_git_peels_it(self) -> None:
        """MEASURED: `cat-file commit <tag>` PEELS to the tagged commit and exits 0.

        Without a type check the tag's oid would be answered with another object's
        parents, so the reader asks `cat-file -t` first and requires exactly `commit`.
        """
        target = self.commit("tagged")
        self.plain("tag", "-a", "v1", "-m", "t", target)
        tag = self.plain("rev-parse", "v1")
        self.assertNotEqual(tag, target, "an annotated tag is its own object")
        peeled = self.hermetic.run_bytes("cat-file", "commit", tag)
        self.assertTrue(peeled.ok, "Git does peel it, which is exactly the hazard")
        self.assertIs(ancestry.raw_parents(self.hermetic, tag), UNKNOWN)

    def test_an_abbreviation_is_refused_before_git_is_asked(self) -> None:
        full = self.commit("a")
        with mock.patch.object(hermetic.HermeticGit, "run_bytes") as never:
            self.assertIs(ancestry.raw_parents(self.hermetic, full[:12]), UNKNOWN)
        never.assert_not_called()

    def test_revision_expressions_are_refused_before_git_is_asked(self) -> None:
        full = self.commit("a")
        for expression in ("HEAD", "main", f"{full}^", f"{full}^{{commit}}", full.upper(), full[:39], full + "a"):
            with self.subTest(expression=expression):
                with mock.patch.object(hermetic.HermeticGit, "run_bytes") as never:
                    self.assertIs(ancestry.raw_parents(self.hermetic, expression), UNKNOWN)
                never.assert_not_called()

    def test_a_hermetic_stop_is_not_swallowed_into_unknown(self) -> None:
        """A broken execution environment is a STOP, not an ancestry answer."""
        hooks = self.store.root / review_paths.RUNTIME_NO_HOOKS_DIR
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "post-index-change").write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
        with self.assertRaises(StopError) as caught:
            ancestry.raw_parents(self.hermetic, self.commit("a"))
        self.assertEqual(caught.exception.code, "review_hooks_path_invalid")


class ClassBInvocationTests(RealRepositoryCase):
    """The read travels through the complete Unit 1 envelope, not a hand-built one."""

    def captured(self):
        seen: list[tuple[tuple[str, ...], dict]] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            seen.append((args, kwargs))
            return real(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git_bytes", recording):
            ancestry.raw_parents(self.hermetic, self.commit("a"))
        found = [call for call in seen if "commit" in call[0] and "cat-file" in call[0]]
        self.assertTrue(found)
        return found[-1]

    def settings(self, args: tuple[str, ...]) -> dict[str, str]:
        return dict(
            argument.split("=", 1)
            for position, argument in enumerate(args)
            if position > 0 and args[position - 1] == "-c"
        )

    def test_the_exact_six_class_b_variables_and_nothing_else(self) -> None:
        _, kwargs = self.captured()
        names = {name for name in kwargs["env"] if name.upper().startswith("GIT_")}
        self.assertEqual(names, set(hermetic.CLASS_B_ALLOWLIST))

    def test_no_replace_and_no_lazy_fetch_are_on_the_actual_invocation(self) -> None:
        _, kwargs = self.captured()
        self.assertEqual(kwargs["env"]["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")

    def test_every_frozen_configuration_control_is_carried(self) -> None:
        args, _ = self.captured()
        settings = self.settings(args)
        for key, value in hermetic.CLASS_B_CONFIGURATION:
            with self.subTest(setting=key):
                self.assertEqual(settings.get(key), value)
        self.assertIn("core.hooksPath", settings)

    def test_no_identity_no_date_and_no_index_file(self) -> None:
        """A read writes no commit and touches no index."""
        _, kwargs = self.captured()
        for name in (*hermetic.CLASS_B_IDENTITY_VARIABLES, "GIT_INDEX_FILE"):
            with self.subTest(variable=name):
                self.assertNotIn(name, kwargs["env"])

    def test_the_output_is_not_decoded(self) -> None:
        found = self.hermetic.run_bytes("cat-file", "commit", self.commit("a"))
        self.assertIsInstance(found.stdout, bytes)

    def test_no_revision_walker_is_ever_invoked(self) -> None:
        """Asserted on the commands actually run, not on the module's prose.

        Every Git invocation the reader makes across a representative set of questions
        must be a `cat-file`. A revision walker - `rev-list`, `merge-base`, `log`,
        `rev-parse` - is what grafts and shallow boundaries lie to, and none may appear.
        """
        made = self.chain(3)
        merge = self.commit("m", (made[2], made[0]))
        commands: list[tuple[str, ...]] = []
        real_bytes, real_text = gitcmd.run_git_bytes, gitcmd.run_git

        def watch_bytes(repo, *args, **kwargs):
            commands.append(args)
            return real_bytes(repo, *args, **kwargs)

        def watch_text(repo, *args, **kwargs):
            commands.append(args)
            return real_text(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git_bytes", watch_bytes), \
             mock.patch.object(gitcmd, "run_git", watch_text):
            ancestry.raw_parents(self.hermetic, made[2])
            ancestry.raw_descends_from(self.hermetic, made[2], made[0])
            ancestry.raw_range(self.hermetic, made[0], made[2])
            ancestry.raw_range(self.hermetic, made[0], merge)

        self.assertTrue(commands)
        for args in commands:
            # skip each -c and the setting that follows it; the next bare word is the verb
            rest = list(args)
            while rest and rest[0] == "-c":
                rest = rest[2:]
            with self.subTest(command=rest[0] if rest else None):
                self.assertEqual(rest[0], "cat-file")


# --------------------------------------------------------------------------- hostile Git


class GraftTests(RealRepositoryCase):
    """M-57: a graft file rewrites the revision view and nothing about the object."""

    def test_the_stored_parent_is_unchanged_by_a_graft(self) -> None:
        made = self.chain(4)
        c1, c3, c4 = made[0], made[2], made[3]
        # entered BEFORE the graft exists, because the entry check refuses a non-empty one
        info = self.store.root / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "grafts").write_text(f"{c4} {c1}\n", encoding="utf-8", newline="\n")

        walker = self.plain("rev-list", "--parents", "-n", "1", c4).split()
        self.assertEqual(walker[1:], [c1], "the revision view should be lied to")
        self.assertEqual(ancestry.raw_parents(self.hermetic, c4), (c3,))
        self.assertIs(ancestry.raw_descends_from(self.hermetic, c4, made[1]), True)

    def test_the_entry_refusal_is_not_weakened(self) -> None:
        info = self.store.root / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "grafts").write_text("dead beef\n", encoding="utf-8", newline="\n")
        with self.assertRaises(StopError) as caught:
            hermetic.enter(self.store)
        self.assertEqual(caught.exception.code, "review_repository_grafted")


class ReplaceTests(RealRepositoryCase):
    """M-58: an oid means the object it names, not a refs/replace view."""

    def test_the_true_parent_is_read_through_a_replacement(self) -> None:
        made = self.chain(3)
        c1, c2, c3 = made
        decoy = self.commit("decoy")
        self.plain("replace", "-f", c2, decoy)

        plain = subprocess.run(
            ["git", "-C", str(self.store.root), "cat-file", "commit", c2],
            capture_output=True, text=True, env=self.clean_env(),
        ).stdout
        plain_parents = [l.split()[1] for l in plain.split("\n\n", 1)[0].splitlines() if l.startswith("parent ")]
        self.assertNotEqual(plain_parents, [c1], "a plain read should see the replacement")
        self.assertEqual(ancestry.raw_parents(self.hermetic, c2), (c1,))
        self.assertIs(ancestry.raw_descends_from(self.hermetic, c3, c1), True)


class ShallowBoundaryTests(WorklineTestCase):
    """M-59: the walker calls it a root; the object names parents that are not here."""

    def clean_env(self) -> dict[str, str]:
        return {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}

    def shallow_clone(self):
        source = self.new_dir("shallow-source")
        git(source, "init", "-b", "main")
        git(source, "config", "user.name", "A")
        git(source, "config", "user.email", "a@x")
        for number in range(3):
            (source / f"f{number}.txt").write_text(f"{number}\n", encoding="utf-8", newline="\n")
            git(source, "add", f"f{number}.txt")
            git(source, "commit", "-m", f"c{number}")
        target = self.new_dir("shallow-clone")
        git(self.tmp, "clone", "-q", "--depth=1", source.resolve().as_uri(), str(target))
        git(target, "config", "user.name", "A")
        git(target, "config", "user.email", "a@x")
        (target / ".workline").mkdir(exist_ok=True)
        return ProjectStore(target)

    def test_a_named_but_absent_parent_is_unknown_never_a_root(self) -> None:
        store = self.shallow_clone()
        marker = store.root / ".git" / "shallow"
        self.assertTrue(marker.is_file(), "the clone is genuinely shallow")
        kept = marker.read_bytes()
        # enter() correctly refuses a shallow repository; hide the marker only long enough to
        # obtain the authority, then restore it byte for byte before any ancestry read.
        marker.unlink()
        try:
            built = hermetic.enter(store)
        finally:
            marker.write_bytes(kept)
        self.assertEqual(marker.read_bytes(), kept)

        head = subprocess.run(
            ["git", "-C", str(store.root), "rev-parse", "HEAD"],
            capture_output=True, text=True, env=self.clean_env(),
        ).stdout.strip()
        walker = subprocess.run(
            ["git", "-C", str(store.root), "rev-list", "--parents", "-n", "1", head],
            capture_output=True, text=True, env=self.clean_env(),
        ).stdout.split()
        self.assertEqual(walker[1:], [], "the walker should report a root")

        stored = ancestry.raw_parents(built, head)
        self.assertNotEqual(stored, (), "the object still names a parent")
        self.assertIsNot(stored, UNKNOWN)
        absent = stored[0]
        self.assertIs(ancestry.raw_parents(built, absent), UNKNOWN)
        self.assertIs(ancestry.raw_descends_from(built, head, "9" * 40), UNKNOWN)

    def test_the_entry_refusal_is_not_weakened(self) -> None:
        store = self.shallow_clone()
        with self.assertRaises(StopError) as caught:
            hermetic.enter(store)
        self.assertEqual(caught.exception.code, "review_repository_shallow")


class ObjectFormatTests(WorklineTestCase):
    """Both widths, matched exactly."""

    def project_with_format(self, object_format: str):
        root = self.new_dir(f"fmt-{object_format}")
        made = subprocess.run(
            ["git", "init", "-q", "-b", "main", f"--object-format={object_format}", str(root)],
            capture_output=True, text=True,
        )
        if made.returncode != 0:
            self.skipTest(f"this Git cannot create a {object_format} repository: {made.stderr.strip()[:80]}")
        git(root, "config", "user.name", "A")
        git(root, "config", "user.email", "a@x")
        (root / "f.txt").write_text("x\n", encoding="utf-8", newline="\n")
        git(root, "add", "f.txt")
        git(root, "commit", "-m", "c0")
        (root / "g.txt").write_text("y\n", encoding="utf-8", newline="\n")
        git(root, "add", "g.txt")
        git(root, "commit", "-m", "c1")
        (root / ".workline").mkdir(exist_ok=True)
        return ProjectStore(root)

    def check(self, object_format: str, width: int) -> None:
        store = self.project_with_format(object_format)
        built = hermetic.enter(store)
        head = subprocess.run(
            ["git", "-C", str(store.root), "rev-parse", "HEAD"], capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
        ).stdout.strip()
        self.assertEqual(len(head), width)
        parents = ancestry.raw_parents(built, head)
        self.assertIsNot(parents, UNKNOWN)
        self.assertEqual(len(parents), 1)
        self.assertEqual(len(parents[0]), width)
        self.assertIs(ancestry.raw_descends_from(built, head, parents[0]), True)

    def test_sha1_forty_hex(self) -> None:
        self.check("sha1", 40)

    def test_sha256_sixty_four_hex(self) -> None:
        self.check("sha256", 64)


# --------------------------------------------------------------------------- the scheduler


class SchedulerTests(unittest.TestCase):
    """The canonical FIFO schedule of IP26-B1, driven by a fake reader."""

    def test_the_reviewer_divergence_case_has_one_answer(self) -> None:
        """H -> [R1, L1], L1 -> A, R1 -> a long chain. FIFO reaches A; depth-first would not.

        The determinate sequence under the frozen rule A-F is H, R1, L1, R2, A - five
        reads. §7.1.8's worked-case NARRATIVE says "H, then R1, then L1, then A ... in
        four steps", which skips R2: reading R1 enqueues R2 behind the already-queued L1,
        so R2 is taken before A. Four steps would require answering YES when A is
        ENQUEUED, and the same clause forbids exactly that ("WHY YES REQUIRES THE READ"),
        because a named-but-absent parent must never be a proof. The rule is authority;
        the illustration undercounts. What the illustration is actually about does hold
        and is asserted below: L1 is reached before the chain goes deep, so the long R
        branch cannot starve it, and the answer is YES rather than UNKNOWN.
        """
        h, r1, l1, a = oid_of(1), oid_of(2), oid_of(3), oid_of(4)
        chain = [oid_of(100 + n) for n in range(8000)]
        parents = {h: (r1, l1), l1: (a,), a: (), r1: (chain[0],)}
        for index, node in enumerate(chain[:-1]):
            parents[node] = (chain[index + 1],)
        parents[chain[-1]] = ()
        fake = FakeHermetic(parents)
        with fake_reader(fake):
            found = ancestry.raw_descends_from(None, h, a)
        self.assertIs(found, True)
        self.assertEqual(fake.reads, [h, r1, l1, chain[0], a])
        # the point of the case: the deep branch is never walked, and A is read
        self.assertNotIn(chain[1], fake.reads)
        self.assertLess(fake.reads.index(l1), fake.reads.index(chain[0]))
        self.assertIn(a, fake.reads)

    def test_a_depth_first_walk_would_have_answered_unknown_here(self) -> None:
        """Why the schedule is frozen: the same graph, walked depth-first, exhausts the budget."""
        h, r1, l1, a = oid_of(1), oid_of(2), oid_of(3), oid_of(4)
        chain = [oid_of(100 + n) for n in range(8000)]
        parents = {h: (r1, l1), l1: (a,), a: (), r1: (chain[0],)}
        for index, node in enumerate(chain[:-1]):
            parents[node] = (chain[index + 1],)
        parents[chain[-1]] = ()

        # A depth-first schedule over the same stored parents, for comparison only: parents
        # are pushed in reverse so the FIRST stored parent (R1) is explored first, which is
        # what "depth-first in header order" means.
        stack, seen, steps = [h], {h}, 0
        answer: object = False
        while stack:
            current = stack.pop()
            if steps == ancestry.P3_RAW_ANCESTRY_STEP_BUDGET:
                answer = UNKNOWN
                break
            steps += 1
            if current == a:
                answer = True
                break
            for parent in reversed(parents.get(current, ())):
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        self.assertIs(answer, UNKNOWN, "depth-first exhausts the budget on the R chain")

        fake = FakeHermetic(parents)
        with fake_reader(fake):
            self.assertIs(ancestry.raw_descends_from(None, h, a), True)

    def test_parents_are_enqueued_in_stored_header_order(self) -> None:
        head, first, second = oid_of(1), oid_of(2), oid_of(3)
        fake = FakeHermetic({head: (first, second), first: (), second: ()})
        with fake_reader(fake):
            ancestry.raw_descends_from(None, head, oid_of(99))
        self.assertEqual(fake.reads, [head, first, second])

    def test_a_shared_ancestor_is_read_once_in_one_evaluation(self) -> None:
        head, left, right, shared = oid_of(1), oid_of(2), oid_of(3), oid_of(4)
        fake = FakeHermetic({head: (left, right), left: (shared,), right: (shared,), shared: ()})
        with fake_reader(fake):
            self.assertIs(ancestry.raw_descends_from(None, head, oid_of(99)), False)
        self.assertEqual(fake.reads.count(shared), 1)
        self.assertEqual(len(fake.reads), 4)

    def test_a_later_evaluation_reads_the_same_oid_again(self) -> None:
        """`seen` is evaluation-local: §21.15's "re-reads every time it is asked" is untouched."""
        head, parent = oid_of(1), oid_of(2)
        fake = FakeHermetic({head: (parent,), parent: ()})
        with fake_reader(fake):
            ancestry.raw_descends_from(None, head, parent)
            ancestry.raw_descends_from(None, head, parent)
        self.assertEqual(fake.reads.count(head), 2)

    def test_the_reflexive_case_reads_nothing(self) -> None:
        fake = FakeHermetic({})
        with fake_reader(fake):
            self.assertIs(ancestry.raw_descends_from(None, OID, OID), True)
        self.assertEqual(fake.reads, [])

    def test_two_identical_invalid_strings_are_not_a_proof(self) -> None:
        """Validation precedes the reflexive shortcut."""
        for value in ("HEAD", "main", "not-an-oid", OID.upper(), OID[:12]):
            with self.subTest(value=value):
                self.assertIs(ancestry.raw_descends_from(None, value, value), UNKNOWN)

    def test_a_non_reflexive_yes_requires_reading_the_ancestor_object(self) -> None:
        """A named-but-absent parent is UNKNOWN, never a successful ancestry proof."""
        head, absent = oid_of(1), oid_of(2)
        fake = FakeHermetic({head: (absent,)})  # absent has no entry -> UNKNOWN when read
        with fake_reader(fake):
            self.assertIs(ancestry.raw_descends_from(None, head, absent), UNKNOWN)
        self.assertIn(absent, fake.reads)

    def test_queue_exhaustion_is_no_and_never_hides_unknown(self) -> None:
        head, parent = oid_of(1), oid_of(2)
        fake = FakeHermetic({head: (parent,), parent: ()})
        with fake_reader(fake):
            self.assertIs(ancestry.raw_descends_from(None, head, oid_of(99)), False)

    def test_an_unreadable_object_on_the_way_is_unknown_not_no(self) -> None:
        head, broken = oid_of(1), oid_of(2)
        fake = FakeHermetic({head: (broken,)})
        with fake_reader(fake):
            self.assertIs(ancestry.raw_descends_from(None, head, oid_of(99)), UNKNOWN)


class BudgetTests(unittest.TestCase):
    """The frozen bound, at its exact boundary, without four thousand subprocesses."""

    def linear(self, length: int) -> dict[str, tuple[str, ...]]:
        nodes = [oid_of(n) for n in range(length)]
        parents = {node: (nodes[index + 1],) for index, node in enumerate(nodes[:-1])}
        parents[nodes[-1]] = ()
        return parents

    def test_the_constant_is_exactly_four_thousand_and_ninety_six(self) -> None:
        self.assertEqual(ancestry.P3_RAW_ANCESTRY_STEP_BUDGET, 4096)

    def test_the_four_thousand_and_ninety_sixth_request_is_allowed(self) -> None:
        parents = self.linear(4096)
        target = oid_of(4095)
        fake = FakeHermetic(parents)
        with fake_reader(fake):
            found = ancestry.raw_descends_from(None, oid_of(0), target)
        self.assertIs(found, True)
        self.assertEqual(len(fake.reads), 4096)

    def test_a_four_thousand_and_ninety_seventh_request_never_happens(self) -> None:
        parents = self.linear(4200)
        target = oid_of(4096)
        fake = FakeHermetic(parents)
        with fake_reader(fake):
            found = ancestry.raw_descends_from(None, oid_of(0), target)
        self.assertIs(found, UNKNOWN)
        self.assertEqual(len(fake.reads), 4096)
        self.assertNotIn(target, fake.reads)


# --------------------------------------------------------------------------- raw_range


class RawRangeTests(unittest.TestCase):
    """The single-parent lineage shape, and nothing wider."""

    def test_base_equal_to_head_is_the_known_empty_range(self) -> None:
        found = ancestry.raw_range(None, OID, OID)
        self.assertEqual(found, ())
        self.assertIsNot(found, UNKNOWN)

    def test_a_linear_chain_walks_head_first_and_excludes_base(self) -> None:
        base, c1, c2, head = oid_of(0), oid_of(1), oid_of(2), oid_of(3)
        fake = FakeHermetic({head: (c2,), c2: (c1,), c1: (base,), base: ()})
        with fake_reader(fake):
            found = ancestry.raw_range(None, base, head)
        self.assertEqual(found, (head, c2, c1))

    def test_a_merge_is_non_linear_and_no_branch_is_chosen(self) -> None:
        base, left, right, head = oid_of(0), oid_of(1), oid_of(2), oid_of(3)
        fake = FakeHermetic({head: (left, right), left: (base,), right: (base,), base: ()})
        with fake_reader(fake):
            found = ancestry.raw_range(None, base, head)
        self.assertIs(found, NON_LINEAR)
        self.assertNotIn(left, fake.reads)
        self.assertNotIn(right, fake.reads)

    def test_non_linear_is_distinguishable_from_unknown_and_from_a_range(self) -> None:
        self.assertIsNot(NON_LINEAR, UNKNOWN)
        self.assertNotEqual(NON_LINEAR, ())
        self.assertNotEqual(NON_LINEAR, UNKNOWN)

    def test_a_root_reached_before_base_is_unknown(self) -> None:
        """A state L-1 has already excluded, so it is a contradiction, not a shorter range."""
        base, c1, head = oid_of(0), oid_of(1), oid_of(2)
        fake = FakeHermetic({head: (c1,), c1: ()})
        with fake_reader(fake):
            self.assertIs(ancestry.raw_range(None, base, head), UNKNOWN)

    def test_an_unreadable_object_is_unknown(self) -> None:
        base, head = oid_of(0), oid_of(2)
        fake = FakeHermetic({head: (oid_of(9),)})
        with fake_reader(fake):
            self.assertIs(ancestry.raw_range(None, base, head), UNKNOWN)

    def test_invalid_input_is_unknown(self) -> None:
        for base, head in ((OID, "HEAD"), ("main", OID), (OID[:12], OID)):
            with self.subTest(base=base, head=head):
                self.assertIs(ancestry.raw_range(None, base, head), UNKNOWN)

    def test_the_budget_applies_to_the_range_walk(self) -> None:
        nodes = [oid_of(n) for n in range(4200)]
        parents = {node: (nodes[index + 1],) for index, node in enumerate(nodes[:-1])}
        parents[nodes[-1]] = ()
        fake = FakeHermetic(parents)
        with fake_reader(fake):
            found = ancestry.raw_range(None, oid_of(4150), oid_of(0))
        self.assertIs(found, UNKNOWN)
        self.assertEqual(len(fake.reads), 4096)


class RawRangeRealTests(RealRepositoryCase):
    """The same shape against real objects."""

    def test_a_real_chain(self) -> None:
        made = self.chain(4)
        found = ancestry.raw_range(self.hermetic, made[0], made[3])
        self.assertEqual(found, (made[3], made[2], made[1]))

    def test_a_real_merge_is_non_linear(self) -> None:
        base = self.commit("base")
        left = self.commit("l", (base,))
        right = self.commit("r", (base,))
        merge = self.commit("m", (left, right))
        self.assertIs(ancestry.raw_range(self.hermetic, base, merge), NON_LINEAR)


# --------------------------------------------------------------------------- boundary


class UnitBoundaryTests(unittest.TestCase):
    """Unit 2 is a reader. It delegates to no revision walker and starts no later unit."""

    def test_the_revision_view_helpers_still_exist(self) -> None:
        """They remain for their existing non-proof callers; Unit 2 simply does not use them."""
        self.assertTrue(hasattr(gitcmd, "commit_parents"))
        self.assertTrue(hasattr(gitcmd, "descends_from"))

    def test_later_unit_machinery_is_still_absent(self) -> None:
        from workline import mutation
        from workline.review import records
        from workline.review.store import ReviewStore

        self.assertFalse(hasattr(gitcmd, "P3_WORK_ATTR_PIN_GIT_MIN"))
        self.assertFalse(hasattr(mutation, "WORK_COMMIT_MODE"))
        self.assertEqual(mutation.PLANNING_COMMIT_MODE, "review-v1-planning-local-v1")
        self.assertFalse(hasattr(ancestry, "CommitTreePlan"))
        self.assertTrue(hasattr(records, "WorkTerminalActivation"))
        for writer in ("write_activation", "create_activation", "activate", "produce_activation"):
            with self.subTest(writer=writer):
                self.assertFalse(hasattr(ReviewStore, writer))

    def test_hermetic_gained_only_a_generic_byte_runner(self) -> None:
        """The class B authority learned to return bytes; it learned no ancestry."""
        self.assertTrue(hasattr(hermetic.HermeticGit, "run_bytes"))
        for name in ("raw_parents", "raw_descends_from", "raw_range", "P3_RAW_ANCESTRY_STEP_BUDGET"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(hermetic.HermeticGit, name))
                self.assertFalse(hasattr(hermetic, name))


if __name__ == "__main__":
    unittest.main()
