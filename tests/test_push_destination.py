"""D-1: push destination identity.

Workline guarantees which repository a Project pushes to. These tests hold the
guarantee to its boundary: the destination is approved by a human, verified
from Git's own resolution before any network contact, carried durably through a
mutation, and never followed automatically when it changes.

Nothing here verifies an authenticating account — that is explicitly outside
the guarantee.
"""

from __future__ import annotations

from pathlib import Path

from helpers import WorklineTestCase, completing_executor, git

from workline import bootstrap as bs
from workline import gitcmd
from workline import pushurl
from workline import roadmap as rm
from workline import start as st
from workline.create import WorkSpec, create_standalone_work
from workline.destination import ensure_push_destination, resolve_active_push_locator
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import Effect, MutationController, WriteScope
from workline.project_start import project_start
from workline.push_pin import pin_push_destination
from workline.state import ProjectView
from workline.store import BOOTSTRAP_REL_PATH, PROJECT_YAML_REL, ProjectStore, PushPin
from workline.validate import validate_project

WORKLINE_ROOT = Path(__file__).resolve().parents[1]

SECRET_URL = "https://carol:ghp_supersecrettoken@example.invalid/org/repo.git"
TOKEN = "ghp_supersecrettoken"


class LocatorInspectionTests(WorklineTestCase):
    """Locators are inspected for credentials only; identity is never inferred."""

    def test_no_identity_normalization_is_offered(self) -> None:
        """The footgun is absent, not merely unused."""
        for removed in ("normalize", "accept", "canonical"):
            self.assertFalse(hasattr(pushurl, removed), removed)

    def test_secret_detection(self) -> None:
        self.assertTrue(pushurl.is_secret_bearing(SECRET_URL))
        self.assertTrue(pushurl.is_secret_bearing("https://user@example.invalid/o/r.git"))
        self.assertFalse(pushurl.is_secret_bearing("git@github.com:o/r.git"))
        self.assertFalse(pushurl.is_secret_bearing("https://github.com/o/r.git"))
        self.assertFalse(pushurl.is_secret_bearing(r"C:\repos\bare.git"))

    def test_redaction_masks_only_the_credential(self) -> None:
        self.assertNotIn(TOKEN, pushurl.redact(SECRET_URL))
        self.assertEqual(pushurl.redact(SECRET_URL), "https://***@example.invalid/org/repo.git")
        # everything else comes back untouched, the .git suffix included
        for plain in ("https://github.com/o/r.git", "git@github.com:o/r.git", r"C:\repos\bare.git"):
            self.assertEqual(pushurl.redact(plain), plain)

    def test_a_credential_bearing_locator_stops(self) -> None:
        with self.assertRaises(StopError) as ctx:
            pushurl.ensure_no_secret(SECRET_URL, "test")
        self.assertEqual(ctx.exception.code, "push_destination_secret")
        self.assertNotIn(TOKEN, str(ctx.exception))


class DestinationBase(WorklineTestCase):
    def bare(self, name: str) -> Path:
        path = self.tmp / f"{name}.git"
        git(self.tmp, "init", "--bare", "-b", "main", str(path))
        return path

    def head_of(self, bare: Path) -> str | None:
        result = git(bare, "rev-parse", "--verify", "--quiet", "refs/heads/main", check=False).strip()
        return result or None

    def bare_at(self, path: Path) -> Path:
        """A bare repository at exactly ``path`` (no suffix is appended)."""
        git(self.tmp, "init", "--bare", "-b", "main", str(path))
        return path

    def seed(self, bare: Path, text: str) -> str | None:
        """Give ``bare`` a history of its own; return its head."""
        seed = self.tmp / f"seed-{bare.name}"
        seed.mkdir()
        git(seed, "init", "-b", "main")
        (seed / "seed.txt").write_text(text, encoding="utf-8")
        git(seed, "add", "seed.txt")
        git(seed, "commit", "-m", f"seed {text}")
        git(seed, "push", str(bare), "main:main")
        return self.head_of(bare)

    def push_effects(self, store: ProjectStore) -> list[dict]:
        effects: list[dict] = []
        for record in MutationController(store).list_pending():
            effects += [e for e in record["effects"] if e["kind"] == "git_push"]
        return effects


