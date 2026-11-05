"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

/** Fired after an approved request, so balances update right away instead of on the next poll. */
export const FUNDS_CHANGED_EVENT = "vira:funds-changed";

type PollState<T> = {
  data?: T;
  error?: string;
  loadedKey?: string;
};

/**
 * Fetches now and then every `intervalMs`, pausing while the tab is hidden.
 * Old data stays on screen during a refetch or when `key` changes: `stale` says it
 * belongs to the previous key, so charts can dim instead of flashing a skeleton.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number, key = "") {
  const [state, setState] = useState<PollState<T>>({});
  const [attempt, setAttempt] = useState(0);
  const latestFetcher = useRef(fetcher);

  useEffect(() => {
    latestFetcher.current = fetcher;
  });

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const load = async (force: boolean) => {
      if (force || !document.hidden) {
        try {
          const data = await latestFetcher.current();
          if (active) setState({ data, loadedKey: key });
        } catch (error) {
          const message = error instanceof ApiError ? error.message : "Something went wrong.";
          if (active) setState((previous) => ({ ...previous, error: message }));
        }
      }
      if (active) timer = setTimeout(() => load(false), intervalMs);
    };

    load(true);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [intervalMs, key, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    window.addEventListener(FUNDS_CHANGED_EVENT, retry);
    return () => window.removeEventListener(FUNDS_CHANGED_EVENT, retry);
  }, [retry]);

  return {
    data: state.data,
    error: state.error,
    stale: state.data !== undefined && state.loadedKey !== key,
    retry,
  };
}
