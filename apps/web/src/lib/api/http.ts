/**
 * Minimal typed REST client for the WorldState local API.
 *
 * - Session credential is an HttpOnly cookie; every request sends credentials.
 * - The CSRF token lives in memory only and is attached to state-changing verbs.
 * - Errors are normalized to the backend envelope { code, message }.
 */

import type { components } from "@worldstate/contracts";

export type Schemas = components["schemas"];
export type SystemResponse = Schemas["SystemResponse"];
export type SceneResponse = Schemas["SceneResponse"];
export type CaptureSessionResponse = Schemas["CaptureSessionResponse"];
export type EntityResponse = Schemas["EntityResponse"];
export type EntityStateResponse = Schemas["EntityStateResponse"];
export type EntityHistoryResponse = Schemas["EntityHistoryResponse"];
export type LastSeenResponse = Schemas["LastSeenResponse"];
export type WorldEventResponse = Schemas["WorldEventResponse"];
export type RelationshipResponse = Schemas["RelationshipResponse"];
export type SceneSnapshotResponse = Schemas["SceneSnapshotResponse"];
export type JobResponse = Schemas["JobResponse"];
export type ReplayInfo = Schemas["ReplayInfo"];
export type UploadResponse = Schemas["UploadResponse"];

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Dev talks to uvicorn on 8000; production is served same-origin. */
export function resolveApiBase(): string {
  if (import.meta.env.DEV) {
    return "http://127.0.0.1:8000";
  }
  return "";
}

export function resolveWsUrl(base: string = resolveApiBase()): string {
  if (base.startsWith("http")) {
    return `${base.replace(/^http/, "ws")}/api/v1/live`;
  }
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/v1/live`;
}

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  base: string = resolveApiBase(),
): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken !== null) {
    headers.set("X-WorldState-CSRF", csrfToken);
  }
  if (init.body !== undefined && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "network_unreachable", "The local backend is not reachable.");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed with status ${String(response.status)}.`;
    try {
      const payload = (await response.json()) as {
        error?: { code?: string; message?: string };
      };
      if (payload.error) {
        code = payload.error.code ?? code;
        message = payload.error.message ?? message;
      }
    } catch {
      // Non-JSON error body; keep defaults.
    }
    throw new ApiError(response.status, code, message);
  }
  return (await response.json()) as T;
}

export const api = {
  system: () => request<SystemResponse>("/api/v1/system"),

  bootstrap: (token: string) =>
    request<Schemas["BootstrapResponse"]>("/api/v1/bootstrap", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  refreshSession: () =>
    request<Schemas["BootstrapResponse"]>("/api/v1/session/refresh", {
      method: "POST",
    }),

  logout: async (): Promise<void> => {
    await request<unknown>("/api/v1/session/logout", { method: "POST" });
  },

  listScenes: () =>
    request<Schemas["SceneListResponse"]>("/api/v1/scenes"),

  createScene: (payload: Schemas["SceneCreate"]) =>
    request<SceneResponse>("/api/v1/scenes", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateScene: (sceneId: string, payload: Schemas["SceneUpdate"]) =>
    request<SceneResponse>(`/api/v1/scenes/${encodeURIComponent(sceneId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  createCaptureSession: (
    sceneId: string,
    payload: Schemas["CaptureSessionCreate"],
  ) =>
    request<CaptureSessionResponse>(
      `/api/v1/scenes/${encodeURIComponent(sceneId)}/sessions`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  finishCaptureSession: (sessionId: string) =>
    request<CaptureSessionResponse>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/finish`,
      { method: "POST" },
    ),

  getCaptureSession: (sessionId: string) =>
    request<CaptureSessionResponse>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    ),

  uploadVideo: (sessionId: string, file: File) => {
    const body = new FormData();
    body.append("upload", file);
    return request<UploadResponse>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/video`,
      { method: "POST", body },
    );
  },

  listEntities: (sceneId: string, label?: string) =>
    request<Schemas["EntityListResponse"]>(
      `/api/v1/scenes/${encodeURIComponent(sceneId)}/entities${
        label ? `?label=${encodeURIComponent(label)}` : ""
      }`,
    ),

  entityHistory: (entityId: string) =>
    request<EntityHistoryResponse>(
      `/api/v1/entities/${encodeURIComponent(entityId)}`,
    ),

  lastSeen: (entityId: string) =>
    request<LastSeenResponse>(
      `/api/v1/entities/${encodeURIComponent(entityId)}/last-seen`,
    ),

  listEvents: (sceneId: string, limit = 500) =>
    request<Schemas["EventListResponse"]>(
      `/api/v1/scenes/${encodeURIComponent(sceneId)}/events?limit=${String(limit)}`,
    ),

  listRelationships: (sceneId: string, at?: string) =>
    request<Schemas["RelationshipListResponse"]>(
      `/api/v1/scenes/${encodeURIComponent(sceneId)}/relationships${
        at ? `?at=${encodeURIComponent(at)}` : ""
      }`,
    ),

  snapshot: (sceneId: string, at: string) =>
    request<SceneSnapshotResponse>(
      `/api/v1/scenes/${encodeURIComponent(sceneId)}/snapshot?at=${encodeURIComponent(at)}`,
    ),

  listJobs: () => request<Schemas["JobListResponse"]>("/api/v1/jobs"),

  createJob: (payload: Schemas["JobCreate"]) =>
    request<JobResponse>("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  cancelJob: (jobId: string) =>
    request<JobResponse>(`/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    }),

  listReplays: () => request<Schemas["ReplayListResponse"]>("/api/v1/replays"),
};
