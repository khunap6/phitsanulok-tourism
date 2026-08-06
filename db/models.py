from datetime import date, datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    search_query: Mapped[Optional[str]] = mapped_column(String(255))
    overall_rating: Mapped[Optional[float]] = mapped_column(Numeric(2, 1))
    location: Mapped[Optional[object]] = mapped_column(
        Geometry("POINT", srid=4326), nullable=True
    )
    zone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    google_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    business_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    opening_hours: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    distance_nu_km: Mapped[Optional[float]] = mapped_column(Numeric(6, 3), nullable=True)
    distance_psru_km: Mapped[Optional[float]] = mapped_column(Numeric(6, 3), nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    reviews: Mapped[list["Review"]] = relationship(
        back_populates="place", cascade="all, delete-orphan"
    )


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("place_id", "text_hash", name="uq_place_text_hash"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="chk_rating"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[Optional[int]] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_clean: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_hash: Mapped[Optional[str]] = mapped_column(String(32))
    review_date: Mapped[Optional[str]] = mapped_column(String(100))
    review_date_approx: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    place: Mapped["Place"] = relationship(back_populates="reviews")
    analysis: Mapped[Optional["AnalyzedReview"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class AnalyzedReview(Base):
    __tablename__ = "analyzed_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    sentiment: Mapped[Optional[str]] = mapped_column(String(20))
    pain_point_category: Mapped[Optional[str]] = mapped_column(String(100))
    pain_point_thai: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[Optional[str]] = mapped_column(String(10))
    keywords: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    model_used: Mapped[Optional[str]] = mapped_column(String(50))

    review: Mapped["Review"] = relationship(back_populates="analysis")


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[Optional[str]] = mapped_column(String(20))
    places_count: Mapped[Optional[int]] = mapped_column(Integer)
    reviews_count: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[Optional[str]] = mapped_column(String(20))
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
