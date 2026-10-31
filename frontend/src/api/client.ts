/**
 * HTTP Client and TanStack Query configuration for Web-Dash.
 * Enforces JSON communication, CSRF headers, error mapping, and auth event dispatching.
 */
import { QueryClient } from "@tanstack/react-query";
import { ApiError, ApiProblemDetails, FieldErrors } from "./types";

export const AUTH_UNAUTHORIZED_EVENT = "webdash:auth:unauthorized";
export const AUTH_PASSWORD_CHANGE_REQUIRED_EVENT = "webdash:auth:password-change-required";

let inMemoryCsrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  inMemoryCsrfToken = token;
}

export function getCsrfToken(): string | null {
  return inMemoryCsrfToken;
}

/**
 * Maps varied backend error payloads (Target Architecture §4, RFC 7807, or Flask standard)
 * to a consistent typed ApiError.
 */
export function parseApiError(status: number, data: unknown): ApiError {
  if (data && typeof data === "object") {
    const payload = data as ApiProblemDetails;

    let code = "HTTP_" + status;
    let message = "Request failed with status " + status;
    let fields: FieldErrors | undefined = undefined;

    // 1. Nested format: { error: { code: '...', message: '...', fields: { ... } } }
    if (payload.error && typeof payload.error === "object") {
      const errObj = payload.error;
      if (errObj.code) code = errObj.code;
      if (errObj.message) message = errObj.message;
      if (errObj.fields) fields = errObj.fields;
    }
    // 2. Direct format: { code: '...', message: '...', fields: { ... } }
    else {
      if (payload.code) code = payload.code;
      if (typeof payload.error === "string") {
        message = payload.error;
      } else if (payload.message) {
        message = payload.message;
      } else if (payload.detail) {
        message = payload.detail;
      } else if (payload.title) {
        message = payload.title;
      }
      if (payload.fields) fields = payload.fields;
    }

    // RFC 7807 invalid_params list conversion
    if (payload.invalid_params && Array.isArray(payload.invalid_params)) {
      fields = fields || {};
      for (const param of payload.invalid_params) {
        fields[param.name] = param.reason;
      }
    }

    return new ApiError(message, status, code, fields, data);
  }

  const rawText = typeof data === "string" ? data : "";
  return new ApiError(
    rawText || "Request failed with status " + status,
    status,
    "HTTP_" + status,
    undefined,
    data
  );
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  skipCsrf?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, headers: customHeaders, skipCsrf = false, ...fetchInit } = options;

  const method = (fetchInit.method || "GET").toUpperCase();
  const headers = new Headers(customHeaders || {});

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  // Mutating requests require CSRF token
  const isMutating = ["POST", "PUT", "DELETE", "PATCH"].includes(method);
  if (isMutating && !skipCsrf && inMemoryCsrfToken) {
    headers.set("X-CSRF-Token", inMemoryCsrfToken);
  }

  let finalBody: BodyInit | undefined = undefined;
  if (body !== undefined && body !== null) {
    if (body instanceof FormData || body instanceof Blob || typeof body === "string") {
      finalBody = body as BodyInit;
    } else {
      headers.set("Content-Type", "application/json; charset=utf-8");
      finalBody = JSON.stringify(body);
    }
  }

  const response = await fetch(path, {
    ...fetchInit,
    method,
    headers,
    body: finalBody,
    credentials: "same-origin",
  });

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as unknown as T;
  }

  let responseData: unknown;
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    try {
      responseData = await response.json();
    } catch {
      responseData = null;
    }
  } else {
    responseData = await response.text();
  }

  if (!response.ok) {
    const apiError = parseApiError(response.status, responseData);

    // 401 Unauthorized handling
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent(AUTH_UNAUTHORIZED_EVENT, {
          detail: { path, status: 401, error: apiError },
        })
      );
    }

    // 403 PASSWORD_CHANGE_REQUIRED handling
    if (
      response.status === 403 &&
      apiError.code === "PASSWORD_CHANGE_REQUIRED" &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(
        new CustomEvent(AUTH_PASSWORD_CHANGE_REQUIRED_EVENT, {
          detail: { path, status: 403, error: apiError },
        })
      );
    }

    throw apiError;
  }

  return responseData as T;
}

export const apiClient = {
  request,
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

/**
 * Global TanStack Query Client configured per NOC standards:
 * - staleTime: 15 seconds
 * - retry: 1 time on 5xx or network errors; NEVER retry 4xx errors
 * - refetchOnWindowFocus: false (avoids disruptive NOC re-renders during active inspection)
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false;
        }
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});
