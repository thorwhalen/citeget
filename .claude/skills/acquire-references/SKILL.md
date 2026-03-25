---
name: acquire-references
description: Acquire PDFs of academic references from a document. Parses reference sections, tries direct URLs and arxiv, falls back to libgen search with smart query strategies. Logs all attempts and produces references.md + missed_references.md.
argument-hint: <path-to-document-with-references> [--work-dir <dir>]
allowed-tools: Bash, Read, Write, Grep, Glob, Agent
---

# Acquire References

Download PDFs for all references cited in an academic document. Uses a
multi-strategy approach: direct URL → arxiv → libgen search (with
progressively adjusted query specificity).

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
    work_dir=work_dir,   # enables auto log naming
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

## Tips

- **Skip non-papers**: Exclude web pages (Math Genealogy, Wikipedia),
  unpublished preprints with no PDF, and similar non-acquirable items
- **Rate limiting**: The default 2s delay between operations is respectful.
  Don't decrease it.
- **Re-downloading**: Already-downloaded files are reported and skipped. To
  force re-download, the user must rename or move the existing file.
- **Matching**: Results are scored on title word overlap (60%), author match
  (25%), and year match (15%). Threshold is 0.4.
- **Topics**: Try "articles" first (for papers), then "books" (for books/
  proceedings). Conference papers often appear under "articles".
