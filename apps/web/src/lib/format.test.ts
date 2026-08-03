import { describe, expect, it } from "vitest";

import {
  formatAgo,
  formatDuration,
  formatMs,
  percentile,
} from "./format";

describe("formatAgo", () => {
  const now = 1_700_000_000_000;
  it("covers seconds, minutes, and hours", () => {
    expect(formatAgo(now - 500, now)).toBe("just now");
    expect(formatAgo(now - 12_000, now)).toBe("12s ago");
    expect(formatAgo(now - 95_000, now)).toBe("1m 35s ago");
    expect(formatAgo(now - 3_700_000, now)).toBe("1h 1m ago");
    expect(formatAgo(now + 5_000, now)).toBe("just now");
  });
});

describe("formatMs", () => {
  it("keeps a decimal below 100ms and none above", () => {
    expect(formatMs(42.34)).toBe("42.3ms");
    expect(formatMs(150.6)).toBe("151ms");
  });
});

describe("percentile", () => {
  it("computes p50 and p95 on unsorted input", () => {
    const values = [90, 10, 20, 30, 40, 50, 60, 70, 80, 100];
    expect(percentile(values, 0.5)).toBe(50);
    expect(percentile(values, 0.95)).toBe(100);
    expect(percentile(values, -1)).toBe(10);
    expect(percentile(values, 2)).toBe(100);
    expect(percentile([], 0.5)).toBe(0);
  });
});

describe("formatDuration", () => {
  it("renders mm:ss", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(75)).toBe("01:15");
    expect(formatDuration(605)).toBe("10:05");
  });
});
