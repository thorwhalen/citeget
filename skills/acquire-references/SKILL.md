---
name: acquire-references
description: Acquire PDFs of academic references from a document. Parses reference sections, tries direct URLs and arxiv, falls back to libgen search with smart query strategies. Logs all attempts and produces references.md + missed_references.md.
argument-hint: <path-to-document-with-references> [--work-dir <dir>]
allowed-tools: Bash, Read, Write, Grep, Glob, Agent
---

# Acquire References

Download PDFs for all references cited in an academic document. Uses a
multi-strategy approach: direct URL → arxiv → libgen search (with
progressively adjusted query specificity) → optional fetch fallback (saves
the reference URL as Markdown when no PDF is reachable).

**For non-academic URL lists** (blog posts, product pages, docs, specs)
prefer the more general `/fetch-resources` skill — this skill is tuned for
finding paper PDFs in libgen / arxiv / sci-hub, which won't help for web
content.

**For a list of book titles** (a reading list, "get me these books") use
`/get-books`. This skill is built around a document's reference section; it
does not know which book you asked for, so it cannot check that the file it
got is that book. `/get-books` can.

## Working directory resolution

The system needs a **work directory** where it puts downloads, logs, and
output files. Resolution rules (in priority order):

1. **User specifies a full path** → use it (create if needed; parent must exist).
2. **User specifies a bare name** (no slashes) → use `~/Downloads/{name}`.
3. **User provides a reference file but no work dir** → derive automatically:
   `{reference_file_stem} -- acquired_references/` in the same directory as
   the file.
4. **Neither given** → ask the user.

```python
from citeget import resolve_work_dir

work_dir = resolve_work_dir(reference_file="/path/to/paper.md")
# -> /path/to/paper -- acquired_references/

work_dir = resolve_work_dir(work_dir="~/projects/refs")
# -> /Users/.../projects/refs/

work_dir = resolve_work_dir(work_dir="my_refs")
# -> ~/Downloads/my_refs/
```

Inside the work directory, PDFs go into a `references/` subdirectory.

## Pre-flight: checking existing downloads

Before acquiring, check what's already downloaded. Report skips to the user
so they can rename/move files to force re-download.

```python
from citeget import check_existing_downloads

to_acquire, already_have = check_existing_downloads(refs, download_dir)
# already_have is [(Reference, filepath), ...]
# to_acquire is [Reference, ...]
```

`acquire_all_references()` does this automatically and prints skip info.

## Core workflow

```python
from citeget import (
    parse_references_section,
    resolve_work_dir,
    acquire_all_references,
    write_references_md,
    write_missed_references_md,
)
from pathlib import Path
from datetime import datetime

# 1. Resolve work directory
work_dir = resolve_work_dir(reference_file="paper.md")
download_dir = work_dir / "references"

# 2. Parse references
refs = parse_references_section(refs_text)

# 3. Acquire (auto-skips existing, auto-generates timestamped log)
successes, failures, log_entries = acquire_all_references(
    refs,
    download_dir=download_dir,
    work_dir=work_dir,  # enables auto log naming
)
# Log written to: {work_dir}/{datetime}__acquisition_log.txt

# 4. Write output files
write_references_md(successes, download_dir, work_dir / "references.md")
ts = datetime.now().strftime("%Y-%m-%d_%H%M")
write_missed_references_md(failures, work_dir / f"{ts}_missed_references.md")
```

## Log format

The acquisition log (`{datetime}__acquisition_log.txt`) is TSV with columns:
```
timestamp  ref_number  ref_title  query  query_type  num_results  matched  best_score  best_title  error
```
Every attempt is logged — direct URL, libgen, arxiv, sci-hub — not just libgen.

## File naming

Downloaded files use APA 7 citation format:
```
{title} ({authors_apa7}, {year}).pdf
```
Where authors_apa7 is: 1 author → "Smith", 2 → "Smith & Jones", 3+ → "Smith et al."

Example: `Retiming synchronous circuitry (Leiserson & Saxe, 1991).pdf`

## Multi-topic search

By default, `acquire_all_references` searches all `libgen_topics` simultaneously
in a single request (e.g. books + articles + fiction at once), rather than
searching each topic sequentially.  This matches how the libgen.vg web UI
works and improves hit rates.

