"""ConstrainedScheduler must deliver feasible AND complete schedules even
when the inner scheduler misbehaves (drops tasks, duplicates onto forbidden
nodes) — observed in the wild with SAGA's HBMCT on pinned graphs."""
from saga import Schedule, ScheduledTask, Scheduler

from opendag.graphs import edge_sensing_fusion
from opendag.presets import regime_network
from opendag.schedule import (
    ConstrainedScheduler,
    assignments_from_schedule,
    classical_schedulers,
    to_saga_task_graph,
    validate_schedule,
)


class DroppyScheduler(Scheduler):
    """Schedules everything on the fastest node — except pinned ingest
    tasks, which it silently drops (mimicking HBMCT's failure mode)."""

    def schedule(self, network, task_graph):
        schedule = Schedule(task_graph, network)
        fastest = max(network.nodes, key=lambda n: n.speed)
        node_free = 0.0
        for task in task_graph.topological_sort():
            if task.name.endswith(".ingest"):
                continue
            try:
                start = schedule.get_earliest_start_time(
                    task.name, fastest.name, append_only=True)
            except ValueError:
                start = 0.0  # parent dropped
            start = max(start, node_free)
            end = start + task.cost / fastest.speed
            schedule.add_task(ScheduledTask(
                node=fastest.name, name=task.name, start=start, end=end))
            node_free = end
        return schedule


def test_wrapper_completes_dropped_tasks():
    g = edge_sensing_fusion(sites=3)
    network = regime_network("hybrid", sites=3)
    feasible = network.feasibility_map(g)
    wrapped = ConstrainedScheduler(inner=DroppyScheduler(), feasible=feasible)
    schedule = wrapped.schedule(network.to_saga(), to_saga_task_graph(g))
    validate_schedule(schedule, feasible=feasible)
    assignment = assignments_from_schedule(schedule)
    for s in range(3):
        assert assignment[f"site{s}.ingest"] == f"site{s}"


def test_wrapper_fixes_hbmct_on_pinned_graph():
    """The real-world case from the E1 campaign."""
    g = edge_sensing_fusion(sites=4)
    network = regime_network("api_rich", sites=6)
    feasible = network.feasibility_map(g)
    wrapped = ConstrainedScheduler(
        inner=classical_schedulers(["HBMCT"])["HBMCT"], feasible=feasible)
    schedule = wrapped.schedule(network.to_saga(), to_saga_task_graph(g))
    validate_schedule(schedule, feasible=feasible)
