"""URLs that differ only in the query string must not share an output file."""

from types import SimpleNamespace

import pytest

import importlib

fetch_mod = importlib.import_module("citeget.fetch")

BASE = "http://example.com/magazine/consider_the_lobster?currentPage="
URLS = [f"{BASE}{i}" for i in (1, 2, 3)]


@pytest.fixture
def fake_http(monkeypatch):
    def _get(url, *, timeout=30, **_):
        return SimpleNamespace(
            headers={"content-type": "text/html"},
            text=f"<html><body><p>content of {url}</p></body></html>",
            content=b"",
        )

    monkeypatch.setattr(fetch_mod, "_http_get", _get)
    monkeypatch.setattr(fetch_mod, "_is_pdf_response", lambda r: False)


def test_query_variants_get_distinct_files_and_rerun_skips(fake_http, tmp_path):
    results = fetch_mod.fetch(URLS, output_dir=tmp_path)
    assert [r.status for r in results] == ["ok"] * 3
    assert len({r.output_file for r in results}) == 3
    for r, url in zip(results, URLS):
        assert url in r.output_file.read_text()

    again = fetch_mod.fetch(URLS, output_dir=tmp_path)
    assert [r.status for r in again] == ["skipped"] * 3
    assert len(list(tmp_path.iterdir())) == 3


def test_same_name_different_source_is_not_skipped(fake_http, tmp_path):
    a = "http://web.archive.org/web/1/http://x.com/post"
    b = "http://web.archive.org/web/2/http://x.com/post"
    ra = fetch_mod.fetch_one(a, output_dir=tmp_path)
    rb = fetch_mod.fetch_one(b, output_dir=tmp_path)
    assert (ra.status, rb.status) == ("ok", "ok")
    assert ra.output_file != rb.output_file
    assert fetch_mod.fetch_one(b, output_dir=tmp_path).status == "skipped"
    assert len(list(tmp_path.iterdir())) == 2
