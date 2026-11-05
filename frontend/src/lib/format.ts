function toNumber(value: string | number) {
  return typeof value === "number" ? value : Number(value);
}

export function formatUsd(value: string | number) {
  const amount = toNumber(value);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: amount !== 0 && Math.abs(amount) < 1 ? 6 : 2,
  }).format(amount);
}

export function formatNgn(value: string | number) {
  const amount = toNumber(value);
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    currencyDisplay: "narrowSymbol",
    maximumFractionDigits: Math.abs(amount) >= 1000 ? 0 : 2,
  }).format(amount);
}

export function formatAmount(value: string | number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 8 }).format(toNumber(value));
}

export function formatCompact(value: number) {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: value !== 0 && Math.abs(value) < 10 ? 4 : 2,
  }).format(value);
}

export function formatChange(value: string | number) {
  const amount = toNumber(value);
  return `${amount > 0 ? "+" : ""}${amount.toFixed(2)}%`;
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}
