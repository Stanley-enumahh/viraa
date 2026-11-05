/**
 * Opens the microphone and cuts what it hears into clips of speech.
 *
 * Detection runs on the device, so nothing leaves the browser until someone has
 * spoken. The recorder hears the mic slightly delayed, so the first syllable that
 * triggered detection is still in the clip ("Hey" in "Hey Vira").
 */

const TICK_MS = 50;
const PRE_ROLL_SECONDS = 0.4;
const MIN_THRESHOLD = 0.015;
const NOISE_MULTIPLIER = 3;
const FRAMES_TO_START = 3;
const SILENCE_TO_STOP_MS = 900;
const MAX_CLIP_MS = 12000;
const MIN_SPEECH_MS = 250;

type Phase = "closed" | "paused" | "waiting" | "recording";

export type SegmenterHandlers = {
  onSpeechStart: () => void;
  onSegment: (clip: Blob) => void;
  /** A clip turned out to be a click or a cough, so listening carried on. */
  onDiscard: () => void;
  onWaitTimeout: () => void;
  onLevel: (level: number) => void;
};

function pickMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

export class SpeechSegmenter {
  private phase: Phase = "closed";
  private stream?: MediaStream;
  private context?: AudioContext;
  private analyser?: AnalyserNode;
  private delayed?: MediaStreamAudioDestinationNode;
  private recorder?: MediaRecorder;
  private timer?: ReturnType<typeof setInterval>;
  private samples = new Float32Array(1024);

  private noiseFloor = 0.005;
  private loudFrames = 0;
  private waitStartedAt = 0;
  private waitTimeoutMs: number | null = null;
  private clipStartedAt = 0;
  private lastLoudAt = 0;
  private speechMs = 0;
  private discardNextClip = false;

  constructor(private handlers: SegmenterHandlers) {}

  async open() {
    if (this.phase !== "closed") return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.context = new AudioContext();
    await this.context.resume();

    const source = this.context.createMediaStreamSource(this.stream);
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = this.samples.length;
    source.connect(this.analyser);

    const delay = this.context.createDelay(1);
    delay.delayTime.value = PRE_ROLL_SECONDS;
    this.delayed = this.context.createMediaStreamDestination();
    source.connect(delay).connect(this.delayed);

    this.phase = "paused";
    this.timer = setInterval(() => this.tick(), TICK_MS);
  }

  /** Wait for the next clip of speech. Passing a timeout gives up if nobody speaks. */
  listen(waitTimeoutMs: number | null) {
    if (this.phase === "closed") return;
    this.cancelRecording();
    this.phase = "waiting";
    this.loudFrames = 0;
    this.waitStartedAt = performance.now();
    this.waitTimeoutMs = waitTimeoutMs;
  }

  /** Stop listening for now and throw away anything being recorded. */
  pause() {
    if (this.phase === "closed") return;
    this.cancelRecording();
    this.phase = "paused";
    this.handlers.onLevel(0);
  }

  /** The user is done talking, so send what we have without waiting for silence. */
  finish() {
    if (this.phase === "recording") this.stopRecording();
  }

  close() {
    clearInterval(this.timer);
    this.cancelRecording();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close().catch(() => {});
    this.stream = undefined;
    this.context = undefined;
    this.phase = "closed";
    this.handlers.onLevel(0);
  }

  private currentLevel() {
    if (!this.analyser) return 0;
    this.analyser.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (const sample of this.samples) sum += sample * sample;
    return Math.sqrt(sum / this.samples.length);
  }

  private tick() {
    if (this.phase !== "waiting" && this.phase !== "recording") return;
    const level = this.currentLevel();
    const now = performance.now();
    const threshold = Math.max(MIN_THRESHOLD, this.noiseFloor * NOISE_MULTIPLIER);
    this.handlers.onLevel(level);

    if (this.phase === "waiting") {
      if (level > threshold) {
        this.loudFrames += 1;
        if (this.loudFrames >= FRAMES_TO_START) {
          this.startRecording(now);
          this.handlers.onSpeechStart();
        }
      } else {
        this.loudFrames = 0;
        this.noiseFloor = this.noiseFloor * 0.95 + level * 0.05;
        if (this.waitTimeoutMs !== null && now - this.waitStartedAt > this.waitTimeoutMs) {
          this.phase = "paused";
          this.handlers.onWaitTimeout();
        }
      }
      return;
    }

    if (level > threshold * 0.7) {
      this.lastLoudAt = now;
      this.speechMs += TICK_MS;
    }
    if (now - this.lastLoudAt > SILENCE_TO_STOP_MS || now - this.clipStartedAt > MAX_CLIP_MS) {
      this.stopRecording();
    }
  }

  private startRecording(now: number) {
    if (!this.delayed) return;
    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(this.delayed.stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      if (this.discardNextClip) {
        this.discardNextClip = false;
        return;
      }
      if (this.speechMs < MIN_SPEECH_MS) {
        this.phase = "waiting";
        this.loudFrames = 0;
        this.waitStartedAt = performance.now();
        this.handlers.onDiscard();
        return;
      }
      this.handlers.onSegment(new Blob(chunks, { type: recorder.mimeType }));
    };
    recorder.start();
    this.recorder = recorder;
    this.phase = "recording";
    this.clipStartedAt = now;
    this.lastLoudAt = now;
    this.speechMs = 0;
  }

  private stopRecording() {
    this.phase = "paused";
    if (this.recorder?.state === "recording") this.recorder.stop();
    this.recorder = undefined;
  }

  private cancelRecording() {
    if (this.recorder?.state === "recording") {
      this.discardNextClip = true;
      this.recorder.stop();
    }
    this.recorder = undefined;
  }
}
