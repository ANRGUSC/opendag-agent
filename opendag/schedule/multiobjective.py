"""Cost-aware scheduling: trade makespan against dollars with one knob.

``CostAwareScheduler`` is a greedy insertion scheduler that picks, for each
task in topological order, the feasible executor minimizing

    earliest_finish_time  +  lam * usd(task, executor)

``lam`` has units of seconds-per-dollar: how many seconds of makespan you
would pay to save one dollar. lam=0 reduces to pure earliest-finish greedy
(MCT-like); large lam converges to cheapest-feasible. Sweeping lam traces a
navigable cost/latency Pareto curve — the knob agent frameworks don't have.
"""
from __future__ import annotations

from typing import Dict, List

from saga import Network, Schedule, TaskGraph

from ..graphs.model import AgentGraph
from .baselines import _PolicyScheduler
from .costs import task_tokens
from .executors import ExecutorNetwork

DEFAULT_LAMBDAS = (0.0, 2.0, 10.0, 60.0, 300.0, 1800.0)


def per_task_usd_map(graph: AgentGraph, network: ExecutorNetwork
                     ) -> dict[str, dict[str, float]]:
    """usd[task][executor]: dollar cost of running the task there."""
    usd: dict[str, dict[str, float]] = {}
    for task in graph:
        tokens_in, tokens_out = task_tokens(graph, task.name)
        row: dict[str, float] = {}
        for e in network.executors:
            if task.kind != "llm":
                row[e.name] = 0.0
            else:
                row[e.name] = (tokens_in * e.usd_per_mtok_in
                               + tokens_out * e.usd_per_mtok_out) / 1e6
        usd[task.name] = row
    return usd


class CostAwareScheduler(_PolicyScheduler):
    """Greedy EFT + lam * $ (see module docstring)."""

    lam: float = 0.0
    usd: Dict[str, Dict[str, float]] = {}

    def _pick(self, task_name: str, candidates: List[str], step: int,
              network: Network, schedule: Schedule,
              task_graph: TaskGraph) -> str:
        cost = task_graph.get_task(task_name).cost
        task_usd = self.usd.get(task_name, {})

        def score(node_name: str) -> tuple[float, str]:
            start = schedule.get_earliest_start_time(task_name, node_name,
                                                     append_only=False)
            finish = start + cost / network.get_node(node_name).speed
            return finish + self.lam * task_usd.get(node_name, 0.0), node_name

        return min(candidates, key=score)


def pareto_front(points: list[tuple[float, float]]) -> list[int]:
    """Indices of non-dominated points, minimizing both coordinates.
    Ties kept; returned in ascending order of the first coordinate."""
    order = sorted(range(len(points)), key=lambda i: (points[i][0], points[i][1]))
    front: list[int] = []
    best_y = float("inf")
    for i in order:
        if points[i][1] < best_y - 1e-12:
            front.append(i)
            best_y = points[i][1]
    return front
