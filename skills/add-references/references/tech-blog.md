# Context: Technical Blog Post

Referencing conventions for software engineering, AI/ML, and technology blog posts
published on platforms like Medium, dev.to, company engineering blogs, personal sites,
Substack, or similar.

## Citation format

Use **inline hyperlinks** in markdown. The linked text should be the natural phrase in the
sentence that the reader would want to click on — not "click here" or raw URLs.

**Good:**
```markdown
The [Transformer architecture](https://arxiv.org/abs/1706.03762) introduced the
self-attention mechanism that underpins modern LLMs.
```

**Bad:**
```markdown
The Transformer architecture (see https://arxiv.org/abs/1706.03762) introduced the
self-attention mechanism.
```

**Also bad:**
```markdown
The Transformer architecture [1] introduced the self-attention mechanism.
```

### Link placement principles

- Link the most specific phrase that identifies the referenced concept. "Transformer
  architecture" is better than "introduced" or "self-attention mechanism" as the link
  anchor when referencing the original paper.
- If referencing a tool or library, link on the tool's name to its official docs or repo.
- If referencing a study or paper, link on the finding or the study's description.
- Don't link the same reference more than once per section. First mention only.
- If multiple sources support a single sentence, it's OK to have multiple links, but
  keep it readable. Consider restructuring if a sentence has 3+ links.

### When a references section is appropriate

Most tech blog posts do NOT need a separate references section — inline links are
sufficient. However, add a `## References` or `## Further Reading` section at the end if:

- The post is especially research-heavy (citing 8+ papers)
- Some references are paywalled or hard to access and benefit from annotation
- The author explicitly wants one
- The post is aimed at an academic-adjacent audience (e.g., an ML research blog)

If a references section is used, format entries as:

```markdown
## References

- [Vaswani et al., 2017] A. Vaswani et al. "Attention Is All You Need." *NeurIPS 2017*.
  [arXiv:1706.03762](https://arxiv.org/abs/1706.03762)
- [Brown et al., 2020] T. Brown et al. "Language Models are Few-Shot Learners."
  *NeurIPS 2020*. [arXiv:2005.14165](https://arxiv.org/abs/2005.14165)
```

## Source quality criteria

### Tier 1 — Prefer these (high credibility)

- **Official documentation**: Language/framework docs, API references, specs (e.g.,
  Python docs, RFC documents, W3C specs, OpenAPI spec)
- **Original research papers**: arXiv preprints, conference papers (NeurIPS, ICML, ACL,
  CVPR, etc.), journal articles
- **Official project repos**: GitHub repositories for open-source tools
- **Company engineering blogs from the source**: Google AI Blog, Meta AI, OpenAI blog,
  Anthropic research posts — when they're the ones announcing/explaining their own work
- **Official announcements**: Release notes, changelogs, launch blog posts from the
  project maintainers

### Tier 2 — Good supporting sources

- **Reputable tech publications**: Ars Technica, The Verge (for industry context),
  IEEE Spectrum, ACM Communications
- **Well-known practitioner blogs**: Individual engineers/researchers with established
  credibility in their domain (e.g., Karpathy's blog, Julia Evans, Martin Fowler)
- **Curated references**: Awesome-lists on GitHub (for "landscape" claims), survey papers
- **Stack Overflow answers**: Only for specific technical claims where the answer is
  highly upvoted and authoritative

### Tier 3 — Use sparingly, with care

- **General tech news sites**: TechCrunch, Wired, VentureBeat — OK for market/industry
  claims, not for technical claims
- **Wikipedia**: Acceptable for general background concepts, not as primary source for
  specific claims. Link to Wikipedia's own references when possible.
- **Tutorial sites**: Useful for "how to" claims but verify accuracy
- **Social media posts**: Tweets/posts from authoritative figures can be cited for
  opinions or announcements, but note their ephemeral nature

### Avoid

- Content farms and SEO-optimized listicles
- Undated content with no clear authorship
- Sites that primarily aggregate or rewrite other sources
- Paywalled content with no free alternative (unless it's the definitive source)
- Outdated documentation (check version numbers!)

## Reference density

Tech blog posts should feel **naturally linked, not academic.** A good target:

- Short post (500-1000 words): 3-6 references
- Medium post (1000-2500 words): 6-12 references
- Long/research-heavy post (2500+ words): 10-20 references

These are rough guides. A deeply technical post explaining one algorithm might only need
2-3 references. A survey-style "state of X" post might have 20+.

## Common patterns in tech blogs

### Referencing code and tools

```markdown
We used [FastAPI](https://fastapi.tiangolo.com/) for the API layer and
[SQLAlchemy](https://www.sqlalchemy.org/) for the ORM.
```

Link to official docs or repos, not to tutorials about the tool.

### Referencing performance claims

```markdown
Recent benchmarks show GPT-4 achieves [86.4% on MMLU](https://arxiv.org/abs/2303.08774),
a significant improvement over previous models.
```

Always link to the source of the benchmark, not to commentary about it.

### Referencing concepts with well-known origins

```markdown
The [twelve-factor app](https://12factor.net/) methodology recommends storing config in
environment variables.
```

Link to the canonical source for the concept.

### Referencing a person's idea or statement

```markdown
As Rich Hickey argued in his talk
["Simple Made Easy"](https://www.infoq.com/presentations/Simple-Made-Easy/), simplicity
and ease are fundamentally different properties.
```

Link to the original talk, post, or paper — not to someone else's summary.

## Recency guidelines

- **Libraries/frameworks**: Link to docs for the current stable version. Avoid linking
  to docs for deprecated versions.
- **AI/ML papers**: The field moves fast. If citing a capability claim, check whether
  more recent work has superseded it. Note the date if relevant.
- **Best practices**: These evolve. A 2015 blog post about Docker best practices may be
  significantly outdated. Prefer recent sources or note the age.
- **Standards/specs**: Link to the latest published version unless discussing the history.
