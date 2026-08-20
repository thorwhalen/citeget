---
name: get-books
description: Acquire one copy of each book in a list of titles. Ranks libgen results against the requested title and author, validates that what arrives is the complete book rather than an excerpt or a landing page, and falls through to the next candidate when it isn't. Use for "get me these books", a reading list, a bibliography of books, or any list of titles — as opposed to a document with a references section (use /acquire-references) or a list of web URLs (use /fetch-resources).
argument-hint: <book title> [author] | <path to a list of titles>
allowed-tools: Bash, Read, Write, Grep, Glob
---

# Get Books

Acquire one copy of each book the user asks for.

## Which skill is this?

| The user gives you | Use |
|---|---|
| A list of book titles, a reading list, "get me these books" | **this skill** |
| A document with a references section to work through | `/acquire-references` |
| A list of web URLs (blogs, docs, product pages) | `/fetch-resources` |

The distinction that matters: this skill knows *what book you asked for*, so it
can check that what arrived is that book. The others cannot.

## The one call

```python
from citeget import get_book

path = get_book("Crossing the Chasm", authors="Geoffrey A. Moore",
                download_dir="~/books")
```

Or `citeget get-book "Crossing the Chasm" --authors "Geoffrey A. Moore"`.

`get_book` searches, ranks every result against the title and author you gave,
downloads the best candidate, checks it is a complete book, and moves to the
next candidate if it is not. It returns the path, or `None`.

**Always pass `authors` when you know it.** Libgen titles are noisy and the
author field is the strongest disambiguating signal available.

## Do not use `search_and_download` for this

`search_and_download(query, max_downloads=5)` downloads the first five rows of
the results table. For a book search those rows are usually **the same book in
five file formats**, and libgen's own ordering puts summaries and download-spam
listings above the real book often enough to matter. That function is for
"give me whatever matches this query", not "get me this book".

## Batch

```python
from citeget import get_book

BOOKS = [
    ("Crossing the Chasm", "Geoffrey A. Moore"),
    ("The Mom Test", "Rob Fitzpatrick"),
    ("A Prehistory of the Cloud", "Tung-Hui Hu"),
]

got, missed = [], []
for title, authors in BOOKS:
    path = get_book(title, authors=authors, download_dir=work_dir, verbose=True)
    (got if path else missed).append((title, path))
```

Report both lists to the user. Do not quietly drop the misses.

Rate limiting: `get_book` already sleeps between page loads (`delay=1.0`).
Don't drive it in parallel and don't lower the delay.

## An empty search result is weak evidence

**This is the failure mode most likely to make you tell the user something
false.** Libgen returns a blank result set for a query that has real matches
often enough to matter — in measured repeats of one query, roughly one run in
four came back with nothing, and the same query returned 0 results and then 21
a minute apart.

`search()` already retries each mirror and requires two mirrors to agree before
returning `[]`, and `get_book` re-runs the whole search once more on top of
that. Even so:

- **Never report "this book is not on libgen" from one empty run.** Say the
  search came back empty and offer to try again, or re-run once yourself.
- Result *counts* vary legitimately too — the same query returns 21 or 9
  depending on which mirror answers. A smaller-than-expected count is not a
  problem to report.
- If *many* books in a batch come back empty, the mirror list is the suspect,
  not the books. Run `citeget check-mirrors` (below) before concluding anything.

## When it returns None

`None` means "no candidate produced a usable file", which is not the same as
"this book does not exist". In order of likelihood:

1. **Spurious empty search** — see above. Re-run.
2. **Every candidate failed validation** — real, but it means citeget protected
   the user from a wrong file. Say so; don't silently retry with validation off.
3. **A slow or broken mirror** — check with `check-mirrors`.
4. **The query is off** — pass `query=` explicitly. A subtitle or an edition
   number in the title can push the real book down the ranking. Try the bare
   title plus the author's surname.

