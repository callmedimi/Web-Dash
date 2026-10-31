/**
 * i18next configuration for Web-Dash NOC Console.
 * Supports English (LTR) and Persian (RTL) with dynamic direction flipping.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enTranslations from "./locales/en.json";
import faTranslations from "./locales/fa.json";

export const defaultNS = "translation";
export const resources = {
  en: {
    translation: enTranslations,
  },
  fa: {
    translation: faTranslations,
  },
} as const;

export function getInitialLanguage(): string {
  if (typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem("wd.prefs");
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.lang && (parsed.lang === "fa" || parsed.lang === "en")) {
          return parsed.lang;
        }
      }
    } catch {
      // Ignore localStorage read errors
    }
  }
  return "en";
}

i18n.use(initReactI18next).init({
  resources,
  lng: getInitialLanguage(),
  fallbackLng: "en",
  defaultNS: "translation",
  interpolation: {
    escapeValue: false, // React already escapes values
  },
});

// Update document language and text direction dynamically on language change
i18n.on("languageChanged", (lng: string) => {
  if (typeof document !== "undefined") {
    const isRtl = lng === "fa";
    document.documentElement.lang = lng;
    document.documentElement.dir = isRtl ? "rtl" : "ltr";
  }
});

export default i18n;
