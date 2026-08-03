/**
 * Live transport abstraction.
 *
 * `WsTransport` speaks protocol v1 against the local backend. A deterministic
 * in-browser `MockTransport` (lib/live/mock) implements the same surface so
 * the entire interface can run — clearly labeled as a simulation — when no
 * backend is reachable.
 */

import {
  makeCommand,
  makeHello,
  parseServerMessage,
  type ClientHello,
  type CommandInput,
  type CommandResult,
  type ServerMessage,
  type ServerReady,
} from "../protocol/messages";

export type TransportKind = "backend" | "simulation";

export type TransportListener = (message: ServerMessage) => void;

export type LiveTransport = {
  readonly kind: TransportKind;
  connect: (sessionId: string, prompts?: string[]) => Promise<ServerReady>;
  sendFrame: (buffer: ArrayBuffer) => void;
  submitCommand: (input: CommandInput) => Promise<CommandResult>;
  subscribe: (listener: TransportListener) => () => void;
  onClose: (handler: (reason: string) => void) => void;
  close: () => void;
};

const HANDSHAKE_TIMEOUT_MS = 8_000;
const COMMAND_TIMEOUT_MS = 8_000;

export class TransportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TransportError";
  }
}

export class WsTransport implements LiveTransport {
  readonly kind = "backend" as const;

  private socket: WebSocket | null = null;
  private readonly listeners = new Set<TransportListener>();
  private readonly pendingCommands = new Map<
    string,
    { resolve: (result: CommandResult) => void; timer: number }
  >();
  private closeHandler: ((reason: string) => void) | null = null;
  private closed = false;

  constructor(private readonly url: string) {}

  async connect(sessionId: string, prompts?: string[]): Promise<ServerReady> {
    const hello: ClientHello = makeHello(sessionId, prompts);
    return new Promise<ServerReady>((resolve, reject) => {
      let settled = false;
      const socket = new WebSocket(this.url);
      socket.binaryType = "arraybuffer";
      this.socket = socket;

      const timeout = window.setTimeout(() => {
        if (!settled) {
          settled = true;
          socket.close();
          reject(new TransportError("The live handshake timed out."));
        }
      }, HANDSHAKE_TIMEOUT_MS);

      socket.onopen = () => {
        socket.send(JSON.stringify(hello));
      };
      socket.onmessage = (event: MessageEvent<unknown>) => {
        if (typeof event.data !== "string") {
          return;
        }
        const message = parseServerMessage(event.data);
        if (message === null) {
          return;
        }
        if (!settled) {
          if (message.type === "server.ready") {
            settled = true;
            window.clearTimeout(timeout);
            resolve(message);
          } else if (message.type === "error") {
            settled = true;
            window.clearTimeout(timeout);
            reject(new TransportError(message.message));
          } else if (message.type === "flow.slow_down") {
            settled = true;
            window.clearTimeout(timeout);
            reject(
              new TransportError(
                "The backend is busy with another live session.",
              ),
            );
          }
          return;
        }
        this.dispatch(message);
      };
      socket.onclose = (event) => {
        if (!settled) {
          settled = true;
          window.clearTimeout(timeout);
          reject(
            new TransportError(
              event.reason.length > 0
                ? event.reason
                : "The live connection closed during the handshake.",
            ),
          );
          return;
        }
        this.handleClose(event.reason.length > 0 ? event.reason : "closed");
      };
      socket.onerror = () => {
        // onclose always follows; the rejection happens there.
      };
    });
  }

  sendFrame(buffer: ArrayBuffer): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(buffer);
    }
  }

  async submitCommand(input: CommandInput): Promise<CommandResult> {
    const socket = this.socket;
    if (socket?.readyState !== WebSocket.OPEN) {
      throw new TransportError("The live connection is not open.");
    }
    const command = makeCommand(input);
    return new Promise<CommandResult>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.pendingCommands.delete(command.idempotency_key);
        reject(new TransportError("The command timed out."));
      }, COMMAND_TIMEOUT_MS);
      this.pendingCommands.set(command.idempotency_key, { resolve, timer });
      socket.send(JSON.stringify(command));
    });
  }

  subscribe(listener: TransportListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  onClose(handler: (reason: string) => void): void {
    this.closeHandler = handler;
  }

  close(): void {
    this.closed = true;
    this.socket?.close(1000, "client teardown");
    this.socket = null;
  }

  private dispatch(message: ServerMessage): void {
    if (message.type === "command.result") {
      const pending = this.pendingCommands.get(message.idempotency_key);
      if (pending !== undefined) {
        window.clearTimeout(pending.timer);
        this.pendingCommands.delete(message.idempotency_key);
        pending.resolve(message);
      }
    }
    for (const listener of this.listeners) {
      listener(message);
    }
  }

  private handleClose(reason: string): void {
    for (const pending of this.pendingCommands.values()) {
      window.clearTimeout(pending.timer);
    }
    this.pendingCommands.clear();
    if (!this.closed) {
      this.closeHandler?.(reason);
    }
  }
}
