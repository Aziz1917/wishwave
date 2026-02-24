"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ApiError, contributeGift, getPublicWishlist, releaseGift, reserveGift, wishlistSocketUrl } from "@/lib/api";
import { getReservationStoreKey } from "@/lib/auth";
import { clampPercent, formatDate, formatMoney } from "@/lib/format";
import { PublicWishlist, ReservationToken } from "@/lib/types";

type ReservationMap = Record<string, ReservationToken>;

function readReservationMap(slug: string): ReservationMap {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(getReservationStoreKey(slug));
    if (!raw) {
      return {};
    }
    return JSON.parse(raw) as ReservationMap;
  } catch {
    return {};
  }
}

function writeReservationMap(slug: string, value: ReservationMap): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(getReservationStoreKey(slug), JSON.stringify(value));
}

function storeHost(rawUrl: string): string {
  try {
    const host = new URL(rawUrl).hostname.replace(/^www\./, "");
    return host || "магазин";
  } catch {
    return "магазин";
  }
}

function centsToInputAmount(amountCents: number): string {
  const amount = amountCents / 100;
  if (Number.isInteger(amount)) {
    return String(amount);
  }
  return amount.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export default function PublicWishlistPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;

  const [wishlist, setWishlist] = useState<PublicWishlist | null>(null);
  const [reservations, setReservations] = useState<ReservationMap>({});
  const [loading, setLoading] = useState(true);
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [friendName, setFriendName] = useState("");
  const [contributionInputs, setContributionInputs] = useState<Record<string, string>>({});

  const hasItems = useMemo(() => (wishlist?.items.length ?? 0) > 0, [wishlist]);
  const viewerIsOwner = wishlist?.viewer_is_owner ?? false;

  useEffect(() => {
    setReservations(readReservationMap(slug));

    async function loadInitial() {
      try {
        const data = await getPublicWishlist(slug);
        setWishlist(data);
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.detail : "Не удалось загрузить вишлист");
      } finally {
        setLoading(false);
      }
    }

    void loadInitial();
  }, [slug]);

  useEffect(() => {
    if (!slug) {
      return;
    }

    const socket = new WebSocket(wishlistSocketUrl(slug));
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          type: string;
          payload?: PublicWishlist | { share_slug: string };
        };
        if (payload.type === "wishlist.updated" || payload.type === "snapshot") {
          const snapshot = payload.payload as PublicWishlist | undefined;
          if (snapshot) {
            setWishlist((previous) => ({
              ...snapshot,
              viewer_is_owner: previous?.viewer_is_owner ?? snapshot.viewer_is_owner ?? false,
            }));
            setError(null);
          }
        } else if (payload.type === "wishlist.deleted") {
          setWishlist(null);
          setError("Владелец удалил этот вишлист");
        }
      } catch {
        // ignore malformed messages
      }
    };

    return () => {
      socket.close();
    };
  }, [slug]);

  async function reserveItem(itemId: string) {
    setBusyItemId(itemId);
    setError(null);
    try {
      const reserved = await reserveGift(slug, itemId, { name: friendName.trim() || undefined });
      const nextReservations = {
        ...reservations,
        [itemId]: {
          reservationId: reserved.reservation_id,
          releaseToken: reserved.release_token,
        },
      };
      setReservations(nextReservations);
      writeReservationMap(slug, nextReservations);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось забронировать подарок");
    } finally {
      setBusyItemId(null);
    }
  }

  async function cancelReservation(itemId: string) {
    const reservation = reservations[itemId];
    if (!reservation) {
      return;
    }
    setBusyItemId(itemId);
    setError(null);
    try {
      await releaseGift(slug, itemId, {
        reservation_id: reservation.reservationId,
        release_token: reservation.releaseToken,
      });
      const nextReservations = { ...reservations };
      delete nextReservations[itemId];
      setReservations(nextReservations);
      writeReservationMap(slug, nextReservations);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось снять бронь");
    } finally {
      setBusyItemId(null);
    }
  }

  async function contribute(itemId: string) {
    const raw = contributionInputs[itemId] ?? "";
    const amount = Number.parseFloat(raw.replace(",", "."));
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Введите корректную сумму взноса");
      return;
    }

    setBusyItemId(itemId);
    setError(null);
    try {
      await contributeGift(slug, itemId, {
        name: friendName.trim() || undefined,
        amount_cents: Math.round(amount * 100),
      });
      setContributionInputs((prev) => ({ ...prev, [itemId]: "" }));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось отправить взнос");
    } finally {
      setBusyItemId(null);
    }
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1080px] px-4 py-6 sm:px-8 sm:py-8">
      <header className="mb-5 flex items-center justify-between">
        <Link className="display text-4xl font-bold" href="/">
          Wishwave
        </Link>
      </header>

      {loading ? <p className="text-sm text-[var(--muted)]">Загрузка вишлиста...</p> : null}

      {wishlist ? (
        <section className="surface relative overflow-hidden rounded-[22px] px-5 py-6 sm:px-7">
          <div className="pointer-events-none absolute -top-16 right-[-34px] h-[180px] w-[180px] rounded-full bg-[radial-gradient(circle,_rgba(217,93,57,0.2)_0%,_rgba(217,93,57,0)_70%)]" />
          <div className="relative">
            <h1 className="display text-5xl font-bold leading-[0.88] sm:text-6xl">{wishlist.title}</h1>
            <p className="mt-2 text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">{formatDate(wishlist.event_date)}</p>
            {wishlist.description ? <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[var(--muted)]">{wishlist.description}</p> : null}

            {!viewerIsOwner ? (
              <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                <div>
                  <label className="label">Ваше имя (необязательно)</label>
                  <input
                    className="input"
                    onChange={(event) => setFriendName(event.target.value)}
                    placeholder="Алекс"
                    value={friendName}
                  />
                </div>
                <div className="text-xs leading-relaxed text-[var(--muted)]">Владелец не увидит, кто бронировал и кто скидывался.</div>
              </div>
            ) : (
              <p className="mt-5 text-xs leading-relaxed text-[var(--muted)]">
                Вы владелец этого списка. Управление резервами и взносами доступно только гостям.
              </p>
            )}
          </div>
        </section>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-[10px] border border-[#efc8bd] bg-[#fff2ee] px-3 py-2 text-sm text-[var(--danger)]">{error}</p>
      ) : null}

      {!loading && wishlist && !hasItems ? (
        <section className="surface mt-4 rounded-[16px] border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
          Этот вишлист пока пуст.
        </section>
      ) : null}

      <section className="mt-4 grid gap-4">
        {wishlist?.items.map((item) => {
          const myReservation = reservations[item.id];
          const isBusy = busyItemId === item.id;
          const hasFundingTarget = item.allow_group_funding && item.price_cents !== null;
          const fundingShortfall = item.funding_deadline_passed && !item.is_fully_funded;
          const reserveDisabled = item.is_deleted || item.is_reserved || (item.contributions_count > 0 && !item.can_reserve_remaining);
          const canReserveGift = !reserveDisabled;
          const contributionDisabled = !item.can_contribute || item.is_deleted || item.is_fully_funded || item.is_reserved || isBusy;
          const contributionValue = contributionInputs[item.id] ?? "";
          const remainingCents = item.remaining_cents ?? 0;
          const quickAmountsCents = remainingCents >= 100000 ? [100000, 500000].filter((amount) => amount <= remainingCents) : [];

          return (
            <article className="surface rounded-[16px] p-4 sm:p-5" key={item.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="display text-4xl font-bold leading-[0.9]">{item.title}</h2>
                  <p className="mt-1 text-sm text-[var(--muted)]">{formatMoney(item.price_cents, item.currency)}</p>
                </div>
                <div className="flex gap-2">
                  {item.is_deleted ? <span className="pill bg-[#f0e3dd] text-[#7b5042]">Архив владельца</span> : null}
                  {hasFundingTarget ? <span className="pill bg-[#ece7d9] text-[#5c544a]">Совместный сбор</span> : null}
                  <span className={`pill ${item.is_reserved ? "bg-[#f0e6cf] text-[#866127]" : "bg-[#e4eee7] text-[#276448]"}`}>
                    {item.is_reserved ? "Забронировано" : "Свободно"}
                  </span>
                </div>
              </div>

              {item.image_url ? (
                <div className="mt-4 overflow-hidden bg-[#f3f0e9]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    alt={item.title}
                    className="mx-auto h-auto max-h-[420px] w-full object-contain sm:max-h-[520px]"
                    loading="lazy"
                    src={item.image_url}
                  />
                </div>
              ) : null}

              {item.note ? <p className="mt-3 text-sm leading-relaxed text-[var(--muted)]">{item.note}</p> : null}

              {item.product_url ? (
                <a
                  className="mt-4 inline-flex w-fit items-center gap-2 border-b border-[var(--text)] pb-0.5 text-sm font-semibold transition-opacity hover:opacity-70"
                  href={item.product_url}
                  rel="noreferrer"
                  target="_blank"
                >
                  Смотреть в {storeHost(item.product_url)}
                  <span aria-hidden="true">↗</span>
                </a>
              ) : null}

              {!viewerIsOwner ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {!myReservation ? (
                    <button
                      className="btn-primary text-sm"
                      disabled={!canReserveGift || isBusy}
                      onClick={() => reserveItem(item.id)}
                      type="button"
                    >
                      {isBusy
                        ? "Резервирую..."
                        : canReserveGift
                          ? item.can_reserve_remaining
                            ? "Забронировать остаток"
                            : "Забронировать подарок"
                          : item.is_reserved
                            ? "Уже зарезервировано"
                            : fundingShortfall
                              ? "Сбор закрыт"
                              : "Сбор уже начат"}
                    </button>
                  ) : (
                    <button className="btn-ghost text-sm" disabled={isBusy} onClick={() => cancelReservation(item.id)} type="button">
                      {isBusy ? "Отменяю..." : "Отменить мою бронь"}
                    </button>
                  )}
                </div>
              ) : null}

              {hasFundingTarget ? (
                <div className="mt-4 space-y-3">
                  <div>
                    <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--muted)]">
                      <span>Собрано {formatMoney(item.contributions_total_cents, item.currency)}</span>
                      <span>{clampPercent(item.funding_percent)}%</span>
                    </div>
                    <div className="progress-wrap">
                      <div className="progress-bar" style={{ width: `${clampPercent(item.funding_percent)}%` }} />
                    </div>
                    <p className="mt-2 text-xs text-[var(--muted)]">Осталось собрать: {formatMoney(remainingCents, item.currency)}.</p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold text-[var(--muted)]">{item.contributions_count} взносов</span>
                    {item.recent_contributions_cents.map((amount, index) => (
                      <span className="pill bg-[#ece7d9] text-[#5c544a]" key={`${item.id}-contribution-${index}`}>
                        +{formatMoney(amount, item.currency)}
                      </span>
                    ))}
                  </div>

                  <p className="text-xs text-[var(--muted)]">Минимальный взнос: {formatMoney(item.min_contribution_cents, item.currency)}.</p>

                  {fundingShortfall ? (
                    <p className="rounded-[10px] border border-[#eddabf] bg-[#fff5e7] px-3 py-2 text-xs text-[#855f2a]">
                      Дата события прошла, цель не достигнута. Совместный сбор закрыт, но один из друзей может забронировать
                      остаток ({formatMoney(remainingCents, item.currency)}) и закрыть покупку вручную.
                    </p>
                  ) : null}

                  {!viewerIsOwner && item.can_contribute && remainingCents > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {quickAmountsCents.map((amount) => (
                        <button
                          className="btn-ghost text-xs"
                          disabled={contributionDisabled}
                          key={`${item.id}-quick-${amount}`}
                          onClick={() =>
                            setContributionInputs((prev) => ({
                              ...prev,
                              [item.id]: centsToInputAmount(amount),
                            }))
                          }
                          type="button"
                        >
                          {formatMoney(amount, item.currency)}
                        </button>
                      ))}
                      <button
                        className="btn-ghost text-xs"
                        disabled={contributionDisabled}
                        onClick={() =>
                          setContributionInputs((prev) => ({
                            ...prev,
                            [item.id]: centsToInputAmount(remainingCents),
                          }))
                        }
                        type="button"
                      >
                        Добить остаток
                      </button>
                    </div>
                  ) : null}

                  {!viewerIsOwner && item.can_contribute ? (
                    <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                      <input
                        className="input"
                        disabled={contributionDisabled}
                        inputMode="decimal"
                        onChange={(event) =>
                          setContributionInputs((prev) => ({
                            ...prev,
                            [item.id]: event.target.value,
                          }))
                        }
                        placeholder="Сумма взноса"
                        value={contributionValue}
                      />
                      <button
                        className="btn-primary text-sm"
                        disabled={contributionDisabled}
                        onClick={() => contribute(item.id)}
                        type="button"
                      >
                        {isBusy ? "Отправляю..." : item.is_reserved ? "Зарезервировано" : item.is_fully_funded ? "Собрано" : "Скинуться"}
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </section>
    </main>
  );
}
