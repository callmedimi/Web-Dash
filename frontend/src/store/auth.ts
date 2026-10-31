/**
 * Authentication and Session Zustand Store for Web-Dash.
 */
import { create } from "zustand";
import {
  apiClient,
  setCsrfToken,
  AUTH_UNAUTHORIZED_EVENT,
  AUTH_PASSWORD_CHANGE_REQUIRED_EVENT,
} from "@/api/client";
import {
  UserInfo,
  MeResponse,
  LoginPayload,
  LoginResponse,
  ChangePasswordPayload,
  ChangePasswordResponse,
} from "@/api/types";

export interface AuthState {
  user: UserInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  readOnly: boolean;
  idleTimeoutNotice: boolean;

  // Actions
  checkAuth: () => Promise<boolean>;
  login: (payload: LoginPayload) => Promise<UserInfo>;
  logout: () => Promise<void>;
  changePassword: (payload: ChangePasswordPayload) => Promise<void>;
  setIdleTimeoutNotice: (open: boolean) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => {
  // Listen for global auth events dispatched by API client
  if (typeof window !== "undefined") {
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, (event: Event) => {
      const customEvent = event as CustomEvent;
      // If we were authenticated, mark session as expired
      if (get().isAuthenticated) {
        set({
          user: null,
          isAuthenticated: false,
          idleTimeoutNotice: customEvent.detail?.error?.code === "SESSION_EXPIRED",
        });
        setCsrfToken(null);
      }
    });

    window.addEventListener(AUTH_PASSWORD_CHANGE_REQUIRED_EVENT, () => {
      const currentUser = get().user;
      if (currentUser && !currentUser.must_change_password) {
        set({
          user: {
            ...currentUser,
            must_change_password: true,
          },
        });
      }
    });
  }

  return {
    user: null,
    isAuthenticated: false,
    isLoading: true,
    readOnly: false,
    idleTimeoutNotice: false,

    checkAuth: async () => {
      set({ isLoading: true });
      try {
        const data = await apiClient.get<MeResponse>("/api/v1/me");
        if (data.authenticated && data.username) {
          const user: UserInfo = {
            username: data.username,
            role: data.role || "viewer",
            display_name: data.display_name || data.username,
            must_change_password: Boolean(data.must_change_password),
            features: data.features || {},
            csrf_token: data.csrf_token,
            read_only: Boolean(data.read_only),
          };
          if (data.csrf_token) {
            setCsrfToken(data.csrf_token);
          }
          set({
            user,
            isAuthenticated: true,
            readOnly: Boolean(data.read_only),
            isLoading: false,
          });
          return true;
        } else {
          set({
            user: null,
            isAuthenticated: false,
            readOnly: Boolean(data.read_only),
            isLoading: false,
          });
          setCsrfToken(data.csrf_token || null);
          return false;
        }
      } catch {
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
        });
        setCsrfToken(null);
        return false;
      }
    },

    login: async (payload: LoginPayload) => {
      set({ isLoading: true });
      try {
        const data = await apiClient.post<LoginResponse>("/api/v1/login", payload);
        const user: UserInfo = {
          username: data.username,
          role: data.role,
          display_name: data.display_name || data.username,
          must_change_password: Boolean(data.must_change_password),
          features: data.features || {},
          csrf_token: data.csrf_token,
          read_only: Boolean(data.read_only),
        };
        if (data.csrf_token) {
          setCsrfToken(data.csrf_token);
        }
        set({
          user,
          isAuthenticated: true,
          readOnly: Boolean(data.read_only),
          isLoading: false,
          idleTimeoutNotice: false,
        });
        return user;
      } catch (err) {
        set({ isLoading: false });
        throw err;
      }
    },

    logout: async () => {
      try {
        await apiClient.post("/api/v1/logout", {});
      } catch {
        // Ignore network failure during logout
      } finally {
        setCsrfToken(null);
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
        });
      }
    },

    changePassword: async (payload: ChangePasswordPayload) => {
      await apiClient.post<ChangePasswordResponse>("/api/v1/change-password", payload);
      const currentUser = get().user;
      if (currentUser) {
        set({
          user: {
            ...currentUser,
            must_change_password: false,
          },
        });
      }
    },

    setIdleTimeoutNotice: (open: boolean) => {
      set({ idleTimeoutNotice: open });
    },

    reset: () => {
      setCsrfToken(null);
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        idleTimeoutNotice: false,
      });
    },
  };
});
