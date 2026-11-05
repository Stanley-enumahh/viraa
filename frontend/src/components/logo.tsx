export function Logo() {
  return (
    <span className="inline-flex items-center gap-2 text-lg font-semibold tracking-tight">
      <svg aria-hidden="true" viewBox="0 0 32 32" className="size-7">
        <rect width="32" height="32" rx="8" fill="var(--accent)" />
        <path
          d="M9 10l7 13 7-13"
          fill="none"
          stroke="var(--on-accent)"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      Vira
    </span>
  );
}
