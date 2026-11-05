import type { InputHTMLAttributes, ReactNode } from "react";

import { formatChange } from "@/lib/format";

export function Card({ title, action, children }: { title?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-surface p-4 sm:p-5">
      {title && (
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium text-ink-2">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function AssetBadge({ symbol }: { symbol: string }) {
  return (
    <span
      aria-hidden="true"
      className="grid size-10 shrink-0 place-items-center rounded-full bg-surface-raised text-[11px] font-semibold tracking-tight text-ink-2"
    >
      {symbol}
    </span>
  );
}

export function Change({ value }: { value: string }) {
  const amount = Number(value);
  const tone = amount > 0 ? "text-up" : amount < 0 ? "text-down" : "text-ink-3";
  return <span className={`tabular-nums ${tone}`}>{formatChange(value)}</span>;
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-down/40 bg-down/10 px-4 py-3 text-sm">
      <span>{message}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="font-medium underline underline-offset-4">
          Try again
        </button>
      )}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-lg bg-surface-raised motion-reduce:animate-none ${className}`} />;
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  errors?: string[];
  hint?: string;
};

export function Field({ label, errors, hint, id, ...input }: FieldProps) {
  const describedBy = errors?.length ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink-2">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={Boolean(errors?.length)}
        aria-describedby={describedBy}
        className="w-full rounded-xl border border-line bg-canvas px-3.5 py-3 text-base text-ink placeholder:text-ink-3 aria-invalid:border-down"
        {...input}
      />
      {hint && !errors?.length && (
        <p id={`${id}-hint`} className="mt-1.5 text-sm text-ink-3">
          {hint}
        </p>
      )}
      {Boolean(errors?.length) && (
        <div id={`${id}-error`} className="mt-1.5 space-y-1 text-sm text-down">
          {errors?.map((error) => <p key={error}>{error}</p>)}
        </div>
      )}
    </div>
  );
}
