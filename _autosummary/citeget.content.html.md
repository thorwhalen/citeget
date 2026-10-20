# citeget.content

Main-article extraction: strip site chrome from HTML before it becomes Markdown.

The default extractor, [`main_content()`](#citeget.content.main_content), is a “readability-lite” scorer built
on `beautifulsoup4` (already a dependency): it drops navigation-like elements,
then picks the block with the most paragraph text. Any callable `html -> html`
can replace it (the *extractor* seam); [`trafilatura_extractor()`](#citeget.content.trafilatura_extractor) is an
optional, stronger one (Apache-2.0, `pip install trafilatura`).

Web Archive copies are cleaned by [`clean_wayback()`](#citeget.content.clean_wayback): the toolbar/banner is
dropped and `web.archive.org/web/<ts>/` link prefixes are rewritten back to
the original URLs.

```pycon
>>> html = "<body><nav>Menu</nav><div><p>" + "Real text. " * 20 + "</p></div></body>"
>>> "Menu" in main_content(html), "Real text." in main_content(html)
(False, True)
```

### Module Attributes

| [`DROP_TAGS`](#citeget.content.DROP_TAGS)             | Elements that are never article content.                                                                                                        |
|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DROP_CLASS_RE`](#citeget.content.DROP_CLASS_RE)         | Class/id fragments that mark chrome.                                                                                                            |
| [`CANDIDATE_TAGS`](#citeget.content.CANDIDATE_TAGS)        | Tags considered as candidate containers for the article.                                                                                        |
| [`LINK_PENALTY`](#citeget.content.LINK_PENALTY)          | Weight of link text subtracted from a candidate's score (menus are all links).                                                                  |
| [`NO_PARAGRAPH_FACTOR`](#citeget.content.NO_PARAGRAPH_FACTOR)   | Pages without `<p>` (e.g. `<br><br>` separated) score by raw text times this.                                                                   |
| [`DESCENT_RATIO`](#citeget.content.DESCENT_RATIO)         | A descendant of the current best wins if it keeps this share of its score (the tighter container, with less surrounding chrome).                |
| [`MAX_CHROME_TEXT_SHARE`](#citeget.content.MAX_CHROME_TEXT_SHARE) | A chrome-looking node holding more than this share of the page's text is a layout wrapper (`no-sidebar`, `content-share`), not chrome: keep it. |
| [`MIN_MAIN_CHARS`](#citeget.content.MIN_MAIN_CHARS)        | Main-mode Markdown shorter than this (characters) is distrusted and the full page is converted instead (see `html_to_markdown`).                |
| [`EXTRACTORS`](#citeget.content.EXTRACTORS)            | Named extractors, for the CLI and for `content_extractor="name"`.                                                                               |

### Functions

| [`clean_wayback`](#citeget.content.clean_wayback)(html)         | Drop the Wayback Machine toolbar/banner and un-prefix archived links.   |
|------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`drop_junk_lines`](#citeget.content.drop_junk_lines)(markdown)   | Remove rule-only / empty-bullet lines and unwrap one-cell table rows.   |
| `is_wayback_url`(url)                                                        |                                                                         |
| [`main_content`](#citeget.content.main_content)(html)          | The HTML of the block that most likely holds the article body.          |
| [`trafilatura_extractor`](#citeget.content.trafilatura_extractor)(html) | Extractor backed by `trafilatura` (optional dependency, Apache-2.0).    |

### citeget.content.CANDIDATE_TAGS *= ('article', 'main', 'div', 'td', 'section', 'font', 'body')*

Tags considered as candidate containers for the article.

### citeget.content.DESCENT_RATIO *= 0.9*

A descendant of the current best wins if it keeps this share of its score
(the tighter container, with less surrounding chrome).

### citeget.content.DROP_CLASS_RE *= re.compile('(^|[-_ ])(comments?|share|sharing|related|sidebar|newsletter|subscribe|subscription|footer|nav|navbar|menu|author-bio|byline|cookie|breadcrumbs?|skip-link|post-navigation)([-_ ]|$)', re.IGNORECASE)*

Class/id fragments that mark chrome. Matched against single class/id tokens.

### citeget.content.DROP_TAGS *= ('script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'iframe')*

Elements that are never article content.

### citeget.content.EXTRACTORS *: [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[[[str](https://docs.python.org/3/builtins/stdtypes.html#str)], [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]* *= {'readability-lite': <function main_content>, 'trafilatura': <function trafilatura_extractor>}*

Named extractors, for the CLI and for `content_extractor="name"`.

### citeget.content.LINK_PENALTY *= 0.3*

Weight of link text subtracted from a candidate’s score (menus are all links).

### citeget.content.MAX_CHROME_TEXT_SHARE *= 0.5*

A chrome-looking node holding more than this share of the page’s text is a
layout wrapper (`no-sidebar`, `content-share`), not chrome: keep it.

### citeget.content.MIN_MAIN_CHARS *= 200*

Main-mode Markdown shorter than this (characters) is distrusted and the
full page is converted instead (see `html_to_markdown`).

### citeget.content.NO_PARAGRAPH_FACTOR *= 0.9*

Pages without `<p>` (e.g. `<br><br>` separated) score by raw text times this.

### citeget.content.clean_wayback(html)

Drop the Wayback Machine toolbar/banner and un-prefix archived links.

```pycon
>>> h = '<a href="https://web.archive.org/web/2020/http://x.org/a">a</a>'
>>> clean_wayback(h)
'<a href="http://x.org/a">a</a>'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.drop_junk_lines(markdown)

Remove rule-only / empty-bullet lines and unwrap one-cell table rows.

Fenced code blocks are left alone. Blank lines are kept (they separate paragraphs).

```pycon
>>> drop_junk_lines("| hello |\n| --- |\n* \n\ntext")
'hello\n\ntext'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.main_content(html)

The HTML of the block that most likely holds the article body.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.content.trafilatura_extractor(html)

Extractor backed by `trafilatura` (optional dependency, Apache-2.0).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
