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
    haiku_lanes: int = 1,
    sonnet_lanes: int = 1,
) -> ExecutorNetwork:
    """API concurrency is modeled as parallel virtual lanes: lane 0 keeps the
    base name ("haiku", "sonnet"); extra lanes are "haiku-1", "haiku-2", ..."""

    def lane_names(base: str, lanes: int) -> list[str]:
        return [base] + [f"{base}-{i}" for i in range(1, lanes)]

    executors = [
        Executor(f"site{s}", ModelTier.SMALL, site_tokens_per_sec, kind="edge")
        for s in range(sites)
    ]
    executors += [Executor("mid", ModelTier.MEDIUM, mid_tokens_per_sec, kind="cloud")]
    executors += [
        Executor(name, ModelTier.MEDIUM, haiku_tokens_per_sec, 1.0, 5.0, "api")
        for name in lane_names("haiku", haiku_lanes)
    ]
    executors += [
        Executor(name, ModelTier.FRONTIER, sonnet_tokens_per_sec, 3.0, 15.0, "api")
        for name in lane_names("sonnet", sonnet_lanes)
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


REGIMES = ("edge_heavy", "hybrid", "api_rich")


def regime_network(regime: str, sites: int = 6) -> ExecutorNetwork:
    """The three E1 network regimes.

    edge_heavy: slow 0.5 Mbps site uplinks, single API lane each — the
        constrained-edge world where locality dominates.
    hybrid: the default 2 Mbps uplinks, modest API concurrency.
    api_rich: fast links and wide API concurrency — the cloud-friendly world
        where naive AllAPI should be hardest to beat.
    """
    if regime == "edge_heavy":
        return default_network(sites=sites, uplink_kBps=60.0,
                               haiku_lanes=1, sonnet_lanes=1)
    if regime == "hybrid":
        return default_network(sites=sites, uplink_kBps=250.0,
                               haiku_lanes=2, sonnet_lanes=1)
    if regime == "api_rich":
        return default_network(sites=sites, uplink_kBps=1250.0,
                               haiku_lanes=4, sonnet_lanes=2)
    raise ValueError(f"Unknown regime: {regime!r} (choose from {REGIMES})")


def api_node_names(network: ExecutorNetwork) -> list[str]:
    return [e.name for e in network.executors if e.kind == "api"]


def price_map(network: ExecutorNetwork) -> dict[str, float]:
    return {e.name: e.usd_per_mtok_out for e in network.executors}
