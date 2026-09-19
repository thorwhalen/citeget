---
name: check-submission-fit
description: Assess how well a draft article fits a set of target journals and recommend the best venue. Compares the article's scope, tone, length, audience, and contribution type against journal profiles. Use when deciding where to submit an article.
argument-hint: <article_file_or_dir> [journal1,journal2,...]
allowed-tools: Read, Write, Glob, Grep, WebSearch
---

# Check Article–Journal Fit

Evaluate how well a draft article matches the requirements and culture of one or more journals, and recommend the best submission venue.

## Arguments

- `$0` — Path to the article file or directory (required)
- `$1` — Comma-separated list of journal keys to evaluate (optional; if omitted, evaluates all known journals)
  - `ieee_software` — IEEE Software
  - `cacm_practice` — CACM Practice
  - `cacm_research` — CACM Research and Advances
  - `cacm_viewpoints` — CACM Viewpoints/Opinion
  - `ieee_tse` — IEEE Transactions on Software Engineering
  - `acm_queue` — ACM Queue

## Workflow

### Phase 1: Extract Article Profile

Read the full article and extract:

| Dimension | Value |
|-----------|-------|
| Word count | (count) |
| Abstract word count | (count) |
| Number of references | (count) |
| Number of figures/tables | (count) |
| Primary audience | researchers / practitioners / both / general CS |
| Contribution type | empirical study / tool / experience report / opinion / survey / vision |
| Has methodology section? | yes / no |
| Has evaluation/data? | yes / no |
| Tone | formal/academic / semi-formal / conversational |
| Main domain | SE / systems / PL / AI / security / distributed / general CS |
| Is novel research? | yes / no |
| Industry relevance | high / medium / low |

### Phase 2: Load Journal Profiles

Read `data/journal_profiles.json` from the project directory. For each journal in the evaluation list, extract its profile.

### Phase 3: Score Each Journal

For each journal, score the article-journal fit on 6 dimensions (1=poor, 3=good, 5=excellent):

#### Dimension Scoring Rubric

**1. Scope Match**
- Does the article's subject fall within what this journal covers?
- 5: Core topic of this venue; 3: Adjacent; 1: Out of scope

**2. Contribution Type Match**
- Does the article's type (empirical, opinion, tool, etc.) match what the journal publishes?
- 5: Exact match; 3: Acceptable variant; 1: Mismatch

**3. Audience Match**
- Does the article's assumed audience match the journal's readership?
- 5: Perfect fit; 3: Requires reframing; 1: Wrong audience

**4. Tone Match**
- Is the writing style appropriate for this journal?
- 5: No adjustment needed; 3: Minor tuning; 1: Major rewrite needed

**5. Length/Format Feasibility**
- Can the article be adapted to fit this journal's format requirements with reasonable effort?
- 5: Already fits; 3: Moderate cuts/additions needed; 1: Fundamental restructuring required

**6. Novelty vs. Accessibility Balance**
- Is the article's novelty/depth appropriate for this venue?
- 5: Perfect balance; 3: Slightly off; 1: Too academic for a magazine or too shallow for a journal

#### Adjustment Factors

Apply these as ±1 adjustments to the total:
- `+1` — Article has strong practitioner takeaways (favors IEEE Software, ACM Queue)
- `+1` — Article has rigorous methodology + evaluation (favors IEEE TSE)
- `+1` — Article is broadly accessible to non-SE CS readers (favors CACM)
- `-1` — Article is too long to fit this journal even with cuts
- `-1` — Article is invitation-only and user has no invite (ACM Queue)
- `-1` — Article is primarily about a narrow tool without generalizable lessons (penalizes CACM Research)

### Phase 4: Produce Fit Report

Write a fit report to `output/<article_slug>_fit_report.md`:

```markdown
# Journal Fit Report: <Title>

**Assessed:** <date>
**Article type:** <contribution type>
**Current word count:** <count>

---

## Fit Scores

| Journal | Scope | Type | Audience | Tone | Length | Novelty | Adjustments | **Total** |
|---------|-------|------|----------|------|--------|---------|-------------|-----------|
| IEEE Software | X | X | X | X | X | X | +/-X | **X/30** |
| CACM Practice | X | X | X | X | X | X | +/-X | **X/30** |
| CACM Research | X | X | X | X | X | X | +/-X | **X/30** |
| CACM Viewpoints | X | X | X | X | X | X | +/-X | **X/30** |
| IEEE TSE | X | X | X | X | X | X | +/-X | **X/30** |
| ACM Queue | X | X | X | X | X | X | +/-X | **X/30** |

---

## Recommendation

**Primary recommendation:** <Journal Name> (score: X/30)

<2-3 sentences explaining why this is the best fit>

**Backup recommendation:** <Journal Name> (score: X/30)

<1-2 sentences>

**Not recommended:** <Journal Name> — <reason in one sentence>

---

## What It Would Take

### To submit to <Primary Recommendation>:
- [ ] <specific change 1>
- [ ] <specific change 2>
- [ ] ...

### To submit to <Backup>:
- [ ] <specific change 1>
- [ ] ...

---

## Red Flags

(Anything that would likely trigger a desk rejection or poor peer review at the recommended venue)

- <flag 1>
- <flag 2>

---

## Notes on Specific Journals

<Any other observations about specific journals not captured in scores>
```

## Output

- `output/<article_slug>_fit_report.md` — Journal fit assessment and recommendations

## Decision Guide

Use these heuristics when scores are close:

| Article type | Best primary target | Best backup |
|-------------|---------------------|------------|
| Empirical study with novel findings | IEEE TSE | CACM Research |
| Tool/method with practitioner validation | IEEE Software | CACM Practice |
| Experience report / case study | IEEE Software | CACM Practice |
| Broad vision / position paper | CACM Research | CACM Viewpoints |
| Opinion / argument | CACM Viewpoints | IEEE Software |
| Deep technical practitioner story | ACM Queue (if invited) | IEEE Software |
| Theoretical contribution | IEEE TSE | CACM Research |

## Notes

- Desk rejection is the biggest risk — always prioritize scope and contribution type match
- IEEE Software and CACM Practice are both practitioner-focused but differ: IEEE Software is SE-specific; CACM Practice targets all of CS
- CACM's editorial bar is high even for well-written work — the "why does this matter to all of CS?" test is real
- IEEE TSE reviewers expect rigorous methodology; if there is no evaluation or formal proof, TSE is probably wrong
- ACM Queue is only worth pursuing if the user has an invitation or a very compelling pitch; flag this clearly
