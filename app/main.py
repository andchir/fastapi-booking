from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
import re
from secrets import compare_digest, token_urlsafe
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import create_db_schema, get_session
from app.i18n import Language, get_language, t, translate_detail
from app.models import BookedDate, BookingObject
from app.schemas import (
    BookingDateAdd,
    BookingDateNoteUpdate,
    BookingDateWithNoteResponse,
    BookingDatesNoteUpdate,
    BookingDatesReplace,
    BookingDatesResponse,
    BookingDatesWithNotesResponse,
    BookingObjectCreateResponse,
    BookingObjectRead,
)
from app.security import require_api_key


DATE_RANGE_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})\s+-\s+(\d{4}-\d{2}-\d{2})\s*$"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_db_schema()
    yield


settings = get_settings()
upload_dir = Path(settings.upload_dir)
upload_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    dependencies=[Depends(require_api_key)],
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")


@app.exception_handler(StarletteHTTPException)
async def localized_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    language = get_language(request)
    detail = (
        translate_detail(exc.detail, language)
        if isinstance(exc.detail, str)
        else exc.detail
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def localized_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    language = get_language(request)
    errors = exc.errors()
    for error in errors:
        message = error.get("msg")
        if isinstance(message, str):
            clean_message = message.removeprefix("Value error, ")
            translated_message = translate_detail(clean_message, language)
            if translated_message != clean_message:
                error["msg"] = translated_message
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(errors)},
    )


def serialize_object(
    booking_object: BookingObject, include_access_key: bool = False
) -> BookingObjectRead | BookingObjectCreateResponse:
    data = {
        "uuid": booking_object.uuid,
        "title": booking_object.title,
        "image": booking_object.image,
        "description": booking_object.description,
        "booked_dates": [booked.date for booked in booking_object.booked_dates],
    }
    if include_access_key:
        return BookingObjectCreateResponse(**data, access_key=booking_object.access_key)
    return BookingObjectRead(**data)


async def get_object_or_404(
    session: AsyncSession, object_uuid: UUID, language: Language
) -> BookingObject:
    result = await session.execute(
        select(BookingObject)
        .options(selectinload(BookingObject.booked_dates))
        .where(BookingObject.uuid == str(object_uuid))
        .execution_options(populate_existing=True)
    )
    booking_object = result.scalar_one_or_none()
    if booking_object is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("object.not_found", language),
        )
    return booking_object


def require_object_access(
    booking_object: BookingObject, access_key: str, language: Language
) -> None:
    if not compare_digest(booking_object.access_key, access_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t("object.invalid_access_key", language),
        )


def save_uploaded_image(request: Request, image: UploadFile) -> str:
    language = get_language(request)
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=t("image.invalid_type", language),
        )

    suffix = Path(image.filename or "").suffix.lower()
    filename = f"{uuid4()}{suffix}"
    file_path = upload_dir / filename

    try:
        with Image.open(image.file) as source:
            image_format = source.format
            resized_image = ImageOps.exif_transpose(source)
            resized_image.thumbnail(
                (settings.image_max_size_px, settings.image_max_size_px),
                Image.Resampling.LANCZOS,
            )

            if image_format == "JPEG" and resized_image.mode in ("RGBA", "P"):
                resized_image = resized_image.convert("RGB")

            resized_image.save(file_path, format=image_format)
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=t("image.invalid_type", language),
        ) from exc

    return str(request.url_for("uploads", path=filename))


def parse_request_date(value: str, language: Language) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=t("date.invalid_format", language),
        ) from exc


