"""F5: cost vs. makespan Pareto view.

Panel A (aggregate): each strategy is a point at (mean makespan ratio,
mean cost ratio), ratios normalized per instance — makespan against the
best strategy on that instance, cost against the AllAPI(sonnet)
framework-default. The non-dominated frontier is drawn; fixed-assignment
baselines should sit strictly inside it.

Panel B (flagship instance): raw makespan vs. dollars for the largest
edge-sensing graph in the hybrid regime, with the cost-aware lambda sweep
connected to show the navigable knob.

Usage: python figures/f5_pareto.py [--csv figures/out/e1_campaign.csv]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from opendag.schedule import pareto_front  # noqa: E402

KIND_STYLE = {
    "classical": dict(color="#4878cf", marker="o", s=28),
    "baseline": dict(color="#d1605e", marker="X", s=60),
    "costaware": dict(color="#2e7d32", marker="D", s=34),
}


def load(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = df[df["status"] == "ok"].copy()
    df["makespan_s"] = df["makespan_s"].astype(float)
    df["usd"] = df["usd"].astype(float)
    grp = df.groupby(["regime", "graph"])
    df["ms_ratio"] = df["makespan_s"] / grp["makespan_s"].transform("min")
    ref = (df[df["strategy"] == "AllAPI(sonnet)"]
           .set_index(["regime", "graph"])["usd"].to_dict())

    def cost_ratio(r):
        denom = ref.get((r["regime"], r["graph"]))
        if denom is None or denom <= 1e-9:
            return float("nan")
        return r["usd"] / denom

    df["cost_ratio"] = df.apply(cost_ratio, axis=1)
    return df.dropna(subset=["cost_ratio"])


def panel_a(ax, df: pd.DataFrame) -> None:
    agg = (df.groupby(["kind", "strategy"])[["ms_ratio", "cost_ratio"]]
           .mean().reset_index())
    for kind, style in KIND_STYLE.items():
        sub = agg[agg["kind"] == kind]
        ax.scatter(sub["ms_ratio"], sub["cost_ratio"], label={
            "classical": "SAGA classical", "baseline": "naive baseline",
            "costaware": "cost-aware (ours)"}[kind], zorder=3, **style)
    points = list(zip(agg["ms_ratio"], agg["cost_ratio"]))
    front = pareto_front(points)
    fx = [points[i][0] for i in front]
    fy = [points[i][1] for i in front]
    ax.plot(fx, fy, "--", color="gray", lw=1, zorder=2, label="Pareto frontier")
    for _, row in agg.iterrows():
        label = row["strategy"]
        if (label in ("HEFT", "AllAPI(sonnet)", "AllAPI(haiku)", "LocalFirst",
                      "GreedyCheapest", "Random(42)", "RoundRobin")
                or label.startswith("CostAware")):
            short = label.replace("CostAware(lam=", "λ=").rstrip(")")
            ax.annotate(short, (row["ms_ratio"], row["cost_ratio"]),
                        textcoords="offset points", xytext=(4, 3), fontsize=6.5)
    ax.set_xlabel("mean makespan ratio (vs best per instance)")
    ax.set_ylabel("mean cost ratio (vs AllAPI(sonnet))")
    ax.set_yscale("log")
    ax.grid(alpha=0.3)
    ax.set_title("A. All instances, strategy means", fontsize=10)
    ax.legend(fontsize=7, loc="upper right")


def panel_b(ax, df: pd.DataFrame) -> None:
    inst = df[(df["regime"] == "hybrid")
              & (df["family"] == "edge_sensing_fusion")]
    if inst.empty:
        ax.set_visible(False)
        return
    graph = sorted(inst["graph"].unique())[-1]
    inst = inst[inst["graph"] == graph]
    for kind, style in KIND_STYLE.items():
        sub = inst[inst["kind"] == kind]
        ax.scatter(sub["makespan_s"], sub["usd"], zorder=3, **style)
    sweep = inst[inst["kind"] == "costaware"].copy()
    sweep["lam"] = sweep["lam"].astype(float)
    sweep = sweep.sort_values("lam")
    ax.plot(sweep["makespan_s"], sweep["usd"], "-", color="#2e7d32",
            lw=1.2, alpha=0.8, zorder=2)
    for _, row in sweep.iterrows():
        ax.annotate(f"λ={row['lam']:g}", (row["makespan_s"], row["usd"]),
                    textcoords="offset points", xytext=(4, 3), fontsize=6.5)
    for _, row in inst[inst["kind"] == "baseline"].iterrows():
        ax.annotate(row["strategy"], (row["makespan_s"], row["usd"]),
                    textcoords="offset points", xytext=(4, 3), fontsize=6.5)
    heft = inst[inst["strategy"] == "HEFT"]
    if not heft.empty:
        ax.annotate("HEFT", (heft["makespan_s"].iloc[0], heft["usd"].iloc[0]),
                    textcoords="offset points", xytext=(4, 3), fontsize=6.5)
    ax.set_xlabel("makespan (s)")
    ax.set_ylabel("cost ($)")
    ax.grid(alpha=0.3)
    ax.set_title(f"B. {graph}, hybrid regime (λ-sweep connected)", fontsize=10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=Path("figures/out/e1_campaign.csv"),
                        type=Path)
    parser.add_argument("--outdir", default=Path("figures/out"), type=Path)
    args = parser.parse_args()

    df = load(args.csv)
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, 4.4))
    panel_a(ax_a, df)
    panel_b(ax_b, df)
    fig.suptitle("Cost vs. makespan: scheduling turns a point into a frontier",
                 fontsize=11)
    fig.tight_layout()
    args.outdir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.outdir / f"f5_pareto.{ext}", dpi=170)
    plt.close(fig)
    print(f"wrote {args.outdir / 'f5_pareto.png'} (+pdf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
