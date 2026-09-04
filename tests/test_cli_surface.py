"""Characterization tests pinning the ``citeget`` command-line surface.

Both goldens under ``tests/cli_goldens/`` were recorded from the *argh*
implementation of :mod:`citeget.cli` before the migration to :mod:`cw`, with
``cw.testing.characterize``. Every assertion below compares today's CLI against
the grammar argh produced, not against something written by hand afterwards.

``citeget`` has **two** entry points with two different usage lines, so there
are two goldens:

``citeget.json``
    the console script. ``prog`` is not pinned in code, so argparse derives it
    from ``sys.argv[0]`` -- ``usage: citeget ...``.
``citeget_module.json``
    ``python -m citeget``, where the same derivation yields
    ``usage: __main__.py ...``. Pinning ``prog=`` would have silently changed
    this second surface, so it is deliberately left underived and pinned here
    instead.

Exit codes are pinned separately because ``cw.dispatch`` *returns* the exit code
where argh exited by itself: ``main()`` hands it to the console-script shim, and
``citeget/__main__.py`` must ``raise SystemExit(main())``. Drop either and every
argument error starts exiting 0 -- invisible to every other test in this suite.

The goldens replay non-strictly: ``--help`` bodies are compared but a pure
formatting difference is reported rather than failed, because CPython rewrites
argparse's own option column between versions. At migration time the *strict*
comparison was empty on CPython 3.10 and 3.12 alike.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cw.testing import assert_replay

GOLDENS = Path(__file__).parent / "cli_goldens"
MODULE_CLI = [sys.executable, "-m", "citeget"]


def _load(name):
    return json.loads((GOLDENS / name).read_text(encoding="utf-8"))


def test_console_script_surface_matches_the_argh_recorded_golden():
    """`citeget ...` -- the grammar users actually type."""
    assert_replay(_load("citeget.json"))


def test_module_surface_matches_the_argh_recorded_golden():
    """`python -m citeget ...` -- a second, differently-prefixed usage line."""
    assert_replay(_load("citeget_module.json"), prog=MODULE_CLI)


@pytest.mark.parametrize("name", ["citeget.json", "citeget_module.json"])
def test_goldens_carry_no_machine_specific_paths(name):
    """A golden that names an absolute path can only replay on one computer."""
    raw = (GOLDENS / name).read_text(encoding="utf-8")
    assert "/Users/" not in raw and "\\\\Users\\\\" not in raw


def _run(*argv):
    return subprocess.run(
        MODULE_CLI + list(argv), capture_output=True, text=True, timeout=120
    )


def test_no_arguments_prints_usage_to_stdout_and_exits_zero():
    """argh's behaviour, preserved. Plain argparse would exit 2 to stderr."""
    r = _run()
    assert r.returncode == 0
    assert r.stdout.startswith("usage: ")
    assert r.stderr == ""


@pytest.mark.parametrize(
    "argv",
    [
        ("no-such-command",),
        ("search", "--no-such-flag"),
        ("search",),  # missing the required positional
    ],
)
def test_argument_errors_exit_two(argv):
    """Guards `raise SystemExit(main())` / `return cw.dispatch(...)`.

    Without them the exit code is swallowed and every one of these exits 0.
    """
    assert _run(*argv).returncode == 2


def test_commands_list_is_what_the_parser_dispatches():
    """`COMMANDS` is the single source of truth the help text is built from."""
    from citeget.cli import COMMANDS

    names = {f.__name__ for f in COMMANDS}
    assert names == {
        "search",
        "download",
        "get_book",
        "acquire",
        "fetch",
        "check_mirrors",
    }

    help_text = _run("--help").stdout
    for cli_name in (
        "search",
        "download",
        "get-book",
        "acquire",
        "fetch",
        "check-mirrors",
    ):
        assert cli_name in help_text
