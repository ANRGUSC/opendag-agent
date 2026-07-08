"""E1 (P0 slice): schedule agentic DAGs on a heterogeneous executor network.

Compares SAGA's classical schedulers against the fixed-assignment baselines
today's agent frameworks effectively use, entirely in simulation (no cost,
no network, no keys). Writes a CSV, renders the naive-vs-HEFT Gantt pair,
and mock-executes one schedule with LocalRunner to sanity-check predicted
makespan against (simulated) execution.

Usage:
    python experiments/e1_sim.py --quick [--no-figures] [--outdir figures/out]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendag.execute import LocalRunner, MockLLMClient
from opendag.graphs import (
    debate,
    edge_sensing_fusion,
    hierarchical_research,
    map_reduce,
    pipeline_verifier,
)
from opendag.presets import api_node_names, default_network, price_map
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


def build_strategies(network, feasible):
    strategies = {}
    for name, inner in classical_schedulers(["HEFT", "CPoP", "MinMin"]).items():
        strategies[name] = ConstrainedScheduler(inner=inner, feasible=feasible)
    strategies["AllAPI(sonnet)"] = AllOnScheduler(target="sonnet", feasible=feasible)
    strategies["AllAPI(haiku)"] = AllOnScheduler(target="haiku", feasible=feasible)
    strategies["LocalFirst"] = LocalFirstScheduler(
        api_nodes=api_node_names(network), feasible=feasible)
    strategies["RoundRobin"] = RoundRobinScheduler(feasible=feasible)
    strategies["Random(42)"] = RandomScheduler(seed=42, feasible=feasible)
    strategies["GreedyCheapest"] = GreedyCheapestScheduler(
        prices=price_map(network), feasible=feasible)
    return strategies


def graphs_for(quick: bool):
    graphs = [
        edge_sensing_fusion(sites=3, site_mb=8.0),
        hierarchical_research(k=8, verifiers=2),
        map_reduce(k=8),
    ]
    if not quick:
        graphs += [
            edge_sensing_fusion(sites=6, site_mb=8.0),
            hierarchical_research(k=16, verifiers=3),
            map_reduce(k=16),
            debate(agents=4, rounds=3),
            pipeline_verifier(stages=6),
        ]
    return graphs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="small graph set")
    parser.add_argument("--no-figures", action="store_true", help="skip PNGs")
    parser.add_argument("--outdir", default="figures/out", type=Path)
    args = parser.parse_args()

    network = default_network(sites=6 if not args.quick else 3)
    rows = []
    gantt_bars = {}

    for graph in graphs_for(args.quick):
        tg = to_saga_task_graph(graph)
        net = network.to_saga()
        feasible = network.feasibility_map(graph)
        for strategy_name, scheduler in build_strategies(network, feasible).items():
            schedule = scheduler.schedule(net, tg)
            validate_schedule(schedule, feasible=feasible)
            assignment = assignments_from_schedule(schedule)
            usd = assignment_cost_usd(graph, assignment, network)
            rows.append({
                "graph": graph.name,
                "tasks": len(graph),
                "strategy": strategy_name,
                "makespan_s": round(schedule.makespan, 2),
                "usd": round(usd, 4),
            })
            if graph.name.startswith("edge_sensing") and strategy_name in (
                    "HEFT", "AllAPI(sonnet)"):
                gantt_bars[strategy_name] = schedule

    # -- console table -------------------------------------------------------
    header = f"{'graph':<28} {'strategy':<16} {'makespan (s)':>12} {'cost ($)':>9}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['graph']:<28} {r['strategy']:<16} "
              f"{r['makespan_s']:>12,.1f} {r['usd']:>9.3f}")

    # -- CSV ------------------------------------------------------------------
    args.outdir.mkdir(parents=True, exist_ok=True)
    csv_path = args.outdir / "e1_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {csv_path} ({len(rows)} rows)")

    # -- Gantt pair (F3 preview) ----------------------------------------------
    if not args.no_figures and len(gantt_bars) == 2:
        from opendag.viz import bars_from_schedule, gantt_pair
        path = gantt_pair(
            bars_from_schedule(gantt_bars["AllAPI(sonnet)"]),
            "AllAPI baseline (every step on the frontier API)",
            bars_from_schedule(gantt_bars["HEFT"]),
            "HEFT via SAGA (placement-aware)",
            args.outdir / "gantt_edge_sensing_allapi_vs_heft.png",
            suptitle="edge_sensing_fusion: same workflow, same network",
        )
        print(f"wrote {path}")

    # -- mock execution sanity check ------------------------------------------
    graph = hierarchical_research(k=8, verifiers=2)
    feasible = network.feasibility_map(graph)
    scheduler = ConstrainedScheduler(
        inner=classical_schedulers(["HEFT"])["HEFT"], feasible=feasible)
    schedule = scheduler.schedule(network.to_saga(), to_saga_task_graph(graph))
    assignment = assignments_from_schedule(schedule)
    speedup = 200.0
    result = LocalRunner(graph, network, assignment,
                         client=MockLLMClient(speedup=speedup),
                         speedup=speedup, strategy="HEFT").run()
    run_path = result.save(Path("runs") / f"{graph.name}_heft_mock.json")
    delta = abs(result.makespan_s - schedule.makespan) / schedule.makespan * 100
    print(f"\nLocalRunner mock execution of {graph.name} under HEFT:")
    print(f"  predicted makespan {schedule.makespan:8.1f} s")
    print(f"  simulated makespan {result.makespan_s:8.1f} s   (delta {delta:.1f}%)")
    print(f"  mock run cost      {result.total_usd:8.4f} $  -> {run_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
