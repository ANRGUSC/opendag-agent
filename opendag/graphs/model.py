"""Agentic task-graph model.

An :class:`AgentGraph` describes a multi-agent LLM workflow as a DAG:
nodes are typed agent steps (LLM calls, tool calls, aggregations) and
edges carry the context payload shipped from producer to consumer.

Units used throughout opendag:
  * task compute weight  = expected output tokens (LLM decode dominates)
  * executor speed       = tokens/second
  * edge payload         = kilobytes (KB)
  * link bandwidth       = kilobytes/second (KB/s)
so both execution time (tokens / tok-per-s) and transfer time (KB / KB-per-s)
come out in seconds and compose in a SAGA schedule.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Iterator


class ModelTier(IntEnum):
    """Minimum model capability required by a task (quality-confound control).

    Schedulers may only place a task on an executor whose tier is >= the
    task's ``min_tier``. Tiers are coarse capability classes, not sizes:
      ANY      -- any model, including ~1B edge SLMs (and non-LLM tool tasks)
      SMALL    -- ~3B-class and up
      MEDIUM   -- ~8B-class and up (includes fast hosted models, e.g. Haiku)
      FRONTIER -- frontier hosted models only (e.g. Sonnet)
    """

    ANY = 0
    SMALL = 1
    MEDIUM = 2
    FRONTIER = 3


@dataclass(frozen=True)
class AgentTask:
    """One step of an agent workflow.

    Attributes:
        name: Unique task name within the graph.
        kind: "llm" (model call), "tool" (non-LLM computation/IO), or
            "aggregate" (merge/format step, negligible compute).
        role: Role prompt template for LLM tasks (informational in mock mode).
        min_tier: Minimum executor tier allowed to run this task.
        output_tokens: Expected output tokens; the task's compute weight.
        pinned_executor: If set, the task MUST run on the named executor
            (e.g. data-source tasks pinned to the site where the data lives).
        tools: Names of tools this task is allowed to call (capability
            manifest; enforced by the task runtime in later phases).
    """

    name: str
    kind: str = "llm"
    role: str = ""
    min_tier: ModelTier = ModelTier.ANY
    output_tokens: float = 256.0
    pinned_executor: str | None = None
    tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in ("llm", "tool", "aggregate"):
            raise ValueError(f"Unknown task kind: {self.kind!r}")
        if self.output_tokens < 0:
            raise ValueError("output_tokens must be >= 0")


@dataclass(frozen=True)
class AgentEdge:
    """A dependency edge carrying ``payload_kb`` kilobytes from src to dst."""

    src: str
    dst: str
    payload_kb: float = 4.0

    def __post_init__(self) -> None:
        if self.payload_kb < 0:
            raise ValueError("payload_kb must be >= 0")


class AgentGraph:
    """A DAG of :class:`AgentTask` nodes joined by :class:`AgentEdge` edges."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.tasks: dict[str, AgentTask] = {}
        self._edges: dict[tuple[str, str], AgentEdge] = {}

    # -- construction -------------------------------------------------------
    def add_task(self, task: AgentTask) -> AgentTask:
        if task.name in self.tasks:
            raise ValueError(f"Duplicate task name: {task.name}")
        self.tasks[task.name] = task
        return task

    def add_edge(self, src: str, dst: str, payload_kb: float = 4.0) -> AgentEdge:
        for endpoint in (src, dst):
            if endpoint not in self.tasks:
                raise ValueError(f"Edge references unknown task: {endpoint}")
        if (src, dst) in self._edges:
            raise ValueError(f"Duplicate edge: {src} -> {dst}")
        edge = AgentEdge(src=src, dst=dst, payload_kb=payload_kb)
        self._edges[(src, dst)] = edge
        self._invalidate_order()
        return edge

    # -- queries ------------------------------------------------------------
    @property
    def edges(self) -> list[AgentEdge]:
        return list(self._edges.values())

    def parents(self, name: str) -> list[str]:
        return [e.src for e in self._edges.values() if e.dst == name]

    def children(self, name: str) -> list[str]:
        return [e.dst for e in self._edges.values() if e.src == name]

    def in_edges(self, name: str) -> list[AgentEdge]:
        return [e for e in self._edges.values() if e.dst == name]

    def sources(self) -> list[str]:
        return [n for n in self.tasks if not self.parents(n)]

    def sinks(self) -> list[str]:
        return [n for n in self.tasks if not self.children(n)]

    _order_cache: list[str] | None = None

    def _invalidate_order(self) -> None:
        self._order_cache = None

    def topological_order(self) -> list[str]:
        """Kahn's algorithm; raises ValueError if the graph has a cycle."""
        if self._order_cache is not None:
            return list(self._order_cache)
        indeg = {n: 0 for n in self.tasks}
        for e in self._edges.values():
            indeg[e.dst] += 1
        ready = sorted(n for n, d in indeg.items() if d == 0)
        order: list[str] = []
        while ready:
            n = ready.pop(0)
            order.append(n)
            for c in sorted(self.children(n)):
                indeg[c] -= 1
                if indeg[c] == 0:
                    ready.append(c)
            ready.sort()
        if len(order) != len(self.tasks):
            raise ValueError(f"AgentGraph {self.name!r} contains a cycle")
        self._order_cache = order
        return list(order)

    def validate(self) -> None:
        """Raise ValueError on structural problems (cycles, empty graph)."""
        if not self.tasks:
            raise ValueError("AgentGraph has no tasks")
        self.topological_order()

    def __iter__(self) -> Iterator[AgentTask]:
        return iter(self.tasks.values())

    def __len__(self) -> int:
        return len(self.tasks)

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": "opendag/agent-graph-v0",
            "name": self.name,
            "tasks": [
                {
                    "name": t.name,
                    "kind": t.kind,
                    "role": t.role,
                    "min_tier": t.min_tier.name,
                    "output_tokens": t.output_tokens,
                    "pinned_executor": t.pinned_executor,
                    "tools": list(t.tools),
                }
                for t in self.tasks.values()
            ],
            "edges": [
                {"src": e.src, "dst": e.dst, "payload_kb": e.payload_kb}
                for e in self._edges.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentGraph":
        graph = cls(data["name"])
        for t in data["tasks"]:
            graph.add_task(
                AgentTask(
                    name=t["name"],
                    kind=t.get("kind", "llm"),
                    role=t.get("role", ""),
                    min_tier=ModelTier[t.get("min_tier", "ANY")],
                    output_tokens=t.get("output_tokens", 256.0),
                    pinned_executor=t.get("pinned_executor"),
                    tools=tuple(t.get("tools", ())),
                )
            )
        for e in data["edges"]:
            graph.add_edge(e["src"], e["dst"], e.get("payload_kb", 4.0))
        return graph

    def to_json(self, path: str | Path | None = None) -> str:
        text = json.dumps(self.to_dict(), indent=2)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    @classmethod
    def from_json(cls, source: str | Path) -> "AgentGraph":
        path = Path(source)
        text = path.read_text(encoding="utf-8") if path.exists() else str(source)
        return cls.from_dict(json.loads(text))

    def to_networkx(self):
        """Return an ``nx.DiGraph`` view (node attr ``weight`` = output tokens,
        edge attr ``weight`` = payload KB), for visualization and analysis."""
        import networkx as nx

        g = nx.DiGraph(name=self.name)
        for t in self.tasks.values():
            g.add_node(t.name, weight=t.output_tokens, kind=t.kind, tier=t.min_tier.name)
        for e in self._edges.values():
            g.add_edge(e.src, e.dst, weight=e.payload_kb)
        return g
