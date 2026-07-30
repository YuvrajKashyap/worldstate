import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useSystemStatus } from "../hooks/useSystemStatus";
import { SystemBadge } from "./SystemBadge";

vi.mock("../hooks/useSystemStatus", () => ({
  useSystemStatus: vi.fn(),
}));

const mockUseSystemStatus = vi.mocked(useSystemStatus);

describe("SystemBadge", () => {
  beforeEach(() => {
    mockUseSystemStatus.mockReset();
  });

  it("shows a pending coordinator state", () => {
    mockUseSystemStatus.mockReturnValue({ kind: "loading" });

    render(<SystemBadge />);

    expect(screen.getByRole("status")).toHaveTextContent("Checking coordinator");
  });

  it("shows an online coordinator state", () => {
    mockUseSystemStatus.mockReturnValue({
      kind: "online",
      value: {
        environment: "test",
        persistence_enabled: false,
        protocol_version: "v1",
        product_phase: "foundation",
      },
    });

    render(<SystemBadge />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Coordinator online / v1",
    );
  });

  it("shows an offline coordinator state", () => {
    mockUseSystemStatus.mockReturnValue({ kind: "offline" });

    render(<SystemBadge />);

    expect(screen.getByRole("status")).toHaveTextContent("Coordinator offline");
  });
});
