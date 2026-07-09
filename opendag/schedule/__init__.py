"""SAGA bridge: executors, exports, baselines, constraints, and costs."""
from .baselines import (
    AllOnScheduler,
    AssignmentScheduler,
    ConstrainedScheduler,
    GreedyCheapestScheduler,
    LocalFirstScheduler,
    RandomScheduler,
    RoundRobinScheduler,
)
from .bridge import (
    assignments_from_schedule,
    is_super,
    to_saga_task_graph,
    validate_schedule,
)
from .costs import ROLE_PROMPT_TOKENS, TOKENS_PER_KB, assignment_cost_usd, task_tokens
from .executors import Executor, ExecutorNetwork
from .multiobjective import (
    DEFAULT_LAMBDAS,
    CostAwareScheduler,
    pareto_front,
    per_task_usd_map,
)


def classical_schedulers(names: list[str] | None = None) -> dict:
    """Instantiate SAGA's classical schedulers by short name.

    Defaults to a fast, representative subset; pass explicit names for more.
    (BruteForce and SMT are available in SAGA but excluded here: exponential
    search / solver dependencies make them unsuitable as defaults.)
    """
    import saga.schedulers as ss

    available = {
        "HEFT": ss.HeftScheduler,
        "CPoP": ss.CpopScheduler,
        "MinMin": ss.MinMinScheduler,
        "MaxMin": ss.MaxMinScheduler,
        "ETF": ss.ETFScheduler,
        "Sufferage": ss.SufferageScheduler,
        "MCT": ss.MCTScheduler,
        "MET": ss.METScheduler,
        "OLB": ss.OLBScheduler,
        "FastestNode": ss.FastestNodeScheduler,
        "Duplex": ss.DuplexScheduler,
        "WBA": ss.WBAScheduler,
        "GDL": ss.GDLScheduler,
        "FCP": ss.FCPScheduler,
        "FLB": ss.FLBScheduler,
        "BIL": ss.BILScheduler,
        "DPS": ss.DPSScheduler,
        "HBMCT": ss.HbmctScheduler,
        "MSBC": ss.MsbcScheduler,
        "MST": ss.MSTScheduler,
        # ss.HybridScheduler is a meta-scheduler (requires a portfolio via its
        # `schedulers` field) rather than a standalone algorithm; construct it
        # explicitly if you want portfolio-best-of behavior.
    }
    if names is None:
        names = ["HEFT", "CPoP", "MinMin"]
    return {n: available[n]() for n in names}


__all__ = [
    "AllOnScheduler",
    "AssignmentScheduler",
    "ConstrainedScheduler",
    "GreedyCheapestScheduler",
    "LocalFirstScheduler",
    "RandomScheduler",
    "RoundRobinScheduler",
    "assignments_from_schedule",
    "is_super",
    "to_saga_task_graph",
    "validate_schedule",
    "ROLE_PROMPT_TOKENS",
    "TOKENS_PER_KB",
    "assignment_cost_usd",
    "task_tokens",
    "Executor",
    "ExecutorNetwork",
    "classical_schedulers",
    "DEFAULT_LAMBDAS",
    "CostAwareScheduler",
    "pareto_front",
    "per_task_usd_map",
]
