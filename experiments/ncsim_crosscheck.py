"""Cross-check SAGA-predicted makespans against ncsim discrete-event runs.

Same instance, two independent engines: SAGA computes an analytic schedule
(insertion-based timing); ncsim simulates event by event with its own
HEFT-driven SagaScheduler adapter. Agreement validates the timing semantics
the whole campaign rests on. Pin-free graphs only (ncsim's adapter is
constraint-unaware, so predicted-side scheduling is plain HEFT too).

Usage: python experiments/ncsim_crosscheck.py [--quick] [--outdir figures/out]
Output: <outdir>/ncsim_crosscheck.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga.schedulers import HeftScheduler

from opendag.graphs import hierarchical_research, map_reduce, pipeline_verifier
from opendag.presets import default_network
from opendag.schedule import to_saga_task_graph


def ncsim_makespan(graph, network) -> float:
    from ncsim import DAG, Link, Network, Node, Simulation, Task
    from ncsim.models.dag import Edge, SingleDAGSource
    from ncsim.scheduler.saga_adapter import SagaScheduler

    nodes = {e.name: Node(id=e.name, compute_capacity=e.tokens_per_sec)
             for e in network.executors}
    links = {}
    names = [e.name for e in network.executors]
    for a in names:
        for b in names:
            if a != b:
                links[f"{a}->{b}"] = Link(
                    id=f"{a}->{b}", from_node=a, to_node=b,
                    bandwidth=network.bandwidth_kBps(a, b))
    ncnet = Network(nodes=nodes, links=links)

    tasks = {t.name: Task(id=t.name, compute_cost=max(t.output_tokens, 1e-6),
                          dag_id=graph.name)
             for t in graph}
    edges = [Edge(from_task=e.src, to_task=e.dst, data_size=e.payload_kb)
             for e in graph.edges]
    dag = DAG(id=graph.name, tasks=tasks, edges=edges)
    try:
        source = SingleDAGSource(dag)
    except TypeError:
        source = SingleDAGSource(dag=dag)

    sim = Simulation(network=ncnet, scheduler=SagaScheduler(algorithm="heft"),
                     dag_source=source, seed=42)
    result = sim.run()
    if result.status != "completed" and result.error_message:
        raise RuntimeError(f"ncsim: {result.status}: {result.error_message}")
    return float(result.makespan)


def run(quick: bool, outdir: Path) -> Path:
    graphs = [hierarchical_research(k=24, verifiers=2)]
    if not quick:
        graphs += [map_reduce(k=24), pipeline_verifier(stages=12),
                   map_reduce(k=96)]
    network = default_network(sites=3)
    net = network.to_saga()

    rows = []
    for graph in graphs:
        predicted = HeftScheduler().schedule(net, to_saga_task_graph(graph)).makespan
        row = {"graph": graph.name, "saga_predicted_s": round(predicted, 2),
               "ncsim_simulated_s": "", "diff_pct": "", "status": "ok"}
        try:
            simulated = ncsim_makespan(graph, network)
            row["ncsim_simulated_s"] = round(simulated, 2)
            row["diff_pct"] = round((simulated - predicted) / predicted * 100, 2)
        except Exception as exc:
            row["status"] = f"error: {type(exc).__name__}: {exc}"[:160]
        rows.append(row)
        print(f"{row['graph']:<32} saga {row['saga_predicted_s']:>9}  "
              f"ncsim {row['ncsim_simulated_s']:>9}  diff {row['diff_pct']}%"
              if row["status"] == "ok" else f"{row['graph']}: {row['status']}")

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "ncsim_crosscheck.csv"
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
