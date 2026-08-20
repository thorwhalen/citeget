"""Tests for the libgen download path (issues #6 and #8).

Issue #8 is the expensive one: when libgen serves the file as an attachment,
``page.goto()`` raises ``Page.goto: Download is starting`` — documented
Playwright behaviour — and the old code let it escape the ``expect_download``
block, discarding a download that was already succeeding. Because the ``key`` in
the ``get.php`` URL is single-use, the HTTP fallback could not recover either,
so a perfectly available book was written off and the caller fell through to
lower-ranked candidates, which on libgen are frequently excerpts.

The Playwright page is faked here: these are logic tests, no browser and no
network.
"""

import io

import pytest

from citeget import core
from citeget.validate import ValidationPolicy

pypdf = pytest.importorskip("pypdf")

GET_URL = "https://libgen.vg/get.php?md5=" + "9c" * 16 + "&key=SINGLEUSE"

# Floors low enough that fixtures are judged on content, not on file size.
_TINY = ValidationPolicy(min_bytes=100, min_pdf_bytes=100)


def _pdf(pages: int = 3) -> bytes:
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class _FakeDownload:
    def __init__(self, payload):
        self._payload = payload

    def save_as(self, path):
        with open(path, "wb") as stream:
            stream.write(self._payload)


class _FakeExpectDownload:
    """Stand-in for ``page.expect_download()``.

    Mirrors the real contract: leaving the block raises if no download arrived,
    and ``.value`` is only meaningful once it has.
    """

    def __init__(self, page):
        self._page = page

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        if self._page.download_error:
            raise TimeoutError(self._page.download_error)
        return False

    @property
    def value(self):
        return _FakeDownload(self._page.payload)


class _FakeResponse:
    def __init__(self, body, ok=True):
        self._body = body
        self.ok = ok

    def body(self):
        return self._body


class _FakeRequest:
    def __init__(self, page):
        self._page = page

    def get(self, url, **kwargs):
        self._page.request_calls.append(url)
        if self._page.request_body is None:
            raise RuntimeError("request failed")
        return _FakeResponse(self._page.request_body)


class FakePage:
    """Minimal Playwright page covering only what the download path touches."""

    def __init__(
        self, *, payload=b"", goto_error=None, download_error=None, request_body=None
    ):
        self.payload = payload
        self.goto_error = goto_error
        self.download_error = download_error
        self.request_body = request_body
        self.goto_calls = []
        self.request_calls = []
        self.request = _FakeRequest(self)

    def expect_download(self, timeout=None):
        return _FakeExpectDownload(self)

    def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        if self.goto_error:
            raise Exception(self.goto_error)


@pytest.fixture
def canned_get_url(monkeypatch):
    """Skip the ads.php hop; it is not what these tests are about."""
    monkeypatch.setattr(core, "_get_download_url", lambda *a, **k: GET_URL)


# --- issue #8 ---------------------------------------------------------------


def test_download_is_starting_is_not_a_failure(canned_get_url, tmp_path):
    """The exact failure from the issue: goto raises, the download still lands."""
    payload = _pdf(241)
    page = FakePage(payload=payload, goto_error="Page.goto: Download is starting")
    target = tmp_path / "A Prehistory of the Cloud (Hu, 2015).pdf"

    saved = core._try_libgen_download(
        page,
        "/ads.php?md5=x",
        target,
        timeout=1000,
        delay=0,
        extension="pdf",
        policy=_TINY,
    )

    assert saved == str(target)
    assert target.read_bytes() == payload


def test_single_use_key_is_not_burned_on_a_pointless_retry(canned_get_url, tmp_path):
    """Once libgen has started the transfer the key is spent, so refetching
    get.php can only return an HTML error page. Do not try."""
    page = FakePage(
        goto_error="Page.goto: Download is starting",
        download_error="Timeout 1000ms exceeded",
        request_body=b"<!DOCTYPE html><html>error</html>",
    )
    with pytest.raises(RuntimeError):
        core._try_libgen_download(
            page, "/ads.php?md5=x", tmp_path / "book.pdf", timeout=1000, delay=0
        )
    assert page.request_calls == []


def test_http_fallback_still_runs_when_goto_never_reached_libgen(
    canned_get_url, tmp_path
):
    """A timeout means the key may be unspent, so the fallback is worth trying."""
    page = FakePage(
        goto_error="Page.goto: Timeout 1000ms exceeded",
        download_error="Timeout 1000ms exceeded",
        request_body=_pdf(200),
    )
    target = tmp_path / "book.pdf"
    saved = core._try_libgen_download(
        page,
        "/ads.php?md5=x",
        target,
        timeout=1000,
        delay=0,
        extension="pdf",
        policy=_TINY,
    )
    assert saved == str(target)
    assert page.request_calls == [GET_URL]


