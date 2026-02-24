import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.item import WishlistItem
from app.models.user import User
from app.models.wishlist import Wishlist
from app.schemas.wishlist import (
    WishlistCreateRequest,
    WishlistDetailOwnerOut,
    WishlistItemCreateRequest,
    WishlistItemUpdateRequest,
    WishlistListOut,
    WishlistOut,
    WishlistUpdateRequest,
)
from app.services.realtime import realtime_manager
from app.services.wishlist_view import (
    build_owner_wishlist_detail,
    build_public_wishlist,
    build_wishlist_list_item,
    build_wishlist_out,
    generate_share_slug,
)

router = APIRouter(prefix="/wishlists", tags=["wishlists"])

settings = get_settings()


async def _load_owned_wishlist(
    db: AsyncSession,
    owner_id: uuid.UUID,
    wishlist_id: uuid.UUID,
    include_relations: bool = True,
) -> Wishlist:
    stmt = select(Wishlist).where(Wishlist.id == wishlist_id, Wishlist.owner_id == owner_id)
    stmt = stmt.execution_options(populate_existing=True)
    if include_relations:
        stmt = stmt.options(
            selectinload(Wishlist.items).selectinload(WishlistItem.reservations),
            selectinload(Wishlist.items).selectinload(WishlistItem.contributions),
        )

    wishlist = await db.scalar(stmt)
    if wishlist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вишлист не найден")
    return wishlist


