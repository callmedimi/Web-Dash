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

---

### گام ۱.۵ — اعتبارسنجی ورودی‌های مدیریت کاربران (Step 1.5 Validate User Management Input)
* **هدف:** رفع آسیب‌پذیری انتساب دسته‌جمعی نامعتبر (Mass Assignment - F-07)، اعمال لیست سفید (Whitelist) روی فیلدهای به‌روزرسانی کاربر، اعتبارسنجی دقیق نقش‌ها و پرمیشن‌ها، و ممانعت از تنزل درجه یا غیرفعال‌سازی آخرین حساب کاربری `god`.
* **اقدامات انجام‌شده:**
  1. لیست سفید کلیدها در اندپوینت `PUT /admin/users/<username>`:
     * انحصاری کردن فیلدهای قابل تغییر به `{role, display_name, password, is_active}` و فیلتر کردن کلیه کلیدهای ناشناخته و تزریقی.
     * اعتبارسنجی نقش: مقدار `role` فقط می‌تواند یکی از مقادیر مجاز `god`، `admin` یا `user` باشد (در غیر این صورت خطای 400 با کد `VALIDATION_ERROR`).
     * اعتبارسنجی بولین بودن فیلد `is_active`.
  2. مصونیت آخرین کاربر با نقش `god` (Last God Protection):
     * در متد `update_user()` در [auth.py](file:///d:/Playground/Web-Dash/auth.py)، تعداد کاربران فعال با نقش `god` شمارش می‌شود.
     * در صورتی که کاربری تنها `god` فعال سیستم باشد، تنزل نقش آن به `admin/user` یا تغییر `is_active=False` مسدود شده و خطای صریح ۴۰۰/۴۰۳ برگردانده می‌شود.
     * در صورت وجود حداقل یک کاربر `god` فعال دیگر، تنزل رتبه مجاز است.
  3. تغییرناپذیری دیکشنری ورودی کالر (Immutability):
     * جلوگیری از جهش (Mutation) دیکشنری پاس داده شده به `update_user()` با کپی اولیه `dict(updates)`.
  4. اعتبارسنجی سخت‌گیرانه پرمیشن‌ها در `PUT /admin/permissions/<username>`:
     * الزام ارسال دیکشنری `{feature_name: bool}`.
     * بررسی اینکه تمامی فیچرهای ارسالی دقیقاً عضو لیست رسمی `DEFAULT_FEATURES` باشند.
     * بررسی نوع داده بولین برای هر فیچر و رد مقادیر رشته‌ای ("true")، عددی یا لیست.
  5. نگارش تست‌های خودکار در [tests/test_step_1_5_validate_user_management.py](file:///d:/Playground/Web-Dash/tests/test_step_1_5_validate_user_management.py).
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه تست‌های پروژه: ۳۲ تست با موفقیت کامل پاس شدند (`32 passed in 10.92s`).
  * ارسال کلیدهای غیرمجاز در آپدیت کاربر بدون اثر بوده و در دیتابیس ذخیره نمی‌شود.
  * ارسال نقش نامعتبر با خطای 400 رد می‌شود.
  * تنزل یا غیرفعال کردن آخرین ادمین کل با خطای 400 مسدود می‌شود.
  * ارسال پرمیشن نامعتبر یا مقدار غیربولین با خطای 400 رد می‌شود.
  * دیکشنری فراخواننده در حین آپدیت دچار تغییر نمی‌شود.

---

### گام ۱.۶ — اعتبارسنجی ورودی‌ها و حدود مجاز (Step 1.6 Input Validation & Limits - F-09, F-10, F-90)
* **هدف:** رفع آسیب‌پذیری‌های منع سرویس از طریق ارسال پی‌لودهای بسیار حجیم (F-09)، جلوگیری از تزریق دستور به تجهیزات شبکه (CLI Command Injection - F-90)، اعتبارسنجی دقیق و اسکیما‌محور کلیه پارامترهای ارسالی در اندپوینت‌های API و لایه دستورات روترها، و یکپارچه‌سازی فرمت خروجی خطاها مطابق معماری هدف (Target Architecture §4).
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی ماژول مستقل اعتبارسنجی و بهسازی در [validators.py](file:///d:/Playground/Web-Dash/validators.py):
     * تعریف لیست سیاه کاراکترهای خطرناک CLI شامل `\r`، `\n`، `;`، `|`، `&`، `$`، `` ` ``، `<`، `>`، `\`، `!`، `"` و `'`.
     * `sanitize_cli_arg`: بررسی نوع رشته، مسدودسازی کاراکترهای مخرب و جلوگیری از فضای خالی (Whitespace) در میان پارامترهای مستقیم CLI.
     * `validate_router_name`: بررسی نام روتر تا حداکثر ۶۴ کاراکتر با الگوی `^[A-Za-z0-9._-]{1,64}$`.
     * `validate_host_or_ip`: اعتبارسنجی آدرس IPv4/IPv6 با ماژول استاندارد `ipaddress` یا انطباق با استاندارد RFC 1123 Hostname بدون بخش‌های ناقص یا کاراکترهای ممنوعه.
     * `validate_target_ip`: اعتبارسنجی IP مقصد و پیشوندهای شبکه (CIDR) و تفکیک امن بخش IP از Mask.
     * `validate_interface_name`: اعتبارسنجی ساختار اینترفیس‌های تجهیزات هواوی (مانند `GE0/0/1`، `Eth-Trunk1.100`، `LoopBack0`، `Vlanif100`، `Serial1/0/0:0`) و ممانعت قطعی از تزریق دستوراتی مثل `GE0/0/1\nundo shutdown`.
     * `validate_vrf_name`: اعتبارسنجی نام VRF / VPN-Instance (حداکثر ۳۱ کاراکتر امن).
     * `validate_province`: اعتبارسنجی کد استان (۲ تا ۶ حرف بزرگ انگلیسی ASCII).
     * `validate_age`: اعتبارسنجی سن آلارم‌ها (مقدار عددی ۱ تا ۳۶۵۰ و واحد زمانی منحصراً `hours` یا `days`).
     * `validate_timeout`: اعتبارسنجی مهلت‌های زمانی SSH و دستورات (۱ تا ۳۰۰ ثانیه).
     * `validate_routers_list`: اعتبارسنجی لیست روترها (حداقل ۱ و حداکثر ۲۰۰۰ عضو) و پاکسازی و اعتبارسنجی همزمان تک‌تک آدرس‌ها و نام‌ها.
  2. محدودسازی حداکثر حجم بدنه درخواست (Payload Size Limit):
     * تنظیم `MAX_CONTENT_LENGTH = 10 MB` (قابلیت تغییر با متغیر محیطی `MAX_CONTENT_LENGTH_MB`).
     * پیاده‌سازی Error Handler خطای 413 (`@app.errorhandler(413)`) جهت بازگرداندن پاسخ ساختاریافته استاندارد `PAYLOAD_TOO_LARGE`.
     * عدم بلعیده شدن استثنای `RequestEntityTooLarge` در متد کمکی `get_json_payload()`.
  3. تبدیل خطاهای ارزیابی و ورودی نامعتبر به خطای استاندارد 400:
     * ثبت هندلرهای سراسری خطای `ValueError` و `KeyError` در [app.py](file:///d:/Playground/Web-Dash/app.py) جهت تولید پاسخ با فرمت معماری هدف:
       `{"error": {"code": "VALIDATION_ERROR", "message": "...", "fields": {}}, "code": "VALIDATION_ERROR", "message": "..."}`.
  4. اعمال اعتبارسنجی در تمامی اندپوینت‌های پردازشی:
     * `/run-manual` و `/run-bulk`: کنترل سقف ۲۰۰۰ روتر و اعتبارسنجی تک‌تک نام‌ها و IPها.
     * `/run-report` و `/run-full-report`: اعتبارسنجی روترها، کد استان و پارامترهای `age_value` و `age_unit`.
     * `/run-license-check` و `/start-renewal`: اعتبارسنجی لیست روترهای منتخب.
     * `/check-vrf-routing`، `/check-bgp-route` و `/show-originator-interfaces`: اعتبارسنجی دقیق `target_ip`، `originator_ip`، `vrf` و تایم‌اوت‌ها قبل از ساخت رشته دستور CLI.
     * `/search-zabbix-ip` و `/ptp/start-troubleshoot`: اعتبارسنجی ورودی IP و تارگت ترابل‌شوتینگ.
  5. حفاظت لایه تجهیزات شبکه:
     * در [check_vrf_routing.py](file:///d:/Playground/Web-Dash/check_vrf_routing.py): اعتبارسنجی `clean_name = validate_interface_name(interface_name)`، `validate_target_ip(target_ip)` و `validate_vrf_name(vrf)` قبل از ارسال هرگونه دستور `display` به سوئیچ/روتر.
     * در [auto_clear_noconf.py](file:///d:/Playground/Web-Dash/auto_clear_noconf.py): اعتبارسنجی اینترفیس‌های استخراج شده از شرح آلارم‌ها پیش از اعمال دستورات `interface {iface}` و `shutdown`.
  6. نگارش تست‌های خودکار و آزمون‌های نفوذ/فازینگ در [tests/test_step_1_6_input_validation_and_limits.py](file:///d:/Playground/Web-Dash/tests/test_step_1_6_input_validation_and_limits.py).
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه تست‌های پروژه: ۴۷ تست با موفقیت کامل پاس شدند (`47 passed in 16.08s`).
  * ارسال پی‌لود با `"age_value": "abc"` با خطای 400 `VALIDATION_ERROR` متوقف می‌شود.
  * ارسال اینترفیس‌های آلوده به کاراکترهای تزریقی با خطای 400 متوقف می‌شود.
  * ارسال لیست روترهای بالای ۲۰۰۰ عدد با خطای 400 رد می‌شود.
  * ارسال بدنه بزرگ‌تر از سقف مجاز بلافاصله با خطای 413 `PAYLOAD_TOO_LARGE` متوقف می‌شود.
  * ساختار کلیه خطاهای اعتبارسنجی کاملاً منطبق با Target Architecture §4 است.
