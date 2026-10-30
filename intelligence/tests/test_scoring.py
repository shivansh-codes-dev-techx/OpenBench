import unittest

from intelligence.scoring import WEIGHTS, component_scores, weighted_score


class ScoringTests(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)

    def test_perfect_match_scores_one(self):
        requirements = {"category": "electronics kit", "purpose": "robotics", "location": "north lab", "date_time": "Mon 10"}
        resource = {"category": "electronics kit", "description": "robotics project", "location": "north lab", "available_slots": ["Mon 10"]}
        self.assertEqual(weighted_score(component_scores(requirements, resource)), 1.0)

    def test_unavailable_requested_slot_lowers_score(self):
        requirements = {"category": "camera", "date_time": "Mon 10"}
        resource = {"category": "camera", "available_slots": ["Tue 10"]}
        scores = component_scores(requirements, resource)
        self.assertEqual(scores["availability"], 0.0)
        self.assertAlmostEqual(weighted_score(scores), 0.8)


if __name__ == "__main__":
    unittest.main()
