"""AgentGraph <-> SAGA bridge.

SAGA auto-inserts ``__super_source__`` / ``__super_sink__`` nodes (cost 0)
when a task graph has multiple sources or sinks; helpers here hide them.
"""
from __future__ import annotations

import math

from saga import Network, Schedule, TaskGraph

from ..graphs.model import AgentGraph

SUPER_NODES = ("__super_source__", "__super_sink__")

# Floor so ranks/speed divisions never see a zero-cost real task.
_MIN_COST = 1e-6


def is_super(task_name: str) -> bool:
    return task_name in SUPER_NODES


def to_saga_task_graph(graph: AgentGraph) -> TaskGraph:
    """Export: node cost = expected output tokens, edge size = payload KB."""
    graph.validate()
    tasks = [(t.name, max(t.output_tokens, _MIN_COST)) for t in graph]
    deps = [(e.src, e.dst, e.payload_kb) for e in graph.edges]
    return TaskGraph.create(tasks=tasks, dependencies=deps)


def assignments_from_schedule(schedule: Schedule) -> dict[str, str]:
    """task name -> executor name, ignoring SAGA's super nodes.

    Schedulers with task duplication may place a task on several nodes; the
    instance that finishes earliest is taken as the assignment of record.
    """
    best: dict[str, tuple[float, str]] = {}
    for node, tasks in schedule.items():
        for st in tasks:
            if is_super(st.name):
                continue
            if st.name not in best or st.end < best[st.name][0]:
                best[st.name] = (st.end, node)
    return {name: node for name, (_, node) in best.items()}


def validate_schedule(
    schedule: Schedule,
    feasible: dict[str, list[str]] | None = None,
    eps: float = 1e-6,
) -> None:
    """Raise ValueError unless ``schedule`` is internally consistent.

    Checks: every task scheduled; no overlap on any executor; every task
    instance starts only after some instance of each parent has finished and
    its payload has arrived (SAGA comm model: size / link speed); execution
    time matches cost / speed; and, if ``feasible`` is given, every real
    task sits on an allowed executor.
    """
    tg, net = schedule.task_graph, schedule.network

    instances: dict[str, list] = {}
    for node, tasks in schedule.items():
        ordered = sorted(tasks, key=lambda t: (t.start, t.end))
        for a, b in zip(ordered, ordered[1:]):
            if b.start < a.end - eps:
                raise ValueError(f"Overlap on {node}: {a} then {b}")
        for st in tasks:
            speed = net.get_node(node).speed
            expected = tg.get_task(st.name).cost / speed
            if not math.isclose(st.end - st.start, expected, rel_tol=1e-6, abs_tol=eps):
                raise ValueError(
                    f"Duration mismatch for {st.name} on {node}: "
                    f"{st.end - st.start} != {expected}"
                )
            instances.setdefault(st.name, []).append(st)

    for task in tg.tasks:
        if task.name not in instances:
            raise ValueError(f"Task {task.name} is not scheduled")

    for dep in tg.dependencies:
        for child in instances[dep.target]:
            ok = False
            for parent in instances[dep.source]:
                bw = net.get_edge(parent.node, child.node).speed
                arrival = parent.end + (dep.size / bw if bw != math.inf else 0.0)
                if arrival <= child.start + eps:
                    ok = True
                    break
            if not ok:
                raise ValueError(
                    f"Precedence violated: {dep.source} -> {dep.target} "
                    f"(child instance on {child.node} starts at {child.start})"
                )

    if feasible is not None:
        for name, insts in instances.items():
            if is_super(name):
                continue
            for st in insts:
                if st.node not in feasible[name]:
                    raise ValueError(
                        f"Infeasible placement: {name} on {st.node} "
                        f"(allowed: {feasible[name]})"
                    )
