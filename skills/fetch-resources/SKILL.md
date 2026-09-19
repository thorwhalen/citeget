---
name: fetch-resources
description: Download one or more web resources (URLs, markdown links, reference-style citations, mixed prose) and save them as Markdown (default), PDF, or original bytes. Use when the user asks to download, fetch, save, archive, or grab web pages, blog posts, docs, specs, or any URL — especially for non-academic content where the acquire-references skill doesn't apply. Triggers on "download these URLs", "save this page", "grab this article", "fetch the docs", "archive these links".
argument-hint: [URLs, file with URLs, or text containing URLs]
allowed-tools: Bash, Read, Write, Grep, Glob
---

# Fetch Resources

Download one or many web resources and save them locally. The general-purpose
counterpart to `acquire-references` — use this when the URLs are NOT academic
papers (blog posts, product pages, specs, docs, GitHub READMEs, etc.).

For citation lists in academic papers (where libgen / arxiv / sci-hub matter),
use `/acquire-references` instead. (That skill now also falls back to this
fetch behavior automatically when academic strategies fail and the reference
has a URL.)

## When to use this vs. acquire-references

| Use this skill | Use `/acquire-references` |
|---|---|
| Bookmarks / reading list | Citation list in an academic paper |
| Product pages, blog posts, specs | Conference / journal papers |
| URLs the user just hands you | Numbered `[1] ... [N]` reference section |
| User says "download these" / "save these pages" | User says "acquire references" / "get the PDFs" |

## Quick Start

### From the CLI

```bash
# A single URL → markdown (default)
citeget fetch "https://example.com/article"

# Multiple URLs (also accepts a file or text with URLs)
citeget fetch "/path/to/refs.txt" --output-dir ~/Downloads/my-refs --prefer md

# Try to get PDF (requires `pip install citeget[fetch]` + wkhtmltopdf)
citeget fetch refs.txt --prefer pdf
```

### From Python

```python
from citeget import fetch

# Pass anything: URL, list, file path, or prose with URLs in it
results = fetch(
    "/path/to/document_with_urls.md",
    output_dir="~/Downloads/my-refs",
    prefer="md",  # "md" (default), "pdf", "original", "auto"
)

for r in results:
    if r.ok:
        print(f"OK   [{r.format}] {r.output_file}")
    else:
        print(f"FAIL {r.url}: {r.error}")
```

## How It Works

### Source parsing

The `fetch()` function accepts a flexible *source*:

- A single URL string
- A path to a file (any text format containing URLs)
- A string of prose / markdown / reference-style citations
- A list of any of the above

URLs are extracted in three forms (deduped, first match wins):
1. **Markdown links**: `[Anchor text](https://url)` → anchor used for filename
2. **Reference-style**: `[1] Citation text. https://url` → ref number prefix
3. **Bare URLs**: anywhere in text

### Per-URL pipeline

1. Fetch via httpx (follows redirects).
2. If the response is a PDF and `prefer in {"pdf", "original", "auto"}` →
   save as `.pdf`.
3. If HTML and `prefer="pdf"` → look for embedded direct-PDF link
   (arxiv `/pdf/`, GitHub `.pdf`, `/doi/pdf/`, etc.); if found, fetch that.
   Otherwise try HTML→PDF via `pdfkit`/`wkhtmltopdf`.
4. Otherwise convert HTML→Markdown via `markdownify` (clean, link-preserving).
5. If a PDF route fails, fall back to Markdown automatically.

### Filename inference

Files are named in this priority order:
1. Anchor / citation title → slug
2. URL's last path segment
3. `{domain}-{hash}`

Reference numbers become a prefix: `ref_03_some-title.md`.

## Format choice (`--prefer` / `prefer=`)

| Value | Behavior |
|---|---|
| `md` (default) | HTML → Markdown. PDFs saved as PDF. |
| `pdf` | Get/render PDF. Requires `wkhtmltopdf` for HTML→PDF. Falls back to MD on failure. |
| `original` | Save whatever bytes came back, with a sensible extension. |
| `auto` | Like `md`. (Reserved for future content-type-driven routing.) |

## Optional dependencies for PDF rendering

HTML→PDF is opt-in:

```bash
pip install 'citeget[fetch]'
brew install wkhtmltopdf      # macOS
# or: apt-get install wkhtmltopdf   # Debian/Ubuntu
```

If `pdfkit` or `wkhtmltopdf` is missing, `prefer="pdf"` falls back to Markdown.

## Workflow for Claude

1. **Identify the source** — a URL, a file the user references, or a block of
   text with URLs in it. Pass it directly to `citeget fetch` or `citeget.fetch()`.
2. **Determine output dir** — what the user said, else `~/Downloads`. If the
   URLs come from a document, prefer `{document_stem} -- fetched/`.
3. **Pick a format**:
   - Default to `md` — works for any HTML page, no extra deps.
   - Use `pdf` only when the user asks for it AND `wkhtmltopdf` is available.
4. **Run it** and report the manifest summary.

### Example: download all references in a document as Markdown

```bash
citeget fetch /path/to/article.md \
    --output-dir "/path/to/article -- fetched/" \
    --prefer md \
    --manifest "/path/to/article -- fetched/manifest.json"
```

### Example: just a few URLs the user pasted

```python
from citeget import fetch

results = fetch(
    [
        "https://en.wikipedia.org/wiki/Script_supervisor",
        "https://fountain.io/",
    ],
    output_dir="~/Downloads/script-refs",
    prefer="md",
)
```

## Failure handling

- Network/HTTP errors are logged and the URL is marked `failed` in the
  result; other URLs still proceed.
- For JS-heavy pages where markdownify gives poor output, suggest re-running
  with `--prefer pdf` (renders the page) or use the `WebFetch` tool as a
  second opinion.
- For paywalled academic content, switch to `/acquire-references` — it has
  arxiv / sci-hub strategies this skill deliberately doesn't.
