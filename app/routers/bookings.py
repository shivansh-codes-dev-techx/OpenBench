
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.booking import (
    BookingCreate,
    BookingResponse,
    BookingDecision,
    ConditionReportCreate,
    ConditionReportResponse,
)
from app.schemas.common import APIResponse
from app.services.booking_service import (
    create_booking,
    get_my_bookings,
    decide_booking,
    get_booking_by_id,
    create_condition_report,
    get_owner_bookings,
    check_in_booking,
    check_out_booking,
)

router = APIRouter(prefix="/bookings", tags=["Bookings"])


# --------------------------------------------------
# CREATE BOOKING
# POST /bookings
# --------------------------------------------------

@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_booking_endpoint(
    booking_data: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.STUDENT)
    ),
):
    try:
        booking = create_booking(
            db=db,
            user_id=current_user.id,
            booking_data=booking_data,
        )

        return APIResponse(
            success=True,
            message="Booking request created successfully",
            data=BookingResponse.model_validate(booking),
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


# --------------------------------------------------
# GET MY BOOKINGS
# GET /bookings/me
# --------------------------------------------------

@router.get(
    "/me",
    response_model=APIResponse,
)
def get_my_bookings_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.STUDENT)
    ),
):
    bookings = get_my_bookings(
        db=db,
        user_id=current_user.id,
    )

    return APIResponse(
        success=True,
        message="Your bookings retrieved successfully",
        data=[
            BookingResponse.model_validate(booking)
            for booking in bookings
        ],
    )

# --------------------------------------------------
# GET OWNER BOOKINGS
# GET /bookings/owner
# --------------------------------------------------

@router.get(
    "/owner",
    response_model=APIResponse,
)
def get_owner_bookings_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN)
    ),
):
    bookings = get_owner_bookings(
        db=db,
        owner_id=current_user.id,
    )

    return APIResponse(
        success=True,
        message="Owner bookings retrieved successfully",
        data=[
            BookingResponse.model_validate(booking)
            for booking in bookings
        ],
    )


# --------------------------------------------------
# APPROVE / REJECT BOOKING
# PATCH /bookings/{booking_id}/decision
# --------------------------------------------------

@router.patch(
    "/{booking_id}/decision",
    response_model=APIResponse,
)
def decide_booking_endpoint(
    booking_id: int,
    decision_data: BookingDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN)
    ),
):
    try:
        booking = decide_booking(
            db=db,
            booking_id=booking_id,
            actor=current_user,
            decision_data=decision_data,
        )

        return APIResponse(
            success=True,
            message="Booking decision recorded successfully",
            data=BookingResponse.model_validate(booking),
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


# --------------------------------------------------
# GET BOOKING DETAIL
# GET /bookings/{booking_id}
# --------------------------------------------------

@router.get(
    "/{booking_id}",
    response_model=APIResponse,
)
def get_booking_detail_endpoint(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.STUDENT,
            UserRole.OWNER,
            UserRole.ADMIN,
        )
    ),
):
    try:
        booking = get_booking_by_id(
            db=db,
            booking_id=booking_id,
            actor=current_user,
        )

        return APIResponse(
            success=True,
            message="Booking details retrieved successfully",
            data=BookingResponse.model_validate(booking),
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


# --------------------------------------------------
# INITIAL CONDITION REPORT
# POST /bookings/{booking_id}/condition-reports/initial
# --------------------------------------------------

@router.post(
    "/{booking_id}/condition-reports/initial",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_initial_condition_report_endpoint(
    booking_id: int,
    report_data: ConditionReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.STUDENT,
            UserRole.OWNER,
            UserRole.ADMIN,
        )
    ),
):
    try:
        report = create_condition_report(
            db=db,
            booking_id=booking_id,
            actor=current_user,
            report_type="INITIAL",
            report_data=report_data,
        )

        return APIResponse(
            success=True,
            message="Initial condition report submitted successfully",
            data=ConditionReportResponse.model_validate(report),
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


# --------------------------------------------------
# FINAL CONDITION REPORT
# POST /bookings/{booking_id}/condition-reports/final
# --------------------------------------------------

@router.post(
    "/{booking_id}/condition-reports/final",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_final_condition_report_endpoint(
    booking_id: int,
    report_data: ConditionReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.STUDENT,
            UserRole.OWNER,
            UserRole.ADMIN,
        )
    ),
):
    try:
        report = create_condition_report(
            db=db,
            booking_id=booking_id,
            actor=current_user,
            report_type="FINAL",
            report_data=report_data,
        )

        return APIResponse(
            success=True,
            message="Final condition report submitted successfully",
            data=ConditionReportResponse.model_validate(report),
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

# --------------------------------------------------
# CHECK IN BOOKING
# POST /bookings/{booking_id}/check-in
# --------------------------------------------------

@router.post(
    "/{booking_id}/check-in",
    response_model=APIResponse,
)
def check_in_booking_endpoint(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.STUDENT,
            UserRole.OWNER,
            UserRole.ADMIN,
        )
    ),
):
    try:
        booking = check_in_booking(
            db=db,
            booking_id=booking_id,
            actor=current_user,
        )

        return APIResponse(
            success=True,
            message="Booking checked in successfully",
            data=BookingResponse.model_validate(booking),
        )

    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# --------------------------------------------------
# CHECK OUT BOOKING
# POST /bookings/{booking_id}/check-out
# --------------------------------------------------

@router.post(
    "/{booking_id}/check-out",
    response_model=APIResponse,
)
def check_out_booking_endpoint(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.STUDENT,
            UserRole.OWNER,
            UserRole.ADMIN,
        )
    ),
):
    try:
        booking = check_out_booking(
            db=db,
            booking_id=booking_id,
            actor=current_user,
        )

        return APIResponse(
            success=True,
            message="Booking checked out successfully",
            data=BookingResponse.model_validate(booking),
        )

    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc