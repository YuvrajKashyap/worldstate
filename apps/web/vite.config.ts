import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The MediaPipe package does not export its wasm assets through the
// package "exports" map; alias them so they bundle from our own origin.
const mediapipeWasmDir = fileURLToPath(
  new URL("./node_modules/@mediapipe/tasks-vision/wasm/", import.meta.url),
);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      {
        find: /^@mediapipe\/tasks-vision\/wasm\/(.+)$/,
        replacement: `${mediapipeWasmDir}$1`,
      },
    ],
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
  build: {
    // The spatial runtime and gesture engine live behind lazy boundaries.
    chunkSizeWarningLimit: 1_400,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      // Coverage is enforced on the protocol/domain/state logic layer.
      // Rendering surfaces (Three.js scene, MediaPipe runtime, HUD chrome)
      // are verified through browser end-to-end passes instead: jsdom cannot
      // execute WebGL or camera pipelines meaningfully.
      include: [
        "src/lib/**",
        "src/state/**",
      ],
      exclude: [
        "src/lib/holo/handTracker.ts",
        "src/lib/live/webcam.ts",
      ],
      thresholds: {
        lines: 80,
        functions: 80,
        statements: 80,
        branches: 75,
      },
    },
  },
});
