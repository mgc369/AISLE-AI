"""A*, multi-start steepest descent hill climbing, and stochastic MDP value iteration.

All three algorithms cooperate on one warehouse-picking mission:
A* supplies pairwise shortest-path distances, hill climbing chooses the
visit order, and value iteration determines risk-aware movement policies.
"""
from __future__ import annotations

from collections import deque, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import heapq
import itertools
import math
import random
from typing import Any

ACTIONS = ((0, -1, 'N'), (1, 0, 'E'), (0, 1, 'S'), (-1, 0, 'W'))
DELTA_BY_NAME = {name: (dx, dy) for dx, dy, name in ACTIONS}


class PlanningError(ValueError):
    """Invalid mission, unreachable task, or incompatible input."""


def point(raw: Any) -> tuple[int, int]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise PlanningError('Coordinates must be [x, y] pairs.')
    if any(isinstance(v, bool) or not isinstance(v, int) for v in raw):
        raise PlanningError('Coordinates must be integers.')
    return raw[0], raw[1]


@dataclass(frozen=True)
class Warehouse:
    width: int
    height: int
    start: tuple[int, int]
    blocked: frozenset[tuple[int, int]]
    hazards: frozenset[tuple[int, int]]
    tasks: tuple[tuple[int, int], ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'Warehouse':
        if not isinstance(payload, dict):
            raise PlanningError('Mission must be a JSON object.')
        width, height = payload.get('width'), payload.get('height')
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (width, height)):
            raise PlanningError('Grid dimensions must be integers.')
        if not 10 <= width <= 24 or not 8 <= height <= 18:
            raise PlanningError('Grid dimensions must be between 10–24 by 8–18.')
        start = point(payload.get('start'))
        blocked_raw = payload.get('blocked', [])
        hazards_raw = payload.get('hazards', [])
        tasks_raw = payload.get('tasks', [])
        if any(not isinstance(x, list) for x in (blocked_raw, hazards_raw, tasks_raw)):
            raise PlanningError('Blocked cells, hazards and tasks must be lists.')
        if len(blocked_raw) > width * height or len(hazards_raw) > width * height or len(tasks_raw) > 8:
            raise PlanningError('Too many elements in the submitted mission.')
        blocked = [point(p) for p in blocked_raw]
        hazards = [point(p) for p in hazards_raw]
        tasks = [point(p) for p in tasks_raw]
        if len(tasks) < 2:
            raise PlanningError('Add at least two pick locations to demonstrate route optimization.')
        if len(set(tasks)) != len(tasks):
            raise PlanningError('Pick locations must be distinct.')
        all_points = [start, *blocked, *hazards, *tasks]
        if any(not (0 <= x < width and 0 <= y < height) for x, y in all_points):
            raise PlanningError('One or more coordinates lie outside the grid.')
        obstacles = frozenset(blocked)
        if start in obstacles or any(task in obstacles for task in tasks):
            raise PlanningError('Depot and pick locations cannot be blocked.')
        if start in tasks:
            raise PlanningError('A pick location cannot overlap the depot.')
        if any(h in obstacles or h == start or h in tasks for h in hazards):
            raise PlanningError('Risk zones cannot overlap shelves, depot or pick locations.')
        return cls(width, height, start, obstacles, frozenset(hazards), tuple(tasks))

    def free(self, pos: tuple[int, int]) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height and pos not in self.blocked

    def neighbor(self, pos: tuple[int, int], action: str) -> tuple[int, int]:
        dx, dy = DELTA_BY_NAME[action]
        candidate = (pos[0] + dx, pos[1] + dy)
        return candidate if self.free(candidate) else pos

    @property
    def cells(self) -> tuple[tuple[int, int], ...]:
        return tuple((x, y) for y in range(self.height) for x in range(self.width)
                     if (x, y) not in self.blocked)


