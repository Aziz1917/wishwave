"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { ApiError, googleOAuthStartUrl, login, register } from "@/lib/api";
import { getAuthToken, setAuthSession } from "@/lib/auth";

type Mode = "login" | "register";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (getAuthToken()) {
      router.replace("/app");
    }
  }, [router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response =
        mode === "login"
          ? await login(email.trim(), password)
          : await register(email.trim(), name.trim(), password);

      setAuthSession(response.access_token, response.user);
      router.replace("/app");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.detail);
      } else {
        setError("Непредвиденная ошибка");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1160px] px-4 py-7 sm:px-8 sm:py-10">
      <header className="mb-6 flex items-center justify-between">
        <Link className="display text-4xl font-bold" href="/">
          Wishwave
        </Link>
        <button
          className="btn-ghost text-xs uppercase tracking-[0.08em]"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
          type="button"
        >
          {mode === "login" ? "Создать аккаунт" : "Уже есть аккаунт"}
        </button>
      </header>

      <section className="surface overflow-hidden rounded-[22px]">
        <div className="grid min-h-[74vh] lg:grid-cols-[1.02fr_0.98fr]">
          <aside className="relative hidden overflow-hidden bg-[linear-gradient(140deg,#f2dec8_0%,#f6efe2_44%,#e8dfcf_100%)] p-8 lg:block">
            <div className="absolute left-[-90px] top-[-90px] h-[260px] w-[260px] rounded-full bg-[radial-gradient(circle,_rgba(217,93,57,0.35)_0%,_rgba(217,93,57,0)_74%)]" />
            <div className="absolute -bottom-16 right-[-60px] h-[250px] w-[250px] rounded-full bg-[radial-gradient(circle,_rgba(26,26,26,0.16)_0%,_rgba(26,26,26,0)_72%)]" />
            <div className="relative flex h-full flex-col justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.09em] text-[var(--muted)]">The Entry</p>
                <h2 className="display mt-3 max-w-sm text-6xl font-bold leading-[0.9]">С возвращением.</h2>
                <p className="mt-4 max-w-sm text-base leading-relaxed text-[var(--muted)]">Ваши желания соскучились.</p>
              </div>
              <div className="surface rounded-[14px] p-4">
                <p className="text-sm leading-relaxed">
                  Публичные ссылки доступны гостям без регистрации, но редактирование и управление списками остаются у владельца.
                </p>
              </div>
            </div>
          </aside>

          <div className="flex items-center px-5 py-8 sm:px-10">
            <div className="w-full max-w-[420px]">
              <h1 className="display text-5xl font-bold leading-[0.9]">{mode === "login" ? "Войти" : "Регистрация"}</h1>
              <p className="mt-3 text-sm leading-relaxed text-[var(--muted)]">
                Авторизация по e-mail и паролю. После входа вы попадёте в личный кабинет вишлистов.
              </p>

              <div className="mt-6 space-y-3">
                <a className="btn-primary inline-flex w-full justify-center" href={googleOAuthStartUrl()}>
                  Войти через Google
                </a>
                <p className="text-center text-xs uppercase tracking-[0.08em] text-[var(--muted)]">или</p>
              </div>

              <form className="mt-3 space-y-4" onSubmit={onSubmit}>
                {mode === "register" ? (
                  <div>
                    <label className="label" htmlFor="name">
                      Имя
                    </label>
                    <input
                      className="input"
                      id="name"
                      maxLength={100}
                      minLength={2}
                      onChange={(event) => setName(event.target.value)}
                      placeholder="Алекс"
                      required
                      value={name}
                    />
                  </div>
                ) : null}

                <div>
                  <label className="label" htmlFor="email">
                    Эл. почта
                  </label>
                  <input
                    className="input"
                    id="email"
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@email.com"
                    required
                    type="email"
                    value={email}
                  />
                </div>

                <div>
                  <label className="label" htmlFor="password">
                    Пароль
                  </label>
                  <div className="grid grid-cols-[1fr_auto] items-center gap-3">
                    <input
                      className="input"
                      id="password"
                      minLength={8}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="Минимум 8 символов"
                      required
                      type={showPassword ? "text" : "password"}
                      value={password}
                    />
                    <button
                      className="btn-ghost h-9 px-3 text-xs uppercase tracking-[0.08em]"
                      onClick={() => setShowPassword((prev) => !prev)}
                      type="button"
                    >
                      {showPassword ? "Скрыть" : "Показать"}
                    </button>
                  </div>
                </div>

                {error ? (
                  <p className="rounded-[10px] border border-[#efc8bd] bg-[#fff2ee] px-3 py-2 text-sm text-[var(--danger)]">{error}</p>
                ) : null}

                <button className="btn-primary mt-2 w-full" disabled={loading} type="submit">
                  {loading ? "Подождите..." : mode === "login" ? "Войти" : "Создать аккаунт"}
                </button>
              </form>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
