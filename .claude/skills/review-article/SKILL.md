---
name: review-article
description: Review a draft article for academic/technical journal submission. Gives structured feedback on clarity, contribution, structure, novelty, and journal fit. Use when you have a draft article and want an expert critical review before submission.
argument-hint: <article_file_or_dir> [target_journal]
allowed-tools: Read, Write, Glob, Grep, WebSearch
---

# Article Review

Perform a thorough editorial and peer-review style critique of a draft article for journal submission.

## Arguments

- `$0` — Path to the article file (`.md`, `.txt`, `.tex`, or a directory) (required)
- `$1` — Target journal name (optional; e.g. "IEEE Software", "CACM", "IEEE TSE"). If omitted, review for general quality and suggest journals.

## Workflow

### Phase 1: Read and Understand the Article

Read the full article (or all files if a directory is given). Extract:

- **Title and authors**
- **Abstract**
- **Sections / structure**
- **Core claim / contribution**
- **Methodology** (if any)
- **Evidence / examples used**
- **References** (count, recency, diversity)

### Phase 2: Evaluate Against Review Criteria

Assess the article on all of the following dimensions. For each, provide a score (1–5) and specific, actionable comments.

#### 2a. Contribution and Novelty
- What is the central insight or contribution?
- Is it new? Has this been said before (and if so, is it said better here)?
- Would a practitioner or researcher learn something they didn't know?
- Is the problem worth solving / the question worth asking?

#### 2b. Clarity and Writing Quality
- Is the abstract clear and self-contained?
- Is the title accurate and compelling?
- Are section transitions smooth?
- Is terminology defined before use?
- Are sentences and paragraphs concise? (Mark any that are bloated or confusing)
- Is passive voice overused?

#### 2c. Structure and Logic
- Does the introduction set up the problem well?
- Does the conclusion follow from the argument?
- Are claims supported by evidence?
- Is the argument logically consistent throughout?
- Are there unsupported leaps in reasoning?

#### 2d. Technical Depth and Accuracy
- Are technical claims correct?
- Is the methodology sound (for empirical work)?
- Are examples well-chosen and accurate?
- Are limitations acknowledged?

#### 2e. Audience Fit
- Who is this written for? (researchers, practitioners, broad CS audience)
- Is the assumed background appropriate for the target venue?
- Is it too academic for a magazine, or too informal for a journal?

#### 2f. References and Related Work
- Is related work adequately covered?
- Are key references missing?
- Are references recent (within 5 years where appropriate)?
- Are self-citations excessive?

#### 2g. Journal Fit (if target journal specified)
- Load the journal profile from `data/journal_profiles.json` (see below) and apply specific constraints:
  - Does word count fit the limit?
  - Does it match the section's scope (for CACM)?
  - Does it satisfy required elements (e.g., IEEE Software practitioner takeaways)?
  - Is the tone right (practitioner vs. research)?

### Phase 3: Produce the Review Report

Write a review report to `output/<article_slug>_review.md` with this structure:

```markdown
# Article Review: <Title>

**Reviewed:** <date>
**Target Journal:** <journal or "Not specified">
**Article File:** <path>

---

## Summary Judgment

<2-3 sentences: overall assessment and recommended action>

**Recommended action:** Accept / Accept with minor revisions / Major revision needed / Reject and resubmit elsewhere

---

## Dimension Scores

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Contribution & Novelty | X | ... |
| Clarity & Writing | X | ... |
| Structure & Logic | X | ... |
| Technical Depth | X | ... |
| Audience Fit | X | ... |
| References & Related Work | X | ... |
| Journal Fit (if applicable) | X | ... |
| **Overall** | **X** | |

---

## Detailed Feedback

### Strengths
(What the article does well — be specific)

### Critical Issues (Must Fix)
(Problems that would likely cause rejection — numbered list)

### Suggested Improvements
(Enhancements that would strengthen the article — numbered list)

### Line-Level Notes
(Specific paragraphs/sentences with issues — quote the text, then comment)

---

## Journal Fit Assessment

<If target journal specified: detailed analysis of fit, including word count check,
required elements checklist, tone assessment, and recommendation on whether to
target this journal or a different one.>

### Recommended Journals
(If no journal specified, or if current target is wrong — list 2-3 best fits with rationale)

---

## Pre-Submission Checklist

Based on this review, the following items must be addressed before submission:

- [ ] <issue 1>
- [ ] <issue 2>
- [ ] ...
```

## Output

- `output/<article_slug>_review.md` — Full review report

## Journal Profile Reference

To load journal constraints, read `data/journal_profiles.json` in this project directory.
Key profiles:
- `ieee_software` — 4,200 words, 15 refs, 150-word abstract, practitioner takeaways required
- `cacm_practice` — 10 pages, 40 refs, broad audience, practitioner-accessible
- `cacm_research` — 10 pages, 40 refs, innovative ideas
- `ieee_tse` — 12 formatted pages, rigorous research, IEEE 2-col format
- `acm_queue` — 3,500 words, invitation-only, practitioner-focused

## Notes

- Be direct and specific — generic praise or generic criticism is not useful
- Quote actual text when identifying problems
- Distinguish between "must fix" (causes rejection) and "nice to have"
- If the article is genuinely strong, say so clearly — over-critical reviews waste the author's time
- For CACM, test whether a non-specialist could follow the article; this is a key editorial criterion
- For IEEE Software, the three practitioner takeaways must be genuinely actionable, not just restatements of the abstract
