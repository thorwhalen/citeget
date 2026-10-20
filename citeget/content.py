"""Main-article extraction: strip site chrome from HTML before it becomes Markdown.

The default extractor, :func:`main_content`, is a "readability-lite" scorer built
on ``beautifulsoup4`` (already a dependency): it drops navigation-like elements,
then picks the block with the most paragraph text. Any callable ``html -> html``
can replace it (the *extractor* seam); :func:`trafilatura_extractor` is an
optional, stronger one (Apache-2.0, ``pip install trafilatura``).

Web Archive copies are cleaned by :func:`clean_wayback`: the toolbar/banner is
dropped and ``web.archive.org/web/<ts>/`` link prefixes are rewritten back to
the original URLs.

>>> html = "<body><nav>Menu</nav><div><p>" + "Real text. " * 20 + "</p></div></body>"
>>> "Menu" in main_content(html), "Real text." in main_content(html)
(False, True)
"""

from __future__ import annotations

import re
from typing import Callable, Mapping

Extractor = Callable[[str], str]

#: Elements that are never article content.
DROP_TAGS = (
    "script", "style", "nav", "header", "footer", "aside", "form", "noscript", "iframe",
)

#: Class/id fragments that mark chrome. Matched against single class/id tokens.
DROP_CLASS_RE = re.compile(
    r"(^|[-_ ])(comments?|share|sharing|related|sidebar|newsletter|subscribe|"
    r"subscription|footer|nav|navbar|menu|author-bio|byline|cookie|breadcrumbs?|"
    r"skip-link|post-navigation)([-_ ]|$)",
    re.I,
)

#: Tags considered as candidate containers for the article.
CANDIDATE_TAGS = ("article", "main", "div", "td", "section", "font", "body")

#: Weight of link text subtracted from a candidate's score (menus are all links).
LINK_PENALTY = 0.3

#: Pages without ``<p>`` (e.g. ``<br><br>`` separated) score by raw text times this.
NO_PARAGRAPH_FACTOR = 0.9

#: A descendant of the current best wins if it keeps this share of its score
#: (the tighter container, with less surrounding chrome).
DESCENT_RATIO = 0.9

#: A chrome-looking node holding more than this share of the page's text is a
#: layout wrapper (``no-sidebar``, ``content-share``), not chrome: keep it.
MAX_CHROME_TEXT_SHARE = 0.5

#: Main-mode Markdown shorter than this (characters) is distrusted and the
#: full page is converted instead (see ``html_to_markdown``).
MIN_MAIN_CHARS = 200

_WAYBACK_PREFIX_RE = re.compile(
    r"https?://web\.archive\.org/web/\d+(?:[a-z]{2}_)?/(?=https?:)", re.I
)


def _text_len(el) -> int:
    return len(el.get_text(" ", strip=True))


def _score(el) -> float:
    paragraphs = el.find_all("p")
    if paragraphs:
        score = sum(_text_len(p) for p in paragraphs)
    else:
        score = _text_len(el) * NO_PARAGRAPH_FACTOR
    return score - LINK_PENALTY * sum(_text_len(a) for a in el.find_all("a"))


def _is_chrome(tag) -> bool:
    if tag.name in ("html", "body"):
        return False
    tokens = [*(tag.get("class") or []), tag.get("id") or ""]
    return any(DROP_CLASS_RE.search(t) for t in tokens if t)


def main_content(html: str) -> str:
    """The HTML of the block that most likely holds the article body."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    total = _text_len(soup) or 1
    for tag in [t for t in soup.find_all(True) if _is_chrome(t)]:
        if _text_len(tag) <= MAX_CHROME_TEXT_SHARE * total:
            tag.decompose()
    best, best_score = soup.body or soup, 0.0  # document order: ancestors first
    for el in soup.find_all(CANDIDATE_TAGS):
        score = _score(el)
        tighter = best in el.parents and score >= DESCENT_RATIO * best_score
        if score > best_score or tighter:
            best, best_score = el, score
    if best.name == "td":  # a bare <td> would render as a table cell
        return f"<div>{best.decode_contents()}</div>"
    return str(best)


def trafilatura_extractor(html: str) -> str:
    """Extractor backed by ``trafilatura`` (optional dependency, Apache-2.0)."""
    try:
        import trafilatura
    except ImportError as e:  # pragma: no cover - depends on environment
        raise ImportError(
            "content_extractor='trafilatura' needs `pip install trafilatura` "
            "(or `pip install citeget[extract]`)."
        ) from e
    out = trafilatura.extract(html, output_format="html", include_links=True)
    return out or html


#: Named extractors, for the CLI and for ``content_extractor="name"``.
EXTRACTORS: Mapping[str, Extractor] = {
    "readability-lite": main_content,
    "trafilatura": trafilatura_extractor,
}

DEFAULT_EXTRACTOR = "readability-lite"


def clean_wayback(html: str) -> str:
    """Drop the Wayback Machine toolbar/banner and un-prefix archived links.

    >>> h = '<a href="https://web.archive.org/web/2020/http://x.org/a">a</a>'
    >>> clean_wayback(h)
    '<a href="http://x.org/a">a</a>'
    """
    html = re.sub(
        r"<!--\s*BEGIN WAYBACK TOOLBAR INSERT\s*-->.*?<!--\s*END WAYBACK TOOLBAR INSERT\s*-->",
        "",
        html,
        flags=re.S | re.I,
    )
    return _WAYBACK_PREFIX_RE.sub("", html)


def is_wayback_url(url: str) -> bool:
    return bool(re.match(r"https?://web\.archive\.org/web/", url or "", re.I))


#: Lines of converted Markdown that carry no content (table scaffolding, rules, empty bullets).
_JUNK_LINE_RE = re.compile(r"^[\s|\-_*=:]*$")


def drop_junk_lines(markdown: str) -> str:
    """Remove rule-only / empty-bullet lines and unwrap one-cell table rows.

    Fenced code blocks are left alone. Blank lines are kept (they separate paragraphs).

    >>> drop_junk_lines("| hello |\\n| --- |\\n* \\n\\ntext")
    'hello\\n\\ntext'
    """
    out, in_fence = [], False
    for line in markdown.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and line.strip():
            if _JUNK_LINE_RE.match(line):
                continue
            s = line.strip()
            if s.startswith("|") and s.endswith("|") and s.count("|") == 2:
                line = s.strip("|").strip()
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))
