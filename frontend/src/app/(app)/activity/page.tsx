"use client";

import { useState } from "react";

import { TransactionRow } from "@/components/transaction-row";
import { Card, ErrorNotice, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";

const FILTERS = [
  { value: "", label: "All" },
  { value: "buy", label: "Buy" },
  { value: "sell", label: "Sell" },
  { value: "swap", label: "Swap" },
  { value: "send", label: "Send" },
  { value: "receive", label: "Receive" },
];

export default function ActivityPage() {
  const [kind, setKind] = useState("");
  const { data, error, stale, retry } = usePolling(() => api.transactions({ kind, limit: 100 }), 10000, kind);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Activity</h1>

      <div role="group" aria-label="Filter by type" className="-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
        {FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={kind === value}
            onClick={() => setKind(value)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium ${
              kind === value ? "bg-surface-raised text-ink" : "text-ink-3 hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && !data && <ErrorNotice message={error} onRetry={retry} />}

      <Card>
        {!data && !error && <Skeleton className="h-48" />}
        {data?.length === 0 && !stale && (
          <p className="py-6 text-center text-ink-2">
            {kind ? "No transactions of this type." : "Nothing yet. Requests you approve will show up here."}
          </p>
        )}
        <ul className={`divide-y divide-line transition-opacity motion-reduce:transition-none ${stale ? "opacity-50" : ""}`}>
          {data?.map((transaction) => (
            <TransactionRow key={transaction.reference} transaction={transaction} />
          ))}
        </ul>
      </Card>
    </div>
  );
}
