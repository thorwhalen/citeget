# citeget

Find, acquire, and manage academic references — for AI agents and humans.

`citeget` automates the tedious work of tracking down PDFs for academic
papers. Point it at a document with a references section, and it will try
every available source — direct URLs, arxiv, Library Genesis, Sci-Hub — to
download each one.

It also handles the more general case: any list of URLs (blog posts, docs,
specs, product pages) saved as Markdown or PDF — useful when references
aren't peer-reviewed papers. See [`citeget fetch`](#general-purpose-fetch)
below.

## Install

```bash
pip install citeget
python -m playwright install chromium   # one-time browser setup
```

## Quick start

### CLI

```bash
# Search for papers
citeget search "graph theory" --topic articles

# Download top results
citeget download "python programming" --download-dir ~/papers --max-downloads 3

# Or get one copy of a *specific* book: ranked against title + author,
# validated as a complete book, next candidate tried if it isn't one
citeget get-book "Crossing the Chasm" --authors "Geoffrey A. Moore" --download-dir ~/books

# Check which libgen mirrors are healthy today
citeget check-mirrors

# Acquire all references from a document (academic mode)
citeget acquire my_paper.md

# Fetch arbitrary URLs — markdown by default, pdf if you ask for it
citeget fetch "https://example.com/article" --output-dir ~/Downloads/refs
citeget fetch refs.md --prefer md   # accepts a file with URLs in any form
```

The `acquire` command reads the references section, resolves a working
directory, and downloads every reference it can find:

```
$ citeget acquire paper.md
Parsed 34 references
Work dir: paper -- acquired_references/

Skipping 5 already-downloaded reference(s):
  [1] Efficiently modeling long sequences...
  [3] High-speed parallel architectures...
        -> (To re-download, rename or move the existing file.)

[1/29] Ref [2]: A two-step computation of cyclic redundancy code...
  SUCCESS (libgen_articles) -> references/A two-step computation... (Glaise, 1997).pdf
[2/29] Ref [4]: High-speed parallel LFSR architectures...
  SUCCESS (libgen_articles) -> references/High-speed parallel... (Hu et al., 2017).pdf
...

Acquired: 30/34
Output: paper -- acquired_references/
```

Output files:
- `references/` — downloaded PDFs, named `{title} ({authors}, {year}).pdf`
- `references.md` — all acquired references with clickable local links
- `{datetime}_missed_references.md` — what couldn't be found and why
- `{datetime}__acquisition_log.txt` — every search attempt (TSV)

### Python API

```python
from citeget import search, search_and_download

# Search and get metadata
results = search("machine learning", topic="articles")
for r in results[:3]:
    print(f"{r['title'][:60]}  ({r['year']})")

# One-shot search + download
search_and_download("python programming", download_dir="~/papers", max_downloads=5)
```

### Getting a specific book

`search_and_download` takes libgen's own ordering, which for a known title is
usually the same book in several formats, interleaved with summaries and
download-spam listings. When you want *one copy of one book*, use `get_book`:

```python
from citeget import get_book

path = get_book(
    "Crossing the Chasm", authors="Geoffrey A. Moore", download_dir="~/books"
)
```

It ranks every result against the title and author you asked for, downloads the
best candidate, checks that what arrived is a complete book, and falls through
to the next candidate if it isn't. The pieces are usable on their own:

```python
from citeget import search, rank_results, download_best, validate_download

results = search("Crossing the Chasm Moore")
ranked = rank_results(results, title="Crossing the Chasm", authors="Geoffrey A. Moore")
ranked[0].score, ranked[0].is_decoy, ranked[0].title_match

path = download_best(
    results,
    title="Crossing the Chasm",
    authors="Geoffrey A. Moore",
    download_dir="~/books",
)
```

Every knob is a keyword argument with a sensible default — format preference,
language, scoring weights, size bounds, the decoy pattern:

