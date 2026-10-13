"""The per-job byte budget of ``acquire_all_references`` (#22).

The per-response ceiling bounds one file; a job of many references could still
write references x ceiling bytes onto a disk every hosted user shares.
"""

from __future__ import annotations

import pytest

from citeget import acquire_references as ar


def _refs(n):
    return [ar.Reference(number=i, raw=f"r{i}", title=f"Title {i}") for i in range(1, n + 1)]


@pytest.fixture
def fake_fetch(monkeypatch):
    """Each reference "downloads" a file of the size given in ``sizes``."""
    calls = []

    def acquire(ref, download_dir, *, log_entries, **kwargs):
        calls.append(ref.number)
        path = download_dir / f"ref{ref.number}.pdf"
        path.write_bytes(b"x" * fake_fetch.sizes[ref.number])
        return ar.AcquisitionResult(
            reference=ref, success=True, filepath=str(path), method="direct_url"
        )

    fake_fetch = type("F", (), {"sizes": {}, "calls": calls})
    monkeypatch.setattr(ar, "acquire_reference", acquire)
    return fake_fetch


def _run(tmp_path, refs, **kwargs):
    return ar.acquire_all_references(
        refs, tmp_path / "refs", delay=0, verbose=False, concurrency_key=None, **kwargs
    )


def test_once_spent_the_remaining_references_are_not_fetched(tmp_path, fake_fetch):
    fake_fetch.sizes = {1: 600, 2: 300, 3: 100, 4: 100}
    ok, failed, _ = _run(tmp_path, _refs(4), max_job_bytes=1000)
    assert [r.reference.number for r in ok] == [1, 2, 3]  # exactly 1000 bytes
    (refused,) = failed
    assert refused.reference.number == 4 and ar.JOB_BUDGET_NOTE in refused.notes
    assert fake_fetch.calls == [1, 2, 3]


def test_a_reference_that_overshoots_is_refused_and_its_file_removed(
    tmp_path, fake_fetch
):
    fake_fetch.sizes = {1: 600, 2: 600, 3: 100}
    ok, failed, _ = _run(tmp_path, _refs(3), max_job_bytes=1000)
    assert [r.reference.number for r in ok] == [1, 3]
    assert ar.JOB_BUDGET_NOTE in failed[0].notes
    assert not (tmp_path / "refs" / "ref2.pdf").exists()
    total = sum(p.stat().st_size for p in (tmp_path / "refs").iterdir())
    assert total <= 1000


def test_files_already_there_do_not_count(tmp_path, fake_fetch):
    (tmp_path / "refs").mkdir()
    (tmp_path / "refs" / "unrelated.bin").write_bytes(b"x" * 5000)
    fake_fetch.sizes = {1: 900}
    ok, failed, _ = _run(tmp_path, _refs(1), max_job_bytes=1000)
    assert len(ok) == 1 and not failed


def test_zero_means_no_budget(tmp_path, fake_fetch):
    fake_fetch.sizes = {1: 5000, 2: 5000}
    ok, failed, _ = _run(tmp_path, _refs(2), max_job_bytes=0)
    assert len(ok) == 2 and not failed


def test_the_budget_defaults_from_the_environment(tmp_path, fake_fetch, monkeypatch):
    monkeypatch.setenv(ar.MAX_JOB_BYTES_ENV_VAR, "500")
    fake_fetch.sizes = {1: 400, 2: 400}
    ok, failed, _ = _run(tmp_path, _refs(2))
    assert len(ok) == 1 and ar.JOB_BUDGET_NOTE in failed[0].notes


@pytest.mark.parametrize("bad", ["-1", "lots"])
def test_a_bad_environment_value_is_refused(tmp_path, fake_fetch, monkeypatch, bad):
    monkeypatch.setenv(ar.MAX_JOB_BYTES_ENV_VAR, bad)
    with pytest.raises(ValueError, match=ar.MAX_JOB_BYTES_ENV_VAR):
        _run(tmp_path, _refs(1))


def test_a_negative_argument_is_refused(tmp_path, fake_fetch):
    with pytest.raises(ValueError):
        _run(tmp_path, _refs(1), max_job_bytes=-5)
