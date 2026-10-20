"""fetch: bounded retry on transient errors, page-title filenames and manifest titles."""

import importlib
from types import SimpleNamespace

import pytest
import requests

fetch_mod = importlib.import_module("citeget.fetch")


def _resp(status=200, text="<html></html>"):
    def raise_for_status():
        if status >= 400:
            raise requests.HTTPError(f"{status}", response=SimpleNamespace(status_code=status))

    return SimpleNamespace(
        status_code=status, text=text, content=b"", headers={"content-type": "text/html"},
        raise_for_status=raise_for_status,
    )


def _script(monkeypatch, outcomes):
    """Make netguard.get yield *outcomes* in turn (exceptions are raised)."""
    calls = []

    def _get(url, **kw):
        calls.append(url)
        out = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(fetch_mod.netguard, "get", _get)
    return calls


def test_retries_a_disconnect_then_succeeds(monkeypatch):
    calls = _script(monkeypatch, [requests.ConnectionError("Server disconnected"), _resp()])
    sleeps = []
    assert fetch_mod._http_get("http://x.com/a", sleep=sleeps.append) is not None
    assert len(calls) == 2 and sleeps == [1.0]


@pytest.mark.parametrize("status", [429, 503])
def test_retries_transient_statuses_with_doubling_backoff(monkeypatch, status):
    calls = _script(monkeypatch, [_resp(status), _resp(status), _resp()])
    sleeps = []
    r = fetch_mod._http_get("http://x.com/a", sleep=sleeps.append, retry_backoff=0.5)
    assert r is not None and len(calls) == 3 and sleeps == [0.5, 1.0]


def test_gives_up_after_the_bound_and_never_retries_404(monkeypatch):
    calls = _script(monkeypatch, [_resp(503)])
    assert fetch_mod._http_get("http://x.com/a", retries=2, sleep=lambda s: None) is None
    assert len(calls) == 3
    calls = _script(monkeypatch, [_resp(404)])
    assert fetch_mod._http_get("http://x.com/a", sleep=lambda s: None) is None
    assert len(calls) == 1


def test_refused_url_is_not_retried(monkeypatch):
    calls = _script(monkeypatch, [fetch_mod.netguard.UnsafeURLError("private")])
    with pytest.raises(fetch_mod.netguard.UnsafeURLError):
        fetch_mod._http_get("http://10.0.0.1/", sleep=lambda s: None)
    assert len(calls) == 1


def test_retries_zero_means_one_attempt(monkeypatch):
    calls = _script(monkeypatch, [requests.ConnectionError("x")])
    assert fetch_mod._http_get("http://x.com/a", retries=0) is None
    assert len(calls) == 1


HTML = "<html><head><title>Hackers and Painters</title></head><body><p>hi</p></body></html>"


@pytest.fixture
def page(monkeypatch):
    def _make(html):
        monkeypatch.setattr(
            fetch_mod, "_http_get",
            lambda url, **kw: SimpleNamespace(headers={"content-type": "text/html"}, text=html, content=b""),
        )
    return _make


def test_page_title_names_the_file_and_fills_the_result(page, tmp_path):
    page(HTML)
    r = fetch_mod.fetch_one("http://paulgraham.com/hp.html", output_dir=tmp_path)
    assert r.title == "Hackers and Painters"
    assert r.output_file.name == "hackers-and-painters.md"


def test_path_stem_beats_the_hash_when_the_page_has_no_title(page, tmp_path):
    page("<html><body><p>hi</p></body></html>")
    r = fetch_mod.fetch_one("http://paulgraham.com/hp.html", output_dir=tmp_path)
    assert r.title is None and r.output_file.name == "hp.md"


def test_hash_only_without_title_or_stem(page, tmp_path):
    page("<html><body><p>hi</p></body></html>")
    r = fetch_mod.fetch_one("http://paulgraham.com/", output_dir=tmp_path)
    assert r.output_file.name.startswith("paulgraham-")


def test_explicit_title_wins_over_the_page(page, tmp_path):
    page(HTML)
    entry = fetch_mod.UrlEntry(url="http://x.com/a", title="Anchor Text")
    r = fetch_mod.fetch_one(entry, output_dir=tmp_path)
    assert r.title == "Anchor Text" and r.output_file.name == "anchor-text.md"


@pytest.mark.parametrize(
    "html, expected",
    [
        ('<head><meta property="og:title" content="OG  Title"><title>T</title></head>', "OG Title"),
        ("<body><h1> Only\n heading </h1></body>", "Only heading"),
        ("<body><p>none</p></body>", None),
    ],
)
def test_page_title_sources(html, expected):
    assert fetch_mod.page_title(html) == expected
