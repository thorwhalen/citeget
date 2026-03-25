"""Tests for citeget.resolve — URL resolution and download strategies."""

from citeget.resolve import (
    list_resolvers,
    list_downloaders,
    list_strategies,
    RESOLVERS,
    STRATEGIES,
    BUILTIN_URL_RULES,
    url_rewriter,
    chain,
    chain_resolvers,
    resolve_and_download,
    _rewrite_arxiv,
    _rewrite_openreview,
    _rewrite_pmc,
    _rewrite_biorxiv,
    _rewrite_ssrn,
    _rewrite_acm,
    _rewrite_ieee,
    _rewrite_siam,
    _rewrite_springer,
)
from citeget.acquire_references import Reference


# -- URL rewrite rules --


def test_rewrite_arxiv_abs():
    assert _rewrite_arxiv("https://arxiv.org/abs/2312.17175") == \
        "https://arxiv.org/pdf/2312.17175.pdf"


def test_rewrite_arxiv_already_pdf():
    assert _rewrite_arxiv("https://arxiv.org/pdf/2312.17175.pdf") == \
        "https://arxiv.org/pdf/2312.17175.pdf"


def test_rewrite_openreview():
    assert _rewrite_openreview("https://openreview.net/forum?id=abc123") == \
        "https://openreview.net/pdf?id=abc123"


def test_rewrite_pmc():
    result = _rewrite_pmc("https://ncbi.nlm.nih.gov/pmc/articles/PMC1234567")
    assert result == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/pdf/"


def test_rewrite_biorxiv():
    result = _rewrite_biorxiv("https://www.biorxiv.org/content/10.1101/2024.01.01")
    assert result.endswith(".full.pdf")


def test_rewrite_biorxiv_already_pdf():
    url = "https://www.biorxiv.org/content/10.1101/2024.01.01.full.pdf"
    assert _rewrite_biorxiv(url) == url


def test_rewrite_ssrn():
    result = _rewrite_ssrn("https://ssrn.com/abstract=4567890")
    assert "4567890" in result
    assert "Delivery.cfm" in result


def test_rewrite_acm():
    result = _rewrite_acm("https://dl.acm.org/doi/10.1145/12345")
    assert "/doi/pdf/" in result


def test_rewrite_acm_already_pdf():
    url = "https://dl.acm.org/doi/pdf/10.1145/12345"
    assert _rewrite_acm(url) == url


def test_rewrite_ieee():
    result = _rewrite_ieee("https://ieeexplore.ieee.org/document/9876543")
    assert "9876543" in result
    assert "getPDF" in result


def test_rewrite_siam():
    result = _rewrite_siam("https://epubs.siam.org/doi/10.1137/20M1372652")
    assert "/doi/pdf/" in result


def test_rewrite_springer():
    result = _rewrite_springer("https://link.springer.com/article/10.1007/s00373-014-1465-6")
    assert "/content/pdf/" in result


# -- Registry --


def test_registries_populated():
    assert "url_rewriter" in list_resolvers()
    assert "doi" in list_resolvers()
    assert "arxiv_search" in list_resolvers()
    assert "pdf" in list_downloaders()
    assert "any" in list_downloaders()
    assert "default" in list_strategies()
    assert "direct" in list_strategies()
    assert "libgen" in list_strategies()


def test_builtin_url_rules():
    assert "arxiv.org" in BUILTIN_URL_RULES
    assert "openreview.net" in BUILTIN_URL_RULES
    assert "ncbi.nlm.nih.gov/pmc" in BUILTIN_URL_RULES
    assert "biorxiv.org" in BUILTIN_URL_RULES
    assert "dl.acm.org" in BUILTIN_URL_RULES
    assert "link.springer.com" in BUILTIN_URL_RULES


# -- url_rewriter resolver --


def test_url_rewriter_arxiv():
    resolver = url_rewriter()
    ref = Reference(number=1, raw="test", url="https://arxiv.org/abs/2312.17175")
    urls = resolver(ref)
    assert "https://arxiv.org/pdf/2312.17175.pdf" in urls
    assert "https://arxiv.org/abs/2312.17175" in urls  # original as fallback


def test_url_rewriter_no_url():
    resolver = url_rewriter()
    ref = Reference(number=1, raw="test", url="")
    assert resolver(ref) == []


def test_url_rewriter_custom_rules():
    rules = {"myrepo.org": lambda u: u.replace("/view/", "/download/")}
    resolver = url_rewriter(rules=rules)
    ref = Reference(number=1, raw="test", url="https://myrepo.org/view/paper123")
    urls = resolver(ref)
    assert "https://myrepo.org/download/paper123" in urls


# -- Composition --


def test_chain_strategies():
    def fail(ref, fp):
        return None

    def succeed(ref, fp):
        return "/tmp/success.pdf"

    chained = chain(fail, succeed)
    ref = Reference(number=1, raw="test")
    from pathlib import Path
    result = chained(ref, Path("/tmp/test.pdf"))
    assert result == "/tmp/success.pdf"


def test_chain_resolvers_deduplicates():
    r1 = lambda ref: ["http://a.com", "http://b.com"]
    r2 = lambda ref: ["http://b.com", "http://c.com"]
    combined = chain_resolvers(r1, r2)
    ref = Reference(number=1, raw="test")
    urls = combined(ref)
    assert urls == ["http://a.com", "http://b.com", "http://c.com"]
