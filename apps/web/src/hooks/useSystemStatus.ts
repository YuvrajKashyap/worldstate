import { useEffect, useState } from "react";

import {
  getSystemStatus,
  type SystemStatus,
} from "../lib/system-api";

type StatusState =
  | { kind: "loading" }
  | { kind: "online"; value: SystemStatus }
  | { kind: "offline" };

export function useSystemStatus(): StatusState {
  const [status, setStatus] = useState<StatusState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    void getSystemStatus(controller.signal)
      .then((value) => {
        setStatus({ kind: "online", value });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setStatus({ kind: "offline" });
      });

    return () => {
      controller.abort();
    };
  }, []);

  return status;
}
