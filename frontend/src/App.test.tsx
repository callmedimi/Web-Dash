import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";
import { useAuthStore } from "./store/auth";

describe("App", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/");
    useAuthStore.getState().reset();
    vi.restoreAllMocks();
  });

  it("renders login screen when unauthenticated", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({ authenticated: false }),
    });

    render(<App />);
    expect(await screen.findByText("Sign in to Operations Console")).toBeInTheDocument();
    expect(screen.getByText("Web-Dash")).toBeInTheDocument();
  });

  it("renders NOC shell and dashboard when authenticated", async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      isLoading: false,
      user: {
        username: "operator01",
        role: "operator",
        display_name: "Operator One",
        must_change_password: false,
        features: {},
      },
    });

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({
        authenticated: true,
        username: "operator01",
        role: "operator",
        display_name: "Operator One",
        must_change_password: false,
        features: {},
      }),
    });

    render(<App />);
    expect(await screen.findByText("System Ready")).toBeInTheDocument();
    expect(screen.getByText("Operations Overview")).toBeInTheDocument();
  });
});
