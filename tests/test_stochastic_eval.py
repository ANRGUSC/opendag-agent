import numpy as np
import pytest

from saga.schedulers.stochastic import MeanHeftScheduler

from opendag.graphs import ModelTier, debate, hierarchical_research
from opendag.presets import default_network
from opendag.schedule.stochastic_eval import (
    mc_makespans,
    order_map_from,
    stochastic_instance,
)

ZERO_SIGMA = {int(t): 1e-9 for t in ModelTier}


def test_zero_variance_replay_matches_prediction(network):
    """With ~zero variance the MC replay must reproduce the deterministic
    makespan of the schedule it replays — the correctness anchor for the
    whole evaluator."""
    g = hierarchical_research(k=6, verifiers=2)
    inst = stochastic_instance(g, network, tier_cost_sigma=ZERO_SIGMA,
                               api_speed_sigma=1e-9, local_speed_sigma=1e-9,
                               n=25, seed=3)
    scheduler = MeanHeftScheduler()
    schedule = scheduler.schedule(inst.network, inst.task_graph)
    samples = mc_makespans(order_map_from(schedule), g, network, inst)
    assert samples.std() / samples.mean() < 1e-6

    # Deterministic reference: same scheduler on the deterministic instance.
    from opendag.schedule import to_saga_task_graph
    from saga.schedulers import HeftScheduler
    predicted = HeftScheduler().schedule(network.to_saga(),
                                         to_saga_task_graph(g)).makespan
    assert samples.mean() == pytest.approx(predicted, rel=1e-3)


def test_paired_sampling_is_deterministic(network):
    g = hierarchical_research(k=6, verifiers=2)
    a = stochastic_instance(g, network, n=50, seed=7)
    b = stochastic_instance(g, network, n=50, seed=7)
    for name in a.cost_samples:
        assert np.array_equal(a.cost_samples[name], b.cost_samples[name])
    schedule = MeanHeftScheduler().schedule(a.network, a.task_graph)
    m1 = mc_makespans(order_map_from(schedule), g, network, a)
    m2 = mc_makespans(order_map_from(schedule), g, network, b)
    assert np.array_equal(m1, m2)


def test_replay_handles_dense_graphs_without_deadlock(network):
    g = debate(agents=4, rounds=3)
    inst = stochastic_instance(g, network, n=20, seed=1)
    schedule = MeanHeftScheduler().schedule(inst.network, inst.task_graph)
    samples = mc_makespans(order_map_from(schedule), g, network, inst)
    assert len(samples) == 20 and (samples > 0).all()
