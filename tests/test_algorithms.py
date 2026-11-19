"""Correctness, reproducibility and algorithm integration regression tests."""
import copy
from collections import deque
import itertools
import json
import math
import unittest

from engine.algorithms import (
    ACTIONS, PlanningError, ValuePolicy, Warehouse, a_star, analyze_mission,
    distance_field, hill_climbing, pair_dist, path_cost, precompute_pairwise,
    transition, run_controller,
)
from engine.scenarios import scenarios


class TestWarehouseValidation(unittest.TestCase):
    def setUp(self):
        self.m = copy.deepcopy(scenarios()['standard'])

    def test_duplicate_locations_are_rejected(self):
        self.m['tasks'].append(self.m['tasks'][0])
        with self.assertRaisesRegex(PlanningError, 'distinct'):
            Warehouse.from_dict(self.m)

    def test_outside_grid_rejected(self):
        self.m['tasks'][0] = [-1, 3]
        with self.assertRaisesRegex(PlanningError, 'outside'):
            Warehouse.from_dict(self.m)

    def test_blocked_goal_rejected(self):
        self.m['blocked'].append(self.m['tasks'][0])
        with self.assertRaisesRegex(PlanningError, 'blocked'):
            Warehouse.from_dict(self.m)

    def test_not_enough_tasks_rejected(self):
        self.m['tasks'] = [self.m['tasks'][0]]
        with self.assertRaisesRegex(PlanningError, 'at least two'):
            Warehouse.from_dict(self.m)

    def test_bool_coordinates_rejected(self):
        self.m['tasks'][0] = [True, 3]
        with self.assertRaisesRegex(PlanningError, 'integers'):
            Warehouse.from_dict(self.m)

    def test_unreachable_task_rejected(self):
        self.m['tasks'][0] = [0, 0]
        self.m['blocked'] += [[0, 1], [1, 0]]
        with self.assertRaisesRegex(PlanningError, 'cannot be reached'):
            analyze_mission(self.m, trials=1)


class TestAStar(unittest.TestCase):
    def test_matches_breadth_first_search_on_every_preset(self):
        for name, raw in scenarios().items():
            with self.subTest(name=name):
                world = Warehouse.from_dict(raw)
                goals = [world.start, *world.tasks]
                for a, b in itertools.combinations(goals, 2):
                    route, expanded = a_star(world, a, b)
                    field = distance_field(world, b)
                    self.assertEqual(len(route)-1, field[a])
                    self.assertEqual(route[0], a)
                    self.assertEqual(route[-1], b)
                    self.assertGreaterEqual(expanded, 1)
                    for x, y in route:
                        self.assertTrue(world.free((x, y)))
                    for u, v in zip(route, route[1:]):
                        self.assertEqual(abs(u[0]-v[0])+abs(u[1]-v[1]), 1)


class TestHillClimbing(unittest.TestCase):
    def test_climbing_never_worse_than_nearest_neighbor(self):
        for raw in scenarios().values():
            world = Warehouse.from_dict(raw)
            nodes, pair_paths, expansions = precompute_pairwise(world)
            result = hill_climbing(pair_paths, len(world.tasks))
            self.assertEqual(sorted(result['optimized_order']), list(range(1,len(world.tasks)+1)))
            self.assertEqual(path_cost(pair_paths,result['optimized_order']),result['optimized_steps'])
            self.assertLessEqual(result['optimized_steps'], result['nearest_steps'])
            self.assertGreater(result['neighbors_evaluated'],0)

    def test_baseline_improves_on_standard(self):
        result = analyze_mission(scenarios()['standard'],trials=3)
        self.assertGreater(result['hill_climbing']['improvement_pct'], 0)


class TestMDP(unittest.TestCase):
    def test_transition_probabilities_sum_to_one(self):
        for raw in scenarios().values():
            world = Warehouse.from_dict(raw)
            for state in world.cells:
                for _,_,action in ACTIONS:
                    outcomes = transition(world,state,action)
                    self.assertAlmostEqual(sum(p for _, p in outcomes), 1.0, places=10)
                    self.assertTrue(all(world.free(p) for p, _ in outcomes))
                    self.assertTrue(all(0 < p <= 1 for _, p in outcomes))

    def test_slippery_tiles_are_less_reliable(self):
        world = Warehouse.from_dict(scenarios()['disruption'])
        hazard = (2,6)
        normal = (2,5)
        self.assertIn(hazard, world.hazards)
        self.assertAlmostEqual(dict(transition(world,hazard,'E'))[(3,6)],0.60)
        self.assertAlmostEqual(dict(transition(world,normal,'E'))[(3,5)],0.88)

    def test_value_iteration_converges(self):
        world=Warehouse.from_dict(scenarios()['standard'])
        model=ValuePolicy(world,world.tasks[0])
        self.assertLess(model.residual,model.TOLERANCE)
        self.assertTrue(0<model.sweeps<=model.MAX_SWEEPS)
        self.assertEqual(len(model.policy),len(world.cells)-1)

    def test_reproducible_statistics_and_positive_safety_effect(self):
        layout=scenarios()['narrow']
        result1=analyze_mission(layout,trials=60)
        result2=analyze_mission(layout,trials=60)
        self.assertEqual(json.dumps(result1,sort_keys=True),json.dumps(result2,sort_keys=True))
        short=result1['mdp']['shortest_controller']
        safe=result1['mdp']['risk_aware_controller']
        self.assertEqual(short['trials'],60)
        self.assertEqual(safe['trials'],60)
        self.assertLess(safe['mean_hazard_entries'],short['mean_hazard_entries'])


class TestIntegration(unittest.TestCase):
    def test_no_input_mutation_and_complete_return_mission(self):
        layout=scenarios()['disruption']
        original=copy.deepcopy(layout)
        res=analyze_mission(layout,trials=5)
        self.assertEqual(layout,original)
        h=res['hill_climbing']
        self.assertEqual(len(res['astar']['optimized_route'])-1,h['optimized_steps'])
        self.assertEqual(res['astar']['optimized_route'][0],layout['start'])
        self.assertEqual(res['astar']['optimized_route'][-1],layout['start'])
        self.assertEqual(len(h['optimized_order']),len(layout['tasks']))
        self.assertEqual(res['mdp']['risk_aware_controller']['mean_tasks_completed'],len(layout['tasks']))
        self.assertEqual(len(res['mdp']['policy_by_leg']),len(layout['tasks'])+1)
        self.assertEqual(res['mdp']['showcase']['steps'],len(res['mdp']['showcase']['trace']))


if __name__ == '__main__':
    unittest.main()
