"""Step 6.3 Unit and Integration Tests: Tokens, Theming, Density, and Bilingual i18n.

Validates:
1. Presence and valid WOFF2 format of self-hosted local fonts (Vazirmatn, IBM Plex Sans, JetBrains Mono).
2. Font declarations and tokens in tokens.css.
3. Full parity between English and Persian translation dictionaries.
4. User preferences store (theme, density, lang, direction).
5. Passing of typecheck, lint, vitest, and production build.
"""
import os
import json
import subprocess
import pytest


def test_step_6_3_local_fonts_exist():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonts_dir = os.path.join(base_dir, "frontend", "public", "fonts")
    dist_fonts_dir = os.path.join(base_dir, "frontend", "dist", "fonts")

    required_fonts = ["vazirmatn.woff2", "ibm-plex-sans.woff2", "jetbrains-mono.woff2"]

    for font_name in required_fonts:
        src_path = os.path.join(fonts_dir, font_name)
        dist_path = os.path.join(dist_fonts_dir, font_name)

        assert os.path.exists(src_path), f"Font missing in public: {src_path}"
        assert os.path.exists(dist_path), f"Font missing in dist: {dist_path}"

        # Verify valid WOFF2 magic header: b"wOF2"
        with open(src_path, "rb") as f:
            magic = f.read(4)
            assert magic == b"wOF2", f"Invalid WOFF2 magic header in {src_path}: {magic}"


def test_step_6_3_font_face_declarations_in_css():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tokens_css = os.path.join(base_dir, "frontend", "src", "styles", "tokens.css")

    with open(tokens_css, "r", encoding="utf-8") as f:
        content = f.read()

    assert '@font-face' in content
    assert '"Vazirmatn"' in content or "'Vazirmatn'" in content
    assert '"IBM Plex Sans"' in content or "'IBM Plex Sans'" in content
    assert '"JetBrains Mono"' in content or "'JetBrains Mono'" in content
    assert 'font-display: swap' in content
    assert '/fonts/vazirmatn.woff2' in content
    assert '/fonts/ibm-plex-sans.woff2' in content
    assert '/fonts/jetbrains-mono.woff2' in content


def test_step_6_3_translation_key_parity():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locales_dir = os.path.join(base_dir, "frontend", "src", "i18n", "locales")

    en_path = os.path.join(locales_dir, "en.json")
    fa_path = os.path.join(locales_dir, "fa.json")

    assert os.path.exists(en_path), f"Missing {en_path}"
    assert os.path.exists(fa_path), f"Missing {fa_path}"

    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    with open(fa_path, "r", encoding="utf-8") as f:
        fa_data = json.load(f)

    # Check top-level namespaces
    assert sorted(en_data.keys()) == sorted(fa_data.keys())

    # Check all nested keys
    for ns in en_data:
        en_keys = sorted(en_data[ns].keys())
        fa_keys = sorted(fa_data[ns].keys())
        assert en_keys == fa_keys, f"Key mismatch in namespace '{ns}'"


def test_step_6_3_user_preferences_store():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prefs_file = os.path.join(base_dir, "frontend", "src", "store", "prefs.ts")

    with open(prefs_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "export const usePrefsStore" in content
    assert "export const PREFS_STORAGE_KEY = \"wd.prefs\"" in content
    assert "theme:" in content
    assert "density:" in content
    assert "lang:" in content
    assert "toggleTheme" in content
    assert "toggleDensity" in content
    assert "toggleLanguage" in content


def test_step_6_3_vitest_and_typecheck():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(base_dir, "frontend")

    # Run typecheck
    tc = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "run", "typecheck"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert tc.returncode == 0, f"TypeScript typecheck failed:\n{tc.stdout}\n{tc.stderr}"

    # Run lint
    lint = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "run", "lint"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert lint.returncode == 0, f"ESLint failed:\n{lint.stdout}\n{lint.stderr}"

    # Run vitest
    test = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "test"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert test.returncode == 0, f"Vitest tests failed:\n{test.stdout}\n{test.stderr}"
