"""Main-content extraction: keep the article, drop the site chrome around it.

A web page saved whole is mostly *not* the thing you wanted: skip links, menus,
sidebars, "about the author" boxes, post navigation, cookie banners, footers.
This module reduces a page to its main article, as HTML, so any HTML→Markdown
converter downstream gets only the document.

The pieces, each usable on its own:

- :func:`extract_main_content` — the default extractor (``html -> html``). A
  "readability-lite" built on ``beautifulsoup4`` alone: drop chrome by tag and
  by class/id, then keep the element holding the most paragraph text.
- :func:`trafilatura_extractor` — the same contract backed by ``trafilatura``
  (Apache-2.0), installed with ``pip install citeget[extract]``.
- :func:`clean_wayback_html` — remove the web.archive.org toolbar and rewrite
  ``web.archive.org/web/<timestamp>/`` link prefixes back to the original URLs.
- :func:`unwrap_layout_tables` — turn tables used for *page layout* (the essay
  sits in one cell) into plain blocks, leaving data tables alone.
- :func:`page_title` — the page's title, from ``<title>``, ``og:title`` or the
  first ``<h1>``, with a trailing site name removed.

Extractors are registered by name in :data:`MAIN_CONTENT_EXTRACTORS`, so a
caller can choose one with a string (``extractor="trafilatura"``) or pass any
callable ``html -> html``.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Callable, MutableMapping, Optional, Union

#: An extractor maps a page's HTML to the HTML of its main content.
Extractor = Callable[[str], str]

#: Tags whose whole subtree is chrome (or never readable text).
CHROME_TAGS = (
    "script",
    "style",
    "noscript",
    "template",
    "nav",
    "aside",
    "form",
    "iframe",
    "button",
    "svg",
    "dialog",
)

#: Dropped too, unless they hold code or a table (Jekyll wraps code blocks in
#: ``<figure class="highlight">``); otherwise they are images and captions.
FIGURE_TAGS = ("figure",)
_KEEP_FIGURE_IF_HOLDS = ("pre", "code", "table")

#: Inside these, class names describe syntax (``hljs-comment``,
#: ``token comment``), not page chrome.
CODE_TAGS = ("pre", "code")

#: Tags that are chrome unless they sit inside the article itself, where a
#: ``<header>`` usually holds the headline and a ``<footer>`` the byline.
OUTER_CHROME_TAGS = ("header", "footer")

#: A class or id token naming chrome. Matched against *whole tokens* split on
#: ``-`` and ``_`` (so ``post-nav`` and ``ad-wrapper`` match, ``canvas`` does
#: not). Values that only describe a *state* are exempt, see
#: :data:`STATE_CLASS_RE`.
CHROME_TOKEN_RE = re.compile(
    r"^(?:comments?|share|sharing|social|related|sidebar|newsletter|subscribe|"
    r"subscription|footer|nav|navbar|navigation|menu|breadcrumbs?|cookie|"
    r"consent|banner|promo|advert|ads?|sponsor|popup|modal|skip|author-?bio|"
    r"widget|pagination|toolbar)$",
    re.IGNORECASE,
)

#: A class saying what something *has* or *allows* (``has-sidebar``,
#: ``share-enabled``, ``with-comments``, ``no-ads``), usually on the article's
#: own wrapper. Not chrome.
STATE_CLASS_RE = re.compile(
    r"^(?:has|with|no|is|show|hide|allow)[-_]|[-_](?:enabled|disabled|active|"
    r"open|visible|hidden|on|off)$",
    re.IGNORECASE,
)

#: Elements considered as the possible main-content container.
CANDIDATE_TAGS = ("article", "main", "section", "div", "td", "font", "body")

#: Elements never removed as chrome, whatever their class says.
_PROTECTED_TAGS = ("html", "body", "article", "main")

# Scoring weights for :func:`extract_main_content`.
_NO_PARAGRAPH_TEXT_WEIGHT = 0.9  # pages like paulgraham.com use <br><br>, not <p>
_LINK_TEXT_PENALTY = 0.3
_DESCEND_RATIO = 0.85  # a child keeping this much of the score is more specific
_LAYOUT_CELL_MIN_CHARS = 200  # a cell this long holds prose, not data
_EDGE_BLOCK_MAX_CHARS = 200  # breadcrumbs and promo boxes are short
_EDGE_LINK_DENSITY = 0.5  # ... and mostly links, or boxed in a table


def _soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# web.archive.org
# ---------------------------------------------------------------------------

_WAYBACK_TOOLBAR_RE = re.compile(
    r"<!--\s*BEGIN WAYBACK TOOLBAR INSERT\s*-->.*?"
    r"<!--\s*END WAYBACK TOOLBAR INSERT\s*-->",
    re.DOTALL | re.IGNORECASE,
)
#: ``https://web.archive.org/web/20150308214418im_/`` and the relative
#: ``/web/20150308214418/`` form Wayback rewrites every link into.
WAYBACK_PREFIX_RE = re.compile(
    r"^(?:(?:https?:)?//web\.archive\.org)?/web/\d{1,14}(?:[a-z]{2}_)?/",
    re.IGNORECASE,
)
_WAYBACK_IDS = ("wm-ipp-base", "wm-ipp", "wm-ipp-print", "donato")


def is_wayback(html: str, url: str = "") -> bool:
    """True if *html* (or *url*) is a web.archive.org capture."""
    return "web.archive.org" in url or "BEGIN WAYBACK TOOLBAR INSERT" in html


def unwayback_url(url: str) -> str:
    """Strip a Wayback prefix from *url*, giving back the original URL.

    >>> unwayback_url("https://web.archive.org/web/20150308214418/http://a.com/x")
    'http://a.com/x'
    >>> unwayback_url("/web/20150308214418im_/http://a.com/p.png")
    'http://a.com/p.png'
    >>> unwayback_url("http://a.com/x")
    'http://a.com/x'
    """
    return WAYBACK_PREFIX_RE.sub("", url)


def clean_wayback_html(html: str) -> str:
    """Remove the Wayback toolbar from *html* and un-prefix its links.

    A page that is not a Wayback capture comes back unchanged.
    """
    if not is_wayback(html):
        return html
    soup = _soup(_WAYBACK_TOOLBAR_RE.sub("", html))
    for wid in _WAYBACK_IDS:
        for tag in soup.find_all(id=wid):
            tag.decompose()
    for tag in soup.find_all(href=True):
        tag["href"] = unwayback_url(tag["href"])
    for tag in soup.find_all(src=True):
        tag["src"] = unwayback_url(tag["src"])
    return str(soup)


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

#: Separators between an article title and a site name in ``<title>``.
TITLE_SEPARATORS = (" | ", " – ", " — ", " - ", " :: ", " · ", " : ")


def _same(a: str, b: str) -> bool:
    def key(text):
        return re.sub(r"\W+", " ", text).strip().lower()

    return bool(a and b) and key(a) == key(b)


def _slug_words(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _strip_site_name(
    title: str, *, site_names=(), article_titles=(), url: str = ""
) -> str:
    """The article's part of a ``Title – Site`` (or ``Site – Title``) title.

    A segment matching one of *article_titles* (``og:title``, the ``<h1>``s),
    or spelled out by the *url*'s path (``/reading-code-is-like-...``), wins;
    segments matching *site_names* (``og:site_name``, ``application-name``)
    are dropped; otherwise the first segment is kept, which is the usual order.

    >>> _strip_site_name("Reading Code is Like Reading the Talmud – Joel on Software")
    'Reading Code is Like Reading the Talmud'
    >>> _strip_site_name("Roger Federer as Religious Experience - Tennis - The New York Times")
    'Roger Federer as Religious Experience'
    >>> _strip_site_name("Joel on Software - Fire and Motion", site_names=["Joel on Software"])
    'Fire and Motion'
    >>> _strip_site_name("Hacker News | Show HN: A thing", article_titles=["Show HN: A thing"])
    'Show HN: A thing'
    >>> _strip_site_name("Stack Overflow - How do I X", url="https://so.com/q/1/how-do-i-x")
    'How do I X'
    >>> _strip_site_name("Beating the Averages")
    'Beating the Averages'
    """
    title = title.strip()
    for sep in TITLE_SEPARATORS:
        if sep not in title:
            continue
        parts = [part.strip() for part in title.split(sep) if part.strip()]
        path = _slug_words(urlparse(url).path) if url else ""
        for part in parts:
            if any(_same(part, t) for t in article_titles):
                return part
            if path and len(part.split()) >= 2 and _slug_words(part) in path:
                return part
        parts = [p for p in parts if not any(_same(p, n) for n in site_names)] or parts
        if len(parts[0].split()) >= 2 or len(parts) == 1:
            return parts[0]  # "X - Site" where X is one word is ambiguous
    return title


def page_title(html: str, *, url: str = "") -> Optional[str]:
    """The title of the page in *html*, or ``None``.

    Tries ``<title>`` (site name removed, using the page's metadata and its
    *url* to tell which part is the site), then ``og:title``, then the first
    ``<h1>``.

    >>> page_title("<title>Hackers and Painters</title>")
    'Hackers and Painters'
    >>> page_title('<meta property="og:title" content="A Title"><h1>Other</h1>')
    'A Title'
    >>> page_title("<p>no title here</p>") is None
    True
    """
    soup = _soup(html)

    def _clean(text):
        return re.sub(r"\s+", " ", text or "").strip()

    def _meta(**attrs):
        tag = soup.find("meta", attrs=attrs)
        return _clean(tag.get("content")) if tag else ""

    og_title = _meta(property="og:title")
    h1s = [_clean(h.get_text(" ")) for h in soup.find_all("h1")]
    if soup.title and _clean(soup.title.get_text()):
        return _strip_site_name(
            _clean(soup.title.get_text()),
            site_names=[_meta(property="og:site_name"), _meta(name="application-name")],
            article_titles=[og_title, *h1s],
            url=url,
        )
    if og_title:
        return og_title
    return next((h for h in h1s if h), None)


# ---------------------------------------------------------------------------
# Layout tables
# ---------------------------------------------------------------------------

_TABLE_PARTS = ("table", "thead", "tbody", "tfoot", "tr", "td", "th")


def _is_layout_table(table) -> bool:
    if table.find("table"):
        return True
    for cell in table.find_all(("td", "th")):
        if cell.find(("p", "br", "h1", "h2", "h3", "ul", "ol", "blockquote")):
            return True
        if len(cell.get_text(" ", strip=True)) > _LAYOUT_CELL_MIN_CHARS:
            return True
    return False


def unwrap_layout_tables(html: str) -> str:
    """Rewrite tables used for page layout as plain ``<div>`` blocks.

    A table is *layout* when it nests another table, or when a cell holds
    prose (paragraphs, line breaks, headings, or more than a short phrase).
    Data tables are left intact, so they still become Markdown tables.

    >>> unwrap_layout_tables("<table><tr><td><p>An essay.</p></td></tr></table>")
    '<div><div><div><p>An essay.</p></div></div></div>'
    >>> unwrap_layout_tables("<table><tr><td>1</td></tr></table>")
    '<table><tr><td>1</td></tr></table>'
    """
    soup = _soup(html)
    # Outermost first; an inner table is judged on its own when its turn comes.
    for table in soup.find_all("table"):
        if not _is_layout_table(table):
            continue
        own_parts = [
            part
            for part in table.find_all(_TABLE_PARTS[1:])
            if part.find_parent("table") is table
        ]
        for part in [table, *own_parts]:
            part.name = "div"
            part.attrs = {}
    # A lone cell handed over as the fragment root.
    for root in soup.find_all(_TABLE_PARTS[1:], recursive=False):
        root.name = "div"
        root.attrs = {}
    return str(soup)


# ---------------------------------------------------------------------------
# The built-in extractor
# ---------------------------------------------------------------------------


def _is_chrome_by_attrs(tag) -> bool:
    """True if a class or the id of *tag* names chrome.

    >>> _is_chrome_by_attrs(_soup('<div class="post-nav"></div>').div)
    True
    >>> _is_chrome_by_attrs(_soup('<div class="post-body share-enabled"></div>').div)
    False
    """
    return _chrome_match(tag) > 0


_NOT_CHROME, _CHROME_TOKEN, _CHROME_NAME = 0, 1, 2


def _chrome_match(tag) -> int:
    """How surely *tag*'s class/id names chrome.

    :data:`_CHROME_NAME` when a whole value is a chrome word (``id="comments"``,
    ``class="sidebar"``), :data:`_CHROME_TOKEN` when only a ``-``/``_`` token is
    (``post-nav``), :data:`_NOT_CHROME` otherwise.
    """
    match = _NOT_CHROME
    for value in (tag.get("class") or []) + [tag.get("id") or ""]:
        if not value or STATE_CLASS_RE.search(value):
            continue
        if CHROME_TOKEN_RE.match(value):
            return _CHROME_NAME
        if any(CHROME_TOKEN_RE.match(t) for t in re.split(r"[-_]", value)):
            match = _CHROME_TOKEN
    return match


def _text_len(tag) -> int:
    return len(tag.get_text(" ", strip=True))


def _paragraph_text_len(tag) -> int:
    return sum(len(p.get_text(" ", strip=True)) for p in tag.find_all("p"))


def _drop_chrome(soup) -> None:
    for tag in soup.find_all(CHROME_TAGS):
        tag.decompose()
    for tag in soup.find_all(FIGURE_TAGS):
        if not tag.find(_KEEP_FIGURE_IF_HOLDS):
            tag.decompose()
    for tag in soup.find_all(OUTER_CHROME_TAGS):
        if not tag.find_parent(("article", "main")):
            tag.decompose()
    total = _text_len(soup)
    total_paragraphs = _paragraph_text_len(soup)
    # Last first, so the comments after an article are gone before the
    # article's wrapper is judged against what is left of the page.
    for tag in reversed(soup.find_all(True)):
        if tag.decomposed:  # inside a subtree already dropped
            continue
        if tag.name in _PROTECTED_TAGS + CODE_TAGS or tag.find_parent(CODE_TAGS):
            continue
        match = _chrome_match(tag)
        if match == _NOT_CHROME:
            continue
        # A wrapper around the article whose class merely *mentions* chrome
        # (a token, not the whole name): it holds most of the page, or most of
        # its prose, or the headline. A section named "comments" outright is
        # dropped however long the discussion got.
        text, paragraphs = _text_len(tag), _paragraph_text_len(tag)
        if match == _CHROME_TOKEN and (
            text > total / 2
            or paragraphs > total_paragraphs / 2
            or tag.find(("article", "main", "h1"))
        ):
            continue
        total, total_paragraphs = total - text, total_paragraphs - paragraphs
        tag.decompose()


#: Tags that end an open ``<p>`` in HTML5. ``html.parser`` does not know this,
#: so ``<p>a <p>b`` (paragraphs never closed, as on idlewords.com) comes out
#: as one paragraph nested in another, the whole page deep.
_P_CLOSERS = (
    "p",
    "div",
    "table",
    "ul",
    "ol",
    "dl",
    "pre",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "section",
    "article",
)


def _unnest_paragraphs(soup) -> None:
    """Close paragraphs the way an HTML5 parser would, in place.

    >>> s = _soup("<div><p>a <p>b <p>c</div>")
    >>> _unnest_paragraphs(s); str(s)
    '<div><p>a </p><p>b </p><p>c</p></div>'
    """
    for p in soup.find_all("p"):  # document order: outer before inner
        children = list(p.children)
        cut = next(
            (
                i
                for i, c in enumerate(children)
                if getattr(c, "name", None) in _P_CLOSERS
            ),
            None,
        )
        if cut is None:
            continue
        anchor = p
        for node in children[cut:]:
            anchor.insert_after(node.extract())
            anchor = node


def _link_density(tag) -> float:
    text = _text_len(tag)
    links = sum(len(a.get_text(" ", strip=True)) for a in tag.find_all("a"))
    return links / text if text else 0.0


_BREADCRUMB_SEP_RE = re.compile(r"\s*[>»›/|·]\s*")


def _is_breadcrumb(node) -> bool:
    """``Home > Talks > This Talk``: links joined by separators, the last may be plain.

    >>> _is_breadcrumb(_soup('<p><a href="/">Home</a> > <a href="/t">Talks</a> > Mine</p>').p)
    True
    >>> _is_breadcrumb(_soup('<p>Read <a href="/">this</a> > that</p>').p)
    False
    """
    crumbs = [c for c in _BREADCRUMB_SEP_RE.split(node.get_text(" ", strip=True)) if c]
    links = {a.get_text(" ", strip=True) for a in node.find_all("a")}
    return len(crumbs) >= 2 and all(c in links for c in crumbs[:-1])


#: Block kinds that may be trimmed as edge chrome. Lists are not: a list of
#: links at the end of an article is usually its references.
_EDGE_TRIMMABLE = ("p", "div", "table", "span", "font", "center")


def _is_edge_chrome(node) -> bool:
    """A breadcrumb, a row of links or a promo box at the article's edge.

    Only short blocks qualify, and only: a breadcrumb; a table holding a link
    (a boxed promo, like paulgraham.com's); or a paragraph of two or more
    links that are most of its text. A data table, a single "see the paper"
    link and a reference list are content and stay.
    """
    if getattr(node, "name", None) not in _EDGE_TRIMMABLE:
        return False
    if _text_len(node) > _EDGE_BLOCK_MAX_CHARS:
        return False
    if _is_breadcrumb(node):
        return True
    links = node.find_all("a")
    if node.name == "table":
        return bool(links)
    return len(links) >= 2 and _link_density(node) >= _EDGE_LINK_DENSITY


def _trim_edges(tag) -> None:
    """Drop chrome blocks from the start and end of *tag*, in place."""

    def _blocks(nodes):
        for node in nodes:
            if getattr(node, "name", None) is None:
                if str(node).strip():
                    return  # real text at the edge: stop trimming
                continue
            if node.name in ("br", "img"):
                continue
            if not _is_edge_chrome(node):
                return
            yield node

    for nodes in (list(tag.children), list(reversed(list(tag.children)))):
        for node in list(_blocks(nodes)):
            node.decompose()


#: A paragraph this long, and not mostly links, is prose.
_PROSE_MIN_CHARS = 80


def _prose_paragraphs(tag) -> set:
    """Ids of the paragraphs under *tag* that are prose, not chrome."""
    return {
        id(p)
        for p in tag.find_all("p")
        if _text_len(p) >= _PROSE_MIN_CHARS and _link_density(p) < _EDGE_LINK_DENSITY
    }


def _score(tag) -> float:
    paragraphs = [p for p in tag.find_all("p") if p.find_parent("p") is None]
    if paragraphs:
        score = sum(len(p.get_text(" ", strip=True)) for p in paragraphs)
    else:
        score = _text_len(tag) * _NO_PARAGRAPH_TEXT_WEIGHT
    link_text = sum(len(a.get_text(strip=True)) for a in tag.find_all("a"))
    return score - _LINK_TEXT_PENALTY * link_text


def extract_main_content(html: str) -> str:
    """Return the HTML of the main content of the page in *html*.

    Drops chrome (by tag, then by class/id token), scores every candidate
    container by the paragraph text it holds less a penalty for link text,
    takes the best, then descends into a child that keeps most of the score,
    so a wrapper holding the article *and* leftovers loses to the article
    itself. Sibling blocks of the same kind that hold prose (an article split
    into sections, with a short conclusion) are kept with it. Needs only
    ``beautifulsoup4``.

    >>> page = '''<body><nav>Home | About</nav>
    ... <div class="sidebar"><p>Subscribe to my newsletter today, please.</p></div>
    ... <article><h1>Title</h1><p>The first sentence of a long article body.</p>
    ... <p>And the last one.</p></article><footer>(c) me</footer></body>'''
    >>> out = extract_main_content(page)
    >>> "first sentence" in out and "last one" in out
    True
    >>> any(s in out for s in ("Home", "Subscribe", "(c) me"))
    False
    """
    soup = _soup(html)
    _unnest_paragraphs(soup)
    _drop_chrome(soup)
    body = soup.body or soup
    candidates = [body, *body.find_all(CANDIDATE_TAGS)]
    scores = {id(tag): _score(tag) for tag in candidates}
    best = max(candidates, key=lambda tag: scores[id(tag)])

    # The most specific container that still holds most of the best score.
    threshold = _DESCEND_RATIO * scores[id(best)]
    if threshold > 0:
        deeper = [
            c for c in best.find_all(CANDIDATE_TAGS) if scores[id(c)] >= threshold
        ]
        best = min([best, *deeper], key=lambda tag: len(str(tag)))

    blocks = [best, *_prose_siblings(best)] if best.name != "body" else [best]
    for block in blocks:
        _trim_edges(block)
    if len(blocks) > 1:  # siblings: put them back in document order
        blocks.sort(key=best.parent.index)

    # Keep the headline when the best block is the body under it.
    h1 = soup.find("h1")
    fragment = "".join(str(block) for block in blocks)
    if h1 is not None and not any(b.find("h1") for b in blocks):
        if best.name != "body":
            fragment = str(h1) + fragment
    return fragment


def _prose_siblings(tag) -> list:
    """Siblings of *tag* (same tag, same class) holding prose: the rest of the article.

    >>> s = _soup('<div><section><p>{}</p></section><div><p>{}</p></div>'
    ...           '<section><p>{}</p></section></div>'.format("a" * 90, "b" * 90, "c" * 90))
    >>> [t.p.string[0] for t in _prose_siblings(s.section)]
    ['c']
    """
    if tag.parent is None:
        return []
    return [
        sibling
        for sibling in tag.parent.find_all(tag.name, recursive=False)
        if sibling is not tag
        and sibling.get("class") == tag.get("class")
        and not _is_chrome_by_attrs(sibling)
        and _prose_paragraphs(sibling)
    ]


def trafilatura_extractor(html: str) -> str:
    """Main content via ``trafilatura`` (Apache-2.0), as HTML.

    Install with ``pip install citeget[extract]``. Falls back to
    :func:`extract_main_content` when trafilatura finds nothing.
    """
    try:
        import trafilatura
    except ImportError as e:
        raise ImportError(
            "The 'trafilatura' extractor needs trafilatura (Apache-2.0). "
            "Install with: pip install citeget[extract]"
        ) from e
    out = trafilatura.extract(
        html,
        output_format="html",
        include_links=True,
        include_formatting=True,
        include_tables=True,
        include_images=False,
        include_comments=False,
    )
    return out or extract_main_content(html)


#: Named extractors, for choosing one with a string (CLI, config).
MAIN_CONTENT_EXTRACTORS: MutableMapping[str, Extractor] = {
    "builtin": extract_main_content,
    "trafilatura": trafilatura_extractor,
}

DFLT_EXTRACTOR = "builtin"


def register_extractor(name: str, extractor: Extractor) -> None:
    """Make *extractor* (``html -> html``) selectable as ``extractor=name``."""
    MAIN_CONTENT_EXTRACTORS[name] = extractor


def resolve_extractor(extractor: Union[str, Extractor, None]) -> Extractor:
    """Turn an extractor name (or callable, or ``None``) into a callable."""
    if extractor is None:
        extractor = DFLT_EXTRACTOR
    if callable(extractor):
        return extractor
    try:
        return MAIN_CONTENT_EXTRACTORS[extractor]
    except KeyError:
        raise ValueError(
            f"Unknown extractor {extractor!r}. "
            f"Known: {', '.join(MAIN_CONTENT_EXTRACTORS)}, or pass a callable."
        ) from None
