/**
 * User Preferences Store (wd.prefs).
 * Manages Theme (light/dark/system), Density (compact/comfortable),
 * and Language (en/fa + RTL) per user, persisted in localStorage.
 */
import { create } from "zustand";
import i18n from "@/i18n/config";

export type ThemeMode = "light" | "dark" | "system";
export type DensityMode = "compact" | "comfortable";
export type LanguageMode = "en" | "fa";

export interface UserPrefs {
  theme: ThemeMode;
  density: DensityMode;
  lang: LanguageMode;
}

export interface PrefsState extends UserPrefs {
  resolvedTheme: "light" | "dark";

  // Actions
  setTheme: (theme: ThemeMode) => void;
  setDensity: (density: DensityMode) => void;
  setLanguage: (lang: LanguageMode) => void;
  toggleTheme: () => void;
  toggleDensity: () => void;
  toggleLanguage: () => void;
  initPrefs: () => void;
}

export const PREFS_STORAGE_KEY = "wd.prefs";

export const DEFAULT_PREFS: UserPrefs = {
  theme: "dark", // NOC default: dark mode ("Night")
  density: "compact", // NOC default: 28px row height
  lang: "en",
};

export function loadStoredPrefs(): UserPrefs {
  if (typeof window === "undefined") {
    return DEFAULT_PREFS;
  }
  try {
    const raw = localStorage.getItem(PREFS_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        theme: ["light", "dark", "system"].includes(parsed.theme)
          ? parsed.theme
          : DEFAULT_PREFS.theme,
        density: ["compact", "comfortable"].includes(parsed.density)
          ? parsed.density
          : DEFAULT_PREFS.density,
        lang: ["en", "fa"].includes(parsed.lang) ? parsed.lang : DEFAULT_PREFS.lang,
      };
    }
  } catch {
    // Fallback on parse failure
  }
  return DEFAULT_PREFS;
}

export function savePrefs(prefs: UserPrefs): void {
  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Ignore quota errors
    }
  }
}

export function resolveEffectiveTheme(theme: ThemeMode): "light" | "dark" {
  if (theme === "system" && typeof window !== "undefined") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return theme === "light" ? "light" : "dark";
}

export function applyPrefsToDom(prefs: UserPrefs): "light" | "dark" {
  if (typeof document === "undefined") {
    return resolveEffectiveTheme(prefs.theme);
  }

  const effectiveTheme = resolveEffectiveTheme(prefs.theme);
  const root = document.documentElement;

  // 1. Theme
  root.setAttribute("data-theme", effectiveTheme);
  if (effectiveTheme === "dark") {
    root.classList.add("dark");
    root.classList.remove("light");
  } else {
    root.classList.add("light");
    root.classList.remove("dark");
  }

  // 2. Density
  root.setAttribute("data-density", prefs.density);

  // 3. Language & Direction
  const isRtl = prefs.lang === "fa";
  root.lang = prefs.lang;
  root.dir = isRtl ? "rtl" : "ltr";

  // 4. Update i18n instance
  if (i18n.language !== prefs.lang) {
    i18n.changeLanguage(prefs.lang);
  }

  return effectiveTheme;
}

export const usePrefsStore = create<PrefsState>((set, get) => {
  return {
    ...DEFAULT_PREFS,
    resolvedTheme: "dark",

    initPrefs: () => {
      const prefs = loadStoredPrefs();
      const resolved = applyPrefsToDom(prefs);
      set({
        ...prefs,
        resolvedTheme: resolved,
      });

      // Listen for system color scheme changes when mode is 'system'
      if (typeof window !== "undefined" && window.matchMedia) {
        const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
        const handler = () => {
          if (get().theme === "system") {
            const newResolved = applyPrefsToDom(get());
            set({ resolvedTheme: newResolved });
          }
        };
        try {
          mediaQuery.addEventListener("change", handler);
        } catch {
          mediaQuery.addListener?.(handler);
        }
      }
    },

    setTheme: (theme: ThemeMode) => {
      const next: UserPrefs = { ...get(), theme };
      savePrefs(next);
      const resolved = applyPrefsToDom(next);
      set({ theme, resolvedTheme: resolved });
    },

    setDensity: (density: DensityMode) => {
      const next: UserPrefs = { ...get(), density };
      savePrefs(next);
      applyPrefsToDom(next);
      set({ density });
    },

    setLanguage: (lang: LanguageMode) => {
      const next: UserPrefs = { ...get(), lang };
      savePrefs(next);
      applyPrefsToDom(next);
      set({ lang });
    },

    toggleTheme: () => {
      const current = get().resolvedTheme;
      const nextTheme: ThemeMode = current === "dark" ? "light" : "dark";
      get().setTheme(nextTheme);
    },

    toggleDensity: () => {
      const current = get().density;
      const nextDensity: DensityMode = current === "compact" ? "comfortable" : "compact";
      get().setDensity(nextDensity);
    },

    toggleLanguage: () => {
      const current = get().lang;
      const nextLang: LanguageMode = current === "en" ? "fa" : "en";
      get().setLanguage(nextLang);
    },
  };
});
