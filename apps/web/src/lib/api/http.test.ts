import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, resolveWsUrl, setCsrfToken } from "./http";

function mockFetch(response: Response) {
  const spy = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

describe("api client", () => {
  it("sends credentials on reads and no CSRF header", async () => {
    const spy = mockFetch(
      new Response(JSON.stringify({ items: [] }), { status: 200 }),
    );
    await api.listScenes();
    const [, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).has("X-WorldState-CSRF")).toBe(false);
  });

  it("attaches the in-memory CSRF token to state-changing requests", async () => {
    setCsrfToken("csrf-abc");
    const spy = mockFetch(
      new Response(JSON.stringify({ id: "x" }), { status: 201 }),
    );
    await api.createScene({
      name: "Desk",
      description: null,
      object_prompts: ["cup"],
      persistence_enabled: false,
    });
    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/scenes");
    const headers = new Headers(init.headers);
    expect(headers.get("X-WorldState-CSRF")).toBe("csrf-abc");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("normalizes backend error envelopes into ApiError", async () => {
    mockFetch(
      new Response(
        JSON.stringify({
          error: { code: "session_required", message: "A valid local session is required." },
        }),
        { status: 401 },
      ),
    );
    const failure = await api.listScenes().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    if (failure instanceof ApiError) {
      expect(failure.code).toBe("session_required");
      expect(failure.status).toBe(401);
    }
  });

  it("degrades gracefully on non-JSON error bodies", async () => {
    mockFetch(new Response("<html>bad gateway</html>", { status: 502 }));
    const failure = await api.listScenes().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    if (failure instanceof ApiError) {
      expect(failure.code).toBe("http_error");
    }
  });

  it("maps network failure to a distinct unreachable error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("refused")));
    const failure = await api.listScenes().catch((error: unknown) => error);
    if (failure instanceof ApiError) {
      expect(failure.code).toBe("network_unreachable");
      expect(failure.status).toBe(0);
    } else {
      throw new Error("expected ApiError");
    }
  });

  it("handles 204 responses without parsing", async () => {
    setCsrfToken("csrf");
    mockFetch(new Response(null, { status: 204 }));
    await expect(api.logout()).resolves.toBeUndefined();
  });
});

describe("endpoint construction", () => {
  it("targets the documented v1 paths with encoded parameters", async () => {
    setCsrfToken("csrf");
    const spy = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ items: [] }), { status: 200 }),
      ),
    );
    vi.stubGlobal("fetch", spy);

    await api.system();
    await api.refreshSession();
    await api.updateScene("scene 1", { object_prompts: ["mug"] });
    await api.listEntities("scene 1", "cup mug");
    await api.entityHistory("ent/1");
    await api.lastSeen("ent-2");
    await api.listEvents("scene-1", 25);
    await api.listRelationships("scene-1", "2026-07-30T00:00:00Z");
    await api.snapshot("scene-1", "2026-07-30T00:00:00Z");
    await api.listJobs();
    await api.createJob({ kind: "scan", parameters: {} });
    await api.cancelJob("job-1");
    await api.listReplays();
    await api.createCaptureSession("scene-1", {
      mode: "live",
      source_name: "webcam",
      camera: null,
    });
    await api.finishCaptureSession("sess-1");
    await api.uploadVideo("sess-1", new File([new Uint8Array(4)], "clip.mp4"));

    const urls = spy.mock.calls.map((call) => String(call[0]));
    expect(urls).toEqual(
      expect.arrayContaining([
        expect.stringContaining("/api/v1/system"),
        expect.stringContaining("/api/v1/session/refresh"),
        expect.stringContaining("/api/v1/scenes/scene%201"),
        expect.stringContaining("/api/v1/scenes/scene%201/entities?label=cup%20mug"),
        expect.stringContaining("/api/v1/entities/ent%2F1"),
        expect.stringContaining("/api/v1/entities/ent-2/last-seen"),
        expect.stringContaining("/api/v1/scenes/scene-1/events?limit=25"),
        expect.stringContaining("/api/v1/scenes/scene-1/relationships?at="),
        expect.stringContaining("/api/v1/scenes/scene-1/snapshot?at="),
        expect.stringContaining("/api/v1/jobs/job-1/cancel"),
        expect.stringContaining("/api/v1/replays"),
        expect.stringContaining("/api/v1/scenes/scene-1/sessions"),
        expect.stringContaining("/api/v1/sessions/sess-1/finish"),
        expect.stringContaining("/api/v1/sessions/sess-1/video"),
      ]),
    );

    // Multipart uploads must not get a JSON content type.
    const uploadCall = spy.mock.calls.find((call) =>
      String(call[0]).includes("/video"),
    );
    const uploadInit = uploadCall?.[1] as RequestInit;
    expect(uploadInit.body).toBeInstanceOf(FormData);
    expect(new Headers(uploadInit.headers).get("Content-Type")).toBeNull();
    expect(new Headers(uploadInit.headers).get("X-WorldState-CSRF")).toBe("csrf");
  });
});

describe("resolveWsUrl", () => {
  it("derives ws:// from an http base", () => {
    expect(resolveWsUrl("http://127.0.0.1:8000")).toBe(
      "ws://127.0.0.1:8000/api/v1/live",
    );
  });

  it("uses the page origin for same-origin production", () => {
    expect(resolveWsUrl("")).toContain("/api/v1/live");
    expect(resolveWsUrl("")).toMatch(/^wss?:\/\//);
  });
});
