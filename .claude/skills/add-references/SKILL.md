---
name: add-references
description: >
  Find and add references to documents. Use this skill whenever a user provides text (usually markdown)
  and wants references, citations, or sources added to it. This includes requests like "add references to
  this document", "find citations for this", "source this article", "add links to back up the claims",
  "reference this for publication", "find supporting evidence", or any variation where the user has
  written content and wants it backed by credible sources. Also use when the user asks to generate a
  references section, find sources for specific claims, or validate statements with citations. Trigger
  even for indirect requests like "make this more credible", "this needs sources", or "prepare this for
  submission". Works for blog posts, academic papers, grant proposals, reports, and any written content
  that benefits from citations.
---

# Reference Finder

Add high-quality references and citations to user-provided documents.

## Overview

This skill takes user-provided text (typically markdown) and returns an equivalent version
with references added. How the referencing is done is governed by a set of parameters — the
skill's first job is to propose sensible defaults for these, get the user's buy-in, and
then proceed.

## Parameters

Nine parameters control the referencing behavior. They are listed in detail in
`references/parameters.md`. Here is a summary:

| # | Parameter | What it controls | Example values |
|---|-----------|-----------------|----------------|
| 1 | **Context** | Domain, audience, venue | tech blog, NIH grant, journal article |
| 2 | **Citation scope** | What warrants a reference | empirical claims, tools, all non-obvious claims |
| 3 | **Citation style** | How refs appear in-text | Vancouver `[1]`, Author-Date `(Smith, 2023)`, inline hyperlinks, footnotes |
| 4 | **Bibliography format** | How the refs section looks | numbered, alphabetical, annotated, grouped, none |
| 5 | **Source criteria** | What counts as acceptable | peer-reviewed only, preprints OK, reputable blogs OK |
| 6 | **Research depth** | How hard to look | surface, standard, deep |
| 7 | **Output mode** | What to return | annotated document, refs list only, annotation report, diff |
| 8 | **Density** | How heavily to reference | light, moderate, comprehensive |
| 9 | **Gap handling** | What to do with unsourceable claims | flag, suggest softening, suggest removal, skip |

