"""Dollar-cost model for an assignment.

Only ``kind == "llm"`` tasks incur API cost; local executors are $0 in P0
(droplet/energy amortization arrives with the profiler in P2). Input tokens
are estimated from the role prompt plus everything shipped in on in-edges;
this deliberately charges naive placements for moving raw data into a paid
context window. The estimate ignores provider context-window limits: a
placement that would overflow a real window simply shows up as expensive,
which is the honest signal at planning time.
"""
from __future__ import annotations

from ..graphs.model import AgentGraph
from .executors import ExecutorNetwork

ROLE_PROMPT_TOKENS = 200.0
TOKENS_PER_KB = 250.0  # ~4 chars/token, ~1000 chars/KB


def task_tokens(graph: AgentGraph, task_name: str) -> tuple[float, float]:
    """(input_tokens, output_tokens) for one task."""
    task = graph.tasks[task_name]
    tokens_in = ROLE_PROMPT_TOKENS + sum(
        e.payload_kb * TOKENS_PER_KB for e in graph.in_edges(task_name)
    )
    return tokens_in, task.output_tokens


def assignment_cost_usd(
    graph: AgentGraph,
    assignment: dict[str, str],
    network: ExecutorNetwork,
) -> float:
    """Total $ cost of running ``graph`` under ``assignment``."""
    total = 0.0
    for task in graph:
        if task.kind != "llm":
            continue
        executor = network.by_name(assignment[task.name])
        tokens_in, tokens_out = task_tokens(graph, task.name)
        total += (
            tokens_in * executor.usd_per_mtok_in
            + tokens_out * executor.usd_per_mtok_out
        ) / 1e6
    return total
