from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from shutil import copyfileobj
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import create_db_schema, get_session
from app.models import BookedDate, BookingObject
from app.schemas import (
    BookingDateAdd,
    BookingDatesReplace,
    BookingDatesResponse,
    BookingObjectCreateResponse,
    BookingObjectRead,
)
from app.security import require_api_key


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
)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")


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


async def get_object_or_404(session: AsyncSession, object_uuid: UUID) -> BookingObject:
    result = await session.execute(
        select(BookingObject)
        .options(selectinload(BookingObject.booked_dates))
        .where(BookingObject.uuid == str(object_uuid))
    )
    booking_object = result.scalar_one_or_none()
    if booking_object is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found.")
    return booking_object


def require_object_access(booking_object: BookingObject, access_key: str) -> None:
    if not compare_digest(booking_object.access_key, access_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid access key for this object.",
        )


def save_uploaded_image(request: Request, image: UploadFile) -> str:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded file must be an image.",
        )

    suffix = Path(image.filename or "").suffix.lower()
    filename = f"{uuid4()}{suffix}"
    file_path = upload_dir / filename

    with file_path.open("wb") as output:
        copyfileobj(image.file, output)

    return str(request.url_for("uploads", path=filename))


def dates_from_request(payload: BookingDateAdd) -> list[date]:
    if payload.date is not None:
        return [payload.date]

    if payload.start_date is None or payload.end_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both start_date and end_date are required for a period.",
        )

    current = payload.start_date
    dates: list[date] = []
    while current <= payload.end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


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
    description: Annotated[str, Form(min_length=1)],
    image: Annotated[UploadFile, File()],
    booked_dates: Annotated[list[date] | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
) -> BookingObjectCreateResponse:
    image_url = save_uploaded_image(request, image)
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
    session: AsyncSession = Depends(get_session),
) -> BookingObjectRead:
    booking_object = await get_object_or_404(session, object_uuid)
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
    booking_object = await get_object_or_404(session, object_uuid)
    require_object_access(booking_object, access_key)

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
    session: AsyncSession = Depends(get_session),
) -> BookingDatesResponse:
    booking_object = await get_object_or_404(session, object_uuid)

    for value in dates_from_request(payload):
        session.add(BookedDate(booking_object_id=booking_object.id, date=value))

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more dates are already booked for this object.",
        ) from exc

    booking_object = await get_object_or_404(session, object_uuid)
    return BookingDatesResponse(
        uuid=booking_object.uuid,
        booked_dates=[booked.date for booked in booking_object.booked_dates],
    )


@app.put("/objects/{object_uuid}/booked-dates", response_model=BookingDatesResponse)
async def replace_booked_dates(
    object_uuid: UUID,
    payload: BookingDatesReplace,
    session: AsyncSession = Depends(get_session),
) -> BookingDatesResponse:
    booking_object = await get_object_or_404(session, object_uuid)
    require_object_access(booking_object, payload.access_key)

    await session.execute(
        delete(BookedDate).where(BookedDate.booking_object_id == booking_object.id)
    )
    for value in payload.booked_dates:
        session.add(BookedDate(booking_object_id=booking_object.id, date=value))

    await session.commit()
    booking_object = await get_object_or_404(session, object_uuid)
    return BookingDatesResponse(
        uuid=booking_object.uuid,
        booked_dates=[booked.date for booked in booking_object.booked_dates],
    )
