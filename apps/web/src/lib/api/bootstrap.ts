/**
 * One-time fragment bootstrap (API_PROTOCOL.md):
 *
 * 1. Read `bootstrap` from location.hash.
 * 2. POST /api/v1/bootstrap with the token.
 * 3. Keep the CSRF token in memory only.
 * 4. Remove the fragment immediately with history.replaceState.
 */

import { api, ApiError, setCsrfToken } from "./http";

export type BootstrapOutcome =
  | { status: "established"; expiresAt: string }
  | { status: "no-token" }
  | { status: "rejected"; message: string }
  | { status: "unreachable" };

/** Extract and consume the `bootstrap` fragment parameter, if present. */
export function readBootstrapFragment(
  hash: string = window.location.hash,
): string | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (raw.length === 0) {
    return null;
  }
  const params = new URLSearchParams(raw);
  const token = params.get("bootstrap");
  return token !== null && token.length > 0 ? token : null;
}

export function scrubFragment(): void {
  if (window.location.hash.length > 0) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
}

export async function establishSession(token: string): Promise<BootstrapOutcome> {
  try {
    const response = await api.bootstrap(token);
    setCsrfToken(response.csrf_token);
    return { status: "established", expiresAt: response.expires_at };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 0) {
        return { status: "unreachable" };
      }
      return { status: "rejected", message: error.message };
    }
    return { status: "rejected", message: "Bootstrap failed unexpectedly." };
  }
}

/**
 * Restore the memory-only CSRF capability from an authenticated, same-origin
 * cookie session. The backend rejects cross-origin POSTs and never exposes
 * the HttpOnly session credential to JavaScript.
 */
export async function probeExistingSession(): Promise<boolean> {
  try {
    const response = await api.refreshSession();
    setCsrfToken(response.csrf_token);
    return true;
  } catch {
    setCsrfToken(null);
    return false;
  }
}