class EntryCheckTests(DestinationBase):
    """1, 2, 3, 12, 13: what an operation checks before it does anything."""

    def test_pinned_destination_lets_every_push_owner_push(self) -> None:
        store = self.new_project(remote=True)
        bare = self.remote_path()

        roadmap = self.simple_roadmap(store)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(bare))
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(bare))
        st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(bare))
        create_standalone_work(store, WorkSpec("Standalone", "done"))
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(bare))
        self.assertEqual(validate_project(store), [])

    def test_bootstrap_backfill_pushes_to_the_pinned_destination(self) -> None:
        store = self.new_project(remote=True)
        git(store.root, "rm", "-q", "--cached", BOOTSTRAP_REL_PATH)
        (store.root / BOOTSTRAP_REL_PATH).unlink()
        git(store.root, "commit", "-m", "legacy project without bootstrap")
        git(store.root, "push", "-u", "origin", "main")

        result = bs.backfill_bootstrap(store.root)
        self.assertTrue(result.pushed)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(self.remote_path()))

    def test_remote_without_a_pin_stops_before_anything_happens(self) -> None:
        store = self.new_project(remote=True, pin=False)
        # A destination that could not be contacted even if we tried: the STOP
        # is a configuration decision, not a failed network call.
        git(store.root, "remote", "set-url", "origin", str(self.tmp / "nowhere.git"))
        head_before = git(store.root, "rev-parse", "HEAD").strip()

        records_before = sorted(p.name for p in store.mutations.glob("*.yaml"))
        with self.assertRaises(StopError) as ctx:
            create_standalone_work(store, WorkSpec("Blocked", "never registered"))
        self.assertEqual(ctx.exception.code, "push_destination_unpinned")
        records_after = sorted(p.name for p in store.mutations.glob("*.yaml"))

        self.assertEqual(list(store.entity_dir("work").glob("*.md")), [])
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(records_after, records_before)  # no new recovery record at all
        self.assertEqual(store.read_events(), [])
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), head_before)
        # nothing was fetched: no remote-tracking state was created either
        self.assertEqual(git(store.root, "for-each-ref", "refs/remotes").strip(), "")

    def test_every_push_owner_stops_when_unpinned(self) -> None:
        store = self.new_project(remote=True, pin=False)
        # backfill only reaches its Git stage when it has something to add
        git(store.root, "rm", "-q", "--cached", BOOTSTRAP_REL_PATH)
        (store.root / BOOTSTRAP_REL_PATH).unlink()
        git(store.root, "commit", "-m", "legacy project without bootstrap")
        for call in (
            lambda: self.simple_roadmap(store),
            lambda: create_standalone_work(store, WorkSpec("X", "x")),
            lambda: bs.backfill_bootstrap(store.root),
        ):
            with self.assertRaises(StopError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, "push_destination_unpinned")

    def test_start_owned_operations_check_the_destination_too(self) -> None:
        store = self.new_project(remote=True)
        work = create_standalone_work(store, WorkSpec("Excludable", "planned")).work_id
        git(store.root, "remote", "set-url", "origin", str(self.bare("elsewhere")))

        for call in (
            lambda: st.start(store, work, "single-work", completing_executor(store)),
            lambda: st.plan_exclude_standalone_work(store, work),
        ):
            with self.assertRaises(StopError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, "push_destination_mismatch")
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(ProjectView.load(store).work_state(work).state, "unstarted")

    def test_remote_less_project_is_unaffected(self) -> None:
        store = self.new_project()
        self.assertIsNone(ensure_push_destination(store))
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        result = st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        self.assertEqual(result.status, "completed")
        self.assertEqual(validate_project(store), [])
        self.assertIsNone(store.read_push_pin())

    def test_a_non_origin_remote_name_is_pinned_and_pushed(self) -> None:
        root = self.new_dir("upstream-proj")
        bare = self.bare("upstream-remote")
        git(root, "init", "-b", "main")
        git(root, "remote", "add", "upstream", str(bare))
        project_start(root, WORKLINE_ROOT, expected_push_url=str(bare), push_remote="upstream")
        store = ProjectStore(root)
        self.assertEqual(store.read_push_pin(), PushPin("upstream", (str(bare),)))

        create_standalone_work(store, WorkSpec("Upstream", "done"))
        self.assertEqual(git(root, "rev-parse", "HEAD").strip(), self.head_of(bare))

    def test_missing_pinned_remote_stops(self) -> None:
        store = self.new_project(remote=True)
        git(store.root, "remote", "remove", "origin")
        with self.assertRaises(StopError) as ctx:
            create_standalone_work(store, WorkSpec("X", "x"))
        self.assertEqual(ctx.exception.code, "push_destination_remote_missing")

    def test_multiple_active_push_urls_stop(self) -> None:
        store = self.new_project(remote=True)
        git(store.root, "remote", "set-url", "--push", "--add", "origin", str(self.remote_path()))
        git(store.root, "remote", "set-url", "--push", "--add", "origin", str(self.bare("mirror")))
        with self.assertRaises(StopError) as ctx:
            create_standalone_work(store, WorkSpec("X", "x"))
        self.assertEqual(ctx.exception.code, "push_destination_multiple")


