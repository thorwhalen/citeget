---
name: format-for-journal
description: Reformat and adapt a draft article to meet the specific requirements of a target journal (IEEE Software, CACM, IEEE TSE, etc.). Adjusts structure, word count, abstract, references, and required elements. Use when you have a polished draft and need to produce a journal-ready version.
argument-hint: <article_file_or_dir> <target_journal>
allowed-tools: Read, Write, Edit, Glob, Grep, WebSearch, Bash(python *)
---

# Format Article for Journal Submission

Transform a draft article into a version that meets the specific structural and formatting requirements of a target journal.

## Arguments

- `$0` — Path to the article file (`.md`, `.txt`, `.tex`, or a directory) (required)
- `$1` — Target journal key (required). One of:
  - `ieee_software` — IEEE Software magazine
  - `cacm_practice` — CACM Practice section
  - `cacm_research` — CACM Research and Advances section
  - `cacm_viewpoints` — CACM Viewpoints/Opinion section
  - `ieee_tse` — IEEE Transactions on Software Engineering
  - `acm_queue` — ACM Queue (note: invitation-only, see notes)

## Workflow

### Phase 1: Load Journal Profile

Read `data/journal_profiles.json` from the project directory to get the exact requirements for the target journal. Key dimensions:

- Word/page limit
- Abstract word limit
- Reference limit
- Required sections
- Required elements (takeaways, author bios, etc.)
- Tone (research vs. practitioner vs. broad audience)
- Citation style

### Phase 2: Inventory the Draft

Read the full draft and build an inventory:

- Current word count (use `scripts/count_words.py` or count manually from content)
- Section structure
- Abstract word count
- Number of references
- Figures and tables (each counts as ~250 words for IEEE Software)
- Any journal-specific required elements present or absent

Report the inventory as a table showing current vs. required for each dimension.

### Phase 3: Apply Journal-Specific Transformations

Work through each requirement and transform the article. Create a new file rather than modifying the original.

#### For `ieee_software`:

1. **Word limit (4,200 words + figures @250 each)**
   - Count figures, compute effective budget: `4200 - (num_figures * 250)`
   - If over budget: identify sections to cut; prioritize cutting related work and methodological details that practitioners don't need
   - If well under budget: consider adding a concrete example or figure

2. **Abstract (max 150 words)**
   - Rewrite to be exactly ≤150 words
   - Must describe the overall focus and main takeaway
   - Should not contain abbreviations or citations

3. **References (max 15)**
   - If over 15: identify which references can be merged, cut, or replaced with a more authoritative single source
   - Prioritize: seminal works > recent influential works > online resources
   - Format: IEEE numbered style `[1]`, `[2]`, ...

4. **Practitioner Takeaways (required)**
   - Add a "Practitioner Takeaways" sidebar/section with exactly 3 bullet points
   - Each must be a concrete, actionable insight — not a restatement of the abstract
   - Format:
     ```
     ## Practitioner Takeaways
     - <Specific insight a practitioner can act on>
     - <Specific insight a practitioner can act on>
     - <Specific insight a practitioner can act on>
     ```

5. **Author bio(s) (required)**
   - Add a brief bio (2-3 sentences) for each author
   - Include: current role, research/practice area, contact/email or affiliation

6. **Tone adjustment**
   - Soften heavy academic hedging; practitioners prefer direct statements
   - Replace "it can be argued that" → "this shows that"
   - Ensure code examples or figures are concrete and immediately useful

#### For `cacm_practice` or `cacm_research`:

1. **Page limit (10 pages single-column single-spaced, ~6,000–7,000 words)**
   - Use ACM `acmsmall` template mentally; single-column, generous margins
   - If over budget: tighten related work, shorten examples

2. **References (max 40, alphabetical order)**
   - Format: ACM style — `[AuthorYear]` or numbered alphabetically by first author last name
   - Ensure all references are complete (no "et al." in reference list itself)

3. **Broad audience requirement**
   - CACM's key editorial test: could a computer scientist outside this subfield follow this article?
   - Add a "What problem are we solving?" paragraph early
   - Define all acronyms and jargon
   - Add context that a non-specialist would need

4. **Author statement of relevance** (required at submission)
   - Draft a 1-paragraph statement: "Why does this matter to the computing field? Why is it valuable to CACM readers?"
   - Save this as a separate file: `output/<slug>_cacm_relevance_statement.md`

#### For `cacm_viewpoints`:

1. **Page limit (5 pages, ~3,000 words)**
   - More opinion-forward; less methodology detail needed
   - Strong thesis statement required in first 2 paragraphs

2. **References (max 10)**
   - Be ruthless; only the most essential citations

3. **Point-counterpoint framing** (optional but valued by CACM)
   - If the article takes a position, acknowledge the strongest opposing view and address it

#### For `ieee_tse`:

1. **Page limit (12 formatted pages in IEEE 2-column format)**
   - IEEE 2-column format is denser than single-column; roughly 8,000–10,000 words equivalent
   - Structured abstract preferred: Objective, Methods, Results, Conclusion

2. **References (unlimited, IEEE numbered style)**
   - Ensure all references include venue, volume, issue, pages
   - Self-citations: list and review for appropriateness

3. **Replication package note** (strongly recommended)
   - Add a Data Availability statement if the work has associated data, code, or artifacts

4. **Rigor markers**
   - Ensure threats to validity section exists (for empirical work)
   - Ensure limitations are explicitly stated

#### For `acm_queue`:

Note: ACM Queue is invitation-only. The formatted version here is for reference or after receiving an invitation.

1. **Word limit (~3,500 words)**
   - Conversational, problem-focused narrative
   - Cut all hedging language; Queue readers are senior engineers who want directness

2. **No rigid section structure**
   - Problem → Challenge → Insight arc, not Introduction/Related Work/Methodology/Conclusion

3. **Tone**
   - Write as if explaining to a colleague at a whiteboard
   - Include real war stories, production numbers, failure modes

### Phase 4: Generate the Formatted Output

Write the transformed article to:
`output/<article_slug>_<journal_key>.md`

Also generate a **change summary** documenting what was modified:
`output/<article_slug>_<journal_key>_changes.md`

Change summary format:
```markdown
# Formatting Changes: <Title> → <Journal>

**Original word count:** X
**Formatted word count:** X (target: X)

## Changes Made

### Structural Changes
- <what was added/removed/moved>

### Abstract
- <original word count> → <new word count>
- <key changes>

### References
- <original count> → <new count>
- <references removed: list titles>

### Added Required Elements
- <list any newly added required sections>

### Tone Adjustments
- <key phrasing changes>

## What Still Needs Human Review

- <list any decisions that require author judgment>
- <any sections where cuts were made that author should verify>
```

## Output Files

1. `output/<article_slug>_<journal_key>.md` — Reformatted article
2. `output/<article_slug>_<journal_key>_changes.md` — Change summary
3. `output/<article_slug>_cacm_relevance_statement.md` — (CACM only) Relevance statement

## Notes

- Never delete content from the original; create a new file
- When cutting for word count, preserve the core argument — cut supporting material, not the thesis
- If cuts are ambiguous, leave a `<!-- AUTHOR: consider cutting this section -->` comment
- The formatted output is a starting point — always review with the author before submission
- LaTeX formatting is outside the scope of this skill; this produces clean markdown that can be pasted into a LaTeX template
- Use `scripts/count_words.py` to get accurate word counts
