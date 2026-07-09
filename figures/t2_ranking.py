"""T2: scheduler ranking table (markdown + CSV).

Per topology family: mean makespan ratio per strategy, top-3 classical
schedulers, and the gap to the naive baselines. If the E1b stochastic CSV
exists, appends the SHEFT-vs-MeanHEFT robustness comparison.

Usage: python figures/t2_ranking.py [--csv figures/out/e1_campaign.csv]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=Path("figures/out/e1_campaign.csv"),
                        type=Path)
    parser.add_argument("--e1b", default=Path("figures/out/e1b_stochastic.csv"),
                        type=Path)
    parser.add_argument("--outdir", default=Path("figures/out"), type=Path)
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    df = df[df["status"] == "ok"].copy()
    df["makespan_s"] = df["makespan_s"].astype(float)
    df["ratio"] = (df["makespan_s"]
                   / df.groupby(["regime", "graph"])["makespan_s"].transform("min"))

    mean_ratio = (df.groupby(["family", "kind", "strategy"])["ratio"]
                  .mean().reset_index())
    rows = []
    for family, sub in mean_ratio.groupby("family"):
        classical = sub[sub["kind"] == "classical"].sort_values("ratio")
        baselines = sub[sub["kind"] == "baseline"].sort_values("ratio")
        top3 = ", ".join(f"{r.strategy} ({r.ratio:.2f})"
                         for r in classical.head(3).itertuples())
        heft = classical[classical["strategy"] == "HEFT"]["ratio"]
        allapi = baselines[baselines["strategy"] == "AllAPI(sonnet)"]["ratio"]
        best_base = baselines.iloc[0]
        rows.append({
            "family": family,
            "top-3 classical (mean ratio)": top3,
            "HEFT": round(float(heft.iloc[0]), 2) if not heft.empty else "",
            "AllAPI(sonnet)": (round(float(allapi.iloc[0]), 2)
                               if not allapi.empty else ""),
            "best baseline": f"{best_base.strategy} ({best_base.ratio:.2f})",
        })
    table = pd.DataFrame(rows)

    args.outdir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.outdir / "t2_ranking.csv", index=False)

    lines = ["# T2 — scheduler ranking by topology family",
             "",
             "Mean makespan ratio (1.00 = best strategy on every instance of "
             "that family; lower is better).",
             "",
             table.to_markdown(index=False)]

    if args.e1b.exists():
        e1b = pd.read_csv(args.e1b)
        lines += ["", "## Robustness under LLM latency variance (E1b)", "",
                  "Paired Monte-Carlo evaluation of SHEFT (mean+std "
                  "determinization) vs. MeanHEFT (means only); same sampled "
                  "realizations for both. Lower is better.", "",
                  e1b.to_markdown(index=False)]
    else:
        lines += ["", "(E1b stochastic results not found — run "
                  "experiments/e1b_stochastic.py.)"]

    md_path = args.outdir / "t2_ranking.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {md_path} and t2_ranking.csv")
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
