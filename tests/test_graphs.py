import pytest

from opendag.graphs import (
    ALL_TOPOLOGIES,
    AgentGraph,
    AgentTask,
    ModelTier,
    edge_sensing_fusion,
    hierarchical_research,
)


def test_all_topologies_validate():
    for name, gen in ALL_TOPOLOGIES.items():
        g = gen()
        g.validate()
        assert len(g) > 3, name
        assert g.sources() and g.sinks(), name


def test_topology_shapes():
    g = hierarchical_research(k=8, verifiers=2)
    # plan + 8 analyses + 2 verifiers + synthesize + critique
    assert len(g) == 13
    assert g.parents("synthesize") == sorted(["verify0", "verify1"]) or set(
        g.parents("synthesize")
    ) == {"verify0", "verify1"}

    g = edge_sensing_fusion(sites=3)
    assert {t.min_tier for t in g}.issuperset({ModelTier.ANY, ModelTier.FRONTIER})
    assert g.tasks["site0.ingest"].pinned_executor == "site0"
    ingest_edge = next(e for e in g.edges if e.src == "site0.ingest")
    assert ingest_edge.payload_kb > 1000  # raw data is heavy


def test_json_round_trip(tmp_path):
    g = edge_sensing_fusion(sites=2, site_mb=4.0)
    path = tmp_path / "g.json"
    g.to_json(path)
    g2 = AgentGraph.from_json(path)
    assert g2.to_dict() == g.to_dict()
    assert g2.tasks["site1.ingest"].pinned_executor == "site1"
    assert g2.tasks["synthesize"].min_tier is ModelTier.FRONTIER


def test_cycle_detection():
    g = AgentGraph("cyclic")
    g.add_task(AgentTask("a"))
    g.add_task(AgentTask("b"))
    g.add_edge("a", "b")
    g.add_edge("b", "a")
    with pytest.raises(ValueError, match="cycle"):
        g.topological_order()


def test_duplicate_and_unknown_edges_rejected():
    g = AgentGraph("g")
    g.add_task(AgentTask("a"))
    g.add_task(AgentTask("b"))
    g.add_edge("a", "b")
    with pytest.raises(ValueError):
        g.add_edge("a", "b")
    with pytest.raises(ValueError):
        g.add_edge("a", "missing")
