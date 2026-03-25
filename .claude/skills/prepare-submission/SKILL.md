---
name: prepare-submission
description: Prepare all materials for journal submission and generate a step-by-step submission guide. Creates a submission checklist, cover letter, author metadata, and submission instructions specific to the target journal. Use when an article is ready and you need to actually submit it.
argument-hint: <article_file_or_dir> <target_journal> [author_info_file]
allowed-tools: Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Bash(python *)
---

# Prepare Article for Submission

Assemble all required submission materials and produce a step-by-step submission guide for a specific journal.

## Arguments

- `$0` — Path to the article file or formatted article directory (required)
- `$1` — Target journal key (required): `ieee_software`, `cacm_practice`, `cacm_research`, `cacm_viewpoints`, `ieee_tse`, `acm_queue`
- `$2` — Path to an author info file (optional; if present, read it to populate author metadata, affiliations, and bio)

## Workflow

### Phase 1: Load Requirements

Read `data/journal_profiles.json` for the target journal. Collect:

- Submission portal URL
- Required files at submission
- Required metadata fields
- Author requirements (bio, photo, ORCID, etc.)
- Cover letter requirements
- Any pre-submission steps (e.g., email EiC for IEEE Software)

### Phase 2: Verify Article Completeness

Read the article and verify the following are present and correct. Flag any that are missing.

#### Universal requirements:
- [ ] Title (clear and informative)
- [ ] Author name(s) and affiliation(s)
- [ ] Abstract (within word limit)
- [ ] Keywords (3–5)
- [ ] All section headers
- [ ] All figures/tables have captions
- [ ] All references are complete (title, venue, year, pages or DOI)
- [ ] All in-text citations match the reference list
- [ ] No broken `[ref]` or `TODO` markers

#### Journal-specific requirements:

**ieee_software:**
- [ ] Practitioner Takeaways (3 bullets)
- [ ] Author bio(s)
- [ ] Author photo(s) ready
- [ ] Word count ≤ 4,200 (plus figures)
- [ ] References ≤ 15
- [ ] Abstract ≤ 150 words

**cacm_practice / cacm_research:**
- [ ] Relevance statement prepared (separate document)
- [ ] Within page/word limit
- [ ] References in ACM style (alphabetical)
- [ ] Abstract present

**cacm_viewpoints:**
- [ ] Opinion/thesis clearly stated in first 2 paragraphs
- [ ] Within 5-page limit (~3,000 words)
- [ ] References ≤ 10

**ieee_tse:**
- [ ] Structured abstract (Objective, Methods, Results, Conclusion)
- [ ] Within 12 formatted-page limit
- [ ] All citations in IEEE numbered format
- [ ] Data availability statement (if applicable)
- [ ] Conflict of interest statement
- [ ] Funding acknowledgment (if applicable)

**acm_queue:**
- [ ] Invitation or prior editorial contact established (flag if not)
- [ ] Conversational tone throughout
- [ ] Within 3,500 words

### Phase 3: Produce the Cover Letter

Draft a cover letter to `output/<slug>_cover_letter.md`.

Cover letter structure:
```markdown
# Cover Letter

**Date:** <date>
**Journal:** <full journal name>
**Editor-in-Chief / Editors:** <name(s) if known from journal profile>

---

Dear Editor(s),

**Opening (1 paragraph):**
Introduce the article by title, state the submission type (e.g., "Feature article for consideration in IEEE Software"), and give a one-sentence statement of the core contribution.

**What the article contributes (1-2 paragraphs):**
- The problem it addresses
- The approach/insight
- Why it matters to this journal's readership

**Why this journal (1 paragraph):**
Explicitly connect the article to the journal's stated scope, recent relevant articles, or editorial priorities. Show you know the venue.

**Confirmation statements (bullet list):**
- The work is original and not under review elsewhere
- All co-authors have approved the submission
- Competing interests: [none / state if any]
- Funding: [acknowledge if applicable]

**Closing:**
Standard professional closing with contact info.

Sincerely,
<Author Name>
<Affiliation>
<Email>
<Date>
```

### Phase 4: Generate Submission Package Index

Create `output/<slug>_submission_package/` and list all files to include:

For each required file, either confirm it exists or note it needs to be created:

| File | Status | Notes |
|------|--------|-------|
| Main manuscript | ✅ exists / ❌ needs formatting | `<path>` |
| Cover letter | ✅ generated | `output/<slug>_cover_letter.md` |
| Author bios | ✅ in manuscript / ❌ missing | |
| Author photos | ❌ manual step — gather headshots | |
| Relevance statement | (CACM only) | |
| Data/code supplement | (if applicable) | |

### Phase 5: Produce Step-by-Step Submission Guide

Write a detailed, journal-specific submission guide to `output/<slug>_submission_guide.md`:

---

#### IEEE Software Submission Guide

