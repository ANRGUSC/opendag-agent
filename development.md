# Development notes / lessons learned

## 2026-07-09 — E1 campaign stalled: SAGA's DPS scheduler is pathologically slow

The full campaign burned 15+ CPU-minutes without finishing an instance list.
Per-scheduler timing on the densest instance (debate 8 agents x 10 rounds:
89 tasks, 648 edges, 12-node network) showed every scheduler completing in
under 0.3 s except DPS, which ran for minutes without returning. DPS is now
excluded from the campaign default list (19 classical schedulers remain),
with the exclusion noted where coverage is reported.

**Lesson:** when sweeping someone else's algorithm portfolio, time each
algorithm on the *worst-case instance first* (densest graph, most nodes)
before launching the full sweep — one pathological member otherwise
dominates the whole campaign's runtime and looks like a hang. Print progress
with flush=True so redirected output shows liveness.

## 2026-07-09 — SHEFT produced NaN ranks: std(inf) on auto-added self-loops

`saga.stochastic.StochasticNetwork.create` fills in missing self-loop edges
with infinite speed and wraps them in single-sample `RandomVariable`s;
`std([inf])` is NaN, so SHEFT's `mean+std` determinization turned self-loop
speeds into NaN, `upward_rank` averaged `size/speed` over *all* edges, and
every non-sink task's rank became NaN — surfacing as a baffling
"Parent task not scheduled yet" deep inside HEFT.

Fix: pass explicit large-finite (1e12 KB/s) self-loops when building
stochastic instances (`opendag/schedule/stochastic_eval.py`).

**Lesson:** when a library auto-completes your input (SAGA fills missing
edges), the auto-filled values follow *its* conventions (inf/0), which can
be poison downstream of a second transformation (RandomVariable stats).
Construct boundary values explicitly. Worth filing upstream as a SAGA issue.

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
