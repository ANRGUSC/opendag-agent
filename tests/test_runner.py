import json

import pytest

from opendag.execute import LocalRunner, MockLLMClient
from opendag.graphs import hierarchical_research
from opendag.schedule import (
    ConstrainedScheduler,
    assignments_from_schedule,
    classical_schedulers,
    to_saga_task_graph,
)

EPS = 1.0  # virtual seconds of tolerance for asyncio timing jitter


@pytest.fixture
def run_result(network):
    g = hierarchical_research(k=4, verifiers=2)
    scheduler = ConstrainedScheduler(
        inner=classical_schedulers(["HEFT"])["HEFT"],
        feasible=network.feasibility_map(g),
    )
    schedule = scheduler.schedule(network.to_saga(), to_saga_task_graph(g))
    assignment = assignments_from_schedule(schedule)
    speedup = 5000.0
    runner = LocalRunner(g, network, assignment,
                         client=MockLLMClient(speedup=speedup),
                         speedup=speedup, strategy="HEFT")
    return g, runner.run()


def test_run_completes_all_tasks(run_result):
    g, result = run_result
    assert {r.name for r in result.records} == set(g.tasks)
    assert result.makespan_s > 0


def test_run_respects_dependencies(run_result):
    g, result = run_result
    by_name = {r.name: r for r in result.records}
    for e in g.edges:
        assert by_name[e.dst].start_s >= by_name[e.src].end_s - EPS, (
            f"{e.dst} started before {e.src} finished"
        )


def test_run_serializes_per_executor(run_result):
    _, result = run_result
    per_exec: dict[str, list] = {}
    for r in result.records:
        per_exec.setdefault(r.executor, []).append(r)
    for records in per_exec.values():
        records.sort(key=lambda r: r.start_s)
        for a, b in zip(records, records[1:]):
            assert b.start_s >= a.end_s - EPS


def test_run_accrues_api_cost(run_result):
    _, result = run_result
    # plan/synthesize are FRONTIER-tier: they must have landed on the API.
    assert result.total_usd > 0


def test_run_artifact_round_trips(tmp_path, run_result):
    _, result = run_result
    path = result.save(tmp_path / "runs" / "r.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == "opendag/run-v0"
    assert data["makespan_s"] == pytest.approx(result.makespan_s)
    assert len(data["records"]) == len(result.records)


def test_infeasible_assignment_rejected(network):
    g = hierarchical_research(k=4, verifiers=2)
    assignment = {name: "site0" for name in g.tasks}  # FRONTIER tasks on a 3B node
    with pytest.raises(ValueError, match="Infeasible"):
        LocalRunner(g, network, assignment)
