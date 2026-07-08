import pytest

from opendag.graphs import edge_sensing_fusion, hierarchical_research, map_reduce
from opendag.presets import api_node_names, price_map
from opendag.schedule import (
    AllOnScheduler,
    ConstrainedScheduler,
    GreedyCheapestScheduler,
    LocalFirstScheduler,
    RandomScheduler,
    RoundRobinScheduler,
    assignment_cost_usd,
    assignments_from_schedule,
    classical_schedulers,
    to_saga_task_graph,
    validate_schedule,
)

GRAPHS = [
    lambda: map_reduce(k=6),
    lambda: hierarchical_research(k=6, verifiers=2),
    lambda: edge_sensing_fusion(sites=3),
]


def _baselines(network, feasible):
    return {
        "AllAPI": AllOnScheduler(target="sonnet", feasible=feasible),
        "LocalFirst": LocalFirstScheduler(api_nodes=api_node_names(network),
                                          feasible=feasible),
        "RoundRobin": RoundRobinScheduler(feasible=feasible),
        "Random": RandomScheduler(seed=42, feasible=feasible),
        "GreedyCheapest": GreedyCheapestScheduler(prices=price_map(network),
                                                  feasible=feasible),
    }


def test_saga_export_preserves_structure(network):
    g = hierarchical_research(k=6, verifiers=2)
    tg = to_saga_task_graph(g)
    real = [t for t in tg.tasks if not t.name.startswith("__super_")]
    assert {t.name for t in real} == set(g.tasks)
    dep = tg.get_dependency("synthesize", "critique")
    assert dep.size == pytest.approx(4.0)
    assert tg.get_task("synthesize").cost == pytest.approx(900.0)


@pytest.mark.parametrize("make_graph", GRAPHS)
def test_baselines_produce_valid_feasible_schedules(network, make_graph):
    g = make_graph()
    tg = to_saga_task_graph(g)
    net = network.to_saga()
    feasible = network.feasibility_map(g)
    for name, scheduler in _baselines(network, feasible).items():
        schedule = scheduler.schedule(net, tg)
        validate_schedule(schedule, feasible=feasible)
        assignment = assignments_from_schedule(schedule)
        assert set(assignment) == set(g.tasks), name


@pytest.mark.parametrize("make_graph", GRAPHS)
def test_classical_schedulers_wrapped_are_feasible(network, make_graph):
    g = make_graph()
    tg = to_saga_task_graph(g)
    net = network.to_saga()
    feasible = network.feasibility_map(g)
    for name, inner in classical_schedulers(["HEFT", "CPoP", "MinMin"]).items():
        wrapped = ConstrainedScheduler(inner=inner, feasible=feasible)
        schedule = wrapped.schedule(net, tg)
        validate_schedule(schedule, feasible=feasible)
        assert wrapped.name == inner.name


def test_allapi_pins_respected_and_rest_on_target(network):
    g = edge_sensing_fusion(sites=3)
    feasible = network.feasibility_map(g)
    schedule = AllOnScheduler(target="sonnet", feasible=feasible).schedule(
        network.to_saga(), to_saga_task_graph(g)
    )
    assignment = assignments_from_schedule(schedule)
    for s in range(3):
        assert assignment[f"site{s}.ingest"] == f"site{s}"
    unpinned = [n for n, t in g.tasks.items() if t.pinned_executor is None]
    assert all(assignment[n] == "sonnet" for n in unpinned)


def test_heft_beats_allapi_on_makespan_and_cost_for_edge_sensing(network):
    """The core P0 sanity check: with heavy site-local data, placement-aware
    scheduling beats ship-everything-to-the-API on both axes."""
    g = edge_sensing_fusion(sites=3)
    tg, net = to_saga_task_graph(g), network.to_saga()
    feasible = network.feasibility_map(g)

    heft = ConstrainedScheduler(
        inner=classical_schedulers(["HEFT"])["HEFT"], feasible=feasible
    ).schedule(net, tg)
    allapi = AllOnScheduler(target="sonnet", feasible=feasible).schedule(net, tg)

    heft_cost = assignment_cost_usd(g, assignments_from_schedule(heft), network)
    allapi_cost = assignment_cost_usd(g, assignments_from_schedule(allapi), network)

    assert heft.makespan < allapi.makespan
    assert heft_cost < allapi_cost


def test_cost_model_charges_api_input_payloads(network):
    g = edge_sensing_fusion(sites=1, site_mb=4.0)
    local = {name: ("site0" if t.min_tier.value <= 1 else
                    "mid" if t.min_tier.value == 2 else "sonnet")
             for name, t in g.tasks.items()}
    shipped = dict(local)
    shipped["site0.extract"] = "sonnet"  # ship 4 MB of raw logs to the API
    assert (assignment_cost_usd(g, shipped, network)
            > assignment_cost_usd(g, local, network) + 1.0)
