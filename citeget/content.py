"""Main-article extraction: strip site chrome from HTML before it becomes Markdown.

The default extractor, :func:`main_content`, is a "readability-lite" scorer built
on ``beautifulsoup4`` (already a dependency): it drops navigation-like elements,
then picks the block with the most paragraph text. Any callable ``html -> html``
can replace it (the *extractor* seam); :func:`trafilatura_extractor` is an
optional, stronger one (Apache-2.0, ``pip install trafilatura``).

Web Archive copies are cleaned by :func:`clean_wayback`: the toolbar/banner is
dropped and ``web.archive.org/web/<ts>/`` link prefixes (absolute, relative or
protocol-relative) are rewritten back to the original URLs. This applies in
every content mode, ``full`` included.

Also here, because the extractor needs them: :func:`page_title` (the page's
title, with a ``Title – Site`` site name removed by :func:`strip_site_name`)
and :func:`unwrap_layout_tables` (tables used for page layout become plain
blocks; data tables are left alone).

>>> html = "<body><nav>Menu</nav><div><p>" + "Real text. " * 20 + "</p></div></body>"
>>> "Menu" in main_content(html), "Real text." in main_content(html)
(False, True)
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, Mapping, Optional
from urllib.parse import urlparse

Extractor = Callable[[str], str]

#: Elements that are never article content.
DROP_TAGS = (
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "noscript",
    "iframe",
    "template",
    "button",
    "svg",
    "dialog",
)

#: Words that, in a class or id, mark chrome.
_CHROME_WORDS = (
    r"comments?|share|sharing|related|sidebar|newsletter|subscribe|"
    r"subscription|footer|nav|navbar|menu|author-bio|byline|cookie|breadcrumbs?|"
    r"skip-link|post-navigation"
)

#: Class/id fragments that mark chrome. Matched against single class/id tokens.
DROP_CLASS_RE = re.compile(rf"(^|[-_ ])({_CHROME_WORDS})([-_ ]|$)", re.I)

#: A class/id value that *is* a chrome word (``id="comments"``): chrome however
#: much of the page it holds, unlike a value merely containing one
#: (``content-share``), which the share guard below may keep as a wrapper.
CHROME_NAME_RE = re.compile(rf"({_CHROME_WORDS})", re.I)

#: A class saying what something *has*, *allows* or *is* (``has-sidebar``,
#: ``share-enabled``, ``with-comments``, ``no-ads``): usually on the article's
#: own wrapper, so never a reason to call it chrome.
STATE_CLASS_RE = re.compile(
    r"^(?:has|with|no|is|show|hide|allow)[-_]|[-_](?:enabled|disabled|active|"
    r"open|visible|hidden|on|off)$",
    re.I,
)

#: Inside these, class names describe syntax (``hljs-comment``,
#: ``token comment``), not page chrome.
CODE_TAGS = ("pre", "code")

#: Elements dropped as chrome only when they hold little of the page: an ASP.NET
#: page wraps its whole body in one ``<form>``, which is a layout wrapper then.
CHROME_IF_SMALL_TAGS = ("form",)

#: Tags considered as candidate containers for the article.
CANDIDATE_TAGS = ("article", "main", "div", "td", "section", "font", "body")

#: Weight of link text subtracted from a candidate's score (menus are all links).
LINK_PENALTY = 0.3

#: Pages without ``<p>`` (e.g. ``<br><br>`` separated) score by raw text times this.
NO_PARAGRAPH_FACTOR = 0.9

#: A descendant of the current best wins if it keeps this share of its score
#: (the tighter container, with less surrounding chrome).
DESCENT_RATIO = 0.9

#: ...but never by shedding more than this many characters of paragraph text:
#: on a long page 10% can be a whole intro, which belongs to the article.
MAX_DESCENT_LOSS = 500

#: A chrome-looking node holding more than this share of the page's text is a
#: layout wrapper (``no-sidebar``, ``content-share``), not chrome: keep it.
MAX_CHROME_TEXT_SHARE = 0.5

#: Main-mode Markdown shorter than this (characters) is distrusted and the
#: full page is converted instead (see ``html_to_markdown``).
MIN_MAIN_CHARS = 200

#: Trimming the edges of the chosen block: breadcrumbs and promo boxes are
#: short (characters) and mostly links (share of the block's text).
EDGE_BLOCK_MAX_CHARS = 200
EDGE_LINK_DENSITY = 0.5

#: How many levels of nested wrappers edge trimming steps into: the ad slot
#: closing an article often sits in the article's last box, not directly in it.
EDGE_TRIM_DEPTH = 3

#: The whole text of an ad slot: its label, and maybe the skip link after it.
_AD_SLOT_RE = re.compile(
    r"\W*(advertisement|sponsored content)(\W+skip\W+advertisement)?\W*", re.I
)

#: A paragraph this long (characters), and not mostly links, is prose: a
#: same-kind sibling of the chosen block holding one is the rest of the article.
PROSE_MIN_CHARS = 80

#: A table cell holding more text than this (characters) holds prose, so the
#: table is page layout, not data.
LAYOUT_CELL_MIN_CHARS = 200

#: ``https://web.archive.org/web/20150308214418im_/``, its protocol-relative
#: form and the relative ``/web/20150308214418/`` Wayback rewrites links into.
WAYBACK_PREFIX_RE = re.compile(
    r"^(?:(?:https?:)?//web\.archive\.org)?/web/\d{1,14}(?:[a-z]{2}_)?/"
    r"(?=https?:|//|mailto:)",
    re.I,
)
#: The same prefix anywhere in text (a URL shown as a link's text, say).
_WAYBACK_TEXT_PREFIX_RE = re.compile(
    r"https?://web\.archive\.org/web/\d+(?:[a-z]{2}_)?/(?=https?:)", re.I
)
#: The toolbar as markup, not as text quoted in a code sample.
_WAYBACK_MARKER_RE = re.compile(
    r"<!--\s*BEGIN WAYBACK TOOLBAR INSERT|<[a-z]+\s[^>]*\bid=[\"']?wm-ipp-base\b", re.I
)
_WAYBACK_TOOLBAR_RE = re.compile(
    r"<!--\s*BEGIN WAYBACK TOOLBAR INSERT\s*-->.*?<!--\s*END WAYBACK TOOLBAR INSERT\s*-->",
    re.S | re.I,
)
#: Ids of the toolbar's elements, for captures saved without its comment markers.
_WAYBACK_IDS = ("wm-ipp-base", "wm-ipp", "wm-ipp-print", "donato")


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
    """True if a class or the id of *tag* names chrome.

    State classes (``share-enabled``) and anything inside code (``hljs-comment``)
    never count.

    >>> from bs4 import BeautifulSoup as B
    >>> _is_chrome(B('<div class="post-nav"></div>', "html.parser").div)
    True
    >>> _is_chrome(B('<div class="post share-enabled"></div>', "html.parser").div)
    False
    >>> _is_chrome(B('<pre><span class="hljs-comment">#</span></pre>', "html.parser").span)
    False
    """
    if tag.name in ("html", "body", *CODE_TAGS) or tag.find_parent(CODE_TAGS):
        return False
    tokens = [*(tag.get("class") or []), tag.get("id") or ""]
    return any(
        DROP_CLASS_RE.search(t) for t in tokens if t and not STATE_CLASS_RE.search(t)
    )


def _is_chrome_name(tag) -> bool:
    """True if a class or the id of *tag* is, as a whole, a chrome word.

    >>> from bs4 import BeautifulSoup as B
    >>> _is_chrome_name(B('<div id="comments"></div>', "html.parser").div)
    True
    >>> _is_chrome_name(B('<div class="content-share"></div>', "html.parser").div)
    False
    """
    tokens = [*(tag.get("class") or []), tag.get("id") or ""]
    return any(CHROME_NAME_RE.fullmatch(t) for t in tokens if t)


def _is_logo(h1, *, site_names: Iterable[str] = ()) -> bool:
    """An ``<h1>`` that is one link to the site's home (or named like the site).

    A blog headline is often a permalink, ``<h1><a href="/post">Title</a></h1>``,
    and is not a logo.

    >>> from bs4 import BeautifulSoup as B
    >>> _is_logo(B('<h1><a href="https://joel.com/">Joel</a></h1>', "html.parser").h1)
    True
    >>> _is_logo(B('<h1><a href="/2020/a-post">A Post</a></h1>', "html.parser").h1)
    False
    """
    links = h1.find_all("a")
    if len(links) != 1 or _text_len(links[0]) != _text_len(h1):
        return False
    if _title_key(h1.get_text(" ")) in {_title_key(n) for n in site_names if n}:
        return True
    return urlparse(links[0].get("href") or "").path in ("", "/")


def _link_density(tag) -> float:
    text = _text_len(tag)
    return sum(_text_len(a) for a in tag.find_all("a")) / text if text else 0.0


_BREADCRUMB_SEP_RE = re.compile(r"\s*[>»›/|·]\s*")


def _is_breadcrumb(node) -> bool:
    """``Home > Talks > This Talk``: links joined by separators, the last may be plain.

    >>> from bs4 import BeautifulSoup as B
    >>> _is_breadcrumb(B('<p><a href="/">Home</a> > <a href="/t">Talks</a> > Mine</p>', "html.parser").p)
    True
    >>> _is_breadcrumb(B('<p>Read <a href="/">this</a> > that</p>', "html.parser").p)
    False
    >>> _is_breadcrumb(B('<p><a href="/gnu">GNU</a>/Linux is a family.</p>', "html.parser").p)
    False
    """
    crumbs = [c for c in _BREADCRUMB_SEP_RE.split(node.get_text(" ", strip=True)) if c]
    links = {a.get_text(" ", strip=True) for a in node.find_all("a")}
    return len(links) >= 2 and len(crumbs) >= 2 and all(c in links for c in crumbs[:-1])


#: Tags that end an open ``<p>`` in HTML5. ``html.parser`` does not know this,
#: so ``<p>a <p>b`` (paragraphs never closed, as on idlewords.com) comes out
#: as one paragraph nested in another, the whole page deep.
_P_CLOSERS = (
    "p", "div", "table", "ul", "ol", "dl", "pre", "blockquote", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "section", "article", "figure",
)  # fmt: skip


def _unnest_paragraphs(soup) -> None:
    """Close paragraphs the way an HTML5 parser would, in place.

    >>> from bs4 import BeautifulSoup as B
    >>> s = B("<div><p>a <p>b <p>c</div>", "html.parser")
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


