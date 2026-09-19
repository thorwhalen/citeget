# Profile: AI/ML Research — Conferences and Journals

Referencing conventions for machine learning and artificial intelligence research
published at top conferences (NeurIPS, ICML, ICLR, ACL, CVPR, AAAI, etc.) and journals
(JMLR, Artificial Intelligence, TMLR, IEEE TPAMI, etc.).

## Citation format

AI/ML venues overwhelmingly use **author-date (natbib) style**, with flexibility on
the exact format as long as it's internally consistent. The two forms:

**Parenthetical** — when the citation is not part of the sentence grammar:

```markdown
Transformers have become the dominant architecture for NLP (Vaswani et al., 2017)
and have since been applied to vision (Dosovitskiy et al., 2021), audio
(Radford et al., 2023), and multi-modal tasks (Alayrac et al., 2022).
```

**Narrative** — when the author is the grammatical subject:

```markdown
Vaswani et al. (2017) introduced the Transformer architecture, which replaced
recurrence with self-attention. Brown et al. (2020) later demonstrated that
scaling language models to 175B parameters yields strong few-shot performance.
```

Multiple citations: `(Smith et al., 2020; Jones & Lee, 2021; Doe et al., 2022)` —
typically ordered chronologically or by relevance.

Most venues accept any consistent style, but in practice the community has converged on
natbib-style author-date. Numbered `[1]` style is acceptable but less common in ML.

### References section format

Alphabetical by first author surname. Include all authors (no "et al." in the reference
list itself). Conference papers include the venue abbreviation and year:

```markdown
## References

Dosovitskiy, A., Beyer, L., Kolesnikov, A., Weissenborn, D., Zhai, X.,
Unterthiner, T., Dehghani, M., Minderer, M., Heigold, G., Gelly, S.,
Uszkoreit, J., and Houlsby, N. An image is worth 16x16 words: Transformers
for image recognition at scale. In *ICLR*, 2021.

Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N.,
Kaiser, Ł., and Polosukhin, I. Attention is all you need. In *Advances in
Neural Information Processing Systems (NeurIPS)*, 2017.
```

For journal articles, include volume and page numbers. For arXiv-only papers, include
the arXiv ID. Always include URLs or DOIs for reproducibility.

## Source quality criteria

### Tier 1 — Core ML literature

- **Top-venue conference papers**: NeurIPS, ICML, ICLR, ACL, EMNLP, CVPR, ECCV,
  AAAI, IJCAI — these are the primary publication venues in ML (unlike most fields
  where journals dominate, ML is conference-driven)
- **Top journals**: JMLR, TMLR, Artificial Intelligence, IEEE TPAMI, TACL
- **Foundational papers**: Regardless of venue, papers that introduced key concepts
  (backprop, attention, GANs, etc.)

### Tier 2 — Strong supporting sources

- **Workshop papers** from top venues (NeurIPS workshops, ICML workshops) — acceptable
  for very recent work, but check if a full version exists
- **arXiv preprints** — essential in ML. Many landmark results (GPT-4, Llama, etc.)
  are only on arXiv. Always acceptable, but note if not peer-reviewed.
- **Technical reports** from major labs (Google Research, DeepMind, OpenAI, Meta AI,
  Anthropic, Microsoft Research) — de facto primary sources for many systems
- **Survey papers** — valuable for positioning and context

### Tier 3 — Use with care

- **Blog posts from major labs** (Google AI Blog, OpenAI blog, Anthropic research) —
  acceptable for system announcements and capability claims, but prefer the
  accompanying paper when one exists
- **Older conference papers** from less selective venues — check citation count and
  community reception
- **Dissertations** — cite the resulting papers instead when possible

### Avoid

- Blog posts from non-researchers (unless citing for a specific factual claim about
  a product/service)
- Medium articles, tutorials, Stack Overflow (for research claims)
- Wikipedia
- Predatory or pay-to-publish venues (check acceptance rates, editorial board quality)
- Press coverage of research (cite the paper, not the TechCrunch article about it)

## Reference density

ML papers are **moderately to heavily cited**. The field has a strong culture of
positioning work relative to prior art:

