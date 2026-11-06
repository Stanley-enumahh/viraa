"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { DraftCard } from "@/components/assistant/draft-card";
import { Card, ErrorNotice } from "@/components/ui";
import { api } from "@/lib/api";
import { errorMessage, openDraftFrom, type OpenDraft } from "@/lib/assistant-controller";
import { formatAmount } from "@/lib/format";
import type { TradeQuote, TradeRequest } from "@/lib/types";
import { FUNDS_CHANGED_EVENT, usePolling } from "@/lib/use-polling";

type Kind = TradeQuote["kind"];

const KINDS: { value: Kind; label: string }[] = [
  { value: "buy", label: "Buy" },
  { value: "sell", label: "Sell" },
  { value: "swap", label: "Swap" },
];
const PAYMENT_ASSETS = ["NGN", "USDT"];
const QUICK_SHARES = [
  { label: "25%", share: 0.25 },
  { label: "50%", share: 0.5 },
];
const AMOUNT_PATTERN = /^\d*\.?\d{0,8}$/;
const ESTIMATE_DELAY_MS = 350;

/** Keep the second asset valid when the first one or the trade type changes. */
function validCounter(kind: Kind, coin: string, counter: string) {
  if (kind === "swap") {
    if (counter !== coin && counter !== "NGN") return counter;
    return coin === "USDT" ? "BTC" : "USDT";
  }
  if (PAYMENT_ASSETS.includes(counter) && counter !== coin) return counter;
  return "NGN";
}

