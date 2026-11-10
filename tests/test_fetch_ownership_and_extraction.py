"""Regression tests for gaps found by reviewing thorwhalen/citeget#33 against main.

#33 implemented #29/#30/#31 in parallel with main. Each test here pins a
behaviour #33 had and main lacked: file ownership across a run and across
naming schemes, ``Retry-After``, site names in titles, and extraction cases
(code comments, state classes, sibling sections, Wayback link forms).
"""

import importlib
import inspect
from types import SimpleNamespace

import pytest
import requests

from citeget import cli
from citeget.content import main_content, page_title

fetch_mod = importlib.import_module("citeget.fetch")

PROSE = "This sentence is long enough to count as a paragraph of real prose. " * 2


def _main_md(html, url=""):
    return fetch_mod.html_to_markdown(html, source_url=url, content="main")


@pytest.fixture
def serve(monkeypatch):
    """Serve ``{url: html-or-pdf-bytes}`` instead of the network."""

    def _serve(pages):
        def _get(url, **_):
            body = pages[url]
            if isinstance(body, bytes):
                return SimpleNamespace(
                    headers={"content-type": "application/pdf"}, text="", content=body
                )
            return SimpleNamespace(
                headers={"content-type": "text/html"}, text=body, content=b""
            )

        monkeypatch.setattr(fetch_mod, "_http_get", _get)

    return _serve


# --- ownership of output files ----------------------------------------------


def test_rerun_over_a_folder_with_old_names_skips_instead_of_duplicating(
    serve, tmp_path
):
    """A file saved under an older naming scheme is found by its Source header."""
    url = "http://paulgraham.com/hp.html"
    serve({url: f"<title>Hackers and Painters</title><p>{PROSE}</p>"})
    (tmp_path / "hp.md").write_text(f"<!-- Source: {url} -->\n\nold copy\n")

    [result] = fetch_mod.fetch([url], output_dir=tmp_path)

    assert result.status == "skipped" and result.output_file.name == "hp.md"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hp.md"]


def test_rerun_without_skip_overwrites_the_old_named_file(serve, tmp_path):
    url = "http://paulgraham.com/hp.html"
    serve({url: f"<title>Hackers and Painters</title><p>{PROSE}</p>"})
    (tmp_path / "hp.md").write_text(f"<!-- Source: {url} -->\n\nold copy\n")

    [result] = fetch_mod.fetch([url], output_dir=tmp_path, skip_existing=False)

    assert result.status == "ok" and result.output_file.name == "hp.md"
    assert "old copy" not in result.output_file.read_text()


def test_two_pdfs_with_the_same_name_in_one_run_both_land(serve, tmp_path):
    """PDFs record no source, so only the run's own claims keep them apart."""
    a, b = "http://a.com/x/paper.pdf", "http://b.com/y/paper.pdf"
    serve({a: b"%PDF-1.4 AAAA", b: b"%PDF-1.4 BBBB"})

    results = fetch_mod.fetch([a, b], output_dir=tmp_path)

    assert [r.status for r in results] == ["ok", "ok"]
    assert {r.output_file.read_bytes() for r in results} == {
        b"%PDF-1.4 AAAA",
        b"%PDF-1.4 BBBB",
    }


def test_same_title_query_variants_get_readable_names(serve, tmp_path):
    base = "http://example.com/magazine/consider_the_lobster?currentPage="
    pages = {
        f"{base}{i}": f"<title>Consider the Lobster</title><p>{PROSE} page {i}</p>"
        for i in (1, 2, 3)
    }
    serve(pages)

    names = [
        r.output_file.name for r in fetch_mod.fetch(list(pages), output_dir=tmp_path)
    ]

    assert names == [
        "consider-the-lobster.md",
        "consider-the-lobster-currentpage-2.md",
        "consider-the-lobster-currentpage-3.md",
    ]


# --- Retry-After --------------------------------------------------------------


def _busy(retry_after):
    resp = requests.Response()
    resp.status_code = 503
    resp.headers["retry-after"] = retry_after
    resp.url = "http://example.com/"
    return resp


def _ok():
    resp = requests.Response()
    resp.status_code = 200
    resp._content = b"<p>ok</p>"
    return resp