**Context (#1) drives defaults for all the others.** A user who says "tech blog" gets
inline hyperlinks, standard depth, moderate density, etc. — without having to think about
the rest. Any individual parameter can be overridden.

For the full menu of values each parameter can take, and what they mean, read
`references/parameters.md`.

Detailed profile-specific rules live in separate files in the `references/` directory.
Each file is a **referencing profile** — a set of citation conventions, source quality
criteria, density rules, and examples for a specific publication setting:

| Profile | File | When to use |
|---------|------|-------------|
| Technical blog | `references/tech-blog.md` | Software/AI/tech blog posts, Medium, dev.to, engineering blogs |
| Social sciences | `references/social-sciences.md` | Journal articles, grant proposals (NIH, NSF, ERC), health research |
| Mathematics | `references/math-combinatorics.md` | Combinatorics, graph theory, discrete math journals |
| AI/ML research | `references/ai-ml.md` | ML conferences (NeurIPS, ICML, ICLR), AI journals (JMLR, AIJ) |

To create a new profile, see "Maintaining profiles" at the end of this file.

## Workflow

### Step 1. Analyze and propose

Before any research, do a **cursory read** of the input text and any instructions the user
has provided. Also **probe for citeget** (see "citeget integration" below) — note
availability in your proposal if relevant.

From the cursory read, infer the best default for each parameter.

Then present a **configuration proposal** to the user. The proposal should be concise —
a quick table or bulleted list — with brief commentary on your reasoning.

**Highlight choices that are ambiguous or could go either way.** For example:
- The text reads like a blog post but has academic-level claims → note the tension
- The audience isn't clear → say what you're assuming and why
- The density is a judgment call → explain the tradeoff

The proposal should feel like a knowledgeable assistant saying "here's how I'd approach
this — anything you'd change?" Not a lengthy questionnaire.

**Example proposal** (adapt the format to what feels natural in context):

> Based on a quick read, here's how I'd approach the referencing:
>
> | Parameter | Proposed | Reasoning |
> |-----------|----------|-----------|
> | Context | Tech blog (AI/ML audience) | The tone and content suggest a Medium-style post for practitioners |
> | Citation scope | Empirical claims, named tools, benchmarks | Skipping well-known concepts (attention, fine-tuning) your audience knows |
> | Citation style | Inline hyperlinks | Standard for blog format |
> | Bibliography | None (links are self-contained) | Could add a "Further Reading" section if you want — let me know |
> | Source criteria | Official docs + papers; reputable blogs OK | No hard peer-review requirement given the venue |
> | Research depth | Standard | I'll verify sources actually support claims, but won't deep-dive into ref chains |
> | Output mode | Annotated document | Full text back with links woven in |
> | Density | Moderate (~8-12 refs for this length) | Enough to back key claims without cluttering |
> | Gap handling | Flag unsourceable claims | I'll call out anything I can't find a good source for |
>
> **One thing I'd flag:** You mention some performance numbers in section 3 without
> attribution — I'll try to find the original benchmarks, but if those are from your own
> experiments, let me know and I'll leave them unlinked.
>
> Want to adjust anything, or should I go ahead?

The user can then:
- **Approve** ("looks good", "go ahead") → proceed to Step 2
- **Adjust** ("make it more academic", "use Vancouver style", "go deeper on the ML
  papers") → update the configuration and confirm
- **Discuss** ("what would change if this were for a journal?", "should I use footnotes
  here?") → talk through the tradeoff, then confirm

Don't proceed to research until you have at least implicit confirmation.

**When to skip this step:** If the user has been very explicit about what they want (e.g.,
"add Vancouver-style references to this grant proposal for NIH, comprehensive density,
deep research"), you can compress the proposal to a single confirming sentence and proceed.
Use judgment — the goal is to save the user time, not to add a bureaucratic gate.

### Step 2. Load profile rules

Read the appropriate profile from `references/` based on the confirmed configuration.
If the user's situation doesn't match an existing profile exactly, adapt the closest one
and note what you're doing.

### Step 3. Scan and flag passages

Read the document carefully. Based on the confirmed **citation scope** and **density**,
identify passages that warrant references.

If the document already contains some citations, parse them first so you don't duplicate
work. If citeget is available, use `citeget.extract_references(text)` for this (it handles
multiple citation formats automatically). Otherwise, scan manually for existing `[N]`
brackets, inline hyperlinks, or author-date patterns.

Categorization of what to reference (adjusted by citation scope setting):

**Empirical claims** — statistics, data points, measurements, performance benchmarks.
Always reference these regardless of scope setting.

**Attributed ideas** — named studies, specific people's arguments, paraphrased work
from others. Always reference.

**Technical claims** — how a tool works, what a standard says, what an algorithm does.
Reference when scope is moderate or comprehensive.

**Conceptual origins** — the DRY principle, Agile methodology, Social Cognitive Theory.
Reference when scope is comprehensive, or when the audience may not know the origin.

**Tools and frameworks** — named software, libraries, platforms. Reference (link to
official source) when scope is moderate or comprehensive.

**Trend claims** — "adoption is growing", "the field is moving toward X". Reference
when any evidence exists; flag if no source found.

**Common knowledge** — skip unless the scope is explicitly set to comprehensive and the
audience is non-specialist.

### Step 4. Research and find sources

This is the core work. The effort invested should match the confirmed **research depth**.

**Surface depth:**
- One or two searches per claim
- Take the first credible source that supports the claim
- Verify the URL loads and is relevant
- Appropriate for: blog posts about well-documented topics, internal reports

**Standard depth:**
- Multiple search queries per claim, varying terms to find the best source
- Prefer primary over secondary sources
- Fetch and verify that sources actually support the specific claim
- Check for more authoritative alternatives to the first hit
- Appropriate for: published blog posts, white papers, conference talks

**Deep depth:**
- Follow reference chains — read what sources cite, find the original
- Cross-reference across multiple databases (web search, arXiv, Google Scholar)
- Check for retractions, corrections, or superseding work
- Verify recency — is this still the best source or has it been updated?
- Appropriate for: journal articles, grant proposals, systematic reviews

Regardless of depth:

- **Never fabricate references.** No invented authors, titles, DOIs, or URLs.
- **Note when you can't find a source.** Handle according to the **gap handling** setting.
- **Prefer primary sources.** The original paper/docs, not someone's summary of it.
- **Supplement with citeget** (if available and context is academic): when web search
  returns secondary coverage, try `citeget.search(title, topic="articles")` to find the
  original paper. See "citeget integration" below.

### Step 5. Assemble output

Return the result according to the confirmed **output mode**:

**Annotated document** — the full text with references woven in, formatted per the
confirmed citation style and bibliography format. Ready to use or nearly so.

**References list only** — a numbered/keyed list of sources, each tied to a passage or
claim in the text (by quoting a short phrase or giving a section/paragraph reference).
The source text is not modified.

**Annotation report** — a structured list: for each flagged passage, the passage text,
the suggested source(s), and any notes (e.g., "this claim may be overstated relative to
the source"). Useful when the author wants to insert citations themselves.

**Diff** — the annotated document, but with changes marked (e.g., using markdown
strikethrough/bold or a separate diff format). Useful for review before accepting.

### Step 6. Summary

After the output, include a brief summary:
- How many references were added
- Any claims that couldn't be sourced (per gap handling policy)
- Passages where the author might want to add their own references (prior work, internal
  data, personal experience)
- Any claims where the best available source is weaker than ideal
- If research depth was less than deep: note any areas that might benefit from deeper
  digging
- If citeget is available and context is academic: offer to acquire PDFs for the
  referenced papers (see "citeget integration" below)

## Important guidelines

**Respect the author's voice.** You're adding references, not rewriting. Keep text
modifications to the minimum needed to incorporate citations.

**Accuracy over quantity.** Five well-chosen, verified references beat fifteen questionable
ones.

**Be transparent about uncertainty.** If a source is imperfect, say so. The author decides.

**Don't over-reference.** Even at comprehensive density, not every sentence needs a
citation. Judgment matters — the goal is a well-supported document, not a wall of brackets.

**Recency is contextual.** In AI, 2020 may be ancient. In social sciences, a 1977 seminal
paper may be exactly right.

## citeget integration (optional)

This skill can optionally leverage [`citeget`](https://pypi.org/project/citeget/) — a
Python package for searching academic databases (Library Genesis), extracting references
from documents, and downloading papers. citeget is NOT required; the skill works fully
via web search alone. When available, it adds capabilities for academic/research contexts.

### Probe for availability

At the start of any referencing session (before the parameter proposal), check whether
citeget is usable. In Claude Code, run:

```python
try:
    import citeget
    _CITEGET = True
except ImportError:
    _CITEGET = False
```

In Claude.ai (no Python execution), assume citeget is NOT available unless the user
explicitly says otherwise.

If available, mention it in the parameter proposal — briefly, as one line:
> "citeget is installed — I can search academic databases and offer PDF acquisition."

### Integration points

There are three specific places in the workflow where citeget adds value. Each is
independent — use whichever apply.

**1. Parse existing references (Step 3)**

If the input document already contains some citations, use citeget to parse them before
scanning for gaps:

```python
from citeget import extract_references
result = extract_references(document_text)
existing_refs = result.references  # list of Reference objects
```

This avoids duplicating citations that are already present. The `extract_references`
function tries multiple extraction strategies automatically (section headers, `[N]`
patterns, bold-numbered entries) and reports confidence. It also supports a
`markdown_links` extractor for documents that use inline hyperlinks.

**2. Search academic databases (Step 4)**

When the context calls for scholarly references (social sciences, grants, research blogs)
and web search hasn't surfaced the right paper, use citeget's libgen search:

```python
from citeget import search
results = search("cognitive behavioral therapy meta-analysis", topic="articles")
# Returns list of dicts: title, authors, year, doi, etc.
```

This is a supplement to web search, not a replacement. Use it when:
- Web search returns news/blog coverage but you need the original paper
- You have a title or author and want to confirm it exists
- The user's context is academic and they'll want the actual PDF later

**3. Offer PDF acquisition (Step 6)**

After delivering the referenced document, if citeget is available AND the context is
academic (journal, grant, research), offer to acquire PDFs:

> "I added 23 references. Want me to acquire PDFs for them using citeget? I can
> search libgen, ArXiv, and other sources."

If the user accepts, you can either:
- Use the CLI: `citeget acquire <output_file> --preview`
- Use the Python API: `acquire_all_references(refs, download_dir=...)`

This is the user's choice — don't auto-download. Just offer.

### When citeget is NOT available

Fall back entirely to web search. No functionality is lost for blog/web contexts. For
academic contexts, you can note in the summary that citeget could help acquire PDFs:
> "Tip: `pip install citeget` enables searching academic databases and downloading
> referenced papers as PDFs."

### Checking for required dependencies

citeget itself may be installed but not fully functional. Its search and download features
require Playwright with Chromium. If you get errors about Playwright, note to the user:
> "citeget is installed but Playwright isn't set up. Run
> `python -m playwright install chromium` to enable academic paper search/download."

The `extract_references` function works without Playwright — it's pure Python regex.
So even a partial citeget install is useful for parsing existing references.

## Usage in Claude Code

Works the same way. The user may provide input via a file path. Read the file, run the
workflow, write output to `{original_name}_referenced.md` (or as specified). The
propose-confirm step happens in the terminal conversation just as it would in Claude.ai.

In Claude Code specifically, citeget integration is most useful — you have Python
execution, filesystem access for downloads, and the user's local environment where
citeget is likely installed and configured.

## Usage in Claude.ai

The skill works in Claude.ai with web search as the sole research tool. citeget is
generally NOT available here (no local Python environment). The propose-confirm workflow,
context-specific referencing rules, and all output modes work identically.

If the user has uploaded a Python environment or explicitly mentions citeget availability,
the code execution sandbox can be used — but this is an edge case.

## Maintaining profiles

Each `.md` file in `references/` is a **referencing profile**. Profiles are the main
extension point for this skill — adding a new publication domain means adding a new file.

### Creating a new profile

1. Copy `references/TEMPLATE.md` to a new file (e.g., `references/legal-brief.md`)
2. Fill in each section following the template's guidance
3. Add a row to the profile table in this SKILL.md (the one in the Parameters section)

The template has six sections — fill in all of them:
- **Citation format**: How refs appear in-text and in the bibliography
- **Source quality criteria**: Tiered list of what counts as credible
- **Reference density**: How heavily to cite, with rough targets
- **Common patterns**: 3-4 examples showing typical citation usage
- **Recency guidelines**: How old is too old, by source type
- **Special considerations**: Domain-specific quirks

Research the target journals/venues before writing a profile. Check their author
guidelines for citation style requirements, and look at published papers to see actual
citation practice (which often diverges from stated guidelines).

### Editing an existing profile

Just edit the file. Changes take effect immediately — no re-installation needed in
Claude Code (it reads from disk). For Claude.ai, re-zip and re-upload the skill.

### Removing a profile

Delete the file from `references/` and remove its row from the profile table in this
SKILL.md. The skill will continue to work — it just won't offer that profile as an option.

### Profile naming convention

Use lowercase kebab-case: `tech-blog.md`, `social-sciences.md`, `math-combinatorics.md`.
The filename should suggest both the domain and the venue type when they differ (e.g.,
`ai-ml.md` covers both conferences and journals because the conventions are similar).
