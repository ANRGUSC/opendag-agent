# OpenDAG-Agent — task tracking

Plan of record: `OpenDAG-Agent-Demo-Plan.docx` (student handoff brief, in the parent
proposal folder). Phases P0–P4 + Final; definitions of done are in the doc.

## P0 — scaffold, agentic DAG model, SAGA bridge, LocalRunner (mock)

- [x] Repo scaffold: pyproject, LICENSE (MIT), .gitignore, CI workflow, directory tree
- [x] `opendag.graphs`: AgentTask/AgentEdge/AgentGraph + JSON round-trip
- [x] `opendag.graphs.topologies`: map_reduce, hierarchical_research, debate,
      pipeline_verifier, edge_sensing_fusion (parameterized)
- [x] `opendag.schedule`: Executor/ExecutorNetwork, AgentGraph→SAGA export,
      baseline schedulers (AllAPI, LocalFirst, RoundRobin, Random, GreedyCheapest)
      as SAGA `Scheduler` subclasses, tier/pin feasibility + repair wrapper
      (`ConstrainedScheduler`), USD cost model
- [x] `opendag.execute`: LocalRunner (async, mock LLM client, per-task records,
      run artifact JSON)
- [x] Tests green (`pytest` — 21 passed)
- [x] `experiments/e1_sim.py --quick` prints makespan/cost table, writes CSV,
      renders the Gantt pair (HEFT vs AllAPI), mock-executes HEFT (Δ ≈ 5%)
- [x] git init + initial commit
- [ ] Publish public repo under ANRGUSC with CI  ← needs PI action/approval

P0 result snapshot (edge_sensing_fusion, 3 sites, default network): HEFT
79.5 s / $10.29 vs AllAPI(sonnet) 101.9 s / $18.53 — faster AND cheaper;
LocalFirst $0.017 / 178 s anchors the cheap end of the Pareto frontier.
Note: with 2 Mbps uplinks HEFT ships raw data to parallel API nodes (makespan-
optimal, cost-blind); the P1 regime sweep + cost-aware λ objective covers this.

## P1 — full E1 simulation campaign

- [x] Network regimes (edge_heavy / hybrid / api_rich) + API lane parallelism
- [x] Cost-aware λ-sweep scheduler (`CostAwareScheduler`) + Pareto helpers
- [x] `experiments/e1_campaign.py`: 5 families × sizes × 3 regimes ×
      19 classical + 6 baselines + λ-sweep, every schedule validated
      (DPS excluded for pathological runtime; see development.md)
- [x] `experiments/e1b_stochastic.py`: SHEFT vs MeanHEFT, paired MC replay
      (planning sees cost uncertainty; world adds API speed volatility)
- [x] `experiments/ncsim_crosscheck.py`: SAGA vs ncsim discrete-event — 0.0% diff
- [x] F4 (makespan distributions), F5 (Pareto), T2 (ranking md+csv)
- [x] One command regenerates everything: `python experiments/run_p1.py`
- [x] Tests (28 passing), CI runs `run_p1 --quick`

## Later phases

P2 (profiler, lab cluster, ODAG compiler, live Scenario A), P3 (full E2 + security
layer E3, incl. privacy-preserving partitioned data/model transfer demo over
Wayline's data plane), P4 (optional DO rerun, docs, DAGBench PR, v0.1.0 + Zenodo),
Final (figure polish + results memo). See the handoff doc.