@pytest.mark.parametrize(
    "value, slept",
    [
        ("5", 5.0),  # honoured
        ("1e9", fetch_mod.MAX_RETRY_WAIT),  # capped
        ("-1", 1.0),  # unusable: the caller's own backoff applies
        ("nan", 1.0),
        ("inf", 1.0),
        ("Wed, 21 Oct 2015 07:28:00 GMT", 1.0),
    ],
)
def test_retry_after_is_honoured_capped_or_ignored(monkeypatch, value, slept):
    outcomes = iter([_busy(value), _ok()])
    monkeypatch.setattr(fetch_mod.netguard, "get", lambda url, **kw: next(outcomes))
    sleeps = []

    resp = fetch_mod._http_get(
        "http://example.com/", retry_backoff=1.0, sleep=sleeps.append
    )

    assert resp.status_code == 200 and sleeps == [slept]


def test_cli_exposes_retries_with_the_library_default():
    param = inspect.signature(cli.fetch).parameters["retries"]
    assert param.default == fetch_mod.DEFAULT_RETRIES


# --- titles -----------------------------------------------------------------


@pytest.mark.parametrize(
    "head, expected",
    [
        ("<title>Reading Code – Joel on Software</title>", "Reading Code"),
        (
            "<title>Joel on Software - Fire and Motion</title>"
            '<meta property="og:site_name" content="Joel on Software">',
            "Fire and Motion",
        ),
        ("<title>Beating the Averages | Paul Graham</title>", "Beating the Averages"),
        # The site's own <h1> (a logo) must not be taken for the article title.
        (
            "<title>Fire and Motion – Joel on Software</title>"
            '<h1><a href="/">Joel on Software</a></h1>',
            "Fire and Motion",
        ),
    ],
)
def test_page_title_drops_the_site_name(head, expected):
    assert page_title(head) == expected


def test_the_filename_carries_no_site_name(serve, tmp_path):
    serve(
        {
            "http://x.com/a": f"<title>Fire and Motion | Joel on Software</title><p>{PROSE}</p>"
        }
    )
    result = fetch_mod.fetch_one("http://x.com/a", output_dir=tmp_path)
    assert result.output_file.name == "fire-and-motion.md"
    assert result.title == "Fire and Motion"


def test_main_mode_leads_with_the_page_title_when_there_is_no_heading():
    page = (
        "<html><head><title>On Things | My Blog</title></head><body>"
        f"<nav><a href='/'>Home</a></nav><article><p>{PROSE * 3}</p></article>"
        "</body></html>"
    )
    first = [line for line in _main_md(page).splitlines() if line.strip()][0]
    assert first == "# On Things"


# --- extraction -------------------------------------------------------------


def test_code_comments_survive():
    page = (
        f"<article><p>{PROSE}</p>"
        '<pre><code>x = 1\n<span class="hljs-comment"># important comment</span>'
        "</code></pre>"
        '<pre><code><span class="token comment"># prism comment</span></code></pre>'
        f"<p>{PROSE}</p></article>"
    )
    md = _main_md(page)
    assert "# important comment" in md and "# prism comment" in md


def test_a_state_class_does_not_make_the_article_chrome():
    comments = "".join(f"<p>Comment {i}: {PROSE}</p>" for i in range(6))
    page = (
        f'<div class="post-body share-enabled"><p>The article. {PROSE * 2}</p></div>'
        f'<div class="comments">{comments}</div>'
    )
    md = _main_md(page)
    assert "The article." in md and "Comment 0" not in md


def test_a_short_conclusion_in_a_sibling_section_is_kept():
    body = "".join(f"<p>Body paragraph {i}. {PROSE}</p>" for i in range(12))
    page = (
        f"<div><section>{body}</section>"
        f"<section><p>In conclusion, {PROSE}</p></section>"
        "<div class='share'><a href='/t'>Tweet</a> <a href='/f'>Share</a></div></div>"
    )
    md = _main_md(page)
    assert md.index("Body paragraph 0.") < md.index("In conclusion,")
    assert "Tweet" not in md


def test_edge_trimming_keeps_tables_single_links_and_references():
    page = (
        "<article><table><tr><th>Version</th><td>1.2</td></tr></table>"
        f"<p>{PROSE}</p><p>See the <a href='/paper.pdf'>paper</a>.</p>"
        "<ol><li><a href='/r1'>Reference one</a></li>"
        "<li><a href='/r2'>Reference two</a></li></ol></article>"
    )
    md = _main_md(page)
    for kept in ("1.2", "See the [paper](/paper.pdf).", "Reference two"):
        assert kept in md