#: Block kinds that may be trimmed as edge chrome. Lists are not: a list of
#: links at the end of an article is usually its references.
_EDGE_TRIMMABLE = ("p", "div", "table", "span", "font", "center")


def _is_edge_chrome(node) -> bool:
    """A breadcrumb, a row of links or a boxed promo at the article's edge.

    Only short blocks qualify, and only: a breadcrumb; an ad slot (its whole
    text is the label); a one-cell table holding a link (a boxed promo, like
    paulgraham.com's); or a row of two or more links, separated by punctuation
    only, maybe after a ``Label:``. A sentence with links in it, a data table, a
    single "see the paper" link and a reference list are content and stay.
    """
    if getattr(node, "name", None) not in _EDGE_TRIMMABLE:
        return False
    if _text_len(node) > EDGE_BLOCK_MAX_CHARS:
        return False
    if _is_breadcrumb(node) or _AD_SLOT_RE.fullmatch(node.get_text(" ", strip=True)):
        return True
    links = node.find_all("a")
    if node.name == "table":
        return bool(links) and len(node.find_all(("td", "th"))) == 1
    return len(links) >= 2 and _is_link_row(node)


#: Wrappers edge trimming may step into.
_EDGE_CONTAINERS = ("div", "section", "article", "main", "font", "center", "td")


