"""Main-content extraction in ``citeget fetch`` (thorwhalen/citeget#29).

The fixtures under ``fixtures/pages/`` are the five pages named in the issue,
saved with their real markup (``make_fixtures.py`` says how they were reduced).
No test here touches the network.
"""

import sys
from pathlib import Path

import pytest

from citeget.fetch import fetch_one, html_to_markdown, main_content_markdown
from citeget.main_content import (
    MAIN_CONTENT_EXTRACTORS,
    clean_wayback_html,
    extract_main_content,
    resolve_extractor,
    unwrap_layout_tables,
)

PAGES_DIR = Path(__file__).parent / "fixtures" / "pages"
sys.path.insert(0, str(PAGES_DIR))
from make_fixtures import PAGES  # noqa: E402

#: name -> (first line, (start, end) of the last line, chrome that must be gone)
EXPECTED = {
    "paulgraham_avg": (
        "# Beating the Averages",
        ("studying, especially", "if you want to design new languages."),
        ["Want to start a startup", "Y Combinator"],
    ),
    "joelonsoftware_talmud": (
        "# Reading Code is Like Reading the Talmud",
        ("Thanks, Seth!", "Great ideas!"),
        [
            "Skip to content",
            "View menu",
            "View sidebar",
            "Your host",
            "Post navigation",
            "Previous Post",
            "Proudly powered by WordPress",
        ],
    ),
    "danluu_wat": (
        "# Normalization of deviance",
        (
            "2. I've spent a lot of time asking about why things are the way",
            "making sure things run smoothly. [[return]](#fnref:P)",
        ),
        ["[Archive](https://danluu.com/)", "Patreon", "Bluesky"],
    ),
    "idlewords_haunted_by_data": (
        "This is the text version of a talk I gave on October 1, 2015, at the "
        "[Strata+Hadoop World](http://strataconf.com/big-data-conference-ny-2015) "
        "conference in New York City. The [video version is here]"
        "(https://www.youtube.com/watch?v=GAXLHM-1Psk) (20 mins).",
        ("STOCHASTIC, EXPONENTIALLY", "DECAYING APPLAUSE"),
        ["[Idle Words](http://idlewords.com/) >"],
    ),
    "wayback_nytimes_federer": (
        "# Roger Federer as Religious Experience",
        # It ends on the paper's correction notice, which is part of the article.
        ("**Correction: Aug. 27, 2006**", "he did not go to the net.*"),
        [
            "SKIP ADVERTISEMENT",
            "Supported by",
            "Manage Privacy Preferences",
            "| Dec | JAN | Feb |",  # the Wayback toolbar's calendar
            "web.archive.org",
        ],
    ),
}


def _html(name):
    return (PAGES_DIR / f"{name}.html").read_text(encoding="utf-8")


def _content_lines(md):
    """Non-blank lines, after the ``<!-- Source: -->`` provenance header."""
    return [
        line
        for line in md.splitlines()
        if line.strip() and not line.startswith("<!-- Source:")
    ]


@pytest.fixture(params=sorted(PAGES))
def saved(request, fake_web, tmp_path):
    """``(name, markdown)`` for one fixture, through ``fetch_one`` as the CLI runs it."""
    name = request.param
    fake_web({PAGES[name]: _html(name)})
    result = fetch_one(PAGES[name], output_dir=tmp_path)
    assert result.status == "ok"
    return name, result.output_file.read_text(encoding="utf-8")


def test_first_line_is_the_title_or_first_sentence(saved):
    name, md = saved
    first, _, _ = EXPECTED[name]
    assert _content_lines(md)[0].strip() == first


def test_last_line_is_the_end_of_the_article(saved):
    name, md = saved
    _, (start, end), _ = EXPECTED[name]
    final = _content_lines(md)[-1].strip()
    assert final.startswith(start) and final.endswith(end)


def test_no_chrome_left(saved):
    name, md = saved
    _, _, chrome = EXPECTED[name]
    body = "\n".join(_content_lines(md))  # the provenance header names the URL
    for text in chrome:
        assert text not in body


def test_no_pipe_tables(saved):
    _, md = saved
    assert not [line for line in md.splitlines() if line.lstrip().startswith("|")]


