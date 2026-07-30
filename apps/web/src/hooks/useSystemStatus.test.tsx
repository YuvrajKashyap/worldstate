import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getSystemStatus } from "../lib/system-api";
import { useSystemStatus } from "./useSystemStatus";

vi.mock("../lib/system-api", () => ({
  getSystemStatus: vi.fn(),
}));

const mockGetSystemStatus = vi.mocked(getSystemStatus);

describe("useSystemStatus", () => {
  afterEach(() => {
    mockGetSystemStatus.mockReset();
  });

  it("moves from loading to online", async () => {
    mockGetSystemStatus.mockResolvedValue({
      environment: "test",
      persistence_enabled: false,
      protocol_version: "v1",
      product_phase: "foundation",
    });

    const { result } = renderHook(() => useSystemStatus());

    expect(result.current).toEqual({ kind: "loading" });
    await waitFor(() => {
      expect(result.current.kind).toBe("online");
    });
  });

  it("moves to offline after a request failure", async () => {
    mockGetSystemStatus.mockRejectedValue(new Error("network unavailable"));

    const { result } = renderHook(() => useSystemStatus());

    await waitFor(() => {
      expect(result.current).toEqual({ kind: "offline" });
    });
  });

  it("ignores an aborted request after unmount", async () => {
    let rejectRequest: ((reason: DOMException) => void) | undefined;
    mockGetSystemStatus.mockImplementation(
      () =>
        new Promise((_resolve, reject: (reason: DOMException) => void) => {
          rejectRequest = reject;
        }),
    );

    const { unmount } = renderHook(() => useSystemStatus());
    unmount();

    await act(async () => {
      rejectRequest?.(new DOMException("aborted", "AbortError"));
      await Promise.resolve();
    });

    expect(mockGetSystemStatus).toHaveBeenCalledOnce();
  });

  it("treats a non-abort DOM exception as offline", async () => {
    mockGetSystemStatus.mockRejectedValue(
      new DOMException("request failed", "NetworkError"),
    );

    const { result } = renderHook(() => useSystemStatus());

    await waitFor(() => {
      expect(result.current).toEqual({ kind: "offline" });
    });
  });
});
