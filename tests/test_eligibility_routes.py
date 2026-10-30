
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.models.enums import UserRole
from app.core.security import hash_password, create_access_token


@pytest.fixture
def test_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, TestingSession

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register_user(client, name, email, role):
    response = client.post(
        "/auth/register",
        json={
            "full_name": name,
            "email": email,
            "password": "StrongPass123",
            "role": role,
        },
    )

    assert response.status_code == 201
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_admin(TestingSession):
    db = TestingSession()
    try:
        admin = User(
            full_name="Test Admin",
            email="admin@example.com",
            hashed_password=hash_password("StrongPass123"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        return {
            "Authorization": f"Bearer {create_access_token(admin.id)}"
        }
    finally:
        db.close()


def create_resource(client, owner_headers):
    response = client.post(
        "/resources",
        json={
            "title": "Lab Equipment",
            "description": "Laboratory equipment",
            "category": "Laboratory",
            "resource_type": "EQUIPMENT",
            "location": "Block A",
            "usage_rules": "Handle carefully",
        },
        headers=owner_headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def add_requirement(
    client,
    resource_id,
    owner_headers,
    requirement_type="CERTIFICATION",
    requirement_value="Lab Safety",
    is_mandatory=True,
):
    return client.post(
        f"/resources/{resource_id}/eligibility-requirements",
        json={
            "requirement_type": requirement_type,
            "requirement_value": requirement_value,
            "is_mandatory": is_mandatory,
        },
        headers=owner_headers,
    )


def submit_qualification(
    client,
    student_headers,
    qualification_type="CERTIFICATION",
    qualification_title="Lab Safety",
):
    return client.post(
        "/users/me/qualifications",
        json={
            "qualification_type": qualification_type,
            "qualification_title": qualification_title,
            "description": "Qualification evidence",
            "evidence_reference": "document-123",
        },
        headers=student_headers,
    )


def review_qualification(
    client,
    admin_headers,
    qualification_id,
    review_status="VERIFIED",
    review_note=None,
):
    return client.patch(
        f"/qualifications/{qualification_id}/verify",
        json={
            "status": review_status,
            "review_note": review_note,
        },
        headers=admin_headers,
    )


def check_eligibility(client, resource_id, headers):
    return client.get(
        f"/resources/{resource_id}/eligibility",
        headers=headers,
    )


def test_student_can_submit_qualification(test_context):
    client, _ = test_context
    student = register_user(
        client, "Student One", "student@example.com", "STUDENT"
    )

    response = submit_qualification(client, student)

    assert response.status_code == 201
    assert response.json()["success"] is True
    assert response.json()["data"]["status"] == "PENDING"


def test_student_can_view_only_own_qualifications(test_context):
    client, _ = test_context
    student_a = register_user(
        client, "Student A", "studenta@example.com", "STUDENT"
    )
    student_b = register_user(
        client, "Student B", "studentb@example.com", "STUDENT"
    )

    submit_qualification(client, student_a)
    submit_qualification(
        client,
        student_b,
        "TRAINING",
        "First Aid",
    )

    response = client.get(
        "/users/me/qualifications",
        headers=student_a,
    )

    assert response.status_code == 200
    qualifications = response.json()["data"]
    assert len(qualifications) == 1
    assert qualifications[0]["qualification_type"] == "CERTIFICATION"


def test_verified_exact_match_grants_eligibility(test_context):
    client, TestingSession = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )
    admin = create_admin(TestingSession)

    resource_id = create_resource(client, owner)
    requirement = add_requirement(client, resource_id, owner)
    assert requirement.status_code == 201

    qualification = submit_qualification(client, student)
    qualification_id = qualification.json()["data"]["id"]

    reviewed = review_qualification(
        client, admin, qualification_id, "VERIFIED"
    )
    assert reviewed.status_code == 200

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is True
    assert response.json()["data"]["requirements"][0]["satisfied"] is True


def test_matching_ignores_case_and_surrounding_whitespace(test_context):
    client, TestingSession = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )
    admin = create_admin(TestingSession)

    resource_id = create_resource(client, owner)

    requirement = add_requirement(
        client,
        resource_id,
        owner,
        " CERTIFICATION ",
        " LAB SAFETY ",
    )
    assert requirement.status_code == 201

    qualification = submit_qualification(
        client,
        student,
        "certification",
        "lab safety",
    )
    qualification_id = qualification.json()["data"]["id"]

    reviewed = review_qualification(
        client, admin, qualification_id, "VERIFIED"
    )
    assert reviewed.status_code == 200

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is True


def test_pending_qualification_does_not_grant_eligibility(test_context):
    client, _ = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )

    resource_id = create_resource(client, owner)
    add_requirement(client, resource_id, owner)
    submit_qualification(client, student)

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is False
    assert response.json()["data"]["requirements"][0]["satisfied"] is False


def test_rejected_qualification_does_not_grant_eligibility(test_context):
    client, TestingSession = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )
    admin = create_admin(TestingSession)

    resource_id = create_resource(client, owner)
    add_requirement(client, resource_id, owner)

    qualification = submit_qualification(client, student)
    qualification_id = qualification.json()["data"]["id"]

    reviewed = review_qualification(
        client,
        admin,
        qualification_id,
        "REJECTED",
        "Evidence is insufficient",
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["data"]["review_note"] == "Evidence is insufficient"

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is False


def test_missing_mandatory_requirement_makes_student_ineligible(test_context):
    client, TestingSession = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )
    admin = create_admin(TestingSession)

    resource_id = create_resource(client, owner)
    add_requirement(client, resource_id, owner)

    qualification = submit_qualification(
        client, student, "TRAINING", "First Aid"
    )
    qualification_id = qualification.json()["data"]["id"]

    review_qualification(
        client, admin, qualification_id, "VERIFIED"
    )

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is False