def a_star(world: Warehouse, start: tuple[int, int], goal: tuple[int, int]):
    """Optimal cardinal-step route using admissible & consistent Manhattan h."""
    if start == goal:
        return [start], 0
    frontier = [(abs(start[0]-goal[0]) + abs(start[1]-goal[1]), 0, start)]
    gscore = {start: 0}
    parent = {}
    expanded = 0
    while frontier:
        _, g, current = heapq.heappop(frontier)
        if g != gscore.get(current):
            continue
        expanded += 1
        if current == goal:
            path = [current]
            while current != start:
                current = parent[current]
                path.append(current)
            return list(reversed(path)), expanded
        for dx, dy, _ in ACTIONS:
            next_cell = (current[0] + dx, current[1] + dy)
            if not world.free(next_cell):
                continue
            new_g = g + 1
            if new_g < gscore.get(next_cell, math.inf):
                gscore[next_cell] = new_g
                parent[next_cell] = current
                h = abs(next_cell[0] - goal[0]) + abs(next_cell[1] - goal[1])
                heapq.heappush(frontier, (new_g + h, new_g, next_cell))
    raise PlanningError('At least one pick location cannot be reached from the depot.')


def concatenate_paths(paths):
    full = []
    for path in paths:
        full.extend(path if not full else path[1:])
    return full


def precompute_pairwise(world: Warehouse):
    nodes = (world.start,) + world.tasks
    pairs = {}
    total_expansions = 0
    for i, j in itertools.combinations(range(len(nodes)), 2):
        path, expanded = a_star(world, nodes[i], nodes[j])
        total_expansions += expanded
        pairs[i, j] = (len(path) - 1, path)
    return nodes, pairs, total_expansions


def pair_dist(pairs, i, j):
    if i == j:
        return 0
    return pairs[tuple(sorted((i, j)))][0]


def routed_path(nodes, pairs, order):
    visit_indices = [0, *order, 0]
    legs = []
    for left, right in zip(visit_indices, visit_indices[1:]):
        path = pairs[tuple(sorted((left, right)))][1]
        if left > right:
            path = list(reversed(path))
        legs.append(path)
    return concatenate_paths(legs), legs


def path_cost(pairs, order):
    seq = (0, *order, 0)
    return sum(pair_dist(pairs, i, j) for i, j in zip(seq, seq[1:]))


def hill_climbing(pairs, number_tasks):
    """Multi-start best-improvement hill climb over swap and 2-opt neighborhoods."""
    unvisited = set(range(1, number_tasks + 1))
    first = []
    current = 0
    while unvisited:
        nxt = min(unvisited, key=lambda k: (pair_dist(pairs, current, k), k))
        first.append(nxt)
        unvisited.remove(nxt)
        current = nxt
    initial = tuple(first)
    starts = [initial, tuple(reversed(initial))]
    # deterministic restarts add search depth without sacrificing reproducibility
    starts.extend(tuple(initial[i:] + initial[:i]) for i in range(1, number_tasks))
    starts.extend(tuple((k, *[i for i in initial if i != k])) for k in initial)
    checked, updates = 0, 0
    best_global, best_global_cost = initial, path_cost(pairs, initial)
    progress = [{'iteration': 0, 'steps': best_global_cost}]
    for start in dict.fromkeys(starts):
        current = start
        current_cost = path_cost(pairs, current)
        while True:
            winner, winning_cost = current, current_cost
            for i in range(number_tasks):
                for j in range(i + 1, number_tasks):
                    swap = list(current)
                    swap[i], swap[j] = swap[j], swap[i]
                    reverse = (*current[:i], *reversed(current[i:j+1]), *current[j+1:])
                    for candidate in (tuple(swap), tuple(reverse)):
                        checked += 1
                        cost = path_cost(pairs, candidate)
                        if cost < winning_cost:
                            winner, winning_cost = candidate, cost
            if winning_cost >= current_cost:
                break
            current, current_cost = winner, winning_cost
            updates += 1
            if current_cost < best_global_cost:
                best_global, best_global_cost = current, current_cost
                progress.append({'iteration': updates, 'steps': best_global_cost})
        if current_cost < best_global_cost:
            best_global, best_global_cost = current, current_cost
            progress.append({'iteration': updates, 'steps': best_global_cost})
    return {
        'nearest_order': list(initial),
        'optimized_order': list(best_global),
        'nearest_steps': path_cost(pairs, initial),
        'optimized_steps': best_global_cost,
        'neighbors_evaluated': checked,
        'improvements': updates,
        'progress': progress,
    }