```python
from citeget import get_book, ScoreWeights

get_book(
    "Some Book",
    authors="A. Author",
    format_preference=("epub", "pdf"),  # e-reader workflow
    weights=ScoreWeights(author=5.0),
)  # trust the author field more
```

### Download validation

Nothing about a successful transfer says the bytes are a document. Every
download path checks magic bytes, rejects HTML pages, enforces a realistic size
floor, and compares against the size libgen advertised — so a captcha wall or a
truncated transfer is a failure, not a book. Files are written to a temporary
path and moved into place only after they validate, so a failed attempt never
leaves a stub that a later run reads back as a cached success.

Books get an extra tier of checking, because libgen catalogues excerpts,
front-matter samples and reviews under the full work's title — files with valid
PDF magic bytes, several megabytes in size, and 17 pages long:

```python
from citeget import download_one, validate_download, BOOK_POLICY

download_one(result, download_dir="~/books", policy=BOOK_POLICY)  # page-count check on
validate_download("suspect.pdf", policy=BOOK_POLICY)  # check one by hand
```

`BOOK_POLICY` is opt-in rather than the default because an 80-page floor is
right for a book and badly wrong for a journal article. `get_book` uses it
automatically. Build your own with `dataclasses.replace`:

```python
from dataclasses import replace
from citeget import BOOK_POLICY, ValidationPolicy

lenient = replace(BOOK_POLICY, min_pages=40)
```

For bulk reference acquisition:

```python
from citeget import (
    parse_references_section,
    resolve_work_dir,
    acquire_all_references,
    write_references_md,
    write_missed_references_md,
)

# Parse references from any text
refs = parse_references_section(my_paper_text)

# Resolve working directory (auto-derived from filename)
work_dir = resolve_work_dir(reference_file="paper.md")

# Acquire — tries direct URL → libgen → arxiv → sci-hub
successes, failures, log = acquire_all_references(
    refs,
    download_dir=work_dir / "references",
    work_dir=work_dir,
)

# Write output files
write_references_md(successes, work_dir / "references", work_dir / "references.md")
```

### AI agent usage (Claude Code skills)

`citeget` ships with Claude Code skills — structured prompts that let an
AI agent use the tools interactively. The skills live in `.claude/skills/`
inside this repository.

**To use in Claude Code**, either work in the citeget project directory
(skills are auto-discovered), or copy the skill folders into your project's
`.claude/skills/` directory. Then invoke them by name:

```
> /acquire-references my_paper.md
> /research-topic "linear recurrence substitution"
> /review-article draft.md ieee_software
> /check-submission-fit draft.md
> /format-for-journal draft.md cacm_practice
> /prepare-submission draft.md ieee_software
```

**To use skills in other systems**, the `SKILL.md` files are self-contained
markdown documents that describe the workflow, tools needed, and expected
output. Any AI agent system that supports tool-use prompts can consume them
— read the `SKILL.md` file and include it in your system prompt alongside
the relevant tool definitions. The skills call into `citeget`'s Python API,
so the agent needs access to a Python environment with `citeget` installed.

Available skills:

| Skill | What it does |
|-------|-------------|
| `/fetch-resources` | Download arbitrary URLs as Markdown / PDF (general) |
| `/acquire-references` | Download PDFs for every reference in an academic document |
| `/research-topic` | Deep literature survey with structured research brief |
| `/review-article` | Peer-review style critique with scored dimensions |
| `/check-submission-fit` | Journal venue recommendation with fit scores |
| `/format-for-journal` | Reformat a draft for a specific journal's requirements |
| `/prepare-submission` | Generate cover letter, checklist, and submission guide |

## Acquisition strategy

For each reference, `citeget` tries these sources in order:

1. **Direct URL** — if the reference includes an arxiv, OpenReview, or other
   direct link, download the PDF.
2. **Library Genesis** — search by title with progressively adjusted
   specificity (full title → title + author → short title → author + year).
