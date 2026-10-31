import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  apiClient,
  request,
  setCsrfToken,
  parseApiError,
  queryClient,
  AUTH_UNAUTHORIZED_EVENT,
  AUTH_PASSWORD_CHANGE_REQUIRED_EVENT,
} from "./client";
import { ApiError } from "./types";

describe("API Client & Error Mapping", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    setCsrfToken(null);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe("parseApiError", () => {
    it("maps Target Architecture §4 nested error format", () => {
      const payload = {
        error: {
          code: "VALIDATION_ERROR",
          message: "Payload validation failed",
          fields: { ip_address: ["Invalid IPv4 format"] },
        },
      };

      const err = parseApiError(422, payload);
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(422);
      expect(err.code).toBe("VALIDATION_ERROR");
      expect(err.message).toBe("Payload validation failed");
      expect(err.fields).toEqual({ ip_address: ["Invalid IPv4 format"] });
    });

    it("maps Flask standard error format", () => {
      const payload = {
        error: "Invalid credentials",
        code: "INVALID_CREDENTIALS",
      };

      const err = parseApiError(401, payload);
      expect(err.status).toBe(401);
      expect(err.code).toBe("INVALID_CREDENTIALS");
      expect(err.message).toBe("Invalid credentials");
    });

    it("maps RFC 7807 problem details with invalid_params", () => {
      const payload = {
        title: "Unprocessable Entity",
        detail: "Validation failed on fields",
        invalid_params: [{ name: "device_id", reason: "Must be a UUID" }],
      };

      const err = parseApiError(422, payload);
      expect(err.status).toBe(422);
      expect(err.message).toBe("Validation failed on fields");
      expect(err.fields).toEqual({ device_id: "Must be a UUID" });
    });

    it("falls back to generic message on empty or string response", () => {
      const err = parseApiError(500, "Internal Server Error");
      expect(err.status).toBe(500);
      expect(err.code).toBe("HTTP_500");
      expect(err.message).toBe("Internal Server Error");
    });
  });

  describe("request() with CSRF & Content-Type", () => {
    it("attaches X-CSRF-Token header on mutating requests when token is set", async () => {
      setCsrfToken("csrf_secret_12345");

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ status: "ok" }),
      });
      globalThis.fetch = mockFetch;

      const res = await apiClient.post("/api/v1/devices", { name: "R1" });
      expect(res).toEqual({ status: "ok" });

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, init] = mockFetch.mock.calls[0];
      expect(url).toBe("/api/v1/devices");
      expect(init.method).toBe("POST");

      const headers = new Headers(init.headers);
      expect(headers.get("X-CSRF-Token")).toBe("csrf_secret_12345");
      expect(headers.get("Content-Type")).toBe("application/json; charset=utf-8");
      expect(init.body).toBe(JSON.stringify({ name: "R1" }));
    });

    it("does not attach X-CSRF-Token on GET requests", async () => {
      setCsrfToken("csrf_secret_12345");

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ items: [] }),
      });
      globalThis.fetch = mockFetch;

      await apiClient.get("/api/v1/devices");

      const [, init] = mockFetch.mock.calls[0];
      const headers = new Headers(init.headers);
      expect(headers.get("X-CSRF-Token")).toBeNull();
    });

    it("handles 204 No Content without attempting JSON parse", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        headers: new Headers(),
      });
      globalThis.fetch = mockFetch;

      const res = await apiClient.delete("/api/v1/devices/1");
      expect(res).toBeUndefined();
    });
  });

  describe("401 Unauthorized handling", () => {
    it("dispatches AUTH_UNAUTHORIZED_EVENT and throws ApiError on 401", async () => {
      const eventSpy = vi.fn();
      window.addEventListener(AUTH_UNAUTHORIZED_EVENT, eventSpy);

      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({
          error: "Session expired due to inactivity",
          code: "SESSION_EXPIRED",
        }),
      });
      globalThis.fetch = mockFetch;

      await expect(request("/api/v1/devices")).rejects.toThrow(ApiError);

      expect(eventSpy).toHaveBeenCalledTimes(1);
      const dispatchedEvent = eventSpy.mock.calls[0][0] as CustomEvent;
      expect(dispatchedEvent.detail.status).toBe(401);
      expect(dispatchedEvent.detail.error.code).toBe("SESSION_EXPIRED");

      window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, eventSpy);
    });
  });

  describe("403 PASSWORD_CHANGE_REQUIRED handling", () => {
    it("dispatches AUTH_PASSWORD_CHANGE_REQUIRED_EVENT on 403 password change required", async () => {
      const eventSpy = vi.fn();
      window.addEventListener(AUTH_PASSWORD_CHANGE_REQUIRED_EVENT, eventSpy);

      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({
          error: "Password change required",
          code: "PASSWORD_CHANGE_REQUIRED",
        }),
      });
      globalThis.fetch = mockFetch;

      await expect(request("/api/v1/devices")).rejects.toThrow(ApiError);

      expect(eventSpy).toHaveBeenCalledTimes(1);
      const dispatchedEvent = eventSpy.mock.calls[0][0] as CustomEvent;
      expect(dispatchedEvent.detail.status).toBe(403);
      expect(dispatchedEvent.detail.error.code).toBe("PASSWORD_CHANGE_REQUIRED");

      window.removeEventListener(AUTH_PASSWORD_CHANGE_REQUIRED_EVENT, eventSpy);
    });
  });

  describe("TanStack QueryClient retry rules", () => {
    it("never retries 4xx errors", () => {
      const defaultOptions = queryClient.getDefaultOptions();
      const retryFn = defaultOptions.queries?.retry as (
        count: number,
        err: unknown
      ) => boolean;

      const err400 = new ApiError("Bad Request", 400, "BAD_REQUEST");
      const err401 = new ApiError("Unauthorized", 401, "UNAUTHORIZED");
      const err403 = new ApiError("Forbidden", 403, "FORBIDDEN");
      const err422 = new ApiError("Unprocessable", 422, "VALIDATION_ERROR");

      expect(retryFn(0, err400)).toBe(false);
      expect(retryFn(0, err401)).toBe(false);
      expect(retryFn(0, err403)).toBe(false);
      expect(retryFn(0, err422)).toBe(false);
    });

    it("retries once for 5xx or network errors", () => {
      const defaultOptions = queryClient.getDefaultOptions();
      const retryFn = defaultOptions.queries?.retry as (
        count: number,
        err: unknown
      ) => boolean;

      const err500 = new ApiError("Internal error", 500, "SERVER_ERROR");
      expect(retryFn(0, err500)).toBe(true);
      expect(retryFn(1, err500)).toBe(false);

      const networkErr = new Error("Network offline");
      expect(retryFn(0, networkErr)).toBe(true);
      expect(retryFn(1, networkErr)).toBe(false);
    });
  });
});
