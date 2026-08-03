/**
 * Session controller: bootstrap, backend discovery, capture lifecycle.
 *
 * Owns the non-serializable runtime resources (transport, capture loop,
 * webcam handle) in module scope and mirrors observable status into the
 * store. Every teardown path stops media tracks (CAP-002) and finishes the
 * backend capture session.
 */

import { create } from "zustand";

import {
  establishSession,
  probeExistingSession,
  readBootstrapFragment,
  scrubFragment,
} from "../lib/api/bootstrap";
import {
  api,
  resolveWsUrl,
  type SystemResponse,
} from "../lib/api/http";
import { createCaptureLoop, type CaptureLoop } from "../lib/live/captureLoop";
import {
  DEFAULT_LIVE_PROMPTS,
  normalizeObjectPrompts,
  SYNTHETIC_PROMPTS,
} from "../lib/live/prompts";
import {
  createSyntheticDesk,
  videoFrameSource,
} from "../lib/live/syntheticDesk";
import { MockTransport } from "../lib/live/mock/mockTransport";
import { MOCK_SCENE_ID } from "../lib/live/mock/mockWorld";
import {
  WsTransport,
  type LiveTransport,
} from "../lib/live/transport";
import {
  acquireWebcam,
  WebcamError,
  type WebcamHandle,
} from "../lib/live/webcam";
import type {
  CommandInput,
  CommandResult,
  FrameResult,
  ProviderMode,
} from "../lib/protocol/messages";
import { useWorldStore } from "./worldStore";

export type SourceKind = "webcam" | "synthetic";

export type BackendStatus =
  | "probing"
  | "ready"
  | "unauthenticated"
  | "unreachable";

export type LiveStatus = "idle" | "starting" | "live" | "stopping" | "error";

export type SessionState = {
  backendStatus: BackendStatus;
  authenticated: boolean;
  canMutate: boolean;
  system: SystemResponse | null;
  mode: "backend" | "simulation" | null;
  providerMode: ProviderMode | null;
  liveStatus: LiveStatus;
  sourceKind: SourceKind | null;
  sceneId: string | null;
  sceneName: string | null;
  captureSessionId: string | null;
  liveError: string | null;
  bootstrapMessage: string | null;
  previewCanvas: HTMLCanvasElement | null;
  webcamVideo: HTMLVideoElement | null;
  objectPrompts: string[];
  setObjectPrompts: (prompts: string[]) => void;
  initialize: () => Promise<void>;
  enterSimulation: () => void;
  startLive: (source: SourceKind) => Promise<void>;
  stopLive: () => Promise<void>;
  submitCommand: (input: CommandInput) => Promise<CommandResult | null>;
};

type Runtime = {
  transport: LiveTransport | null;
  loop: CaptureLoop | null;
  webcam: WebcamHandle | null;
  unsubscribe: (() => void) | null;
  presentationTimer: number | null;
  pendingPresentation: FrameResult | null;
  pendingTelemetry: {
    frame: FrameResult;
    captureToResultMs: number[];
    encodeMs: number[];
    resultToCaptureMs: number[];
    inferenceMs: number[];
    receivedCount: number;
  } | null;
  pendingEvents: FrameResult["events"];
  receivedResults: number;
};

// Learned tracking runs at the fastest sustainable one-in-flight cadence.
// Committing the newest aggregate to React/Three twice per second keeps the
// reconstruction current while springs interpolate smoothly between states.
const PRESENTATION_INTERVAL_MS = 500;

const runtime: Runtime = {
  transport: null,
  loop: null,
  webcam: null,
  unsubscribe: null,
  presentationTimer: null,
  pendingPresentation: null,
  pendingTelemetry: null,
  pendingEvents: [],
  receivedResults: 0,
};

function clearPendingPresentation(): void {
  if (runtime.presentationTimer !== null) {
    window.clearTimeout(runtime.presentationTimer);
    runtime.presentationTimer = null;
  }
  runtime.pendingPresentation = null;
  runtime.pendingTelemetry = null;
  runtime.pendingEvents = [];
  runtime.receivedResults = 0;
}

function releaseRuntime(): void {
  clearPendingPresentation();
  runtime.loop?.stop();
  runtime.loop = null;
  runtime.unsubscribe?.();
  runtime.unsubscribe = null;
  runtime.webcam?.release();
  runtime.webcam = null;
  runtime.transport?.close();
  runtime.transport = null;
}

function releaseCaptureSources(): void {
  clearPendingPresentation();
  runtime.loop?.stop();
  runtime.loop = null;
  runtime.unsubscribe?.();
  runtime.unsubscribe = null;
  runtime.webcam?.release();
  runtime.webcam = null;
}

