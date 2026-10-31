import unittest
from datetime import datetime, timedelta, timezone
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

    def test_aware_datetimes_with_different_offsets_are_compared_by_instant(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        booking = SimpleNamespace(
            start_at=datetime(2026, 10, 30, 15, 45, tzinfo=ist),
            end_at=datetime(2026, 10, 30, 16, 15, tzinfo=ist),
            status="APPROVED",
        )
        self.assertFalse(availability_from_bookings([booking], self.start, self.end))

    def test_invalid_requested_interval_is_rejected(self):
        with self.assertRaises(ValueError):
            availability_from_bookings([], self.end, self.start)

    def test_naive_blocking_booking_fails_closed(self):
        booking = SimpleNamespace(
            start_at=datetime(2026, 10, 30, 10),
            end_at=datetime(2026, 10, 30, 11),
            status="IN_USE",
        )
        self.assertFalse(availability_from_bookings([booking], self.start, self.end))

    def test_missing_blocking_booking_timestamps_fail_closed(self):
        for booking in (
            SimpleNamespace(status="APPROVED", end_at=self.end),
            SimpleNamespace(status="IN_USE", start_at=self.start),
        ):
            with self.subTest(booking=booking):
                self.assertFalse(availability_from_bookings([booking], self.start, self.end))

    def test_invalid_blocking_booking_interval_fails_closed(self):
        booking = SimpleNamespace(
            start_at=self.end, end_at=self.start, status="APPROVED"
        )
        self.assertFalse(availability_from_bookings([booking], self.start, self.end))

    def test_exact_overlap_boundaries_are_available(self):
        ending_at_request_start = SimpleNamespace(
            start_at=self.start - timedelta(hours=1),
            end_at=self.start,
            status="APPROVED",
        )
        starting_at_request_end = SimpleNamespace(
            start_at=self.end,
            end_at=self.end + timedelta(hours=1),
            status="IN_USE",
        )
        self.assertTrue(availability_from_bookings(
            [ending_at_request_start, starting_at_request_end], self.start, self.end
        ))

    def test_backend_fields_and_verified_gate_are_adapted(self):
        resource = SimpleNamespace(id=1, title="Laser Cutter", category="fabrication", description="laser prototyping", location="Lab", is_active=True)
        requirements = [SimpleNamespace(requirement_type="training", requirement_value="Certified", is_mandatory=True)]
        qualifications = [SimpleNamespace(user_id=7, qualification_type=" TRAINING ", qualification_title=" certified ", status="VERIFIED")]
        results = recommend_backend_resources(
            {"category": "fabrication", "purpose": "laser", "location": "Lab"},
            [resource], requesting_student_id=7, qualifications=qualifications,
            requirements_by_resource={1: requirements}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertEqual(results[0]["resource_id"], 1)

    def test_pending_qualification_is_hard_gate(self):
        resource = SimpleNamespace(id=1, title="Laser Cutter", category="fabrication", description="laser", location="Lab", is_active=True)
        requirements = [SimpleNamespace(requirement_type="training", requirement_value="Certified", is_mandatory=True)]
        results = recommend_backend_resources(
            {"category": "fabrication"}, [resource],
            requesting_student_id=7,
            qualifications=[SimpleNamespace(user_id=7, qualification_type="training", qualification_title="Certified", status="PENDING")],
            requirements_by_resource={1: requirements}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertEqual(results, [])

    def test_verified_qualification_from_another_student_does_not_grant_access(self):
        resource = SimpleNamespace(id=1, title="Laser Cutter", category="fabrication", description="laser", location="Lab", is_active=True)
        requirements = [SimpleNamespace(requirement_type="training", requirement_value="Certified", is_mandatory=True)]
        results = recommend_backend_resources(
            {"category": "fabrication"}, [resource], requesting_student_id=7,
            qualifications=[SimpleNamespace(user_id=8, qualification_type="training", qualification_title="Certified", status="VERIFIED")],
            requirements_by_resource={1: requirements}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertEqual(results, [])

    def test_backend_title_is_used_for_purpose_matching(self):
        resource = SimpleNamespace(id=1, title="Laser Cutter", category="fabrication", description=None, location="Lab", is_active=True)
        results = recommend_backend_resources(
            {"purpose": "laser cutter"}, [resource], requesting_student_id=7,
            qualifications=[], requirements_by_resource={1: []}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertIn("Purpose relevance (100%)", results[0]["reasons"])

    def test_same_type_verified_qualifications_work_in_either_order(self):
        resource = SimpleNamespace(id=1, title="Workshop", category="lab", description="", location="Lab", is_active=True)
        requirement = SimpleNamespace(requirement_type="training", requirement_value="CNC certified", is_mandatory=True)
        requested = SimpleNamespace(user_id=7, qualification_type="training", qualification_title="CNC certified", status="VERIFIED")
        other = SimpleNamespace(user_id=7, qualification_type="training", qualification_title="First aid", status="VERIFIED")
        for qualifications in ([requested, other], [other, requested]):
            with self.subTest(order=qualifications):
                results = recommend_backend_resources(
                    {}, [resource], requesting_student_id=7, qualifications=qualifications,
                    requirements_by_resource={1: [requirement]}, bookings_by_resource={1: []},
                    requested_start=self.start, requested_end=self.end,
                )
                self.assertEqual([item["resource_id"] for item in results], [1])

    def test_multiple_mandatory_requirements_of_same_type_are_preserved(self):
        resource = SimpleNamespace(id=1, title="Workshop", category="lab", description="", location="Lab", is_active=True)
        requirements = [
            SimpleNamespace(requirement_type="training", requirement_value="CNC certified", is_mandatory=True),
            SimpleNamespace(requirement_type="training", requirement_value="First aid", is_mandatory=True),
        ]
        qualifications = [
            SimpleNamespace(user_id=7, qualification_type="training", qualification_title="CNC certified", status="VERIFIED"),
            SimpleNamespace(user_id=7, qualification_type="training", qualification_title="First aid", status="VERIFIED"),
        ]
        results = recommend_backend_resources(
            {}, [resource], requesting_student_id=7, qualifications=qualifications,
            requirements_by_resource={1: requirements}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertEqual([item["resource_id"] for item in results], [1])

    def test_one_of_two_same_type_mandatory_requirements_is_not_enough(self):
        resource = SimpleNamespace(id=1, title="Workshop", category="lab", description="", location="Lab", is_active=True)
        requirements = [
            SimpleNamespace(requirement_type="training", requirement_value="CNC certified", is_mandatory=True),
            SimpleNamespace(requirement_type="training", requirement_value="First aid", is_mandatory=True),
        ]
        qualifications = [
            SimpleNamespace(user_id=7, qualification_type="training", qualification_title="CNC certified", status="VERIFIED"),
        ]
        results = recommend_backend_resources(
            {}, [resource], requesting_student_id=7, qualifications=qualifications,
            requirements_by_resource={1: requirements}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertEqual(results, [])

    def test_all_same_type_mandatory_requirements_must_be_satisfied(self):
        resource = SimpleNamespace(id=1, title="Workshop", category="lab", description="", location="Lab", is_active=True)
        requirements = [
            SimpleNamespace(requirement_type="training", requirement_value="CNC certified", is_mandatory=True),
            SimpleNamespace(requirement_type="training", requirement_value="First aid", is_mandatory=True),
        ]
        qualifications = [
            SimpleNamespace(user_id=7, qualification_type="training", qualification_title="CNC certified", status="VERIFIED"),
            SimpleNamespace(user_id=7, qualification_type="training", qualification_title="First aid", status="VERIFIED"),
        ]
        results = recommend_backend_resources(
            {}, [resource], requesting_student_id=7, qualifications=qualifications,
            requirements_by_resource={1: requirements}, bookings_by_resource={1: []},
            requested_start=self.start, requested_end=self.end,
        )
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
