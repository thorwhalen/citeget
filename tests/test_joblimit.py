"""The per-owner concurrent-acquisition cap."""

import subprocess
import sys
import textwrap

import pytest

from citeget import joblimit
from citeget.joblimit import JobLimitExceeded, job_slot

pytestmark = pytest.mark.skipif(
    joblimit.fcntl is None, reason="the cap is not enforced without fcntl (Windows)"
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.delenv(joblimit.MAX_CONCURRENT_ENV_VAR, raising=False)
    monkeypatch.setenv(joblimit.LOCK_DIR_ENV_VAR, str(tmp_path / "locks"))


def test_the_default_cap_admits_that_many_and_refuses_the_next():
    cap = joblimit.DEFAULT_MAX_CONCURRENT_JOBS
    with pytest.MonkeyPatch.context():
        held = [job_slot("alice") for _ in range(cap)]
        slots = [h.__enter__() for h in held]
        assert sorted(slots) == list(range(cap))
        with pytest.raises(JobLimitExceeded):
            with job_slot("alice"):
                pass
        for h in held:
            h.__exit__(None, None, None)


def test_owners_do_not_share_slots():
    with job_slot("alice", max_concurrent=1):
        with job_slot("bob", max_concurrent=1) as slot:
            assert slot == 0


def test_a_slot_is_freed_when_the_block_raises():
    with pytest.raises(ZeroDivisionError):
        with job_slot("alice", max_concurrent=1):
            1 / 0
    with job_slot("alice", max_concurrent=1) as slot:
        assert slot == 0


def test_the_environment_sets_the_cap(monkeypatch):
    monkeypatch.setenv(joblimit.MAX_CONCURRENT_ENV_VAR, "1")
    with job_slot("alice"):
        with pytest.raises(JobLimitExceeded):
            with job_slot("alice"):
                pass


def test_zero_means_no_cap(monkeypatch):
    monkeypatch.setenv(joblimit.MAX_CONCURRENT_ENV_VAR, "0")
    with job_slot("alice") as a, job_slot("alice") as b:
        assert a is None and b is None


def test_a_malformed_cap_is_an_informative_error(monkeypatch):
    monkeypatch.setenv(joblimit.MAX_CONCURRENT_ENV_VAR, "two")
    with pytest.raises(ValueError, match=joblimit.MAX_CONCURRENT_ENV_VAR):
        with job_slot("alice"):
            pass


def test_a_killed_job_frees_its_slot(tmp_path):
    """Slots are kernel locks: a holder that dies without cleanup releases them."""
    lock_dir = tmp_path / "locks"
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                f"""
                import sys, time
                from citeget.joblimit import job_slot
                with job_slot("alice", max_concurrent=1, lock_dir={str(lock_dir)!r}):
                    print("held", flush=True)
                    time.sleep(60)
                """
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(JobLimitExceeded):
            with job_slot("alice", max_concurrent=1, lock_dir=lock_dir):
                pass
    finally:
        holder.kill()
        holder.wait()
    with job_slot("alice", max_concurrent=1, lock_dir=lock_dir) as slot:
        assert slot == 0


def test_acquire_all_references_refuses_before_doing_any_work(tmp_path, monkeypatch):
    from citeget import acquire_references as ar

    monkeypatch.setattr(
        ar, "acquire_reference", lambda *a, **k: pytest.fail("work started")
    )
    user_jobs = tmp_path / "users" / "alice" / "jobs"
    job_a, job_b = user_jobs / "a", user_jobs / "b"
    job_a.mkdir(parents=True)
    job_b.mkdir()
    ref = ar.Reference(number=1, raw="x", title="x")

    # Job A holds alice's only slot; job B, a sibling dir, is refused.
    with job_slot(str(user_jobs.resolve()), max_concurrent=1):
        with pytest.raises(JobLimitExceeded):
            ar.acquire_all_references(
                [ref], job_b / "references", work_dir=job_b, max_concurrent_jobs=1
            )


def test_acquire_all_references_cap_can_be_switched_off(tmp_path, monkeypatch):
    from citeget import acquire_references as ar

    monkeypatch.setattr(ar, "check_existing_downloads", lambda refs, d: ([], []))
    job = tmp_path / "jobs" / "a"
    job.mkdir(parents=True)
    with job_slot(str((tmp_path / "jobs").resolve()), max_concurrent=1):
        successes, failures, _ = ar.acquire_all_references(
            [], job / "references", work_dir=job, concurrency_key=None, verbose=False
        )
    assert successes == failures == []
