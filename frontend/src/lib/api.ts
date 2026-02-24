import {
  ContributionResponse,
  MetadataResponse,
  OwnerWishlist,
  PublicWishlist,
  ReserveResponse,
  TokenResponse,
  User,
  WishlistListItem,
} from "@/lib/types";
import { getAuthToken } from "@/lib/auth";

const RAW_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function apiBase(): string {
  const base = RAW_API.endsWith("/") ? RAW_API.slice(0, -1) : RAW_API;
  return base.endsWith("/api/v1") ? base : `${base}/api/v1`;
}

export function wishlistSocketUrl(slug: string): string {
  const httpBase = apiBase();
  const url = httpBase.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
  return `${url}/public/ws/${slug}`;
}

export function googleOAuthStartUrl(): string {
  return `${apiBase()}/auth/oauth/google/start`;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

type RequestInitExtended = RequestInit & {
  token?: string | null;
};

async function request<T>(path: string, init: RequestInitExtended = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Content-Type", "application/json");
  if (init.token) {
    headers.set("Authorization", `Bearer ${init.token}`);
  }

  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = "Ошибка запроса";
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload?.detail) {
        detail = payload.detail;
      }
    } catch {
      // ignore non-json errors
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return (await response.json()) as T;
}

export async function register(email: string, name: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, name, password }),
  });
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function getMe(token: string): Promise<User> {
  return request<User>("/auth/me", {
    method: "GET",
    token,
  });
}

export async function getMyWishlists(token: string): Promise<WishlistListItem[]> {
  return request<WishlistListItem[]>("/wishlists/mine", {
    method: "GET",
    token,
  });
}

export async function createWishlist(
  token: string,
  payload: { title: string; description?: string; event_date?: string }
): Promise<{ id: string }> {
  return request<{ id: string }>("/wishlists", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function getWishlist(token: string, wishlistId: string): Promise<OwnerWishlist> {
  return request<OwnerWishlist>(`/wishlists/${wishlistId}`, {
    method: "GET",
    token,
  });
}

export async function updateWishlist(
  token: string,
  wishlistId: string,
  payload: { title?: string; description?: string | null; event_date?: string | null; is_public?: boolean }
): Promise<void> {
  await request(`/wishlists/${wishlistId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(payload),
  });
}

export async function deleteWishlist(token: string, wishlistId: string): Promise<void> {
  await request(`/wishlists/${wishlistId}`, {
    method: "DELETE",
    token,
  });
}

export async function createItem(
  token: string,
  wishlistId: string,
  payload: {
    title: string;
    product_url?: string;
    image_url?: string;
    note?: string;
    price_cents?: number;
    currency?: string;
    allow_group_funding?: boolean;
    min_contribution_cents?: number;
    sort_order?: number;
  }
): Promise<OwnerWishlist> {
  return request<OwnerWishlist>(`/wishlists/${wishlistId}/items`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function updateItem(
  token: string,
  wishlistId: string,
  itemId: string,
  payload: {
    title?: string;
    product_url?: string | null;
    image_url?: string | null;
    note?: string | null;
    price_cents?: number | null;
    currency?: string;
    allow_group_funding?: boolean;
    min_contribution_cents?: number;
    sort_order?: number;
    is_deleted?: boolean;
  }
): Promise<OwnerWishlist> {
  return request<OwnerWishlist>(`/wishlists/${wishlistId}/items/${itemId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(payload),
  });
}

export async function softDeleteItem(token: string, wishlistId: string, itemId: string): Promise<OwnerWishlist> {
  return request<OwnerWishlist>(`/wishlists/${wishlistId}/items/${itemId}`, {
    method: "DELETE",
    token,
  });
}

export async function extractByUrl(token: string, url: string): Promise<MetadataResponse> {
  return request<MetadataResponse>("/metadata/extract", {
    method: "POST",
    token,
    body: JSON.stringify({ url }),
  });
}

export async function getPublicWishlist(slug: string): Promise<PublicWishlist> {
  const token = getAuthToken();
  return request<PublicWishlist>(`/public/w/${slug}`, {
    method: "GET",
    token,
  });
}

export async function reserveGift(
  slug: string,
  itemId: string,
  payload: { name?: string }
): Promise<ReserveResponse> {
  const token = getAuthToken();
  return request<ReserveResponse>(`/public/w/${slug}/items/${itemId}/reserve`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function releaseGift(
  slug: string,
  itemId: string,
  payload: { reservation_id: string; release_token: string }
): Promise<void> {
  const token = getAuthToken();
  await request(`/public/w/${slug}/items/${itemId}/release`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function contributeGift(
  slug: string,
  itemId: string,
  payload: { name?: string; amount_cents: number; message?: string }
): Promise<ContributionResponse> {
  const token = getAuthToken();
  return request<ContributionResponse>(`/public/w/${slug}/items/${itemId}/contribute`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}
