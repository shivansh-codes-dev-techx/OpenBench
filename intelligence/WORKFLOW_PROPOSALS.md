# Condition and incident workflow proposals

The latest backend branch already contains `condition_reports` and `incidents` tables. No shared model or API changes are proposed in this branch.

## Condition reports

Use the existing `booking_id`, `submitted_by_id`, `report_type`, `condition_description`, `evidence_reference`, and `created_at` fields. Validate `report_type` against the backend contract values `INITIAL` and `FINAL`, require a non-empty trimmed description, require a booking in the appropriate lifecycle state, and ensure the submitting user is the booking student or resource owner. Resolve the resource through the booking rather than duplicating `resource_id`.

## Incidents

Use the existing `booking_id`, `reported_by_id`, `title`, `description`, `severity`, `resolution_note`, and `created_at` fields. Validate a non-empty title and description, constrain severity to a small documented set such as `LOW`, `MEDIUM`, and `HIGH`, and allow reports from the booking student, resource owner, or an administrator. Booking ownership supplies the resource link. Review and resolution should be explicit admin/owner actions. Incident records must not create automatic fines, bans, or penalties; any consequence requires human review.

## Eligibility test checklist

The backend pytest suite should cover verified exact matches, pending/rejected/missing qualifications, trimming and case-folding, all-versus-one-missing mandatory requirements, no requirements, student submission ownership, admin-only review, private qualification visibility, booking denial for ineligible students, and eligibility recheck during approval. These tests should be added beside the existing backend tests only after Shivansh confirms the current branch and fixtures.
