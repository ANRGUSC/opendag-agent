"""One command regenerates every P1 artifact (the P1 definition of done).

Runs, in order: the E1 campaign, the E1b stochastic experiment, the ncsim
cross-check, then the F4/F5/T2 figure scripts. All offline; no keys.

Usage: python experiments/run_p1.py [--quick]
Artifacts land in figures/out/.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(script: Path, *args: str) -> None:
    cmd = [sys.executable, str(script), *args]
    print(f"\n=== {' '.join(cmd[1:])} ===")
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    quick = ["--quick"] if args.quick else []

    run(ROOT / "experiments" / "e1_campaign.py", *quick)
    run(ROOT / "experiments" / "e1b_stochastic.py", *quick)
    run(ROOT / "experiments" / "ncsim_crosscheck.py", *quick)
    run(ROOT / "figures" / "f4_makespan_distributions.py")
    run(ROOT / "figures" / "f5_pareto.py")
    run(ROOT / "figures" / "t2_ranking.py")

    out = ROOT / "figures" / "out"
    print("\nP1 artifacts:")
    for p in sorted(out.iterdir()):
        print(f"  {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
