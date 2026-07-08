"""LocalRunner: execute an AgentGraph in-process under a fixed assignment.

This is the development/CI runner. It honors the same semantics the Wayline
execution path will honor (dependencies, per-executor serialization,
inter-executor transfer delays) but runs everything in one asyncio loop with
a pluggable LLM client. ``MockLLMClient`` makes runs free and deterministic;
time is simulated at ``speedup``x so a minutes-long workflow finishes in
milliseconds while producing realistic virtual timestamps.

Official experiment numbers come from Wayline runs on a k3s cluster (P2+);
LocalRunner exists so development, tests, and outside users need no cluster.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from ..graphs.model import AgentGraph, AgentTask
from ..schedule.costs import task_tokens
from ..schedule.executors import Executor, ExecutorNetwork


@dataclass
class LLMResult:
    text: str
    tokens_in: float
    tokens_out: float


class LLMClient(Protocol):
    async def generate(self, task: AgentTask, executor: Executor, prompt: str) -> LLMResult: ...


class MockLLMClient:
    """Deterministic stand-in for a model call.

    Sleeps the task's simulated execution time (output_tokens / executor
    speed, divided by ``speedup``) and returns synthetic text sized to the
    task's expected output. No network, no keys, no cost.
    """

    def __init__(self, speedup: float = 100.0) -> None:
        if speedup <= 0:
            raise ValueError("speedup must be > 0")
        self.speedup = speedup

    async def generate(self, task: AgentTask, executor: Executor, prompt: str) -> LLMResult:
        exec_seconds = task.output_tokens / executor.tokens_per_sec
        await asyncio.sleep(exec_seconds / self.speedup)
        words = max(1, int(task.output_tokens // 2))
        text = f"[{executor.name}:{task.name}] " + " ".join(
            f"tok{i}" for i in range(min(words, 200))
        )
        return LLMResult(text=text, tokens_in=len(prompt) / 4.0, tokens_out=task.output_tokens)


@dataclass
class TaskRecord:
    name: str
    executor: str
    start_s: float          # virtual seconds since run start
    end_s: float
    tokens_in: float
    tokens_out: float
    usd: float
    output_preview: str


@dataclass
class RunResult:
    graph: str
    strategy: str
    assignment: dict[str, str]
    records: list[TaskRecord] = field(default_factory=list)

    @property
    def makespan_s(self) -> float:
        return max((r.end_s for r in self.records), default=0.0)

    @property
    def total_usd(self) -> float:
        return sum(r.usd for r in self.records)

    def to_dict(self) -> dict:
        return {
            "format": "opendag/run-v0",
            "graph": self.graph,
            "strategy": self.strategy,
            "assignment": self.assignment,
            "makespan_s": self.makespan_s,
            "total_usd": self.total_usd,
            "records": [asdict(r) for r in self.records],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


class LocalRunner:
    """Run ``graph`` under ``assignment`` on ``network`` with ``client``."""

    def __init__(
        self,
        graph: AgentGraph,
        network: ExecutorNetwork,
        assignment: dict[str, str],
        client: LLMClient | None = None,
        speedup: float = 100.0,
        strategy: str = "unspecified",
    ) -> None:
        graph.validate()
        missing = [t.name for t in graph if t.name not in assignment]
        if missing:
            raise ValueError(f"Assignment missing tasks: {missing}")
        for name, executor in assignment.items():
            if name in graph.tasks and not network.can_run(executor, graph.tasks[name]):
                raise ValueError(f"Infeasible assignment: {name} on {executor}")
        self.graph = graph
        self.network = network
        self.assignment = assignment
        self.speedup = speedup
        self.client = client or MockLLMClient(speedup=speedup)
        self.strategy = strategy

    def run(self) -> RunResult:
        return asyncio.run(self._run())

    async def _run(self) -> RunResult:
        result = RunResult(self.graph.name, self.strategy, dict(self.assignment))
        done: dict[str, asyncio.Event] = {n: asyncio.Event() for n in self.graph.tasks}
        finish_v: dict[str, float] = {}
        outputs: dict[str, str] = {}
        locks: dict[str, asyncio.Lock] = {e.name: asyncio.Lock() for e in self.network.executors}
        t0 = time.perf_counter()

        def now_v() -> float:
            return (time.perf_counter() - t0) * self.speedup

        async def run_task(name: str) -> None:
            task = self.graph.tasks[name]
            executor = self.network.by_name(self.assignment[name])

            for parent in self.graph.parents(name):
                await done[parent].wait()

            # Payload transfer from each parent's executor (overlapping
            # transfers: the slowest one gates the start).
            ready_v = 0.0
            for edge in self.graph.in_edges(name):
                bw = self.network.bandwidth_kBps(self.assignment[edge.src], executor.name)
                transfer = 0.0 if bw == float("inf") else edge.payload_kb / bw
                ready_v = max(ready_v, finish_v[edge.src] + transfer)
            wait_v = ready_v - now_v()
            if wait_v > 0:
                await asyncio.sleep(wait_v / self.speedup)

            async with locks[executor.name]:
                prompt = task.role + "\n\n" + "\n".join(
                    outputs[p] for p in sorted(self.graph.parents(name))
                )
                start_v = now_v()
                llm = await self.client.generate(task, executor, prompt)
                end_v = now_v()

            tokens_in, tokens_out = task_tokens(self.graph, name)
            usd = 0.0
            if task.kind == "llm":
                usd = (tokens_in * executor.usd_per_mtok_in
                       + tokens_out * executor.usd_per_mtok_out) / 1e6
            result.records.append(TaskRecord(
                name=name, executor=executor.name, start_s=start_v, end_s=end_v,
                tokens_in=tokens_in, tokens_out=tokens_out, usd=usd,
                output_preview=llm.text[:120],
            ))
            outputs[name] = llm.text
            finish_v[name] = end_v
            done[name].set()

        await asyncio.gather(*(run_task(n) for n in self.graph.topological_order()))
        result.records.sort(key=lambda r: r.start_s)
        return result