def test_failure_message_is_one_line_not_a_playwright_call_log(
    canned_get_url, tmp_path
):
    page = FakePage(
        goto_error="Page.goto: Timeout 1000ms exceeded\nCall log:\n  - navigating to ...",
        download_error="Timeout 1000ms exceeded\nCall log:\n  - waiting for download",
    )
    with pytest.raises(RuntimeError) as excinfo:
        core._try_libgen_download(
            page, "/ads.php?md5=x", tmp_path / "book.pdf", timeout=1000, delay=0
        )
    assert "\n" not in str(excinfo.value)


def test_is_download_started_recognises_the_playwright_message():
    assert core._is_download_started(Exception("Page.goto: Download is starting"))
    assert not core._is_download_started(
        Exception("Page.goto: Timeout 20000ms exceeded")
    )


# --- issue #6: a failed attempt must not poison the cache -------------------


def test_invalid_download_leaves_nothing_behind(canned_get_url, tmp_path):
    """The old code saved first and validated after, leaving a stub on disk."""
    page = FakePage(payload=b"<!DOCTYPE html><html>not a book</html>")
    target = tmp_path / "book.pdf"

    with pytest.raises(Exception):
        core._try_libgen_download(
            page, "/ads.php?md5=x", target, timeout=1000, delay=0, extension="pdf"
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_successful_download_leaves_no_temp_file(canned_get_url, tmp_path):
    page = FakePage(payload=_pdf(120))
    target = tmp_path / "book.pdf"
    core._try_libgen_download(
        page,
        "/ads.php?md5=x",
        target,
        timeout=1000,
        delay=0,
        extension="pdf",
        policy=_TINY,
    )
    assert [p.name for p in tmp_path.iterdir()] == ["book.pdf"]


def test_stub_on_disk_is_not_returned_as_a_cached_success(tmp_path, monkeypatch):
    """Reproduction A from the issue: a 200-byte leftover read back as success."""
    result = {
        "title": "Some Book",
        "authors": "Smith, John",
        "year": "2020",
        "extension": "pdf",
        "libgen_href": "/ads.php?md5=" + "0" * 32,
        "mirrors": {},
        "base_url": "https://libgen.vg",
        "size": "3 MB",
    }
    stub = tmp_path / core._make_filename(result)
    stub.write_bytes(b"x" * 200)

    # No browser: the point is that the stub is rejected before any download.
    page = FakePage(goto_error="Page.goto: net::ERR_CONNECTION_REFUSED")
    monkeypatch.setattr(core, "_get_download_url", lambda *a, **k: None)

    assert core.download_one(result, download_dir=str(tmp_path), page=page) is None
    assert not stub.exists()


def test_valid_file_on_disk_is_still_a_cached_success(tmp_path):
    result = {
        "title": "Some Book",
        "authors": "Smith, John",
        "year": "2020",
        "extension": "pdf",
        "libgen_href": "/ads.php?md5=" + "0" * 32,
        "mirrors": {},
        "size": "",  # nothing advertised, so no truncation cross-check
    }
    cached = tmp_path / core._make_filename(result)
    cached.write_bytes(_pdf(300))

    got = core.download_one(
        result, download_dir=str(tmp_path), page=FakePage(), policy=_TINY
    )
    assert got == str(cached)


def test_validation_can_be_turned_off(tmp_path):
    result = {
        "title": "Some Book",
        "authors": "Smith, John",
        "year": "2020",
        "extension": "pdf",
        "libgen_href": "/ads.php?md5=" + "0" * 32,
        "mirrors": {},
        "size": "3 MB",
    }
    stub = tmp_path / core._make_filename(result)
    stub.write_bytes(b"x" * 200)
    got = core.download_one(
        result, download_dir=str(tmp_path), page=FakePage(), validate=False
    )
    assert got == str(stub)


def test_cached_file_far_smaller_than_advertised_is_rejected(tmp_path, monkeypatch):
    """A complete-looking PDF that is a fraction of the advertised size is a
    truncated transfer, not a cache hit."""
    result = {
        "title": "Some Book",
        "authors": "Smith, John",
        "year": "2020",
        "extension": "pdf",
        "libgen_href": "/ads.php?md5=" + "0" * 32,
        "mirrors": {},
        "size": "25 MB",
    }
    cached = tmp_path / core._make_filename(result)
    cached.write_bytes(_pdf(300))
    monkeypatch.setattr(core, "_get_download_url", lambda *a, **k: None)

    assert (
        core.download_one(
            result, download_dir=str(tmp_path), page=FakePage(), policy=_TINY
        )
        is None
    )
    assert not cached.exists()
