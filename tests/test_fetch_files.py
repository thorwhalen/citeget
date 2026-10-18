"""Output naming, collisions, skipping, retries and titles of ``citeget.fetch``.

Covers thorwhalen/citeget#30 (URLs differing only in their query string were
saved to one file, and the rest silently skipped) and #31 (no retry on
transient errors; hash filenames when a title or stem exists; ``title`` always
null in the manifest).
"""

import importlib
import json

import httpx
import pytest

from citeget.fetch import fetch, fetch_one


def _http_get(url, **kwargs):
    """The module's ``_http_get`` as patched by ``fake_web`` (looked up per call)."""
    return importlib.import_module("citeget.fetch")._http_get(url, **kwargs)


LOBSTER = (
    "http://web.archive.org/web/{ts}/http://www.gourmet.com:80/magazine/2000s/"
    "2004/08/consider_the_lobster?currentPage={page}"
)
LOBSTER_URLS = [
    LOBSTER.format(ts="20150308214418", page=1),
    LOBSTER.format(ts="20150302012444", page=2),
    LOBSTER.format(ts="20150308214424", page=3),
]


def _lobster_page(n):
    # Every page of a paginated article carries the same <title>.
    return (
        "<html><head><title>Consider the Lobster | Gourmet</title></head>"
        f"<body><article><p>This is page {n} of the lobster essay, "
        "long enough to be the article.</p></article></body></html>"
    )


@pytest.fixture
def lobster(fake_web, tmp_path):
    fake_web({url: _lobster_page(i) for i, url in enumerate(LOBSTER_URLS, 1)})
    urls_file = tmp_path / "pages.urls"
    urls_file.write_text("\n".join(LOBSTER_URLS) + "\n")
    return urls_file


# --- #30: distinct URLs never share a file -----------------------------------


def test_urls_differing_only_in_query_produce_one_file_each(lobster, tmp_path):
    out = tmp_path / "out"
    results = fetch(lobster, output_dir=out)

    assert [r.status for r in results] == ["ok", "ok", "ok"]
    files = sorted(out.iterdir())
    assert len(files) == 3
    assert len({r.output_file for r in results}) == 3
    for i, r in enumerate(results, 1):
        assert f"This is page {i} of the lobster" in r.output_file.read_text()
    assert [r.output_file.name for r in results] == [
        "consider-the-lobster.md",
        "consider-the-lobster-currentpage-2.md",
        "consider-the-lobster-currentpage-3.md",
    ]


def test_rerun_skips_all_three(lobster, tmp_path):
    out = tmp_path / "out"
    first = fetch(lobster, output_dir=out)
    before = {p.name: p.read_text() for p in out.iterdir()}

    again = fetch(lobster, output_dir=out)

    assert [r.status for r in again] == ["skipped", "skipped", "skipped"]
    assert [r.output_file for r in again] == [r.output_file for r in first]
    assert {p.name: p.read_text() for p in out.iterdir()} == before


def test_existing_file_from_another_url_is_not_a_skip(fake_web, tmp_path):
    """Across runs too: the ``<!-- Source: -->`` header says whose file it is."""
    fake_web({u: _lobster_page(i) for i, u in enumerate(LOBSTER_URLS, 1)})
    fetch_one(LOBSTER_URLS[0], output_dir=tmp_path)

    result = fetch_one(LOBSTER_URLS[1], output_dir=tmp_path)  # a separate run

    assert result.status == "ok"
    assert result.output_file.name == "consider-the-lobster-currentpage-2.md"
    assert "page 1" in (tmp_path / "consider-the-lobster.md").read_text()


def test_without_skip_existing_a_url_overwrites_only_its_own_file(fake_web, tmp_path):
    fake_web({u: _lobster_page(i) for i, u in enumerate(LOBSTER_URLS, 1)})
    fetch(LOBSTER_URLS, output_dir=tmp_path)

    again = fetch(LOBSTER_URLS, output_dir=tmp_path, skip_existing=False)

    assert [r.status for r in again] == ["ok", "ok", "ok"]
    assert len(list(tmp_path.iterdir())) == 3


def test_same_name_without_a_query_falls_back_to_a_url_hash(fake_web, tmp_path):
    urls = ["http://a.com/one/essay", "http://b.com/two/essay"]
    fake_web({u: "<p>An essay with no title at all, but some text.</p>" for u in urls})

    results = fetch(urls, output_dir=tmp_path)

    names = [r.output_file.name for r in results]
    assert names[0] == "essay.md"
    assert names[1].startswith("essay-") and names[1] != names[0]


# --- #31.1: retry transient errors -------------------------------------------

URL = "http://example.com/page"


