# citeget.rank

Rank libgen search results against a requested title and author.

`search()` returns whatever libgen’s relevance ordering produced, which for a
known title is typically the same book repeated in several formats, interleaved
with derivative works (summaries, workbooks) and download-spam listings. This
module scores each result against what the caller actually asked for, so a
caller can take the best match rather than the first row.

Simple case:

```default
from citeget import search
from citeget.rank import rank_results

results = search("Introduction to Algorithms Cormen")
best = rank_results(results, title="Introduction to Algorithms",
                    authors="Thomas H. Cormen")[0]
```

Everything about the scoring is overridable without editing this module: pass
`weights`, `format_preference`, `language`, or `decoy_pattern`.

Scoring uses only fields already present in a `search()` result dict, so
ranking costs no extra requests.

Two independent guards keep non-books from winning:

- a **decoy pattern** over the title (`summary`, `workbook`, `gratis`, …),
  catching derivative works and download-spam landing pages, and
- a **stub check** — a PDF under a few hundred kB is a landing page, not a scan.
  This floor is much higher than the general one, because a short EPUB of a real
  book is legitimately ~100 kB; one shared floor gets one of those two wrong.

Both are penalties rather than filters, so a decoy can still surface when it is
genuinely the only thing available — it just never outranks a real match.

Based on the ranking contributed in
[https://github.com/thorwhalen/citeget/issues/7](https://github.com/thorwhalen/citeget/issues/7).

### Functions

| [`score_result`](#citeget.rank.score_result)(result, \*, title[, authors, ...])   | Score one `search()` result against a requested title and author.                                            |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| [`rank_results`](#citeget.rank.rank_results)(results, \*, title[, authors])       | Return `results` as [`ScoredResult`](#citeget.rank.ScoredResult) objects, best match first. |
| [`dedupe_results`](#citeget.rank.dedupe_results)(results, \*[, key])                | Keep only the first result for each distinct work, preserving order.                                         |
| [`dedupe_key`](#citeget.rank.dedupe_key)(result)                                | Identity of the *work* behind a result, ignoring which format it is in.                                      |
| [`parse_size`](#citeget.rank.parse_size)(size_text)                             | Bytes from a libgen size string such as `'2 MB'`; 0 if unparseable.                                          |
| [`candidate_surnames`](#citeget.rank.candidate_surnames)(authors)                       | Normalized surnames usable for matching, in either name ordering.                                            |

### Classes

| [`ScoreWeights`](#citeget.rank.ScoreWeights)([title, author, format, ...])    | Relative contribution of each signal to the total score.           |
|------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`SizeBounds`](#citeget.rank.SizeBounds)([min_bytes, min_pdf_bytes, ...])   | Plausibility bounds for a real book file.                          |
| [`ScoredResult`](#citeget.rank.ScoredResult)(result, score, title_match, ...) | A search result with its score and the signal breakdown behind it. |

### *class* citeget.rank.ScoreWeights(title=5.0, author=3.0, format=1.2, language=1.0, size=0.8, decoy_penalty=6.0, stub_penalty=3.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Relative contribution of each signal to the total score.

Title and author dominate: format and language only break ties between
results that are already plausibly the right book.

### *class* citeget.rank.ScoredResult(result, score, title_match, author_match, is_decoy, is_stub)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A search result with its score and the signal breakdown behind it.

### *class* citeget.rank.SizeBounds(min_bytes=80000, min_pdf_bytes=300000, implausible_bytes=120000000)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Plausibility bounds for a real book file.

`min_pdf_bytes` is deliberately far above `min_bytes`: a landing-page
“download” stub is typically a valid but nearly empty PDF, whereas a short
epub of a genuine book can legitimately be ~100 kB.

### citeget.rank.candidate_surnames(authors)

Normalized surnames usable for matching, in either name ordering.

Multi-word surnames contribute their last word, since that is what a
caller-supplied author string is most likely to share.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)

```pycon
>>> sorted(candidate_surnames("Alice Smith & Bob Jones"))
['jones', 'smith']
>>> sorted(candidate_surnames("Sander van der Linden"))
['linden']
```

### citeget.rank.dedupe_key(result)

Identity of the *work* behind a result, ignoring which format it is in.

Libgen lists one edition once per format, so `max_downloads=5` otherwise
means “five copies of one book”. Title, year and author surnames together
identify an edition well enough to collapse those rows while keeping
genuinely different editions apart.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### citeget.rank.dedupe_results(results, \*, key=<function dedupe_key>)

Keep only the first result for each distinct work, preserving order.

Apply after ranking so the surviving copy of each work is the best-scoring
one. Accepts either plain result dicts or [`ScoredResult`](#citeget.rank.ScoredResult) objects and
returns the same kind it was given.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.rank.parse_size(size_text)

Bytes from a libgen size string such as `'2 MB'`; 0 if unparseable.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> parse_size("2 MB")
2000000
>>> parse_size("587 kB")
587000
>>> parse_size("")
0
```

### citeget.rank.rank_results(results, , title, authors=None, \*\*kwargs)

Return `results` as [`ScoredResult`](#citeget.rank.ScoredResult) objects, best match first.

`kwargs` are forwarded to [`score_result()`](#citeget.rank.score_result) (`format_preference`,
`language`, `weights`, `size_bounds`, `decoy_pattern`).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.rank.score_result(result, \*, title, authors=None, format_preference=('pdf', 'epub', 'azw3', 'mobi', 'azw', 'djvu', 'fb2', 'txt'), language='english', weights=ScoreWeights(title=5.0, author=3.0, format=1.2, language=1.0, size=0.8, decoy_penalty=6.0, stub_penalty=3.0), size_bounds=SizeBounds(min_bytes=80000, min_pdf_bytes=300000, implausible_bytes=120000000), decoy_pattern=re.compile('\\\\\\\\b(summary|summaries|workbook|study guide|sparknotes|cliffs?notes|key takeaways|conversation starters|review and analysis|analysis of|insights (?:on|from)|companion to|instaread|blinkist|downloaden|, re.IGNORECASE))

Score one `search()` result against a requested title and author.

* **Parameters:**
  * **result** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – A result dict from [`citeget.search()`](citeget.html.md#citeget.search).
  * **title** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The title actually wanted.
  * **authors** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – The author(s) wanted, in any of the orderings
    [`citeget.names`](citeget.names.html.md#module-citeget.names) understands. None skips author scoring.
  * **format_preference** ([`Sequence`](https://docs.python.org/3/library/typing.html#typing.Sequence)) – File formats, best first.
  * **language** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Preferred language; a result with no language set is treated
    as neutral rather than penalised, since libgen often omits it.
  * **weights** ([`ScoreWeights`](#citeget.rank.ScoreWeights)) – Per-signal weights.
  * **size_bounds** ([`SizeBounds`](#citeget.rank.SizeBounds)) – What counts as a plausible file size.
  * **decoy_pattern** ([`Pattern`](https://docs.python.org/3/library/re.html#re.Pattern)) – Title pattern marking derivative or spam listings.
* **Return type:**
  [`ScoredResult`](#citeget.rank.ScoredResult)
