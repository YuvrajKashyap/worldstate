/**
 * In-browser simulation transport.
 *
 * Implements the exact LiveTransport surface (hello → ready, one frame in,
 * three messages out, idempotent commands) against the deterministic
 * MockWorldEngine. Used when no backend is reachable; the interface labels
 * this mode SIMULATION everywhere.
 */

import {
  type CommandInput,
  type CommandResult,
  type ServerMessage,
  type ServerReady,
  PROTOCOL_VERSION,
} from "../../protocol/messages";
import type { LiveTransport, TransportListener } from "../transport";
import { FRAME_HEADER_BYTES } from "@worldstate/contracts/protocol";
import { MOCK_SCENE_ID, MockWorldEngine } from "./mockWorld";

const SIMULATED_INFERENCE_MS = 6;

export class MockTransport implements LiveTransport {
  readonly kind = "simulation" as const;

  private readonly engine = new MockWorldEngine();
  private readonly listeners = new Set<TransportListener>();
  private readonly commandCache = new Map<string, CommandResult>();
  private readonly lastSeen = new Map<
    string,
    { label: string; at: string; position: [number, number, number] | null; confidence: number }
  >();
  private closed = false;
  private frameCount = 0;
  private droppedFrames = 0;
  private lastSequence = -1;

  connect(): Promise<ServerReady> {
    const ready: ServerReady = {
      type: "server.ready",
      protocol_version: PROTOCOL_VERSION,
      request_id: "sim-ready",
      accepted_capabilities: [
        "frame.result",
        "world.patch",
        "event.batch",
        "command.submit",
      ],
      provider_mode: "replay",
      limits: {
        max_frame_bytes: 2_500_000,
        max_frame_width: 1920,
        max_frame_height: 1080,
        max_upload_bytes: 2_147_483_648,
        max_video_duration_seconds: 1800,
        max_pending_jobs: 16,
        storage_quota_bytes: 75_000_000_000,
      },
    };
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve(ready);
      }, 120);
    });
  }

  sendFrame(buffer: ArrayBuffer): void {
    if (this.closed || buffer.byteLength < FRAME_HEADER_BYTES) {
      return;
    }
    const view = new DataView(buffer);
    const wireSequence = Number(view.getBigUint64(4, false));
    const capturedAt = view.getFloat64(12, false);
    if (this.lastSequence >= 0) {
      this.droppedFrames += Math.max(0, wireSequence - this.lastSequence - 1);
    }
    this.lastSequence = wireSequence;
    const simSequence = this.frameCount;
    this.frameCount += 1;

    const capturedIso = new Date(capturedAt * 1000).toISOString();
    const { objects, events } = this.engine.tick(simSequence, capturedIso);
    for (const object of objects) {
      if (object.presence === "visible" || object.presence === "rediscovered") {
        this.lastSeen.set(object.entity_id, {
          label: object.label,
          at: capturedIso,
          position: object.position_m,
          confidence: object.confidence,
        });
      }
    }

    setTimeout(() => {
      if (this.closed) {
        return;
      }
      const presentedIso = new Date().toISOString();
      this.emit({
        type: "world.patch",
        protocol_version: PROTOCOL_VERSION,
        request_id: `patch-${String(wireSequence)}`,
        scene_id: MOCK_SCENE_ID,
        sequence: wireSequence,
        entities: objects,
      });
      this.emit({
        type: "event.batch",
        protocol_version: PROTOCOL_VERSION,
        request_id: `events-${String(wireSequence)}`,
        scene_id: MOCK_SCENE_ID,
        sequence: wireSequence,
        events,
      });
      this.emit({
        type: "frame.result",
        protocol_version: PROTOCOL_VERSION,
        request_id: `frame-${String(wireSequence)}`,
        sequence: wireSequence,
        captured_at: capturedIso,
        presented_at: presentedIso,
        objects,
        events,
        metrics: {
          sequence: wireSequence,
          capture_to_result_ms: Math.max(
            0,
            Date.now() - capturedAt * 1000,
          ),
          inference_ms:
            SIMULATED_INFERENCE_MS + Math.sin(simSequence * 0.7) * 6,
          queue_depth: 0,
          dropped_frames: this.droppedFrames,
          discovery_ran: simSequence % 12 === 0,
          depth_ran: simSequence % 4 === 0,
          embedding_ran: simSequence % 12 === 0,
        },
        quality: {
          brightness: 0.52 + Math.sin(simSequence * 0.05) * 0.04,
          contrast: 0.61 + Math.sin(simSequence * 0.09) * 0.05,
          sharpness: 0.72 + Math.sin(simSequence * 0.13) * 0.08,
          exposure: 0.93,
          keyframe_score: 0.68 + Math.sin(simSequence * 0.11) * 0.06,
        },
      });
    }, SIMULATED_INFERENCE_MS);
  }

  submitCommand(input: CommandInput): Promise<CommandResult> {
    const cachedKey = JSON.stringify([input.command, input.entityId]);
    const cached = this.commandCache.get(cachedKey);
    const requestId = `sim-cmd-${String(this.frameCount)}`;
    let result: CommandResult;
    if (cached !== undefined && input.command === "query_entity") {
      result = cached;
    } else if (
      (input.command === "query_entity" || input.command === "find_last_seen") &&
      input.entityId !== undefined
    ) {
      const seen = this.lastSeen.get(input.entityId);
      result = {
        type: "command.result",
        protocol_version: PROTOCOL_VERSION,
        request_id: requestId,
        idempotency_key: `sim-${cachedKey}`,
        status: "completed",
        result: {
          entity_id: input.entityId,
          label: seen?.label ?? null,
          last_seen_at: seen?.at ?? null,
          position_m: seen?.position ?? null,
          confidence: seen?.confidence ?? 0,
        },
      };
    } else {
      result = {
        type: "command.result",
        protocol_version: PROTOCOL_VERSION,
        request_id: requestId,
        idempotency_key: `sim-${cachedKey}`,
        status: "completed",
        result: { accepted_by: "worldstate-simulation" },
      };
    }
    this.commandCache.set(cachedKey, result);
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve(result);
      }, 24);
    });
  }

  subscribe(listener: TransportListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  onClose(): void {
    // The simulation never drops the connection.
  }

  close(): void {
    this.closed = true;
    this.listeners.clear();
  }

  private emit(message: ServerMessage): void {
    for (const listener of this.listeners) {
      listener(message);
    }
  }
}