def build_date_period(
    start_date: date, end_date: date, language: Language
) -> list[date]:
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=t("date.invalid_period_order", language),
        )

    current = start_date
    dates: list[date] = []
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def dates_from_request(payload: BookingDateAdd, language: Language) -> list[date]:
    if payload.date is not None:
        if isinstance(payload.date, date):
            return [payload.date]

        range_match = DATE_RANGE_RE.fullmatch(payload.date)
        if range_match is not None:
            start_date, end_date = (
                parse_request_date(value, language) for value in range_match.groups()
            )
            return build_date_period(start_date, end_date, language)

        return [parse_request_date(payload.date, language)]

    if payload.start_date is None or payload.end_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=t("date.period_required", language),
        )

    return build_date_period(payload.start_date, payload.end_date, language)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/objects",
    response_model=BookingObjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_object(
    request: Request,
    title: Annotated[str, Form(min_length=1, max_length=255)],
    image: Annotated[UploadFile | None, File()] = None,
    description: Annotated[str | None, Form(min_length=1)] = None,
    booked_dates: Annotated[list[date] | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
) -> BookingObjectCreateResponse:
    image_url = save_uploaded_image(request, image) if image is not None else None
    booking_object = BookingObject(
        access_key=token_urlsafe(32),
        title=title,
        image=image_url,
        description=description,
        booked_dates=[BookedDate(date=value) for value in sorted(set(booked_dates or []))],
    )
    session.add(booking_object)
    await session.commit()
    await session.refresh(booking_object, attribute_names=["booked_dates"])
    return serialize_object(booking_object, include_access_key=True)


@app.get("/objects/{object_uuid}", response_model=BookingObjectRead)
async def get_object(
    object_uuid: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BookingObjectRead:
    language = get_language(request)
    booking_object = await get_object_or_404(session, object_uuid, language)
    return serialize_object(booking_object)


@app.patch("/objects/{object_uuid}", response_model=BookingObjectRead)
async def update_object(
    object_uuid: UUID,
    request: Request,
    access_key: Annotated[str, Form(min_length=32, max_length=128)],
    title: Annotated[str | None, Form(min_length=1, max_length=255)] = None,
    description: Annotated[str | None, Form(min_length=1)] = None,
    image: Annotated[UploadFile | None, File()] = None,
    session: AsyncSession = Depends(get_session),
) -> BookingObjectRead:
    language = get_language(request)
    booking_object = await get_object_or_404(session, object_uuid, language)
    require_object_access(booking_object, access_key, language)

    if title is not None:
        booking_object.title = title
    if description is not None:
        booking_object.description = description
    if image is not None:
        booking_object.image = save_uploaded_image(request, image)

    await session.commit()
    await session.refresh(booking_object, attribute_names=["booked_dates"])
    return serialize_object(booking_object)


@app.post("/objects/{object_uuid}/booked-dates", response_model=BookingDatesResponse)
async def add_booked_dates(
    object_uuid: UUID,
    payload: BookingDateAdd,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BookingDatesResponse:
    language = get_language(request)
    booking_object = await get_object_or_404(session, object_uuid, language)

    for value in dates_from_request(payload, language):
        session.add(
            BookedDate(
                booking_object_id=booking_object.id,
                date=value,
                note=payload.note,
            )
        )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=t("date.already_booked", language),
        ) from exc

    booking_object = await get_object_or_404(session, object_uuid, language)
    return BookingDatesResponse(
        uuid=booking_object.uuid,
        booked_dates=[booked.date for booked in booking_object.booked_dates],
    )


@app.get(
    "/objects/{object_uuid}/booked-dates",
    response_model=BookingDatesWithNotesResponse,
)
async def get_booked_dates_with_notes(
    object_uuid: UUID,
    request: Request,
    access_key: Annotated[str, Query(min_length=32, max_length=128)],
    start_date: date | None = None,
    end_date: date | None = None,
    session: AsyncSession = Depends(get_session),
) -> BookingDatesWithNotesResponse:
    language = get_language(request)
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=t("date.invalid_period_order", language),
        )

    booking_object = await get_object_or_404(session, object_uuid, language)
    require_object_access(booking_object, access_key, language)

    statement = select(BookedDate).where(BookedDate.booking_object_id == booking_object.id)
    if start_date is not None:
        statement = statement.where(BookedDate.date >= start_date)
    if end_date is not None:
        statement = statement.where(BookedDate.date <= end_date)
    statement = statement.order_by(BookedDate.date)

    result = await session.execute(statement)
    return BookingDatesWithNotesResponse(
        uuid=booking_object.uuid,
        booked_dates=[
            {"date": booked.date, "note": booked.note}
            for booked in result.scalars().all()
        ],
    )


@app.put("/objects/{object_uuid}/booked-dates", response_model=BookingDatesResponse)
async def replace_booked_dates(
    object_uuid: UUID,
    payload: BookingDatesReplace,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BookingDatesResponse:
    language = get_language(request)
    booking_object = await get_object_or_404(session, object_uuid, language)
    require_object_access(booking_object, payload.access_key, language)

    await session.execute(
        delete(BookedDate).where(BookedDate.booking_object_id == booking_object.id)
    )
    for booked_date in payload.booked_dates:
        session.add(
            BookedDate(
                booking_object_id=booking_object.id,
                date=booked_date.date,
                note=booked_date.note,
            )
        )

    await session.commit()
    booking_object = await get_object_or_404(session, object_uuid, language)
    return BookingDatesResponse(
        uuid=booking_object.uuid,
        booked_dates=[booked.date for booked in booking_object.booked_dates],
    )


@app.patch(
    "/objects/{object_uuid}/booked-dates",
    response_model=BookingDatesWithNotesResponse,
)
async def update_booked_dates_note(
    object_uuid: UUID,
    payload: BookingDatesNoteUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BookingDatesWithNotesResponse:
    language = get_language(request)
    booking_object = await get_object_or_404(session, object_uuid, language)
    require_object_access(booking_object, payload.access_key, language)

    period_dates = build_date_period(payload.start_date, payload.end_date, language)
    result = await session.execute(
        select(BookedDate)
        .where(
            BookedDate.booking_object_id == booking_object.id,
            BookedDate.date >= payload.start_date,
            BookedDate.date <= payload.end_date,
        )
        .order_by(BookedDate.date)
    )
    booked_dates = result.scalars().all()
    booked_dates_by_value = {booked.date: booked for booked in booked_dates}
    if set(booked_dates_by_value) != set(period_dates):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("booked_dates.period_not_fully_booked", language),
        )

    for booked in booked_dates:
        booked.note = payload.note

    await session.commit()
    return BookingDatesWithNotesResponse(
        uuid=booking_object.uuid,
        booked_dates=[
            {"date": booked.date, "note": booked.note}
            for booked in booked_dates
        ],
    )


@app.patch(
    "/objects/{object_uuid}/booked-dates/{booked_date}",
    response_model=BookingDateWithNoteResponse,
)
async def update_booked_date_note(
    object_uuid: UUID,
    booked_date: date,
    payload: BookingDateNoteUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BookingDateWithNoteResponse:
    language = get_language(request)
    booking_object = await get_object_or_404(session, object_uuid, language)
    require_object_access(booking_object, payload.access_key, language)

    result = await session.execute(
        select(BookedDate).where(
            BookedDate.booking_object_id == booking_object.id,
            BookedDate.date == booked_date,
        )
    )
    booked = result.scalar_one_or_none()
    if booked is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("booked_date.not_found", language),
        )

    booked.note = payload.note
    await session.commit()
    await session.refresh(booked)
    return BookingDateWithNoteResponse(
        uuid=booking_object.uuid,
        booked_date={"date": booked.date, "note": booked.note},
    )


@app.delete("/objects/{object_uuid}/booked-dates")
async def delete_booked_dates_range(
    object_uuid: UUID,
    request: Request,
    access_key: Annotated[str, Query(min_length=32, max_length=128)],
    start_date: date,
    end_date: date,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool | int]:
    language = get_language(request)
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=t("date.invalid_period_order", language),
        )

    booking_object = await get_object_or_404(session, object_uuid, language)
    require_object_access(booking_object, access_key, language)

    result = await session.execute(
        delete(BookedDate).where(
            BookedDate.booking_object_id == booking_object.id,
            BookedDate.date >= start_date,
            BookedDate.date <= end_date,
        )
    )
    deleted_count = result.rowcount or 0
    if deleted_count == 0:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("booked_dates.not_found", language),
        )

    await session.commit()
    return {"success": True, "deleted_count": deleted_count}


@app.delete(
    "/objects/{object_uuid}/booked-dates/{booked_date}",
)
async def delete_booked_date(
    object_uuid: UUID,
    booked_date: date,
    request: Request,
    access_key: Annotated[str, Query(min_length=32, max_length=128)],
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    language = get_language(request)
    booking_object = await get_object_or_404(session, object_uuid, language)
    require_object_access(booking_object, access_key, language)

    result = await session.execute(
        select(BookedDate).where(
            BookedDate.booking_object_id == booking_object.id,
            BookedDate.date == booked_date,
        )
    )
    booked = result.scalar_one_or_none()
    if booked is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("booked_date.not_found", language),
        )

    await session.delete(booked)
    await session.commit()
    return {"success": True}