function AssetSelect({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="min-w-0 flex-1">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink-2">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-line bg-canvas px-3 py-3 text-base text-ink"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function TradeForm() {
  const params = useSearchParams();
  const requestedKind = KINDS.find(({ value }) => value === params.get("kind"))?.value ?? "buy";
  const linkedCoin = params.get("asset")?.toUpperCase();
  const requestedCoin = linkedCoin && linkedCoin !== "NGN" ? linkedCoin : "BTC";

  const [kind, setKind] = useState<Kind>(requestedKind);
  const [coin, setCoin] = useState(requestedCoin);
  const [counter, setCounter] = useState(validCounter(requestedKind, requestedCoin, "NGN"));
  const [amount, setAmount] = useState("");
  const [settledAmount, setSettledAmount] = useState("");
  const [amountInReceived, setAmountInReceived] = useState(false);
  const [open, setOpen] = useState<OpenDraft | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");

  const prices = usePolling(api.prices, 5000);
  const portfolio = usePolling(api.portfolio, 5000);

  const from = kind === "buy" ? counter : coin;
  const to = kind === "buy" ? coin : counter;

  useEffect(() => {
    const timer = setTimeout(() => setSettledAmount(amount), ESTIMATE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [amount]);

  const trade: TradeRequest = {
    kind,
    from_asset: from,
    to_asset: to,
    amount: settledAmount,
    amount_asset: amountInReceived ? to : from,
  };
  const hasAmount = Number(settledAmount) > 0;
  const estimate = usePolling(
    () => (hasAmount ? api.tradeEstimate(trade) : Promise.resolve(null)),
    5000,
    JSON.stringify(trade),
  );
  const currentEstimate = estimate.stale ? null : estimate.data;
  const typingAhead = amount !== settledAmount;

  const coins = prices.data?.prices ?? [];
  const nameOf = (symbol: string) =>
    symbol === "NGN" ? "Nigerian Naira" : (coins.find((price) => price.symbol === symbol)?.name ?? symbol);
  const assetOption = (symbol: string) => ({ value: symbol, label: `${nameOf(symbol)} (${symbol})` });
  const coinOptions = coins.map((price) => assetOption(price.symbol));
  // The list loads a moment after the page, and a link can preselect a coin.
  const coinSelectOptions = coinOptions.some((option) => option.value === coin) ? coinOptions : [assetOption(coin), ...coinOptions];
  const counterOptions = (
    kind === "swap" ? coins.map((price) => price.symbol) : PAYMENT_ASSETS
  )
    .filter((symbol) => symbol !== coin)
    .map(assetOption);
  const counterSelectOptions = counterOptions.some((option) => option.value === counter)
    ? counterOptions
    : [assetOption(counter), ...counterOptions];

  const available = portfolio.data?.wallets.find((wallet) => wallet.asset === from)?.balance ?? "0";

  function changeKind(next: Kind) {
    setKind(next);
    setCounter(validCounter(next, coin, counter));
    setAmountInReceived(false);
    setError("");
  }

  function changeCoin(next: string) {
    setCoin(next);
    setCounter(validCounter(kind, next, counter));
    setError("");
  }

  function changeAmount(next: string) {
    if (AMOUNT_PATTERN.test(next)) {
      setAmount(next);
      setError("");
    }
  }

  function applyShare(share: number) {
    // Never rounds up past the balance. NGN and USDT work in two decimals.
    const places = PAYMENT_ASSETS.includes(from) ? 2 : 8;
    const factor = 10 ** places;
    setAmountInReceived(false);
    changeAmount(String(Math.floor(Number(available) * share * factor) / factor));
  }

  function applyMax() {
    setAmountInReceived(false);
    changeAmount(available.includes(".") ? available.replace(/\.?0+$/, "") : available);
  }

  async function review(event: FormEvent) {
    event.preventDefault();
    if (!currentEstimate || typingAhead) return;
    setPreparing(true);
    setError("");
    try {
      setOpen(openDraftFrom(await api.createTradeDraft(trade)));
    } catch (caught) {
      setError(errorMessage(caught));
    }
    setPreparing(false);
  }

  async function approve() {
    if (!open) return;
    setOpen({ ...open, phase: "approving" });
    try {
      const { reply } = await api.approveDraft(open.draft.reference);
      setReceipt(reply);
      setAmount("");
      window.dispatchEvent(new Event(FUNDS_CHANGED_EVENT));
    } catch (caught) {
      setError(errorMessage(caught));
    }
    setOpen(null);
  }

  async function reject() {
    if (!open) return;
    setOpen({ ...open, phase: "rejecting" });
    try {
      await api.rejectDraft(open.draft.reference);
    } catch (caught) {
      setError(errorMessage(caught));
    }
    setOpen(null);
  }

  if (receipt) {
    return (
      <Card>
        <div role="status" className="py-2">
          <h2 className="text-lg font-semibold">Trade complete</h2>
          <p className="mt-1 text-ink-2">{receipt}</p>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <Link href="/activity" className="rounded-xl border border-line px-4 py-2.5 text-center font-medium">
            View activity
          </Link>
          <button
            type="button"
            onClick={() => setReceipt("")}
            className="rounded-xl bg-accent px-4 py-2.5 font-semibold text-on-accent"
          >
            New trade
          </button>
        </div>
      </Card>
    );
  }

  if (open) {
    return (
      <DraftCard
        key={open.draft.reference}
        open={open}
        onApprove={() => void approve()}
        onReject={() => void reject()}
        onDismiss={() => setOpen(null)}
      />
    );
  }

  const insufficient = currentEstimate && !currentEstimate.has_balance && !typingAhead;
  const canReview = Boolean(currentEstimate?.has_balance) && !typingAhead && !preparing;

  return (
    <Card>
      <form onSubmit={review} className="space-y-4">
        <div role="group" aria-label="Trade type" className="grid grid-cols-3 gap-1 rounded-xl bg-canvas p-1">
          {KINDS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={kind === value}
              onClick={() => changeKind(value)}
              className={`rounded-lg px-3 py-2 font-medium ${
                kind === value ? "bg-surface-raised text-ink" : "text-ink-3 hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <AssetSelect
            id="trade-coin"
            label={kind === "buy" ? "Coin to buy" : kind === "sell" ? "Coin to sell" : "Swap from"}
            value={coin}
            options={coinSelectOptions}
            onChange={changeCoin}
          />
          <AssetSelect
            id="trade-counter"
            label={kind === "buy" ? "Pay with" : kind === "sell" ? "Receive" : "Swap to"}
            value={counter}
            options={counterSelectOptions}
            onChange={(next) => {
              setCounter(next);
              setError("");
            }}
          />
        </div>

        <div>
          <div className="mb-1.5 flex items-baseline justify-between gap-3">
            <label htmlFor="trade-amount" className="text-sm font-medium text-ink-2">
              Amount
            </label>
            <p className="min-w-0 truncate text-sm text-ink-3">
              Available: {formatAmount(available)} {from}
            </p>
          </div>
          <div className="flex gap-2">
            <input
              id="trade-amount"
              inputMode="decimal"
              autoComplete="off"
              placeholder="0"
              value={amount}
              onChange={(event) => changeAmount(event.target.value)}
              className="w-full min-w-0 flex-1 rounded-xl border border-line bg-canvas px-3.5 py-3 text-base text-ink placeholder:text-ink-3"
            />
            <div role="group" aria-label="Amount is in" className="flex shrink-0 gap-1 rounded-xl bg-canvas p-1">
              {[false, true].map((inReceived) => (
                <button
                  key={String(inReceived)}
                  type="button"
                  aria-pressed={amountInReceived === inReceived}
                  onClick={() => setAmountInReceived(inReceived)}
                  className={`rounded-lg px-2.5 text-sm font-medium ${
                    amountInReceived === inReceived ? "bg-surface-raised text-ink" : "text-ink-3 hover:text-ink"
                  }`}
                >
                  {inReceived ? to : from}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-2 flex gap-2">
            {QUICK_SHARES.map(({ label, share }) => (
              <button
                key={label}
                type="button"
                onClick={() => applyShare(share)}
                className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink-2 hover:bg-surface-raised"
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              onClick={applyMax}
              className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink-2 hover:bg-surface-raised"
            >
              Max
            </button>
          </div>
        </div>

        {hasAmount && !estimate.error && currentEstimate && (
          <dl
            aria-live="polite"
            className={`space-y-1.5 rounded-xl bg-canvas p-3 text-sm transition-opacity motion-reduce:transition-none ${
              typingAhead ? "opacity-50" : ""
            }`}
          >
            <div className="flex justify-between gap-4">
              <dt className="text-ink-3">You pay</dt>
              <dd className="text-right font-medium break-words">
                {formatAmount(currentEstimate.from_amount)} {currentEstimate.from_asset}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-3">You get about</dt>
              <dd className="text-right font-medium break-words">
                {formatAmount(currentEstimate.to_amount)} {currentEstimate.to_asset}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-3">Fee (included)</dt>
              <dd className="text-right font-medium break-words">
                {formatAmount(currentEstimate.fee_amount)} {currentEstimate.fee_asset}
              </dd>
            </div>
          </dl>
        )}

        {hasAmount && estimate.error && <ErrorNotice message={estimate.error} />}
        {insufficient && <ErrorNotice message={`You don't have enough ${from} for this trade.`} />}
        {error && <ErrorNotice message={error} />}

        <button
          type="submit"
          disabled={!canReview}
          className="w-full rounded-xl bg-accent px-4 py-3 font-semibold text-on-accent disabled:opacity-50"
        >
          {preparing ? "Locking your price…" : "Review and lock price"}
        </button>
        <p className="text-center text-sm text-ink-3">You&apos;ll see the exact amounts before anything moves.</p>
      </form>
    </Card>
  );
}
