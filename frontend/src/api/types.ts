/**
 * API and Authentication Types for Web-Dash NOC Console.
 */

export interface FieldErrors {
  [fieldName: string]: string[] | string;
}

export interface ApiProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  code?: string;
  error?: string | { code?: string; message?: string; fields?: FieldErrors };
  message?: string;
  fields?: FieldErrors;
  invalid_params?: Array<{ name: string; reason: string }>;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly fields?: FieldErrors;
  public readonly raw?: unknown;

  constructor(
    message: string,
    status: number,
    code = "UNKNOWN_ERROR",
    fields?: FieldErrors,
    raw?: unknown
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.raw = raw;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export type UserRole = "god" | "admin" | "operator" | "viewer" | string;

export interface UserInfo {
  username: string;
  role: UserRole;
  display_name: string;
  must_change_password: boolean;
  features: Record<string, boolean>;
  csrf_token?: string;
  read_only?: boolean;
}

export interface MeResponse {
  authenticated: boolean;
  username?: string;
  role?: UserRole;
  display_name?: string;
  must_change_password?: boolean;
  features?: Record<string, boolean>;
  csrf_token?: string;
  read_only?: boolean;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LoginResponse {
  username: string;
  role: UserRole;
  display_name: string;
  must_change_password: boolean;
  features: Record<string, boolean>;
  csrf_token: string;
  read_only?: boolean;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface ChangePasswordResponse {
  status: string;
  message?: string;
}
