"""Independent edge-case and property regressions found during final QA.

No third-party test tools are required. Randomized maps use a fixed seed.
"""
from collections import deque
import copy
import itertools
import random
import unittest

from engine.algorithms import (
    ACTIONS, PlanningError, ValuePolicy, Warehouse, a_star, analyze_mission,
    hill_climbing, path_cost, precompute_pairwise, run_controller,
    distance_field, transition,
)
from engine.scenarios import scenarios


class TestAlgorithmPropertyAudit(unittest.TestCase):
    def test_astar_matches_independent_bfs_on_random_grid_pairs(self):
        rng = random.Random(58263)
        checked = 0
        for _ in range(24):
            w, h = 12, 9
            blocked = {(x, y) for y in range(h) for x in range(w)
                       if rng.random() < 0.20 and (x, y) != (0, 0)}
            free = [(x, y) for y in range(h) for x in range(w) if (x, y) not in blocked]
            selected = rng.sample(free, 5)
            world = Warehouse(w, h, selected[0], frozenset(blocked), frozenset(), tuple(selected[1:]))
            for src, dst in itertools.combinations(selected, 2):
                q = deque([src])
                dist = {src: 0}
                while q:
                    current = q.popleft()
                    for dx, dy, _ in ACTIONS:
                        next_cell = (current[0]+dx, current[1]+dy)
                        if world.free(next_cell) and next_cell not in dist:
                            dist[next_cell] = dist[current] + 1
                            q.append(next_cell)
                if dst not in dist:
                    with self.assertRaises(PlanningError):
                        a_star(world, src, dst)
                else:
                    path, _ = a_star(world, src, dst)
                    self.assertEqual(len(path) - 1, dist[dst])
                    self.assertEqual(path[0], src)
                    self.assertEqual(path[-1], dst)
                checked += 1
        self.assertEqual(checked, 240)

    def test_hill_climbing_route_is_valid_and_bounded_by_optimum(self):
        for layout in scenarios().values():
            world = Warehouse.from_dict(layout)
            _, pairs, _ = precompute_pairwise(world)
            best = min(path_cost(pairs, permutation)
                       for permutation in itertools.permutations(range(1, len(world.tasks)+1)))
            candidate = hill_climbing(pairs, len(world.tasks))
            self.assertGreaterEqual(candidate['optimized_steps'], best)
            self.assertLessEqual(candidate['optimized_steps'], candidate['nearest_steps'])
            self.assertEqual(sorted(candidate['optimized_order']), list(range(1, len(world.tasks)+1)))

    def test_mdp_policy_is_bellman_greedy_on_every_preset(self):
        for layout in scenarios().values():
            world = Warehouse.from_dict(layout)
            model = ValuePolicy(world, world.tasks[0])
            for state in world.cells:
                if state == model.target:
                    self.assertEqual(model.values[state], 0)
                    continue
                qs = {a[2]: model.expected_q(state, a[2], model.values) for a in ACTIONS}
                self.assertAlmostEqual(model.values[state], max(qs.values()), delta=0.0002)
                self.assertAlmostEqual(qs[model.policy[state]], max(qs.values()), places=9)

    def test_complete_trace_visits_each_pick_and_returns_home(self):
        for layout in scenarios().values():
            result = analyze_mission(layout, trials=5)
            world = Warehouse.from_dict(layout)
            order = result['hill_climbing']['optimized_order']
            for key in ['showcase', 'showcase_shortest']:
                trace = result['mdp'][key]
                self.assertTrue(trace['success'])
                self.assertEqual(trace['completed'], len(order))
                self.assertEqual(trace['steps'], len(trace['path'])-1)
                self.assertEqual(len(trace['trace']), trace['steps'])
                self.assertEqual(trace['path'][0], layout['start'])
                self.assertEqual(trace['path'][-1], layout['start'])
                goals = [world.tasks[i-1] for i in order] + [world.start]
                seen_goals = [trace['path'][0]]
                last_leg = -1
                for previous, current, movement in zip(trace['path'], trace['path'][1:], trace['trace']):
                    self.assertTrue(world.free(tuple(current)))
                    self.assertLessEqual(abs(previous[0]-current[0])+abs(previous[1]-current[1]), 1)
                    self.assertEqual(current, [movement['x'], movement['y']])
                    self.assertEqual(movement['target'], list(goals[movement['leg']]))
                    self.assertGreaterEqual(movement['leg'], last_leg)
                    last_leg = movement['leg']
                self.assertEqual(sum(p in layout['hazards'] for p in trace['path'][1:]),trace['hazard_entries'])

    def test_empty_hazards_have_zero_risk_and_traversable_routes(self):
        layout = copy.deepcopy(scenarios()['standard'])
        layout['hazards'] = []
        result = analyze_mission(layout, trials=5)
        self.assertEqual(result['mdp']['shortest_controller']['mean_hazard_entries'], 0)
        self.assertEqual(result['mdp']['risk_aware_controller']['mean_hazard_entries'], 0)
        self.assertEqual(result['mdp']['risk_aware_controller']['success_rate'], 100)

    def test_all_risk_floor_transitions_and_simulated_execution(self):
        layout = copy.deepcopy(scenarios()['standard'])
        excluded = {tuple(layout['start']), *(tuple(x) for x in layout['tasks']), *(tuple(x) for x in layout['blocked'])}
        layout['hazards'] = [[x,y] for x in range(layout['width']) for y in range(layout['height'])
                             if (x,y) not in excluded]
        result = analyze_mission(layout, trials=3)
        self.assertEqual(result['mdp']['risk_aware_controller']['trials'], 3)
        self.assertTrue(0 <= result['mdp']['risk_aware_controller']['success_rate'] <= 100)
        self.assertLessEqual(result['mdp']['showcase']['hazard_entries'], result['mdp']['showcase']['steps'])

    def test_maximum_grid_and_eight_pick_points(self):
        layout = {'width':24, 'height':18, 'start':[0,0], 'blocked':[], 'hazards':[],
                  'tasks':[[23,17],[0,17],[23,0],[12,12],[12,0],[0,8],[22,8],[9,17]]}
        result = analyze_mission(layout, trials=3)
        self.assertEqual(len(result['mdp']['policy_by_leg']), 9)
        self.assertEqual(result['mdp']['showcase']['completed'], 8)
        self.assertEqual(result['astar']['nearest_route'][0], [0,0])
        self.assertEqual(result['astar']['optimized_route'][-1], [0,0])

    def test_long_snaking_layout_mdp_completes_instead_of_looping_forever(self):
        # Reproduces a real edge-case discovered in the audit: discounted
        # value iteration could keep circling at the far end of a long maze.
        blocked = []
        for y in range(1, 18, 2):
            if y == 17:
                continue
            exit_x = 23 if ((y-1)//2) % 2 == 0 else 0
            blocked.extend([[x, y] for x in range(24) if x != exit_x])
        layout = {'width':24, 'height':18, 'start':[0,0],
                  'blocked':blocked, 'hazards':[], 'tasks':[[0,16],[23,12]]}
        result = analyze_mission(layout, trials=10)
        self.assertGreater(result['mdp']['properness_corrections'], 0)
        self.assertTrue(result['mdp']['showcase']['success'])
        self.assertEqual(result['mdp']['risk_aware_controller']['success_rate'], 100)
        self.assertEqual(result['mdp']['risk_aware_controller']['mean_tasks_completed'], 2)


    def test_dense_risk_map_nominal_policy_has_no_loops_and_mission_completes(self):
        # A verified counterexample to the old positive-probability safeguard.
        # The previous MDP policy oscillated at (4, 6)/(5, 6) for 1,035 moves
        # rather than completing a reachable 23x15 warehouse mission.
        rng = random.Random(20261023)
        for case in range(8):
            w, h = rng.randint(10, 24), rng.randint(8, 18)
            board = [(x, y) for x in range(w) for y in range(h)]
            start = rng.choice(board)
            blocked = set(rng.sample([p for p in board if p != start],
                                     int(w * h * rng.uniform(0.05, 0.37))))
            free = [p for p in board if p not in blocked and p != start]
            tasks = rng.sample(free, rng.randint(2, min(8, len(free))))
            hazards = set(rng.sample([p for p in free if p not in tasks],
                                     int((len(free) - len(tasks)) * rng.uniform(0, 0.40))))
            if case == 7:
                break
        layout = dict(width=w, height=h, start=list(start),
                      blocked=[list(p) for p in blocked],
                      hazards=[list(p) for p in hazards],
                      tasks=[list(p) for p in tasks])
        self.assertEqual((w, h), (23, 15))
        world = Warehouse.from_dict(layout)
        nodes, pairs, _ = precompute_pairwise(world)
        order = hill_climbing(pairs, len(tasks))['optimized_order']
        goals = [world.tasks[i - 1] for i in order] + [world.start]
        policies = {g: ValuePolicy(world, g) for g in goals}
        fields = {g: distance_field(world, g) for g in goals}
        self.assertGreater(sum(p.properness_corrections for p in policies.values()), 0)
        for goal, policy in policies.items():
            for origin in fields[goal]:
                cursor = origin
                visited = set()
                while cursor != goal:
                    self.assertNotIn(cursor, visited, 'Nominal-action policy contains a cycle')
                    visited.add(cursor)
                    cursor = world.neighbor(cursor, policy.policy[cursor])
                    self.assertLessEqual(len(visited), len(fields[goal]))
        for trial in range(10):
            run = run_controller(world, order, policies, fields, True, 2900 + trial * 101)
            self.assertTrue(run['success'], 'Robot failed to finish reachable dense maze')
            self.assertEqual(run['completed'], 4)

    def test_mdp_expected_transitions_are_normalized(self):
        for layout in scenarios().values():
            world = Warehouse.from_dict(layout)
            for state in world.cells:
                for _, _, action in ACTIONS:
                    self.assertAlmostEqual(sum(prob for _, prob in transition(world, state, action)), 1.0, places=12)

    def test_validation_rejects_unexpected_data_types(self):
        layout = scenarios()['standard']
        candidates = [None, [], 7, 'abc']
        for bad in candidates:
            with self.subTest(bad=bad):
                with self.assertRaises(PlanningError):
                    Warehouse.from_dict(bad)
        for field in ['blocked', 'hazards', 'tasks']:
            bad = copy.deepcopy(layout)
            bad[field] = 'not a list'
            with self.assertRaises(PlanningError):
                Warehouse.from_dict(bad)
        for count in (0, -1, True, 1.5, '10'):
            with self.subTest(trials=count):
                with self.assertRaisesRegex(PlanningError, 'Trial count'):
                    analyze_mission(layout, trials=count)

    def test_transition_changes_only_to_free_neighbors_or_stays(self):
        layout = scenarios()['disruption']
        world = Warehouse.from_dict(layout)
        for state in world.cells:
            for _, _, direction in ACTIONS:
                for nxt, prob in transition(world, state, direction):
                    self.assertLessEqual(abs(nxt[0]-state[0])+abs(nxt[1]-state[1]),1)
                    self.assertTrue(world.free(nxt))
                    self.assertGreater(prob,0)

if __name__ == '__main__':
    unittest.main()