class ResolutionTests(DestinationBase):
    """6, 7, 14, 15: the destination Git actually writes to is the only evidence."""

    def _diverged_fetch_remote(self, name: str) -> Path:
        """A bare repo whose main is unrelated to the Project's history."""
        bare = self.bare(name)
        seed = self.new_dir(f"{name}-seed")
        git(seed, "init", "-b", "main")
        (seed / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
        git(seed, "add", "unrelated.txt")
        git(seed, "commit", "-m", "unrelated history")
        git(seed, "push", str(bare), "main:main")
        return bare

    def _split_project(self) -> tuple[ProjectStore, Path, Path]:
        """fetch URL A (divergent history) / push URL B (the real destination)."""
        fetch_remote = self._diverged_fetch_remote("fetch-side")
        push_remote = self.bare("push-side")
        root = self.new_dir("split")
        git(root, "init", "-b", "main")
        git(root, "remote", "add", "origin", str(fetch_remote))
        git(root, "remote", "set-url", "--push", "origin", str(push_remote))
        project_start(root, WORKLINE_ROOT, expected_push_url=str(push_remote))
        return ProjectStore(root), fetch_remote, push_remote

    def test_pushurl_decides_the_destination_and_the_evidence(self) -> None:
        store, fetch_remote, push_remote = self._split_project()
        fetch_head_before = self.head_of(fetch_remote)

        create_standalone_work(store, WorkSpec("Split", "done"))

        local = git(store.root, "rev-parse", "HEAD").strip()
        self.assertEqual(self.head_of(push_remote), local)
        # the fetch side never received anything and never decided anything:
        # its divergent history would have been read as a mismatch
        self.assertEqual(self.head_of(fetch_remote), fetch_head_before)
        self.assertEqual(store.read_push_pin(), PushPin("origin", (str(push_remote),)))
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_pin_against_the_fetch_url_stops_when_pushurl_differs(self) -> None:
        store, fetch_remote, _push_remote = self._split_project()
        with self.assertRaises(StopError) as ctx:
            pin_push_destination(store.root, [str(fetch_remote)])
        self.assertEqual(ctx.exception.code, "push_destination_mismatch")

    def test_push_insteadof_rewriting_is_the_resolved_destination(self) -> None:
        configured = self.bare("configured")
        rewritten = self.bare("rewritten")
        root = self.new_dir("rewrite")
        git(root, "init", "-b", "main")
        git(root, "remote", "add", "origin", str(configured))
        git(root, "config", f"url.{rewritten}.pushInsteadOf", str(configured))

        # Git reports the rewritten destination, so that is what may be pinned.
        self.assertEqual(
            resolve_active_push_locator(root, "origin"), str(rewritten)
        )
        with self.assertRaises(StopError) as ctx:
            project_start(root, WORKLINE_ROOT, expected_push_url=str(configured))
        self.assertEqual(ctx.exception.code, "push_destination_mismatch")

        project_start(root, WORKLINE_ROOT, expected_push_url=str(rewritten))
        store = ProjectStore(root)
        create_standalone_work(store, WorkSpec("Rewritten", "done"))
        self.assertEqual(git(root, "rev-parse", "HEAD").strip(), self.head_of(rewritten))
        self.assertIsNone(self.head_of(configured))

    def test_a_stale_remote_tracking_ref_is_not_evidence(self) -> None:
        store = self.new_project(remote=True)
        bare = self.remote_path()
        create_standalone_work(store, WorkSpec("First", "done"))
        local = git(store.root, "rev-parse", "HEAD").strip()
        self.assertEqual(self.head_of(bare), local)

        # The destination loses the branch; the remote-tracking ref still says
        # it holds exactly our HEAD. Believing it would report a push that
        # never happened.
        git(bare, "update-ref", "-d", "refs/heads/main")
        git(store.root, "update-ref", "refs/remotes/origin/main", local)
        self.assertIsNone(self.head_of(bare))

        create_standalone_work(store, WorkSpec("Second", "done"))
        self.assertEqual(self.head_of(bare), git(store.root, "rev-parse", "HEAD").strip())


class DurablePushEffectTests(DestinationBase):
    """4, 5: the recorded destination survives, and is re-checked, on resume."""

    def _stall_push(self, store: ProjectStore, spec: WorkSpec) -> Path:
        """Record a mutation whose push failed, without changing the destination."""
        away = self.tmp / "proj-remote-away.git"
        self.remote_path().rename(away)
        with self.assertRaises(StopError):
            create_standalone_work(store, spec)
        return away

    def test_resume_keeps_the_recorded_destination(self) -> None:
        store = self.new_project(remote=True)
        spec = WorkSpec("Retry", "done")
        away = self._stall_push(store, spec)

        recorded = self.push_effects(store)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["payload"]["locator"], self.remote_url())
        self.assertEqual(recorded[0]["payload"]["remote"], "origin")
        pending = MutationController(store).list_pending()

        away.rename(self.remote_path())
        result = create_standalone_work(store, spec)
        self.assertTrue(result.resumed)
        self.assertEqual(result.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(len(list(store.entity_dir("work").glob("*.md"))), 1)
        self.assertEqual(git(store.root, "log", "--format=%s").count("create W-01"), 1)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(self.remote_path()))

    def test_a_changed_destination_stops_the_resume_before_the_network(self) -> None:
        """The pin approves A and B; the mutation was recorded for A only."""
        store = self.new_project(remote=True)
        other = self.bare("second-destination")
        pin_push_destination(store.root, [str(self.remote_path()), str(other)])
        spec = WorkSpec("Drift", "done")
        away = self._stall_push(store, spec)

        recorded = self.push_effects(store)
        self.assertEqual(recorded[0]["payload"]["locator"], self.remote_url())

        # The remote now points at the other approved destination: the entry
        # check passes, and the recorded effect is what refuses.
        git(store.root, "remote", "set-url", "origin", str(other))
        with self.assertRaises(ReconcileRequired) as ctx:
            create_standalone_work(store, spec)
        self.assertEqual(ctx.exception.code, "reconcile_required")
        self.assertIn("push destination changed", str(ctx.exception))
        self.assertIsNone(self.head_of(other))  # nothing was sent anywhere new
        away.rename(self.remote_path())