#: What may stand between the links of a row of links: separators only.
_LINK_ROW_GLUE_RE = re.compile(r"[\s,;|·•/–—-]*")


def _is_link_row(node) -> bool:
    """Links separated by punctuation only, maybe after a ``Label:``.

    >>> from bs4 import BeautifulSoup as B
    >>> _is_link_row(B('<div>See more on: <a>Tennis</a>, <a>Federer</a></div>', "html.parser").div)
    True
    >>> _is_link_row(B('<p>A reply to <a>Joel</a> and <a>Paul</a>.</p>', "html.parser").p)
    False
    >>> _is_link_row(B('<p>Update: see <a>the post</a> and <a>the errata</a>.</p>', "html.parser").p)
    False
    """
    from bs4 import NavigableString

    texts, before_first_link = [], True
    for piece in node.descendants:
        if isinstance(piece, NavigableString) and piece.find_parent("a") is None:
            texts.append(("pre" if before_first_link else "mid", str(piece)))
        elif getattr(piece, "name", None) == "a":
            before_first_link = False
    label = "".join(t for kind, t in texts if kind == "pre").strip()
    glue = "".join(t for kind, t in texts if kind == "mid")
    return (not label or label.endswith(":")) and bool(
        _LINK_ROW_GLUE_RE.fullmatch(glue)
    )


