"""Agentic DAG model, JSON format, and canonical topology generators."""
from .model import AgentEdge, AgentGraph, AgentTask, ModelTier
from .topologies import (
    ALL_TOPOLOGIES,
    debate,
    edge_sensing_fusion,
    hierarchical_research,
    map_reduce,
    pipeline_verifier,
)

__all__ = [
    "AgentEdge",
    "AgentGraph",
    "AgentTask",
    "ModelTier",
    "ALL_TOPOLOGIES",
    "debate",
    "edge_sensing_fusion",
    "hierarchical_research",
    "map_reduce",
    "pipeline_verifier",
]