class CloneTests(DestinationBase):
    """10, 11: the approval travels with the repository."""

    def test_a_fresh_clone_keeps_the_pin_and_pushes(self) -> None:
        store = self.new_project(remote=True)
        create_standalone_work(store, WorkSpec("Seed", "done"))
        clone = self.tmp / "clone"
        git(self.tmp, "clone", "-q", str(self.remote_path()), str(clone))

        cloned = ProjectStore(clone)
        self.assertEqual(cloned.read_push_pin(), store.read_push_pin())
        create_standalone_work(cloned, WorkSpec("FromClone", "done"))
        self.assertEqual(git(clone, "rev-parse", "HEAD").strip(), self.head_of(self.remote_path()))

    def test_a_clone_of_a_copy_stops(self) -> None:
        store = self.new_project(remote=True)
        create_standalone_work(store, WorkSpec("Seed", "done"))
        copy = self.tmp / "copy.git"
        git(self.tmp, "clone", "-q", "--bare", str(self.remote_path()), str(copy))
        clone = self.tmp / "fork-clone"
        git(self.tmp, "clone", "-q", str(copy), str(clone))

        head_before = self.head_of(copy)
        with self.assertRaises(StopError) as ctx:
            create_standalone_work(ProjectStore(clone), WorkSpec("Fork", "done"))
        self.assertEqual(ctx.exception.code, "push_destination_mismatch")
        self.assertEqual(self.head_of(copy), head_before)


