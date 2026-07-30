import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("./components/WorldViewport", () => ({
  default: () => <div aria-label="Test memory volume">Memory volume</div>,
}));

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            environment: "test",
            persistence_enabled: false,
            protocol_version: "v1",
            product_phase: "foundation",
          }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the world model foundation", async () => {
    render(<App />);

    expect(screen.getByLabelText("WorldState home")).toBeInTheDocument();
    expect(screen.getByText("Persistent objects")).toBeInTheDocument();
    expect(await screen.findByText("Coordinator online / v1")).toBeInTheDocument();
  });
});