def test_edge_trimming_drops_breadcrumbs_and_ad_slots():
    page = (
        '<div><p><a href="/">Home</a> &gt; <a href="/talks">Talks</a> &gt; This one</p>'
        "<div><p>Advertisement</p><a href='#after'>SKIP ADVERTISEMENT</a></div>"
        f"<p>{PROSE * 3}</p>"
        "<div>See more on: <a href='/a'>Roger Federer</a>, "
        "<a href='/b'>International Tennis Federation</a></div></div>"
    )
    html = main_content(page)
    assert (
        "Talks" not in html and "ADVERTISEMENT" not in html and "See more" not in html
    )
    assert "real prose" in html


def test_figures_and_their_captions_are_kept():
    page = (
        f"<article><p>{PROSE * 3}</p><figure><img src='a.png'>"
        "<figcaption>Figure 1: the setup.</figcaption></figure></article>"
    )
    assert "Figure 1: the setup." in _main_md(page)


def test_wayback_link_forms_and_toolbar_are_cleaned_in_full_mode():
    page = (
        "<html><body><div id='wm-ipp-base'>WAYBACK TOOLBAR Dec JAN Feb</div>"
        f"<article><h1>T</h1><p>{PROSE * 3}</p>"
        "<p><a href='/web/20150308214418/http://a.com/x'>rel</a> "
        "<a href='//web.archive.org/web/20150308214418/http://a.com/y'>proto</a> "
        "<a href='http://web.archive.org/web/20150308214418/mailto:me@a.com'>mail</a>"
        "</p></article></body></html>"
    )
    src = "https://web.archive.org/web/20150308214418/http://a.com/"
    md = fetch_mod.html_to_markdown(page, source_url=src, content="full")
    assert "(http://a.com/x)" in md and "(http://a.com/y)" in md
    assert "(mailto:me@a.com)" in md and "WAYBACK TOOLBAR" not in md


# --- found by the adversarial review of the port ------------------------------


def _doc(title, body):
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


def test_a_name_the_caller_asked_for_is_used_not_an_older_file(serve, tmp_path):
    """One page cited as [1] and as [7] gets both files; so does a chosen title."""
    url = "http://a.com/x"
    serve({url: f"<title>Some Page</title><p>{PROSE}</p>"})
    entries = [
        fetch_mod.UrlEntry(url=url, ref="1"),
        fetch_mod.UrlEntry(url=url, ref="7"),
        fetch_mod.UrlEntry(url=url, title="My Chosen Name"),
    ]
    names = [
        fetch_mod.fetch_one(e, output_dir=tmp_path).output_file.name for e in entries
    ]
    assert names == ["ref_01_some-page.md", "ref_07_some-page.md", "my-chosen-name.md"]
    # ...and a rerun of each finds its own file.
    again = [fetch_mod.fetch_one(e, output_dir=tmp_path) for e in entries]
    assert [r.status for r in again] == ["skipped"] * 3
    assert [r.output_file.name for r in again] == names


def test_several_old_files_for_one_url_resolve_deterministically(serve, tmp_path):
    url = "http://paulgraham.com/hp.html"
    serve({url: f"<title>Hackers and Painters</title><p>{PROSE}</p>"})
    for name in ("zz-old.md", "aa-old.md"):
        (tmp_path / name).write_text(f"<!-- Source: {url} -->\n\nold\n")
    [result] = fetch_mod.fetch([url], output_dir=tmp_path)
    assert result.status == "skipped" and result.output_file.name == "aa-old.md"


def test_scanning_a_folder_reads_only_new_or_changed_files(tmp_path, monkeypatch):
    for i in range(20):
        (tmp_path / f"f{i}.md").write_text(f"<!-- Source: http://x.com/{i} -->\n")
    fetch_mod._existing_claims(tmp_path)  # warm
    reads = []
    real = fetch_mod._recorded_source
    monkeypatch.setattr(
        fetch_mod, "_recorded_source", lambda p: reads.append(p.name) or real(p)
    )
    (tmp_path / "new.md").write_text("<!-- Source: http://x.com/new -->\n")

    claims = fetch_mod._existing_claims(tmp_path)

    assert reads == ["new.md"] and len(claims) == 21


