export function formatMoney(cents: number | null, currency: string): string {
  if (cents === null) {
    return "Цена не указана";
  }
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: (currency || "RUB").toUpperCase(),
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

export function formatDate(value: string | null): string {
  if (!value) {
    return "Дата не указана";
  }
  const date = new Date(value);
  return date.toLocaleDateString("ru-RU", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function toDateInput(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  return date.toISOString().slice(0, 10);
}

export function clampPercent(value: number): number {
  if (value < 0) {
    return 0;
  }
  if (value > 100) {
    return 100;
  }
  return Math.round(value);
}

