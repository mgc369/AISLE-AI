# AISLE.AI — Warehouse Intelligence Lab

**AI Fundamentals · Final Project · Functional Python + Web Application**

> An autonomous warehouse robot must visit multiple pick-up points and return home. AISLE.AI integrates **A\* Search**, **Hill Climbing**, and **Markov Decision Process (MDP) Value Iteration** into one operational system. It plans a short mission and then acts reliably when motion is uncertain.

## Quick start — Windows, macOS, Linux

**Prerequisite:** Python **3.10+**. No pip installation, web account, database, API key, or paid service is needed.

```bash
cd AISLE_AI_Final_Project
python run.py
```

Open **http://localhost:8000** in any modern browser. On Windows, you can also double-click `START_WINDOWS.bat` (if Python is installed).

If `python` isn't recognized on Windows, try `py -3 run.py`. If port 8000 is busy, use `python run.py --port 8001`, then open `http://localhost:8001`.

**Important:** Open the address through the running Python server. Opening `web/index.html` directly will *not* connect to the AI engine.

## Interactive demonstration

1. Select **Distribution center**, **High disruption**, or **Narrow aisles**. Each includes a working warehouse, depot, five pick-up points, shelves, and risk zones.
2. Press **RUN AI ANALYSIS**. It computes A\* paths, Hill Climbing order, and MDP policies; the right panel shows quantitative results from **60 reproducible simulation trials**.
3. Under **ROUTE PLAYBACK**, compare four modes: *nearest-neighbor A\**, optimized A\* + Hill Climbing, stochastic A\* controller, and stochastic MDP*. Press ▶ and change speed or move the scrubber.
4. Click **Policy field** to inspect action arrows from Value Iteration toward the first target.
5. Edit the map using **Pick point**, **Shelf**, **Risk zone**, or **Erase**. Press **RUN AI ANALYSIS** to recompute all results. At least two pick locations are required, up to eight.
6. Press **Export** to download the complete model output and trial comparison as JSON.

## Why these algorithms belong together

```text
              WAREHOUSE / PICK-UP LOCATIONS / DEPOT
                                 │
            A* SEARCH: shortest paths between points
                                 │
             PAIRWISE SHORTEST-PATH DISTANCE MATRIX
                                 │
         HILL CLIMBING: improve the order of all visits
                                 │
                 MISSION TARGET ORDER, RETURN HOME
                                 │
       MDP VALUE ITERATION: choose actions per next target
                                 │
             STOCHASTIC ROBOT SIMULATION + METRICS
```

They are **not** three unrelated examples: A\* computes travel costs that Hill Climbing needs. Hill Climbing produces the mission order that the MDP executes, one target at a time. A stochastic rollout measures whether the robot completes the whole mission and how much hazardous floor it encounters.

### A\* Search — informed graph search

- Four cardinal moves; shelves block movement; each planned move has unit cost.
- Evaluation: `f(n) = g(n) + h(n)` where `g` is path cost and `h` is Manhattan distance.
- Manhattan distance is admissible and consistent for cardinal unit-cost moves, so the returned path is shortest in this graph.
- Output: shortest-path distances between the depot and each pick-up point and between each pair of pick-up points; reference route geometry.

### Multi-start Hill Climbing — local optimization

- Initial tour: nearest-neighbor ordering by A\* distance.
- Neighborhood: swap any two picks, or reverse any contiguous subsequence (2-opt-style).
- Choose the **best strictly improving** neighbor, repeat until no improvement; use reproducible alternate restarts.
- Objective: minimize total planned steps `d(home,p1) + Σd(pi,pi+1) + d(pn,home)`.
- This is a heuristic: it **does not guarantee** the globally shortest multi-stop tour. A\* optimality applies to individual segments, not to the entire ordering.

### MDP Value Iteration — stochastic sequential decision-making

- State: robot's grid cell; action: N/E/S/W; goal state: the next pick-up or home.
- Normal floor: probability **0.88** moves as commanded, **0.06** slips left, **0.06** slips right.
- Risk floor: **0.60** moves as commanded, **0.20** slips left, **0.20** slips right.
- Invalid moves become **stay-in-place**. Duplicate outcomes are merged; probabilities sum to 1.
- Reward per action: `-1` plus **+42 on entering the goal**, **−6 on entering risk floor**, and **−0.5 when movement is blocked**. Discount `γ = 0.97`.
- Bellman optimality update: `V(s) = max_a Σ_s' P(s'|s,a) [R(s,a,s') + γV(s')]`.
- Synchronous value iteration stops at Bellman residual `< 1e−4` or 450 sweeps. A greedy policy is extracted from converged values.
- Recompute/prepare a separate MDP policy **for every target**. After a random deviation, the controller chooses a new action according to its current state; it does not blindly follow a pre-written path.
- **Dependable goal-reaching safeguard:** unconstrained discounted Value Iteration may circle or repeatedly bounce between cells instead of completing a distant mission. A stochastic policy may technically have a *positive-probability* escape path but still take far too long to leave a cycle. We therefore check each **intended-action policy graph** and replace actions that cannot reach their target under nominal motion with shortest-distance recovery actions. This ensures every target-connected state has a finite loop-free nominal path to the goal, while preserving risk-aware Value Iteration actions in already goal-reaching states. Random slips still occur, and finite-run success is never guaranteed. The interface reports the number of corrected policy cells; built-in presets need zero.

