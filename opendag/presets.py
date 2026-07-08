"""Reference executor networks used by tests, experiments, and docs.

``default_network`` models the planned testbed shape: per-site edge nodes
hosting ~3B SLMs behind constrained uplinks, one mid-tier 8B cloud/lab node,
and two hosted API tiers (fast/cheap and frontier) as virtual nodes.
Numbers are declared, plausible parameters for P0; the P2 profiler replaces
them with measurements.
"""
from __future__ import annotations

from .graphs.model import ModelTier
from .schedule.executors import Executor, ExecutorNetwork


def default_network(
    sites: int = 3,
    uplink_kBps: float = 250.0,   # ~2 Mbps constrained site uplink
    lan_kBps: float = 1250.0,     # ~10 Mbps everywhere else
    site_tokens_per_sec: float = 8.0,     # ~3B on edge CPU
    mid_tokens_per_sec: float = 20.0,     # ~8B on the mid-tier node
    haiku_tokens_per_sec: float = 70.0,
    sonnet_tokens_per_sec: float = 50.0,
) -> ExecutorNetwork:
    executors = [
        Executor(f"site{s}", ModelTier.SMALL, site_tokens_per_sec, kind="edge")
        for s in range(sites)
    ]
    executors += [
        Executor("mid", ModelTier.MEDIUM, mid_tokens_per_sec, kind="cloud"),
        Executor("haiku", ModelTier.MEDIUM, haiku_tokens_per_sec, 1.0, 5.0, "api"),
        Executor("sonnet", ModelTier.FRONTIER, sonnet_tokens_per_sec, 3.0, 15.0, "api"),
    ]
    overrides: dict[tuple[str, str], float] = {}
    names = [e.name for e in executors]
    for s in range(sites):
        for other in names:
            if other != f"site{s}":
                overrides[(f"site{s}", other)] = uplink_kBps
    return ExecutorNetwork(
        executors=executors,
        default_bandwidth_kBps=lan_kBps,
        overrides=overrides,
    )


def api_node_names(network: ExecutorNetwork) -> list[str]:
    return [e.name for e in network.executors if e.kind == "api"]


def price_map(network: ExecutorNetwork) -> dict[str, float]:
    return {e.name: e.usd_per_mtok_out for e in network.executors}
