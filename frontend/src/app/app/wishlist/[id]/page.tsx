"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { ApiError, createItem, deleteWishlist, extractByUrl, getWishlist, updateItem, updateWishlist } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { formatDate, formatMoney, toDateInput } from "@/lib/format";
import { OwnerWishlist, OwnerWishlistItem } from "@/lib/types";

function parseIntOrUndefined(raw: string): number | undefined {
  if (!raw.trim()) {
    return undefined;
  }
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parsePriceToCents(raw: string): number | undefined {
  if (!raw.trim()) {
    return undefined;
  }
  const normalized = raw.replace(",", ".").trim();
  const parsed = Number.parseFloat(normalized);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return undefined;
  }
  return Math.round(parsed * 100);
}

type ItemEditorProps = {
  item: OwnerWishlistItem;
  token: string;
  wishlistId: string;
  onUpdated: (wishlist: OwnerWishlist) => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
};

function ItemEditor({ item, token, wishlistId, onUpdated, onError, onNotice }: ItemEditorProps) {
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [productUrl, setProductUrl] = useState(item.product_url ?? "");
  const [imageUrl, setImageUrl] = useState(item.image_url ?? "");
  const [note, setNote] = useState(item.note ?? "");
  const [price, setPrice] = useState(item.price_cents ? String(item.price_cents / 100) : "");
  const [currency, setCurrency] = useState(item.currency);
  const [allowGroupFunding, setAllowGroupFunding] = useState(item.allow_group_funding);
  const [minContribution, setMinContribution] = useState(String(item.min_contribution_cents));
  const [isDeleted, setIsDeleted] = useState(item.is_deleted);

  useEffect(() => {
    setTitle(item.title);
    setProductUrl(item.product_url ?? "");
    setImageUrl(item.image_url ?? "");
    setNote(item.note ?? "");
    setPrice(item.price_cents ? String(item.price_cents / 100) : "");
    setCurrency(item.currency);
    setAllowGroupFunding(item.allow_group_funding);
    setMinContribution(String(item.min_contribution_cents));
    setIsDeleted(item.is_deleted);
  }, [item]);

  async function saveChanges(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    onError("");
    try {
      const updated = await updateItem(token, wishlistId, item.id, {
        title: title.trim(),
        product_url: productUrl.trim() ? productUrl.trim() : null,
        image_url: imageUrl.trim() ? imageUrl.trim() : null,
        note: note.trim() ? note.trim() : null,
        price_cents: parsePriceToCents(price) ?? null,
        currency: currency.trim().toUpperCase(),
        allow_group_funding: allowGroupFunding,
        min_contribution_cents: parseIntOrUndefined(minContribution),
        is_deleted: isDeleted,
      });
      onUpdated(updated);
      onNotice("Подарок обновлён");
    } catch (caught) {
      onError(caught instanceof ApiError ? caught.detail : "Не удалось обновить подарок");
    } finally {
      setSaving(false);
    }
  }

  async function toggleArchive() {
    setSaving(true);
    onError("");
    try {
      const nextArchived = !isDeleted;
      const updated = await updateItem(token, wishlistId, item.id, {
        is_deleted: nextArchived,
      });
      onUpdated(updated);
      onNotice(nextArchived ? "Подарок в архиве" : "Подарок возвращён из архива");
    } catch (caught) {
      onError(caught instanceof ApiError ? caught.detail : "Не удалось изменить статус архива");
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="surface rounded-[14px] p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="display text-3xl font-bold leading-[0.95]">{item.title}</p>
          <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">
            Броней: {item.stats.reserved_count} | Взносов: {item.stats.contributions_count} | Собрано:{" "}
            {formatMoney(item.stats.contributions_total_cents, item.currency)}
          </p>
        </div>
        <span className={`pill ${item.is_deleted ? "bg-[#f0e3dd] text-[#7b5042]" : "bg-[#e4eee7] text-[#276448]"}`}>
          {item.is_deleted ? "В архиве" : "Активен"}
        </span>
      </div>

      <form className="grid gap-3" onSubmit={saveChanges}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label">Название</label>
            <input className="input" minLength={2} onChange={(event) => setTitle(event.target.value)} required value={title} />
          </div>
          <div>
            <label className="label">Цена</label>
            <input
              className="input"
              inputMode="decimal"
              onChange={(event) => setPrice(event.target.value)}
              placeholder="1000,00"
              value={price}
            />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label">Ссылка на товар</label>
            <input className="input" onChange={(event) => setProductUrl(event.target.value)} value={productUrl} />
          </div>
          <div>
            <label className="label">Ссылка на картинку</label>
            <input className="input" onChange={(event) => setImageUrl(event.target.value)} value={imageUrl} />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="label">Валюта</label>
            <input
              className="input uppercase"
              maxLength={3}
              onChange={(event) => setCurrency(event.target.value)}
              value={currency}
            />
          </div>
          <div>
            <label className="label">Мин. взнос (в копейках)</label>
            <input className="input" onChange={(event) => setMinContribution(event.target.value)} value={minContribution} />
          </div>
          <div className="flex items-end gap-2">
            <label className="inline-flex items-center gap-2 text-sm font-semibold">
              <input checked={allowGroupFunding} onChange={(event) => setAllowGroupFunding(event.target.checked)} type="checkbox" />
              Совместный сбор
            </label>
            <label className="inline-flex items-center gap-2 text-sm font-semibold">
              <input checked={isDeleted} onChange={(event) => setIsDeleted(event.target.checked)} type="checkbox" />
              Архив
            </label>
          </div>
        </div>

        <div>
          <label className="label">Комментарий</label>
          <textarea className="input min-h-20 resize-y" onChange={(event) => setNote(event.target.value)} value={note} />
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          <button className="btn-primary text-sm" disabled={saving} type="submit">
            {saving ? "Сохраняю..." : "Сохранить"}
          </button>
          <button className="btn-ghost text-sm" disabled={saving} onClick={toggleArchive} type="button">
            {isDeleted ? "Из архива" : "В архив"}
          </button>
        </div>
      </form>
    </article>
  );
}

export default function WishlistEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [wishlist, setWishlist] = useState<OwnerWishlist | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingMeta, setSavingMeta] = useState(false);
  const [creatingItem, setCreatingItem] = useState(false);
  const [autofilling, setAutofilling] = useState(false);
  const [deletingWishlist, setDeletingWishlist] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [isPublic, setIsPublic] = useState(true);

  const [itemTitle, setItemTitle] = useState("");
  const [itemProductUrl, setItemProductUrl] = useState("");
  const [itemImageUrl, setItemImageUrl] = useState("");
  const [itemNote, setItemNote] = useState("");
  const [itemPrice, setItemPrice] = useState("");
  const [itemCurrency, setItemCurrency] = useState("RUB");
  const [itemGroupFunding, setItemGroupFunding] = useState(false);
  const [itemMinContribution, setItemMinContribution] = useState("100");

  const token = useMemo(() => getAuthToken(), []);
  const wishlistId = params.id;

  function showNotice(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2500);
  }

  useEffect(() => {
    if (!token) {
      router.replace("/auth");
      return;
    }
    const sessionToken = token;

    async function run() {
      try {
        const loaded = await getWishlist(sessionToken, wishlistId);
        setWishlist(loaded);
        setTitle(loaded.title);
        setDescription(loaded.description ?? "");
        setEventDate(toDateInput(loaded.event_date));
        setIsPublic(loaded.is_public);
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 401) {
          router.replace("/auth");
          return;
        }
        setError(caught instanceof ApiError ? caught.detail : "Не удалось загрузить вишлист");
      } finally {
        setLoading(false);
      }
    }

    void run();
  }, [router, token, wishlistId]);

  async function saveWishlistMeta(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !wishlist) {
      return;
    }
    setSavingMeta(true);
    setError(null);
    try {
      await updateWishlist(token, wishlist.id, {
        title: title.trim(),
        description: description.trim() ? description.trim() : null,
        event_date: eventDate || null,
        is_public: isPublic,
      });
      const loaded = await getWishlist(token, wishlist.id);
      setWishlist(loaded);
      showNotice("Настройки вишлиста сохранены");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось сохранить вишлист");
    } finally {
      setSavingMeta(false);
    }
  }

  async function autoFillByUrl() {
    if (!token || !itemProductUrl.trim()) {
      return;
    }
    setAutofilling(true);
    setError(null);
    try {
      const extracted = await extractByUrl(token, itemProductUrl.trim());
      const hasTitle = Boolean(extracted.title);
      const hasImage = Boolean(extracted.image_url);
      const hasPrice = extracted.price_cents !== null;
      const hasCurrency = Boolean(extracted.currency);

      if (extracted.title) {
        setItemTitle(extracted.title);
      }
      if (extracted.image_url) {
        setItemImageUrl(extracted.image_url);
      }
      if (extracted.price_cents !== null) {
        setItemPrice(String(extracted.price_cents / 100));
      }
      if (extracted.currency) {
        setItemCurrency(extracted.currency.toUpperCase());
      }
      if (hasTitle && hasImage && hasPrice) {
        showNotice("Автозаполнение завершено: название, фото и цена загружены");
      } else if (hasTitle || hasImage || hasPrice || hasCurrency) {
        showNotice("Автозаполнение загрузило только часть данных. Проверьте поля.");
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось выполнить автозаполнение по ссылке");
    } finally {
      setAutofilling(false);
    }
  }

  async function addItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !wishlist) {
      return;
    }
    setCreatingItem(true);
    setError(null);
    try {
      const updated = await createItem(token, wishlist.id, {
        title: itemTitle.trim(),
        product_url: itemProductUrl.trim() || undefined,
        image_url: itemImageUrl.trim() || undefined,
        note: itemNote.trim() || undefined,
        price_cents: parsePriceToCents(itemPrice),
        currency: itemCurrency.trim().toUpperCase(),
        allow_group_funding: itemGroupFunding,
        min_contribution_cents: parseIntOrUndefined(itemMinContribution),
      });
      setWishlist(updated);
      setItemTitle("");
      setItemProductUrl("");
      setItemImageUrl("");
      setItemNote("");
      setItemPrice("");
      setItemCurrency("RUB");
      setItemGroupFunding(false);
      setItemMinContribution("100");
      showNotice("Подарок добавлен");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось добавить подарок");
    } finally {
      setCreatingItem(false);
    }
  }

  async function copyLink() {
    if (!wishlist || typeof window === "undefined") {
      return;
    }
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/w/${wishlist.share_slug}`);
      showNotice("Публичная ссылка скопирована");
    } catch {
      setError("Не удалось получить доступ к буферу обмена");
    }
  }

  async function deleteCurrentWishlist() {
    if (!wishlist || !token) {
      return;
    }

    const confirmed = window.confirm("Удалить этот вишлист навсегда?");
    if (!confirmed) {
      return;
    }

    setDeletingWishlist(true);
    setError(null);
    try {
      await deleteWishlist(token, wishlist.id);
      router.push("/app");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось удалить вишлист");
      setDeletingWishlist(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-8 sm:px-6">
        <p className="text-sm text-[var(--muted)]">Загрузка вишлиста...</p>
      </main>
    );
  }

  if (!wishlist) {
    return (
      <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-8 sm:px-6">
        <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-[var(--danger)]">
          {error ?? "Вишлист не найден"}
        </p>
        <Link className="btn-ghost mt-4 inline-flex text-sm" href="/app">
          Назад в кабинет
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1220px] px-4 py-6 sm:px-8 sm:py-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="display text-6xl font-bold leading-[0.9]">{wishlist.title}</p>
          <p className="mt-2 text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">{formatDate(wishlist.event_date)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="btn-ghost text-sm" href="/app">
            Кабинет
          </Link>
          <Link className="btn-ghost text-sm" href={`/w/${wishlist.share_slug}`}>
            Публичная страница
          </Link>
          <button className="btn-primary text-sm" onClick={copyLink} type="button">
            Копировать ссылку
          </button>
          <button
            className="rounded-[2px] border border-[#efc8bd] bg-[#fff2ee] px-4 py-2 text-sm font-semibold text-[var(--danger)]"
            disabled={deletingWishlist}
            onClick={deleteCurrentWishlist}
            type="button"
          >
            {deletingWishlist ? "Удаляю..." : "Удалить вишлист"}
          </button>
        </div>
      </header>

      {error ? (
        <p className="mb-4 rounded-[10px] border border-[#efc8bd] bg-[#fff2ee] px-3 py-2 text-sm text-[var(--danger)]">{error}</p>
      ) : null}
      {notice ? (
        <p className="mb-4 rounded-[10px] border border-[#c9e3d8] bg-[#edf8f2] px-3 py-2 text-sm text-[var(--good)]">{notice}</p>
      ) : null}

      <section className="grid gap-5 lg:grid-cols-[1fr_1.45fr]">
        <article className="surface rounded-[20px] p-5">
          <h2 className="display text-4xl font-bold leading-[0.95]">Настройки вишлиста</h2>
          <form className="mt-4 space-y-3" onSubmit={saveWishlistMeta}>
            <div>
              <label className="label">Название</label>
              <input className="input" minLength={2} onChange={(event) => setTitle(event.target.value)} required value={title} />
            </div>

            <div>
              <label className="label">Описание</label>
              <textarea className="input min-h-20 resize-y" onChange={(event) => setDescription(event.target.value)} value={description} />
            </div>

            <div>
              <label className="label">Дата события</label>
              <input className="input" onChange={(event) => setEventDate(event.target.value)} type="date" value={eventDate} />
            </div>

            <label className="inline-flex items-center gap-2 text-sm font-semibold">
              <input checked={isPublic} onChange={(event) => setIsPublic(event.target.checked)} type="checkbox" />
              Публичная ссылка включена
            </label>

            <button className="btn-primary w-full" disabled={savingMeta} type="submit">
              {savingMeta ? "Сохраняю..." : "Сохранить настройки"}
            </button>
          </form>
        </article>

        <article className="surface rounded-[20px] p-5">
          <h2 className="display text-4xl font-bold leading-[0.95]">Добавить подарок</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Для дорогих подарков включите совместный сбор и задайте минимальный взнос.
          </p>

          <form className="mt-4 grid gap-3" onSubmit={addItem}>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <div>
                <label className="label">Ссылка на товар</label>
                <input
                  className="input"
                  onChange={(event) => setItemProductUrl(event.target.value)}
                  placeholder="https://shop.example/item"
                  value={itemProductUrl}
                />
              </div>
              <div className="self-end">
                <button className="btn-ghost text-sm" disabled={autofilling || !itemProductUrl.trim()} onClick={autoFillByUrl} type="button">
                  {autofilling ? "Загружаю..." : "Автозаполнение"}
                </button>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label">Название</label>
                <input
                  className="input"
                  minLength={2}
                  onChange={(event) => setItemTitle(event.target.value)}
                  placeholder="Наушники Sony"
                  required
                  value={itemTitle}
                />
              </div>
              <div>
                <label className="label">Ссылка на картинку</label>
                <input className="input" onChange={(event) => setItemImageUrl(event.target.value)} value={itemImageUrl} />
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label className="label">Цена</label>
                <input
                  className="input"
                  inputMode="decimal"
                  onChange={(event) => setItemPrice(event.target.value)}
                  placeholder="12990"
                  value={itemPrice}
                />
              </div>
              <div>
                <label className="label">Валюта</label>
                <input
                  className="input uppercase"
                  maxLength={3}
                  onChange={(event) => setItemCurrency(event.target.value)}
                  value={itemCurrency}
                />
              </div>
              <div>
                <label className="label">Мин. взнос (в копейках)</label>
                <input className="input" onChange={(event) => setItemMinContribution(event.target.value)} value={itemMinContribution} />
              </div>
            </div>

            <label className="inline-flex items-center gap-2 text-sm font-semibold">
              <input checked={itemGroupFunding} onChange={(event) => setItemGroupFunding(event.target.checked)} type="checkbox" />
              Включить совместный сбор для этого подарка
            </label>

            <div>
              <label className="label">Комментарий</label>
              <textarea
                className="input min-h-20 resize-y"
                onChange={(event) => setItemNote(event.target.value)}
                placeholder="Цвет, размер, предпочтения по магазину..."
                value={itemNote}
              />
            </div>

            <button className="btn-primary" disabled={creatingItem} type="submit">
              {creatingItem ? "Добавляю..." : "Добавить подарок"}
            </button>
          </form>
        </article>
      </section>

      <section className="mt-6">
        <h2 className="display text-5xl font-bold leading-[0.9]">Подарки</h2>
        {wishlist.items.length === 0 ? (
          <div className="surface mt-3 rounded-[12px] border border-dashed border-[var(--line)] p-4 text-sm text-[var(--muted)]">
            Вишлист пока пуст. Добавьте первый подарок выше.
          </div>
        ) : null}
        <div className="mt-3 max-h-[72vh] overflow-y-auto pr-1">
          <div className="grid gap-3">
            {wishlist.items.map((item) => (
              <ItemEditor
                item={item}
                key={item.id}
                onError={(message) => setError(message)}
                onNotice={showNotice}
                onUpdated={(updated) => {
                  setWishlist(updated);
                  setError(null);
                }}
                token={token ?? ""}
                wishlistId={wishlist.id}
              />
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

