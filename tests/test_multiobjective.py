import pytest

from opendag.graphs import ModelTier, hierarchical_research
from opendag.presets import regime_network
from opendag.schedule import (
    CostAwareScheduler,
    assignment_cost_usd,
    assignments_from_schedule,
    pareto_front,
    per_task_usd_map,
    to_saga_task_graph,
    validate_schedule,
)


def test_lambda_sweep_trades_cost_for_makespan():
    g = hierarchical_research(k=6, verifiers=2)
    network = regime_network("hybrid", sites=3)
    feasible = network.feasibility_map(g)
    tg, net = to_saga_task_graph(g), network.to_saga()
    usd_map = per_task_usd_map(g, network)

    results = {}
    for lam in (0.0, 1800.0):
        schedule = CostAwareScheduler(lam=lam, usd=usd_map,
                                      feasible=feasible).schedule(net, tg)
        validate_schedule(schedule, feasible=feasible)
        assignment = assignments_from_schedule(schedule)
        results[lam] = (schedule.makespan,
                        assignment_cost_usd(g, assignment, network))

    # Strong cost aversion must not cost more, and pure EFT must not be slower.
    assert results[1800.0][1] <= results[0.0][1]
    assert results[0.0][0] <= results[1800.0][0]
    # And the knob actually moves something on this instance.
    assert results[1800.0][1] < results[0.0][1]


def test_per_task_usd_map_semantics():
    g = hierarchical_research(k=4, verifiers=2)
    network = regime_network("hybrid", sites=3)
    usd = per_task_usd_map(g, network)
    assert usd["synthesize"]["sonnet"] > 0        # frontier llm on paid API
    assert usd["synthesize"]["site0"] == 0.0      # local is free in P0/P1
    assert all(v == 0.0 for v in usd["plan"].values()) is False


def test_pareto_front_toy():
    points = [(1.0, 5.0), (2.0, 3.0), (3.0, 4.0), (4.0, 1.0), (5.0, 2.0)]
    assert pareto_front(points) == [0, 1, 3]


def test_regime_networks_shape():
    for regime, haiku_lanes, sonnet_lanes in (("edge_heavy", 1, 1),
                                              ("hybrid", 2, 1),
                                              ("api_rich", 4, 2)):
        network = regime_network(regime, sites=6)
        names = [e.name for e in network.executors]
        assert names.count("haiku") == 1
        assert sum(1 for n in names if n.startswith("haiku")) == haiku_lanes
        assert sum(1 for n in names if n.startswith("sonnet")) == sonnet_lanes
        # frontier tasks feasible on every sonnet lane
        g = hierarchical_research(k=4, verifiers=2)
        feas = network.feasibility_map(g)
        for lane in (n for n in names if n.startswith("sonnet")):
            assert lane in feas["synthesize"]
    with pytest.raises(ValueError):
        regime_network("nope")
