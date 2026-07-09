# Development notes / lessons learned

## 2026-07-09 — CI failed on Python 3.11 with `Scheduler() takes no arguments`

First CI run failed on the 3.11 matrix job with
`TypeError: AllOnScheduler() takes no arguments` while local tests (3.12)
passed. Root cause: `anrg-saga` was unpinned in `pyproject.toml`; saga 2.x
declares `requires-python >= 3.12`, so pip on the 3.11 runner silently
resolved saga **1.x**, whose `Scheduler` is a plain ABC rather than a
pydantic `BaseModel` — our field-declaring subclasses therefore had no
generated `__init__`.

Fix: pin `anrg-saga>=2.0.4`, set our `requires-python >= 3.12`, and align
the CI matrix (3.12, 3.13).

**Lesson:** pin research-stack dependencies to the major version whose API
the code was written against, and keep `requires-python` and the CI matrix
at or above the pinned dependency's floor — otherwise pip backsolves to an
old major on some interpreter and the failure surfaces far from its cause.