class OwnerGuardTests(DestinationBase):
    """16, 17, 18: who may write ``git.push``."""

    def test_project_start_may_create_the_pin(self) -> None:
        store = self.new_project(remote=True)
        self.assertEqual(store.read_push_pin(), PushPin("origin", (self.remote_url(),)))
        self.assertIn(PROJECT_YAML_REL, git(store.root, "ls-files"))
        self.assertEqual(validate_project(store), [])
        self.assertEqual(git(store.root, "log", "--format=%s").strip(), "chore(workline): initialize project")

    def test_project_start_stops_when_the_remote_is_not_the_expected_one(self) -> None:
        root = self.new_dir("mismatch")
        bare = self.bare("actual")
        git(root, "init", "-b", "main")
        git(root, "remote", "add", "origin", str(bare))
        with self.assertRaises(StopError) as ctx:
            project_start(root, WORKLINE_ROOT, expected_push_url=str(self.bare("expected")))
        self.assertEqual(ctx.exception.code, "push_destination_mismatch")
        self.assertFalse((root / ".workline").exists())

    def test_project_start_reports_an_unpinned_remote(self) -> None:
        root = self.new_dir("unpinned")
        bare = self.bare("unpinned-remote")
        git(root, "init", "-b", "main")
        git(root, "remote", "add", "origin", str(bare))
        result = project_start(root, WORKLINE_ROOT)
        self.assertEqual(result.status, "initialized")
        self.assertIsNone(result.pinned_url)
        self.assertEqual(result.unpinned_remotes, ("origin",))
        self.assertIsNone(ProjectStore(root).read_push_pin())

    def test_a_domain_owner_cannot_change_the_pin(self) -> None:
        store = self.new_project(remote=True)
        other = str(self.bare("elsewhere"))
        controller = MutationController(store)
        content = store.project_yaml_with_pin(PushPin("origin", (other,)))
        for owner in ("roadmap", "start", "create-direct", "bootstrap-backfill"):
            mutation = controller.open(owner, {"operation": f"{owner}-guard-probe"}, WriteScope(files=(PROJECT_YAML_REL,)))
            with self.assertRaises(ValidationError) as ctx:
                mutation.add_effects("pin", [Effect.write_file(PROJECT_YAML_REL, content)])
            self.assertEqual(ctx.exception.code, "push_pin_owner")
            mutation.abandon()
        self.assertEqual(store.read_push_pin(), PushPin("origin", (self.remote_url(),)))

    def test_a_domain_owner_may_rewrite_project_yaml_without_touching_the_pin(self) -> None:
        store = self.new_project(remote=True)
        unchanged = store.project_yaml_with_pin(store.read_push_pin())
        mutation = MutationController(store).open("roadmap", {"operation": "unchanged-probe"}, WriteScope(files=(PROJECT_YAML_REL,)))
        mutation.add_effects("same", [Effect.write_file(PROJECT_YAML_REL, unchanged)])
        mutation.apply()
        mutation.complete()
        self.assertEqual(store.read_push_pin(), PushPin("origin", (self.remote_url(),)))


