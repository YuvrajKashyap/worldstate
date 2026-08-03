import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setCsrfToken, type SystemResponse } from "../lib/api/http";
import { useWorldStore, type EntityRecord } from "./worldStore";
import { __runtimeForTests, useSessionStore } from "./sessionStore";

const SYSTEM_RESPONSE = {
  environment: "development",
  persistence_enabled: false,
  protocol_version: "v1",
  product_phase: "operational",
  provider_mode: "replay",
  capabilities: { live: "ready", scan: "degraded" },
  limits: {
    max_frame_bytes: 2_500_000,
    max_frame_width: 1920,
    max_frame_height: 1080,
    max_upload_bytes: 1,
    max_video_duration_seconds: 1,
    max_pending_jobs: 16,
    storage_quota_bytes: 1,
  },
} satisfies SystemResponse;

const MODEL_SYSTEM_RESPONSE = {
  ...SYSTEM_RESPONSE,
  persistence_enabled: true,
  provider_mode: "models",
} satisfies SystemResponse;

const SYNTHETIC_ENTITY: EntityRecord = {
  id: "synthetic-cup",
  label: "cup",
  firstSeenAt: 1,
  lastSeenAt: 1,
  lastVisibleAt: 1,
  presence: "visible",
  confidence: 0.94,
  uncertainty: 0.06,
  position: [0, 0, 1],
  bounds: null,
  box: [10, 10, 40, 50],
  history: [],
  eventCount: 1,
};

function seedSyntheticWorld(): void {
  useWorldStore.setState({
    sceneId: "synthetic-scene",
    entities: { [SYNTHETIC_ENTITY.id]: SYNTHETIC_ENTITY },
    order: [SYNTHETIC_ENTITY.id],
  });
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status });
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return input;
  }
  return input instanceof URL ? input.href : input.url;
}

describe("sessionStore.initialize", () => {
  beforeEach(() => {
    window.location.hash = "";
    useSessionStore.setState({
      backendStatus: "probing",
      authenticated: false,
      canMutate: false,
      system: null,
      mode: null,
      providerMode: null,
      bootstrapMessage: null,
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setCsrfToken(null);
  });

  it("marks the backend unreachable when /system fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("refused")));
    await useSessionStore.getState().initialize();
    expect(useSessionStore.getState().backendStatus).toBe("unreachable");
  });

  it("establishes a session from a fragment token and scrubs the URL", async () => {
    window.location.hash = "#bootstrap=launcher-token";
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/api/v1/system")) {
        return Promise.resolve(jsonResponse(SYSTEM_RESPONSE));
      }
      if (url.endsWith("/api/v1/bootstrap")) {
        return Promise.resolve(
          jsonResponse({
            csrf_token: "csrf",
            expires_at: "2026-07-30T12:00:00Z",
            protocol_version: "v1",
          }),
        );
      }
      return Promise.resolve(jsonResponse({ items: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    await useSessionStore.getState().initialize();
    const state = useSessionStore.getState();
    expect(window.location.hash).toBe("");
    expect(state.backendStatus).toBe("ready");
    expect(state.authenticated).toBe(true);
    expect(state.canMutate).toBe(true);
    expect(state.mode).toBe("backend");
    expect(state.providerMode).toBe("replay");
  });

  it("falls back to unauthenticated when no token and no cookie session", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/api/v1/system")) {
        return Promise.resolve(jsonResponse(SYSTEM_RESPONSE));
      }
      return Promise.resolve(jsonResponse({}, 401));
    });
    vi.stubGlobal("fetch", fetchMock);

    await useSessionStore.getState().initialize();
    const state = useSessionStore.getState();
    expect(state.backendStatus).toBe("unauthenticated");
    expect(state.mode).toBeNull();
    expect(state.system?.provider_mode).toBe("replay");
  });

  it("restores a writable session after reload from the HttpOnly cookie", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/api/v1/system")) {
        return Promise.resolve(jsonResponse(SYSTEM_RESPONSE));
      }
      if (url.endsWith("/api/v1/session/refresh")) {
        return Promise.resolve(
          jsonResponse({
            csrf_token: "restored-csrf",
            expires_at: "2026-07-30T12:00:00Z",
            protocol_version: "v1",
          }),
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    await useSessionStore.getState().initialize();
    const state = useSessionStore.getState();
    expect(state.backendStatus).toBe("ready");
    expect(state.authenticated).toBe(true);
    expect(state.canMutate).toBe(true);
  });

  it("surfaces a rejected bootstrap token but still probes cookies", async () => {
    window.location.hash = "#bootstrap=stale-token";
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/api/v1/system")) {
        return Promise.resolve(jsonResponse(SYSTEM_RESPONSE));
      }
      if (url.endsWith("/api/v1/bootstrap")) {
        return Promise.resolve(
          jsonResponse(
            { error: { code: "invalid_bootstrap", message: "The launcher token is invalid." } },
            401,
          ),
        );
      }
      return Promise.resolve(jsonResponse({}, 401));
    });
    vi.stubGlobal("fetch", fetchMock);

    await useSessionStore.getState().initialize();
    const state = useSessionStore.getState();
    expect(state.bootstrapMessage).toContain("invalid");
    expect(state.backendStatus).toBe("unauthenticated");
  });
});

