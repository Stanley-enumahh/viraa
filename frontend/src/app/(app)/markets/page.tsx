"use client";

import Link from "next/link";

import { AssetBadge, Card, Change, ErrorNotice, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { formatNgn, formatUsd } from "@/lib/format";
import { usePolling } from "@/lib/use-polling";

export default function MarketsPage() {
  const { data, error, retry } = usePolling(api.prices, 5000);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Markets</h1>
        <p className="mt-1 text-ink-2">Simulated prices, updated every 5 seconds.</p>
      </div>

      {error && !data && <ErrorNotice message={error} onRetry={retry} />}

      <Card>
        {!data && !error && <Skeleton className="h-96" />}
        <ul className="divide-y divide-line">
          {data?.prices.map((price) => (
            <li key={price.symbol}>
              <Link href={`/markets/${price.symbol}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                <AssetBadge symbol={price.symbol} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{price.name}</p>
                  <p className="text-sm text-ink-3">{price.symbol}</p>
                </div>
                <div className="text-right">
                  <p className="font-medium tabular-nums">{formatUsd(price.price_usd)}</p>
                  <p className="text-sm text-ink-3 tabular-nums">{formatNgn(price.price_ngn)}</p>
                </div>
                <div className="w-16 text-right text-sm sm:w-20">
                  <Change value={price.change_24h_pct} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
