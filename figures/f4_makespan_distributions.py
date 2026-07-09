"""F4: normalized-makespan distributions across strategies.

For every problem instance (regime x graph), each strategy's makespan is
divided by the best makespan any strategy achieved on that instance, giving
a ratio >= 1 that is comparable across instances. Box plots per strategy,
sorted by median, colored by kind (classical / baseline / cost-aware).

Usage: python figures/f4_makespan_distributions.py [--csv figures/out/e1_campaign.csv]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

KIND_COLORS = {"classical": "#4878cf", "baseline": "#d1605e", "costaware": "#6acc65"}


def load_ratios(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = df[df["status"] == "ok"].copy()
    df["makespan_s"] = df["makespan_s"].astype(float)
    best = df.groupby(["regime", "graph"])["makespan_s"].transform("min")
    df["ratio"] = df["makespan_s"] / best
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=Path("figures/out/e1_campaign.csv"),
                        type=Path)
    parser.add_argument("--outdir", default=Path("figures/out"), type=Path)
    args = parser.parse_args()

    df = load_ratios(args.csv)
    order = (df.groupby("strategy")["ratio"].median()
             .sort_values(ascending=False).index.tolist())
    data = [df.loc[df["strategy"] == s, "ratio"].values for s in order]
    kinds = {s: df.loc[df["strategy"] == s, "kind"].iloc[0] for s in order}

    fig, ax = plt.subplots(figsize=(9, 0.32 * len(order) + 1.6))
    boxes = ax.boxplot(data, orientation="horizontal", patch_artist=True,
                       showfliers=True,
                       flierprops=dict(marker=".", markersize=3, alpha=0.5),
                       medianprops=dict(color="black"))
    for patch, s in zip(boxes["boxes"], order):
        patch.set_facecolor(KIND_COLORS[kinds[s]])
        patch.set_alpha(0.85)
    ax.set_yticks(range(1, len(order) + 1), order, fontsize=8)
    ax.set_xlabel("makespan / best makespan on the same instance (log scale)")
    ax.set_xscale("log")
    ax.grid(axis="x", alpha=0.3)
    n_inst = df.groupby(["regime", "graph"]).ngroups
    ax.set_title(
        f"Makespan ratio across {n_inst} instances "
        "(5 topology families x sizes x 3 network regimes)", fontsize=10)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c, alpha=0.85)
               for c in KIND_COLORS.values()]
    ax.legend(handles, ["SAGA classical", "naive baseline", "cost-aware (ours)"],
              loc="lower right", fontsize=8)
    fig.tight_layout()
    args.outdir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.outdir / f"f4_makespan_distributions.{ext}", dpi=170)
    plt.close(fig)
    print(f"wrote {args.outdir / 'f4_makespan_distributions.png'} (+pdf)")

    summary = (df.groupby(["kind", "strategy"])["ratio"]
               .agg(["median", "mean", "max", "count"]).round(3))
    summary.to_csv(args.outdir / "f4_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
