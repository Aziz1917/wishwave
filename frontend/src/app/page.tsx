"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { AUTH_CHANGED_EVENT, getAuthToken, getStoredUser } from "@/lib/auth";

const SERVER_AUTH_SNAPSHOT = "0";

const sampleDreams = [
  "Мария ждёт Apple Watch",
  "Артём мечтает о виниле",
  "Лера собирает на камеру Fujifilm",
  "Никита хочет редкое LEGO",
  "Саша ищет идеальные наушники",
  "Алиса выбирает кольцо ручной работы",
];

function readAuthSnapshot(): string {
  const token = getAuthToken();
  const storedUser = getStoredUser();
  if (!token) {
    return "0";
  }
  return `1:${storedUser?.name ?? ""}`;
}

function subscribeAuth(onStoreChange: () => void) {
  if (typeof window === "undefined") {
    return () => {};
  }

  const handler = () => onStoreChange();
  window.addEventListener("storage", handler);
  window.addEventListener(AUTH_CHANGED_EVENT, handler);
  return () => {
    window.removeEventListener("storage", handler);
    window.removeEventListener(AUTH_CHANGED_EVENT, handler);
  };
}

export default function Home() {
  const authSnapshot = useSyncExternalStore(subscribeAuth, readAuthSnapshot, () => SERVER_AUTH_SNAPSHOT);
  const isAuthenticated = authSnapshot.startsWith("1:");
  const rawName = isAuthenticated ? authSnapshot.slice(2) : "";
  const profileName = rawName.trim() ? rawName : null;
  const [highlightHow, setHighlightHow] = useState(false);
  const howItWorksRef = useRef<HTMLElement | null>(null);

  function scrollHowToBottom() {
    const section = howItWorksRef.current;
    if (!section) {
      return;
    }
    const targetTop = Math.max(section.offsetTop + section.offsetHeight - window.innerHeight + 20, 0);
    window.scrollTo({ top: targetTop, behavior: "smooth" });
  }

  function openHowItWorksFromHero() {
    setHighlightHow(true);
    window.history.replaceState(null, "", "#how-it-works");
    window.requestAnimationFrame(() => {
      scrollHowToBottom();
      window.setTimeout(scrollHowToBottom, 220);
    });
  }

  useEffect(() => {
    if (!highlightHow) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const clickedHowSection = target.closest("[data-how-section='true']");
      const clickedToggle = target.closest("[data-how-toggle='true']");
      const clickedCard = target.closest("[data-how-card='true']");

      if (clickedToggle || clickedCard) {
        return;
      }
      if (!clickedHowSection) {
        setHighlightHow(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [highlightHow]);

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1180px] px-4 py-7 sm:px-8 sm:py-9">
      <header className="mb-7 flex items-center justify-between">
        <p className="display text-4xl font-bold">Wishwave</p>
        {isAuthenticated ? (
          <Link className="btn-ghost text-sm" href="/app">
            {`Профиль${profileName ? `: ${profileName}` : ""}`}
          </Link>
        ) : (
          <Link className="btn-ghost text-sm" href="/auth">
            Войти
          </Link>
        )}
      </header>

      <section className="surface reveal-in relative overflow-hidden rounded-[22px] px-5 py-7 sm:px-8 sm:py-10">
        <div className="pointer-events-none absolute left-[-12%] top-[-22%] h-[340px] w-[340px] rounded-full bg-[radial-gradient(circle,_rgba(217,93,57,0.35)_0%,_rgba(217,93,57,0)_70%)]" />
        <div className="pointer-events-none absolute -bottom-16 right-0 h-[300px] w-[300px] rounded-full bg-[radial-gradient(circle,_rgba(26,26,26,0.14)_0%,_rgba(26,26,26,0)_72%)]" />
        <div className="relative grid gap-8 lg:grid-cols-[1.16fr_0.84fr]">
          <div>
            <h1 className="display text-5xl font-bold leading-[0.95] sm:text-7xl">
              Дарите то,
              <br />
              что действительно
              <br />
              ждут.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-[var(--muted)] sm:text-lg">
              Удобный список желаний для любого праздника: друзья не купят одинаковые подарки и смогут скинуться на дорогие.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link className="btn-primary" href={isAuthenticated ? "/app" : "/auth"}>
                {isAuthenticated ? "Открыть кабинет" : "Создать волну желаний"}
              </Link>
              <button className="btn-ghost" data-how-toggle="true" onClick={openHowItWorksFromHero} type="button">
                Как это работает
              </button>
            </div>
            <p className="mt-4 text-sm font-semibold tracking-[0.05em] text-[var(--muted)] uppercase">
              12 400 мечтаний исполнено
            </p>
          </div>

          <div className="grid content-end gap-3">
            <article className="surface rounded-[14px] p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">Приватность владельца</p>
              <p className="mt-2 text-sm leading-relaxed">
                Владелец видит только, что подарок заняли или что идёт сбор. Кто именно участвовал и сколько внёс, не показываем.
              </p>
            </article>
            <article className="surface rounded-[14px] p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">Сбор на дорогие подарки</p>
              <p className="mt-2 text-sm leading-relaxed">
                Друзья могут скидываться частями. Сумма на карточке обновляется сама, без ручного обновления страницы.
              </p>
            </article>
            <article className="surface rounded-[14px] p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">Автозаполнение по ссылке</p>
              <p className="mt-2 text-sm leading-relaxed">
                Вставьте ссылку на товар, и мы постараемся сами подставить название, фото и цену.
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sampleDreams.map((dream, index) => (
          <article
            className="surface flex min-h-[84px] items-center rounded-[12px] px-4 py-3 text-base font-semibold leading-tight"
            key={dream}
            style={{
              transform: `translateY(${(index % 3) * 2}px)`,
            }}
          >
            {dream}
          </article>
        ))}
      </section>

      <section
        className="surface mt-9 scroll-mt-24 rounded-[20px] p-4 sm:p-6"
        data-how-section="true"
        id="how-it-works"
        onPointerDownCapture={(event) => {
          const target = event.target;
          if (!(target instanceof Element)) {
            return;
          }
          const clickedCard = target.closest("[data-how-card='true']");
          const clickedToggle = target.closest("[data-how-toggle='true']");
          if (!clickedCard && !clickedToggle) {
            setHighlightHow(false);
          }
        }}
        ref={howItWorksRef}
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="display text-4xl font-bold">Как это работает</h2>
          <button
            className="btn-ghost text-xs uppercase tracking-[0.08em]"
            data-how-toggle="true"
            onClick={() => setHighlightHow((prev) => !prev)}
            type="button"
          >
            {highlightHow ? "Свернуть шаги" : "Увеличить шаги"}
          </button>
        </div>

        <div className={`grid transition-all duration-500 ${highlightHow ? "gap-6 sm:grid-cols-1 lg:grid-cols-3" : "gap-3 sm:grid-cols-3"}`}>
          <article
            className={`surface transition-all duration-500 ${highlightHow ? "rounded-[16px] p-8 scale-[1.04]" : "rounded-[12px] p-5 scale-100"}`}
            data-how-card="true"
          >
            <p className="pill mb-3 inline-block bg-[#ece7d9] text-[#5c544a]">Шаг 1</p>
            <h3 className={`display font-bold leading-none ${highlightHow ? "text-5xl" : "text-3xl"}`}>Создайте список</h3>
            <p className={`mt-3 text-[var(--muted)] ${highlightHow ? "text-base" : "text-sm"}`}>
              Добавьте подарки вручную или вставьте ссылку из магазина.
            </p>
          </article>
          <article
            className={`surface transition-all duration-500 ${highlightHow ? "rounded-[16px] p-8 scale-[1.04]" : "rounded-[12px] p-5 scale-100"}`}
            data-how-card="true"
          >
            <p className="pill mb-3 inline-block bg-[#f0e5dd] text-[#6a4d43]">Шаг 2</p>
            <h3 className={`display font-bold leading-none ${highlightHow ? "text-5xl" : "text-3xl"}`}>Поделитесь ссылкой</h3>
            <p className={`mt-3 text-[var(--muted)] ${highlightHow ? "text-base" : "text-sm"}`}>
              Гости бронируют подарок и подключаются к совместному сбору.
            </p>
          </article>
          <article
            className={`surface transition-all duration-500 ${highlightHow ? "rounded-[16px] p-8 scale-[1.04]" : "rounded-[12px] p-5 scale-100"}`}
            data-how-card="true"
          >
            <p className="pill mb-3 inline-block bg-[#e4e2d7] text-[#4f4c44]">Шаг 3</p>
            <h3 className={`display font-bold leading-none ${highlightHow ? "text-5xl" : "text-3xl"}`}>Следите за сбором</h3>
            <p className={`mt-3 text-[var(--muted)] ${highlightHow ? "text-base" : "text-sm"}`}>
              Прогресс обновляется сразу и остаётся без спойлеров для владельца.
            </p>
          </article>
        </div>
      </section>
    </main>
  );
}