- **Introduction**: High density. Motivate the problem, cite the main approaches, and
  clearly state what's new. 10-20 citations in a 1-1.5 page intro is typical.
- **Related work**: Very high density. This section exists specifically to cite and
  discuss prior work. 15-40 citations depending on breadth.
- **Method**: Moderate. Cite the techniques, architectures, and training procedures
  you build on.
- **Experiments**: Cite baselines, benchmarks, datasets, and evaluation metrics.
- **Conclusion/Discussion**: Sparse. Cite future directions if pointing to specific
  open problems.

**Overall**: A typical 8-page ML conference paper (plus unlimited references) has
30-60 references. Some survey-style or empirical papers have 80-100+.

## Common patterns

### Introducing a line of work

```markdown
Large language models (LLMs) have shown remarkable capabilities across a wide
range of tasks (Brown et al., 2020; Chowdhery et al., 2023; Touvron et al.,
2023). Recent work has focused on improving their reasoning abilities through
chain-of-thought prompting (Wei et al., 2022) and reinforcement learning from
human feedback (Ouyang et al., 2022; Bai et al., 2022).
```

### Citing a specific method or architecture

```markdown
Our model builds on the Vision Transformer (ViT) architecture (Dosovitskiy
et al., 2021), using the standard patch embedding and multi-head self-attention
layers. We add a cross-attention module following Alayrac et al. (2022).
```

### Citing benchmarks and datasets

```markdown
We evaluate on MMLU (Hendrycks et al., 2021), GSM8K (Cobbe et al., 2021),
and HumanEval (Chen et al., 2021). Results are reported using pass@k
following the protocol of Chen et al. (2021).
```

### Citing concurrent or very recent work

```markdown
Concurrent with our work, Li et al. (2024) proposed a similar approach using
retrieval-augmented generation. Our method differs in that we...
```

## Recency guidelines

ML moves extremely fast. Recency norms:

- **Benchmarks and SOTA**: Must be current. Citing a 2020 SOTA when a 2024 result
  exists is a significant omission that reviewers will catch.
- **Architectures and techniques**: Cite the original paper regardless of age (e.g.,
  Hochreiter & Schmidhuber, 1997 for LSTM), but also cite recent extensions or the
  version you actually use.
- **Datasets**: Cite the original dataset paper. Note if using a modified version.
- **Scaling results**: These become outdated rapidly. Always cite the most recent
  scaling study if making claims about model capabilities.
- **arXiv preprints**: Check regularly — a paper you cited as a preprint may now be
  published at a venue. Update the citation.

**General rule**: Reviewers expect to see citations from the last 1-2 years. A related
work section with nothing newer than 2022 (as of 2025-2026) signals the authors aren't
current with the literature.

## Special considerations

**Conference-driven field**: Unlike most academic fields, ML's prestige hierarchy is
conference → journal, not the other way around. A NeurIPS paper is typically more
prestigious than a journal publication in all but the top journals (JMLR, TMLR).

**Double-blind submission**: When submitting to double-blind venues (NeurIPS, ICML,
ICLR), refer to your own work in third person: "Smith et al. (2023) showed..." not
"In our prior work (Smith et al., 2023), we showed..." This affects how you write
the citations, not which ones you include.

**arXiv culture**: Posting to arXiv before or simultaneously with conference submission
is standard. Citing arXiv preprints is fully accepted. Include the arXiv ID
(e.g., `arXiv:2301.12345`) for preprints that haven't appeared at a venue.

**Reproducibility citations**: Cite code repositories, datasets, and computational
resources. The ML community increasingly values reproducibility, and reviewers notice
when key implementation details lack citation.

**Software and framework citations**: When using specific frameworks (PyTorch, JAX,
Hugging Face Transformers), cite them. Standard practice:
`(Paszke et al., 2019)` for PyTorch, `(Wolf et al., 2020)` for Transformers.

**Benchmark gaming**: Don't cherry-pick which baselines to compare against. Cite and
compare with the current best results, even if your method doesn't beat them. Reviewers
view selective citation of baselines very negatively.