```python
# Default: searches books and articles together
successes, failures, log = acquire_all_references(refs, download_dir)

# For books specifically, search books + fiction + articles together
successes, failures, log = acquire_all_references(
    refs,
    download_dir,
    libgen_topics=("books", "fiction", "articles"),
)
```

## Query strategies

Queries are tried from most to least specific.  The first query uses
APA-style formatting (e.g. `Kodokan Judo (Kano)`) which matches how
humans typically search.  If that fails, progressively broader queries
are tried automatically.

## What "downloaded" means

Every download is validated before it counts as a success: magic bytes matching
the extension, no HTML bodies, a size floor, and a truncation check against the
size libgen advertised. A captcha wall, a Cloudflare interstitial or a
half-transferred file is reported as a failure rather than saved under a paper's
name. Files are written to a temporary path and moved into place only once
valid, so a failed attempt leaves nothing behind.

So a failure in the log can now mean *"we received something and it wasn't the
paper"*, not only *"nothing arrived"*. The `error` column says which.

Within one query, the top-scoring result is not the only one tried — up to
three plausible candidates are attempted in order, because libgen catalogues
excerpts and stubs under the real work's title.

When the primary libgen path (ads.php → get.php) fails, `download_one` also
tries external mirrors (Anna's Archive, library.lol, etc.), each validated the
same way.

Note the default policy checks *integrity*, not length — right for papers,
which are legitimately short. The stricter page-count check that rejects
excerpts is opt-in and belongs to `/get-books`.

## An empty search result is weak evidence

Libgen returns a blank result set for a query with real matches often enough to
matter: in measured repeats of one query, roughly one run in four came back
empty, and the same query gave 0 results then 21 a minute apart. `search()`
retries each mirror and requires two mirrors to agree before returning `[]`,
but that does not eliminate it.

Practical consequences for this skill:

- A reference landing in `missed_references.md` after `num_results: 0` may
  simply have been unlucky. **Re-running the skill on the missed list is worth
  doing before telling the user those references are unavailable** — the
  acquisition is idempotent, so a re-run only retries the misses.
- If an unusually large share of a batch missed, suspect the mirrors rather
  than the references. Run `citeget check-mirrors`.
- Result counts vary by mirror (the same query can return 21 or 9). A low
  `num_results` is not itself a problem.

## Fetch fallback (for non-paper URLs)

When all academic strategies fail and the reference has a URL,
`acquire_reference()` falls back to fetching that URL as Markdown via
`citeget.fetch.fetch_one`. This catches references that point at web pages
(blogs, product pages, specs, docs) instead of papers — the resulting `.md`
goes into the same download dir as the PDFs.

To disable, pass `fetch_fallback=False`:

```python
acquire_all_references(refs, download_dir, fetch_fallback=False)
```

When the entire reference list is non-papers, skip this skill and use
`/fetch-resources` directly — it's faster (no libgen / arxiv attempts) and
the API is designed for the bulk-URL case.

## Tips

- **Skip non-papers**: For lists that are *all* web pages (Wikipedia,
  blogs), use `/fetch-resources` instead — this skill burns time trying
  libgen/arxiv/sci-hub on URLs that will never resolve there.
- **Rate limiting**: The default 2s delay between operations is respectful.
  Don't decrease it.
- **Re-downloading**: Already-downloaded files are skipped — but only after
  being re-validated, so a stub or HTML page left by an earlier failed attempt
  is discarded and retried automatically. To force re-download of a *good*
  file, the user must rename or move it.
- **Matching**: Results are scored on title word overlap (60%), author match
  (25%), and year match (15%). Threshold is 0.4, and up to three results above
  it are tried per query.
- **Topics**: Use multi-topic search for best coverage.  For books, use
  ``libgen_topics=("books", "fiction", "articles")``.
- **Download failures after match**: Check the acquisition log's `error`
  column. Common causes: a timeout on ads.php, no get.php link found, or the
  bytes failing validation (an HTML page, a truncated transfer). Mirror
  fallbacks and multi-candidate retries handle most cases automatically.
- **Reporting results**: Give the user the miss list explicitly, and say
  whether a miss was "nothing found" or "found but the file was not usable" —
  they are different problems with different fixes.
