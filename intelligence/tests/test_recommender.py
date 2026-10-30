import unittest

from intelligence import recommend_resources


class RecommenderTests(unittest.TestCase):
    def setUp(self):
        self.requirements = {"category": "electronics kit", "purpose": "robotics", "location": "north lab", "date_time": "Mon 10"}
        self.resources = [
            {"resource_id": 1, "category": "electronics kit", "description": "robotics projects", "location": "north lab", "available_slots": ["Mon 10"]},
            {"resource_id": 2, "category": "electronics kit", "description": "robotics projects", "location": "north lab", "available_slots": ["Mon 10"], "eligibility_required": {"training": "certified"}},
            {"resource_id": 3, "category": "electronics kit", "description": "robotics", "location": "south lab", "available": False},
        ]

    def test_ineligible_resource_is_excluded_before_ranking(self):
        results = recommend_resources(self.requirements, self.resources, user_eligibility={"training": "uncertified"})
        self.assertEqual([item["resource_id"] for item in results], [1, 3])

    def test_results_are_ranked_and_explainable(self):
        results = recommend_resources(self.requirements, self.resources, user_eligibility={"training": "certified"})
        self.assertEqual(results[0]["resource_id"], 1)
        self.assertGreater(results[0]["score"], results[-1]["score"])
        self.assertTrue(any("Category relevance" in reason for reason in results[0]["reasons"]))
        self.assertTrue(any("Eligibility requirements satisfied" in reason for reason in results[0]["reasons"]))

    def test_limit_and_empty_results(self):
        self.assertEqual(len(recommend_resources(self.requirements, self.resources, user_eligibility={"training": "certified"}, limit=1)), 1)
        gated_resources = [dict(item, eligibility_required={"training": "certified"}) for item in self.resources]
        self.assertEqual(recommend_resources({}, gated_resources, user_eligibility={"training": "none"}), [])


if __name__ == "__main__":
    unittest.main()
