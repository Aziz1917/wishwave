"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, createWishlist, deleteWishlist, getMyWishlists } from "@/lib/api";
import { clearAuthSession, getAuthToken, getStoredUser } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { User, WishlistListItem } from "@/lib/types";

export default function DashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [wishlists, setWishlists] = useState<WishlistListItem[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [deletingWishlistId, setDeletingWishlistId] = useState<string | null>(null);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      router.replace("/auth");
      return;
    }
    setUser(getStoredUser());
    const sessionToken = token;

    async function run() {
      try {
        const data = await getMyWishlists(sessionToken);
        setWishlists(data);
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 401) {
          clearAuthSession();
          router.replace("/auth");
          return;
        }
        setError(caught instanceof ApiError ? caught.detail : "Не удалось загрузить вишлисты");
      } finally {
        setLoading(false);
      }
    }

    void run();
  }, [router]);

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const token = getAuthToken();
    if (!token) {
      router.replace("/auth");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createWishlist(token, {
        title: title.trim(),
        description: description.trim() || undefined,
        event_date: eventDate || undefined,
      });
      router.push(`/app/wishlist/${created.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось создать вишлист");
      setSubmitting(false);
    }
  }

  function onSignOut() {
    clearAuthSession();
    router.replace("/auth");
  }

  function showNotice(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2500);
  }

  async function copyPublicLink(slug: string) {
    if (typeof window === "undefined") {
      return;
    }
    const url = `${window.location.origin}/w/${slug}`;
    try {
      await navigator.clipboard.writeText(url);
      showNotice("Публичная ссылка скопирована");
    } catch {
      showNotice("Не удалось получить доступ к буферу обмена");
    }
  }

  async function onDeleteWishlist(wishlistId: string) {
    const token = getAuthToken();
    if (!token) {
      router.replace("/auth");
      return;
    }

    const confirmed = window.confirm("Удалить этот вишлист навсегда?");
    if (!confirmed) {
      return;
    }

    setDeletingWishlistId(wishlistId);
    setError(null);
    try {
      await deleteWishlist(token, wishlistId);
      setWishlists((prev) => prev.filter((wishlist) => wishlist.id !== wishlistId));
      showNotice("Вишлист удалён");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Не удалось удалить вишлист");
    } finally {
      setDeletingWishlistId(null);
    }
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1220px] px-4 py-6 sm:px-8 sm:py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="display text-6xl font-bold leading-[0.9]">Мои события</p>
          <p className="mt-2 text-xs font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
            {user ? `Вы вошли как ${user.email}` : "Коллекция вишлистов"}
          </p>
        </div>
        <div className="flex gap-2">
          <Link className="btn-ghost text-sm" href="/">
            Витрина
          </Link>
          <button className="btn-ghost text-sm" onClick={onSignOut} type="button">
            Выйти
          </button>
        </div>
      </header>

      {error ? (
        <p className="mb-4 rounded-[10px] border border-[#efc8bd] bg-[#fff2ee] px-3 py-2 text-sm text-[var(--danger)]">{error}</p>
      ) : null}
      {notice ? (
        <p className="mb-4 rounded-[10px] border border-[#c9e3d8] bg-[#edf8f2] px-3 py-2 text-sm text-[var(--good)]">{notice}</p>
      ) : null}

      <section className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
        <article className="surface rounded-[20px] p-5" id="create-wishlist">
          <h2 className="display text-4xl font-bold leading-[0.95]">Новый вишлист</h2>
          <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">
            Создайте отдельную коллекцию под каждое событие и сразу получите публичную ссылку.
          </p>

          <form className="mt-5 space-y-4" onSubmit={onCreate}>
            <div>
              <label className="label" htmlFor="title">
                Название
              </label>
              <input
                className="input"
                id="title"
                minLength={2}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="День рождения 2026"
                required
                value={title}
              />
            </div>

            <div>
              <label className="label" htmlFor="description">
                Описание
              </label>
              <textarea
                className="input min-h-24 resize-y"
                id="description"
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Пожелания по стилю, цвету, размерам..."
                value={description}
              />
            </div>

            <div>
              <label className="label" htmlFor="eventDate">
                Дата события
              </label>
              <input className="input" id="eventDate" onChange={(event) => setEventDate(event.target.value)} type="date" value={eventDate} />
            </div>

            <button className="btn-primary w-full" disabled={submitting} type="submit">
              {submitting ? "Создаю..." : "Создать вишлист"}
            </button>
          </form>
        </article>

        <article className="surface rounded-[20px] p-5">
          <h2 className="display text-4xl font-bold leading-[0.95]">Коллекция</h2>
          {loading ? <p className="mt-4 text-sm text-[var(--muted)]">Загрузка...</p> : null}

          {!loading && !error && wishlists.length === 0 ? (
            <div className="mt-4 rounded-[12px] border border-dashed border-[var(--line)] px-4 py-6 text-sm text-[var(--muted)]">
              Здесь пока тихо. Создайте первый вишлист в левой колонке.
            </div>
          ) : null}

          <div className="mt-4 columns-1 gap-4 md:columns-2">
            {wishlists.map((wishlist, index) => (
              <div className="mb-4 break-inside-avoid" key={wishlist.id}>
                <article className="surface rounded-[14px] p-4">
                  <div
                    className="mb-3 h-28 rounded-[10px]"
                    style={{
                      background:
                        index % 3 === 0
                          ? "linear-gradient(140deg, rgba(217,93,57,0.28), rgba(217,93,57,0.02))"
                          : index % 3 === 1
                            ? "linear-gradient(140deg, rgba(26,26,26,0.2), rgba(26,26,26,0.03))"
                            : "linear-gradient(140deg, rgba(226,222,208,0.9), rgba(249,247,242,0.6))",
                    }}
                  />
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="display text-3xl font-bold leading-[0.95]">{wishlist.title}</p>
                      <p className="mt-1 text-xs text-[var(--muted)]">{formatDate(wishlist.event_date)}</p>
                    </div>
                    <span className="pill bg-[#ece7d9] text-[#5c544a]">{wishlist.item_count} подарков</span>
                  </div>
                  {wishlist.description ? <p className="mt-3 text-sm text-[var(--muted)]">{wishlist.description}</p> : null}
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link className="btn-primary text-sm" href={`/app/wishlist/${wishlist.id}`}>
                      Открыть
                    </Link>
                    <Link className="btn-ghost text-sm" href={`/w/${wishlist.share_slug}`}>
                      Публичная
                    </Link>
                    <button className="btn-ghost text-sm" onClick={() => copyPublicLink(wishlist.share_slug)} type="button">
                      Копировать
                    </button>
                    <button
                      className="rounded-[2px] border border-[#efc8bd] bg-[#fff2ee] px-4 py-2 text-sm font-semibold text-[var(--danger)]"
                      disabled={deletingWishlistId === wishlist.id}
                      onClick={() => onDeleteWishlist(wishlist.id)}
                      type="button"
                    >
                      {deletingWishlistId === wishlist.id ? "Удаляю..." : "Удалить"}
                    </button>
                  </div>
                </article>
              </div>
            ))}
          </div>
        </article>
      </section>

      <a
        className="btn-primary fixed bottom-5 right-5 z-20 hidden h-12 w-12 items-center justify-center text-2xl leading-none lg:inline-flex"
        href="#create-wishlist"
      >
        +
      </a>
    </main>
  );
}