```markdown
# Submission Guide: IEEE Software

**Portal:** https://ieee.atyponrex.com/journal/sw-cs
**Estimated time:** 30–60 minutes

## Pre-submission (recommended)
1. Email abstract to Editor-in-Chief at sigrid.eldh@ieee.org
   - Subject: "Pre-submission inquiry: <Your Title>"
   - Include: 150-word abstract + one paragraph on why it fits IEEE Software
   - Wait for confirmation before submitting (~1-2 weeks typical response)

## Account Setup
2. Go to https://ieee.atyponrex.com/journal/sw-cs
3. Click "Submit a Manuscript"
4. Log in with your IEEE account (or create one at ieee.org)

## Submission Steps
5. Select Article Type: "Feature Article"
6. Enter manuscript metadata:
   - Title
   - Abstract (≤150 words, paste from cover letter)
   - Keywords (3-5)
   - All author names, affiliations, and emails
7. Upload files in this order:
   a. Main manuscript (Word .docx or PDF; LaTeX is acceptable)
   b. Author photos (one per author, 300 DPI minimum, JPEG/PNG)
   c. Any supplementary figures as separate high-resolution files
8. Enter practitioner takeaways in the designated field (if separate from manuscript)
9. Confirm no competing interests or funding declarations
10. Review the submission preview
11. Click "Submit"

## After Submission
- You will receive an automated confirmation email with a manuscript ID
- First editorial decision typically takes 4–8 weeks
- Track status at the same portal under "My Submissions"
```

---

#### CACM Submission Guide

```markdown
# Submission Guide: CACM (<Section>)

**Portal:** https://mc.manuscriptcentral.com/cacm
**Estimated time:** 30–45 minutes

## Pre-submission
1. Review author guidelines at https://cacm.acm.org/author-guidelines/
2. Confirm which section you are targeting (Practice, Research, Viewpoints)
3. Prepare your relevance statement (why this matters to all of CS)

## Submission Steps
4. Go to https://mc.manuscriptcentral.com/cacm
5. Log in or create an ACM account
6. Click "Submit New Manuscript"
7. Select Section Type: <Practice / Research and Advances / Viewpoints>
8. Enter metadata:
   - Title
   - Abstract
   - 3–5 keywords
   - All author info
9. Paste your relevance statement in the "Cover Letter" field
10. Upload:
    a. Main manuscript (PDF, Word, or LaTeX)
    b. Figures as separate files (TIFF or high-res PNG preferred)
11. Complete the required fields (conflicts of interest, funding)
12. Review and submit

## After Submission
- Confirmation email from Manuscript Central
- Initial editorial review: 4–6 weeks
- If invited to revise: typically 60-day turnaround requested
```

---

#### IEEE TSE Submission Guide

```markdown
# Submission Guide: IEEE Transactions on Software Engineering

**Portal:** https://www.computer.org/csdl/journal/ts/write-for-us/15090
**Portal type:** IEEE Author Portal / ScholarOne
**Estimated time:** 45–60 minutes

## Pre-submission
1. Review TSE author guidelines: https://www.computer.org/csdl/journal/ts/write-for-us/15090
2. Confirm manuscript is in IEEE two-column format
3. Write a structured abstract (Objective / Methods / Results / Conclusion)
4. Prepare conflict-of-interest and data availability statements

## Submission Steps
5. Go to the TSE submission portal (link on the write-for-us page)
6. Create/log in to your IEEE account
7. Start new submission
8. Enter:
   - Article type: Research Paper / Survey / Letter
   - Title, abstract, keywords
   - All co-author information and ORCID numbers
9. Upload:
    a. Manuscript (LaTeX preferred; Word acceptable) — with figures embedded
    b. Separate source files if using LaTeX
10. Enter conflict-of-interest statement
11. Enter data availability statement
12. Submit for review

## After Submission
- Automated confirmation with manuscript ID
- Peer review typically takes 3–6 months
- Decision: Accept / Major revision / Minor revision / Reject
- Revisions tracked in the same system
```

---

### Phase 6: Final Pre-flight Check

Run `scripts/check_article.py <article_file> <journal_key>` (if available) to get an automated word count and formatting check. Report results.

If the script is not available, manually verify:
- [ ] Word count within limit
- [ ] Abstract within limit
- [ ] References within limit and properly formatted
- [ ] All required elements present

## Output Files

```
output/<article_slug>_submission_package/
├── <article_slug>_cover_letter.md        # Cover letter draft
├── <article_slug>_submission_guide.md    # Step-by-step submission instructions
├── <article_slug>_preflight_report.md    # Checklist and any remaining issues
└── (links/refs to formatted article and other files)
```

## Notes

- The cover letter is as important as the manuscript for magazine submissions — editors use it to quickly decide whether to send to review
- Never submit to multiple journals simultaneously (simultaneous submission is an ethics violation; flag this clearly)
- If the pre-submission email to IEEE Software EiC yields no response after 2 weeks, it is acceptable to submit directly
- ACM Queue: if the user does not have an invitation, draft an editorial pitch instead of a full submission guide
- For IEEE TSE: ORCID numbers for all authors are strongly recommended; some journals now require them