async def _broadcast_public_snapshot(db: AsyncSession, wishlist_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as fresh_db:
        wishlist = await fresh_db.scalar(
            select(Wishlist)
            .where(Wishlist.id == wishlist_id)
            .options(
                selectinload(Wishlist.items).selectinload(WishlistItem.reservations),
                selectinload(Wishlist.items).selectinload(WishlistItem.contributions),
            )
        )
    if wishlist is None:
        return
    snapshot = build_public_wishlist(wishlist)
    await realtime_manager.broadcast(
        wishlist.share_slug,
        {"type": "wishlist.updated", "payload": snapshot.model_dump(mode="json")},
    )


@router.get("/mine", response_model=list[WishlistListOut])
async def list_my_wishlists(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WishlistListOut]:
    wishlists = (
        await db.scalars(
            select(Wishlist)
            .where(Wishlist.owner_id == current_user.id)
            .order_by(Wishlist.created_at.desc())
            .options(selectinload(Wishlist.items))
        )
    ).all()
    return [build_wishlist_list_item(wishlist) for wishlist in wishlists]


@router.post("", response_model=WishlistOut, status_code=status.HTTP_201_CREATED)
async def create_wishlist(
    payload: WishlistCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistOut:
    wishlist = Wishlist(
        owner_id=current_user.id,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        event_date=payload.event_date,
        share_slug=generate_share_slug(),
    )
    db.add(wishlist)
    await db.commit()
    await db.refresh(wishlist)
    return build_wishlist_out(wishlist)


@router.get("/{wishlist_id}", response_model=WishlistDetailOwnerOut)
async def get_wishlist(
    wishlist_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistDetailOwnerOut:
    try:
        parsed_id = uuid.UUID(wishlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор вишлиста") from exc

    wishlist = await _load_owned_wishlist(db, current_user.id, parsed_id, include_relations=True)
    return build_owner_wishlist_detail(wishlist)


@router.patch("/{wishlist_id}", response_model=WishlistOut)
async def update_wishlist(
    wishlist_id: str,
    payload: WishlistUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistOut:
    try:
        parsed_id = uuid.UUID(wishlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор вишлиста") from exc

    wishlist = await _load_owned_wishlist(db, current_user.id, parsed_id, include_relations=False)

    patch = payload.model_dump(exclude_unset=True)
    if "title" in patch:
        wishlist.title = str(patch["title"]).strip()
    if "description" in patch:
        description = patch["description"]
        wishlist.description = str(description).strip() if isinstance(description, str) and description.strip() else None
    if "event_date" in patch:
        wishlist.event_date = patch["event_date"]
    if "is_public" in patch:
        wishlist.is_public = bool(patch["is_public"])

    await db.commit()
    await db.refresh(wishlist)
    await _broadcast_public_snapshot(db, parsed_id)
    return build_wishlist_out(wishlist)


@router.delete("/{wishlist_id}")
async def delete_wishlist(
    wishlist_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    try:
        parsed_id = uuid.UUID(wishlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор вишлиста") from exc

    wishlist = await _load_owned_wishlist(db, current_user.id, parsed_id, include_relations=False)
    share_slug = wishlist.share_slug
    await db.delete(wishlist)
    await db.commit()

    await realtime_manager.broadcast(share_slug, {"type": "wishlist.deleted", "payload": {"share_slug": share_slug}})
    return {"status": "deleted"}


@router.post("/{wishlist_id}/items", response_model=WishlistDetailOwnerOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    wishlist_id: str,
    payload: WishlistItemCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistDetailOwnerOut:
    try:
        parsed_id = uuid.UUID(wishlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор вишлиста") from exc

    wishlist = await _load_owned_wishlist(db, current_user.id, parsed_id, include_relations=True)
    if payload.allow_group_funding and payload.price_cents is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для совместного сбора нужно указать целевую цену подарка",
        )

    item = WishlistItem(
        wishlist_id=wishlist.id,
        title=payload.title.strip(),
        product_url=str(payload.product_url) if payload.product_url else None,
        image_url=str(payload.image_url) if payload.image_url else None,
        note=payload.note.strip() if payload.note else None,
        price_cents=payload.price_cents,
        currency=payload.currency.upper(),
        allow_group_funding=payload.allow_group_funding,
        min_contribution_cents=payload.min_contribution_cents or settings.default_min_contribution_cents,
        sort_order=payload.sort_order,
    )
    db.add(item)
    await db.commit()

    refreshed = await _load_owned_wishlist(db, current_user.id, parsed_id, include_relations=True)
    await _broadcast_public_snapshot(db, parsed_id)
    return build_owner_wishlist_detail(refreshed)


@router.patch("/{wishlist_id}/items/{item_id}", response_model=WishlistDetailOwnerOut)
async def update_item(
    wishlist_id: str,
    item_id: str,
    payload: WishlistItemUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistDetailOwnerOut:
    try:
        parsed_wishlist_id = uuid.UUID(wishlist_id)
        parsed_item_id = uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор") from exc

    wishlist = await _load_owned_wishlist(db, current_user.id, parsed_wishlist_id, include_relations=True)
    item = next((candidate for candidate in wishlist.items if candidate.id == parsed_item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подарок не найден")

    patch = payload.model_dump(exclude_unset=True)

    if "title" in patch:
        item.title = str(patch["title"]).strip()
    if "product_url" in patch:
        product_url = patch["product_url"]
        item.product_url = str(product_url) if product_url else None
    if "image_url" in patch:
        image_url = patch["image_url"]
        item.image_url = str(image_url) if image_url else None
    if "note" in patch:
        note = patch["note"]
        item.note = str(note).strip() if isinstance(note, str) and note.strip() else None
    if "price_cents" in patch:
        item.price_cents = patch["price_cents"]
    if "currency" in patch:
        currency = patch["currency"]
        item.currency = str(currency).upper() if currency else item.currency
    if "allow_group_funding" in patch:
        item.allow_group_funding = bool(patch["allow_group_funding"])
    if "min_contribution_cents" in patch:
        item.min_contribution_cents = int(patch["min_contribution_cents"])
    if "sort_order" in patch:
        item.sort_order = int(patch["sort_order"])
    if "is_deleted" in patch:
        item.is_deleted = bool(patch["is_deleted"])

    if item.allow_group_funding and item.price_cents is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для совместного сбора нужно указать целевую цену подарка",
        )

    await db.commit()

    refreshed = await _load_owned_wishlist(db, current_user.id, parsed_wishlist_id, include_relations=True)
    await _broadcast_public_snapshot(db, parsed_wishlist_id)
    return build_owner_wishlist_detail(refreshed)


@router.delete("/{wishlist_id}/items/{item_id}", response_model=WishlistDetailOwnerOut)
async def delete_item(
    wishlist_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistDetailOwnerOut:
    try:
        parsed_wishlist_id = uuid.UUID(wishlist_id)
        parsed_item_id = uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор") from exc

    wishlist = await _load_owned_wishlist(db, current_user.id, parsed_wishlist_id, include_relations=True)
    item = next((candidate for candidate in wishlist.items if candidate.id == parsed_item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подарок не найден")

    item.is_deleted = True
    await db.commit()

    refreshed = await _load_owned_wishlist(db, current_user.id, parsed_wishlist_id, include_relations=True)
    await _broadcast_public_snapshot(db, parsed_wishlist_id)
    return build_owner_wishlist_detail(refreshed)