def transition(world: Warehouse, state: tuple[int, int], action: str):
    """Stochastic actions: intended move + left/right slips; collision = stay.

    Hazard cells represent slippery floor: actions originating on them are
    significantly less reliable; entering them also adds an explicit cost.
    """
    names = [a[2] for a in ACTIONS]
    idx = names.index(action)
    intended = 0.60 if state in world.hazards else 0.88
    lateral = (1.0 - intended) / 2.0
    outcomes = {}
    for chosen, probability in ((names[idx], intended),
                                (names[(idx-1) % 4], lateral),
                                (names[(idx+1) % 4], lateral)):
        next_cell = world.neighbor(state, chosen)
        outcomes[next_cell] = outcomes.get(next_cell, 0.0) + probability
    return tuple(outcomes.items())


class ValuePolicy:
    """Finite grid stochastic shortest-path policy from discounted value iteration."""
    GAMMA = 0.97
    GOAL_REWARD = 42.0
    HAZARD_PENALTY = 6.0
    BUMP_PENALTY = 0.5
    TOLERANCE = 0.0001
    MAX_SWEEPS = 450

    def __init__(self, world: Warehouse, target: tuple[int, int]):
        self.world = world
        self.target = target
        self.states = world.cells
        self.transitions = {
            (s, a[2]): transition(world, s, a[2])
            for s in self.states for a in ACTIONS if s != target
        }
        self.values = {s: 0.0 for s in self.states}
        self.policy = {}
        self.sweeps = 0
        self.residual = 0.0
        self.properness_corrections = 0
        self.solve()

    def reward(self, state, nxt):
        return (-1.0 + (self.GOAL_REWARD if nxt == self.target else 0.0)
                - (self.HAZARD_PENALTY if nxt in self.world.hazards else 0.0)
                - (self.BUMP_PENALTY if nxt == state else 0.0))

    def expected_q(self, s, action, values):
        return sum(p * (self.reward(s, next_cell) + self.GAMMA * values[next_cell])
                   for next_cell, p in self.transitions[(s, action)])

    def solve(self):
        for n in range(self.MAX_SWEEPS):
            old = self.values
            new = dict(old)
            delta = 0.0
            for s in self.states:
                if s == self.target:
                    continue
                value = max(self.expected_q(s, a[2], old) for a in ACTIONS)
                new[s] = value
                delta = max(delta, abs(value - old[s]))
            self.values = new
            self.sweeps = n + 1
            self.residual = delta
            if delta < self.TOLERANCE:
                break
        for s in self.states:
            if s != self.target:
                self.policy[s] = max(ACTIONS, key=lambda a: self.expected_q(s, a[2], self.values))[2]
        self.ensure_goal_reachability()

    def ensure_goal_reachability(self):
        """Remove *intended-action* cycles that prevent dependable completion.

        Positive-probability reachability alone is insufficient: a policy may
        bounce between two cells and only escape after an extraordinarily rare
        sequence of lateral slips.  A sound warehouse controller must make
        progress even when every move follows its intended direction.

        Preserve the Value Iteration policy in all states whose nominal-action
        chain already reaches the goal.  In all other states connected to the
        goal, switch to an exact shortest-distance recovery action.  Such
        actions strictly reduce grid distance, so every corrected state joins
        an acyclic goal-reaching chain.  Stochastic slips remain simulated.
        """
        field = distance_field(self.world, self.target)
        connected = set(field)
        predecessors = defaultdict(set)
        for state in connected - {self.target}:
            intended_next = self.world.neighbor(state, self.policy[state])
            predecessors[intended_next].add(state)
        good = {self.target}
        queue = deque([self.target])
        while queue:
            for preceding in predecessors[queue.popleft()]:
                if preceding not in good:
                    good.add(preceding)
                    queue.append(preceding)
        trapped = connected - good
        for state in trapped:
            self.policy[state] = shortest_path_action(self.world, state, field)
        self.properness_corrections = len(trapped)

        # Verify deterministic progress from every connected state, not just
        # that some low-probability stochastic escape path exists.
        remaining = set(connected) - {self.target}
        reached = {self.target}
        while remaining:
            joined = {s for s in remaining
                      if self.world.neighbor(s, self.policy[s]) in reached}
            if not joined:
                raise PlanningError('Cannot construct a dependable goal-reaching policy.')
            reached.update(joined)
            remaining.difference_update(joined)


