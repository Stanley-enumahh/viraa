export type User = {
  id: number;
  email: string;
  username: string;
  full_name: string;
  date_joined: string;
};

export type AuthResponse = {
  access: string;
  refresh: string;
  user: User;
};

export type Price = {
  symbol: string;
  name: string;
  price_usd: string;
  price_ngn: string;
  change_24h_pct: string;
};

export type PriceList = {
  as_of: string;
  tick_seconds: number;
  prices: Price[];
};

export type HistoryRange = "1h" | "24h" | "7d" | "30d";

export type PriceHistory = {
  symbol: string;
  range: HistoryRange;
  high_usd: string;
  low_usd: string;
  points: { t: string; price_usd: string }[];
};

export type WalletRow = {
  asset: string;
  name: string;
  balance: string;
  value_usd: string;
  value_ngn: string;
};

export type Portfolio = {
  wallets: WalletRow[];
  total_usd: string;
  total_ngn: string;
};

export type TradeQuote = {
  kind: "buy" | "sell" | "swap";
  from_asset: string;
  from_amount: string;
  to_asset: string;
  to_amount: string;
  rate: string;
  fee_asset: string;
  fee_amount: string;
};

export type SendQuote = {
  asset: string;
  amount: string;
  fee_amount: string;
  total: string;
  recipient: string | null;
  recipient_name: string | null;
  address: string | null;
};

export type Draft = {
  reference: string;
  status: "pending" | "executed" | "rejected" | "expired" | "failed";
  summary: string;
  transcript: string;
  expires_at: string;
  created_at: string;
} & ({ action: "buy" | "sell" | "swap"; quote: TradeQuote } | { action: "send"; quote: SendQuote });

export type AssistantResult = {
  transcript: string;
  type: "draft" | "answer" | "question" | "refused" | "listening" | "ignored";
  reply: string;
  parser: "claude" | "fallback" | null;
  draft: Draft | null;
};

export type TransactionKind = "buy" | "sell" | "swap" | "send" | "receive";

export type Transaction = {
  reference: string;
  kind: TransactionKind;
  summary: string;
  created_at: string;
};
