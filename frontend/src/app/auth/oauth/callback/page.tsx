"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import { setAuthSession } from "@/lib/auth";

export default function OAuthCallbackPage() {
  const router = useRouter();

  const parsed = useMemo(() => {
    if (typeof window === "undefined") {
      return null;
    }

    const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";
    const params = new URLSearchParams(hash);

    const accessToken = params.get("access_token");
    const userId = params.get("user_id");
    const userEmail = params.get("user_email");
    const userName = params.get("user_name");

    if (!accessToken || !userId || !userEmail || !userName) {
      return { error: "Не удалось завершить OAuth вход. Попробуйте снова." } as const;
    }

    return {
      accessToken,
      user: {
        id: userId,
        email: userEmail,
        name: userName,
      },
    } as const;
  }, []);

  useEffect(() => {
    if (!parsed || "error" in parsed) {
      return;
    }

    setAuthSession(parsed.accessToken, parsed.user);
    router.replace("/app");
  }, [parsed, router]);

  return (
    <main className="mx-auto min-h-screen w-full max-w-xl px-4 py-10">
      <section className="surface rounded-[18px] p-6">
        <h1 className="display text-4xl font-bold">Завершаем вход</h1>
        {parsed && "error" in parsed ? (
          <>
            <p className="mt-3 text-sm text-[var(--danger)]">{parsed.error}</p>
            <Link className="btn-ghost mt-4 inline-flex text-sm" href="/auth">
              Назад к авторизации
            </Link>
          </>
        ) : (
          <p className="mt-3 text-sm text-[var(--muted)]">Секунду, переносим вас в кабинет...</p>
        )}
      </section>
    </main>
  );
}
