from datetime import date as date_type
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class BookingObjectBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    image: HttpUrl
    description: str = Field(min_length=1)


class BookingDateAdd(BaseModel):
    date: date_type | None = None
    start_date: date_type | None = None
    end_date: date_type | None = None

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


class BookingDatesReplace(BaseModel):
    access_key: str = Field(min_length=32, max_length=128)
    booked_dates: list[date_type]

    @field_validator("booked_dates")
    @classmethod
    def deduplicate_dates(cls, value: list[date_type]) -> list[date_type]:
        return sorted(set(value))


class BookingObjectRead(BookingObjectBase):
    uuid: UUID
    booked_dates: list[date_type]


class BookingObjectCreateResponse(BookingObjectRead):
    access_key: str


class BookingDatesResponse(BaseModel):
    uuid: UUID
    booked_dates: list[date_type]
