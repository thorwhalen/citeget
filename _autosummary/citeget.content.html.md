# citeget.content

Main-article extraction: strip site chrome from HTML before it becomes Markdown.

The default extractor, [`main_content()`](#citeget.content.main_content), is a “readability-lite” scorer built
on `beautifulsoup4` (already a dependency): it drops navigation-like elements,
then picks the block with the most paragraph text. Any callable `html -> html`
can replace it (the *extractor* seam); [`trafilatura_extractor()`](#citeget.content.trafilatura_extractor) is an
optional, stronger one (Apache-2.0, `pip install trafilatura`).

Web Archive copies are cleaned by [`clean_wayback()`](#citeget.content.clean_wayback): the toolbar/banner is
dropped and `web.archive.org/web/<ts>/` link prefixes (absolute, relative or
protocol-relative) are rewritten back to the original URLs. This applies in
every content mode, `full` included.

Also here, because the extractor needs them: [`page_title()`](#citeget.content.page_title) (the page’s
title, with a `Title – Site` site name removed by [`strip_site_name()`](#citeget.content.strip_site_name))
and [`unwrap_layout_tables()`](#citeget.content.unwrap_layout_tables) (tables used for page layout become plain
blocks; data tables are left alone).

```pycon
>>> html = "<body><nav>Menu</nav><div><p>" + "Real text. " * 20 + "</p></div></body>"
>>> "Menu" in main_content(html), "Real text." in main_content(html)
(False, True)
```

### Module Attributes

| [`DROP_TAGS`](#citeget.content.DROP_TAGS)             | Elements that are never article content.                                                                                                                                                      |
|------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DROP_CLASS_RE`](#citeget.content.DROP_CLASS_RE)         | Class/id fragments that mark chrome.                                                                                                                                                          |
| [`CHROME_NAME_RE`](#citeget.content.CHROME_NAME_RE)        | chrome however much of the page it holds, unlike a value merely containing one (`content-share`), which the share guard below may keep as a wrapper.                                          |
| [`STATE_CLASS_RE`](#citeget.content.STATE_CLASS_RE)        | A class saying what something *has*, *allows* or *is* (`has-sidebar`, `share-enabled`, `with-comments`, `no-ads`): usually on the article's own wrapper, so never a reason to call it chrome. |
| [`CODE_TAGS`](#citeget.content.CODE_TAGS)             | Inside these, class names describe syntax (`hljs-comment`, `token comment`), not page chrome.                                                                                                 |
| [`CHROME_IF_SMALL_TAGS`](#citeget.content.CHROME_IF_SMALL_TAGS)  | an ASP.NET page wraps its whole body in one `<form>`, which is a layout wrapper then.                                                                                                         |
| [`CANDIDATE_TAGS`](#citeget.content.CANDIDATE_TAGS)        | Tags considered as candidate containers for the article.                                                                                                                                      |
| [`LINK_PENALTY`](#citeget.content.LINK_PENALTY)          | Weight of link text subtracted from a candidate's score (menus are all links).                                                                                                                |
| [`NO_PARAGRAPH_FACTOR`](#citeget.content.NO_PARAGRAPH_FACTOR)   | Pages without `<p>` (e.g. `<br><br>` separated) score by raw text times this.                                                                                                                 |
| [`DESCENT_RATIO`](#citeget.content.DESCENT_RATIO)         | A descendant of the current best wins if it keeps this share of its score (the tighter container, with less surrounding chrome).                                                              |
| [`MAX_DESCENT_LOSS`](#citeget.content.MAX_DESCENT_LOSS)      | ...but never by shedding more than this many characters of paragraph text: on a long page 10% can be a whole intro, which belongs to the article.                                             |
| [`MAX_CHROME_TEXT_SHARE`](#citeget.content.MAX_CHROME_TEXT_SHARE) | A chrome-looking node holding more than this share of the page's text is a layout wrapper (`no-sidebar`, `content-share`), not chrome: keep it.                                               |
| [`MIN_MAIN_CHARS`](#citeget.content.MIN_MAIN_CHARS)        | Main-mode Markdown shorter than this (characters) is distrusted and the full page is converted instead (see `html_to_markdown`).                                                              |
| [`EDGE_BLOCK_MAX_CHARS`](#citeget.content.EDGE_BLOCK_MAX_CHARS)  | breadcrumbs and promo boxes are short (characters) and mostly links (share of the block's text).                                                                                              |
| [`EDGE_TRIM_DEPTH`](#citeget.content.EDGE_TRIM_DEPTH)       | the ad slot closing an article often sits in the article's last box, not directly in it.                                                                                                      |
| [`PROSE_MIN_CHARS`](#citeget.content.PROSE_MIN_CHARS)       | a same-kind sibling of the chosen block holding one is the rest of the article.                                                                                                               |
| [`LAYOUT_CELL_MIN_CHARS`](#citeget.content.LAYOUT_CELL_MIN_CHARS) | A table cell holding more text than this (characters) holds prose, so the table is page layout, not data.                                                                                     |
| [`WAYBACK_PREFIX_RE`](#citeget.content.WAYBACK_PREFIX_RE)     | `https://web.archive.org/web/20150308214418im_/`, its protocol-relative form and the relative `/web/20150308214418/` Wayback rewrites links into.                                             |
| [`EXTRACTORS`](#citeget.content.EXTRACTORS)            | Named extractors, for the CLI and for `content_extractor="name"`.                                                                                                                             |
| [`TITLE_SEPARATORS`](#citeget.content.TITLE_SEPARATORS)      | Separators between an article title and a site name in a page title.                                                                                                                          |

### Functions

| [`clean_wayback`](#citeget.content.clean_wayback)(html)                           | Drop the Wayback Machine toolbar/banner and un-prefix archived links.                       |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`drop_junk_lines`](#citeget.content.drop_junk_lines)(markdown)                     | Remove rule-only / empty-bullet lines and unwrap one-cell table rows.                       |
| [`is_wayback_html`](#citeget.content.is_wayback_html)(html)                         | True if *html* is a Wayback capture (it carries the toolbar's markup).                      |
| `is_wayback_url`(url)                                                                          |                                                                                             |
| [`main_content`](#citeget.content.main_content)(html)                            | The HTML of the block that most likely holds the article body.                              |
| [`page_title`](#citeget.content.page_title)(html, \*[, url])                   | The page's own title: `og:title`, `<title>`, else the first `<h1>` that is not a site logo. |
| [`strip_site_name`](#citeget.content.strip_site_name)(title, \*[, site_names, ...]) | The article's part of a `Title – Site` (or `Site – Title`) title.                           |
| [`trafilatura_extractor`](#citeget.content.trafilatura_extractor)(html)                   | Extractor backed by `trafilatura` (optional dependency, Apache-2.0).                        |
| [`unwayback_url`](#citeget.content.unwayback_url)(url)                            | Strip a Wayback prefix from *url*, giving back the original URL.                            |
| [`unwrap_layout_tables`](#citeget.content.unwrap_layout_tables)(html)                    | Rewrite tables used for page layout as plain `<div>` blocks.                                |

### citeget.content.CANDIDATE_TAGS *= ('article', 'main', 'div', 'td', 'section', 'font', 'body')*

Tags considered as candidate containers for the article.

### citeget.content.CHROME_IF_SMALL_TAGS *= ('form',)*

an ASP.NET
page wraps its whole body in one `<form>`, which is a layout wrapper then.

* **Type:**
  Elements dropped as chrome only when they hold little of the page

### citeget.content.CHROME_NAME_RE *= re.compile('(comments?|share|sharing|related|sidebar|newsletter|subscribe|subscription|footer|nav|navbar|menu|author-bio|byline|cookie|breadcrumbs?|skip-link|post-navigation)', re.IGNORECASE)*

chrome however
much of the page it holds, unlike a value merely containing one
(`content-share`), which the share guard below may keep as a wrapper.

* **Type:**
  A class/id value that *is* a chrome word (`id="comments"`)

### citeget.content.CODE_TAGS *= ('pre', 'code')*

Inside these, class names describe syntax (`hljs-comment`,
`token comment`), not page chrome.

### citeget.content.DESCENT_RATIO *= 0.9*

A descendant of the current best wins if it keeps this share of its score
(the tighter container, with less surrounding chrome).

### citeget.content.DROP_CLASS_RE *= re.compile('(^|[-_ ])(comments?|share|sharing|related|sidebar|newsletter|subscribe|subscription|footer|nav|navbar|menu|author-bio|byline|cookie|breadcrumbs?|skip-link|post-navigation)([-_ ]|$)', re.IGNORECASE)*

Class/id fragments that mark chrome. Matched against single class/id tokens.

### citeget.content.DROP_TAGS *= ('script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript', 'iframe', 'template', 'button', 'svg', 'dialog')*

Elements that are never article content.

### citeget.content.EDGE_BLOCK_MAX_CHARS *= 200*

breadcrumbs and promo boxes are
short (characters) and mostly links (share of the block’s text).

* **Type:**
  Trimming the edges of the chosen block

### citeget.content.EDGE_TRIM_DEPTH *= 3*

the ad slot
closing an article often sits in the article’s last box, not directly in it.

* **Type:**
  How many levels of nested wrappers edge trimming steps into

### citeget.content.EXTRACTORS *: [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[[[str](https://docs.python.org/3/builtins/stdtypes.html#str)], [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]* *= {'readability-lite': <function main_content>, 'trafilatura': <function trafilatura_extractor>}*

Named extractors, for the CLI and for `content_extractor="name"`.

### citeget.content.LAYOUT_CELL_MIN_CHARS *= 200*

A table cell holding more text than this (characters) holds prose, so the
table is page layout, not data.

### citeget.content.LINK_PENALTY *= 0.3*

Weight of link text subtracted from a candidate’s score (menus are all links).

### citeget.content.MAX_CHROME_TEXT_SHARE *= 0.5*

A chrome-looking node holding more than this share of the page’s text is a
layout wrapper (`no-sidebar`, `content-share`), not chrome: keep it.

### citeget.content.MAX_DESCENT_LOSS *= 500*

…but never by shedding more than this many characters of paragraph text:
on a long page 10% can be a whole intro, which belongs to the article.

### citeget.content.MIN_MAIN_CHARS *= 200*

Main-mode Markdown shorter than this (characters) is distrusted and the
full page is converted instead (see `html_to_markdown`).

### citeget.content.NO_PARAGRAPH_FACTOR *= 0.9*

Pages without `<p>` (e.g. `<br><br>` separated) score by raw text times this.

### citeget.content.PROSE_MIN_CHARS *= 80*

a
same-kind sibling of the chosen block holding one is the rest of the article.

* **Type:**
  A paragraph this long (characters), and not mostly links, is prose

### citeget.content.STATE_CLASS_RE *= re.compile('^(?:has|with|no|is|show|hide|allow)[-_]|[-_](?:enabled|disabled|active|open|visible|hidden|on|off)$', re.IGNORECASE)*

A class saying what something *has*, *allows* or *is* (`has-sidebar`,
`share-enabled`, `with-comments`, `no-ads`): usually on the article’s
own wrapper, so never a reason to call it chrome.

### citeget.content.TITLE_SEPARATORS *= (' | ', ' – ', ' — ', ' - ', ' :: ', ' · ', ' : ')*

Separators between an article title and a site name in a page title.

### citeget.content.WAYBACK_PREFIX_RE *= re.compile('^(?:(?:https?:)?//web\\\\.archive\\\\.org)?/web/\\\\d{1,14}(?:[a-z]{2}_)?/(?=https?:|//|mailto:)', re.IGNORECASE)*

`https://web.archive.org/web/20150308214418im_/`, its protocol-relative
form and the relative `/web/20150308214418/` Wayback rewrites links into.

### citeget.content.clean_wayback(html)

Drop the Wayback Machine toolbar/banner and un-prefix archived links.

```pycon
>>> h = '<a href="https://web.archive.org/web/2020/http://x.org/a">a</a>'
>>> clean_wayback(h)
'<a href="http://x.org/a">a</a>'
>>> clean_wayback('<div id="wm-ipp-base">Dec JAN Feb</div><a href="/web/2015/http://x.org/">x</a>')
'<a href="http://x.org/">x</a>'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.drop_junk_lines(markdown)

Remove rule-only / empty-bullet lines and unwrap one-cell table rows.

Fenced code blocks are left alone. Blank lines are kept (they separate paragraphs).
A thematic break (`***`, `---`, `* * *`) standing alone between two paragraphs is a
scene break, and is kept.

```pycon
>>> drop_junk_lines("| hello |\n| --- |\n* \n\ntext")
'hello\n\ntext'
>>> drop_junk_lines("one\n\n***\n\ntwo")
'one\n\n***\n\ntwo'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.is_wayback_html(html)

True if *html* is a Wayback capture (it carries the toolbar’s markup).

```pycon
>>> is_wayback_html('<div id="wm-ipp-base"></div>')
True
>>> is_wayback_html('<code>&lt;div id="wm-ipp-base"&gt;</code>')
False
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### citeget.content.main_content(html)

The HTML of the block that most likely holds the article body.

Drops chrome, picks the candidate block with the most paragraph text,
adds same-kind sibling blocks holding prose (an article split into
sections), trims breadcrumbs and promo boxes from their edges, and leads
with the article’s headline when the block left it behind.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.page_title(html, , url='')

The page’s own title: `og:title`, `<title>`, else the first `<h1>`
that is not a site logo.

A site name joined to it (`Title – Site`) is removed, using the page’s
`og:site_name`, its 

```
``
```

<h1>\`\`s and the *url*’s path to tell which part is
the site (see [`strip_site_name()`](#citeget.content.strip_site_name)).

```pycon
>>> page_title("<title>Hackers and Painters</title>")
'Hackers and Painters'
>>> page_title('<title>Fire and Motion – Joel on Software</title>')
'Fire and Motion'
>>> page_title("<p>no title here</p>") is None
True
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.content.strip_site_name(title, , site_names=(), article_titles=(), url='')

The article’s part of a `Title – Site` (or `Site – Title`) title.

Segments matching one of *site_names* (`og:site_name`, `application-name`)
go first. Of the rest, one matching one of *article_titles* (the page’s
`<h1>``s, ``<title>`) wins, then one spelled out by the *url*’s path
(`/reading-code-is-like-...`); otherwise the first segment is kept, which
is the usual order. A title with no separator comes back as it is.

```pycon
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
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.trafilatura_extractor(html)

Extractor backed by `trafilatura` (optional dependency, Apache-2.0).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.unwayback_url(url)

Strip a Wayback prefix from *url*, giving back the original URL.

```pycon
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
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.unwrap_layout_tables(html)

Rewrite tables used for page layout as plain `<div>` blocks.

A table is *layout* when it nests another table, or when its cells hold
prose (see `_is_layout_table()`). Data tables, header cells or a grid
of short values, are left intact, so they still become Markdown tables.

```pycon
>>> unwrap_layout_tables("<table><tr><td><p>An essay.</p></td></tr></table>")
'<div><div><div><p>An essay.</p></div></div></div>'
>>> unwrap_layout_tables("<table><tr><td>1</td></tr></table>")
'<table><tr><td>1</td></tr></table>'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