def _trim_edges(tag, *, depth: int = EDGE_TRIM_DEPTH) -> None:
    """Drop chrome blocks from the start and the end of *tag*, in place.

    From each end, blocks are dropped while they are edge chrome (see
    :func:`_is_edge_chrome`); at the end, so is a heading with nothing after
    it ("Related Content" over an empty box). Empty elements are passed
    over. A heading counts only if it already closed the block: one whose
    section was just trimmed (``## Downloads`` over a promo) stays. The first
    block that is content stops the trimming on that side,
    except that a wrapper is stepped into, *depth* levels at most (and
    dropped, and passed, if that leaves it empty).
    """

    def trim(parent, from_end, depth):
        children, trimmed = list(parent.children), False
        for node in reversed(children) if from_end else children:
            if getattr(node, "name", None) is None:
                if str(node).strip():
                    return  # real text at the edge: stop
                continue
            if node.name in ("br", "img", "hr") or not _text_len(node):
                continue
            if _is_edge_chrome(node) or (
                from_end and not trimmed and re.fullmatch(r"h[1-6]", node.name)
            ):  # a heading closing the block, not one left by our own trimming
                node.decompose()
                trimmed = True
                continue
            if depth > 0 and node.name in _EDGE_CONTAINERS:
                trim(node, from_end, depth - 1)
                if not _text_len(node):  # it held nothing but edge chrome
                    node.decompose()
                    continue
            return

    for from_end in (False, True):
        trim(tag, from_end, depth)


def _is_prose(p) -> bool:
    return _text_len(p) >= PROSE_MIN_CHARS and _link_density(p) < EDGE_LINK_DENSITY


def _prose_siblings(tag) -> list:
    """Siblings of *tag* (same tag, same class) holding prose: the rest of the article.

    An article split into sections ends, often, on a short one (a conclusion)
    that scores too low to be chosen with the rest.

    >>> from bs4 import BeautifulSoup as B
    >>> s = B('<div><section><p>{}</p></section><div><p>{}</p></div>'
    ...       '<section><p>{}</p></section></div>'.format("a" * 90, "b" * 90, "c" * 90),
    ...       "html.parser")
    >>> [t.p.string[0] for t in _prose_siblings(s.section)]
    ['c']
    """
    if tag.parent is None or tag.name in ("body", "td"):
        return []
    return [
        sibling
        for sibling in tag.parent.find_all(tag.name, recursive=False)
        if sibling is not tag
        and sibling.name != "article"  # the next post on an index page
        and sibling.find("h1") is None
        and sibling.get("class") == tag.get("class")
        and not _is_chrome(sibling)
        and any(_is_prose(p) for p in sibling.find_all("p"))
    ]


def _headline(soup, title: Optional[str]):
    """The page's article headline: the ``<h1>`` naming its *title*, if one does.

    Otherwise the first ``<h1>`` that is not just a link (a site logo is
    ``<h1><a href="/">Site</a></h1>``), or ``None``.
    """
    h1s = soup.find_all("h1")
    key = _title_key(title or "")
    for h1 in h1s:
        if key and _title_key(h1.get_text(" ")) == key:
            return h1
    return next((h1 for h1 in h1s if not _is_logo(h1)), None)


