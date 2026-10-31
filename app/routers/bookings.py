
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
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
from app.schemas.condition_report_image import ConditionReportImageMetadata
from app.services.inspection_image_service import (
    DuplicateInspectionImageError,
    InspectionImageTooLargeError,
    InvalidInspectionAngleError,
    InvalidInspectionImageError,
    UnsupportedInspectionImageTypeError,
    get_condition_report_image,
    list_condition_report_images,
    upload_condition_report_image,
)
from cv_engine.quality import MAX_IMAGE_BYTES
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


def _inspection_image_metadata(booking, report, image) -> dict:
    return {
        "image_id": image.id,
        "booking_id": booking.id,
        "report_id": report.id,
        "angle": image.angle,
        "stage": report.report_type,
        "mime_type": image.mime_type,
        "byte_size": image.byte_size,
        "sha256": image.sha256,
        "uploaded_at": image.uploaded_at,
    }


def _raise_inspection_image_error(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, PermissionError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, DuplicateInspectionImageError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, RuntimeError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, InspectionImageTooLargeError):
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    elif isinstance(exc, UnsupportedInspectionImageTypeError):
        code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif isinstance(exc, (InvalidInspectionAngleError, InvalidInspectionImageError, ValueError)):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        raise exc
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post(
    "/{booking_id}/condition-reports/{report_id}/images",
    response_model=ConditionReportImageMetadata,
    status_code=status.HTTP_201_CREATED,
)
async def upload_condition_report_image_endpoint(
    booking_id: int,
    report_id: int,
    file: UploadFile = File(...),
    angle: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.STUDENT, UserRole.OWNER, UserRole.ADMIN)
    ),
):
    image_data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(image_data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image exceeds the 15 MiB size limit",
        )
    try:
        booking, report, image = upload_condition_report_image(
            db,
            booking_id=booking_id,
            report_id=report_id,
            actor=current_user,
            angle=angle,
            filename=file.filename,
            declared_mime_type=file.content_type,
            image_data=image_data,
        )
        return _inspection_image_metadata(booking, report, image)
    except (
        LookupError,
        PermissionError,
        RuntimeError,
        ValueError,
        DuplicateInspectionImageError,
        InspectionImageTooLargeError,
        UnsupportedInspectionImageTypeError,
    ) as exc:
        _raise_inspection_image_error(exc)
    finally:
        await file.close()


@router.get(
    "/{booking_id}/condition-reports/{report_id}/images",
)
def list_condition_report_images_endpoint(
    booking_id: int,
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.STUDENT, UserRole.OWNER, UserRole.ADMIN)
    ),
):
    try:
        booking, report, images = list_condition_report_images(
            db,
            booking_id=booking_id,
            report_id=report_id,
            actor=current_user,
        )
        return {
            "images": [
                _inspection_image_metadata(booking, report, image)
                for image in images
            ]
        }
    except (LookupError, PermissionError, ValueError) as exc:
        _raise_inspection_image_error(exc)


@router.get(
    "/{booking_id}/condition-reports/{report_id}/images/{image_id}",
)
def get_condition_report_image_endpoint(
    booking_id: int,
    report_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.STUDENT, UserRole.OWNER, UserRole.ADMIN)
    ),
):
    try:
        _, image = get_condition_report_image(
            db,
            booking_id=booking_id,
            report_id=report_id,
            image_id=image_id,
            actor=current_user,
        )
    except (LookupError, PermissionError, ValueError) as exc:
        _raise_inspection_image_error(exc)
    return Response(
        content=image.image_data,
        media_type=image.mime_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


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