3. **Arxiv API** — structured search by author + title keywords.
4. **Sci-Hub** — DOI lookup via Crossref, then Sci-Hub download.
5. **Fetch fallback** — if no PDF is reachable but the reference has a URL,
   the page is fetched and saved as Markdown. Catches non-paper references
   (blog posts, docs, product pages). Disable with `fetch_fallback=False`.

Files are named in APA 7 citation style:
`{title} ({authors_apa7}, {year}).pdf` — e.g.,
`Retiming synchronous circuitry (Leiserson & Saxe, 1991).pdf`

Author parsing handles libgen's mixed conventions — `"Moore, Geoffrey A."`,
`"Edward R. Tufte"`, `"Chris Voss & Tahl Raz"`, and role markers like
`"(author)"` — via `citeget.names`, which is also what result ranking matches
authors with, so the two never disagree.

## General-purpose fetch

Not all "references" are papers. For lists of arbitrary web URLs, use
`citeget fetch` (or `citeget.fetch()`) — it accepts a URL, a list, a file
of URLs, or prose with embedded URLs, and saves each one as Markdown
(default), PDF, or original bytes.

```python
from citeget import fetch

# Pass anything — citeget figures out what URLs are in there
results = fetch(
    "/path/to/links.md",
    output_dir="~/Downloads/refs",
    prefer="md",  # "md" (default), "pdf", "original", or "auto"
)
for r in results:
    print(r.status, r.format, r.output_file)
```

URL parsing recognizes markdown links `[anchor](url)`, reference-style
`[1] ... https://url` citations, and bare URLs in prose. Filenames are
inferred from anchor text → URL path → domain hash.

PDF rendering is opt-in (HTML→PDF needs `wkhtmltopdf`):

```bash
pip install 'citeget[fetch]'
brew install wkhtmltopdf      # or apt-get install wkhtmltopdf
```

Without it, `--prefer pdf` quietly falls back to Markdown.

## Article publication toolkit

Beyond reference acquisition, `citeget` includes tools for the full
publication workflow. These are primarily used through Claude Code skills,
backed by machine-readable journal profiles in `citeget/article_pub/data/journal_profiles.json`.

Supported journals: IEEE Software, CACM (Practice/Research/Viewpoints),
IEEE TSE, ACM Queue.

Standalone scripts in `citeget/article_pub/scripts/`:

```bash
# Check article against journal requirements
python -m citeget.article_pub.scripts.check_article draft.md ieee_software

# Word count with section breakdown
python -m citeget.article_pub.scripts.word_count draft.md --breakdown

# Reference consistency check
python -m citeget.article_pub.scripts.extract_references draft.md
```

## Mirrors

Libgen mirror domains rotate, so the shipped default list goes stale on its own
schedule. `citeget` tries each mirror in order, retries one that merely timed
out before failing over, and tells you which of the two failure modes happened
if they all fail.

When searches start failing, ask which mirrors are alive:

```bash
citeget check-mirrors
```

It prints a health table and a ready-to-use override for the working ones:

```bash
export CITEGET_LIBGEN_MIRRORS='https://libgen.vg,https://libgen.la'
# or a single mirror
export CITEGET_LIBGEN_BASE_URL='https://libgen.la'
```

Or pass `base_url=` / `mirrors=` to `search()` and friends. Only
libgen.vg-family mirrors (the JS `#tablelibgen` layout) are compatible with the
parser; the older libgen.is/.rs/.st forks use different HTML.

## How it works

Library Genesis renders search results via JavaScript, so `citeget` uses
Playwright (headless Chromium) to load pages. Ad domains are blocked for
speed. Downloads use session keys extracted from intermediate pages — those
keys are single-use, so a download is claimed on the first attempt or not at
all.

The acquisition log records every attempt in TSV format, making it easy to
audit what was tried, what matched, and what failed.