@pytest.mark.parametrize(
    "body, kept",
    [
        (  # a link, then "/": not a breadcrumb
            f'<article><h1>On Linux</h1><p><a href="https://gnu.org">GNU</a>/Linux'
            f" is what this whole essay is about.</p><p>{PROSE}</p></article>",
            "/Linux is what this whole essay is about.",
        ),
        (  # the word, not an ad slot
            "<article><h1>Ads</h1><p>Advertisement budgets doubled in 2024, says "
            f"the report.</p><p>{PROSE}</p></article>",
            "Advertisement budgets doubled",
        ),
        (  # a sentence with two links, not a row of links
            f"<article><h1>Post</h1><p>A reply to <a href='/j'>Joel Spolsky</a> and "
            f"<a href='/p'>Paul Graham</a>.</p><p>{PROSE}</p></article>",
            "A reply to [Joel Spolsky](/j)",
        ),
        (
            f"<article><h1>Post</h1><p>{PROSE}</p><p>Update: see <a href='/a'>the "
            "follow-up post</a> and <a href='/b'>the errata</a>.</p></article>",
            "Update: see [the follow-up post](/a)",
        ),
        (  # a closing section: its heading and its two-cell table stay
            f"<article><h1>Post</h1><p>{PROSE}</p><h2>Downloads</h2><table><tr>"
            "<td>Dataset</td><td><a href='/d.csv'>d.csv</a></td></tr></table></article>",
            "## Downloads",
        ),
    ],
)
def test_edge_trimming_keeps_real_opening_and_closing_content(body, kept):
    assert kept in _main_md(_doc("Post", body))


def test_a_data_table_with_a_line_break_stays_a_table():
    table = (
        "<table><thead><tr><th>Lib</th><th>Licence</th><th>Notes</th></tr></thead>"
        "<tbody><tr><td>a</td><td>MIT</td><td>fast<br>small</td></tr>"
        "<tr><td>b</td><td>GPL</td><td>slow</td></tr></tbody></table>"
    )
    md = _main_md(
        _doc("Libs", f"<article><h1>Libs</h1><p>{PROSE}</p>{table}</article>")
    )
    assert "| Lib | Licence | Notes |" in md


def test_a_permalink_headline_is_not_a_logo(serve, tmp_path):
    page = _doc(
        "Jane's Blog",
        '<header><h1><a href="/2020/real-post">The Real Post Title</a></h1></header>'
        f"<article><p>{PROSE}</p><p>{PROSE}</p></article>",
    )
    md = _main_md(page)
    assert "The Real Post Title" in md and "# Jane's Blog" not in md
    no_title = page.replace("<title>Jane's Blog</title>", "")
    assert page_title(no_title) == "The Real Post Title"


def test_a_title_the_headline_repeats_whole_is_not_split():
    html = (
        "<title>Rust vs. Go - A Comparison</title><h1>Rust vs. Go - A Comparison</h1>"
    )
    assert page_title(html) == "Rust vs. Go - A Comparison"


def test_the_next_post_on_the_page_is_not_merged_in():
    html = _doc(
        "Post One",
        f"<main><article class='post'><h1>Post One</h1>{f'<p>{PROSE * 2}</p>' * 3}"
        "</article><article class='post'><h1>Post Two</h1><p>Teaser of the next "
        "story that is long enough to be prose, over eighty chars.</p></article></main>",
    )
    assert "Post Two" not in _main_md(html)


def test_a_page_quoting_the_wayback_toolbar_is_left_alone():
    page = (
        '<p>The toolbar is <code>&lt;div id="wm-ipp-base"&gt;</code>. Our site has '
        '<a href="/web/2019/">2019 posts</a>.</p>'
    )
    md = fetch_mod.html_to_markdown(
        page, source_url="http://blog.example/p", content="full"
    )
    assert "[2019 posts](/web/2019/)" in md


def test_wayback_urls_shown_as_link_text_are_cleaned_too():
    cap = (
        '<p>See <a href="https://web.archive.org/web/20150308214418/http://x.org/a">'
        "https://web.archive.org/web/20150308214418/http://x.org/a</a>.</p>"
    )
    src = "https://web.archive.org/web/20150308214418/http://x.org/post"
    md = fetch_mod.html_to_markdown(cap, source_url=src, content="full")
    assert "web.archive.org" not in md.split("-->", 1)[1] and "http://x.org/a" in md
