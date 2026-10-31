import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useAuthStore } from "./auth";
import { getCsrfToken, setCsrfToken, AUTH_UNAUTHORIZED_EVENT } from "@/api/client";

describe("Auth Store (Zustand)", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    useAuthStore.getState().reset();
    setCsrfToken(null);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("initializes with unauthenticated state", () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
  });

  it("checks auth successfully with /api/v1/me", async () => {
    const mockMeResponse = {
      authenticated: true,
      username: "admin_user",
      role: "admin",
      display_name: "Operations Admin",
      must_change_password: false,
      features: { user_management: true, alarm_clear: true },
      csrf_token: "csrf_token_abc_123",
      read_only: false,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => mockMeResponse,
    });

    const isAuthed = await useAuthStore.getState().checkAuth();
    expect(isAuthed).toBe(true);

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user?.username).toBe("admin_user");
    expect(state.user?.role).toBe("admin");
    expect(getCsrfToken()).toBe("csrf_token_abc_123");
  });

  it("handles login and sets user + CSRF token", async () => {
    const mockLoginResponse = {
      username: "noc_operator",
      role: "operator",
      display_name: "NOC Operator 01",
      must_change_password: false,
      features: { alarm_clear: true },
      csrf_token: "csrf_token_op_456",
      read_only: false,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => mockLoginResponse,
    });

    const user = await useAuthStore.getState().login({
      username: "noc_operator",
      password: "SafePassword123!",
    });

    expect(user.username).toBe("noc_operator");
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(getCsrfToken()).toBe("csrf_token_op_456");
  });

  it("handles logout and clears auth state", async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        username: "test",
        role: "operator",
        display_name: "Test",
        must_change_password: false,
        features: {},
      },
    });
    setCsrfToken("active_token");

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({ status: "logged_out" }),
    });

    await useAuthStore.getState().logout();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
    expect(getCsrfToken()).toBeNull();
  });

  it("clears auth state on AUTH_UNAUTHORIZED_EVENT", () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        username: "test",
        role: "operator",
        display_name: "Test",
        must_change_password: false,
        features: {},
      },
    });
    setCsrfToken("active_token");

    window.dispatchEvent(
      new CustomEvent(AUTH_UNAUTHORIZED_EVENT, {
        detail: {
          error: { code: "SESSION_EXPIRED" },
        },
      })
    );

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().idleTimeoutNotice).toBe(true);
  });
});
