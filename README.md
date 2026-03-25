# citeget

Find, acquire, and manage academic references — for AI agents and humans.

`citeget` automates the tedious work of tracking down PDFs for academic
papers. Point it at a document with a references section, and it will try
every available source — direct URLs, arxiv, Library Genesis, Sci-Hub — to
download each one.

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

# Acquire all references from a document
citeget acquire my_paper.md
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
| `/acquire-references` | Download PDFs for every reference in a document |
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

Files are named in APA 7 citation style:
`{title} ({authors_apa7}, {year}).pdf` — e.g.,
`Retiming synchronous circuitry (Leiserson & Saxe, 1991).pdf`

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

## How it works

Library Genesis renders search results via JavaScript, so `citeget` uses
Playwright (headless Chromium) to load pages. Ad domains are blocked for
speed. Downloads use session keys extracted from intermediate pages.

The acquisition log records every attempt in TSV format, making it easy to
audit what was tried, what matched, and what failed.
