# Context: Social Sciences — Journals & Grant Proposals

Referencing conventions for academic papers, journal articles, and grant proposals in the
social and behavioral sciences (psychology, sociology, education, public health, health
services research, etc.). Covers both journal submission and grant applications to funders
like NIH, NSF, ERC, and similar agencies.

## Citation format

Use **Vancouver-style numbered citations** by default. This means:

- Sequential numbers in square brackets `[1]`, `[2]`, etc. placed immediately after the
  claim they support
- A numbered **REFERENCES** section at the end of the document
- Numbers assigned in order of first appearance in the text

### In-text citation placement

Place the citation number:
- After the specific claim, not at the end of the paragraph
- Before the period if the citation applies to the sentence
- After a closing quotation mark if quoting

```markdown
Cognitive behavioral therapy has been shown to be effective for treating anxiety
disorders [1]. However, access to trained therapists remains limited in rural
communities [2], suggesting a need for scalable digital interventions [3,4].
```

Multiple citations for a single claim: `[3,4]` or for a range: `[3-6]`

### References section format

```markdown
## REFERENCES

[1] Smith J, Doe A. Effectiveness of CBT for generalized anxiety disorder: a
meta-analysis. J Clin Psychol. 2021;77(3):456-470. doi:10.1002/jclp.23089

[2] Garcia M, Lee K, Patel R. Mental health service gaps in rural America: a
cross-sectional analysis. Am J Public Health. 2022;112(5):789-798.
doi:10.2105/AJPH.2021.306521

[3] World Health Organization. Mental health and psychosocial support in emergencies
[Internet]. Geneva: WHO; 2023 [cited 2024 Jan 15]. Available from:
https://www.who.int/mental_health/emergencies/en/
```

### When to use APA instead

Some funders or journals explicitly require APA (Author-Date) format. If the user
specifies APA, or if the target journal's guidelines call for it, switch to:

```markdown
Cognitive behavioral therapy has been shown to be effective for treating anxiety
disorders (Smith & Doe, 2021). However, access to trained therapists remains limited
in rural communities (Garcia et al., 2022).
```

With a corresponding alphabetized references section. Ask the user if unclear.

**Key rule: Check the funder's or journal's guidelines.** Many RFPs/FOAs specify a
citation style. NIH and NSF proposals generally accept any consistent style, with
Vancouver or APA being most common in health and social sciences respectively. ERC
proposals similarly accept any consistent format. If no style is specified, default to
Vancouver for health-adjacent work and APA for pure social sciences.

## Source quality criteria

### The evidence hierarchy

In social sciences and health research, sources are evaluated along an evidence hierarchy.
When choosing references, prefer higher-tier evidence where available:

**Tier 1 — Strongest evidence:**
- Systematic reviews and meta-analyses (Cochrane reviews, Campbell Collaboration)
- Randomized controlled trials (RCTs) published in peer-reviewed journals
- Large-scale longitudinal cohort studies

**Tier 2 — Strong evidence:**
- Peer-reviewed journal articles (cross-sectional studies, qualitative research,
  mixed-methods studies) in indexed journals
- Pre-registered studies and replication studies
- Government statistical reports (e.g., CDC, Census Bureau, Eurostat, ONS)
- Reports from major intergovernmental bodies (WHO, OECD, World Bank)

**Tier 3 — Acceptable supporting evidence:**
- Dissertations and theses (especially from well-known programs)
- Conference proceedings and presentations (published abstracts)
- Working papers from recognized institutions (NBER, SSRN, IZA)
- Technical reports from government agencies or NGOs
- Books and book chapters from academic publishers

**Tier 4 — Use cautiously, always with justification:**
- Grey literature: NGO reports, white papers, policy briefs — credibility depends heavily
  on the publishing organization. Apply the AACODS criteria (Authority, Accuracy,
  Coverage, Objectivity, Date, Significance) to evaluate.
- Preprints (not yet peer-reviewed) — acceptable for very recent findings, but flag as
  preprint and check if a published version now exists
- News articles — only for context (e.g., documenting a policy event), never as evidence
  for research claims
- Blogs and opinion pieces — generally avoid, unless written by recognized authorities
  and cited for their perspective, not as evidence

