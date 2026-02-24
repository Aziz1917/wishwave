import json
import secrets
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_optional_user
from app.core.security import hash_password, verify_password
from app.db.session import AsyncSessionLocal
from app.models.contribution import Contribution
from app.models.item import WishlistItem
from app.models.reservation import Reservation
from app.models.user import User
from app.models.wishlist import Wishlist
from app.schemas.public import (
    ContributeRequest,
    ContributeResponse,
    PublicWishlistOut,
    ReleaseReservationRequest,
    ReserveRequest,
    ReserveResponse,
)
from app.services.realtime import realtime_manager
from app.services.wishlist_view import build_public_wishlist

router = APIRouter(prefix="/public", tags=["public"])


def _format_cents_for_detail(amount_cents: int, currency: str) -> str:
    amount = amount_cents / 100
    pretty = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{pretty} {currency.upper()}"


def _funding_deadline_passed(event_date: date | None) -> bool:
    return bool(event_date and date.today() > event_date)


async def _load_public_wishlist(db: AsyncSession, share_slug: str) -> Wishlist:
    wishlist = await db.scalar(
        select(Wishlist)
        .where(Wishlist.share_slug == share_slug, Wishlist.is_public.is_(True))
        .options(
            selectinload(Wishlist.items).selectinload(WishlistItem.reservations),
            selectinload(Wishlist.items).selectinload(WishlistItem.contributions),
        )
    )
    if wishlist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вишлист не найден")
    return wishlist


async def _broadcast_snapshot(share_slug: str) -> None:
    async with AsyncSessionLocal() as fresh_db:
        wishlist = await _load_public_wishlist(fresh_db, share_slug)
    snapshot = build_public_wishlist(wishlist)
    await realtime_manager.broadcast(
        share_slug,
        {"type": "wishlist.updated", "payload": snapshot.model_dump(mode="json")},
    )


@router.get("/w/{share_slug}", response_model=PublicWishlistOut)
async def get_public_wishlist(
    share_slug: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> PublicWishlistOut:
    wishlist = await _load_public_wishlist(db, share_slug)
    payload = build_public_wishlist(wishlist)
    return payload.model_copy(update={"viewer_is_owner": bool(user and user.id == wishlist.owner_id)})


@router.post("/w/{share_slug}/items/{item_id}/reserve", response_model=ReserveResponse)
async def reserve_item(
    share_slug: str,
    item_id: str,
    payload: ReserveRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> ReserveResponse:
    wishlist = await _load_public_wishlist(db, share_slug)
    if user and user.id == wishlist.owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Владелец не может бронировать подарки в своём вишлисте")

    try:
        parsed_item_id = uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор подарка") from exc

    item = next((candidate for candidate in wishlist.items if candidate.id == parsed_item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подарок не найден")
    if item.is_deleted:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Подарок недоступен")
    contribution_total = sum(contribution.amount_cents for contribution in item.contributions)
    deadline_passed = _funding_deadline_passed(wishlist.event_date)
    allow_reserve_remaining = bool(item.price_cents is not None and deadline_passed and contribution_total < item.price_cents)
    if len(item.contributions) > 0 and not allow_reserve_remaining:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="По этому подарку уже есть взносы")
    if item.price_cents is not None and contribution_total >= item.price_cents:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Цель сбора уже достигнута")

    if any(reservation.is_active for reservation in item.reservations):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Подарок уже зарезервирован")

    release_token = secrets.token_urlsafe(24)
    reservation = Reservation(
        item_id=item.id,
        reserver_name=(payload.name or "").strip() or "Гость",
        reserver_user_id=user.id if user else None,
        release_token_hash=hash_password(release_token),
        is_active=True,
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation)

    await _broadcast_snapshot(share_slug)
    return ReserveResponse(reservation_id=str(reservation.id), release_token=release_token, item_id=str(item.id))


@router.post("/w/{share_slug}/items/{item_id}/release")
async def release_reservation(
    share_slug: str,
    item_id: str,
    payload: ReleaseReservationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    wishlist = await _load_public_wishlist(db, share_slug)

    try:
        parsed_item_id = uuid.UUID(item_id)
        parsed_reservation_id = uuid.UUID(payload.reservation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор") from exc

    item = next((candidate for candidate in wishlist.items if candidate.id == parsed_item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подарок не найден")

    reservation = next((candidate for candidate in item.reservations if candidate.id == parsed_reservation_id), None)
    if reservation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Бронь не найдена")
    if not reservation.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Бронь уже снята")
    if not verify_password(payload.release_token, reservation.release_token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Некорректный токен снятия брони")

    reservation.is_active = False
    await db.commit()
    await _broadcast_snapshot(share_slug)
    return {"status": "released"}


@router.post("/w/{share_slug}/items/{item_id}/contribute", response_model=ContributeResponse)
async def contribute(
    share_slug: str,
    item_id: str,
    payload: ContributeRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> ContributeResponse:
    wishlist = await _load_public_wishlist(db, share_slug)
    if user and user.id == wishlist.owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Владелец не может скидываться в свой вишлист")

    try:
        parsed_item_id = uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор подарка") from exc

    item = next((candidate for candidate in wishlist.items if candidate.id == parsed_item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подарок не найден")
    if item.is_deleted:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Подарок недоступен")
    if not item.allow_group_funding:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для этого подарка совместный сбор отключён")
    if item.price_cents is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="У подарка не задана целевая сумма")
    if any(reservation.is_active for reservation in item.reservations):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Подарок уже зарезервирован")
    if payload.amount_cents < item.min_contribution_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Минимальный взнос: {_format_cents_for_detail(item.min_contribution_cents, item.currency)}",
        )

    total = sum(contribution.amount_cents for contribution in item.contributions)
    remaining = item.price_cents - total
    if remaining <= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Цель сбора уже достигнута")
    if _funding_deadline_passed(wishlist.event_date):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сбор закрыт после даты события. Остаток можно закрыть только бронью.",
        )
    if payload.amount_cents > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Максимально доступный взнос: {_format_cents_for_detail(remaining, item.currency)}",
        )

    contribution = Contribution(
        item_id=item.id,
        contributor_name=(payload.name or "").strip() or "Гость",
        contributor_user_id=user.id if user else None,
        amount_cents=payload.amount_cents,
        message=(payload.message or "").strip() or None,
    )
    db.add(contribution)
    await db.commit()
    await db.refresh(contribution)

    await _broadcast_snapshot(share_slug)
    return ContributeResponse(
        contribution_id=str(contribution.id),
        item_id=str(item.id),
        amount_cents=contribution.amount_cents,
    )


@router.websocket("/ws/{share_slug}")
async def wishlist_ws(websocket: WebSocket, share_slug: str) -> None:
    await realtime_manager.connect(share_slug, websocket)
    try:
        async with AsyncSessionLocal() as db:
            try:
                snapshot = build_public_wishlist(await _load_public_wishlist(db, share_slug))
                await websocket.send_text(json.dumps({"type": "snapshot", "payload": snapshot.model_dump(mode="json")}))
            except HTTPException:
                await websocket.send_text(json.dumps({"type": "error", "payload": "Вишлист не найден"}))
                await websocket.close(code=4404)
                return

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_manager.disconnect(share_slug, websocket)

