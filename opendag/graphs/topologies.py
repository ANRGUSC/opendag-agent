"""Parameterized generators for the five canonical agentic DAG topologies.

Every generator returns a validated :class:`AgentGraph`. Default token and
payload numbers are plausible mid-range values; all are overridable so the
same topologies drive both the simulation campaign (E1) and live runs (E2).
"""
from __future__ import annotations

from .model import AgentEdge, AgentGraph, AgentTask, ModelTier


def map_reduce(k: int = 8, chunk_kb: float = 64.0, name: str | None = None) -> AgentGraph:
    """Map-reduce summarization: split -> k parallel maps -> reduce."""
    g = AgentGraph(name or f"map_reduce_k{k}")
    g.add_task(AgentTask("split", kind="tool", output_tokens=1.0,
                         role="Split the corpus into chunks."))
    g.add_task(AgentTask("reduce", min_tier=ModelTier.FRONTIER, output_tokens=800.0,
                         role="Synthesize the chunk summaries into one summary."))
    for i in range(k):
        g.add_task(AgentTask(f"map{i}", min_tier=ModelTier.SMALL, output_tokens=300.0,
                             role="Summarize this chunk faithfully."))
        g.add_edge("split", f"map{i}", payload_kb=chunk_kb)
        g.add_edge(f"map{i}", "reduce", payload_kb=1.5)
    g.validate()
    return g


def hierarchical_research(k: int = 8, verifiers: int = 2, name: str | None = None) -> AgentGraph:
    """Plan -> k parallel analyses -> cross-verification -> synthesis -> critique."""
    g = AgentGraph(name or f"hierarchical_research_k{k}v{verifiers}")
    g.add_task(AgentTask("plan", min_tier=ModelTier.FRONTIER, output_tokens=500.0,
                         role="Decompose the research question into sub-questions."))
    g.add_task(AgentTask("synthesize", min_tier=ModelTier.FRONTIER, output_tokens=900.0,
                         role="Write the report from verified findings."))
    g.add_task(AgentTask("critique", min_tier=ModelTier.MEDIUM, output_tokens=400.0,
                         role="Critique the report for gaps and unsupported claims."))
    for j in range(verifiers):
        g.add_task(AgentTask(f"verify{j}", min_tier=ModelTier.MEDIUM, output_tokens=300.0,
                             role="Cross-check the analyses against each other."))
        g.add_edge(f"verify{j}", "synthesize", payload_kb=2.0)
    for i in range(k):
        g.add_task(AgentTask(f"analyze{i}", min_tier=ModelTier.SMALL, output_tokens=400.0,
                             role="Analyze one document for the assigned sub-question."))
        g.add_edge("plan", f"analyze{i}", payload_kb=2.0)
        for j in range(verifiers):
            g.add_edge(f"analyze{i}", f"verify{j}", payload_kb=1.6)
    g.add_edge("synthesize", "critique", payload_kb=4.0)
    g.validate()
    return g


def debate(agents: int = 3, rounds: int = 2, name: str | None = None) -> AgentGraph:
    """Committee debate: each round every agent reads all previous positions;
    a frontier judge rules on the final round."""
    g = AgentGraph(name or f"debate_a{agents}r{rounds}")
    for i in range(agents):
        g.add_task(AgentTask(f"r0_agent{i}", min_tier=ModelTier.SMALL, output_tokens=300.0,
                             role="State your initial position with reasons."))
    for r in range(1, rounds + 1):
        for i in range(agents):
            g.add_task(AgentTask(f"r{r}_agent{i}", min_tier=ModelTier.SMALL,
                                 output_tokens=300.0,
                                 role="Rebut the other positions and refine yours."))
            for j in range(agents):
                g.add_edge(f"r{r-1}_agent{j}", f"r{r}_agent{i}", payload_kb=1.2)
    g.add_task(AgentTask("judge", min_tier=ModelTier.FRONTIER, output_tokens=500.0,
                         role="Weigh the final positions and issue a ruling."))
    for i in range(agents):
        g.add_edge(f"r{rounds}_agent{i}", "judge", payload_kb=1.2)
    g.validate()
    return g


