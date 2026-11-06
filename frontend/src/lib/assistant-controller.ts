/**
 * Runs a conversation with Vira: mic, wake word, follow-ups, drafts and spoken replies.
 *
 * Nothing here can move funds on its own. The only route to the approve endpoint is
 * `approve()`, which is called from the approve button on the draft card.
 */

import { api, ApiError } from "./api";
import { SpeechSegmenter } from "./speech-segmenter";
import type { AssistantResult, Draft } from "./types";
import { FUNDS_CHANGED_EVENT } from "./use-polling";

const FOLLOW_UP_WAIT_MS = 8000;
const MAX_MESSAGES = 30;
// An empty WAV. Playing it during a click lets later replies play on strict mobile browsers.
const SILENT_AUDIO = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

export type AssistantStatus = "idle" | "waiting" | "recording" | "thinking" | "speaking";

export type ChatMessage = {
  id: number;
  from: "user" | "vira";
  text: string;
};

export type OpenDraft = {
  draft: Draft;
  deadline: number;
  phase: "open" | "approving" | "rejecting";
  error: string;
};

export type AssistantState = {
  panelOpen: boolean;
  status: AssistantStatus;
  handsFree: boolean;
  /** The next clip is an answer to Vira, so it doesn't need the wake word. */
  followUp: boolean;
  messages: ChatMessage[];
  openDraft: OpenDraft | null;
  notice: string;
};

const INITIAL_STATE: AssistantState = {
  panelOpen: false,
  status: "idle",
  handsFree: false,
  followUp: false,
  messages: [],
  openDraft: null,
  notice: "",
};

function micErrorMessage(error: unknown) {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError") return "Vira can't use your microphone. Allow access in your browser, or type instead.";
  if (name === "NotFoundError") return "No microphone found. You can type your request instead.";
  return "The microphone isn't available. You can type your request instead.";
}

/** Timed from when it arrived, so a wrong clock on this device can't change the countdown. */
export function openDraftFrom(draft: Draft): OpenDraft {
  const lifetime = new Date(draft.expires_at).getTime() - new Date(draft.created_at).getTime();
  return { draft, deadline: Date.now() + lifetime, phase: "open", error: "" };
}

export function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

export class AssistantController {
  private state = INITIAL_STATE;
  private listeners = new Set<() => void>();
  private levelListener: ((level: number) => void) | null = null;
  private segmenter: SpeechSegmenter | null = null;
  private audio: HTMLAudioElement | null = null;
  private stopPlayback: (() => void) | null = null;
  private speechRequest = 0;
  private messageId = 0;
  // Someone who typed may be somewhere quiet, so only voice requests get spoken replies.
  private lastRequestWasVoice = false;
  // Bumped by dispose(), so a reply arriving after logout is ignored.
  private generation = 0;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getState = () => this.state;

  setLevelListener(listener: ((level: number) => void) | null) {
    this.levelListener = listener;
  }

  private update(patch: Partial<AssistantState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  private addMessage(from: ChatMessage["from"], text: string) {
    this.messageId += 1;
    const messages = [...this.state.messages, { id: this.messageId, from, text }].slice(-MAX_MESSAGES);
    this.update({ messages });
  }

  setPanelOpen(panelOpen: boolean) {
    this.update({ panelOpen });
  }

  dismissNotice() {
    this.update({ notice: "" });
  }

  // Microphone

  private async openMic() {
    if (this.segmenter) return true;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      this.update({ notice: "This browser can't record audio here. Use HTTPS or localhost, or type instead." });
      return false;
    }
    const segmenter = new SpeechSegmenter({
      onSpeechStart: () => this.update({ status: "recording" }),
      onSegment: (clip) => void this.handleClip(clip),
      onDiscard: () => this.update({ status: "waiting" }),
      onWaitTimeout: () => this.handleWaitTimeout(),
      onLevel: (level) => this.levelListener?.(level),
    });
    try {
      await segmenter.open();
    } catch (error) {
      segmenter.close();
      this.update({ notice: micErrorMessage(error), handsFree: false, status: "idle" });
      return false;
    }
    this.segmenter = segmenter;
    return true;
  }