def distance_field(world: Warehouse, target: tuple[int, int]):
    """Exact unit-edge shortest-path distances (same objective as A*)."""
    q = deque([target])
    distance = {target: 0}
    while q:
        s = q.popleft()
        for dx, dy, _ in ACTIONS:
            candidate = (s[0] + dx, s[1] + dy)
            if world.free(candidate) and candidate not in distance:
                distance[candidate] = distance[s] + 1
                q.append(candidate)
    return distance


def shortest_path_action(world, current, field):
    # Choose the next shortest-path step using the cached breadth-first distance field.
    moves = [(field.get(world.neighbor(current, a[2]), math.inf), i, a[2])
             for i, a in enumerate(ACTIONS)]
    return min(moves)[2]


def run_controller(world, order, policies, fields, use_mdp, seed, include_trace=False):
    rng = random.Random(seed)
    current = world.start
    path = [current]
    trace = []
    traversed_hazards = 0
    slips = 0
    goals = [world.tasks[index-1] for index in order] + [world.start]
    completed_tasks = 0
    # Strict finite trial horizon, shared between controllers.
    # Long enough for recovery from several disturbances.
    limit_per_leg = max(80, world.width * world.height * 3)
    for leg, target in enumerate(goals):
        policy = policies[target]
        field = fields[target]
        for step in range(limit_per_leg):
            if current == target:
                break
            action = policy.policy[current] if use_mdp else shortest_path_action(world, current, field)
            outcomes = transition(world, current, action)
            r = rng.random()
            cumulative = 0.0
            next_cell = outcomes[-1][0]
            for candidate, probability in outcomes:
                cumulative += probability
                if r < cumulative:
                    next_cell = candidate
                    break
            expected = world.neighbor(current, action)
            slipped = next_cell != expected
            slips += slipped
            traversed_hazards += next_cell in world.hazards
            if include_trace:
                trace.append({
                    'x': next_cell[0], 'y': next_cell[1], 'action': action,
                    'slipped': slipped, 'hazard': next_cell in world.hazards,
                    'leg': leg, 'target': list(target),
                })
            current = next_cell
            path.append(current)
        if current != target:
            return {'success': False, 'steps': len(path)-1, 'hazard_entries': traversed_hazards,
                    'slips': slips, 'completed': completed_tasks, 'path': path if include_trace else [], 'trace': trace}
        if leg < len(order):
            completed_tasks += 1
    return {'success': True, 'steps': len(path)-1, 'hazard_entries': traversed_hazards,
            'slips': slips, 'completed': completed_tasks, 'path': path if include_trace else [], 'trace': trace}


def summarize_trials(trials):
    n = len(trials)
    return {
        'trials': n,
        'success_rate': round(100 * sum(t['success'] for t in trials) / n, 1),
        'mean_steps': round(sum(t['steps'] for t in trials) / n, 2),
        'mean_hazard_entries': round(sum(t['hazard_entries'] for t in trials) / n, 2),
        'mean_slips': round(sum(t['slips'] for t in trials) / n, 2),
        'mean_tasks_completed': round(sum(t['completed'] for t in trials) / n, 2),
    }


def ints_path(path):
    return [list(p) for p in path]


