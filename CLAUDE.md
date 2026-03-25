# CLAUDE.md — citeget

## What is citeget?

A toolkit for finding, acquiring, and managing academic references. Designed
for AI agents (Claude Code skills) and humans (CLI + Python API).

**Two main capabilities:**

1. **Reference acquisition** — given a document with citations, automatically
   download PDFs via direct URL, arxiv, libgen, or sci-hub.
2. **Article publication** — journal profiling, pre-submission checking,
   formatting, and submission preparation (via Claude skills).

## Package structure

```
citeget/
├── __init__.py              # Public API
├── cli.py                   # CLI entry points (search, download, acquire)
├── __main__.py              # python -m citeget
├── core.py                  # Libgen search & download (requires playwright)
├── acquire_references.py    # Multi-strategy reference acquisition
├── data/                    # Reference docs
└── article_pub/             # Article publication toolkit
    ├── data/journal_profiles.json
    └── scripts/             # check_article, word_count, extract_references
```

## Dependencies

- `playwright` — headless browser for libgen (JS-rendered pages)
- `requests` + `beautifulsoup4` — direct downloads, sci-hub
- `argh` — CLI dispatch

Install playwright browsers: `python -m playwright install chromium`

## Skills (in .claude/skills/)

| Skill | Purpose |
|-------|---------|
| `acquire-references` | Bulk-acquire PDFs for all references in a document |
| `research-topic` | Deep literature research for article writing |
| `review-article` | Expert peer-review style critique |
| `check-submission-fit` | Journal venue recommendation |
| `format-for-journal` | Reformat draft for target journal |
| `prepare-submission` | Full submission package generation |

## Key patterns

- File naming: `{title} ({authors_apa7}, {year}).pdf`
- Work dir resolution: from reference file, full path, or bare name
- Rate limiting: 2s default between operations
- Idempotent: existing downloads are skipped automatically
