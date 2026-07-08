"""Gantt rendering for SAGA schedules and LocalRunner results.

Matplotlib is an optional dependency (``pip install opendag-agent[figures]``);
imports happen inside functions so the core package works without it.
"""
from __future__ import annotations

from pathlib import Path

from saga import Schedule

from .execute.local import RunResult
from .schedule.bridge import is_super

Bar = tuple[str, str, float, float]  # (executor, task, start, end)


def bars_from_schedule(schedule: Schedule) -> list[Bar]:
    return [
        (node, st.name, st.start, st.end)
        for node, tasks in schedule.items()
        for st in tasks
        if not is_super(st.name)
    ]


def bars_from_run(result: RunResult) -> list[Bar]:
    return [(r.executor, r.name, r.start_s, r.end_s) for r in result.records]


def _draw(ax, bars: list[Bar], title: str) -> None:
    import matplotlib.pyplot as plt

    rows = sorted({b[0] for b in bars})
    index = {name: i for i, name in enumerate(rows)}
    cmap = plt.get_cmap("tab20")
    for executor, task, start, end in bars:
        y = index[executor]
        color = cmap(hash(task.split(".")[0].rstrip("0123456789")) % 20)
        ax.barh(y, max(end - start, 1e-9), left=start, height=0.6,
                color=color, edgecolor="black", linewidth=0.4)
        if len(bars) <= 30:
            ax.text((start + end) / 2, y, task, ha="center", va="center",
                    fontsize=6, rotation=0, clip_on=True)
    ax.set_yticks(range(len(rows)), rows)
    ax.set_xlabel("time (s)")
    makespan = max(b[3] for b in bars)
    ax.set_title(f"{title}  (makespan {makespan:,.0f} s)", fontsize=10)
    ax.grid(axis="x", alpha=0.3)


def gantt(bars: list[Bar], title: str, path: str | Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 0.5 + 0.45 * len({b[0] for b in bars})))
    _draw(ax, bars, title)
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def gantt_pair(bars_a: list[Bar], title_a: str, bars_b: list[Bar], title_b: str,
               path: str | Path, suptitle: str = "") -> Path:
    """Two Gantt charts stacked with a shared x-axis: the naive-vs-scheduled
    comparison figure (F3 in the plan)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_rows = max(len({b[0] for b in bars_a}), len({b[0] for b in bars_b}))
    fig, (ax_a, ax_b) = plt.subplots(
        2, 1, figsize=(9, 1.2 + 0.9 * n_rows), sharex=True
    )
    _draw(ax_a, bars_a, title_a)
    _draw(ax_b, bars_b, title_b)
    if suptitle:
        fig.suptitle(suptitle, fontsize=11)
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