def test_all_mandatory_requirements_must_be_satisfied(test_context):
    client, TestingSession = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )
    admin = create_admin(TestingSession)

    resource_id = create_resource(client, owner)

    add_requirement(
        client, resource_id, owner, "CERTIFICATION", "Lab Safety"
    )
    add_requirement(
        client, resource_id, owner, "TRAINING", "First Aid"
    )

    qualification = submit_qualification(
        client, student, "CERTIFICATION", "Lab Safety"
    )
    qualification_id = qualification.json()["data"]["id"]

    review_qualification(
        client, admin, qualification_id, "VERIFIED"
    )

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is False

    second_qualification = submit_qualification(
        client, student, "TRAINING", "First Aid"
    )
    second_id = second_qualification.json()["data"]["id"]

    review_qualification(client, admin, second_id, "VERIFIED")

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is True


def test_unsatisfied_optional_requirement_does_not_block_eligibility(test_context):
    client, _ = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )

    resource_id = create_resource(client, owner)

    add_requirement(
        client,
        resource_id,
        owner,
        "CERTIFICATION",
        "Lab Safety",
        True,
    )
    add_requirement(
        client,
        resource_id,
        owner,
        "TRAINING",
        "First Aid",
        False,
    )

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is False


def test_resource_with_no_requirements_is_eligible(test_context):
    client, _ = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )

    resource_id = create_resource(client, owner)

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is True
    assert response.json()["data"]["requirements"] == []


def test_student_cannot_verify_own_qualification(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )
    qualification = submit_qualification(client, student)
    qualification_id = qualification.json()["data"]["id"]

    response = review_qualification(
        client, student, qualification_id, "VERIFIED"
    )

    assert response.status_code == 403


def test_non_admin_owner_cannot_verify_qualification(test_context):
    client, _ = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )

    qualification = submit_qualification(client, student)
    qualification_id = qualification.json()["data"]["id"]

    response = review_qualification(
        client, owner, qualification_id, "VERIFIED"
    )

    assert response.status_code == 403


def test_eligibility_is_recalculated_after_admin_rejection(test_context):
    client, TestingSession = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )
    admin = create_admin(TestingSession)

    resource_id = create_resource(client, owner)
    add_requirement(client, resource_id, owner)

    qualification = submit_qualification(client, student)
    qualification_id = qualification.json()["data"]["id"]

    review_qualification(
        client, admin, qualification_id, "VERIFIED"
    )

    first_check = check_eligibility(client, resource_id, student)
    assert first_check.json()["data"]["eligible"] is True

    review_qualification(
        client,
        admin,
        qualification_id,
        "REJECTED",
        "Verification revoked",
    )

    second_check = check_eligibility(client, resource_id, student)
    assert second_check.json()["data"]["eligible"] is False


def test_owner_cannot_add_requirement_to_another_owners_resource(test_context):
    client, _ = test_context

    owner_a = register_user(
        client, "Owner A", "ownera@example.com", "OWNER"
    )
    owner_b = register_user(
        client, "Owner B", "ownerb@example.com", "OWNER"
    )

    resource_id = create_resource(client, owner_a)

    response = add_requirement(
        client,
        resource_id,
        owner_b,
    )

    assert response.status_code == 403


def test_admin_can_add_requirement_to_any_resource(test_context):
    client, TestingSession = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    admin = create_admin(TestingSession)

    resource_id = create_resource(client, owner)

    response = add_requirement(
        client,
        resource_id,
        admin,
    )

    assert response.status_code == 201
    assert response.json()["data"]["resource_id"] == resource_id


def test_invalid_resource_returns_404(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )

    response = check_eligibility(client, 99999, student)

    assert response.status_code == 404


def test_invalid_qualification_returns_404(test_context):
    client, TestingSession = test_context

    admin = create_admin(TestingSession)

    response = review_qualification(
        client,
        admin,
        99999,
        "VERIFIED",
    )

    assert response.status_code == 404

def test_unsatisfied_optional_requirement_does_not_block_eligible_student(
    test_context,
):
    client, TestingSession = test_context

    owner = register_user(
        client, "Owner", "owner@example.com", "OWNER"
    )
    student = register_user(
        client, "Student", "student@example.com", "STUDENT"
    )
    admin = create_admin(TestingSession)

    resource_id = create_resource(client, owner)

    # Mandatory requirement
    add_requirement(
        client, resource_id, owner,
        "CERTIFICATION", "Lab Safety", True,
    )

    # Optional requirement
    add_requirement(
        client, resource_id, owner,
        "TRAINING", "First Aid", False,
    )

    qualification = submit_qualification(
        client, student,
        "CERTIFICATION", "Lab Safety",
    )
    qualification_id = qualification.json()["data"]["id"]

    reviewed = review_qualification(
        client, admin, qualification_id, "VERIFIED"
    )
    assert reviewed.status_code == 200

    response = check_eligibility(client, resource_id, student)

    assert response.status_code == 200
    assert response.json()["data"]["eligible"] is True

    requirements = response.json()["data"]["requirements"]
    assert requirements[0]["satisfied"] is True
    assert requirements[1]["satisfied"] is False