def test_the_essay_survives_whole(saved):
    """Main mode trims chrome, not text: most of the full page's prose remains."""
    name, md = saved
    article_words = len(md.split())
    assert article_words > 250  # Joel's post, the shortest, is about 300 words


@pytest.mark.parametrize("name", sorted(PAGES))
def test_content_full_reproduces_the_previous_output(fake_web, tmp_path, name):
    """``*.full.md`` was produced by ``html_to_markdown`` before #29 existed."""
    fake_web({PAGES[name]: _html(name)})
    result = fetch_one(PAGES[name], output_dir=tmp_path, content="full")
    golden = (PAGES_DIR / f"{name}.full.md").read_text(encoding="utf-8")
    assert result.output_file.read_text(encoding="utf-8") == golden
    assert html_to_markdown(_html(name), source_url=PAGES[name]) == golden


def test_full_page_output_had_the_chrome_the_issue_describes():
    """Sanity check on the fixtures: the problem is real in ``content="full"``."""
    joel = (PAGES_DIR / "joelonsoftware_talmud.full.md").read_text()
    assert "[Skip to content](#content)" in joel and "## Your host" in joel
    pg = (PAGES_DIR / "paulgraham_avg.full.md").read_text()
    assert any(line.startswith("|") for line in pg.splitlines())


# --- web.archive.org ---------------------------------------------------------


def test_wayback_links_point_back_at_the_original_site():
    md = main_content_markdown(_html("wayback_nytimes_federer"))
    assert "nytimes.com" in md
    assert "web.archive.org" not in md
    assert "/web/2026" not in md


def test_clean_wayback_html_drops_the_toolbar_and_unprefixes_links():
    page = (
        "<html><body><!-- BEGIN WAYBACK TOOLBAR INSERT --><div id='wm-ipp-base'>"
        "Wayback Machine</div><!-- END WAYBACK TOOLBAR INSERT -->"
        "<a href='/web/20150308214418/http://a.com/x'>x</a>"
        "<img src='https://web.archive.org/web/20150308214418im_/http://a.com/p.png'>"
        "</body></html>"
    )
    out = clean_wayback_html(page)
    assert "Wayback Machine" not in out
    assert 'href="http://a.com/x"' in out
    assert 'src="http://a.com/p.png"' in out


def test_non_wayback_pages_are_left_alone():
    page = "<p><a href='/web/20150308214418/http://a.com/x'>x</a></p>"
    assert clean_wayback_html(page) == page


# --- the extractor seam ------------------------------------------------------


def test_extractor_accepts_any_callable(fake_web, tmp_path):
    url = "http://example.com/a"
    fake_web({url: "<title>T</title><p>ignored</p>"})
    result = fetch_one(
        url,
        output_dir=tmp_path,
        extractor=lambda html: "<p>From my own extractor.</p>",
    )
    assert "From my own extractor." in result.output_file.read_text()


def test_extractor_by_name():
    assert resolve_extractor(None) is extract_main_content
    assert resolve_extractor("builtin") is extract_main_content
    assert set(MAIN_CONTENT_EXTRACTORS) >= {"builtin", "trafilatura"}
    with pytest.raises(ValueError, match="Unknown extractor"):
        resolve_extractor("no-such-extractor")


def test_trafilatura_missing_names_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "trafilatura", None)  # import fails
    with pytest.raises(ImportError, match=r"citeget\[extract\]"):
        resolve_extractor("trafilatura")("<p>x</p>")


def test_unknown_content_mode_is_an_error(fake_web, tmp_path):
    url = "http://example.com/a"
    fake_web({url: "<p>x</p>"})
    with pytest.raises(ValueError, match="'main' or 'full'"):
        fetch_one(url, output_dir=tmp_path, content="everything")


# --- building blocks ---------------------------------------------------------


def test_data_tables_survive_main_content():
    page = (
        "<article><p>Results of the long experiment are in the table below.</p>"
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        "<p>And that is the end of the article, as these things go.</p></article>"
    )
    md = main_content_markdown(page)
    assert "| A | B |" in md


def test_layout_table_cell_becomes_a_block():
    html = "<table><tr><td>nav</td><td><p>The essay itself.</p></td></tr></table>"
    out = unwrap_layout_tables(html)
    assert "<table" not in out and "<td" not in out
    assert "The essay itself." in out
