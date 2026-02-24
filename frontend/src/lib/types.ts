export type User = {
  id: string;
  email: string;
  name: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  user: User;
};

export type WishlistListItem = {
  id: string;
  title: string;
  description: string | null;
  event_date: string | null;
  share_slug: string;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  item_count: number;
};

export type OwnerItemStats = {
  reserved_count: number;
  contributions_count: number;
  contributions_total_cents: number;
};

export type OwnerWishlistItem = {
  id: string;
  title: string;
  product_url: string | null;
  image_url: string | null;
  note: string | null;
  price_cents: number | null;
  currency: string;
  allow_group_funding: boolean;
  min_contribution_cents: number;
  sort_order: number;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
  stats: OwnerItemStats;
};

export type OwnerWishlist = {
  id: string;
  title: string;
  description: string | null;
  event_date: string | null;
  share_slug: string;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  items: OwnerWishlistItem[];
};

export type PublicItem = {
  id: string;
  title: string;
  product_url: string | null;
  image_url: string | null;
  note: string | null;
  price_cents: number | null;
  currency: string;
  allow_group_funding: boolean;
  can_contribute: boolean;
  min_contribution_cents: number;
  is_deleted: boolean;
  is_reserved: boolean;
  reserved_count: number;
  contributions_total_cents: number;
  contributions_count: number;
  recent_contributions_cents: number[];
  remaining_cents: number | null;
  funding_percent: number;
  is_fully_funded: boolean;
  funding_deadline_passed: boolean;
  can_reserve_remaining: boolean;
  created_at: string;
  updated_at: string;
};

export type PublicWishlist = {
  id: string;
  title: string;
  description: string | null;
  event_date: string | null;
  share_slug: string;
  viewer_is_owner: boolean;
  created_at: string;
  updated_at: string;
  items: PublicItem[];
};

export type ReserveResponse = {
  reservation_id: string;
  release_token: string;
  item_id: string;
};

export type ContributionResponse = {
  contribution_id: string;
  item_id: string;
  amount_cents: number;
};

export type MetadataResponse = {
  source_url: string;
  title: string | null;
  image_url: string | null;
  price_cents: number | null;
  currency: string | null;
};

export type ReservationToken = {
  reservationId: string;
  releaseToken: string;
};
