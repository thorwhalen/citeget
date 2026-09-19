# Reference Finder — Parameters

Detailed reference for all configurable parameters. The agent reads this when it needs to
understand the full menu of options. Users don't need to read this directly — the agent
translates it into natural proposals.

---

## 1. Context

The situational frame. Drives defaults for all other parameters.

### Sub-dimensions

- **Domain/field**: software engineering, AI/ML, data science, social sciences,
  psychology, public health, biomedical, education, humanities, policy, business, etc.
- **Audience**: practitioners, academic peer reviewers, grant reviewers, general public,
  executives/decision-makers, students, mixed/cross-disciplinary
- **Venue**: blog post, journal article, grant proposal, conference paper, technical
  report, white paper, internal memo, book chapter, thesis/dissertation, policy brief

In practice, the user specifies 1-2 of these and the rest are inferred. For example:
"NIH grant proposal" implies domain=health/behavioral sciences, audience=grant reviewers,
venue=grant proposal.

### Context → Default mappings

| Context shorthand | Scope | Style | Bib format | Sources | Depth | Density |
|-------------------|-------|-------|------------|---------|-------|---------|
| Tech blog | empirical + tools | inline hyperlinks | none | docs, papers, blogs OK | standard | moderate |
| ML research blog | empirical + tools + concepts | hybrid (links + refs section) | numbered by appearance | papers + official | standard-deep | moderate-high |
| Journal (social sci) | comprehensive | Author-Date (APA) | alphabetical | peer-reviewed preferred | deep | comprehensive |
| Grant proposal (NIH) | comprehensive | Vancouver | numbered by appearance | peer-reviewed + govt stats | deep | comprehensive |
| Grant proposal (NSF) | comprehensive | any consistent | numbered or alphabetical | peer-reviewed + govt stats | deep | comprehensive |
| White paper | empirical + trends | footnotes or inline links | endnotes or none | flexible | standard | moderate |
| Conference paper | comprehensive | per venue style guide | per venue | peer-reviewed preferred | standard-deep | moderate-high |
| Internal report | empirical only | inline links | none | flexible | surface | light |

These are starting points. The agent adjusts based on the specific text.

---

## 2. Citation scope

What categories of claim warrant a reference. Ordered from always-cite to cite-only-when-
scope-is-wide:

| Category | Description | When to cite |
|----------|-------------|--------------|
| **Empirical claims** | Statistics, data points, measurements, benchmarks | Always |
| **Attributed ideas** | Named studies, credited arguments, paraphrased work | Always |
| **Methodological refs** | Tools, instruments, validated scales, algorithms, software | Moderate+ scope |
| **Prior art** | Related or competing work | Moderate+ scope (academic contexts: always) |
| **Technical claims** | How something works, what a spec says | Moderate+ scope |
| **Conceptual origins** | Named principles, theories, frameworks with a traceable origin | Comprehensive scope, or when audience may not know |
| **Definitions** | Non-standard or domain-specific terminology | Comprehensive scope |
| **Tools & frameworks** | Named software, libraries, platforms | Moderate+ scope (link to official source) |
| **Trend claims** | "Adoption is growing", "the field is moving toward X" | Moderate+ scope; flag if unsourceable |
| **Common knowledge** | Facts any member of the target audience would know | Skip unless comprehensive + non-specialist audience |

A related sub-parameter is the **common knowledge threshold** — what can you assume the
audience already knows? This is inferred from the audience dimension of context. Senior ML
engineers know what a Transformer is; NIH grant reviewers who aren't ML specialists may not.

---

## 3. Citation style

How references appear in the body text.

| Style | Format | Typical context |
|-------|--------|-----------------|
| **Vancouver** | Sequential numbered brackets: `[1]`, `[2,3]`, `[4-7]` | Biomedical journals, NIH grants, health sciences |
| **Author-Date (APA)** | `(Smith & Doe, 2023)` or `Smith and Doe (2023)` | Social sciences, psychology, education |
| **Author-Date (Harvard)** | Similar to APA with minor formatting differences | UK social sciences, some business |
| **Notes (Chicago NB)** | Superscript numbers¹ linking to footnotes/endnotes | Humanities, history, some policy writing |
| **Inline hyperlinks** | `[anchor text](url)` — no separate numbering | Blog posts, web content, documentation |
| **Hybrid** | Mix of styles depending on source type | Research-adjacent blogs: links for tools/docs, numbered for papers |
| **IEEE** | Numbered brackets like Vancouver but with different bib format | Engineering, CS conferences |

If the user doesn't specify and context doesn't clearly determine it, prefer: inline
hyperlinks for blogs/web, Vancouver for health/biomedical, APA for social sciences.

---

## 4. Bibliography format

How the collected references are presented, typically at the end of the document.

