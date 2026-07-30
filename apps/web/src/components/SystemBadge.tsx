import { useSystemStatus } from "../hooks/useSystemStatus";

type SystemStatusState = ReturnType<typeof useSystemStatus>;

function statusCopy(status: SystemStatusState) {
  switch (status.kind) {
    case "loading":
      return { label: "Checking coordinator", tone: "pending" };
    case "online":
      return {
        label: `Coordinator online / ${status.value.protocol_version}`,
        tone: "online",
      };
    case "offline":
      return { label: "Coordinator offline", tone: "offline" };
  }
}

export function SystemBadge() {
  const status = useSystemStatus();
  const copy = statusCopy(status);

  return (
    <div className={`system-badge system-badge--${copy.tone}`} role="status">
      <span className="system-badge__signal" aria-hidden="true" />
      <span>{copy.label}</span>
    </div>
  );
}
