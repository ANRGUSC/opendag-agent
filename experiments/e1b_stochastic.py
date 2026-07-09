"""E1b: SHEFT vs. MeanHEFT under LLM latency variance.

Builds stochastic instances (lognormal task output lengths; volatile API
throughput, stable local throughput), schedules with SAGA's SHEFT
(mean+std determinization) and MeanHEFT (means only), then evaluates both
by paired Monte-Carlo replay — the same sampled realization is applied to
both policies, so differences are policy, not luck.

Usage: python experiments/e1b_stochastic.py [--quick] [--outdir figures/out]
Output: <outdir>/e1b_stochastic.csv (one row per instance)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga.schedulers.stochastic import MeanHeftScheduler, SheftScheduler

from opendag.graphs import hierarchical_research, map_reduce, pipeline_verifier
from opendag.presets import default_network
from opendag.schedule.stochastic_eval import (
    mc_makespans,
    order_map_from,
    stochastic_instance,
)


def run(quick: bool, outdir: Path) -> Path:
    graphs = [hierarchical_research(k=24, verifiers=2)]
    if not quick:
        graphs += [map_reduce(k=24), pipeline_verifier(stages=12),
                   hierarchical_research(k=48, verifiers=3)]
    network = default_network(sites=3, haiku_lanes=2, sonnet_lanes=1)
    n = 150 if quick else 400

    rows = []
    for seed, graph in enumerate(graphs):
        inst = stochastic_instance(graph, network, n=n, seed=seed)
        policies = {
            "SHEFT": SheftScheduler(),
            "MeanHEFT": MeanHeftScheduler(),
        }
        stats = {}
        for name, scheduler in policies.items():
            schedule = scheduler.schedule(inst.network, inst.task_graph)
            samples = mc_makespans(order_map_from(schedule), graph, network, inst)
            stats[name] = samples
        sheft, mean_heft = stats["SHEFT"], stats["MeanHEFT"]
        p95_gain = (np.percentile(mean_heft, 95) - np.percentile(sheft, 95)) \
            / np.percentile(mean_heft, 95) * 100
        rows.append({
            "graph": graph.name,
            "MC samples": n,
            "SHEFT mean (s)": round(float(sheft.mean()), 1),
            "MeanHEFT mean (s)": round(float(mean_heft.mean()), 1),
            "SHEFT p95 (s)": round(float(np.percentile(sheft, 95)), 1),
            "MeanHEFT p95 (s)": round(float(np.percentile(mean_heft, 95)), 1),
            "p95 gain of SHEFT (%)": round(float(p95_gain), 1),
        })
        print(f"{graph.name:<32} SHEFT p95 {rows[-1]['SHEFT p95 (s)']:>8}  "
              f"MeanHEFT p95 {rows[-1]['MeanHEFT p95 (s)']:>8}  "
              f"gain {rows[-1]['p95 gain of SHEFT (%)']:>5}%")

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "e1b_stochastic.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--outdir", default=Path("figures/out"), type=Path)
    args = parser.parse_args()
    run(args.quick, args.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
