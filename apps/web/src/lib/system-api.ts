export type SystemStatus = {
  environment: string;
  persistence_enabled: boolean;
  protocol_version: "v1";
  product_phase: "foundation";
};

const apiBaseUrl =
  import.meta.env.VITE_WORLDSTATE_API_URL ?? "http://127.0.0.1:8000";

export async function getSystemStatus(signal: AbortSignal): Promise<SystemStatus> {
  const response = await fetch(`${apiBaseUrl}/api/v1/system`, { signal });

  if (!response.ok) {
    throw new Error(`WorldState API returned ${String(response.status)}`);
  }

  return (await response.json()) as SystemStatus;
}