class PinMaintenanceTests(DestinationBase):
    """18, 19, 20, 21: the only path that changes an approved destination."""

    def test_first_pin_of_an_existing_project(self) -> None:
        store = self.new_project(remote=True, pin=False)
        self.assertIsNone(store.read_push_pin())

        result = pin_push_destination(store.root, [str(self.remote_path())])
        self.assertEqual(result.status, "pinned")
        self.assertTrue(result.pushed)
        self.assertEqual(store.read_push_pin(), PushPin("origin", (self.remote_url(),)))
        self.assertEqual(git(store.root, "log", "-1", "--format=%s").strip(), "chore(workline): pin push destination")
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(self.remote_path()))
        # domain state untouched
        self.assertEqual(store.read_events(), [])
        self.assertEqual(store.read_roadmap_relations(), [])
        self.assertEqual(list(store.entity_dir("work").glob("*.md")), [])
        self.assertEqual(validate_project(store), [])
        create_standalone_work(store, WorkSpec("AfterPin", "done"))

    def test_pin_is_idempotent(self) -> None:
        store = self.new_project(remote=True)
        head_before = git(store.root, "rev-parse", "HEAD").strip()
        result = pin_push_destination(store.root, [str(self.remote_path())])
        self.assertEqual(result.status, "already_pinned")
        self.assertIsNone(result.mutation_id)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), head_before)

    def test_the_pin_never_follows_the_current_remote(self) -> None:
        store = self.new_project(remote=True)
        moved = self.bare("moved")
        git(store.root, "remote", "set-url", "origin", str(moved))
        # asking to keep the old approval while the remote already moved
        with self.assertRaises(StopError) as ctx:
            pin_push_destination(store.root, [str(self.remote_path())])
        self.assertEqual(ctx.exception.code, "push_destination_mismatch")
        self.assertEqual(store.read_push_pin(), PushPin("origin", (self.remote_url(),)))

    def test_pin_maintenance_stops_while_another_mutation_is_pending(self) -> None:
        store = self.new_project(remote=True)
        away = self.tmp / "proj-remote-away.git"
        self.remote_path().rename(away)
        with self.assertRaises(StopError):
            create_standalone_work(store, WorkSpec("Pending", "done"))
        away.rename(self.remote_path())
        self.assertEqual(len(MutationController(store).list_pending()), 1)

        other = self.bare("other")
        git(store.root, "remote", "set-url", "origin", str(other))
        with self.assertRaises(StopError) as ctx:
            pin_push_destination(store.root, [str(other)])
        self.assertEqual(ctx.exception.code, "pending_operation")
        self.assertEqual(store.read_push_pin(), PushPin("origin", (self.remote_url(),)))

    def test_pin_maintenance_resumes_its_own_mutation(self) -> None:
        store = self.new_project(remote=True, pin=False)
        away = self.tmp / "proj-remote-away.git"
        self.remote_path().rename(away)
        with self.assertRaises(StopError):
            pin_push_destination(store.root, [str(self.remote_path())])
        pending = MutationController(store).list_pending()
        self.assertEqual([p["owner"] for p in pending], ["push-destination-pin"])
        self.assertEqual(store.read_push_pin(), PushPin("origin", (self.remote_url(),)))

        away.rename(self.remote_path())
        result = pin_push_destination(store.root, [str(self.remote_path())])
        self.assertTrue(result.resumed)
        self.assertEqual(result.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(git(store.root, "log", "--format=%s").count("pin push destination"), 1)
        self.assertEqual(store.read_push_pin(), PushPin("origin", (self.remote_url(),)))
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(self.remote_path()))

    def test_legitimate_destination_change(self) -> None:
        store = self.new_project(remote=True)
        old = self.remote_path()
        new = self.bare("new-destination")
        create_standalone_work(store, WorkSpec("BeforeMove", "done"))
        old_head = self.head_of(old)

        # 1. the human moves the Git remote
        git(store.root, "remote", "set-url", "origin", str(new))
        # 2. ordinary operations STOP — fail-closed until the approval moves too
        with self.assertRaises(StopError) as ctx:
            create_standalone_work(store, WorkSpec("Blocked", "done"))
        self.assertEqual(ctx.exception.code, "push_destination_mismatch")
        self.assertIsNone(self.head_of(new))

        # 3. the human approves the new destination explicitly
        result = pin_push_destination(store.root, [str(new)])
        self.assertEqual(result.status, "pinned")
        self.assertEqual(store.read_push_pin(), PushPin("origin", (str(new),)))

        # 4. ordinary operations resume, against the new destination only
        create_standalone_work(store, WorkSpec("AfterMove", "done"))
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), self.head_of(new))
        self.assertEqual(self.head_of(old), old_head)
        self.assertEqual(validate_project(store), [])


class SecretTests(DestinationBase):
    """9: a credential-bearing URL is refused before anything durable exists."""

    def _no_token_on_disk(self, store: ProjectStore) -> None:
        self.assertNotIn(TOKEN, store.project_yaml.read_text(encoding="utf-8"))
        for path in store.root.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                self.assertNotIn(TOKEN, path.read_text(encoding="utf-8", errors="replace"), path)

    def test_pin_maintenance_refuses_a_credential_bearing_url(self) -> None:
        store = self.new_project(remote=True, pin=False)
        with self.assertRaises(StopError) as ctx:
            pin_push_destination(store.root, [SECRET_URL])
        self.assertEqual(ctx.exception.code, "push_destination_secret")
        self.assertNotIn(TOKEN, str(ctx.exception))
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertIsNone(store.read_push_pin())
        self._no_token_on_disk(store)

    def test_project_start_refuses_a_credential_bearing_url(self) -> None:
        root = self.new_dir("secret-start")
        bare = self.bare("secret-remote")
        git(root, "init", "-b", "main")
        git(root, "remote", "add", "origin", str(bare))
        with self.assertRaises(StopError) as ctx:
            project_start(root, WORKLINE_ROOT, expected_push_url=SECRET_URL)
        self.assertEqual(ctx.exception.code, "push_destination_secret")
        self.assertNotIn(TOKEN, str(ctx.exception))
        self.assertFalse((root / ".workline").exists())

    def test_a_credential_bearing_remote_stops_the_operation(self) -> None:
        store = self.new_project(remote=True)
        git(store.root, "remote", "set-url", "origin", SECRET_URL)
        with self.assertRaises(StopError) as ctx:
            create_standalone_work(store, WorkSpec("Secret", "done"))
        self.assertEqual(ctx.exception.code, "push_destination_secret")
        self.assertNotIn(TOKEN, str(ctx.exception))
        self.assertEqual(MutationController(store).list_pending(), [])
        self._no_token_on_disk(store)


