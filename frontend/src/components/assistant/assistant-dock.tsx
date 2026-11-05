"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";

import { AssistantController, type AssistantState } from "@/lib/assistant-controller";

import { CloseIcon, MicIcon, SendIcon, StopIcon } from "../icons";
import { DraftCard } from "./draft-card";

const SUGGESTIONS = [
  "Buy 20k naira of bitcoin",
  "What's the price of Solana?",
  "Swap half my ETH to USDT",
  "How much USDT do I have?",
];

function statusLabel({ status, handsFree, followUp }: AssistantState) {
  switch (status) {
    case "waiting":
      return handsFree && !followUp ? "Say “Hey Vira”" : "Listening…";
    case "recording":
      return "Hearing you…";
    case "thinking":
      return handsFree && !followUp ? "One moment…" : "Thinking…";
    case "speaking":
      return "Speaking…";
    default:
      return handsFree ? "Hands-free is on" : "Tap the mic or type";
  }
}

function micLabel({ status, handsFree }: AssistantState) {
  if (status === "recording") return "Finish speaking";
  if (status === "speaking") return "Stop speaking";
  if (status === "waiting" && !handsFree) return "Stop listening";
  if (status === "waiting") return "Talk now without the wake word";
  return "Start talking to Vira";
}

export function AssistantDock() {
  const [controller] = useState(() => new AssistantController());
  const state = useSyncExternalStore(controller.subscribe, controller.getState, controller.getState);
  const [text, setText] = useState("");
  const levelRings = useRef<HTMLElement[]>([]);
  const scrollArea = useRef<HTMLDivElement>(null);

  useEffect(() => {
    controller.setLevelListener((level) => {
      const scale = 1 + Math.min(level * 8, 0.6);
      levelRings.current.forEach((ring) => {
        ring.style.transform = `scale(${scale})`;
      });
    });
    return () => {
      controller.setLevelListener(null);
      controller.dispose();
    };
  }, [controller]);

  useEffect(() => {
    scrollArea.current?.scrollTo({ top: scrollArea.current.scrollHeight });
  }, [state.messages, state.openDraft?.draft.reference, state.panelOpen]);

  useEffect(() => {
    if (!state.panelOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") controller.setPanelOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [controller, state.panelOpen]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void controller.sendText(text);
    setText("");
  }

  const micActive = state.status === "waiting" || state.status === "recording";
  const busy = state.status === "thinking";

  const micButton = (size: "large" | "small") => (
    <button
      type="button"
      onClick={() => void controller.pressMic()}
      disabled={busy}
      aria-label={micLabel(state)}
      className={`relative grid shrink-0 place-items-center rounded-full bg-accent text-on-accent shadow-lg disabled:opacity-60 ${
        size === "large" ? "size-14" : "size-11"
      }`}
    >
      {micActive && (
        <span
          ref={(element) => {
            if (!element) return;
            levelRings.current.push(element);
            return () => {
              levelRings.current = levelRings.current.filter((ring) => ring !== element);
            };
          }}
          aria-hidden="true"
          className="absolute inset-0 rounded-full bg-accent/40 transition-transform duration-75 motion-reduce:hidden"
        />
      )}
      <span className="relative">{state.status === "recording" || state.status === "speaking" ? <StopIcon /> : <MicIcon />}</span>
    </button>
  );

  return (
    <>
      {!state.panelOpen && (
        <div className="fixed right-4 bottom-20 z-20 flex items-center gap-3 md:right-6 md:bottom-6">
          <button
            type="button"
            onClick={() => controller.setPanelOpen(true)}
            className="rounded-full border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-2 shadow-lg"
          >
            {state.openDraft ? "1 request waiting" : statusLabel(state)}
          </button>
          {micButton("large")}
        </div>
      )}

      {state.panelOpen && (
        <aside
          aria-label="Vira assistant"
          className="fixed inset-x-2 bottom-[70px] z-20 flex max-h-[calc(100dvh-90px)] flex-col rounded-2xl border border-line bg-surface shadow-2xl md:inset-x-auto md:right-6 md:bottom-6 md:max-h-[calc(100dvh-48px)] md:w-[400px]"
        >
          <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <h2 className="font-semibold">Vira</h2>
              <p role="status" className="truncate text-sm text-ink-2">
                {statusLabel(state)}
              </p>
            </div>
            <label className="ml-auto flex shrink-0 cursor-pointer items-center gap-2 text-sm text-ink-2">
              Hands-free
              <input
                type="checkbox"
                role="switch"
                checked={state.handsFree}
                onChange={(event) => void controller.setHandsFree(event.target.checked)}
                className="peer sr-only"
              />
              <span
                aria-hidden="true"
                className={`relative h-6 w-10 rounded-full transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent ${
                  state.handsFree ? "bg-accent" : "bg-line"
                }`}
              >
                <span
                  className={`absolute top-1 size-4 rounded-full bg-ink transition-[left] ${state.handsFree ? "left-5" : "left-1"}`}
                />
              </span>
            </label>
            <button
              type="button"
              onClick={() => controller.setPanelOpen(false)}
              aria-label="Close assistant"
              className="rounded-lg p-1.5 text-ink-2 hover:bg-surface-raised"
            >
              <CloseIcon />
            </button>
          </header>

          <div ref={scrollArea} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {state.messages.length === 0 && (
              <div>
                <p className="text-ink-2">Tell me what you want to do. Nothing happens until you approve it.</p>
                <ul className="mt-3 flex flex-wrap gap-2">
                  {SUGGESTIONS.map((suggestion) => (
                    <li key={suggestion}>
                      <button
                        type="button"
                        onClick={() => void controller.sendText(suggestion)}
                        className="rounded-full border border-line px-3 py-1.5 text-left text-sm text-ink-2 hover:bg-surface-raised"
                      >
                        {suggestion}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <ol aria-live="polite" className="space-y-2">
              {state.messages.map((message) => (
                <li key={message.id} className={message.from === "user" ? "flex justify-end" : "flex"}>
                  <p
                    className={`max-w-[85%] rounded-2xl px-3 py-2 break-words ${
                      message.from === "user" ? "bg-surface-raised" : "text-ink"
                    }`}
                  >
                    <span className="sr-only">{message.from === "user" ? "You: " : "Vira: "}</span>
                    {message.text}
                  </p>
                </li>
              ))}
            </ol>

            {state.openDraft && (
              <DraftCard
                key={state.openDraft.draft.reference}
                open={state.openDraft}
                onApprove={() => void controller.approve()}
                onReject={() => void controller.reject()}
                onDismiss={() => controller.dismissDraft()}
              />
            )}

            {state.notice && (
              <p role="alert" className="rounded-xl border border-down/40 bg-down/10 px-3 py-2 text-sm">
                {state.notice}
              </p>
            )}
          </div>

          <form onSubmit={submit} className="flex items-center gap-2 border-t border-line p-3">
            <label htmlFor="assistant-input" className="sr-only">
              Type a request
            </label>
            <input
              id="assistant-input"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Type a request"
              maxLength={500}
              autoComplete="off"
              className="min-w-0 flex-1 rounded-xl border border-line bg-canvas px-3 py-2.5 text-base placeholder:text-ink-3"
            />
            {text.trim() ? (
              <button
                type="submit"
                disabled={busy}
                aria-label="Send"
                className="grid size-11 shrink-0 place-items-center rounded-full bg-accent text-on-accent disabled:opacity-60"
              >
                <SendIcon />
              </button>
            ) : (
              micButton("small")
            )}
          </form>
        </aside>
      )}
    </>
  );
}
