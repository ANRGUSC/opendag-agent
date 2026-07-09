"""Baseline strategies and the constraint wrapper, as SAGA ``Scheduler``s.

The baselines reproduce what today's agent frameworks actually do (fixed
model assignment, no placement reasoning) while remaining *feasible*: they
honor pins (data physically lives somewhere) and tier constraints (a 1B edge
model cannot serve a frontier-tier task), so comparisons against classical
schedulers are honest.

``feasible`` maps each real task to its allowed executor names — produce it
with :meth:`opendag.schedule.executors.ExecutorNetwork.feasibility_map`.
Tasks absent from the map (e.g. SAGA's super nodes) may run anywhere.
"""
from __future__ import annotations

import random
from typing import Dict, List

from saga import Network, Schedule, ScheduledTask, Scheduler, TaskGraph

from .bridge import assignments_from_schedule, is_super


def _add(schedule: Schedule, network: Network, task_graph: TaskGraph,
         task_name: str, node_name: str) -> None:
    start = schedule.get_earliest_start_time(task_name, node_name, append_only=False)
    speed = network.get_node(node_name).speed
    cost = task_graph.get_task(task_name).cost
    schedule.add_task(
        ScheduledTask(node=node_name, name=task_name, start=start, end=start + cost / speed)
    )


class AssignmentScheduler(Scheduler):
    """Realize a fixed task->executor assignment as a valid SAGA schedule
    (insertion-based, topological order). Unassigned tasks (super nodes)
    go to the lexicographically first node; their cost is ~0."""

    assignment: Dict[str, str] = {}

    def schedule(self, network: Network, task_graph: TaskGraph) -> Schedule:
        schedule = Schedule(task_graph, network)
        default = sorted(n.name for n in network.nodes)[0]
        for task in task_graph.topological_sort():
            _add(schedule, network, task_graph, task.name,
                 self.assignment.get(task.name, default))
        return schedule


class _PolicyScheduler(Scheduler):
    """Shared machinery: iterate topologically, pick among feasible nodes."""

    feasible: Dict[str, List[str]] = {}

    def _candidates(self, task_name: str, network: Network) -> List[str]:
        if task_name in self.feasible:
            return sorted(self.feasible[task_name])
        return sorted(n.name for n in network.nodes)

    def _pick(self, task_name: str, candidates: List[str], step: int,
              network: Network, schedule: Schedule,
              task_graph: TaskGraph) -> str:
        raise NotImplementedError

    def schedule(self, network: Network, task_graph: TaskGraph) -> Schedule:
        schedule = Schedule(task_graph, network)
        for step, task in enumerate(task_graph.topological_sort()):
            node = self._pick(task.name, self._candidates(task.name, network),
                              step, network, schedule, task_graph)
            _add(schedule, network, task_graph, task.name, node)
        return schedule


class AllOnScheduler(_PolicyScheduler):
    """Everything on one target executor when feasible (pins excepted).

    With the target set to a frontier API node this is the framework-default
    baseline: one hosted model runs every step ("AllAPI")."""

    target: str = ""

    def _pick(self, task_name, candidates, step, network, schedule, task_graph):
        return self.target if self.target in candidates else candidates[0]


class LocalFirstScheduler(_PolicyScheduler):
    """Prefer the fastest non-API executor; use an API node only when the
    tier constraint forces it ("AllEdge" / local-first)."""

    api_nodes: List[str] = []

    def _pick(self, task_name, candidates, step, network, schedule, task_graph):
        local = [c for c in candidates if c not in self.api_nodes]
        pool = local if local else candidates
        return max(pool, key=lambda n: (network.get_node(n).speed, n))


class RoundRobinScheduler(_PolicyScheduler):
    """Cycle through each task's feasible executors in name order."""

    def _pick(self, task_name, candidates, step, network, schedule, task_graph):
        return candidates[step % len(candidates)]


class RandomScheduler(_PolicyScheduler):
    """Uniform random feasible executor (seeded, reproducible)."""

    seed: int = 0

    def schedule(self, network: Network, task_graph: TaskGraph) -> Schedule:
        self._rng = random.Random(self.seed)
        return super().schedule(network, task_graph)

    def _pick(self, task_name, candidates, step, network, schedule, task_graph):
        return self._rng.choice(candidates)


class GreedyCheapestScheduler(_PolicyScheduler):
    """Per-task cheapest feasible executor ($/Mtok out), fastest as tiebreak.
    Greedy on cost with no view of the critical path or communication."""

    prices: Dict[str, float] = {}

    def _pick(self, task_name, candidates, step, network, schedule, task_graph):
        return min(candidates,
                   key=lambda n: (self.prices.get(n, 0.0),
                                  -network.get_node(n).speed, n))


class ConstrainedScheduler(Scheduler):
    """Make any (constraint-unaware) SAGA scheduler feasibility-safe.

    Runs ``inner`` on the full network, then repairs any placement that
    violates ``feasible`` by moving the task to its fastest allowed executor
    and rebuilding the schedule from the repaired assignment (topological,
    insertion-based). If nothing violates, the inner schedule is returned
    untouched. Note: a repair rebuild drops task duplication, which is the
    honest price of enforcing constraints post-hoc; constraint-aware variants
    of the classical algorithms are future work (see docs).
    """

    inner: Scheduler
    feasible: Dict[str, List[str]] = {}

    @property
    def name(self) -> str:
        return self.inner.name

    def schedule(self, network: Network, task_graph: TaskGraph) -> Schedule:
        schedule = self.inner.schedule(network, task_graph)
        # Any infeasible instance counts — schedulers with task duplication
        # (HEFT-family, HBMCT) may place a *copy* on a forbidden node even
        # when the earliest instance is fine. Rebuilding drops duplicates.
        dirty = False
        for node, tasks in schedule.items():
            for st in tasks:
                allowed = self.feasible.get(st.name)
                if allowed is not None and node not in allowed:
                    dirty = True
        assignment = assignments_from_schedule(schedule)
        repaired = dict(assignment)
        for task_name, node in assignment.items():
            allowed = self.feasible.get(task_name)
            if allowed is not None and node not in allowed:
                repaired[task_name] = max(
                    allowed, key=lambda n: (network.get_node(n).speed, n)
                )
                dirty = True
        # Completeness: some inner schedulers (observed: HBMCT) can drop
        # tasks from their schedule entirely. Place any missing real task on
        # its fastest feasible executor.
        for task in task_graph.tasks:
            if is_super(task.name) or task.name in repaired:
                continue
            allowed = self.feasible.get(task.name) \
                or [n.name for n in network.nodes]
            repaired[task.name] = max(
                allowed, key=lambda n: (network.get_node(n).speed, n)
            )
            dirty = True
        if not dirty:
            return schedule
        return AssignmentScheduler(assignment=repaired).schedule(network, task_graph)
