# 05 — گزارش مراحل پیاده‌سازی گام‌به‌گام (Implementation Log)

این سند گزارش پیشرفت و اجرای مرحله‌به‌مرحله اقدامات فنی فاز ۱ تا ۸ پروژه **Web-Dash** را ثبت می‌کند.

---

## فاز ۱ — امنیت و پایدارسازی (Phase 1: Stabilize & Security)

### گام ۱.۰ — ممیزی کامل کدهای ندیده‌شده (Step 1.0 Audit)
* **وضعیت:** تکمیل شد (Done)
* **تغییرات:**
  * ممیزی فایل‌های فرانت‌اند (`templates/index.html` با بیش از ۴۴۰۰ خط کد جاوااسکریپت و استایل‌های لوکال Bootstrap/netmate).
  * ممیزی کامل سرویس‌های Zabbix، PTP، ARP/MAC، VRF Routing، Reporting و License Renewal.
  * کشف و ثبت آسیب‌پذیری‌های جدید **F-90 تا F-96** در فایل [plan/01_AUDIT_FINDINGS.md](file:///d:/Playground/Web-Dash/plan/01_AUDIT_FINDINGS.md).
  * ثبت تحلیل معماری فرانت‌اند و فهرست متغیرهای نیازمند اعتبارسنجی در [plan/NOTES_FROM_AGENT.md](file:///d:/Playground/Web-Dash/plan/NOTES_FROM_AGENT.md).
  * ایجاد برنچ `phase1` و کامیت اولیه.
* **تأییدیه (Verify):** تحلیل و کاتالوگ تمام متغیرهای ورودی کاربر که به دستورات CLI تجهیزات تزریق می‌شوند.

---

### گام ۱.۱ — خروج سکرت‌ها و وضعیت از ایمیج داکر (Step 1.1 Secrets & State out of Image)
* **هدف:** رفع آسیب‌پذیری‌های F-08 و F-92 و جداسازی کامل داده‌های حساس و پایگاه داده از سورس‌کد و ایمیج داکر.
* **اقدامات انجام‌شده:**
  1. معرفی متغیر محیطی `DATA_DIR` با مقدار پیش‌فرض `./data`.
  2. هدایت مسیر ذخیره فایل کاربران (`users.json`) در [auth.py](file:///d:/Playground/Web-Dash/auth.py) به زیرمجموعه `DATA_DIR`.
  3. هدایت کلید سکرت (`.secret_key`) و پوشه آپلودها (`uploads`) در [app.py](file:///d:/Playground/Web-Dash/app.py) به زیرمجموعه `DATA_DIR`.
  4. اعمال اولویت امنیتی برای کلید رمزنگاری نشست Flask:
     * ابتدا مقدار `FLASK_SECRET_KEY` از متغیرهای محیطی.
     * سپس فایل `.secret_key` درون `DATA_DIR`.
     * در غیر این صورت، تولید کلید تصادفی با `secrets.token_hex(32)` و ایجاد فایل با پرمیشن ایمن `0600`.
  5. به‌روزرسانی [.gitignore](file:///d:/Playground/Web-Dash/.gitignore) جهت چشم‌پوشی از `data/`، `users.json`، `.secret_key`، و `*.env` (با حفظ `config.example.env`).
  6. ایجاد فایل [.dockerignore](file:///d:/Playground/Web-Dash/.dockerignore) جهت ممانعت از قرارگیری داده‌ها و سکرت‌ها داخل ایمیج داکر.
  7. به‌روزرسانی [Dockerfile](file:///d:/Playground/Web-Dash/Dockerfile) و [docker-compose.yml](file:///d:/Playground/Web-Dash/docker-compose.yml) و تعریف Named Volume به نام `webdash_data` روی مسیر `/data` به همراه `DATA_DIR=/data`.
  8. نگارش و اجرای تست‌های خودکار در [tests/test_step_1_1_secrets_and_data_dir.py](file:///d:/Playground/Web-Dash/tests/test_step_1_1_secrets_and_data_dir.py).
* **تأییدیه (Verify):**
  * اجرای تست‌های واحد با Pytest: ۴ تست با موفقیت پاس شدند (`4 passed`).
  * بررسی وضعیت گیت (`git status`): هیچ فایل سکرتی ترک نمی‌شود.
