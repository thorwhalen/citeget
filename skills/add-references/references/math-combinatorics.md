# Profile: Mathematics — Combinatorics, Graph Theory, Discrete Math

Referencing conventions for academic papers in combinatorics, graph theory, extremal
combinatorics, algebraic combinatorics, and related areas of discrete mathematics.
Covers journals like *Journal of Combinatorial Theory (A/B)*, *Journal of Graph Theory*,
*Graphs and Combinatorics*, *Combinatorica*, *Discrete Mathematics*, *SIAM Journal on
Discrete Mathematics*, *European Journal of Combinatorics*, and the *Electronic Journal
of Combinatorics*.

## Citation format

Mathematics journals vary, but the dominant convention in combinatorics is **numbered
citations in square brackets**, assigned in order of appearance or alphabetically
depending on the journal:

- **Order of appearance** (Vancouver-like): `[1]`, `[2]`, `[3]` — used by *J. Graph
  Theory*, *Combinatorial Press* journals, some Elsevier journals
- **Alphabetical numbering**: References listed alphabetically, numbers reflect that
  order — used by many Springer journals (*Graphs and Combinatorics*, *Combinatorica*)

Both use `[N]` in running text. When the author's name is part of the sentence, write
it out:

```markdown
Erdős and Rényi [7] proved that the threshold for connectivity in G(n,p) is
p = (ln n)/n. This was later extended by Bollobás [3], who showed that...
```

When citing without naming the author:

```markdown
The chromatic number of a random graph satisfies χ(G(n,1/2)) = Θ(n/log n) [1].
```

Multiple citations: `[3, 7, 12]` or `[3–5]` for consecutive numbers.

### References section format

Follow the target journal. The most common format in combinatorics:

```markdown
## References

[1] N. Alon and J.H. Spencer, The Probabilistic Method, 4th ed., Wiley, 2016.

[2] B. Bollobás, Random Graphs, 2nd ed., Cambridge University Press, 2001.

[3] P. Erdős and A. Rényi, On random graphs I, Publ. Math. Debrecen 6 (1959),
    290–297.

[4] L. Lovász, Large Networks and Graph Limits, AMS Colloquium Publications,
    vol. 60, American Mathematical Society, 2012.

[5] R. Diestel, Graph Theory, 5th ed., Springer GTM 173, 2017.
```

Key conventions: author initials before surname, journal names often abbreviated (but
not always), volume number in bold or followed by year in parentheses, page range.
Book references include publisher and year, sometimes series.

**When in doubt**, check the target journal's author guidelines or recent published
papers — formatting varies enough between journals that matching the specific venue
matters.

## Source quality criteria

### Tier 1 — Core mathematical literature

- **Peer-reviewed journal articles** in recognized combinatorics/discrete math journals
- **Published books** from academic publishers (Springer, Cambridge, AMS, Wiley)
  — especially standard references (Diestel, Bollobás, Alon & Spencer, Lovász)
- **Conference proceedings** from top venues when the paper hasn't appeared as a journal
  article (though math prefers journals over conferences)

### Tier 2 — Accepted mathematical sources

- **arXiv preprints** — widely accepted in mathematics as near-primary sources. Many
  important results circulate on arXiv for years before (or instead of) journal
  publication. Always check if a journal version exists and cite that if so.
- **Lecture notes** by recognized mathematicians (e.g., published course notes,
  Bourbaki-style)
- **Survey articles** in journals or edited volumes
- **PhD dissertations** from strong programs

### Tier 3 — Supplementary

- **MathOverflow / Math StackExchange** answers — acceptable for attribution of folklore
  results or pointers to literature, but cite the actual paper, not the MO answer
- **Personal communications** — traditional in math ("Erdős, personal communication");
  use sparingly and only for unpublished results
- **OEIS (Online Encyclopedia of Integer Sequences)** — cite for sequence identification

### Avoid

- Wikipedia (use it to find references, never cite it)
- Textbooks aimed at undergraduates (unless they're the standard reference for a result)
- Blog posts (unless by a recognized mathematician and the result isn't published elsewhere)
- AI-generated proofs or results without human verification

## Reference density

Mathematics papers are **moderately cited** compared to social sciences — the emphasis is
on proof, not on literature coverage. Typical density:

- **Introduction**: Moderate. Cite the main prior results you're building on, and the
  problem's origin. Usually 5-15 citations in a 1-2 page intro.
- **Preliminaries**: Cite sources for notation, definitions, or lemmas borrowed from
  elsewhere.
- **Main results/proofs**: Sparse. Cite only when using a specific lemma or technique
  from another paper.
- **Discussion/remarks**: Moderate. Cite related problems, open questions, and
  connections to other work.

**Overall**: A typical 15-20 page combinatorics paper has 15-35 references. Quality
and precision matter far more than quantity.

## Common patterns

### Citing a foundational result

```markdown
The Szemerédi Regularity Lemma [23] provides an approximate structural
decomposition of dense graphs. Its applications to extremal graph theory
were developed extensively by Komlós and Simonovits [15].
```

### Citing a technique you're using

```markdown
We apply the deletion method (see, e.g., [2, Ch. 4]) to obtain a lower
bound on the independence number.
```

### Citing for a known bound or conjecture

```markdown
The conjecture that every planar graph is 4-choosable was proved by
Thomassen [25] for 5-choosability and remains open in the 4-list case.
It is known that χ_l(G) ≤ 5 for all planar G [25].
```

### Referencing standard notation or definitions

```markdown
We follow the notation of Diestel [5] throughout. In particular, G = (V,E)
denotes a simple undirected graph, and we write δ(G) for the minimum degree.
```

## Recency guidelines

- **Foundational results**: Often decades old. Citing Ramsey (1930), Erdős-Rényi (1959),
  or Szemerédi (1975) is normal and expected.
- **State-of-the-art bounds**: Cite the most recent improvement. If a bound was
  improved last year, cite the new paper, not the 20-year-old one.
- **Survey/textbook references**: Prefer the most recent edition.
- **arXiv preprints**: Check if a journal version has appeared since the preprint.
  Cite the journal version when available.

## Special considerations

**Attribution culture**: Mathematics has strong norms around proper attribution. If a
result is "well known" or "folklore," either cite where it first appeared or write
"it is well known that..." — don't cite it as if you proved it.

**Proofs vs. results**: When citing a result, be precise about what you're using. "By
Theorem 3.1 of [12]" is better than just "[12]" when you need a specific statement.

**arXiv norms**: In combinatorics, citing an arXiv preprint is standard practice. But
always include the arXiv identifier (e.g., `arXiv:2301.12345`) and check whether a
published version exists.

**Self-citation**: Expected when building on your own prior work. Don't avoid it — the
mathematical community values clear lineage of results.

**Proof verification**: Every cited result used in your proof should be one you've
verified or one from a source you trust. Citing an unverified preprint as a lemma in
your proof is risky.