**Avoid entirely:**
- Wikipedia (use it to *find* references, never as the reference itself)
- Predatory journals (check Beall's List, DOAJ status, or journal metrics)
- Undated web content with no clear institutional authorship
- Press releases used as evidence (find the underlying study)
- Social media posts (except when studying social media itself)

### Evaluating source quality

For each reference, consider:

1. **Is it peer-reviewed?** This is the baseline expectation for primary claims.
2. **Is the journal reputable?** Check for impact factor, indexing (PubMed, Scopus, Web
   of Science), and disciplinary standing.
3. **Is the study design appropriate?** A cross-sectional survey cannot establish
   causation, no matter how prestigious the journal.
4. **Is it recent enough?** For prevalence data and policy claims, prefer sources from the
   last 5 years. For foundational theories, seminal older papers are fine.
5. **Is it the original source?** Don't cite a review paper for a specific finding if
   the original study is available. Cite the original, or cite both.
6. **Sample relevance.** A study on college students in the US may not generalize to
   elderly populations in Sub-Saharan Africa. Note when cited evidence has limited
   generalizability.

## Reference density

Academic and grant writing requires higher reference density than other contexts.
Guidelines by section:

### For journal articles

- **Introduction/Background**: High density. Every substantive claim about prior work,
  prevalence, or the state of knowledge should be cited. Typical: 2-4 citations per
  paragraph.
- **Methods**: Cite the original description of validated instruments, scales, or
  analytical techniques. Cite software with version numbers.
- **Results**: Minimal citations — this section reports your findings.
- **Discussion**: Moderate density. Compare findings to prior work, with citations.

### For grant proposals

- **Needs/Problem statement**: Very high density. Every statistic and claim about the
  problem must be cited. Reviewers use citation quality as a proxy for rigor.
- **Background/Significance**: High density. Demonstrate mastery of the literature.
  Cite seminal works and recent advances.
- **Approach/Methods**: Cite evidence supporting your chosen methodology.
  Cite preliminary data from your own prior work (this strengthens the proposal).
- **Innovation**: Moderate. Cite what exists to contrast with what you're proposing.

**Overall target:**
- A 3000-word grant narrative: 30-60 references
- A journal article: 30-80 references depending on article type
- A short policy brief: 10-20 references

## Common patterns

### Establishing the problem (grant proposals)

```markdown
Depression affects approximately 280 million people globally [1], with prevalence rates
rising sharply among adolescents over the past decade [2,3]. In low-resource settings,
fewer than 10% of affected individuals receive adequate treatment [4], a gap that has
widened since the COVID-19 pandemic [5].
```

Note: every quantitative claim gets a citation. This density is expected and valued.

### Citing methodology

```markdown
We will use the Patient Health Questionnaire-9 (PHQ-9) [12], a validated 9-item
self-report measure of depression severity with established psychometric properties
across diverse populations [13,14]. Data will be analyzed using mixed-effects logistic
regression [15] in R version 4.3 (R Foundation for Statistical Computing, Vienna).
```

### Citing theoretical frameworks

```markdown
The intervention is grounded in Social Cognitive Theory [18], which posits that behavior
change occurs through the interplay of personal factors, environmental influences, and
behavioral patterns. This framework has been successfully applied to health behavior
interventions in similar populations [19,20].
```

### Handling conflicting evidence

```markdown
While some studies suggest that digital interventions are as effective as face-to-face
therapy [21,22], others have found significantly lower retention rates in digital-only
formats [23,24]. A recent meta-analysis found moderate effect sizes for digital CBT
(d = 0.56, 95% CI: 0.41-0.71) with significant heterogeneity across studies [25].
```

Present the landscape of evidence, not just the supporting side.

## Special considerations

### Self-citation

In grant proposals, citing the PI's own prior work is expected and strategically
important — it demonstrates expertise and preliminary data. When adding references to a
grant proposal, ask the user if they have prior publications that should be cited, and
note where their own work would strengthen the proposal.

### Recency

- **Prevalence/epidemiological data**: Use the most recent available (< 3-5 years ideal)
- **Foundational theories**: Cite the original plus a recent application
- **Methodological references**: Cite the original description of the method
- **Policy context**: Must be current — cite the latest version of guidelines, laws, etc.

### DOIs and access

- Always include DOIs where available (format: `doi:10.xxxx/xxxxx`)
- For online-only sources, include the full URL and access date
- For government reports, include the publishing agency and report number
- For forthcoming articles, note "in press" and include DOI if available

### Grant-specific funder requirements

- **NIH (US)**: Accepts any consistent citation style. References/bibliography does NOT
  count toward the page limit in most FOAs. Use PubMed citation format (Vancouver) for
  consistency with biomedical convention.
- **NSF (US)**: Accepts any consistent style. References are typically included within
  page limits. Be concise — use abbreviated journal names.
- **ERC (EU)**: Accepts any consistent style. Note: the word limit for ERC proposals is
  strict, so concise citation format matters.
- **NIDA/NIMH (NIH institutes)**: Same as NIH general, but expect heavy citation of
  existing NIH-funded work in the field to demonstrate awareness of the funding
  landscape.
