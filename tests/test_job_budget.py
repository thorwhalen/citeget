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


def test_a_reference_that_overshoots_is_refused_its_file_removed_and_the_job_stops(
    tmp_path, fake_fetch
):
    fake_fetch.sizes = {1: 600, 2: 600, 3: 100}
    ok, failed, log = _run(tmp_path, _refs(3), max_job_bytes=1000)
    assert [r.reference.number for r in ok] == [1]
    assert [r.reference.number for r in failed] == [2, 3]
    assert all(ar.JOB_BUDGET_NOTE in r.notes for r in failed)
    assert fake_fetch.calls == [1, 2]  # 3 is never fetched only to be discarded
    assert not (tmp_path / "refs" / "ref2.pdf").exists()
    assert any(ar.JOB_BUDGET_NOTE in str(e.get("error")) for e in log)


def test_an_overshoot_never_removes_a_file_another_run_wrote(
    tmp_path, fake_fetch, monkeypatch
):
    """A concurrent run sharing the directory may write while we fetch (review)."""
    fake_fetch.sizes = {1: 600}
    inner = ar.acquire_reference

    def with_neighbour(ref, download_dir, **kwargs):
        (download_dir / "other-run.pdf").write_bytes(b"y" * 900)
        return inner(ref, download_dir, **kwargs)

    monkeypatch.setattr(ar, "acquire_reference", with_neighbour)
    ok, failed, _ = _run(tmp_path, _refs(1), max_job_bytes=1000)
    assert not ok and ar.JOB_BUDGET_NOTE in failed[0].notes
    assert (tmp_path / "refs" / "other-run.pdf").exists()
    assert not (tmp_path / "refs" / "ref1.pdf").exists()


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


# --- #26: what is left of the budget caps each response as it arrives ---------

_UNDECLARED = b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n"  # no Content-Length


@pytest.mark.parametrize("declared", [True, False], ids=["declared", "streamed"])
def test_the_remaining_budget_refuses_a_response_before_it_lands(
    tmp_path, net, monkeypatch, declared
):
    """1000-byte budget, 600 spent: a 600-byte response is refused, no file left."""
    from tests.conftest import PUBLIC_IP, _response

    from citeget import resolve

    body = b"%PDF-" + b"x" * 595
    net.transport.responses[PUBLIC_IP] = (
        _response(200, body) if declared else _UNDECLARED + body
    )
    seen = []

    def acquire(ref, download_dir, **kwargs):
        path = download_dir / f"ref{ref.number}.pdf"
        if ref.number == 1:
            path.write_bytes(b"x" * 600)
            ok = True
        else:
            ok = resolve._any_downloader("http://good.example/paper.pdf", path)
        seen.append((ok, net.transport.connected[:]))
        return ar.AcquisitionResult(
            reference=ref, success=ok, filepath=str(path) if ok else None
        )

    monkeypatch.setattr(ar, "acquire_reference", acquire)
    ok, failed, _ = _run(tmp_path, _refs(2), max_job_bytes=1000)

    assert [r.reference.number for r in ok] == [1]
    assert [r.reference.number for r in failed] == [2]
    # Refused while it arrived -- not downloaded, counted, then deleted.
    assert seen[-1] == (False, [PUBLIC_IP]), "the download was not refused"
    assert not (tmp_path / "refs" / "ref2.pdf").exists(), "a refused body left a file"


def test_the_ceiling_names_the_budget_and_never_loosens_the_policy(net):
    from tests.conftest import PUBLIC_IP, _response

    from citeget import netguard

    net.transport.responses[PUBLIC_IP] = _response(200, b"y" * 600)
    with netguard.response_ceiling(400, source="the job byte budget"):
        with pytest.raises(netguard.ResponseTooLargeError, match="the job byte budget"):
            netguard.get("http://good.example/")
        # A policy tighter than the ceiling keeps its own limit and its own name.
        tight = netguard.NetPolicy(max_response_bytes=100)
        with pytest.raises(netguard.ResponseTooLargeError, match="CITEGET_MAX_RESPONSE"):
            netguard.get("http://good.example/", policy=tight)
        with netguard.response_ceiling(10_000):  # a looser inner block cannot widen it
            assert netguard.capped(netguard.NetPolicy()).max_response_bytes == 400
    assert netguard.get("http://good.example/").content == b"y" * 600


def test_a_swallowed_ceiling_refusal_still_spends_the_budget_and_stops_the_job(
    tmp_path, net, monkeypatch
):
    """Found by the review of #27. Downloaders swallow the refusal, so the
    reference merely "failed": the budget looked unspent and the job went on
    fetching. Real chain, no fake between the loop and netguard."""
    from tests.conftest import PUBLIC_IP, _response

    net.transport.responses[PUBLIC_IP] = _response(200, b"%PDF-" + b"x" * 1595)
    for name in ("_try_libgen", "_try_arxiv_search", "_try_scihub_via_doi"):
        monkeypatch.setattr(ar, name, lambda *a, **k: None)
    refs = [
        ar.Reference(
            number=i, raw=f"r{i}", title=f"Title {i}", url="http://good.example/paper.pdf"
        )
        for i in (1, 2, 3)
    ]
    ok, failed, _ = _run(tmp_path, refs, max_job_bytes=3000, fetch_fallback=False)

    assert [r.reference.number for r in ok] == [1]
    assert [r.reference.number for r in failed] == [2, 3]
    assert all(ar.JOB_BUDGET_NOTE in r.notes for r in failed), [r.notes for r in failed]
    assert len(net.transport.connected) == 2, "reference 3 was fetched after the overshoot"
