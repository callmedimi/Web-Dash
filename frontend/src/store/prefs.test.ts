import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  usePrefsStore,
  PREFS_STORAGE_KEY,
  DEFAULT_PREFS,
  resolveEffectiveTheme,
} from "./prefs";
import i18n from "@/i18n/config";

describe("User Preferences Store (wd.prefs)", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("data-density");
    document.documentElement.removeAttribute("dir");
    document.documentElement.removeAttribute("lang");
    document.documentElement.className = "";
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("initializes with default preferences when localStorage is empty", () => {
    usePrefsStore.getState().initPrefs();
    const state = usePrefsStore.getState();

    expect(state.theme).toBe(DEFAULT_PREFS.theme);
    expect(state.density).toBe(DEFAULT_PREFS.density);
    expect(state.lang).toBe(DEFAULT_PREFS.lang);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-density")).toBe("compact");
    expect(document.documentElement.getAttribute("dir")).toBe("ltr");
    expect(document.documentElement.getAttribute("lang")).toBe("en");
  });

  it("loads existing preferences from localStorage", () => {
    localStorage.setItem(
      PREFS_STORAGE_KEY,
      JSON.stringify({
        theme: "light",
        density: "comfortable",
        lang: "fa",
      })
    );

    usePrefsStore.getState().initPrefs();
    const state = usePrefsStore.getState();

    expect(state.theme).toBe("light");
    expect(state.density).toBe("comfortable");
    expect(state.lang).toBe("fa");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-density")).toBe("comfortable");
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    expect(document.documentElement.getAttribute("lang")).toBe("fa");
  });

  it("updates theme and persists to localStorage", () => {
    usePrefsStore.getState().initPrefs();

    usePrefsStore.getState().setTheme("light");
    expect(usePrefsStore.getState().theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);

    const stored = JSON.parse(localStorage.getItem(PREFS_STORAGE_KEY) || "{}");
    expect(stored.theme).toBe("light");

    usePrefsStore.getState().toggleTheme();
    expect(usePrefsStore.getState().theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("updates density mode between compact (28px) and comfortable (36px)", () => {
    usePrefsStore.getState().initPrefs();

    usePrefsStore.getState().setDensity("comfortable");
    expect(usePrefsStore.getState().density).toBe("comfortable");
    expect(document.documentElement.getAttribute("data-density")).toBe("comfortable");

    usePrefsStore.getState().toggleDensity();
    expect(usePrefsStore.getState().density).toBe("compact");
    expect(document.documentElement.getAttribute("data-density")).toBe("compact");
  });

  it("updates language and flips text direction to RTL for Persian", () => {
    usePrefsStore.getState().initPrefs();

    usePrefsStore.getState().setLanguage("fa");
    expect(usePrefsStore.getState().lang).toBe("fa");
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    expect(document.documentElement.getAttribute("lang")).toBe("fa");
    expect(i18n.language).toBe("fa");

    usePrefsStore.getState().toggleLanguage();
    expect(usePrefsStore.getState().lang).toBe("en");
    expect(document.documentElement.getAttribute("dir")).toBe("ltr");
    expect(document.documentElement.getAttribute("lang")).toBe("en");
    expect(i18n.language).toBe("en");
  });

  it("resolves system theme based on matchMedia", () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = () =>
      ({
        matches: true, // prefers-color-scheme: dark
        media: "(prefers-color-scheme: dark)",
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;

    expect(resolveEffectiveTheme("system")).toBe("dark");

    window.matchMedia = () =>
      ({
        matches: false, // prefers-color-scheme: light
        media: "(prefers-color-scheme: dark)",
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;

    expect(resolveEffectiveTheme("system")).toBe("light");

    window.matchMedia = originalMatchMedia;
  });
});
