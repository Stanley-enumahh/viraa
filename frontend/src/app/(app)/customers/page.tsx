"use client";

import { useState, type FormEvent } from "react";

import { Card, ErrorNotice, Field, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/assistant-controller";
import type { Customer } from "@/lib/types";
import { usePolling } from "@/lib/use-polling";

import { SendForm } from "./send-form";

function AddCustomer({ onAdded }: { onAdded: () => void }) {
  const [username, setUsername] = useState("");
  const [found, setFound] = useState<{ username: string; full_name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function find(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setFound(await api.lookupCustomer(username));
    } catch (caught) {
      setError(errorMessage(caught));
    }
    setBusy(false);
  }

  async function add() {
    if (!found) return;
    setBusy(true);
    setError("");
    try {
      await api.addCustomer(found.username);
      setUsername("");
      onAdded();
    } catch (caught) {
      setError(errorMessage(caught));
    }
    setFound(null);
    setBusy(false);
  }

  return (
    <Card title="Add a customer">
      {found ? (
        <div>
          <p className="text-ink-2">Is this the right person?</p>
          <p className="mt-1 text-lg font-semibold">{found.full_name}</p>
          <p className="text-sm text-ink-3">@{found.username}</p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setFound(null)}
              disabled={busy}
              className="rounded-xl border border-line px-4 py-2.5 font-medium disabled:opacity-60"
            >
              Back
            </button>
            <button
              type="button"
              onClick={() => void add()}
              disabled={busy}
              className="rounded-xl bg-accent px-4 py-2.5 font-semibold text-on-accent disabled:opacity-60"
            >
              {busy ? "Adding…" : "Add customer"}
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={find} className="space-y-3">
          <Field
            id="customer-username"
            label="Their Vira username"
            placeholder="tunde"
            autoComplete="off"
            autoCapitalize="none"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <button
            type="submit"
            disabled={busy || !username.trim()}
            className="w-full rounded-xl bg-accent px-4 py-2.5 font-semibold text-on-accent disabled:opacity-50"
          >
            {busy ? "Looking…" : "Find"}
          </button>
        </form>
      )}
      {error && (
        <div className="mt-3">
          <ErrorNotice message={error} />
        </div>
      )}
    </Card>
  );
}

export default function CustomersPage() {
  const { data, error, retry } = usePolling(api.customers, 15000);
  const [paying, setPaying] = useState<Customer | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);
  const [removeError, setRemoveError] = useState("");

  async function remove(customer: Customer) {
    setRemoving(customer.id);
    setRemoveError("");
    try {
      await api.removeCustomer(customer.id);
      retry();
    } catch (caught) {
      setRemoveError(errorMessage(caught));
    }
    setRemoving(null);
  }

  if (paying) {
    return (
      <div className="mx-auto max-w-xl space-y-5">
        <h1 className="text-2xl font-semibold tracking-tight">Pay {paying.full_name}</h1>
        <SendForm customer={paying} onBack={() => setPaying(null)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Customers</h1>
        <p className="mt-1 text-ink-2">Save anyone on Vira by username, then pay them on the network you choose.</p>
      </div>

      <AddCustomer onAdded={retry} />

      {error && !data && <ErrorNotice message={error} onRetry={retry} />}
      {removeError && <ErrorNotice message={removeError} />}

      <Card title="Your customers">
        {!data && !error && <Skeleton className="h-24" />}
        {data?.length === 0 && <p className="py-3 text-ink-2">Nobody yet. Add someone above, or say “Add tunde as a customer”.</p>}
        <ul className="divide-y divide-line">
          {data?.map((customer) => (
            <li key={customer.id} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{customer.full_name}</p>
                <p className="truncate text-sm text-ink-3">@{customer.username}</p>
              </div>
              <button
                type="button"
                onClick={() => void remove(customer)}
                disabled={removing === customer.id}
                aria-label={`Remove ${customer.full_name}`}
                className="rounded-lg px-2 py-1.5 text-sm font-medium text-ink-3 hover:text-ink disabled:opacity-60"
              >
                Remove
              </button>
              <button
                type="button"
                onClick={() => setPaying(customer)}
                aria-label={`Pay ${customer.full_name}`}
                className="rounded-xl bg-accent px-4 py-2 font-semibold text-on-accent"
              >
                Pay
              </button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