def main_content(html: str) -> str:
    """The HTML of the block that most likely holds the article body.

    Drops chrome, picks the candidate block with the most paragraph text,
    adds same-kind sibling blocks holding prose (an article split into
    sections), trims breadcrumbs and promo boxes from their edges, and leads
    with the article's headline when the block left it behind.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    _unnest_paragraphs(soup)
    headline = _headline(soup, page_title(html))  # may sit in a dropped <header>
    title_html = str(headline) if headline is not None else ""
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    total = _text_len(soup) or 1
    for tag in soup.find_all(CHROME_IF_SMALL_TAGS):
        if _text_len(tag) <= MAX_CHROME_TEXT_SHARE * total:
            tag.decompose()
    for tag in [t for t in soup.find_all(True) if _is_chrome(t)]:
        if tag.decomposed:  # inside a subtree already dropped
            continue
        if _is_chrome_name(tag) or _text_len(tag) <= MAX_CHROME_TEXT_SHARE * total:
            tag.decompose()
    best, best_score = soup.body or soup, 0.0  # document order: ancestors first
    for el in soup.find_all(CANDIDATE_TAGS):
        score = _score(el)
        tighter = best in el.parents and score >= max(
            DESCENT_RATIO * best_score, best_score - MAX_DESCENT_LOSS
        )
        if score > best_score or tighter:
            best, best_score = el, score
    blocks = [best, *_prose_siblings(best)]
    if len(blocks) > 1:  # back in document order
        blocks.sort(key=best.parent.index)
    for block in blocks:
        _trim_edges(block)
    body = "".join(
        f"<div>{b.decode_contents()}</div>" if b.name == "td" else str(b)
        for b in blocks
    )  # a bare <td> would render as a table cell
    if title_html and not any(b.find("h1") for b in blocks):
        return f"{title_html}{body}"  # keep the headline the extraction left behind
    return body


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
    return (
        out or ""
    )  # nothing found: html_to_markdown falls back to the full page, as for every extractor


#: Named extractors, for the CLI and for ``content_extractor="name"``.
EXTRACTORS: Mapping[str, Extractor] = {
    "readability-lite": main_content,
    "trafilatura": trafilatura_extractor,
}

DEFAULT_EXTRACTOR = "readability-lite"


def unwayback_url(url: str) -> str:
    """Strip a Wayback prefix from *url*, giving back the original URL.

    >>> unwayback_url("https://web.archive.org/web/20150308214418/http://a.com/x")
    'http://a.com/x'
    >>> unwayback_url("/web/20150308214418im_/http://a.com/p.png")
    'http://a.com/p.png'
    >>> unwayback_url("//web.archive.org/web/2015/mailto:me@a.com")
    'mailto:me@a.com'
    >>> unwayback_url("http://a.com/x")
    'http://a.com/x'
    >>> unwayback_url("/web/2019/")  # a site's own /web/ section, not a capture
    '/web/2019/'
    """
    return WAYBACK_PREFIX_RE.sub("", url)


def clean_wayback(html: str) -> str:
    """Drop the Wayback Machine toolbar/banner and un-prefix archived links.

    >>> h = '<a href="https://web.archive.org/web/2020/http://x.org/a">a</a>'
    >>> clean_wayback(h)
    '<a href="http://x.org/a">a</a>'
    >>> clean_wayback('<div id="wm-ipp-base">Dec JAN Feb</div><a href="/web/2015/http://x.org/">x</a>')
    '<a href="http://x.org/">x</a>'
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_WAYBACK_TOOLBAR_RE.sub("", html), "html.parser")
    for wid in _WAYBACK_IDS:
        for tag in soup.find_all(id=wid):
            tag.decompose()
    for attr in ("href", "src"):
        for tag in soup.find_all(attrs={attr: True}):
            tag[attr] = unwayback_url(tag[attr])
    return _WAYBACK_TEXT_PREFIX_RE.sub("", str(soup))


def is_wayback_url(url: str) -> bool:
    return bool(re.match(r"https?://web\.archive\.org/web/", url or "", re.I))


