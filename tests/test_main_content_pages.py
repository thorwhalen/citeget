"""Main-content extraction on five real pages (thorwhalen/citeget#29).

The fixtures under ``fixtures/pages/`` are the five pages named in the issue,
saved with their real markup and the prose replaced by filler of the same
length (``make_fixtures.py`` says how), so the extractor scores and chooses
exactly as on the live pages and no article is redistributed. No test here
touches the network.
"""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

fetch_mod = importlib.import_module("citeget.fetch")

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
            "[Joel on Software]",
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
        # The page opens on this note, above its <h1>; the breadcrumb is gone.
        "This is the text version of a talk I gave on October 1, 2015, at the "
        "[Strata+Hadoop World](http://strataconf.com/big-data-conference-ny-2015) "
        "conference in New York City. The [video version is here]"
        "(https://www.youtube.com/watch?v=GAXLHM-1Psk) (20 mins).",
        ("STOCHASTIC, EXPONENTIALLY", "DECAYING APPLAUSE"),
        ["[Idle Words](http://idlewords.com/) >"],
    ),
    "wayback_nytimes_federer": (
        "# Roger Federer as Religious Experience",
        # It ends on the article's bottom box (correction notice, corrections
        # policy, print-edition line; filler here), kept whole since #40 caps
        # what a descent into the story body may shed. "See more on" is trimmed.
        ("xxxxx xxxxxx xxxxxxx xx xxx xxxxxx", "xxx xxxxxxx xxxxx xxxxx."),
        [
            "SKIP ADVERTISEMENT",
            "Supported by",
            "Manage Privacy Preferences",
            "| Dec | JAN | Feb |",  # the Wayback toolbar's calendar
            "web.archive.org",
            "See more on",
            "Share full article",
            "Related Content",
        ],
    ),
}

#: Pages whose ``content="full"`` output is pinned byte for byte. The Wayback
#: page is not: since #39 its toolbar and link prefixes are cleaned in every
#: mode, which the golden (recorded before that) predates.
FULL_GOLDENS = sorted(set(PAGES) - {"wayback_nytimes_federer"})


def _html(name):
    return (PAGES_DIR / f"{name}.html").read_text(encoding="utf-8")


def _content_lines(md):
    """Non-blank lines, after the ``<!-- Source: -->`` provenance header."""
    return [
        line
        for line in md.splitlines()
        if line.strip() and not line.startswith("<!-- Source:")
    ]


@pytest.fixture
def serve(monkeypatch):
    """Serve fixture pages instead of the network."""

    def _serve(pages):
        def _get(url, **_):
            return SimpleNamespace(
                headers={"content-type": "text/html"}, text=pages[url], content=b""
            )

        monkeypatch.setattr(fetch_mod, "_http_get", _get)

    return _serve


@pytest.fixture(params=sorted(PAGES))
def saved(request, serve, tmp_path):
    """``(name, markdown)`` for one fixture, through ``fetch_one`` as the CLI runs it."""
    name = request.param
    serve({PAGES[name]: _html(name)})
    result = fetch_mod.fetch_one(PAGES[name], output_dir=tmp_path, retries=0)
    assert result.status == "ok"
    return name, result.output_file.read_text(encoding="utf-8")


def test_first_line_is_the_title(saved):
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
    """Every table on these pages is page layout, so none may become a pipe table."""
    _, md = saved
    assert not [line for line in md.splitlines() if line.lstrip().startswith("|")]


def test_the_essay_survives_whole(saved):
    """Main mode trims chrome, not text: most of the full page's prose remains."""
    _, md = saved
    assert len(md.split()) > 250  # Joel's post, the shortest, is about 300 words


@pytest.mark.parametrize("name", FULL_GOLDENS)
def test_content_full_reproduces_the_previous_output(name):
    """``*.full.md`` was produced by ``html_to_markdown`` before #29 existed."""
    golden = (PAGES_DIR / f"{name}.full.md").read_text(encoding="utf-8")
    assert fetch_mod.html_to_markdown(_html(name), source_url=PAGES[name]) == golden


def test_full_page_output_had_the_chrome_the_issue_describes():
    """Sanity check on the fixtures: the problem is real in ``content="full"``."""
    joel = (PAGES_DIR / "joelonsoftware_talmud.full.md").read_text(encoding="utf-8")
    assert "[Skip to content](#content)" in joel and "## Your host" in joel
    pg = (PAGES_DIR / "paulgraham_avg.full.md").read_text(encoding="utf-8")
    assert any(line.startswith("|") for line in pg.splitlines())


def test_wayback_is_cleaned_from_the_page_alone():
    """A saved Wayback capture is recognised by its toolbar, without its URL."""
    md = fetch_mod.html_to_markdown(_html("wayback_nytimes_federer"), content="main")
    assert "nytimes.com" in md and "web.archive.org" not in md and "/web/20" not in md


def test_the_correction_notice_is_kept():
    html = _html("wayback_nytimes_federer")
    md = fetch_mod.html_to_markdown(html, content="main")
    assert "A correction was made on" in md and "he did not go to the net." in md
