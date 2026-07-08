"""Executors (edge SLM hosts, cloud nodes, hosted APIs) and their network.

An :class:`ExecutorNetwork` converts directly to a SAGA ``Network``:
executor ``tokens_per_sec`` becomes node speed, pairwise ``bandwidth_kBps``
becomes link speed, so SAGA's ``cost/speed`` and ``size/speed`` semantics
yield seconds for both compute and communication (see units note in
``opendag.graphs.model``).

Hosted APIs are modeled as *virtual nodes*: effectively-fast executors that
carry a $/Mtok price. Provider-side concurrency is modeled by adding k
parallel virtual nodes for the same API (e.g. ``haiku-0``, ``haiku-1``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from saga import Network

from ..graphs.model import AgentGraph, AgentTask, ModelTier


@dataclass(frozen=True)
class Executor:
    """A place an agent task can run.

    Attributes:
        name: Unique executor name (referenced by ``AgentTask.pinned_executor``).
        tier: Highest :class:`ModelTier` this executor's model can serve.
        tokens_per_sec: Effective decode throughput of the model hosted here.
        usd_per_mtok_in / usd_per_mtok_out: API price; 0 for local executors.
        kind: "edge", "cloud", or "api" (used by baseline policies and costs).
    """

    name: str
    tier: ModelTier
    tokens_per_sec: float
    usd_per_mtok_in: float = 0.0
    usd_per_mtok_out: float = 0.0
    kind: str = "edge"

    def __post_init__(self) -> None:
        if self.tokens_per_sec <= 0:
            raise ValueError("tokens_per_sec must be > 0")
        if self.kind not in ("edge", "cloud", "api"):
            raise ValueError(f"Unknown executor kind: {self.kind!r}")


@dataclass
class ExecutorNetwork:
    """Executors plus pairwise bandwidths (KB/s).

    ``default_bandwidth_kBps`` applies to any pair without an explicit
    override. Overrides are symmetric: set ``("a", "b")`` once.
    """

    executors: list[Executor]
    default_bandwidth_kBps: float = 1250.0  # 10 Mbps
    overrides: dict[tuple[str, str], float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        names = [e.name for e in self.executors]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate executor names")
        if self.default_bandwidth_kBps <= 0:
            raise ValueError("default_bandwidth_kBps must be > 0")

    def by_name(self, name: str) -> Executor:
        for e in self.executors:
            if e.name == name:
                return e
        raise ValueError(f"Unknown executor: {name}")

    def bandwidth_kBps(self, a: str, b: str) -> float:
        if a == b:
            return float("inf")
        key = (a, b) if (a, b) in self.overrides else (b, a)
        return self.overrides.get(key, self.default_bandwidth_kBps)

    def to_saga(self) -> Network:
        """Build the SAGA Network (complete graph; every pair gets a positive
        bandwidth so no placement is silently unreachable)."""
        nodes = [(e.name, e.tokens_per_sec) for e in self.executors]
        edges = []
        for i, a in enumerate(self.executors):
            for b in self.executors[i + 1:]:
                edges.append((a.name, b.name, self.bandwidth_kBps(a.name, b.name)))
        return Network.create(nodes=nodes, edges=edges)

    # -- feasibility ---------------------------------------------------------
    def can_run(self, executor: Executor | str, task: AgentTask) -> bool:
        e = executor if isinstance(executor, Executor) else self.by_name(executor)
        if task.pinned_executor is not None and e.name != task.pinned_executor:
            return False
        return e.tier >= task.min_tier

    def feasible_executors(self, task: AgentTask) -> list[Executor]:
        return [e for e in self.executors if self.can_run(e, task)]

    def feasibility_map(self, graph: AgentGraph) -> dict[str, list[str]]:
        """task name -> feasible executor names. Raises if any task has none."""
        out: dict[str, list[str]] = {}
        for task in graph:
            feasible = [e.name for e in self.feasible_executors(task)]
            if not feasible:
                raise ValueError(
                    f"Task {task.name!r} (min_tier={task.min_tier.name}, "
                    f"pinned={task.pinned_executor!r}) has no feasible executor"
                )
            out[task.name] = feasible
        return out
