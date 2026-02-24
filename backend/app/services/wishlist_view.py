import secrets
from datetime import date

from app.models.item import WishlistItem
from app.models.wishlist import Wishlist
from app.schemas.public import PublicItemOut, PublicWishlistOut
from app.schemas.wishlist import OwnerItemStats, OwnerWishlistItemOut, WishlistDetailOwnerOut, WishlistListOut, WishlistOut


def generate_share_slug() -> str:
    return secrets.token_urlsafe(10).replace("_", "a").replace("-", "b")


def build_owner_item(item: WishlistItem) -> OwnerWishlistItemOut:
    active_reservations = [reservation for reservation in item.reservations if reservation.is_active]
    contribution_total = sum(contribution.amount_cents for contribution in item.contributions)
    stats = OwnerItemStats(
        reserved_count=len(active_reservations),
        contributions_count=len(item.contributions),
        contributions_total_cents=contribution_total,
    )
    return OwnerWishlistItemOut(
        id=str(item.id),
        title=item.title,
        product_url=item.product_url,
        image_url=item.image_url,
        note=item.note,
        price_cents=item.price_cents,
        currency=item.currency,
        allow_group_funding=item.allow_group_funding,
        min_contribution_cents=item.min_contribution_cents,
        sort_order=item.sort_order,
        is_deleted=item.is_deleted,
        created_at=item.created_at,
        updated_at=item.updated_at,
        stats=stats,
    )


def build_owner_wishlist_detail(wishlist: Wishlist) -> WishlistDetailOwnerOut:
    sorted_items = sorted(wishlist.items, key=lambda item: (item.sort_order, item.created_at))
    return WishlistDetailOwnerOut(
        id=str(wishlist.id),
        title=wishlist.title,
        description=wishlist.description,
        event_date=wishlist.event_date,
        share_slug=wishlist.share_slug,
        is_public=wishlist.is_public,
        created_at=wishlist.created_at,
        updated_at=wishlist.updated_at,
        items=[build_owner_item(item) for item in sorted_items],
    )


def build_wishlist_list_item(wishlist: Wishlist) -> WishlistListOut:
    visible_items = [item for item in wishlist.items if not item.is_deleted]
    return WishlistListOut(
        id=str(wishlist.id),
        title=wishlist.title,
        description=wishlist.description,
        event_date=wishlist.event_date,
        share_slug=wishlist.share_slug,
        is_public=wishlist.is_public,
        created_at=wishlist.created_at,
        updated_at=wishlist.updated_at,
        item_count=len(visible_items),
    )


def build_wishlist_out(wishlist: Wishlist) -> WishlistOut:
    return WishlistOut(
        id=str(wishlist.id),
        title=wishlist.title,
        description=wishlist.description,
        event_date=wishlist.event_date,
        share_slug=wishlist.share_slug,
        is_public=wishlist.is_public,
        created_at=wishlist.created_at,
        updated_at=wishlist.updated_at,
    )


def build_public_item(item: WishlistItem, event_date: date | None) -> PublicItemOut | None:
    active_reservations = [reservation for reservation in item.reservations if reservation.is_active]
    contributions_total = sum(contribution.amount_cents for contribution in item.contributions)
    recent_contributions = sorted(item.contributions, key=lambda contribution: contribution.created_at, reverse=True)[:8]
    has_activity = len(active_reservations) > 0 or contributions_total > 0

    # Deleted items stay visible only when there is already a reservation/contribution.
    if item.is_deleted and not has_activity:
        return None

    price_cents = item.price_cents
    remaining_cents = None
    funding_percent = 0
    is_fully_funded = False
    funding_deadline_passed = bool(event_date and date.today() > event_date)
    can_reserve_remaining = False

    if price_cents is not None:
        remaining_cents = max(price_cents - contributions_total, 0)
        if price_cents > 0:
            funding_percent = min(int((contributions_total / price_cents) * 100), 100)
        is_fully_funded = contributions_total >= price_cents
        can_reserve_remaining = (
            funding_deadline_passed and contributions_total > 0 and not is_fully_funded and not item.is_deleted and len(active_reservations) == 0
        )

    return PublicItemOut(
        id=str(item.id),
        title=item.title,
        product_url=item.product_url,
        image_url=item.image_url,
        note=item.note,
        price_cents=item.price_cents,
        currency=item.currency,
        allow_group_funding=item.allow_group_funding,
        can_contribute=item.allow_group_funding and item.price_cents is not None and not (funding_deadline_passed and not is_fully_funded),
        min_contribution_cents=item.min_contribution_cents,
        is_deleted=item.is_deleted,
        is_reserved=len(active_reservations) > 0,
        reserved_count=len(active_reservations),
        contributions_total_cents=contributions_total,
        contributions_count=len(item.contributions),
        recent_contributions_cents=[contribution.amount_cents for contribution in recent_contributions],
        remaining_cents=remaining_cents,
        funding_percent=funding_percent,
        is_fully_funded=is_fully_funded,
        funding_deadline_passed=funding_deadline_passed,
        can_reserve_remaining=can_reserve_remaining,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def build_public_wishlist(wishlist: Wishlist) -> PublicWishlistOut:
    sorted_items = sorted(wishlist.items, key=lambda item: (item.sort_order, item.created_at))
    public_items = [built for built in (build_public_item(item, wishlist.event_date) for item in sorted_items) if built is not None]
    return PublicWishlistOut(
        id=str(wishlist.id),
        title=wishlist.title,
        description=wishlist.description,
        event_date=wishlist.event_date,
        share_slug=wishlist.share_slug,
        created_at=wishlist.created_at,
        updated_at=wishlist.updated_at,
        items=public_items,
    )
