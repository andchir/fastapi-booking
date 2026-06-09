from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_uuid() -> str:
    return str(uuid4())


class BookingObject(Base):
    __tablename__ = "booking_objects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=new_uuid)
    access_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    image: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    booked_dates: Mapped[list["BookedDate"]] = relationship(
        back_populates="booking_object",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BookedDate.date",
    )


class BookedDate(Base):
    __tablename__ = "booked_dates"
    __table_args__ = (
        UniqueConstraint("booking_object_id", "date", name="uq_booked_date_object_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_object_id: Mapped[int] = mapped_column(
        ForeignKey("booking_objects.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    booking_object: Mapped[BookingObject] = relationship(back_populates="booked_dates")
