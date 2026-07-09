"""E1: the full simulation campaign.

Sweeps 5 topology families x sizes (10-100 tasks) x 3 network regimes
(edge_heavy / hybrid / api_rich) x all SAGA classical schedulers + naive
baselines + a cost-aware lambda sweep. Every schedule is validated
(precedence, overlap, tier/pin feasibility) before its makespan and dollar
cost are recorded. Entirely offline: no network, no keys, no cost.

Usage:
    python experiments/e1_campaign.py [--quick] [--outdir figures/out]
Output:
    <outdir>/e1_campaign.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendag.graphs import ALL_TOPOLOGIES
from opendag.presets import REGIMES, api_node_names, price_map, regime_network
from opendag.schedule import (
    DEFAULT_LAMBDAS,
    AllOnScheduler,
    ConstrainedScheduler,
    CostAwareScheduler,
    GreedyCheapestScheduler,
    LocalFirstScheduler,
    RandomScheduler,
    RoundRobinScheduler,
    assignment_cost_usd,
    assignments_from_schedule,
    classical_schedulers,
    per_task_usd_map,
    to_saga_task_graph,
    validate_schedule,
)

# DPS is excluded: it needs multiple minutes per ~90-task dense instance
# (every other scheduler stays under 0.3s there), which would dominate the
# campaign's runtime for one row of the ranking table. Noted in T2 coverage.
FULL_CLASSICAL = ["HEFT", "CPoP", "MinMin", "MaxMin", "ETF", "Sufferage",
                  "MCT", "MET", "OLB", "FastestNode", "Duplex", "WBA", "GDL",
                  "FCP", "FLB", "BIL", "HBMCT", "MSBC", "MST"]
QUICK_CLASSICAL = ["HEFT", "CPoP", "MinMin"]

FAMILY_SIZES = {
    "map_reduce": [dict(k=8), dict(k=24), dict(k=48), dict(k=96)],
    "hierarchical_research": [dict(k=8, verifiers=2), dict(k=24, verifiers=2),
                              dict(k=48, verifiers=3), dict(k=90, verifiers=3)],
    "debate": [dict(agents=3, rounds=2), dict(agents=4, rounds=4),
               dict(agents=6, rounds=6), dict(agents=8, rounds=10)],
    "pipeline_verifier": [dict(stages=4), dict(stages=12),
                          dict(stages=24), dict(stages=48)],
    "edge_sensing_fusion": [dict(sites=2), dict(sites=4), dict(sites=6)],
}


def instances(quick: bool):
    for family, sizes in FAMILY_SIZES.items():
        for params in (sizes[:1] if quick else sizes):
            yield family, params, ALL_TOPOLOGIES[family](**params)


def strategies(network, graph, feasible, quick: bool):
    """Yield (label, kind, lam, scheduler)."""
    names = QUICK_CLASSICAL if quick else FULL_CLASSICAL
    for name, inner in classical_schedulers(names).items():
        yield name, "classical", "", ConstrainedScheduler(inner=inner,
                                                          feasible=feasible)
    yield ("AllAPI(sonnet)", "baseline", "",
           AllOnScheduler(target="sonnet", feasible=feasible))
    yield ("AllAPI(haiku)", "baseline", "",
           AllOnScheduler(target="haiku", feasible=feasible))
    yield ("LocalFirst", "baseline", "",
           LocalFirstScheduler(api_nodes=api_node_names(network),
                               feasible=feasible))
    yield "RoundRobin", "baseline", "", RoundRobinScheduler(feasible=feasible)
    yield "Random(42)", "baseline", "", RandomScheduler(seed=42, feasible=feasible)
    yield ("GreedyCheapest", "baseline", "",
           GreedyCheapestScheduler(prices=price_map(network), feasible=feasible))
    usd = per_task_usd_map(graph, network)
    lambdas = (0.0, 60.0) if quick else DEFAULT_LAMBDAS
    for lam in lambdas:
        yield (f"CostAware(lam={lam:g})", "costaware", lam,
               CostAwareScheduler(lam=lam, usd=usd, feasible=feasible))


def run_campaign(quick: bool, outdir: Path) -> Path:
    rows = []
    regimes = ("hybrid",) if quick else REGIMES
    for regime in regimes:
        network = regime_network(regime, sites=6)
        net = network.to_saga()
        for family, params, graph in instances(quick):
            feasible = network.feasibility_map(graph)
            tg = to_saga_task_graph(graph)
            ok = failed = 0
            for label, kind, lam, scheduler in strategies(network, graph,
                                                          feasible, quick):
                row = {"regime": regime, "family": family, "graph": graph.name,
                       "tasks": len(graph), "strategy": label, "kind": kind,
                       "lam": lam, "makespan_s": "", "usd": "",
                       "wall_ms": "", "status": "ok", "error": ""}
                t0 = time.perf_counter()
                try:
                    schedule = scheduler.schedule(net, tg)
                    validate_schedule(schedule, feasible=feasible)
                    assignment = assignments_from_schedule(schedule)
                    row["makespan_s"] = round(schedule.makespan, 3)
                    row["usd"] = round(assignment_cost_usd(graph, assignment,
                                                           network), 5)
                    ok += 1
                except Exception as exc:  # record and continue: coverage matters
                    row["status"] = "error"
                    row["error"] = f"{type(exc).__name__}: {exc}"[:160]
                    failed += 1
                row["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                rows.append(row)
            print(f"[{regime}] {graph.name:<32} ok={ok:>2} err={failed}",
                  flush=True)

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "e1_campaign.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    n_err = sum(1 for r in rows if r["status"] != "ok")
    print(f"\nwrote {path} ({len(rows)} rows, {n_err} errors)")
    if n_err:
        errs = {}
        for r in rows:
            if r["status"] != "ok":
                errs.setdefault((r["strategy"], r["error"]), 0)
                errs[(r["strategy"], r["error"])] += 1
        for (strategy, err), count in sorted(errs.items()):
            print(f"  {count:>3}x {strategy}: {err}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--outdir", default="figures/out", type=Path)
    args = parser.parse_args()
    run_campaign(args.quick, args.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
