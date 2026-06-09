from datetime import date as date_type
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class BookingObjectBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    image: HttpUrl | None = None
    description: str | None = Field(default=None, min_length=1)


class BookingDateAdd(BaseModel):
    date: date_type | None = None
    start_date: date_type | None = None
    end_date: date_type | None = None
    note: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_single_or_period(self) -> "BookingDateAdd":
        has_single = self.date is not None
        has_period = self.start_date is not None or self.end_date is not None
        if has_single == has_period:
            raise ValueError("Send either date or start_date/end_date period.")
        if has_period and (self.start_date is None or self.end_date is None):
            raise ValueError("Both start_date and end_date are required for a period.")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be earlier than or equal to end_date.")
        return self


class BookedDateInput(BaseModel):
    date: date_type
    note: str | None = Field(default=None, max_length=255)


class BookingDatesReplace(BaseModel):
    access_key: str = Field(min_length=32, max_length=128)
    booked_dates: list[BookedDateInput]

    @field_validator("booked_dates", mode="before")
    @classmethod
    def normalize_dates(cls, value: list[date_type | dict]) -> list[date_type | dict]:
        return [
            {"date": item} if not isinstance(item, dict) else item
            for item in value
        ]

    @field_validator("booked_dates")
    @classmethod
    def deduplicate_dates(cls, value: list[BookedDateInput]) -> list[BookedDateInput]:
        dates_by_value = {item.date: item for item in value}
        return [dates_by_value[date_value] for date_value in sorted(dates_by_value)]


class BookedDateWithNote(BaseModel):
    date: date_type
    note: str | None = None


class BookingDateNoteUpdate(BaseModel):
    access_key: str = Field(min_length=32, max_length=128)
    note: str | None = Field(default=None, max_length=255)


class BookingDateWithNoteResponse(BaseModel):
    uuid: UUID
    booked_date: BookedDateWithNote


class BookingObjectRead(BookingObjectBase):
    uuid: UUID
    booked_dates: list[date_type]


class BookingObjectCreateResponse(BookingObjectRead):
    access_key: str


class BookingDatesResponse(BaseModel):
    uuid: UUID
    booked_dates: list[date_type]


class BookingDatesWithNotesResponse(BaseModel):
    uuid: UUID
    booked_dates: list[BookedDateWithNote]
