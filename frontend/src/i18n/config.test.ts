import { describe, it, expect } from "vitest";
import i18n, { resources } from "./config";

describe("i18n Configuration & Localization", () => {
  it("has matching translation keys between en and fa", () => {
    const enSections = Object.keys(resources.en.translation);
    const faSections = Object.keys(resources.fa.translation);

    expect(enSections.sort()).toEqual(faSections.sort());

    for (const sec of enSections as Array<keyof typeof resources.en.translation>) {
      const enSubKeys = Object.keys(resources.en.translation[sec]).sort();
      const faSubKeys = Object.keys(resources.fa.translation[sec]).sort();
      expect(enSubKeys).toEqual(faSubKeys);
    }
  });

  it("translates common and auth keys correctly in English and Persian", async () => {
    await i18n.changeLanguage("en");
    expect(i18n.t("common.systemReady")).toBe("System Ready");
    expect(i18n.t("auth.signInButton")).toBe("Sign in to console");
    expect(i18n.t("prefs.densityCompact")).toBe("Compact");

    await i18n.changeLanguage("fa");
    expect(i18n.t("common.systemReady")).toBe("سامانه آماده است");
    expect(i18n.t("auth.signInButton")).toBe("ورود به سامانه");
    expect(i18n.t("prefs.densityCompact")).toBe("فشرده");
  });

  it("updates documentElement attributes on languageChanged", async () => {
    await i18n.changeLanguage("fa");
    expect(document.documentElement.lang).toBe("fa");
    expect(document.documentElement.dir).toBe("rtl");

    await i18n.changeLanguage("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });
});