class GuaranteeBoundaryTests(DestinationBase):
    """The boundary itself: destination identity, never account identity."""

    def test_no_account_verification_exists(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "workline").rglob("*.py")
        text = "\n".join(path.read_text(encoding="utf-8") for path in source)
        for provider_specific in ("gh auth", "credential fill", "ssh -T"):
            self.assertNotIn(provider_specific, text)

    def test_a_verified_destination_says_nothing_about_the_account(self) -> None:
        store = self.new_project(remote=True)
        destination = ensure_push_destination(store)
        self.assertEqual(destination.locator, self.remote_url())
        self.assertFalse(hasattr(destination, "account"))


class LocatorIdentityTests(DestinationBase):
    """A destination is the exact locator Git resolves, not a tidied form of it.

    ``<path>/target`` and ``<path>/target.git`` are two different repositories
    here, as they may be on any server. Workline must never decide they are the
    same one, and must never contact one while intending to push to the other.
    """

    def _pair(self) -> tuple[Path, Path]:
        plain = self.bare_at(self.tmp / "target")
        dotgit = self.bare_at(self.tmp / "target.git")
        self.seed(plain, "a different repository")  # must never be consulted
        return plain, dotgit

    def _pinned_to(self, locator: str, name: str = "locator-proj") -> ProjectStore:
        root = self.new_dir(name)
        git(root, "init", "-b", "main")
        git(root, "remote", "add", "origin", locator)
        project_start(root, WORKLINE_ROOT, expected_push_url=locator)
        return ProjectStore(root)

    def test_target_and_target_dot_git_stay_distinct(self) -> None:
        plain, dotgit = self._pair()
        plain_head = self.head_of(plain)
        store = self._pinned_to(str(dotgit))
        self.assertEqual(store.read_push_pin(), PushPin("origin", (str(dotgit),)))

        create_standalone_work(store, WorkSpec("Exact", "done"))

        local = git(store.root, "rev-parse", "HEAD").strip()
        self.assertEqual(self.head_of(dotgit), local)  # ls-remote / ancestry / push
        self.assertEqual(self.head_of(plain), plain_head)  # never touched
        recorded = [
            e["payload"]
            for e in MutationController(store).list_pending()
            for e in e["effects"]
            if e["kind"] == "git_push"
        ]
        self.assertEqual(recorded, [])
        self.assertEqual(validate_project(store), [])

    def test_drift_from_dot_git_to_plain_stops(self) -> None:
        plain, dotgit = self._pair()
        store = self._pinned_to(str(dotgit))
        create_standalone_work(store, WorkSpec("Before", "done"))
        plain_head = self.head_of(plain)

        git(store.root, "remote", "set-url", "origin", str(plain))
        with self.assertRaises(StopError) as ctx:
            create_standalone_work(store, WorkSpec("After", "done"))
        self.assertEqual(ctx.exception.code, "push_destination_mismatch")
        self.assertEqual(self.head_of(plain), plain_head)
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_resume_does_not_follow_an_equivalent_looking_locator(self) -> None:
        plain, dotgit = self._pair()
        store = self._pinned_to(str(dotgit))
        # a human approves both repositories, so the entry check passes either
        # way and only the recorded locator can refuse
        pin_push_destination(store.root, [str(dotgit), str(plain)])
        plain_head = self.head_of(plain)

        away = self.tmp / "target-away.git"
        dotgit.rename(away)
        spec = WorkSpec("Drift", "done")
        with self.assertRaises(StopError):
            create_standalone_work(store, spec)
        recorded = self.push_effects(store)
        self.assertEqual([e["payload"]["locator"] for e in recorded], [str(dotgit)])
        away.rename(dotgit)  # reachable again: the STOP must be about identity

        git(store.root, "remote", "set-url", "origin", str(plain))
        with self.assertRaises(ReconcileRequired):
            create_standalone_work(store, spec)
        self.assertEqual(self.head_of(plain), plain_head)

    def test_a_trailing_slash_is_not_assumed_equivalent(self) -> None:
        """A false negative is the accepted price of never guessing identity."""
        store = self.new_project(remote=True)
        git(store.root, "remote", "set-url", "origin", str(self.remote_path()) + "/")
        with self.assertRaises(StopError) as ctx:
            create_standalone_work(store, WorkSpec("Slash", "done"))
        self.assertEqual(ctx.exception.code, "push_destination_mismatch")


