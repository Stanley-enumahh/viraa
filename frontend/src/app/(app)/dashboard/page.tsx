"use client";

import Link from "next/link";

import { TransactionRow } from "@/components/transaction-row";
import { AssetBadge, Card, Change, ErrorNotice, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatAmount, formatNgn, formatUsd } from "@/lib/format";
import { usePolling } from "@/lib/use-polling";

const MARKET_PREVIEW = 4;

function ViewAll({ href }: { href: string }) {
  return (
    <Link href={href} className="text-sm font-medium text-ink-2 underline-offset-4 hover:underline">
      View all
    </Link>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const portfolio = usePolling(api.portfolio, 5000);
  const prices = usePolling(api.prices, 5000);
  const activity = usePolling(() => api.transactions({ limit: 5 }), 10000);

  const holdings = [...(portfolio.data?.wallets ?? [])]
    .filter((wallet) => Number(wallet.balance) > 0)
    .sort((a, b) => Number(b.value_usd) - Number(a.value_usd));

  const movers = [...(prices.data?.prices ?? [])]
    .filter((price) => price.symbol !== "USDT")
    .sort((a, b) => Math.abs(Number(b.change_24h_pct)) - Math.abs(Number(a.change_24h_pct)))
    .slice(0, MARKET_PREVIEW);

  return (
    <div className="space-y-5">
      {portfolio.error && !portfolio.data && <ErrorNotice message={portfolio.error} onRetry={portfolio.retry} />}

      <section aria-label="Portfolio value" className="py-2">
        <p className="text-ink-2">Hi {user?.full_name.split(" ")[0]}, your portfolio is worth</p>
        {portfolio.data ? (
          <>
            <p className="mt-1 text-5xl font-semibold tracking-tight break-words sm:text-6xl">
              {formatNgn(portfolio.data.total_ngn)}
            </p>
            <p className="mt-1 text-lg text-ink-2">about {formatUsd(portfolio.data.total_usd)}</p>
          </>
        ) : (
          !portfolio.error && (
            <div className="mt-2 space-y-2">
              <Skeleton className="h-14 w-64 max-w-full" />
              <Skeleton className="h-6 w-32" />
            </div>
          )
        )}
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card title="Your assets">
          {!portfolio.data && !portfolio.error && <Skeleton className="h-40" />}
          {portfolio.data && holdings.length === 0 && <p className="py-3 text-ink-2">You don&apos;t hold any assets yet.</p>}
          <ul className="divide-y divide-line">
            {holdings.map((wallet) => {
              const row = (
                <>
                  <AssetBadge symbol={wallet.asset} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{wallet.name}</p>
                    <p className="truncate text-sm text-ink-3">
                      {formatAmount(wallet.balance)} {wallet.asset}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium tabular-nums">{formatNgn(wallet.value_ngn)}</p>
                    <p className="text-sm text-ink-3 tabular-nums">{formatUsd(wallet.value_usd)}</p>
                  </div>
                </>
              );
              return (
                <li key={wallet.asset}>
                  {wallet.asset === "NGN" ? (
                    <div className="flex items-center gap-3 py-3">{row}</div>
                  ) : (
                    <Link href={`/markets/${wallet.asset}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                      {row}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>

        <div className="space-y-5">
          <Card title="Biggest movers today" action={<ViewAll href="/markets" />}>
            {prices.error && !prices.data && <ErrorNotice message={prices.error} onRetry={prices.retry} />}
            {!prices.data && !prices.error && <Skeleton className="h-40" />}
            <ul className="divide-y divide-line">
              {movers.map((price) => (
                <li key={price.symbol}>
                  <Link href={`/markets/${price.symbol}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                    <AssetBadge symbol={price.symbol} />
                    <p className="min-w-0 flex-1 truncate font-medium">{price.name}</p>
                    <div className="text-right">
                      <p className="font-medium tabular-nums">{formatUsd(price.price_usd)}</p>
                      <p className="text-sm">
                        <Change value={price.change_24h_pct} />
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Recent activity" action={<ViewAll href="/activity" />}>
            {activity.error && !activity.data && <ErrorNotice message={activity.error} onRetry={activity.retry} />}
            {!activity.data && !activity.error && <Skeleton className="h-24" />}
            {activity.data?.length === 0 && (
              <p className="py-3 text-ink-2">Nothing yet. Requests you approve will show up here.</p>
            )}
            <ul className="divide-y divide-line">
              {activity.data?.map((transaction) => (
                <TransactionRow key={transaction.reference} transaction={transaction} />
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
