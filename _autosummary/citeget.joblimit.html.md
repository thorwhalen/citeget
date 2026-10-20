# citeget.joblimit

Cap how many acquisitions one owner runs at the same time.

An acquisition drives a headless Chromium and downloads whole books, so a few
of them at once is the most one user should be able to start on a shared
server. [`job_slot()`](#citeget.joblimit.job_slot) hands out a fixed number of slots per *owner key*
(a user, or a user’s jobs directory). It is a context manager: entering it
takes a free slot or raises [`JobLimitExceeded`](#citeget.joblimit.JobLimitExceeded) at once (it never
queues), and leaving it frees the slot.

Slots are advisory `flock` locks on small files, so they are shared by every
process on the machine and freed by the kernel when the process holding one
exits, even if it is killed. A crashed job can never leave a slot taken.

Configuration, most specific first:

- the `max_concurrent=` argument;
- the `CITEGET_MAX_CONCURRENT_JOBS` environment variable;
- [`DEFAULT_MAX_CONCURRENT_JOBS`](#citeget.joblimit.DEFAULT_MAX_CONCURRENT_JOBS).

`0` (or a negative number) means “no cap”. Lock files live under
`CITEGET_JOB_LOCK_DIR` if set, else a `citeget-job-slots-<uid>` directory
in the system temp dir. On a platform without `fcntl` (Windows) the cap is not
enforced.

```pycon
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
```

### Module Attributes

| [`DEFAULT_MAX_CONCURRENT_JOBS`](#citeget.joblimit.DEFAULT_MAX_CONCURRENT_JOBS)   | Concurrent acquisitions allowed per owner when nothing else is configured.   |
|--------------------------------------------------------------------------------|------------------------------------------------------------------------------|

### Functions

| [`job_slot`](#citeget.joblimit.job_slot)(key, \*[, max_concurrent, lock_dir])   | Hold one of *key*'s concurrency slots for the duration of the block.        |
|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`max_concurrent_jobs`](#citeget.joblimit.max_concurrent_jobs)([value])                    | The cap in force: *value* if given, else the environment, else the default. |

### Exceptions

| [`JobLimitExceeded`](#citeget.joblimit.JobLimitExceeded)   | The owner already has as many acquisitions running as allowed.   |
|---------------------------------------------------------------------|------------------------------------------------------------------|

### citeget.joblimit.DEFAULT_MAX_CONCURRENT_JOBS *= 2*

Concurrent acquisitions allowed per owner when nothing else is configured.

### *exception* citeget.joblimit.JobLimitExceeded

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The owner already has as many acquisitions running as allowed.

### citeget.joblimit.job_slot(key, , max_concurrent=None, lock_dir=None)

Hold one of *key*’s concurrency slots for the duration of the block.

Yields the slot number, or `None` when no cap applies.

* **Raises:**
  [**JobLimitExceeded**](#citeget.joblimit.JobLimitExceeded) – every slot for *key* is held by a running job.
* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]]

### citeget.joblimit.max_concurrent_jobs(value=None)

The cap in force: *value* if given, else the environment, else the default.

```pycon
>>> max_concurrent_jobs(5)
5
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