**Comparison fairness:** Both stochastic controllers operate on the *same Hill Climbing order* and *same transition model*. The comparison controller selects a shortest-path action at each step using an exact cached distance-to-go field (equivalent to replanning an optimal unit-cost A\* route). Only its action selection differs from MDP.

## Reproducible results (built-in scenarios)

Exactly 60 Monte Carlo trials per controller and scenario; deterministic seeds `2900 + 101 × trial_index`.

| Scenario | Nearest steps | Hill Climb steps | Steps saved | Mean risk entries: shortest | Mean risk entries: MDP | Mission success: MDP |
|:--|--:|--:|--:|--:|--:|--:|
| Distribution center | 70 | 62 | 8 (11.43%) | 0.32 | 0.07 | 100% |
| High disruption | 76 | 66 | 10 (13.16%) | 3.08 | 0.30 | 100% |
| Narrow aisles | 60 | 60 | 0 (0.00%) | 13.57 | 0.92 | 100% |

These are **synthetic simulation results**, not measurements from a physical warehouse. Results depend on the configured geometry, stochastic transition probabilities, reward weights, and fixed random seeds. A local-search run may improve some layouts but not others. The success rate is 100% for these scenarios and therefore does *not* establish a success-rate advantage for MDP.

Run any preset in the application and choose **Export** to save the full JSON results, including mean execution steps, slips, and both controllers' trial summaries.

## Project structure

```text
AISLE_AI_Final_Project/
├── run.py                   # HTTP server + API; Python standard library only
├── engine/
│   ├── algorithms.py        # A*, hill climbing, MDP, simulation and metrics
│   └── scenarios.py         # Three deterministic warehouse layouts
├── web/
│   ├── index.html           # Responsive interactive interface
│   ├── styles.css           # Design system, animations and mobile layout
│   └── app.js               # Canvas visualization, editor, playback, charts
├── tests/
│   ├── test_algorithms.py       # Algorithm and integration tests
│   ├── test_http.py             # Real HTTP endpoint tests
│   ├── test_regression_audit.py # Edge cases and regression tests
│   ├── test_web_client.js       # Frontend state regression tests
│   └── optional_browser_audit.py
├── START_WINDOWS.bat
├── requirements.txt
└── README.md
```

## Test the complete backend

```bash
python -m unittest discover -s tests -v
```

36 Python tests cover route optimality against breadth-first search (including 240 randomized source/target pairs), transition normalization, MDP convergence, Hill Climbing feasibility, two reproduced pathological missions (a serpentine map and a dense risky map with rare-slip oscillation), robust HTTP error handling, reproducible results, integration consistency, and API endpoints. An additional frontend regression test (including rapid scenario switching and stale-response suppression) can be run with `node tests/test_web_client.js` (requires Node.js; not needed to run the application).

### API

- `GET /api/presets` → warehouse presets.
- `POST /api/analyze` → JSON containing `width`, `height`, `start`, `blocked`, `hazards`, `tasks`. Returns planned routes, optimized order, MDP policy field, sample rollouts and 60-trial comparative summaries.
- `GET /` → graphical user interface.

## Technical scope and limitations

1. Synthetic 2D grid and single robot; no lidar, real telemetry, robotics hardware, collision avoidance between multiple robots, charging, or dynamic forklift detection.
2. Independent target-conditioned MDPs; the global pick ordering minimizes **deterministic** A\* step distance, not total expected stochastic mission cost. Recovery actions used to guarantee possible goal arrival in pathological layouts may differ from the unconstrained greedy Value Iteration policy.
3. The reward and slip probabilities are modeled assumptions and would need to be calibrated using real data.
4. MDP discounted finite-state model uses a fixed grid. Larger continuous environments need function approximation, hierarchical planning or online model updates.
5. Monte Carlo estimates are based on a finite sample; do not infer real-world safety or statistical significance.
