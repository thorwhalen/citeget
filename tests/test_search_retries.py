"""Tests for mirror retry and failure classification (issues #3 and #4).

A single transient page-load timeout used to abort the entire search and report
it as "no mirror could be reached", even when the mirror was up and had been
serving results seconds earlier. The fix is to retry a mirror that merely timed
out, to wait for the results table rather than for network idle, and to say
which of the two failure modes actually happened.

No browser and no network: the page is faked.
"""

import pytest

from citeget import core
from citeget.core import (
    DEFAULT_LIBGEN_MIRRORS,
    _format_unreachable_message,
    _is_hard_unreachable,
    _load_with_retries,
    _looks_like_transient,
    _looks_like_unreachable,
)


class FakePage:
    """A page whose ``goto`` fails a scripted number of times, then succeeds."""

    def __init__(self, *, failures=(), table="<table>"):
        self.failures = list(failures)
        self.table = table
        self.goto_calls = []
        self.selector_waits = []

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        if self.failures:
            raise Exception(self.failures.pop(0))

    def wait_for_selector(self, selector, **kwargs):
        self.selector_waits.append((selector, kwargs))
        if self.table is None:
            raise TimeoutError("Timeout waiting for selector")

    def query_selector(self, selector):
        return self.table


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    """Retry backoff must not make the suite slow."""
    monkeypatch.setattr(core.time, "sleep", lambda seconds: None)


# --- issue #3: the mirror list ---------------------------------------------


def test_dead_mirror_is_gone_from_the_defaults():
    """libgen.gs has no A record; keeping it left one working mirror."""
    assert "https://libgen.gs" not in DEFAULT_LIBGEN_MIRRORS


def test_defaults_have_real_failover_depth():
    assert len(DEFAULT_LIBGEN_MIRRORS) >= 4
    assert len(set(DEFAULT_LIBGEN_MIRRORS)) == len(DEFAULT_LIBGEN_MIRRORS)
    assert all(m.startswith("https://") for m in DEFAULT_LIBGEN_MIRRORS)


def test_error_message_no_longer_recommends_the_dead_mirror():
    msg = _format_unreachable_message("q", [("https://libgen.vg", Exception("boom"))])
    assert "libgen.gs" not in msg


# --- issue #4: classification ----------------------------------------------


@pytest.mark.parametrize(
    "text", ["net::ERR_NAME_NOT_RESOLVED", "net::ERR_CONNECTION_REFUSED"]
)
def test_hard_failures_are_recognised(text):
    assert _is_hard_unreachable(Exception(text))
    assert not _looks_like_transient(Exception(text))


@pytest.mark.parametrize(
    "text",
    [
        "Page.goto: Timeout 20000ms exceeded.",
        "net::ERR_CONNECTION_TIMED_OUT",
        'interrupted by another navigation to "chrome-error://chromewebdata/"',
    ],
)
def test_transient_failures_are_recognised(text):
    assert _looks_like_transient(Exception(text))
    assert not _is_hard_unreachable(Exception(text))


def test_both_kinds_still_count_as_unreachable():
    # The coarse predicate keeps its old meaning: fail over to the next mirror.
    assert _looks_like_unreachable(Exception("Timeout 20000ms exceeded"))
    assert _looks_like_unreachable(Exception("net::ERR_NAME_NOT_RESOLVED"))
    assert not _looks_like_unreachable(Exception("some parsing error"))


# --- issue #4: retries ------------------------------------------------------


def test_a_timeout_is_retried_and_the_mirror_recovers():
    """The reported case: the first five searches worked, the sixth timed out
    once, and the mirror was fine the whole time."""
    page = FakePage(failures=["Page.goto: Timeout 20000ms exceeded."])
    table, exc = _load_with_retries(
        page,
        "https://libgen.vg/x",
        timeout=45000,
        table_timeout=20000,
        attempts=2,
        backoff=0,
    )
    assert exc is None and table == "<table>"
    assert len(page.goto_calls) == 2


def test_a_dead_domain_is_not_retried():
    page = FakePage(
        failures=["net::ERR_NAME_NOT_RESOLVED", "net::ERR_NAME_NOT_RESOLVED"]
    )
    table, exc = _load_with_retries(
        page,
        "https://libgen.gs/x",
        timeout=45000,
        table_timeout=20000,
        attempts=3,
        backoff=0,
    )
    assert table is None and "ERR_NAME_NOT_RESOLVED" in str(exc)
    assert len(page.goto_calls) == 1


def test_retries_are_bounded():
    page = FakePage(failures=["Timeout"] * 10)
    _, exc = _load_with_retries(
        page,
        "https://libgen.vg/x",
        timeout=45000,
        table_timeout=20000,
        attempts=3,
        backoff=0,
    )
    assert exc is not None
    assert len(page.goto_calls) == 3


def test_page_that_loads_without_a_table_is_a_no_results_answer():
    """Not an error: a mirror that answered is authoritative about having none."""
    page = FakePage(table=None)
    table, exc = _load_with_retries(
        page,
        "https://libgen.vg/x",
        timeout=45000,
        table_timeout=20000,
        attempts=2,
        backoff=0,
    )
    assert table is None and exc is None
    assert len(page.goto_calls) == 1  # no pointless retry


# --- issue #4: waiting for the right thing ---------------------------------