describe("sessionStore simulation mode", () => {
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("enters simulation with replay provider labeling", () => {
    useSessionStore.getState().enterSimulation();
    const state = useSessionStore.getState();
    expect(state.mode).toBe("simulation");
    expect(state.providerMode).toBe("replay");
  });

  it("refuses to present a physical webcam as simulation", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    useSessionStore.getState().enterSimulation();

    await useSessionStore.getState().startLive("webcam");

    const state = useSessionStore.getState();
    expect(state.liveStatus).toBe("error");
    expect(state.liveError).toContain("authenticated learned-model backend");
    expect(state.captureSessionId).toBeNull();
    expect(state.webcamVideo).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses a webcam session when the backend is configured for replay", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    useSessionStore.setState({
      mode: "backend",
      authenticated: true,
      canMutate: true,
      system: SYSTEM_RESPONSE,
      providerMode: "replay",
      liveStatus: "idle",
      captureSessionId: null,
      webcamVideo: null,
    });

    await useSessionStore.getState().startLive("webcam");

    const state = useSessionStore.getState();
    expect(state.liveStatus).toBe("error");
    expect(state.liveError).toContain("learned perception provider");
    expect(state.captureSessionId).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns null for commands without a live transport", async () => {
    await expect(
      useSessionStore.getState().submitCommand({
        command: "select_entity",
        sceneId: "s".repeat(36),
      }),
    ).resolves.toBeNull();
  });

  it("runs the synthetic live lifecycle end to end without a backend", async () => {
    useSessionStore.getState().enterSimulation();
    await useSessionStore.getState().startLive("synthetic");
    let state = useSessionStore.getState();
    expect(state.liveStatus).toBe("live");
    expect(state.sceneName).toBe("Simulated Desk");
    expect(state.sourceKind).toBe("synthetic");
    expect(state.providerMode).toBe("replay");

    // Commands now flow through the simulated command channel.
    const result = await useSessionStore.getState().submitCommand({
      command: "select_entity",
      sceneId: state.sceneId ?? "",
    });
    expect(result?.status).toBe("completed");

    await useSessionStore.getState().stopLive();
    state = useSessionStore.getState();
    expect(state.liveStatus).toBe("idle");
    expect(state.captureSessionId).toBeNull();
    expect(state.previewCanvas).toBeNull();
  });

  it("ignores duplicate start requests while live", async () => {
    useSessionStore.getState().enterSimulation();
    await useSessionStore.getState().startLive("synthetic");
    const before = useSessionStore.getState().sceneId;
    await useSessionStore.getState().startLive("synthetic");
    expect(useSessionStore.getState().sceneId).toBe(before);
    await useSessionStore.getState().stopLive();
  });
});

