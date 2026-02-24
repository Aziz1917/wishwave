from datetime import date, datetime

from pydantic import BaseModel, Field, HttpUrl


class WishlistCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    event_date: date | None = None


class WishlistUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    event_date: date | None = None
    is_public: bool | None = None


class WishlistItemCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    product_url: HttpUrl | None = None
    image_url: HttpUrl | None = None
    note: str | None = Field(default=None, max_length=4000)
    price_cents: int | None = Field(default=None, ge=1)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    allow_group_funding: bool = False
    min_contribution_cents: int | None = Field(default=None, ge=1)
    sort_order: int = 0


class WishlistItemUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    product_url: HttpUrl | None = None
    image_url: HttpUrl | None = None
    note: str | None = Field(default=None, max_length=4000)
    price_cents: int | None = Field(default=None, ge=1)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    allow_group_funding: bool | None = None
    min_contribution_cents: int | None = Field(default=None, ge=1)
    sort_order: int | None = None
    is_deleted: bool | None = None


class OwnerItemStats(BaseModel):
    reserved_count: int
    contributions_count: int
    contributions_total_cents: int


class OwnerWishlistItemOut(BaseModel):
    id: str
    title: str
    product_url: str | None
    image_url: str | None
    note: str | None
    price_cents: int | None
    currency: str
    allow_group_funding: bool
    min_contribution_cents: int
    sort_order: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    stats: OwnerItemStats


class WishlistOut(BaseModel):
    id: str
    title: str
    description: str | None
    event_date: date | None
    share_slug: str
    is_public: bool
    created_at: datetime
    updated_at: datetime


class WishlistListOut(WishlistOut):
    item_count: int


class WishlistDetailOwnerOut(WishlistOut):
    items: list[OwnerWishlistItemOut]