def pipeline_verifier(stages: int = 4, name: str | None = None) -> AgentGraph:
    """Sequential draft -> check pairs, ending in a frontier polish step."""
    g = AgentGraph(name or f"pipeline_verifier_s{stages}")
    prev: str | None = None
    for s in range(stages):
        draft, check = f"draft{s}", f"check{s}"
        g.add_task(AgentTask(draft, min_tier=ModelTier.SMALL, output_tokens=400.0,
                             role="Produce the next revision of the artifact."))
        g.add_task(AgentTask(check, min_tier=ModelTier.MEDIUM, output_tokens=200.0,
                             role="Check the revision; list defects to fix."))
        if prev is not None:
            g.add_edge(prev, draft, payload_kb=3.0)
        g.add_edge(draft, check, payload_kb=3.0)
        prev = check
    g.add_task(AgentTask("polish", min_tier=ModelTier.FRONTIER, output_tokens=600.0,
                         role="Final pass: resolve remaining defects, polish style."))
    g.add_edge(prev, "polish", payload_kb=3.0)
    g.validate()
    return g


def edge_sensing_fusion(sites: int = 3, site_mb: float = 8.0,
                        name: str | None = None) -> AgentGraph:
    """Scenario A shape: per-site ingest (pinned; raw data lives there) ->
    local extract/summarize -> regional aggregate -> frontier synthesis ->
    verification against the extracts -> report.

    Only ``ingest`` is pinned. Extraction placement is the scheduler's choice:
    running it off-site is *allowed* but requires shipping ``site_mb`` of raw
    data across the ingest->extract edge, which is how data locality enters
    the schedule honestly rather than by fiat.
    """
    g = AgentGraph(name or f"edge_sensing_fusion_s{sites}")
    g.add_task(AgentTask("aggregate", min_tier=ModelTier.MEDIUM, output_tokens=500.0,
                         role="Fuse the site summaries into a regional picture."))
    g.add_task(AgentTask("synthesize", min_tier=ModelTier.FRONTIER, output_tokens=900.0,
                         role="Write the cross-site incident report."))
    g.add_task(AgentTask("verify", min_tier=ModelTier.MEDIUM, output_tokens=400.0,
                         role="Verify every report claim against the site extracts."))
    g.add_task(AgentTask("report", kind="aggregate", output_tokens=1.0,
                         role="Assemble the final signed report."))
    for s in range(sites):
        site = f"site{s}"
        g.add_task(AgentTask(f"{site}.ingest", kind="tool", output_tokens=1.0,
                             pinned_executor=site,
                             role="Read the local log/sensor archive."))
        g.add_task(AgentTask(f"{site}.extract", min_tier=ModelTier.ANY,
                             output_tokens=250.0,
                             role="Extract suspicious events from the raw logs."))
        g.add_task(AgentTask(f"{site}.summarize", min_tier=ModelTier.SMALL,
                             output_tokens=300.0,
                             role="Summarize the extracted events for this site."))
        g.add_edge(f"{site}.ingest", f"{site}.extract", payload_kb=site_mb * 1024.0)
        g.add_edge(f"{site}.extract", f"{site}.summarize", payload_kb=8.0)
        g.add_edge(f"{site}.summarize", "aggregate", payload_kb=2.0)
        g.add_edge(f"{site}.extract", "verify", payload_kb=4.0)
    g.add_edge("aggregate", "synthesize", payload_kb=4.0)
    g.add_edge("synthesize", "verify", payload_kb=3.0)
    g.add_edge("verify", "report", payload_kb=3.0)
    g.validate()
    return g


ALL_TOPOLOGIES = {
    "map_reduce": map_reduce,
    "hierarchical_research": hierarchical_research,
    "debate": debate,
    "pipeline_verifier": pipeline_verifier,
    "edge_sensing_fusion": edge_sensing_fusion,
}
