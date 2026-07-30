import { afterEach, describe, expect, it, vi } from "vitest";

import { getSystemStatus } from "./system-api";

describe("getSystemStatus", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the typed coordinator status", async () => {
    const status = {
      environment: "test",
      persistence_enabled: false,
      protocol_version: "v1" as const,
      product_phase: "foundation" as const,
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(status),
    });
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;

    await expect(getSystemStatus(signal)).resolves.toEqual(status);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/system",
      { signal },
    );
  });

  it("rejects a non-successful coordinator response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
      }),
    );

    await expect(
      getSystemStatus(new AbortController().signal),
    ).rejects.toThrow("WorldState API returned 503");
  });
});