| Format | Description | When to use |
|--------|-------------|-------------|
| **Numbered (by appearance)** | `[1] ...` `[2] ...` in order of first citation | Vancouver, IEEE |
| **Alphabetical by author** | Sorted A-Z by first author surname | APA, Harvard, Chicago Author-Date |
| **Annotated** | Each entry includes a 1-2 sentence note on what it contributes | "Further reading" sections, some grant proposals |
| **Grouped** | Organized by topic, by section, or by source type | Long documents, literature reviews |
| **None** | No separate section — inline links are self-contained | Blog posts with inline hyperlinks |

**Metadata per entry** (varies by style but worth making explicit): author(s), title,
journal/venue, year, volume/issue/pages, DOI, URL, access date (for web sources),
publisher (for books), report number (for technical reports).

---

## 5. Source criteria

What counts as an acceptable reference. Multiple sub-dimensions:

### Minimum evidence tier

| Tier | Sources included | When appropriate |
|------|-----------------|------------------|
| **Peer-reviewed only** | Published journal articles, systematic reviews | Strict academic contexts, journal submissions |
| **Peer-reviewed + recognized grey lit** | Above + govt reports, WHO/OECD, working papers from named institutions | Grant proposals, policy writing |
| **Credible sources** | Above + reputable blogs, official docs, conference talks | Tech blogs, white papers |
| **Any substantive source** | Above + community content (StackOverflow, forums) | Internal docs, informal writing |

### Recency preference

| Setting | Rule |
|---------|------|
| **Strict** | Within last 3-5 years; older only for foundational/seminal work |
| **Moderate** | Prefer recent; older OK when it's the definitive source |
| **No constraint** | Age doesn't matter if the content is still accurate |

### Accessibility preference

| Setting | Rule |
|---------|------|
| **Open access preferred** | Prefer freely available sources; note paywalls when unavoidable |
| **No constraint** | Use the best source regardless of access model |

### Originality preference

| Setting | Rule |
|---------|------|
| **Primary sources preferred** | Cite original papers/docs; avoid secondary coverage |
| **Secondary OK** | Review papers, well-sourced summaries are acceptable |

---

## 6. Research depth

How much effort to invest in finding each source.

| Level | Behavior | Typical use |
|-------|----------|-------------|
| **Surface** | 1-2 searches per claim. First credible hit. Verify URL loads. | Blog posts on well-known topics, internal docs |
| **Standard** | Multiple queries per claim. Prefer primary sources. Fetch and verify content supports the claim. Check for better alternatives. | Published blog posts, white papers, talks |
| **Deep** | Follow reference chains. Cross-reference databases. Check for retractions/superseding work. Verify recency. | Journal articles, grant proposals, systematic reviews |

A useful heuristic: surface ≈ 1 min/claim, standard ≈ 3-5 min/claim, deep ≈ 10+ min/claim
(in human-equivalent effort terms).

---

## 7. Output mode

What the skill returns to the user.

| Mode | What the user gets |
|------|-------------------|
| **Annotated document** | Full text with references woven in, ready to use |
| **References list only** | Numbered/keyed source list without modifying the original text. Each entry keyed to a passage (by quoting a short phrase or giving location). |
| **Annotation report** | Structured list: passage → suggested source(s) → notes. The user inserts citations themselves. |
| **Diff** | Annotated document with changes marked (strikethrough/bold or diff format) for review before accepting |

Modes can be combined: e.g., annotated document + a summary of unsourceable claims.

---

## 8. Density

How heavily to reference the document. This interacts with citation scope — scope
determines *what* to cite, density determines *how many* to actually cite when multiple
opportunities exist.

| Level | Description | Rough target |
|-------|-------------|--------------|
| **Light** | Only the most critical: key statistics, direct attributions | ~2-4 refs per 1000 words |
| **Moderate** | Most substantive claims; trust the reader on broadly accepted facts | ~5-10 refs per 1000 words |
| **Comprehensive** | Everything defensible gets a citation | ~10-20+ refs per 1000 words |

These are rough guides — the actual number depends heavily on the content. A methods
section is naturally denser than a narrative introduction.

---

## 9. Gap handling

What to do when a claim in the text can't be adequately sourced.

| Strategy | Behavior |
|----------|----------|
| **Flag** | Mark the passage, note that no adequate source was found. Author decides. |
| **Suggest softening** | Propose qualified language: "reportedly", "some evidence suggests", "anecdotally" |
| **Suggest removal** | Recommend cutting unsupported claims (appropriate for high-stakes academic work) |
| **Skip silently** | Don't mention it. Only appropriate for light-touch informal contexts. |
| **Propose alternatives** | Offer a related but sourceable claim that serves the same rhetorical purpose |

Multiple strategies can apply: e.g., flag AND suggest softening.
