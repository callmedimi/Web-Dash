/**
 * Shared Network Credentials helper (TACACS / SSH credentials)
 * Persisted in sessionStorage across all NOC tool workflows.
 */

export interface NetworkCredentials {
  username: string;
  password: string;
}

const STORAGE_USER_KEY = "webdash:net:user";
const STORAGE_PASS_KEY = "webdash:net:pass";
export const NET_CREDS_EVENT = "webdash:net:creds:updated";

export function getNetworkCredentials(): NetworkCredentials {
  if (typeof window === "undefined") {
    return { username: "", password: "" };
  }
  try {
    const username = sessionStorage.getItem(STORAGE_USER_KEY) || "";
    const password = sessionStorage.getItem(STORAGE_PASS_KEY) || "";
    return { username, password };
  } catch {
    return { username: "", password: "" };
  }
}

export function setNetworkCredentials(creds: NetworkCredentials): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(STORAGE_USER_KEY, creds.username.trim());
    sessionStorage.setItem(STORAGE_PASS_KEY, creds.password);
    window.dispatchEvent(new CustomEvent(NET_CREDS_EVENT, { detail: creds }));
  } catch {
    // Ignore sessionStorage write errors
  }
}

export function clearNetworkCredentials(): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(STORAGE_USER_KEY);
    sessionStorage.removeItem(STORAGE_PASS_KEY);
    window.dispatchEvent(new CustomEvent(NET_CREDS_EVENT, { detail: { username: "", password: "" } }));
  } catch {
    // Ignore sessionStorage write errors
  }
}
