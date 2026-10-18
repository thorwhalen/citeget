"""Shared fixtures: a fake web for exercising ``citeget.fetch`` with no network."""

import importlib

import httpx
import pytest


@pytest.fixture
def fake_web(monkeypatch):
    """Serve canned responses to ``citeget.fetch``, through its real ``_http_get``.

    Returns ``serve(routes)``, where *routes* maps a URL to a response or to a
    list of responses handed out one per request (the last one repeating). A
    response is an HTML string (served 200), an ``(status, html)`` pair, or an
    exception instance to raise. ``serve`` returns a dict counting requests per
    URL; ``serve.sleeps`` records every backoff wait.
    """
    # ``citeget.fetch`` is also the name of a function re-exported by the package.
    fetch_module = importlib.import_module("citeget.fetch")

    real_http_get = fetch_module._http_get
    calls: dict = {}
    sleeps: list = []

    def serve(routes):
        def handler(request):
            url = str(request.url)
            calls[url] = calls.get(url, 0) + 1
            answers = routes[url]
            if not isinstance(answers, list):
                answers = [answers]
            answer = answers[min(calls[url], len(answers)) - 1]
            if isinstance(answer, Exception):
                raise answer
            status, html = answer if isinstance(answer, tuple) else (200, answer)
            return httpx.Response(
                status, text=html, headers={"content-type": "text/html"}
            )

        def http_get(url, **kwargs):
            return real_http_get(
                url,
                transport=httpx.MockTransport(handler),
                sleep=sleeps.append,
                **kwargs,
            )

        monkeypatch.setattr(fetch_module, "_http_get", http_get)
        return calls

    serve.sleeps = sleeps
    return serve