def test_waits_for_the_table_not_for_network_idle():
    """Libgen pages carry polling ad traffic and may never reach network idle,
    so goto must not require it — we only need #tablelibgen."""
    page = FakePage()
    core._load_results_table(
        page, "https://libgen.vg/x", timeout=45000, table_timeout=20000
    )
    _, goto_kwargs = page.goto_calls[0]
    assert goto_kwargs["wait_until"] == "domcontentloaded"
    assert page.selector_waits[0][0] == core.RESULTS_TABLE_SELECTOR


def test_defaults_are_generous_enough_for_ad_heavy_pages():
    """20s was routinely exceeded under load; the reporter's 45s made a
    38-book batch complete with zero mirror errors."""
    import inspect

    assert core.DEFAULT_SEARCH_TIMEOUT >= 45000
    assert inspect.signature(core.search).parameters["timeout"].default == (
        core.DEFAULT_SEARCH_TIMEOUT
    )
    assert core.DEFAULT_ATTEMPTS_PER_MIRROR >= 2


# --- issue #4: the message must not send you down a dead end ---------------


def test_message_for_timeouts_talks_about_timeouts():
    attempts = [
        ("https://libgen.vg", Exception("Page.goto: Timeout 20000ms exceeded.")),
        ("https://libgen.la", Exception("Page.goto: Timeout 20000ms exceeded.")),
    ]
    msg = _format_unreachable_message("q", attempts)
    assert "reachable, just slow" in msg
    assert "timeout=" in msg
    assert "127.0.0.1" not in msg  # the DNS dead end the reporter chased


def test_message_for_dead_domains_talks_about_dns():
    attempts = [("https://libgen.gs", Exception("net::ERR_NAME_NOT_RESOLVED"))]
    msg = _format_unreachable_message("q", attempts)
    assert "nothing answered at all" in msg
    assert "127.0.0.1" in msg


def test_message_for_a_mix_says_so():
    attempts = [
        ("https://libgen.gs", Exception("net::ERR_NAME_NOT_RESOLVED")),
        ("https://libgen.vg", Exception("Timeout 20000ms exceeded")),
    ]
    msg = _format_unreachable_message("q", attempts)
    assert "some mirrors did not answer" in msg
    assert "127.0.0.1" in msg and "timeout=" in msg


def test_message_points_at_the_mirror_health_check():
    msg = _format_unreachable_message("q", [("https://libgen.vg", Exception("boom"))])
    assert "check-mirrors" in msg


# --- a single empty mirror is not evidence of "no results" -----------------


class _FakeTable:
    """A results table element carrying a fixed number of data rows."""

    def __init__(self, rows):
        self._rows = rows

    def query_selector_all(self, selector):
        return self._rows


class _ScriptedPage:
    """Serves a scripted outcome per mirror, keyed by substring of the URL."""

    def __init__(self, script):
        self.script = script
        self.visited = []

    def _outcome(self, url):
        for key, outcome in self.script.items():
            if key in url:
                return outcome
        return None

    def goto(self, url, **kwargs):
        self.visited.append(url)
        outcome = self._outcome(url)
        if isinstance(outcome, Exception):
            raise outcome

    def wait_for_selector(self, selector, **kwargs):
        if self._outcome(self.visited[-1]) is None:
            raise TimeoutError("Timeout waiting for selector")

    def query_selector(self, selector):
        return self._outcome(self.visited[-1])


@pytest.fixture
def scripted_browser(monkeypatch):
    """Run search() against scripted pages instead of a real browser."""

    def _install(script):
        page = _ScriptedPage(script)

        class _Context:
            def new_page(self):
                return page

        class _Browser:
            def close(self):
                pass

        class _Playwright:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(
            "playwright.sync_api.sync_playwright", lambda: _Playwright()
        )
        monkeypatch.setattr(
            core, "_create_browser_context", lambda p, **kw: (_Browser(), _Context())
        )
        monkeypatch.setattr(core, "_parse_results_table", lambda t: [{"title": "hit"}])
        return page

    return _install


def test_empty_first_mirror_falls_over_to_a_working_one(scripted_browser):
    """The regression this guards: libgen.vg went slow, its table never
    rendered, and a query with 21 real hits came back as "Found 0 results"."""
    page = scripted_browser(
        {"libgen.vg": None, "libgen.la": _FakeTable(["header", "row"])}
    )
    results = core.search("q", mirrors=["https://libgen.vg", "https://libgen.la"])
    assert results == [{"title": "hit", "base_url": "https://libgen.la"}]
    assert len(page.visited) == 2


def test_two_empty_mirrors_agreeing_means_no_results(scripted_browser):
    page = scripted_browser({"libgen": None})
    mirrors = ["https://libgen.vg", "https://libgen.la", "https://libgen.li"]
    assert core.search("q", mirrors=mirrors) == []
    # Stops as soon as two mirrors agree; does not walk the whole list.
    assert len(page.visited) == 2


def test_unreachable_mirrors_still_raise_rather_than_returning_empty(
    scripted_browser,
):
    scripted_browser({"libgen": Exception("net::ERR_NAME_NOT_RESOLVED")})
    with pytest.raises(core.MirrorUnreachableError):
        core.search("q", mirrors=["https://libgen.vg", "https://libgen.la"])


def test_a_dead_mirror_plus_an_empty_one_reports_no_results(scripted_browser):
    scripted_browser(
        {
            "libgen.vg": Exception("net::ERR_NAME_NOT_RESOLVED"),
            "libgen.la": None,
        }
    )
    # One mirror answered and had nothing; that is the honest answer even
    # though the confirmation threshold was never reached.
    assert core.search("q", mirrors=["https://libgen.vg", "https://libgen.la"]) == []
