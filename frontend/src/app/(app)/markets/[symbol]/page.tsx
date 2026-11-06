"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { BackIcon } from "@/components/icons";
import { PriceChart, PriceTable } from "@/components/price-chart";
import { Card, Change, ErrorNotice, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { formatAmount, formatNgn, formatUsd } from "@/lib/format";
import type { HistoryRange } from "@/lib/types";
import { usePolling } from "@/lib/use-polling";

const RANGES: HistoryRange[] = ["1h", "24h", "7d", "30d"];

export default function CoinPage() {
  const symbol = useParams<{ symbol: string }>().symbol.toUpperCase();
  const [range, setRange] = useState<HistoryRange>("24h");

  const price = usePolling(() => api.price(symbol), 5000, symbol);
  const history = usePolling(() => api.history(symbol, range), range === "1h" ? 5000 : 30000, `${symbol}:${range}`);
  const portfolio = usePolling(api.portfolio, 5000);

  const holding = portfolio.data?.wallets.find((wallet) => wallet.asset === symbol);

  return (
    <div className="space-y-5">
      <Link href="/markets" className="-ml-1 inline-flex items-center gap-1 text-sm font-medium text-ink-2 hover:text-ink">
        <BackIcon />
        Markets
      </Link>

      {price.error && !price.data ? (
        price.error === "Not found." ? (
          <ErrorNotice message={`Vira doesn't list ${symbol}.`} />
        ) : (
          <ErrorNotice message={price.error} onRetry={price.retry} />
        )
      ) : (
        <section>
          <h1 className="text-ink-2">{price.data ? `${price.data.name} (${price.data.symbol})` : symbol}</h1>
          {price.data ? (
            <>
              <p className="mt-1 text-5xl font-semibold tracking-tight break-words">{formatUsd(price.data.price_usd)}</p>
              <p className="mt-1 flex flex-wrap gap-x-3 text-ink-2">
                <span>{formatNgn(price.data.price_ngn)}</span>
                <span>
                  <Change value={price.data.change_24h_pct} /> <span className="text-ink-3">in 24h</span>
                </span>
              </p>
            </>
          ) : (
            <Skeleton className="mt-2 h-14 w-64 max-w-full" />
          )}
        </section>
      )}

      {!(price.error && !price.data) && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Link
              href={`/trade?kind=buy&asset=${symbol}`}
              className="rounded-xl bg-accent px-4 py-2.5 text-center font-semibold text-on-accent"
            >
              Buy
            </Link>
            <Link href={`/trade?kind=sell&asset=${symbol}`} className="rounded-xl border border-line px-4 py-2.5 text-center font-medium">
              Sell
            </Link>
            <Link href={`/trade?kind=swap&asset=${symbol}`} className="rounded-xl border border-line px-4 py-2.5 text-center font-medium">
              Swap
            </Link>
          </div>

          <div role="group" aria-label="Chart range" className="flex gap-1">
            {RANGES.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={range === option}
                onClick={() => setRange(option)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                  range === option ? "bg-surface-raised text-ink" : "text-ink-3 hover:text-ink"
                }`}
              >
                {option.toUpperCase()}
              </button>
            ))}
          </div>

          <Card>
            {history.error && !history.data && <ErrorNotice message={history.error} onRetry={history.retry} />}
            {history.data ? (
              <>
                <PriceChart history={history.data} name={price.data?.name ?? symbol} stale={history.stale} />
                <PriceTable history={history.data} />
              </>
            ) : (
              !history.error && <Skeleton className="h-[280px]" />
            )}
          </Card>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Stat label={`High (${history.data?.range ?? range})`} value={history.data && formatUsd(history.data.high_usd)} />
            <Stat label={`Low (${history.data?.range ?? range})`} value={history.data && formatUsd(history.data.low_usd)} />
            <div className="col-span-2 sm:col-span-1">
              <Stat
                label="You hold"
                value={portfolio.data && `${formatAmount(holding?.balance ?? 0)} ${symbol}`}
                detail={holding ? formatNgn(holding.value_ngn) : undefined}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, detail }: { label: string; value?: string; detail?: string }) {
  return (
    <div className="h-full rounded-2xl border border-line bg-surface p-4">
      <p className="text-sm text-ink-3">{label}</p>
      <p className="mt-1 text-lg font-semibold break-words">{value ?? "–"}</p>
      {detail && <p className="text-sm text-ink-3">{detail}</p>}
    </div>
  );
}