  private closeMic() {
    this.segmenter?.close();
    this.segmenter = null;
  }

  private listen() {
    const { handsFree, followUp } = this.state;
    this.update({ status: "waiting" });
    this.segmenter?.listen(handsFree && !followUp ? null : FOLLOW_UP_WAIT_MS);
  }

  /** After a reply: keep listening if the conversation continues, otherwise switch the mic off. */
  private resume() {
    const { handsFree, followUp } = this.state;
    if (this.segmenter && (handsFree || followUp)) {
      this.listen();
    } else {
      this.closeMic();
      this.update({ status: "idle", followUp: false });
    }
  }

  private handleWaitTimeout() {
    const { handsFree, followUp } = this.state;
    if (handsFree) {
      this.update({ followUp: false });
      this.listen();
      return;
    }
    if (!followUp) this.update({ notice: "I didn't hear anything. Tap the mic and try again." });
    this.closeMic();
    this.update({ status: "idle", followUp: false });
  }

  /** The mic button. What it does depends on what's happening right now. */
  async pressMic() {
    this.unlockAudio();
    this.update({ panelOpen: true, notice: "" });
    const { status, handsFree } = this.state;

    if (status === "recording") {
      this.segmenter?.finish();
    } else if (status === "speaking") {
      this.interruptSpeech();
    } else if (status === "waiting" && handsFree) {
      // Talk now, without saying the wake word.
      this.update({ followUp: true });
      this.listen();
    } else if (status === "waiting") {
      this.closeMic();
      this.update({ status: "idle", followUp: false });
    } else if (status === "idle" && (await this.openMic())) {
      this.listen();
    }
  }

  async setHandsFree(enabled: boolean) {
    this.unlockAudio();
    this.update({ notice: "", handsFree: enabled, followUp: false });
    if (!enabled) {
      if (this.state.status === "waiting" || this.state.status === "recording") {
        this.closeMic();
        this.update({ status: "idle" });
      }
      return;
    }
    if (this.state.status === "idle" && (await this.openMic())) this.listen();
  }

  // Conversation

  private async handleClip(clip: Blob) {
    const generation = this.generation;
    const needsWakeWord = this.state.handsFree && !this.state.followUp;
    this.update({ status: "thinking", followUp: false });
    try {
      const result = await api.voice(clip, needsWakeWord);
      if (generation !== this.generation) return;
      await this.handleResult(result, true);
    } catch (error) {
      if (generation !== this.generation) return;
      this.update({ notice: errorMessage(error) });
    }
    if (generation === this.generation) this.resume();
  }

  async sendText(text: string) {
    const trimmed = text.trim();
    if (!trimmed || this.state.status === "thinking" || this.state.status === "recording") return;
    const generation = this.generation;
    this.interruptSpeech();
    this.segmenter?.pause();
    this.addMessage("user", trimmed);
    this.update({ status: "thinking", notice: "", panelOpen: true, followUp: false });
    try {
      const result = await api.command(trimmed);
      if (generation !== this.generation) return;
      await this.handleResult(result, false);
    } catch (error) {
      if (generation !== this.generation) return;
      this.update({ notice: errorMessage(error) });
    }
    if (generation === this.generation) this.resume();
  }

  private async handleResult(result: AssistantResult, spoken: boolean) {
    if (result.type === "ignored") return;

    this.lastRequestWasVoice = spoken;
    // A request can change what's on the page behind the dock, such as adding a customer.
    window.dispatchEvent(new Event(FUNDS_CHANGED_EVENT));
    if (spoken && result.transcript && result.type !== "listening") this.addMessage("user", result.transcript);
    this.addMessage("vira", result.reply);
    this.update({ panelOpen: true, followUp: spoken && (result.type === "question" || result.type === "listening") });

    if (result.draft) {
      this.showDraft(result.draft);
    } else {
      await this.syncOpenDraft();
    }
    if (spoken) await this.speak(result.reply);
  }

