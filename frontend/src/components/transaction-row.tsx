import { formatDateTime } from "@/lib/format";
import type { Transaction, TransactionKind } from "@/lib/types";

import { InIcon, OutIcon, SwapIcon } from "./icons";

const KIND_ICONS: Record<TransactionKind, () => React.ReactNode> = {
  buy: InIcon,
  receive: InIcon,
  sell: OutIcon,
  send: OutIcon,
  swap: SwapIcon,
};

export function TransactionRow({ transaction }: { transaction: Transaction }) {
  const Icon = KIND_ICONS[transaction.kind];
  return (
    <li className="flex items-center gap-3 py-3">
      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-surface-raised text-ink-2">
        <Icon />
      </span>
      <div className="min-w-0">
        <p className="break-words">{transaction.summary}</p>
        <p className="text-sm text-ink-3">{formatDateTime(transaction.created_at)}</p>
      </div>
    </li>
  );
}
