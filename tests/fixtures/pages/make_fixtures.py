"""Regenerate the saved-page fixtures used by ``tests/test_main_content.py``.

Run by hand (it needs the network); the tests themselves never fetch::

    python tests/fixtures/pages/make_fixtures.py

Each fixture is the page's real markup -- the chrome, the layout, the Wayback
toolbar -- with two reductions, so that a public repo does not redistribute
the articles themselves:

1. ``<script>`` and ``<style>`` bodies are emptied (extraction drops them, and
   they are most of the bytes).
2. Every long text node is replaced by filler of exactly the same length
   (letters and digits become ``x``), except the nodes holding the article's
   first and last lines, which are what the tests check. Same length means
   the extractor's text-length scores, and so its choice of block, are the
   same as on the live page.

Next to each ``NAME.html`` it writes ``NAME.full.md``: the whole-page Markdown
of that fixture as produced by ``html_to_markdown`` -- the ``content="full"``
behaviour -- which the tests pin.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

#: name -> URL, the five pages of thorwhalen/citeget#29.
PAGES = {
    "paulgraham_avg": "http://paulgraham.com/avg.html",
    "joelonsoftware_talmud": (
        "https://www.joelonsoftware.com/2000/05/26/"
        "reading-code-is-like-reading-the-talmud/"
    ),
    "danluu_wat": "https://danluu.com/wat/",
    "idlewords_haunted_by_data": "https://idlewords.com/talks/haunted_by_data.htm",
    "wayback_nytimes_federer": (
        "http://web.archive.org/web/20260107113355/https://www.nytimes.com/"
        "2006/08/20/sports/playmagazine/20federer.html"
    ),
}

LONG_TEXT = 80  # characters: shorter nodes (menus, headings, labels) are kept


def _norm(text):
    return re.sub(r"\s+", " ", text).strip()


def reduce_page(html: str) -> str:
    from bs4 import BeautifulSoup, Comment, NavigableString

    from citeget.fetch import main_content_markdown

    lines = [
        _norm(re.sub(r"[*_`>\[\]]", "", re.sub(r"\]\([^)]*\)", "", line)))
        for line in main_content_markdown(html).splitlines()
        if line.strip() and not line.startswith(("<!--", "#"))
    ]
    keep = (lines[0][:40], lines[-1][-40:], lines[-1][4:40])  # 4: past "12. "

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(("script", "style")):
        tag.string = ""
    for node in soup.find_all(string=True):
        if isinstance(node, Comment) or not isinstance(node, NavigableString):
            continue
        if node.parent.name in ("title", "script", "style"):
            continue
        text = str(node)
        if len(text.strip()) < LONG_TEXT or any(k and k in _norm(text) for k in keep):
            continue
        node.replace_with(re.sub(r"[^\W_]", "x", text))
    return str(soup)


def main(names=()):
    import httpx

    from citeget.fetch import _HEADERS, html_to_markdown

    for name, url in PAGES.items():
        if names and name not in names:
            continue
        html = httpx.get(url, follow_redirects=True, timeout=60, headers=_HEADERS).text
        page = reduce_page(html)
        (HERE / f"{name}.html").write_text(page, encoding="utf-8")
        full = html_to_markdown(page, source_url=url)
        (HERE / f"{name}.full.md").write_text(full, encoding="utf-8")
        print(f"{name}: {len(page):,} chars")


if __name__ == "__main__":
    main(sys.argv[1:])
