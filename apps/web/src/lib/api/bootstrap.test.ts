import { afterEach, describe, expect, it, vi } from "vitest";

import {
  establishSession,
  probeExistingSession,
  readBootstrapFragment,
  scrubFragment,
} from "./bootstrap";
import { getCsrfToken, setCsrfToken } from "./http";

describe("readBootstrapFragment", () => {
  it("extracts the bootstrap token from the hash", () => {
    expect(readBootstrapFragment("#bootstrap=abc123")).toBe("abc123");
    expect(readBootstrapFragment("bootstrap=abc123")).toBe("abc123");
    expect(readBootstrapFragment("#other=1&bootstrap=tok")).toBe("tok");
  });

  it("returns null when absent or empty", () => {
    expect(readBootstrapFragment("")).toBeNull();
    expect(readBootstrapFragment("#")).toBeNull();
    expect(readBootstrapFragment("#bootstrap=")).toBeNull();
    expect(readBootstrapFragment("#unrelated=x")).toBeNull();
  });
});

describe("scrubFragment", () => {
  it("removes the fragment via history.replaceState", () => {
    window.location.hash = "#bootstrap=secret";
    scrubFragment();
    expect(window.location.hash).toBe("");
  });
});

describe("establishSession", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setCsrfToken(null);
  });

  it("stores the CSRF token in memory only on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            csrf_token: "csrf-token-value",
            expires_at: "2026-07-30T12:00:00Z",
            protocol_version: "v1",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const outcome = await establishSession("launcher-token");
    expect(outcome.status).toBe("established");
    expect(getCsrfToken()).toBe("csrf-token-value");
  });

  it("reports rejection with the backend message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "invalid_bootstrap", message: "The launcher token is invalid." },
          }),
          { status: 401 },
        ),
      ),
    );
    const outcome = await establishSession("bad");
    expect(outcome).toEqual({
      status: "rejected",
      message: "The launcher token is invalid.",
    });
    expect(getCsrfToken()).toBeNull();
  });

  it("reports unreachable backends distinctly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    const outcome = await establishSession("token");
    expect(outcome.status).toBe("unreachable");
  });
});

describe("probeExistingSession", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setCsrfToken(null);
  });

  it("restores CSRF when the authenticated refresh succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            csrf_token: "restored-csrf",
            expires_at: "2026-07-30T12:00:00Z",
            protocol_version: "v1",
          }),
          { status: 200 },
        ),
      ),
    );
    await expect(probeExistingSession()).resolves.toBe(true);
    expect(getCsrfToken()).toBe("restored-csrf");
  });

  it("is false on 401", async () => {
    setCsrfToken("stale-csrf");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
    );
    await expect(probeExistingSession()).resolves.toBe(false);
    expect(getCsrfToken()).toBeNull();
  });
});