def analyze_mission(payload: dict, trials: int = 60):
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise PlanningError('Trial count must be a positive integer.')
    world = Warehouse.from_dict(payload)
    nodes, pair_paths, expanded = precompute_pairwise(world)
    climb = hill_climbing(pair_paths, len(world.tasks))
    first_route, first_legs = routed_path(nodes, pair_paths, climb['nearest_order'])
    better_route, better_legs = routed_path(nodes, pair_paths, climb['optimized_order'])
    targets = list(dict.fromkeys([*world.tasks, world.start]))
    policies = {t: ValuePolicy(world, t) for t in targets}
    fields = {t: distance_field(world, t) for t in targets}
    # Reproducible, paired seed list. Both controllers use identical dynamics.
    baseline_trials = [run_controller(world, climb['optimized_order'], policies, fields,
                                     False, 2900 + seed * 101) for seed in range(trials)]
    mdp_trials = [run_controller(world, climb['optimized_order'], policies, fields,
                                True, 2900 + seed * 101) for seed in range(trials)]
    showcase = run_controller(world, climb['optimized_order'], policies, fields, True, 2026, True)
    showcase_baseline = run_controller(world, climb['optimized_order'], policies, fields, False, 2026, True)
    first_goal = world.tasks[climb['optimized_order'][0] - 1]
    goals = [world.tasks[index - 1] for index in climb['optimized_order']] + [world.start]
    policy_by_leg = [
        {'target': list(target), 'cells': [
            {'x': x, 'y': y, 'action': policies[target].policy.get((x, y), ''),
             'value': round(policies[target].values[(x, y)], 2)}
            for x, y in world.cells]}
        for target in goals
    ]
    result = {
        'mission': {
            'width': world.width, 'height': world.height, 'start': list(world.start),
            'blocked': ints_path(sorted(world.blocked)),
            'hazards': ints_path(sorted(world.hazards)),
            'tasks': ints_path(world.tasks),
        },
        'astar': {
            'expanded_nodes_total': expanded,
            'nearest_route': ints_path(first_route),
            'optimized_route': ints_path(better_route),
            'nearest_legs': [ints_path(p) for p in first_legs],
            'optimized_legs': [ints_path(p) for p in better_legs],
            'nearest_hazard_entries': sum(s in world.hazards for s in first_route[1:]),
            'optimized_hazard_entries': sum(s in world.hazards for s in better_route[1:]),
        },
        'hill_climbing': {
            **climb,
            'nearest_order': [i for i in climb['nearest_order']],
            'optimized_order': [i for i in climb['optimized_order']],
            'improvement_pct': round(100*(climb['nearest_steps']-climb['optimized_steps'])/climb['nearest_steps'], 2),
        },
        'mdp': {
            'gamma': ValuePolicy.GAMMA,
            'goal_reward': ValuePolicy.GOAL_REWARD,
            'hazard_penalty': ValuePolicy.HAZARD_PENALTY,
            'normal_intended_probability': 0.88,
            'hazard_intended_probability': 0.60,
            'value_iteration_sweeps': sum(p.sweeps for p in policies.values()),
            'properness_corrections': sum(p.properness_corrections for p in policies.values()),
            'max_residual': round(max(p.residual for p in policies.values()), 6),
            'policy_first_goal': list(first_goal),
            'policy_by_leg': policy_by_leg,
            'showcase': {**showcase, 'path': ints_path(showcase['path'])},
            'showcase_shortest': {**showcase_baseline, 'path': ints_path(showcase_baseline['path'])},
            'shortest_controller': summarize_trials(baseline_trials),
            'risk_aware_controller': summarize_trials(mdp_trials),
        },
        'notes': [
            'A* uses four-neighbor movement, unit step costs and Manhattan distance.',
            'Hill climbing reorders all pick locations and includes the depot return.',
            'MDP policy is recomputed for each destination; transitions include lateral slips.',
            'If intended policy actions do not reach the current goal, recovery uses exact shortest-path distances computed by breadth-first search.',
            'Monte Carlo results are simulation estimates, not field-test measurements.',
        ],
    }
    return result