```python
get_book("The Design of Everyday Things", authors="Donald A. Norman",
         query="Design of Everyday Things Norman")   # override the search string
```

## What "validated" means, and when to relax it

`get_book` uses `BOOK_POLICY`: magic bytes matching the extension, no HTML
bodies, a size floor, a truncation check against the size libgen advertised,
and — the part that catches the subtle cases — a **page-count check**.

That last one exists because libgen catalogues excerpts, front-matter samples
and reviews under the full work's title. Files that pass every byte-level check
and are still not the book:

| requested | what libgen served |
|---|---|
| *The Visual Display of Quantitative Information* (~200 pp) | 17 pages, 5.9 MB, valid PDF, top-ranked result |
| *Visual Explanations* (~156 pp) | 2 pages — a journal review *of* the book |
| *A Prehistory of the Cloud* (~208 pp) | 33 pages — front matter |

Falling through to the next candidate recovered the real book in every case.

`BOOK_POLICY` assumes a **book**. If the user's list is actually papers or
short works, the 80-page floor will reject legitimate files — pass a looser
policy rather than turning validation off:

```python
from dataclasses import replace
from citeget import get_book, BOOK_POLICY, DEFAULT_POLICY

get_book(title, policy=replace(BOOK_POLICY, min_pages=30))  # short works
get_book(title, policy=DEFAULT_POLICY)                      # integrity only
```

`validate=False` disables checking entirely. Don't reach for it to make a
stubborn book "work" — you will hand the user an excerpt or an HTML page and
report success. If you use it, tell the user you did.

## Verify before reporting success

A path is not proof. Cheap, no extra network:

```python
from citeget.validate import pdf_page_count, epub_markup_bytes

pdf_page_count(path)        # None if not a readable PDF
epub_markup_bytes(path)     # total xhtml/html bytes inside the epub
```

Reporting page counts alongside filenames is the single most useful thing you
can give the user, because it is what distinguishes a book from an excerpt.

## Preferences worth passing on

```python
get_book(title, authors=authors,
         format_preference=("epub", "pdf"),   # e-reader workflow
         max_candidates=8,                    # try harder before giving up
         topic="fiction")                     # novels
```

`topic` defaults to `"books"`. Use `"fiction"` for novels and `"articles"` for
papers — or ask for several at once via the lower-level `search(topics=...)`.

## Checking mirrors

Mirror domains rotate, so the shipped default list goes stale on its own
schedule. When searches start failing across the board:

```bash
citeget check-mirrors
```

It prints a health table and a ready-to-use override:

```
  status  mirror                        hits     time  detail
  OK      https://libgen.vg               25   10523ms
  OK      https://libgen.la               25    1932ms
  ...
Working mirrors — use them without editing code:
  export CITEGET_LIBGEN_MIRRORS='https://libgen.vg,https://libgen.la,...'
```

If *nothing* is healthy, tell the user the mirror list needs updating — that is
an actionable diagnosis, unlike "citeget is broken".

## Filenames

`{title} ({authors_apa7}, {year}).{ext}`, e.g.
`Crossing the Chasm Revised edition (Moore, 1991).pdf`.

The author part comes from libgen's own metadata, which uses several
incompatible conventions (`"Moore, Geoffrey A."`, `"Moore G.A."`,
`"Brian Christian, Tom Griffiths"`). These are handled, but the *title* is
libgen's, not the user's — so a file may be named after an edition-specific
title. Don't be surprised, and don't rename without asking.

## Tips

- **Existing files are re-validated, not just detected.** A file left by an
  earlier failed attempt is discarded and re-downloaded automatically. There is
  no need to tell the user to delete anything first.
- **Different editions are different books.** `get_book("Crossing the Chasm")`
  scores an exact title match above a subtitled one, so it may pick the revised
  edition over the 3rd. If the user wants a specific edition, put it in the
  title or pass `query=`.
- **Don't parallelise.** Libgen rate-limits, and the flakiness above gets worse
  under load.