def is_wayback_html(html: str) -> bool:
    """True if *html* is a Wayback capture (it carries the toolbar's markup).

    >>> is_wayback_html('<div id="wm-ipp-base"></div>')
    True
    >>> is_wayback_html('<code>&lt;div id="wm-ipp-base"&gt;</code>')
    False
    """
    return bool(_WAYBACK_MARKER_RE.search(html))


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

#: Separators between an article title and a site name in a page title.
TITLE_SEPARATORS = (" | ", " – ", " — ", " - ", " :: ", " · ", " : ")


def _title_key(text: str) -> str:
    return re.sub(r"\W+", " ", text or "").strip().lower()


def strip_site_name(
    title: str,
    *,
    site_names: Iterable[str] = (),
    article_titles: Iterable[str] = (),
    url: str = "",
) -> str:
    """The article's part of a ``Title – Site`` (or ``Site – Title``) title.

    Segments matching one of *site_names* (``og:site_name``, ``application-name``)
    go first. Of the rest, one matching one of *article_titles* (the page's
    ``<h1>``s, ``<title>``) wins, then one spelled out by the *url*'s path
    (``/reading-code-is-like-...``); otherwise the first segment is kept, which
    is the usual order. A title with no separator comes back as it is.

    >>> strip_site_name("Reading Code is Like Reading the Talmud – Joel on Software")
    'Reading Code is Like Reading the Talmud'
    >>> strip_site_name("Roger Federer as Religious Experience - Tennis - The New York Times")
    'Roger Federer as Religious Experience'
    >>> strip_site_name("Joel on Software - Fire and Motion", site_names=["Joel on Software"])
    'Fire and Motion'
    >>> strip_site_name("Hacker News | Show HN: A thing", article_titles=["Show HN: A thing"])
    'Show HN: A thing'
    >>> strip_site_name("Stack Overflow - How do I X", url="https://so.com/q/1/how-do-i-x")
    'How do I X'
    >>> strip_site_name("Beating the Averages")
    'Beating the Averages'
    >>> strip_site_name("Rust vs. Go - A Comparison", article_titles=["Rust vs. Go - A Comparison"])
    'Rust vs. Go - A Comparison'
    """
    title = " ".join(title.split())
    site_keys = {_title_key(n) for n in site_names if n}
    article_keys = {_title_key(t) for t in article_titles if t}
    if _title_key(title) in article_keys:
        return title  # the headline says it whole: "Rust vs. Go - A Comparison"
    path = _title_key(urlparse(url).path.replace("_", " "))
    for sep in TITLE_SEPARATORS:
        if sep not in title:
            continue
        parts = [part.strip() for part in title.split(sep) if part.strip()]
        parts = [p for p in parts if _title_key(p) not in site_keys] or parts
        for part in parts:
            if _title_key(part) in article_keys:
                return part
        for part in parts:
            if path and len(part.split()) >= 2 and _title_key(part) in path:
                return part
        if len(parts[0].split()) >= 2 or len(parts) == 1:
            return parts[0]  # "X - Site" where X is one word is ambiguous
    return title


