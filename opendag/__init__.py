"""OpenDAG-Agent: plan, schedule, execute, and audit multi-LLM-agent
workflows as task graphs across heterogeneous edge, cloud, and hosted-API
executors. SAGA plans, Wayline executes.

Built on the ANRG open-source family: SAGA (schedulers), dagprofiler
(profiling standard), Wayline (k3s ODAG runtime), DAGBench (benchmarks),
ncsim (simulation).
"""
from .graphs import AgentEdge, AgentGraph, AgentTask, ModelTier
from .schedule import Executor, ExecutorNetwork

__version__ = "0.0.1"

__all__ = [
    "AgentEdge",
    "AgentGraph",
    "AgentTask",
    "ModelTier",
    "Executor",
    "ExecutorNetwork",
    "__version__",
]
