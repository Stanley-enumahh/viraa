"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { DraftCard } from "@/components/assistant/draft-card";
import { Card, ErrorNotice } from "@/components/ui";
import { api } from "@/lib/api";
import { errorMessage, openDraftFrom, type OpenDraft } from "@/lib/assistant-controller";
import { formatAmount } from "@/lib/format";
import type { Customer, SendRequest } from "@/lib/types";
import { FUNDS_CHANGED_EVENT, usePolling } from "@/lib/use-polling";

const AMOUNT_PATTERN = /^\d*\.?\d{0,8}$/;
const ESTIMATE_DELAY_MS = 350;
const DECIMALS_FOR_TWO_PLACE_ASSETS = ["NGN", "USDT"];

function floorFor(asset: string, value: number) {
  const factor = 10 ** (DECIMALS_FOR_TWO_PLACE_ASSETS.includes(asset) ? 2 : 8);
  return String(Math.floor(value * factor) / factor);
}

export function SendForm({ customer, onBack }: { customer: Customer; onBack: () => void }) {
  const [chosenAsset, setChosenAsset] = useState("");
  const [chosenNetwork, setChosenNetwork] = useState("");
  const [amount, setAmount] = useState("");
  const [settledAmount, setSettledAmount] = useState("");
  const [open, setOpen] = useState<OpenDraft | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");

  const portfolio = usePolling(api.portfolio, 5000);
  const networkList = usePolling(api.networks, 30000);

  const held = (portfolio.data?.wallets ?? []).filter((wallet) => Number(wallet.balance) > 0);
  const asset = chosenAsset || held.find((wallet) => wallet.asset === "USDT")?.asset || held[0]?.asset || "";
  const available = portfolio.data?.wallets.find((wallet) => wallet.asset === asset)?.balance ?? "0";

  // Naira has no network. A coin with one network needs no choice. USDT does.
  const networks = networkList.data?.[asset] ?? [];
  const network = networks.length === 1 ? networks[0].code : networks.some((n) => n.code === chosenNetwork) ? chosenNetwork : "";
  const selectedFee = networks.find((n) => n.code === network)?.fee_amount;
  const needsNetwork = asset !== "NGN";

  useEffect(() => {
    const timer = setTimeout(() => setSettledAmount(amount), ESTIMATE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [amount]);

  const send: SendRequest = { asset, amount: settledAmount, recipient: customer.username, network };
  const readyToEstimate = Boolean(asset) && Number(settledAmount) > 0 && (!needsNetwork || Boolean(network));
  const estimate = usePolling(
    () => (readyToEstimate ? api.sendEstimate(send) : Promise.resolve(null)),
    5000,
    JSON.stringify(send),
  );
  const currentEstimate = estimate.stale ? null : estimate.data;
  const typingAhead = amount !== settledAmount;

  function changeAmount(next: string) {
    if (AMOUNT_PATTERN.test(next)) {
      setAmount(next);
      setError("");
    }
  }

  function applyMax() {
    // The network fee comes on top of the amount, so leave room for it.
    const spendable = Number(available) - Number(selectedFee ?? 0);
    changeAmount(spendable > 0 ? floorFor(asset, spendable) : "");
  }

  async function review(event: FormEvent) {
    event.preventDefault();
    if (!currentEstimate || typingAhead) return;
    setPreparing(true);
    setError("");
    try {
      setOpen(openDraftFrom(await api.createSendDraft(send)));
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
          <h2 className="text-lg font-semibold">Payment sent</h2>
          <p className="mt-1 break-words text-ink-2">{receipt}</p>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <Link href="/activity" className="rounded-xl border border-line px-4 py-2.5 text-center font-medium">
            View activity
          </Link>
          <button type="button" onClick={onBack} className="rounded-xl bg-accent px-4 py-2.5 font-semibold text-on-accent">
            Done
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
        <p className="text-sm text-ink-3">To @{customer.username}</p>

        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="min-w-0 flex-1">
            <label htmlFor="send-asset" className="mb-1.5 block text-sm font-medium text-ink-2">
              Asset
            </label>
            <select
              id="send-asset"
              value={asset}
              onChange={(event) => {
                setChosenAsset(event.target.value);
                setChosenNetwork("");
                setError("");
              }}
              className="w-full rounded-xl border border-line bg-canvas px-3 py-3 text-base text-ink"
            >
              {held.map((wallet) => (
                <option key={wallet.asset} value={wallet.asset}>
                  {wallet.name} ({wallet.asset})
                </option>
              ))}
            </select>
          </div>

          {needsNetwork && (
            <div className="min-w-0 flex-1">
              <label htmlFor="send-network" className="mb-1.5 block text-sm font-medium text-ink-2">
                Network
              </label>
              <select
                id="send-network"
                value={network}
                onChange={(event) => {
                  setChosenNetwork(event.target.value);
                  setError("");
                }}
                className="w-full rounded-xl border border-line bg-canvas px-3 py-3 text-base text-ink"
              >
                {networks.length > 1 && <option value="">Choose a network</option>}
                {networks.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.name} (fee {formatAmount(option.fee_amount)} {asset})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div>
          <div className="mb-1.5 flex items-baseline justify-between gap-3">
            <label htmlFor="send-amount" className="text-sm font-medium text-ink-2">
              Amount
            </label>
            <p className="min-w-0 truncate text-sm text-ink-3">
              Available: {formatAmount(available)} {asset}
            </p>
          </div>
          <div className="flex gap-2">
            <input
              id="send-amount"
              inputMode="decimal"
              autoComplete="off"
              placeholder="0"
              value={amount}
              onChange={(event) => changeAmount(event.target.value)}
              className="w-full min-w-0 flex-1 rounded-xl border border-line bg-canvas px-3.5 py-3 text-base text-ink placeholder:text-ink-3"
            />
            <button
              type="button"
              onClick={applyMax}
              disabled={needsNetwork && !network}
              className="rounded-xl border border-line px-4 text-sm font-medium text-ink-2 hover:bg-surface-raised disabled:opacity-50"
            >
              Max
            </button>
          </div>
        </div>

        {currentEstimate && readyToEstimate && !estimate.error && (
          <dl
            aria-live="polite"
            className={`space-y-1.5 rounded-xl bg-canvas p-3 text-sm transition-opacity motion-reduce:transition-none ${
              typingAhead ? "opacity-50" : ""
            }`}
          >
            <div className="flex justify-between gap-4">
              <dt className="text-ink-3">{customer.full_name} gets</dt>
              <dd className="text-right font-medium break-words">
                {formatAmount(currentEstimate.amount)} {currentEstimate.asset}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-3">Network fee</dt>
              <dd className="text-right font-medium break-words">
                {Number(currentEstimate.fee_amount) > 0
                  ? `${formatAmount(currentEstimate.fee_amount)} ${currentEstimate.asset}`
                  : "Free"}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-3">You pay in total</dt>
              <dd className="text-right font-medium break-words">
                {formatAmount(currentEstimate.total)} {currentEstimate.asset}
              </dd>
            </div>
          </dl>
        )}

        {readyToEstimate && estimate.error && <ErrorNotice message={estimate.error} />}
        {insufficient && <ErrorNotice message={`You don't have enough ${asset} for this, including the fee.`} />}
        {error && <ErrorNotice message={error} />}

        <div className="grid grid-cols-[auto_1fr] gap-2">
          <button type="button" onClick={onBack} className="rounded-xl border border-line px-4 py-3 font-medium">
            Back
          </button>
          <button
            type="submit"
            disabled={!canReview}
            className="rounded-xl bg-accent px-4 py-3 font-semibold text-on-accent disabled:opacity-50"
          >
            {preparing ? "Locking your price…" : "Review payment"}
          </button>
        </div>
        <p className="text-center text-sm text-ink-3">Networks and fees are simulated.</p>
      </form>
    </Card>
  );
}
