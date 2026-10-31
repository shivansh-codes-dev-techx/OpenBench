import unittest

from intelligence.matching import is_eligible, text_similarity


class MatchingTests(unittest.TestCase):
    def test_keyword_overlap_is_case_insensitive(self):
        self.assertEqual(text_similarity("Electronics Kit", "electronics development kit"), 1.0)

    def test_empty_query_is_neutral(self):
        self.assertEqual(text_similarity("", "anything"), 1.0)

    def test_eligibility_requires_every_attribute(self):
        required = {"department": ["ECE", "EEE"], "training": "laser-certified"}
        self.assertTrue(is_eligible({"department": "ece", "training": "LASER-CERTIFIED"}, required))
        self.assertFalse(is_eligible({"department": "ECE"}, required))
        self.assertFalse(is_eligible({"department": "CSE", "training": "laser-certified"}, required))

    def test_no_declared_requirements_allows_any_user(self):
        self.assertTrue(is_eligible(None, {}))


if __name__ == "__main__":
    unittest.main()