class ChainedRewriteTests(DestinationBase):
    """Push evidence must travel the push path, not a locator handed back to Git.

    ``remote.origin.url = A`` with ``url.B.pushInsteadOf = A`` sends the push to
    B — but B handed to another Git command is rewritten again by
    ``url.C.insteadOf = B``. Verification by locator would therefore inspect C
    while the push writes to B.
    """

    def _chain(self) -> tuple[ProjectStore, Path, Path, Path]:
        configured = self.bare_at(self.tmp / "A.git")  # what the config shows
        destination = self.bare_at(self.tmp / "B.git")  # where pushes land
        decoy = self.bare_at(self.tmp / "C.git")  # what a locator read would hit
        self.seed(decoy, "a third repository")
        root = self.new_dir("chain")
        git(root, "init", "-b", "main")
        git(root, "remote", "add", "origin", str(configured))
        git(root, "config", f"url.{destination}.pushInsteadOf", str(configured))
        git(root, "config", f"url.{decoy}.insteadOf", str(destination))
        project_start(root, WORKLINE_ROOT, expected_push_url=str(destination))
        return ProjectStore(root), configured, destination, decoy

    def _classification(self, store: ProjectStore, locator: str) -> str:
        record = {
            "kind": "git_push",
            "payload": {"remote": "origin", "branch": "main", "locator": locator},
        }
        return MutationController(store).classify(record)

    def test_no_direct_locator_command_remains(self) -> None:
        """The locator is never handed back to Git as an argument."""
        for removed in ("ls_remote_head", "fetch_locator", "has_commit", "is_ancestor"):
            self.assertFalse(hasattr(gitcmd, removed), removed)

    def test_the_push_and_its_evidence_reach_the_same_repository(self) -> None:
        store, configured, destination, decoy = self._chain()
        decoy_head = self.head_of(decoy)
        self.assertEqual(resolve_active_push_locator(store.root, "origin"), str(destination))
        # a locator handed back to Git would land on the decoy instead
        self.assertEqual(
            git(store.root, "ls-remote", "--heads", "--", str(destination), "refs/heads/main").split()[0],
            decoy_head,
        )

        preview = gitcmd.push_dry_run(store.root, "origin", "main")
        self.assertEqual(preview.destination, str(destination))

        create_standalone_work(store, WorkSpec("Chained", "done"))

        local = git(store.root, "rev-parse", "HEAD").strip()
        self.assertEqual(self.head_of(destination), local)
        self.assertEqual(self.head_of(decoy), decoy_head)  # never written to
        self.assertIsNone(self.head_of(configured))
        self.assertEqual(validate_project(store), [])

    def test_a_diverged_third_repository_does_not_decide_anything(self) -> None:
        store, _configured, destination, decoy = self._chain()
        create_standalone_work(store, WorkSpec("Chained", "done"))
        local = git(store.root, "rev-parse", "HEAD").strip()

        # destination up to date, decoy diverged -> up to date
        self.assertNotEqual(self.head_of(decoy), local)
        self.assertEqual(self._classification(store, str(destination)), "applied_matching")

        # destination behind, decoy exactly at HEAD -> still an unapplied push
        git(store.root, "push", "-q", "-f", str(decoy), "main:main")
        self.assertEqual(self.head_of(decoy), local)
        first = git(store.root, "rev-list", "--max-parents=0", "HEAD").strip().splitlines()[0]
        git(destination, "update-ref", "refs/heads/main", first)
        self.assertEqual(self._classification(store, str(destination)), "unapplied")

        # destination diverged -> reconcile required, whatever the decoy holds
        seed = self.new_dir("diverge")
        git(seed, "init", "-b", "main")
        (seed / "d.txt").write_text("diverged\n", encoding="utf-8")
        git(seed, "add", "d.txt")
        git(seed, "commit", "-m", "diverged")
        git(seed, "push", "-q", "-f", str(destination), "main:main")
        with self.assertRaises(ReconcileRequired):
            self._classification(store, str(destination))

    def test_a_new_branch_at_the_destination_is_unapplied(self) -> None:
        store, _configured, destination, _decoy = self._chain()
        self.assertIsNone(self.head_of(destination))
        self.assertEqual(self._classification(store, str(destination)), "unapplied")