def test_server_disconnect_is_retried(fake_web):
    calls = fake_web(
        {
            URL: [
                httpx.RemoteProtocolError(
                    "Server disconnected without sending a response."
                ),
                "<p>fine now</p>",
            ]
        }
    )
    resp = _http_get(URL, retry_backoff=1.5)

    assert resp is not None and "fine now" in resp.text
    assert calls[URL] == 2
    assert fake_web.sleeps == [1.5]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_statuses_are_retried_with_backoff(fake_web, status):
    calls = fake_web({URL: [(status, "busy"), (status, "busy"), "<p>ok</p>"]})

    resp = _http_get(URL, retries=2, retry_backoff=1.0)

    assert resp is not None and resp.status_code == 200
    assert calls[URL] == 3
    assert fake_web.sleeps == [1.0, 2.0]  # exponential


def test_other_errors_fail_at_once(fake_web):
    calls = fake_web({URL: (404, "gone")})
    assert _http_get(URL) is None
    assert calls[URL] == 1
    assert fake_web.sleeps == []


def test_retries_are_bounded(fake_web, tmp_path):
    calls = fake_web({URL: httpx.ConnectError("connection reset")})

    result = fetch_one(URL, output_dir=tmp_path, retries=3)

    assert result.status == "failed" and result.error == "fetch_failed"
    assert calls[URL] == 4  # the first attempt and three retries


def test_retries_zero_means_one_attempt(fake_web):
    calls = fake_web({URL: [(503, "busy"), "<p>ok</p>"]})
    resp = _http_get(URL, retries=0)
    assert calls[URL] == 1
    assert resp is None  # the 503 is final


# --- #31.2 / #31.3: title-based names, title in the result and manifest ------

HP = "http://paulgraham.com/hp.html"


def test_page_title_names_the_file_before_the_path_stem(fake_web, tmp_path):
    fake_web({HP: "<title>Hackers and Painters</title><p>May 2003. Text.</p>"})
    result = fetch_one(HP, output_dir=tmp_path)
    assert result.output_file.name == "hackers-and-painters.md"


def test_path_stem_names_the_file_before_the_domain_hash(fake_web, tmp_path):
    fake_web({HP: "<p>May 2003. A page with no title.</p>"})
    result = fetch_one(HP, output_dir=tmp_path)
    assert result.output_file.name == "hp.md"  # was paulgraham-79c7b37d.md


def test_link_text_still_wins_over_the_page_title(fake_web, tmp_path):
    fake_web({HP: "<title>Hackers and Painters</title><p>Text.</p>"})
    result = fetch(f"[My own name for it]({HP})", output_dir=tmp_path)[0]
    assert result.output_file.name == "my-own-name-for-it.md"
    assert result.title == "My own name for it"


@pytest.mark.parametrize(
    "head, expected",
    [
        ("<title>Hackers and Painters</title>", "Hackers and Painters"),
        ('<meta property="og:title" content="Hackers and Painters">', None),
        ("", None),
    ],
)
def test_result_title_comes_from_the_page(fake_web, tmp_path, head, expected):
    body = "<body><h1>Hackers and Painters</h1><p>Text.</p></body>"
    fake_web({HP: f"<html><head>{head}</head>{body}</html>"})
    result = fetch_one(HP, output_dir=tmp_path)
    # og:title and the first <h1> are the fallbacks after <title>.
    assert result.title == (expected or "Hackers and Painters")


def test_manifest_records_the_page_title(fake_web, tmp_path, capsys):
    from citeget.cli import fetch as cli_fetch

    fake_web({HP: "<title>Hackers and Painters</title><p>May 2003. Text.</p>"})
    manifest = tmp_path / "manifest.json"

    cli_fetch(HP, output_dir=str(tmp_path / "out"), manifest=str(manifest))

    (entry,) = json.loads(manifest.read_text())
    assert entry["title"] == "Hackers and Painters"
    assert entry["output_file"].endswith("hackers-and-painters.md")


# --- regressions found in review ---------------------------------------------


@pytest.mark.parametrize("value", ["-5", "nan", "inf", "1e9", "soon"])
def test_unusable_retry_after_does_not_crash(fake_web, value):
    busy = httpx.Response(503, headers={"retry-after": value})
    calls = fake_web({URL: [busy, "<p>ok</p>"]})

    resp = _http_get(URL)

    assert resp is not None and resp.status_code == 200
    assert calls[URL] == 2
    assert len(fake_web.sleeps) == 1 and 0 <= fake_web.sleeps[0] <= 60


def test_rerun_over_files_named_by_the_old_scheme_skips(fake_web, tmp_path):
    """A folder from before title-based names: ``hp.md`` is found, not duplicated."""
    old = tmp_path / "hp.md"
    old.write_text(f"<!-- Source: {HP} -->\n\nsaved by an older citeget\n")
    fake_web({HP: "<title>Hackers and Painters</title><p>May 2003. Text.</p>"})

    result = fetch(HP, output_dir=tmp_path)[0]

    assert result.status == "skipped"
    assert result.output_file == old
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hp.md"]
