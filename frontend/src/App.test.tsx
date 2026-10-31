import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

describe("App", () => {
  it("renders Web-Dash header and system ready badge", () => {
    render(<App />);
    expect(screen.getByText("Web-Dash")).toBeInTheDocument();
    expect(screen.getByText("System Ready")).toBeInTheDocument();
  });
});
