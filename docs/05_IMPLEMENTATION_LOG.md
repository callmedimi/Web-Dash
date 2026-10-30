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

---

### گام ۱.۲ — حذف حساب کاربری پیش‌فرض god/god و الزام سیاست کلمه عبور (Step 1.2 Kill Default god/god Account)
* **هدف:** رفع آسیب‌پذیری بحرانی F-01 و ایمن‌سازی فرآیند بوت‌استرپ و سیاست‌های کلمه عبور.
* **اقدامات انجام‌شده:**
  1. حذف کامل کاربر پیش‌فرض هاردکدشده سازنده (`Dimi/god`).
  2. پیاده‌سازی سازوکار بوت‌استرپ در اجرای اول:
     * در صورت خالی بودن دیتابیس کاربران، متغیرهای `INITIAL_ADMIN_USER` و `INITIAL_ADMIN_PASSWORD` از متغیرهای محیطی خوانده می‌شوند.
     * در صورت عدم تنظیم، کاربر `admin` با دسترسی `god` و یک کلمه عبور ۲۰ کاراکتری تصادفی و پیچیده تولید شده و تنها یک بار در خروجی استاندارد کنسول چاپ می‌شود و فلگ `must_change_password=True` برای آن تنظیم می‌گردد.
  3. تدوین سیاست سخت‌گیرانه کلمه عبور در `validate_password()`:
     * حداقل ۱۲ کاراکتر.
     * عدم برابری یا شامل بودن نام کاربری.
     * رد کلمات عبور ضعیف و شناخته‌شده (Blocklist).
  4. اعمال این سیاست در توابع `create_user()` و `update_user()`.
  5. اضافه شدن روت `POST /change-password` برای تغییر امن کلمه عبور کاربران.
  6. اعمال فیلتر سراسری `@app.before_request`: در صورت فعال بودن فلگ `must_change_password`، کلیه اندپوینت‌ها (به استثنای `/me`، `/logout` و `/change-password`) با خطای 403 و کد `PASSWORD_CHANGE_REQUIRED` مسدود می‌شوند.
  7. نگارش تست‌های جامع در [tests/test_step_1_2_auth_bootstrap_and_policy.py](file:///d:/Playground/Web-Dash/tests/test_step_1_2_auth_bootstrap_and_policy.py).
* **تأییدیه (Verify):**
  * اجرای Pytest روی تمام تست‌ها: ۹ تست با موفقیت پاس شدند (`9 passed`).
  * ورود با `Dimi/god` رد می‌شود (خطای 401).
  * ایجاد کاربر با پسورد ضعیف یا کوتاه رد می‌شود (خطای 400).
  * کاربر موقت تا زمان تغییر رمز به سایر اندپوینت‌های سیستم دسترسی ندارد (خطای 403 با کد `PASSWORD_CHANGE_REQUIRED`).

---

### گام ۱.۳ — ایمن‌سازی نشست‌ها و محافظت در برابر CSRF (Step 1.3 Session & CSRF Hardening)
* **هدف:** رفع آسیب‌پذیری‌های F-02, F-03, F-91 و محافظت از کلیه متدهای تغییردهنده با هدر ضد جعل CSRF، انقضای نشست‌های غیرفعال، و بی‌اعتبارسازی سشن در صورت تغییر رمز/دسترسی یا غیرفعال شدن کاربر.
* **اقدامات انجام‌شده:**
  1. پیکربندی سخت‌گیرانه سشن‌های فلسک:
     * `SESSION_COOKIE_HTTPONLY = True` (ممانعت از سرقت سشن از طریق XSS).
     * `SESSION_COOKIE_SAMESITE = "Lax"` (محافظت در برابر حملات جعل درخواست فراسایتی).
     * `SESSION_COOKIE_SECURE` کنترل‌شده از متغیر محیطی `COOKIE_SECURE` (پیش‌فرض False برای محیط Lab، مقدار True در تولید).
     * طول عمر دائمی نشست برابر ۸ ساعت (`PERMANENT_SESSION_LIFETIME = 8h`).
     * کنترل Idle Timeout به مدت ۳۰ دقیقه با ذخیره `last_seen`.
  2. محافظت ضد جعل درخواست فراسایتی (CSRF Protection):
     * در ورود موفق (`POST /login`) و در روت وضعیت (`GET /me`)، یک توکن تصادفی و رمزنگاری‌شده با `secrets.token_hex(32)` در سشن ثبت و در پاسخ JSON به کاربر برگردانده می‌شود.
     * در لایه `@app.before_request`، کلیه درخواست‌های تغییردهنده (`POST`, `PUT`, `DELETE`, `PATCH`) به جز خود لاگین، مستلزم ارسال هدر `X-CSRF-Token` برابر با توکن سشن هستند که با مقایسه در زمان ثابت (`secrets.compare_digest`) ارزیابی می‌شود و در صورت خطا کد 403 با `CSRF_ERROR` بازمی‌گردد.
  3. بازخوانی بلادرنگ مشخصات کاربر و ابطال نشست (Session Revocation):
     * در هر درخواست، وضعیت کاربر مستقیماً با متد جدید `get_user()` بازخوانی می‌شود.
     * در صورت حذف کاربر: خطای 401 با کد `USER_NOT_FOUND`.
     * در صورت غیرفعال شدن کاربر (`is_active = False`): خطای 401 با کد `USER_DISABLED`.
     * در صورت تغییر کلمه عبور، نقش یا سطح دسترسی: متغیر `token_version` در دیتابیس کاربران یک واحد افزایش می‌یابد و سشن‌های قبلی بلافاصله با خطای 401 و کد `SESSION_INVALIDATED` خاتمه می‌یابند.
     * در صورت سپری شدن بیش از ۳۰ دقیقه از آخرین درخواست: سشن با خطای 401 و کد `SESSION_EXPIRED` منقضی می‌شود.
  4. اعمال تابع اعتبارسنجی سراسری `get_json_payload()`:
     * جایگزینی تمام فراخوانی‌های ناایمن `request.get_json(force=True)` در سرتاسر `app.py`.
     * الزام استفاده از `Content-Type: application/json` و بازگرداندن خطای استاندارد 415 با کد `UNSUPPORTED_MEDIA_TYPE` در صورت ارسال داده‌های متنی یا فرم نامعتبر.
     * بازگرداندن خطای 400 با کد `INVALID_JSON` در صورت ارسال JSON مخدوش.
  5. رفع نقص امنیتی F-91:
     * افزودن دکوراتورهای `@login_required` و `@permission_required("ptp_troubleshoot")` به اندپوینت‌های استریم و اطلاعات نشست PTP (`/ptp/stream/<sid>` و `/ptp/session/<sid>`).
  6. هماهنگ‌سازی فرانت‌اند در [templates/index.html](file:///d:/Playground/Web-Dash/templates/index.html):
     * پیاده‌سازی اینترسپتور سراسری روی `window.fetch` در ابتدای اسکریپت اصلی فرانت‌اند.
     * ارسال خودکار هدر `X-CSRF-Token` در کلیه درخواست‌های متد `POST/PUT/DELETE/PATCH`.
     * ذخیره‌سازی توکن هنگام لاگین یا فراخوانی `/me`.
     * هدایت خودکار کاربر به صفحه ورود در صورت دریافت خطای 401 ناشی از ابطال نشست.
  7. نگارش مجموعه تست‌های جامع در [tests/test_step_1_3_session_csrf_hardening.py](file:///d:/Playground/Web-Dash/tests/test_step_1_3_session_csrf_hardening.py).
* **تأییدیه (Verify):**
  * اجرای Pytest روی کل تست‌های پروژه: ۲۱ تست با موفقیت کامل پاس شدند (`21 passed in 5.81s`).
  * ارسال درخواست POST بدون هدر CSRF با خطای 403 مسدود می‌شود.
  * ارسال داده با Content-Type غیرجیسون با خطای 415 رد می‌شود.
  * ارسال جیسون ناقص با خطای 400 رد می‌شود.
  * حذف، غیرفعال‌سازی یا تغییر پسورد کاربر در یک مرورگر، فوراً کلیه سشن‌های فعال او در سایر کلاینت‌ها را به 401 تبدیل می‌کند.
  * دسترسی بدون احراز هویت به اندپوینت‌های PTP بلافاصله 401 بازمی‌گرداند.

---

### گام ۱.۴ — محدودسازی تلاش‌های ورود ناموفق و ثبت ردپای حسابرسی (Step 1.4 Login Throttling & Audit Log)
* **هدف:** رفع آسیب‌پذیری بحرانی F-04، جلوگیری از حملات Brute-Force و دیکشنری روی `/login`، مقابله با حملات Timing Attack در تشخیص نام‌های کاربری موجود، و ایجاد لاگ وقایع امنیتی غیرقابل دستکاری (`audit.log`).
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی مکانیزم Throttling و Rate Limiting ورود در [auth.py](file:///d:/Playground/Web-Dash/auth.py):
     * ردیابی تلاش‌های ناموفق بر اساس کلید ترکیبی `(username, client_ip)`.
     * در صورت ثبت ۵ تلاش ناموفق متوالی، حساب/آی‌پی به مدت ۱۵ دقیقه قفل موقت می‌شود (`LOCKOUT_DURATION_SECONDS = 15 * 60`).
     * هرگونه تلاش ورود مجدد (حتی با پسورد درست) در بازه قفل، بلافاصله خطای 429 با کد `TOO_MANY_REQUESTS` برمی‌گرداند.
     * در صورت ورود موفق، شمارنده تلاش‌های ناموفق مربوطه ریست می‌شود.
  2. محافظت در برابر Timing Attack (تشخیص وجود نام کاربری بر اساس تفاوت زمانی):
     * در صورت عدم وجود نام کاربری در دیتابیس یا غیرفعال بودن آن، یک هش کاذب (`DUMMY_PASSWORD_HASH`) با الگوریتم Scrypt بررسی می‌شود تا زمان پاسخگویی برای کاربران موجود و ناموجود یکسان باشد.
  3. ماژول مستقل لاگ حسابرسی پیوست‌افزا در [audit.py](file:///d:/Playground/Web-Dash/audit.py):
     * ذخیره‌سازی لاگ‌ها به صورت خطوط JSON (JSON Lines) در مسیر `DATA_DIR/audit.log`.
     * ایمنی کامل در برابر درج اطلاعات حساس (Sanitization): تمام کلیدهای حساس اعم از `password`، `secret`، `token`، `creds` و غیره به صورت خودکار با مقدار `[REDACTED]` ماسک می‌شوند و هیچ رمز عبوری در فایل لاگ ثبت نمی‌گردد.
     * ثبت بلادرنگ وقایع امنیتی: `login_success`، `login_failed`، `login_blocked_rate_limit`، `account_locked`، `logout`، `password_changed`، `user_created`، `user_updated`، `user_deleted`، `permissions_updated` و کلیه جاب‌های اجرایی (`job_started`).
  4. افزودن اندپوینت نظارتی `GET /admin/audit-log` ویژه ادمین‌ها برای مشاهده آخرین رکوردهای حسابرسی بدون دسترسی به دیسک سرور.
  5. نگارش تست‌های خودکار در [tests/test_step_1_4_login_throttling_and_audit.py](file:///d:/Playground/Web-Dash/tests/test_step_1_4_login_throttling_and_audit.py).
* **تأییدیه (Verify):**
  * اجرای Pytest روی تمامی تست‌های پروژه: ۲۶ تست با موفقیت کامل پاس شدند (`26 passed in 8.91s`).
  * پنجمین تلاش ناموفق حساب را قفل کرده و ششمین لاگین خطای 429 برمی‌گرداند.
  * بررسی فایل `audit.log` تأیید کرد هیچ ردی از رشته‌های کلمه عبور وجود ندارد.
  * فایل `audit.log` در دایرکتوری پایدار `DATA_DIR` تولید و وقایع را به درستی ثبت می‌کند.
