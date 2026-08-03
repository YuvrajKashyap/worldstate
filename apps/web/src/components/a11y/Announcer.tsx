/** Polite live region announcing world changes without interrupting. */

import { useEffect, useState } from "react";

import { useWorldStore } from "../../state/worldStore";

export function Announcer() {
  const announcement = useWorldStore((state) => state.announcement);
  const [message, setMessage] = useState("");

  // Throttle: at most one spoken update per 4 seconds.
  useEffect(() => {
    if (announcement === null) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (!cancelled) {
        setMessage(announcement);
      }
    }, 150);
    const clear = window.setTimeout(() => {
      if (!cancelled) {
        setMessage("");
      }
    }, 4000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.clearTimeout(clear);
    };
  }, [announcement]);

  return (
    <div aria-live="polite" role="status" className="visually-hidden">
      {message}
    </div>
  );
}
