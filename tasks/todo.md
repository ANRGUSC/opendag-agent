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

## P1 — full E1 simulation campaign (next)

- [ ] Topology sweep × network configs × all SAGA schedulers → F4/F5(sim)/T2

## Later phases

P2 (profiler, lab cluster, ODAG compiler, live Scenario A), P3 (full E2 + security
layer E3, incl. privacy-preserving partitioned data/model transfer demo over
Wayline's data plane), P4 (optional DO rerun, docs, DAGBench PR, v0.1.0 + Zenodo),
Final (figure polish + results memo). See the handoff doc.
