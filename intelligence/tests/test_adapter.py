import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from intelligence.adapter import availability_from_bookings, recommend_backend_resources


class AdapterTests(unittest.TestCase):
    start = datetime(2026, 10, 30, 10, tzinfo=timezone.utc)
    end = datetime(2026, 10, 30, 11, tzinfo=timezone.utc)

    def test_only_approved_and_in_use_overlaps_block(self):
        overlap = SimpleNamespace(resource_id=1, start_at=self.start, end_at=self.end, status="APPROVED")
        pending = SimpleNamespace(resource_id=1, start_at=self.start, end_at=self.end, status="PENDING")
        self.assertFalse(availability_from_bookings([overlap], self.start, self.end))
        self.assertTrue(availability_from_bookings([pending], self.start, self.end))

    def test_backend_fields_and_verified_gate_are_adapted(self):
        resource = SimpleNamespace(id=1, title="Laser Cutter", category="fabrication", description="laser prototyping", location="Lab", is_active=True)
        requirements = [SimpleNamespace(requirement_type="training", requirement_value="Certified", is_mandatory=True)]
        qualifications = [SimpleNamespace(qualification_type=" TRAINING ", qualification_title=" certified ", status="VERIFIED")]
        results = recommend_backend_resources(
            {"category": "fabrication", "purpose": "laser", "location": "Lab"},
            [resource], qualifications=qualifications,
            requirements_by_resource={1: requirements}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertEqual(results[0]["resource_id"], 1)

    def test_pending_qualification_is_hard_gate(self):
        resource = SimpleNamespace(id=1, title="Laser Cutter", category="fabrication", description="laser", location="Lab", is_active=True)
        requirements = [SimpleNamespace(requirement_type="training", requirement_value="Certified", is_mandatory=True)]
        results = recommend_backend_resources(
            {"category": "fabrication"}, [resource],
            qualifications=[SimpleNamespace(qualification_type="training", qualification_title="Certified", status="PENDING")],
            requirements_by_resource={1: requirements}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