def page_title(html: str, *, url: str = "") -> Optional[str]:
    """The page's own title: ``og:title``, ``<title>``, else the first ``<h1>``
    that is not a site logo.

    A site name joined to it (``Title – Site``) is removed, using the page's
    ``og:site_name``, its ``<h1>``s and the *url*'s path to tell which part is
    the site (see :func:`strip_site_name`).

    >>> page_title("<title>Hackers and Painters</title>")
    'Hackers and Painters'
    >>> page_title('<title>Fire and Motion – Joel on Software</title>')
    'Fire and Motion'
    >>> page_title("<p>no title here</p>") is None
    True
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    def meta(**attrs):
        tag = soup.find("meta", attrs=attrs)
        return " ".join((tag.get("content") or "").split()) if tag else ""

    def text(tag):
        return " ".join(tag.get_text(" ").split()) if tag else ""

    site_names = [meta(property="og:site_name"), meta(name="application-name")]
    h1s = [
        text(h) for h in soup.find_all("h1") if not _is_logo(h, site_names=site_names)
    ]
    candidates = [meta(property="og:title"), text(soup.title), *h1s[:1]]
    for title in candidates:
        if title:
            # Evidence for which part is the article: the other candidates,
            # and every headline (one equal to *title* confirms it whole).
            others = [c for c in candidates if c and c != title] + h1s
            return strip_site_name(
                title, site_names=site_names, article_titles=others, url=url
            )
    return None


# ---------------------------------------------------------------------------
# Layout tables
# ---------------------------------------------------------------------------

_TABLE_PARTS = ("table", "thead", "tbody", "tfoot", "tr", "td", "th")


#: Cell content that is prose, not data: a grid with these in a cell is layout.
_BLOCK_PROSE_TAGS = ("p", "h1", "h2", "h3", "ul", "ol", "blockquote")


def _is_layout_table(table) -> bool:
    """A table used for page layout, not data.

    One that nests another table is layout; one with header cells is data.
    Otherwise it is layout when a cell holds block prose (paragraphs,
    headings, lists, quotes, as on idlewords.com, an image beside each
    paragraph) or more than a short phrase; a single row or column whose
    cell has line breaks is layout too. A line break in a grid's cell is data.
    """
    if table.find("table"):
        return True
    if table.find(("th", "thead")):
        return False
    rows = [r for r in table.find_all("tr") if r.find_parent("table") is table]
    grid = (
        len(rows) >= 2
        and max(
            (len(r.find_all(("td", "th"), recursive=False)) for r in rows), default=0
        )
        >= 2
    )
    prose_tags = _BLOCK_PROSE_TAGS if grid else (*_BLOCK_PROSE_TAGS, "br")
    return any(
        cell.find(prose_tags) or _text_len(cell) > LAYOUT_CELL_MIN_CHARS
        for cell in table.find_all(("td", "th"))
    )


def unwrap_layout_tables(html: str) -> str:
    """Rewrite tables used for page layout as plain ``<div>`` blocks.

    A table is *layout* when it nests another table, or when its cells hold
    prose (see :func:`_is_layout_table`). Data tables, header cells or a grid
    of short values, are left intact, so they still become Markdown tables.

    >>> unwrap_layout_tables("<table><tr><td><p>An essay.</p></td></tr></table>")
    '<div><div><div><p>An essay.</p></div></div></div>'
    >>> unwrap_layout_tables("<table><tr><td>1</td></tr></table>")
    '<table><tr><td>1</td></tr></table>'
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
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
    return str(soup)


#: Lines of converted Markdown that carry no content (table scaffolding, rules, empty bullets).
_JUNK_LINE_RE = re.compile(r"^[\s|\-_*=:]*$")


def drop_junk_lines(markdown: str) -> str:
    """Remove rule-only / empty-bullet lines and unwrap one-cell table rows.

    Fenced code blocks are left alone. Blank lines are kept (they separate paragraphs).
    A thematic break (``***``, ``---``, ``* * *``) standing alone between two paragraphs is a
    scene break, and is kept.

    >>> drop_junk_lines("| hello |\\n| --- |\\n* \\n\\ntext")
    'hello\\n\\ntext'
    >>> drop_junk_lines("one\\n\\n***\\n\\ntwo")
    'one\\n\\n***\\n\\ntwo'
    """
    out, in_fence = [], False
    lines = markdown.split("\n")
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and line.strip():
            if _JUNK_LINE_RE.match(line):
                if not _is_scene_break(lines, i):
                    continue
                out.append(line)
                continue
            s = line.strip()
            if s.startswith("|") and s.endswith("|") and s.count("|") == 2:
                line = s.strip("|").strip()
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


_THEMATIC_BREAK_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")


def _is_scene_break(lines: list[str], i: int) -> bool:
    """A thematic break with a blank line, then prose, on both sides."""
    if not _THEMATIC_BREAK_RE.match(lines[i]):
        return False

    def prose(j: int) -> bool:
        return (
            0 <= j < len(lines)
            and lines[j].strip() != ""
            and not _JUNK_LINE_RE.match(lines[j])
        )

    blank = lambda j: 0 <= j < len(lines) and not lines[j].strip()
    return blank(i - 1) and blank(i + 1) and prose(i - 2) and prose(i + 2)
