"""LLM latency variance: stochastic instances, SHEFT bridge, MC evaluation.

LLM execution times are stochastic — output length varies run to run, and
hosted-API throughput fluctuates far more than a dedicated local node's.
SAGA already ships stochastic schedulers (SHEFT = HEFT on mean+std,
MeanHEFT = HEFT on means). This module builds stochastic instances from an
AgentGraph + ExecutorNetwork, runs those schedulers, and evaluates any
resulting (assignment, per-node order) by Monte-Carlo replay: sample every
task cost and node speed, then re-time the schedule respecting precedence,
transfer delays, and per-node order. Paired sampling (same realization index
across policies) makes comparisons low-variance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from saga.stochastic import StochasticNetwork, StochasticSchedule, StochasticTaskGraph
from saga.utils.random_variable import RandomVariable

from ..graphs.model import AgentGraph
from .executors import ExecutorNetwork


def _lognormal(rng: np.random.Generator, mean: float, sigma: float,
               n: int) -> np.ndarray:
    """Lognormal samples with the requested arithmetic mean."""
    mu = math.log(max(mean, 1e-9)) - sigma * sigma / 2.0
    return rng.lognormal(mu, sigma, n)


@dataclass
class StochasticInstance:
    task_graph: StochasticTaskGraph
    network: StochasticNetwork
    cost_samples: dict[str, np.ndarray]     # task -> per-realization tokens
    speed_samples: dict[str, np.ndarray]    # executor -> per-realization tok/s
    n: int


TIER_COST_SIGMA = {0: 0.20, 1: 0.20, 2: 0.25, 3: 0.35}  # ModelTier -> sigma


def stochastic_instance(
    graph: AgentGraph,
    network: ExecutorNetwork,
    tier_cost_sigma: dict[int, float] | None = None,  # output-length variability
    api_speed_sigma: float = 0.30,   # hosted APIs are volatile...
    local_speed_sigma: float = 0.05, # ...dedicated local nodes are not
    n: int = 400,
    seed: int = 0,
) -> StochasticInstance:
    """Planning model vs. world model, deliberately decoupled.

    The *planning* instance exposes uncertainty only in task costs (as
    RandomVariables, sigma per model tier — long frontier generations vary
    most); node speeds are deterministic means. This matches published SHEFT
    semantics, which determinize execution *time* as mean+std: applying
    mean+std to a speed variable would make volatile nodes look faster, the
    opposite of pessimism. The Monte-Carlo *world* (cost_samples,
    speed_samples) additionally keeps per-node speed volatility, so policies
    are evaluated under conditions their planner never fully saw.
    """
    sigmas = tier_cost_sigma or TIER_COST_SIGMA
    rng = np.random.default_rng(seed)
    cost_samples: dict[str, np.ndarray] = {}
    tasks = []
    for t in graph:
        sigma = sigmas[int(t.min_tier)]
        samples = _lognormal(rng, max(t.output_tokens, 1e-6), sigma, n)
        cost_samples[t.name] = samples
        tasks.append((t.name, RandomVariable(samples=samples)))
    deps = [(e.src, e.dst, float(e.payload_kb)) for e in graph.edges]

    speed_samples: dict[str, np.ndarray] = {}
    nodes = []
    for e in network.executors:
        sigma = api_speed_sigma if e.kind == "api" else local_speed_sigma
        speed_samples[e.name] = _lognormal(rng, e.tokens_per_sec, sigma, n)
        nodes.append((e.name, float(e.tokens_per_sec)))
    edges = []
    for i, a in enumerate(network.executors):
        for b in network.executors[i + 1:]:
            edges.append((a.name, b.name,
                          float(network.bandwidth_kBps(a.name, b.name))))
    # Explicit large-finite self-loops: StochasticNetwork.create wraps its
    # default infinite self-loop speeds into single-sample RandomVariables,
    # and std(inf) is NaN — which poisons SHEFT's mean+std determinization
    # and every upward rank computed from it.
    for e in network.executors:
        edges.append((e.name, e.name, 1e12))

    return StochasticInstance(
        task_graph=StochasticTaskGraph.create(tasks=tasks, dependencies=deps),
        network=StochasticNetwork.create(nodes=nodes, edges=edges),
        cost_samples=cost_samples,
        speed_samples=speed_samples,
        n=n,
    )


def order_map_from(schedule: StochasticSchedule) -> dict[str, list[str]]:
    """executor -> task names in rank order (SAGA super nodes included)."""
    return {
        node: [t.name for t in sorted(tasks, key=lambda t: t.rank)]
        for node, tasks in schedule.mapping.items()
        if tasks
    }


def mc_makespans(
    order_map: dict[str, list[str]],
    graph: AgentGraph,
    network: ExecutorNetwork,
    inst: StochasticInstance,
) -> np.ndarray:
    """Replay the (assignment, per-node order) under each sampled realization.

    Standard list-schedule replay: a task starts when its executor is free,
    all parents are done, and every in-edge payload has arrived. Tasks not in
    the AgentGraph (SAGA's super nodes) run with zero duration.
    """
    assignment = {t: node for node, ts in order_map.items() for t in ts}
    parents = {t: graph.parents(t) for t in graph.tasks}
    in_edges = {t: graph.in_edges(t) for t in graph.tasks}
    total = sum(len(ts) for ts in order_map.values())

    makespans = np.empty(inst.n)
    for k in range(inst.n):
        finish: dict[str, float] = {}
        node_free = {node: 0.0 for node in order_map}
        idx = {node: 0 for node in order_map}
        done = 0
        while done < total:
            progressed = False
            for node, queue in order_map.items():
                i = idx[node]
                if i >= len(queue):
                    continue
                t = queue[i]
                if any(p not in finish for p in parents.get(t, ())):
                    continue
                ready = 0.0
                for e in in_edges.get(t, ()):
                    bw = network.bandwidth_kBps(assignment[e.src], node)
                    transfer = 0.0 if bw == math.inf else e.payload_kb / bw
                    ready = max(ready, finish[e.src] + transfer)
                start = max(node_free[node], ready)
                if t in inst.cost_samples:
                    dur = inst.cost_samples[t][k] / inst.speed_samples[node][k]
                else:
                    dur = 0.0
                finish[t] = start + dur
                node_free[node] = finish[t]
                idx[node] += 1
                done += 1
                progressed = True
            if not progressed:
                raise RuntimeError("Replay deadlock: inconsistent order map")
        makespans[k] = max(
            finish[t] for t in finish if t in graph.tasks
        )
    return makespans
