"""Tests for libgen mirror resolution and unreachable-mirror handling.

These cover the pure logic added to make the libgen mirror configurable and to
fail with an actionable message (rather than a raw Playwright stack trace) when
no mirror can be reached. None of these tests touch the network.
"""

import pytest

from citeget.core import (
    DEFAULT_LIBGEN_MIRRORS,
    BASE_URL,
    MirrorUnreachableError,
    _resolve_mirrors,
    _env_mirrors,
    _looks_like_unreachable,
    _format_unreachable_message,
    _build_search_url,
)

_ENV_KEYS = ("CITEGET_LIBGEN_MIRRORS", "CITEGET_LIBGEN_BASE_URL")


@pytest.fixture(autouse=True)
def _clear_mirror_env(monkeypatch):
    """Ensure mirror env vars never leak between tests."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_base_url_is_first_default_mirror():
    assert BASE_URL == DEFAULT_LIBGEN_MIRRORS[0]


def test_resolve_mirrors_default():
    assert _resolve_mirrors() == DEFAULT_LIBGEN_MIRRORS


def test_resolve_mirrors_explicit_precedence():
    # explicit mirrors beat base_url; trailing slashes are normalized
    assert _resolve_mirrors("https://one/", ["https://a/", "https://b"]) == (
        "https://a",
        "https://b",
    )
    assert _resolve_mirrors("https://only/") == ("https://only",)


def test_resolve_mirrors_env_multi(monkeypatch):
    monkeypatch.setenv("CITEGET_LIBGEN_MIRRORS", " https://m1/ , https://m2 ")
    assert _resolve_mirrors() == ("https://m1", "https://m2")


def test_resolve_mirrors_env_single(monkeypatch):
    monkeypatch.setenv("CITEGET_LIBGEN_BASE_URL", "https://single/")
    assert _resolve_mirrors() == ("https://single",)


def test_resolve_mirrors_multi_beats_single_env(monkeypatch):
    monkeypatch.setenv("CITEGET_LIBGEN_MIRRORS", "https://multi")
    monkeypatch.setenv("CITEGET_LIBGEN_BASE_URL", "https://single")
    assert _resolve_mirrors() == ("https://multi",)


def test_resolve_mirrors_arg_beats_env(monkeypatch):
    monkeypatch.setenv("CITEGET_LIBGEN_MIRRORS", "https://from-env")
    assert _resolve_mirrors(mirrors=["https://from-arg"]) == ("https://from-arg",)


def test_env_mirrors_none_when_unset():
    assert _env_mirrors() is None


@pytest.mark.parametrize(
    "text",
    [
        "Page.goto: net::ERR_CONNECTION_REFUSED at https://libgen.vg/...",
        "net::ERR_NAME_NOT_RESOLVED",
        "Timeout 20000ms exceeded",
        "net::ERR_CONNECTION_TIMED_OUT",
    ],
)
def test_looks_like_unreachable_true(text):
    assert _looks_like_unreachable(Exception(text)) is True


def test_looks_like_unreachable_false():
    assert _looks_like_unreachable(Exception("some parsing error")) is False


def test_build_search_url_uses_base_url():
    url = _build_search_url("foo bar", base_url="https://libgen.gs", topic="l")
    assert url.startswith("https://libgen.gs/index.php?")
    assert "req=foo+bar" in url


def test_build_search_url_strips_trailing_slash():
    url = _build_search_url("x", base_url="https://libgen.gs/", topic="l")
    assert url.startswith("https://libgen.gs/index.php?")
    assert "//index.php" not in url


def test_format_unreachable_message_is_actionable():
    attempts = [
        ("https://libgen.vg", Exception("net::ERR_CONNECTION_REFUSED\nsecond line")),
        ("https://libgen.gs", Exception("net::ERR_CONNECTION_REFUSED")),
    ]
    msg = _format_unreachable_message("my query", attempts)
    assert "my query" in msg
    assert "https://libgen.vg" in msg and "https://libgen.gs" in msg
    assert "127.0.0.1" in msg  # DNS-block hint
    assert "CITEGET_LIBGEN_MIRRORS" in msg  # override hint
    assert "second line" not in msg  # only the first line of each error is shown


def test_mirror_unreachable_error_is_runtimeerror():
    assert issubclass(MirrorUnreachableError, RuntimeError)
