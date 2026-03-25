---
name: research-topic
description: Research a technical or academic topic in depth to support article writing. Finds key papers, surveys the state of the art, identifies competing approaches, and produces a research brief with citations. Use when preparing to write an article and needing to understand the landscape and find references.
argument-hint: <topic> [output_dir] [target_journal]
allowed-tools: Read, Write, Glob, Grep, WebSearch, WebFetch, Task
---

# Topic Research for Article Writing

Research a topic deeply to support writing a technical or academic article, with a focus on what has been published and what gaps remain.

## Arguments

- `$0` — The topic to research (required; can be a short phrase or a question, e.g. "LLM-based code generation for embedded systems" or "does pair programming improve code quality?")
- `$1` — Output directory (optional; defaults to `output/<topic_slug>/`)
- `$2` — Target journal (optional; shapes the depth and style of research — practitioner vs. research)

## Workflow

### Phase 1: Understand the Topic

Break the topic down into:

1. **Core concept** — What is the subject?
2. **Key sub-questions** — What specific aspects need to be covered?
3. **Key terms** — What search terms will find the best material?
4. **Competing framings** — Are there different schools of thought?

### Phase 2: Literature Search

Search for material systematically. For each category below, run 2–4 targeted searches.

#### 2a. Foundational Papers and Surveys
Search: `<topic> survey`, `<topic> review`, `<topic> overview`
Look for papers with >100 citations or from top venues (ICSE, FSE, ISSTA, PLDI, OOPSLA, etc.)

#### 2b. Recent Work (last 3 years)
Search: `<topic> 2024`, `<topic> 2025`, `<topic> 2026`
Focus on novel results, tools, datasets, benchmarks.

#### 2c. Practical/Industry Angle
Search: `<topic> industry`, `<topic> practice`, `<topic> case study`
Especially important for IEEE Software and CACM Practice submissions.

#### 2d. Contrarian or Critical Views
Search: `<topic> limitations`, `<topic> criticism`, `<topic> failure`, `<topic> challenges`
A strong article acknowledges the limits of the approach.

#### 2e. Tools, Benchmarks, Datasets
Search: `<topic> tool`, `<topic> benchmark`, `<topic> dataset`, `<topic> open source`

### Phase 3: Read and Extract

For the top 5–10 most relevant sources found, use WebFetch to read abstracts and key sections.

Extract for each source:
- Title, authors, year, venue
- Key claim / contribution
- Methodology (if applicable)
- Key findings / numbers
- Limitations
- Relation to the target article topic

### Phase 4: Identify the Gap

After surveying the landscape, identify:

1. **What is well-established** — broadly accepted, widely replicated
2. **What is actively debated** — multiple competing approaches, no consensus
3. **What is missing** — topics not covered, approaches not tried, questions not asked
4. **Where the article fits** — how the author's contribution relates to the above

### Phase 5: Produce Research Brief

Write a research brief to `output/<topic_slug>/<topic_slug>_research_brief.md` with this structure:

```markdown
# Research Brief: <Topic>

**Prepared:** <date>
**Target journal:** <journal or "General">
**Topic query:** <original topic phrase>

---

## 1. Topic Overview

<2-3 paragraphs explaining the topic, why it matters, and how it is typically studied>

## 2. Key Concepts and Terminology

| Term | Definition | First use |
|------|-----------|-----------|
| ... | ... | ... |

## 3. Foundational Work

| Paper/Work | Authors | Year | Contribution | Venue |
|-----------|---------|------|-------------|-------|
| ... | ... | ... | ... | ... |

## 4. State of the Art (Recent Work)

| Paper/Work | Authors | Year | Contribution | Key Result |
|-----------|---------|------|-------------|-----------|
| ... | ... | ... | ... | ... |

## 5. Industry / Practitioner Perspective

<What practitioners know/believe about this topic; what tools exist; what problems remain unsolved in practice>

## 6. Key Debates and Open Questions

(What is contested? What has been tried and failed?)

## 7. The Gap — Where New Work Fits

<What is missing that a new article could contribute>

## 8. Suggested Related Work to Cite

(Organized by section/argument of a potential article)

## 9. Sources

| # | Title | URL / Reference | Year | Notes |
|---|-------|----------------|------|-------|
| ... | ... | ... | ... | ... |
```

### Phase 6: (Optional) Search for Competing Submissions

If time permits, search for recent arXiv preprints or workshop papers on this topic to check whether very similar work has already been published recently:
- Search: `arxiv <topic> 2025`, `arxiv <topic> 2026`

## Output

- `output/<topic_slug>/<topic_slug>_research_brief.md` — Research brief with structured findings and citations

## Notes

- Prioritize papers from top-tier venues (ICSE, FSE, PLDI, SOSP, etc.) and IEEE/ACM publications
- For IEEE Software and CACM Practice, spend more time on the industry/practitioner angle; these editors expect work grounded in real-world experience
- For IEEE TSE, cover methodology and related work in depth — reviewers expect comprehensive literature awareness
- If the user's core claim is already well-established in the literature, flag this prominently — it means the framing or contribution needs sharpening
- Use the `data/journal_profiles.json` file in this project to understand what each journal values
