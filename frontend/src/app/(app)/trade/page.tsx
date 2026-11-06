import { Suspense } from "react";

import { TradeForm } from "./trade-form";

export default function TradePage() {
  return (
    <div className="mx-auto max-w-xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Trade</h1>
      <Suspense>
        <TradeForm />
      </Suspense>
    </div>
  );
}
