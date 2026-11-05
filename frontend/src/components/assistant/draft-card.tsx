"use client";

import { useEffect, useState } from "react";

import type { OpenDraft } from "@/lib/assistant-controller";
import { formatAmount } from "@/lib/format";
import type { Draft } from "@/lib/types";

const ACTION_TITLES: Record<Draft["action"], string> = {
  buy: "Approve this purchase?",
  sell: "Approve this sale?",
  swap: "Approve this swap?",
  send: "Approve this transfer?",
};

function detailRows({ action, quote }: Draft): [string, string][] {
  if (action === "send") {
    const to = quote.recipient ? `${quote.recipient_name} (@${quote.recipient})` : `Address ending ${quote.address?.slice(-4)}`;
    const rows: [string, string][] = [
      ["Send", `${formatAmount(quote.amount)} ${quote.asset}`],
      ["To", to],
    ];
    if (Number(quote.fee_amount) > 0) {
      rows.push(["Network fee", `${formatAmount(quote.fee_amount)} ${quote.asset}`]);
      rows.push(["Total", `${formatAmount(quote.total)} ${quote.asset}`]);
    } else {
      rows.push(["Fee", "Free"]);
    }
    return rows;
  }

  const [base, counter, price] =
    action === "buy"
      ? [quote.to_asset, quote.from_asset, 1 / Number(quote.rate)]
      : [quote.from_asset, quote.to_asset, Number(quote.rate)];
  return [
    ["You pay", `${formatAmount(quote.from_amount)} ${quote.from_asset}`],
    ["You get", `${formatAmount(quote.to_amount)} ${quote.to_asset}`],
    ["Fee (included)", `${formatAmount(quote.fee_amount)} ${quote.fee_asset}`],
    ["Locked price", `1 ${base} = ${price >= 1 ? price.toLocaleString("en-US", { maximumFractionDigits: 2 }) : formatAmount(price)} ${counter}`],
  ];
}

type DraftCardProps = {
  open: OpenDraft;
  onApprove: () => void;
  onReject: () => void;
  onDismiss: () => void;
};

export function DraftCard({ open, onApprove, onReject, onDismiss }: DraftCardProps) {
  const { draft, deadline, phase } = open;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, []);

  const secondsLeft = Math.max(0, Math.ceil((deadline - now) / 1000));
  const expired = secondsLeft === 0;
  const busy = phase !== "open";
  const totalSeconds = Math.max(1, (new Date(draft.expires_at).getTime() - new Date(draft.created_at).getTime()) / 1000);

  return (
    <section aria-label="Request waiting for approval" className="rounded-xl border border-accent/50 bg-surface-raised p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-semibold">{ACTION_TITLES[draft.action]}</h3>
        <span className="shrink-0 text-sm text-ink-2 tabular-nums">{expired ? "Expired" : `${secondsLeft}s left`}</span>
      </div>

      <div aria-hidden="true" className="mt-2 h-1 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-200 ease-linear motion-reduce:transition-none"
          style={{ width: `${Math.min(100, (secondsLeft / totalSeconds) * 100)}%` }}
        />
      </div>

      <dl className="mt-3 space-y-1.5 text-sm">
        {detailRows(draft).map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4">
            <dt className="shrink-0 text-ink-3">{label}</dt>
            <dd className="min-w-0 text-right font-medium break-words">{value}</dd>
          </div>
        ))}
      </dl>

      {expired && !busy ? (
        <div className="mt-4">
          <p className="text-sm text-ink-2">This price expired, so nothing was done. Ask again for a fresh price.</p>
          <button type="button" onClick={onDismiss} className="mt-3 w-full rounded-xl border border-line px-4 py-2.5 font-medium">
            Dismiss
          </button>
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onReject}
            disabled={busy}
            className="rounded-xl border border-line px-4 py-2.5 font-medium disabled:opacity-60"
          >
            {phase === "rejecting" ? "Cancelling…" : "Reject"}
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={busy}
            className="rounded-xl bg-accent px-4 py-2.5 font-semibold text-on-accent disabled:opacity-60"
          >
            {phase === "approving" ? "Approving…" : "Approve"}
          </button>
        </div>
      )}
    </section>
  );
}