async function ensureScene(
  source: SourceKind,
  prompts: string[],
): Promise<{ id: string; name: string }> {
  const targetName = source === "synthetic" ? "Synthetic Desk" : "Live Desk";
  const scenes = await api.listScenes();
  const existing = scenes.items.find((scene) => scene.name === targetName);
  if (existing !== undefined) {
    const expectedPersistence = source === "webcam";
    if (existing.persistence_enabled !== expectedPersistence) {
      throw new Error(
        `${targetName} has incompatible persistence settings; use a separate scene for this source.`,
      );
    }
    const promptsChanged =
      existing.object_prompts.length !== prompts.length ||
      existing.object_prompts.some((prompt, index) => prompt !== prompts[index]);
    const scene = promptsChanged
      ? await api.updateScene(existing.id, { object_prompts: prompts })
      : existing;
    return { id: scene.id, name: scene.name };
  }
  const created = await api.createScene({
    name: targetName,
    description:
      source === "synthetic"
        ? "Isolated deterministic replay scene."
        : "Primary workspace observed by WorldState.",
    object_prompts: prompts,
    persistence_enabled: source === "webcam",
  });
  return { id: created.id, name: created.name };
}

export const useSessionStore = create<SessionState>((set, get) => ({
  backendStatus: "probing",
  authenticated: false,
  canMutate: false,
  system: null,
  mode: null,
  providerMode: null,
  liveStatus: "idle",
  sourceKind: null,
  sceneId: null,
  sceneName: null,
  captureSessionId: null,
  liveError: null,
  bootstrapMessage: null,
  previewCanvas: null,
  webcamVideo: null,
  objectPrompts: [...DEFAULT_LIVE_PROMPTS],

  setObjectPrompts(prompts) {
    const normalized = normalizeObjectPrompts(prompts);
    if (normalized.length > 0) {
      set({ objectPrompts: normalized });
    }
  },

  async initialize() {
    const token = readBootstrapFragment();
    scrubFragment();

    let system: SystemResponse | null = null;
    try {
      system = await api.system();
    } catch {
      set({ backendStatus: "unreachable", system: null });
      return;
    }

    if (token !== null) {
      const outcome = await establishSession(token);
      if (outcome.status === "established") {
        set({
          backendStatus: "ready",
          authenticated: true,
          canMutate: true,
          system,
          mode: "backend",
          providerMode: system.provider_mode,
          bootstrapMessage: null,
        });
        return;
      }
      set({
        bootstrapMessage:
          outcome.status === "rejected"
            ? outcome.message
            : "The backend did not answer the bootstrap exchange.",
      });
    }

    const hasSession = await probeExistingSession();
    if (hasSession) {
      set({
        backendStatus: "ready",
        authenticated: true,
        canMutate: true,
        system,
        mode: "backend",
        providerMode: system.provider_mode,
      });
      return;
    }
    set({
      backendStatus: "unauthenticated",
      system,
      providerMode: system.provider_mode,
    });
  },

  enterSimulation() {
    releaseRuntime();
    useWorldStore.getState().reset();
    set({
      mode: "simulation",
      providerMode: "replay",
      liveStatus: "idle",
      liveError: null,
      sourceKind: null,
      sceneId: null,
      sceneName: null,
      captureSessionId: null,
      previewCanvas: null,
      webcamVideo: null,
    });
  },

  async startLive(source) {
    const state = get();
    if (state.liveStatus === "starting" || state.liveStatus === "live") {
      return;
    }
    releaseRuntime();
    useWorldStore.getState().reset();
    set({
      liveStatus: "starting",
      liveError: null,
      sourceKind: source,
      sceneId: null,
      sceneName: null,
      captureSessionId: null,
      previewCanvas: null,
      webcamVideo: null,
      providerMode:
        state.mode === "simulation" ? "replay" : (state.system?.provider_mode ?? null),
    });

    if (
      source === "webcam" &&
      (state.mode !== "backend" || !state.authenticated || !state.canMutate)
    ) {
      set({
        liveStatus: "error",
        liveError: "Webcam capture requires an authenticated learned-model backend.",
      });
      return;
    }
    if (source === "webcam" && state.system?.provider_mode !== "models") {
      set({
        liveStatus: "error",
        liveError:
          "Webcam capture requires the learned perception provider; replay cannot stand in for the camera.",
      });
      return;
    }

    let pendingBackendSessionId: string | null = null;
    try {
      let transport: LiveTransport;
      let sessionId: string;
      let sceneId: string;
      let sceneName: string;
      const prompts =
        source === "synthetic"
          ? [...SYNTHETIC_PROMPTS]
          : normalizeObjectPrompts(state.objectPrompts);

      // Acquire the physical source before creating backend state. Permission
      // prompts can be denied or left unanswered; neither should create an
      // orphan capture session or make synthetic memory look live.
      let video: HTMLVideoElement | null = null;
      let sourceImpl;
      let advance: (() => void) | null = null;
      if (source === "webcam") {
        const handle = await acquireWebcam();
        runtime.webcam = handle;
        video = handle.video;
        // Permission and a real video frame are now confirmed. Surface the
        // preview immediately while backend scene/session startup continues.
        set({ webcamVideo: video });
        sourceImpl = videoFrameSource(handle.video);
      } else {
        const desk = createSyntheticDesk();
        sourceImpl = desk;
        advance = () => {
          desk.advance();
        };
      }

      if (state.mode === "backend") {
        const scene = await ensureScene(source, prompts);
        sceneId = scene.id;
        sceneName = scene.name;
        const capture = await api.createCaptureSession(scene.id, {
          mode: source === "webcam" ? "live" : "replay",
          source_name:
            source === "webcam" ? "browser-webcam" : "synthetic-desk",
          camera: null,
        });
        sessionId = capture.id;
        pendingBackendSessionId = capture.id;
        transport = new WsTransport(resolveWsUrl());
      } else {
        sceneId = MOCK_SCENE_ID;
        sceneName = "Simulated Desk";
        sessionId = MOCK_SCENE_ID;
        transport = new MockTransport();
      }

      const ready = await transport.connect(sessionId, prompts);
      pendingBackendSessionId = null;
      runtime.transport = transport;

      const world = useWorldStore.getState();
      world.reset();

      // Construct the loop first so its transport listener records the local
      // monotonic round trip before the world telemetry listener ingests it.
      const loop = createCaptureLoop({
        transport,
        source: sourceImpl,
        // The acceptance floor is also the best latency/coverage balance for
        // loopback lossless I420. Learned discovery still receives a full 16:9
        // image; avoiding 44% extra transport pixels leaves GPU time for the
        // small-object vocabulary rather than adding uncalibrated resolution.
        maxWidth: Math.min(640, ready.limits.max_frame_width),
        maxHeight: Math.min(360, ready.limits.max_frame_height),
        maxFrameBytes: ready.limits.max_frame_bytes,
        // Request at display cadence. The one-in-flight protocol naturally
        // settles at the fastest sustainable rate without ever queueing work.
        intervalMs: 1000 / 60,
        onTick: (canvas, stats) => {
          useWorldStore.getState().noteSkippedIntervals(stats.skipped);
          const current = get();
          if (current.previewCanvas !== canvas) {
            set({ previewCanvas: canvas });
          }
          // Advance only after a frame is actually submitted. This keeps the
          // painted synthetic frame and replay-provider sequence in lockstep
          // even when backpressure skips capture intervals.
          advance?.();
        },
      });
      runtime.loop = loop;

      runtime.unsubscribe = transport.subscribe((message) => {
        if (message.type === "frame.result") {
          const activeLoop = runtime.loop;
          const captureToResultMs =
            activeLoop?.stats.lastCaptureToResultMs ??
            message.metrics.capture_to_result_ms;
          const encodeMs = activeLoop?.stats.lastEncodeMs ?? 0;
          const resultToCaptureMs =
            activeLoop?.stats.lastResultToCaptureMs ?? 0;
          runtime.receivedResults += 1;
          runtime.pendingPresentation = message;
          runtime.pendingTelemetry ??= {
            frame: message,
            captureToResultMs: [],
            encodeMs: [],
            resultToCaptureMs: [],
            inferenceMs: [],
            receivedCount: runtime.receivedResults,
          };
          runtime.pendingTelemetry.frame = message;
          runtime.pendingTelemetry.receivedCount = runtime.receivedResults;
          runtime.pendingTelemetry.captureToResultMs.push(captureToResultMs);
          runtime.pendingTelemetry.encodeMs.push(encodeMs);
          runtime.pendingTelemetry.resultToCaptureMs.push(resultToCaptureMs);
          runtime.pendingTelemetry.inferenceMs.push(message.metrics.inference_ms);
          runtime.presentationTimer ??= window.setTimeout(() => {
            runtime.presentationTimer = null;
            if (runtime.loop !== activeLoop) {
              runtime.pendingPresentation = null;
              runtime.pendingTelemetry = null;
              runtime.pendingEvents = [];
              return;
            }
            const latest = runtime.pendingPresentation;
            const telemetry = runtime.pendingTelemetry;
            const events = runtime.pendingEvents;
            runtime.pendingPresentation = null;
            runtime.pendingTelemetry = null;
            runtime.pendingEvents = [];
            const worldState = useWorldStore.getState();
            if (telemetry !== null) {
              worldState.noteFrameBatch(
                telemetry.frame,
                telemetry.captureToResultMs,
                telemetry.encodeMs,
                telemetry.receivedCount,
                telemetry.resultToCaptureMs,
                telemetry.inferenceMs,
              );
            }
            if (latest !== null) {
              worldState.presentFrame(latest);
            }
            if (events.length > 0) {
              worldState.ingestEvents(events[0]?.scene_id ?? "", events);
            }
          }, PRESENTATION_INTERVAL_MS);
          // Event batches are buffered into the same presentation turn below;
          // this keeps every durable event while avoiding hot-path rendering.
        } else if (message.type === "event.batch") {
          runtime.pendingEvents.push(...message.events);
        } else if (message.type === "error" && !message.recoverable) {
          releaseRuntime();
          if (source === "synthetic") {
            useWorldStore.getState().reset();
          }
          set({ liveStatus: "error", liveError: message.message });
        }
      });
      transport.onClose((reason) => {
        releaseRuntime();
        if (source === "synthetic") {
          useWorldStore.getState().reset();
        }
        set((current) =>
          current.liveStatus === "live" || current.liveStatus === "starting"
            ? {
                liveStatus: "error",
                liveError: `The live link closed: ${reason}`,
              }
            : {},
        );
      });
      loop.start();

      set({
        liveStatus: "live",
        sceneId,
        sceneName,
        captureSessionId: sessionId,
        providerMode: ready.provider_mode,
        webcamVideo: video,
      });
    } catch (error) {
      releaseRuntime();
      if (source === "synthetic") {
        useWorldStore.getState().reset();
      }
      if (state.mode === "backend" && pendingBackendSessionId !== null) {
        try {
          await api.finishCaptureSession(pendingBackendSessionId);
        } catch {
          // Crash recovery will close an unreachable backend session.
        }
      }
      const message =
        error instanceof WebcamError || error instanceof Error
          ? error.message
          : "The live session could not start.";
      set({
        liveStatus: "error",
        liveError: message,
        webcamVideo: null,
        ...(source === "synthetic"
          ? {
              sourceKind: null,
              sceneId: null,
              sceneName: null,
              captureSessionId: null,
              previewCanvas: null,
              providerMode:
                state.mode === "backend"
                  ? (state.system?.provider_mode ?? null)
                  : "replay",
            }
          : {}),
      });
    }
  },

  async stopLive() {
    const { captureSessionId, mode, liveStatus, sourceKind, system } = get();
    if (liveStatus === "idle" || liveStatus === "stopping") {
      return;
    }
    set({ liveStatus: "stopping" });
    // Stop producing frames and release the camera first, while leaving the
    // socket connected long enough for the authoritative REST finish call.
    releaseCaptureSources();
    let finishError: string | null = null;
    if (mode === "backend" && captureSessionId !== null) {
      try {
        const capture = await api.finishCaptureSession(captureSessionId);
        if (capture.status !== "completed") {
          finishError = `The backend reported session status ${capture.status}.`;
        }
      } catch (error) {
        finishError =
          error instanceof Error
            ? error.message
            : "The backend did not confirm session completion.";
      }
    }
    runtime.transport?.close();
    runtime.transport = null;
    if (finishError !== null && captureSessionId !== null) {
      try {
        const capture = await api.getCaptureSession(captureSessionId);
        if (capture.status === "completed") {
          finishError = null;
        }
      } catch {
        // Preserve the first actionable error.
      }
    }
    if (finishError !== null) {
      if (sourceKind === "synthetic") {
        useWorldStore.getState().reset();
      }
      set({
        liveStatus: "error",
        liveError: `The camera is off, but session finalization failed: ${finishError}`,
        previewCanvas: null,
        webcamVideo: null,
        ...(sourceKind === "synthetic"
          ? {
              sourceKind: null,
              sceneId: null,
              sceneName: null,
              providerMode:
                mode === "backend" ? (system?.provider_mode ?? null) : "replay",
            }
          : {}),
      });
      return;
    }
    if (sourceKind === "synthetic") {
      useWorldStore.getState().reset();
    }
    set({
      liveStatus: "idle",
      captureSessionId: null,
      previewCanvas: null,
      webcamVideo: null,
      ...(sourceKind === "synthetic"
        ? {
            sourceKind: null,
            sceneId: null,
            sceneName: null,
            providerMode:
              mode === "backend" ? (system?.provider_mode ?? null) : "replay",
          }
        : {}),
    });
  },

  async submitCommand(input) {
    const transport = runtime.transport;
    if (transport === null) {
      return null;
    }
    try {
      return await transport.submitCommand(input);
    } catch {
      return null;
    }
  },
}));

/** Test-only hook to inspect runtime wiring without exporting internals. */
export function __runtimeForTests(): Readonly<Runtime> {
  return runtime;
}