describe("sessionStore backend stop finalization", () => {
  const captureId = "018f0000-0000-7000-8000-000000000042";

  beforeEach(() => {
    useSessionStore.setState({
      mode: "backend",
      liveStatus: "live",
      liveError: null,
      captureSessionId: captureId,
      previewCanvas: document.createElement("canvas"),
      webcamVideo: null,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns to idle only after the backend confirms completion", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: captureId,
          status: "completed",
        }),
      ),
    );

    await useSessionStore.getState().stopLive();

    const state = useSessionStore.getState();
    expect(state.liveStatus).toBe("idle");
    expect(state.captureSessionId).toBeNull();
    expect(state.previewCanvas).toBeNull();
  });

  it("accepts socket-side completion when the finish request fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: "busy", message: "finish raced with socket close" } },
          503,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: captureId,
          status: "completed",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await useSessionStore.getState().stopLive();

    expect(useSessionStore.getState().liveStatus).toBe("idle");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("surfaces an unconfirmed backend session instead of pretending to stop", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: captureId,
          status: "active",
        }),
      ),
    );

    await useSessionStore.getState().stopLive();

    const state = useSessionStore.getState();
    expect(state.liveStatus).toBe("error");
    expect(state.liveError).toContain("session finalization failed");
    expect(state.captureSessionId).toBe(captureId);
    expect(state.previewCanvas).toBeNull();
  });
});

describe("sessionStore live source isolation", () => {
  beforeEach(() => {
    useSessionStore.getState().enterSimulation();
    useSessionStore.setState({
      mode: "backend",
      backendStatus: "ready",
      authenticated: true,
      canMutate: true,
      system: MODEL_SYSTEM_RESPONSE,
      providerMode: "models",
      liveStatus: "idle",
      sourceKind: null,
      sceneId: null,
      sceneName: null,
      captureSessionId: null,
      liveError: null,
      previewCanvas: null,
      webcamVideo: null,
    });
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: true,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useSessionStore.getState().enterSimulation();
  });

  it("clears stopped backend simulation entities and restores the learned provider", async () => {
    const captureId = "018f0000-0000-7000-8000-000000000077";
    seedSyntheticWorld();
    useSessionStore.setState({
      liveStatus: "live",
      sourceKind: "synthetic",
      sceneId: "synthetic-scene",
      sceneName: "Synthetic Desk",
      captureSessionId: captureId,
      providerMode: "replay",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ id: captureId, status: "completed" }),
      ),
    );

    await useSessionStore.getState().stopLive();

    const session = useSessionStore.getState();
    expect(useWorldStore.getState().order).toEqual([]);
    expect(session.sourceKind).toBeNull();
    expect(session.sceneId).toBeNull();
    expect(session.sceneName).toBeNull();
    expect(session.providerMode).toBe("models");
  });

  it("clears synthetic state before requesting webcam permission", async () => {
    seedSyntheticWorld();
    let rejectCamera: ((reason: unknown) => void) | undefined;
    const cameraRequest = new Promise<MediaStream>((_resolve, reject) => {
      rejectCamera = reject;
    });
    const getUserMedia = vi.fn().mockReturnValue(cameraRequest);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const startup = useSessionStore.getState().startLive("webcam");
    await Promise.resolve();

    expect(useWorldStore.getState().order).toEqual([]);
    expect(useSessionStore.getState().captureSessionId).toBeNull();
    expect(__runtimeForTests().transport).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();

    rejectCamera?.(new DOMException("declined", "NotAllowedError"));
    await startup;
    expect(useSessionStore.getState().liveStatus).toBe("error");
    expect(useSessionStore.getState().captureSessionId).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
