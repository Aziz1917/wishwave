from datetime import date, datetime

from pydantic import BaseModel, Field, HttpUrl


class PublicItemOut(BaseModel):
    id: str
    title: str
    product_url: str | None
    image_url: str | None
    note: str | None
    price_cents: int | None
    currency: str
    allow_group_funding: bool
    can_contribute: bool
    min_contribution_cents: int
    is_deleted: bool
    is_reserved: bool
    reserved_count: int
    contributions_total_cents: int
    contributions_count: int
    recent_contributions_cents: list[int]
    remaining_cents: int | None
    funding_percent: int
    is_fully_funded: bool
    funding_deadline_passed: bool
    can_reserve_remaining: bool
    created_at: datetime
    updated_at: datetime


class PublicWishlistOut(BaseModel):
    id: str
    title: str
    description: str | None
    event_date: date | None
    share_slug: str
    viewer_is_owner: bool = False
    created_at: datetime
    updated_at: datetime
    items: list[PublicItemOut]


class ReserveRequest(BaseModel):
    name: str | None = Field(default=None, max_length=80)


class ReserveResponse(BaseModel):
    reservation_id: str
    release_token: str
    item_id: str


class ReleaseReservationRequest(BaseModel):
    reservation_id: str
    release_token: str = Field(min_length=8, max_length=255)


class ContributeRequest(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    amount_cents: int = Field(ge=1)
    message: str | None = Field(default=None, max_length=200)


class ContributeResponse(BaseModel):
    contribution_id: str
    item_id: str
    amount_cents: int


class MetadataExtractRequest(BaseModel):
    url: HttpUrl


class MetadataExtractResponse(BaseModel):
    source_url: str
    title: str | None
    image_url: str | None
    price_cents: int | None
    currency: str | None
