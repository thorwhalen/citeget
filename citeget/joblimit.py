"""Cap how many acquisitions one owner runs at the same time.

An acquisition drives a headless Chromium and downloads whole books, so a few
of them at once is the most one user should be able to start on a shared
server. :func:`job_slot` hands out a fixed number of slots per *owner key*
(a user, or a user's jobs directory). It is a context manager: entering it
takes a free slot or raises :class:`JobLimitExceeded` at once (it never
queues), and leaving it frees the slot.

Slots are advisory ``flock`` locks on small files, so they are shared by every
process on the machine and freed by the kernel when the process holding one
exits, even if it is killed. A crashed job can never leave a slot taken.

Configuration, most specific first:

- the ``max_concurrent=`` argument;
- the ``CITEGET_MAX_CONCURRENT_JOBS`` environment variable;
- :data:`DEFAULT_MAX_CONCURRENT_JOBS`.

``0`` (or a negative number) means "no cap". Lock files live under
``CITEGET_JOB_LOCK_DIR`` if set, else a ``citeget-job-slots`` directory in the
system temp dir. On a platform without ``fcntl`` (Windows) the cap is not
enforced.

>>> import tempfile
>>> d = tempfile.mkdtemp()
>>> with job_slot("alice", max_concurrent=1, lock_dir=d):
...     try:
...         with job_slot("alice", max_concurrent=1, lock_dir=d):
...             pass
...     except JobLimitExceeded as e:
...         print("refused")
refused
>>> with job_slot("alice", max_concurrent=1, lock_dir=d):  # freed on exit
...     print("ok")
ok
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Iterator, Optional, Union

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

#: Concurrent acquisitions allowed per owner when nothing else is configured.
DEFAULT_MAX_CONCURRENT_JOBS = 2
MAX_CONCURRENT_ENV_VAR = "CITEGET_MAX_CONCURRENT_JOBS"
LOCK_DIR_ENV_VAR = "CITEGET_JOB_LOCK_DIR"
_LOCK_DIR_NAME = "citeget-job-slots"


class JobLimitExceeded(RuntimeError):
    """The owner already has as many acquisitions running as allowed."""


def max_concurrent_jobs(value: Optional[int] = None) -> int:
    """The cap in force: *value* if given, else the environment, else the default.

    >>> max_concurrent_jobs(5)
    5
    """
    if value is not None:
        return int(value)
    raw = os.environ.get(MAX_CONCURRENT_ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_MAX_CONCURRENT_JOBS
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(
            f"{MAX_CONCURRENT_ENV_VAR}={raw!r} is not an integer "
            "(use 0 for no cap)"
        ) from e


def _lock_dir(lock_dir: Union[str, Path, None]) -> Path:
    if lock_dir is not None:
        return Path(lock_dir)
    env = os.environ.get(LOCK_DIR_ENV_VAR)
    if env:
        return Path(env).expanduser()
    return Path(tempfile.gettempdir()) / _LOCK_DIR_NAME


@contextlib.contextmanager
def job_slot(
    key: str,
    *,
    max_concurrent: Optional[int] = None,
    lock_dir: Union[str, Path, None] = None,
) -> Iterator[Optional[int]]:
    """Hold one of *key*'s concurrency slots for the duration of the block.

    Yields the slot number, or ``None`` when no cap applies.

    Raises:
        JobLimitExceeded: every slot for *key* is held by a running job.
    """
    cap = max_concurrent_jobs(max_concurrent)
    if cap <= 0 or fcntl is None:
        yield None
        return
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    owner_dir = _lock_dir(lock_dir) / digest
    owner_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for slot in range(cap):
        fd = os.open(owner_dir / f"slot-{slot}.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            continue
        try:
            yield slot
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return
    raise JobLimitExceeded(
        f"{cap} acquisition(s) are already running for this account; wait for "
        f"one to finish (the cap is set by {MAX_CONCURRENT_ENV_VAR})."
    )