  private showDraft(draft: Draft) {
    this.update({ openDraft: openDraftFrom(draft) });
  }

  /** The user may have cancelled the open draft by voice. */
  private async syncOpenDraft() {
    const open = this.state.openDraft;
    if (!open || open.phase !== "open") return;
    try {
      const draft = await api.draft(open.draft.reference);
      if (draft.status === "rejected" && this.state.openDraft?.draft.reference === draft.reference) {
        this.update({ openDraft: null });
      }
    } catch {
      // The card keeps showing, and approving it will report any problem.
    }
  }

  // Approval

  async approve() {
    const open = this.state.openDraft;
    if (!open || open.phase !== "open") return;
    this.unlockAudio();
    this.update({ openDraft: { ...open, phase: "approving", error: "" } });
    try {
      const { reply } = await api.approveDraft(open.draft.reference);
      this.update({ openDraft: null });
      this.addMessage("vira", reply);
      window.dispatchEvent(new Event(FUNDS_CHANGED_EVENT));
      if (this.lastRequestWasVoice) await this.speakBetweenTurns(reply);
    } catch (error) {
      // The backend closes a draft it couldn't run, so the card can't be retried.
      if (this.state.openDraft?.draft.reference === open.draft.reference) {
        this.update({ openDraft: null });
      }
      this.addMessage("vira", errorMessage(error));
    }
  }

  async reject() {
    const open = this.state.openDraft;
    if (!open || open.phase !== "open") return;
    this.update({ openDraft: { ...open, phase: "rejecting", error: "" } });
    try {
      const { reply } = await api.rejectDraft(open.draft.reference);
      this.addMessage("vira", reply);
    } catch (error) {
      this.addMessage("vira", errorMessage(error));
    }
    if (this.state.openDraft?.draft.reference === open.draft.reference) this.update({ openDraft: null });
  }

  dismissDraft() {
    this.update({ openDraft: null });
  }

  // Spoken replies

  private unlockAudio() {
    if (!this.audio) this.audio = new Audio();
    if (this.state.status === "speaking") return;
    this.audio.src = SILENT_AUDIO;
    void this.audio.play().catch(() => {});
  }

  /** Speak outside a voice turn. Skipped if the user is mid-sentence or Vira is already busy. */
  private async speakBetweenTurns(text: string) {
    if (this.state.status !== "idle" && this.state.status !== "waiting") return;
    const generation = this.generation;
    await this.speak(text);
    // A new turn may have started while this played. That turn will resume when it finishes.
    if (generation === this.generation && this.getState().status === "speaking") this.resume();
  }

  /** Vira's reply is already on screen, so failing to voice it is not worth an error. */
  private async speak(text: string) {
    const generation = this.generation;
    this.speechRequest += 1;
    const request = this.speechRequest;
    // Pause the mic, or Vira would hear herself.
    this.segmenter?.pause();
    this.update({ status: "speaking" });
    try {
      const clip = await api.speak(text);
      if (generation !== this.generation || request !== this.speechRequest) return;
      await this.play(clip);
    } catch {
      // Text only for this reply.
    }
  }

  private async play(clip: Blob) {
    const audio = this.audio ?? new Audio();
    this.audio = audio;
    const url = URL.createObjectURL(clip);
    await new Promise<void>((resolve) => {
      this.stopPlayback = resolve;
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      audio.src = url;
      audio.play().catch(() => resolve());
    });
    this.stopPlayback = null;
    audio.onended = null;
    audio.onerror = null;
    URL.revokeObjectURL(url);
  }

  private interruptSpeech() {
    this.speechRequest += 1;
    this.audio?.pause();
    this.stopPlayback?.();
  }

  /** Called when leaving the logged-in app. Always releases the mic. */
  dispose() {
    this.generation += 1;
    this.interruptSpeech();
    this.closeMic();
    this.state = { ...INITIAL_STATE };
    this.listeners.forEach((listener) => listener());
  }
}
