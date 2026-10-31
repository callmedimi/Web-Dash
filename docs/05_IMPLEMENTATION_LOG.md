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

---

### گام ۱.۷ — انتقال مقادیر ثابت زیرساخت به فایل پیکربندی (Step 1.7 Move Hardcoded Infra Constants to Config - F-12)
* **هدف:** حذف کامل آدرس‌های IP و نام‌های هاردکدشده تجهیزات شبکه از کدهای پایتون (`HARDCODED_ROUTER_NAME`، `HARDCODED_ROUTER_IP`، `HARDCODED_RR_IP` و `TARGET_NE_PREFIXES`) و انتقال آنها به ماژول متمرکز تنظیمات [settings.py](file:///d:/Playground/Web-Dash/settings.py) با پشتیبانی همزمان از متغیرهای محیطی و فایل `config.ini`.
* **اقدامات انجام‌شده:**
  1. طراحی و ساخت ماژول متمرکز [settings.py](file:///d:/Playground/Web-Dash/settings.py):
     * اولویت‌بندی لایه‌ای بارگذاری: ابتدا متغیرهای محیطی سیستم، سپس فایل پیکربندی `config.ini` و در نهایت مسیرهای کاندید.
     * اعتبارسنجی مقادیر زیرساختی هنگام راه‌اندازی با ماژول `validators` (اطمینان از ساختار معتبر نام روتر و آدرس‌های IP/Host).
     * شکست سریع و ایمن در شروع به کار (Fail-Fast): در صورت مفقود بودن هر یک از مقادیر حیاتی (`VRF_ROUTER_NAME`، `VRF_ROUTER_IP`، `VRF_RR_IP`)، استثنای صریح `RuntimeError` با پیام راهنمای شفاف بالا می‌آید.
     * حفظ کامل سازگاری عقبرو (Backward Compatibility) با تعریف نام‌های مستعار قدیمی (`HARDCODED_ROUTER_*`).
  2. توسعه فایل‌های نمونه و پیکربندی پیش‌فرض:
     * اضافه شدن بخش‌های `[vrf]` و `[site_arp]` به [config.example.ini](file:///d:/Playground/Web-Dash/config.example.ini) و [config.example.env](file:///d:/Playground/Web-Dash/config.example.env).
     * ایجاد فایل پیش‌فرض [config.ini](file:///d:/Playground/Web-Dash/config.ini) در ریشه مخزن.
  3. بازنویسی کدهای مصرف‌کننده:
     * حذف ثابت‌های هاردکدشده در [check_vrf_routing.py](file:///d:/Playground/Web-Dash/check_vrf_routing.py) و جایگزینی با ایمپورت از `settings.py`.
     * اتصال پیشوندهای هدف در [site_arp_service.py](file:///d:/Playground/Web-Dash/site_arp_service.py) به مقدار پیکربندی‌شده `TARGET_NE_PREFIXES`.
     * پاکسازی نمونه‌های کامنتی و داک‌استرینگ حاوی IP نقطه‌دار در کد منبع.
  4. نگارش تست‌های خودکار در [tests/test_step_1_7_settings_and_config.py](file:///d:/Playground/Web-Dash/tests/test_step_1_7_settings_and_config.py):
     * تست بارگذاری صحیح از فایل `config.ini`.
     * تست تقدم متغیرهای محیطی بر مقادیر فایل `config.ini`.
     * تست بالا آمدن `RuntimeError` در صورت نبودن تنظیمات حیاتی.
     * تست اعتبارسنجی و رد مقادیر IP نامعتبر در تنظیمات.
     * تست سراسری و خودکار گریپ روی کلیه فایل‌های پایتون مخزن (خارج از پوشه tests) جهت تأیید عدم وجود حتی یک IP زیرساختی هاردکدشده.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه تست‌های پروژه: ۵۲ تست با موفقیت کامل پاس شدند (`52 passed in 12.53s`).
  * اجرای آزمون گریپ تأیید کرد هیچ IP نقطه‌داری در کدهای برنامه وجود ندارد (`SUCCESS: No hardcoded dotted IPs found in any non-test python files`).

---

### گام ۱.۸ — کلید قطع اضطراری و حالت فقط‌خواندنی (Step 1.8 Safety Net: Kill-Switch & Read-Only Mode)
* **هدف:** ایجاد سازوکار حفاظتی سطح پلتفرم جهت جلوگیری از ارسال ناخواسته دستورات تغییر پیکربندی به تجهیزات زنده شبکه با فعال‌سازی متغیر محیطی `READ_ONLY_MODE=true` (یا تعریف در `config.ini`) و نمایش بنر هشدار دائمی در رابط کاربری ادمین.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی متد `is_read_only_mode()` در [settings.py](file:///d:/Playground/Web-Dash/settings.py):
     * بررسی متغیرهای محیطی `READ_ONLY_MODE` (مقادیر مجاز `true`، `1`، `yes`، `on`).
     * بررسی پشتیبان از فایل `config.ini` در بخش‌های `[app]` یا `[security]`.
     * مقدار پیش‌فرض: `False`.
  2. پیاده‌سازی دکوراتور محافظتی `@read_only_blocked` در [app.py](file:///d:/Playground/Web-Dash/app.py):
     * در صورت فعال بودن وضعیت فقط‌خواندنی، درخواست‌های ارسالی به روت‌های تغییردهنده وضعیت تجهیزات بلافاصله با خطای 403 و فرمت ساختاریافته معماری هدف متوقف می‌شوند:
       `{"error": {"code": "READ_ONLY", "message": "System is running in READ-ONLY mode. Device-modifying operations are disabled.", "fields": {}}, "code": "READ_ONLY", "message": "..."}`.
  3. اعمال محدودیت روی کلیه روت‌های ارائه‌دهنده دستورات پیکربندی (Configuring Routes):
     * `/run-manual` (پاکسازی دستی آلارم و خاموش‌سازی پورت).
     * `/run-bulk` (پاکسازی گروهی آلارم‌ها و shutdown اینترفیس‌ها بر مبنای CSV).
     * `/start-renewal` (عملیات اعمال و تمدید لایسنس تجهیزات و رفتن به `system-view`).
     * `/confirm-renewal/<sid>` (تأیید اقدام تمدید لایسنس).
  4. حفظ عملکرد کامل بخش‌های تشخیصی و تحلیلی:
     * اندپوینت‌های فقط‌خواندنی نظیر `/run-report`، `/run-full-report`، `/check-vrf-routing`، `/check-bgp-route`، `/run-license-check` و جستجوهای زبیکس بدون وقفه به کار خود ادامه می‌دهند.
  5. بازتاب وضعیت در رابط کاربری (Frontend & Admin UI):
     * ارسال فیلد `"read_only": is_read_only_mode()` در پاسخ اندپوینت‌های `/login` و `/me`.
     * ایجاد بنر اخطار نارنجی رنگ با هویت بصری مشخص در [templates/index.html](file:///d:/Playground/Web-Dash/templates/index.html) با پیام:
       `READ-ONLY MODE ACTIVE: Device configuration changes and alarm clearing are disabled`.
     * کنترل پویای نمایش بنر در متد `showApp()` پس از احراز هویت.
  6. نگارش تست‌های خودکار در [tests/test_step_1_8_read_only_mode.py](file:///d:/Playground/Web-Dash/tests/test_step_1_8_read_only_mode.py):
     * تست بررسی پیش‌فرض غیرفعال بودن حالت فقط‌خواندنی.
     * تست فعال‌سازی با مقادیر مختلف متغیر محیطی.
     * تست دریافت وضعیت فقط‌خواندنی در اندپوینت `/me`.
     * تست رد کلیه درخواست‌های تغییردهنده (`/run-manual`، `/run-bulk`، `/start-renewal`، `/confirm-renewal`) با خطای 403 `READ_ONLY`.
     * تست ادامه کار صحیح اندپوینت‌های گزارش‌گیری و بررسی تشخیصی لایسنس در حالت فعال بودن Kill-Switch.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه تست‌های پروژه: ۵۷ تست با موفقیت کامل پاس شدند (`57 passed in 12.98s`).
  * با فعال بودن فلگ `READ_ONLY_MODE=true`، روت‌های `/run-manual` و `/run-bulk` اجرا را رد کرده و گزارش‌گیری‌ها کماکان به درستی کار می‌کنند.

---

### گام ۱.۹ — آزمون رگرسیون فاز ۱ و تأییدیه دود (Step 1.9 Phase 1 Regression Pass & Acceptance)
* **هدف:** اجرای کامل چک‌لیست آزمون‌های دود (Smoke Checklist مطابق با `11_TESTING_ACCEPTANCE.md` §2)، اطمینان از سلامت همه‌جانبه سیستم، پیاده‌سازی پروب‌های نظارتی `/healthz` و `/readyz`، و آماده‌سازی شاخه `phase1` جهت ادغام به شاخه اصلی (`main`).
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی پروب‌های لایونس و آمادگی کانتینر در [app.py](file:///d:/Playground/Web-Dash/app.py):
     * `GET /healthz`: بررسی زنده بودن پروسه وب (Liveness Probe) و پاسخ 200 با `{"status": "ok", "app": "Web-Dash"}`.
     * `GET /readyz`: بررسی آمادگی سرویس (Readiness Probe)، اعتبارسنجی قابلیت نوشتن روی `DATA_DIR`، و بازگرداندن وضعیت سیستم و فلگ `read_only`.
  2. اعتبارسنجی جامع چک‌لیست دود (Smoke Checklist):
     * [x] راه‌اندازی موفق در دایرکتوری داده کاملاً خالی و تولید خودکار کاربر روت `admin` با رمز تصادفی و الزام به تغییر.
     * [x] پروب‌های سلامت و آمادگی `/healthz` و `/readyz` با وضعیت 200 OK.
     * [x] ایمپورت فایل‌های CSV نودها با اعتبارسنجی سخت‌گیرانه مقادیر.
     * [x] عملکرد کلید قطع اضطراری (`READ_ONLY_MODE=true`): مسدودسازی موفق عملیات تغییر کانفیگ و مجاز بودن گزارش‌ها.
     * [x] گزارش‌گیری Down-Links و حفظ ترتیب و نام ستون‌های خروجی CSV مطابق `FIELD_NAMES`.
     * [x] حذف ۱۰۰٪ آدرس‌های IP زیرساختی هاردکدشده از کل کدهای برنامه.
     * [x] آزمون ضد بروت‌فورس: قفل شدن حساب پس از ۵ تلاش و ثبت وقایع بدون کلمات عبور در فایل `audit.log`.
     * [x] آزمون هاردنینگ نشست‌ها و بررسی توکن ضد CSRF در تمامی متدهای تغییردهنده.
     * [x] اعتبارسنجی فرمت ورودی‌ها و جلوگیری از تزریق دستور به CLI تجهیزات.
  3. به‌روزرسانی یادداشت‌های تجمیعی در [plan/NOTES_FROM_AGENT.md](file:///d:/Playground/Web-Dash/plan/NOTES_FROM_AGENT.md) و ثبت وضعیت تیک‌های چک‌لیست.
  4. نگارش آزمون‌های انتها-به-انتها در [tests/test_step_1_9_phase1_regression.py](file:///d:/Playground/Web-Dash/tests/test_step_1_9_phase1_regression.py).
* **تأییدیه (Verify):**
  * اجرای سراسری Pytest روی تمامی تست‌های فاز ۱: مجموعاً ۵۹ تست بدون هیچ هشدار یا خطایی پاس شدند (`59 passed in 13.53s`).
  * شاخه `phase1` دارای پوشش آزمون کامل، پایداری امنیتی و قابلیت ادغام سبز (Green Merge) می‌باشد.

---

### گام ۲.۱ — اسکلت پکیج backend/app، دیتابیس رابطه‌ای PostgreSQL، آرشیو ARP/MAC و مهاجرت داده‌ها (Step 2.1 Package Skeleton, Config, Relational DB & Schema - F-06, F-15)
* **هدف:** مهاجرت از معماری تک‌فایلی به اسکلت ماژولار `backend/app/`، اتصال تنظیمات متمرکز با `pydantic-settings`، پیاده‌سازی لایه دسترسی داده‌ها بر پایه **PostgreSQL** با استفاده از **SQLAlchemy 2.0** و **Alembic** (با حفظ پشتیبانی آسان از SQLite WAL در حالت محلی)، ایجاد جداول اختصاصی وضعیت فعال و آرشیو تاریخی ARP/MAC، و پیاده‌سازی اسکریپت و ماژول خودکار مهاجرت داده‌ها (ETL) از فایل‌های JSON و CSV.
* **اقدامات انجام‌شده:**
  1. ساخت ساختار پوشه‌ای معماری مقصد مطابق [plan/02_TARGET_ARCHITECTURE.md](file:///d:/Playground/Web-Dash/plan/02_TARGET_ARCHITECTURE.md):
     * [backend/app/config.py](file:///d:/Playground/Web-Dash/backend/app/config.py): تنظیمات با پیشوند `WEBDASH_`، خواندن `DATABASE_URL`، مسیر داده‌ها و استراتژی اتصال.
     * [backend/app/db/base.py](file:///d:/Playground/Web-Dash/backend/app/db/base.py) و [backend/app/db/session.py](file:///d:/Playground/Web-Dash/backend/app/db/session.py): موتور دیتابیس، پولینگ اتصالات، پشتیبانی خودکار از دستورات `PRAGMA` در SQLite و استخر اتصالات امن در PostgreSQL.
     * [backend/app/extensions.py](file:///d:/Playground/Web-Dash/backend/app/extensions.py): راه‌انداز سشن‌های Scoped و توابع `init_db` و `get_db_session`.
  2. طراحی و پیاده‌سازی ۱۹ جدول در مدل‌های داده [backend/app/models/](file:///d:/Playground/Web-Dash/backend/app/models/):
     * **مدل‌های اصلی سامانه (Target Architecture §3):**
       * `User` و `Permission`: تفکیک کاربران، هش رمزها، وضعیت قفل و فیلدهای دسترسی مجزا به جای ساختار غیرنرمالایز قبلی.
       * `Device`, `Credential`, `DeviceLock`: مدیریت مشخصات روترها، نگهداری امن کلیدها/پسوردها، و قفل همزمانی توزیع‌شده بر روی روترها (`device_locks`).
       * `Job`, `JobTask`, `JobEvent`: صف کارهای ناهمگام، ثبت رویدادهای زنده برای استریم SSE و تفکیک جاب‌ها و وظایف روترها.
       * `AuditLog`: جدول ثبت ممیزی بدون امکان دستکاری با نگهداری جزییات JSONB.
       * `ConfigSnapshot`, `ChangeRequest`, `Event`, `Schedule`: مدیریت کانفیگ، درخواست‌های تغییر، رویدادهای زبیکس و زمان‌بندی جاب‌ها.
     * **مدل‌های اختصاصی و بهینه‌سازی‌شده برای دیتای حجیم شبکه:**
       * `ArpMacRecord` (`arp_mac_records`): جدول ذخیره بیش از ۲۰,۰۰۰ رکورد زنده جدول ARP/MAC با ایندکس‌های ترکیبی B-Tree روی `(arp_ip, arp_mac)` و `(ne_name)`.
       * `ArpMacSnapshot` و `ArpMacHistory`: ایجاد ساختار نگهداری آرشیو تاریخی اسکن‌های کالکتور ادمین. هر اسکن با شناسه مجزا و متادیتا ذخیره شده و امکان دانلود CSV، بازیابی وضعیت گذشته و مشاهده تایم‌لاین تغییر اینترفیس هر IP/MAC را فراهم می‌کند.
       * `SiteInventory` (`sites_inventory`): ساختار داده تمیز متناظر با فایل `unified_sites.csv` با ایندکس روی `site_code` و `ip`.
       * `ZabbixInventoryCache` (`zabbix_inventory_cache`): کش داده‌های مانیتورینگ زبیکس با ستون‌های `JSONB` برای نگهداری و جستجوی بسیار سریع بیش از ۵۰۰ متریک و اینترفیس به ازای هر دیوایس.
       * `LicenseRenewalReport` (`license_renewal_reports`): جدول تاریخچه گزارشات تمدید لایسنس.
  3. پیکربندی سیستم مهاجرت اسکیما (Alembic Migrations):
     * تنظیم [backend/migrations/env.py](file:///d:/Playground/Web-Dash/backend/migrations/env.py) متصل به تنظیمات و متادیتای مدل‌ها.
     * تولید نخستین مایگریشن خودکار در [backend/migrations/versions/d3a52d1724ac_initial_schema.py](file:///d:/Playground/Web-Dash/backend/migrations/versions/d3a52d1724ac_initial_schema.py) و اعمال موفق بر پایگاه داده با دستور `alembic upgrade head`.
  4. پیاده‌سازی خط‌لوله انتقال داده‌ها (Data Migration ETL):
     * ایجاد ماژول مستقل و بدون خطا [backend/app/db/migrate_files.py](file:///d:/Playground/Web-Dash/backend/app/db/migrate_files.py).
     * شناسایی، پارس و انتقال خودکار اطلاعات از فایل‌های `users.json`، `arp_mac.csv`، `unified_sites.csv`، `zabbix_router_db.json` و `license_renewals.json`.
     * تضمین خاصیت Idempotency (تکرارپذیری بدون ایجاد رکوردهای تکراری در اجرای مجدد).
  5. اتصال یکپارچه با سامانه فعلی:
     * فکتوری `create_app()` در [backend/app/__init__.py](file:///d:/Playground/Web-Dash/backend/app/__init__.py) تنظیم شد و در [app.py](file:///d:/Playground/Web-Dash/app.py) مورد استفاده قرار گرفت.
     * پروب‌های `/healthz` و `/readyz` با بررسی زنده بودن موتور دیتابیس ارتقا یافتند.
     * وابستگی‌های مدرن (`SQLAlchemy`, `alembic`, `pydantic-settings`, `psycopg[binary]`) به [requirements.txt](file:///d:/Playground/Web-Dash/requirements.txt) افزوده شدند.
  6. نگارش آزمون‌های اختصاصی در [tests/test_step_2_1_db_models_and_migration.py](file:///d:/Playground/Web-Dash/tests/test_step_2_1_db_models_and_migration.py):
     * آزمون چرخه حیات مدل‌های کاربر، سطوح دسترسی، جاب‌ها و تسک‌ها.
     * آزمون مدل‌های آرشیو و اسنپ‌شات‌های تاریخی ARP/MAC.
     * آزمون شبیه‌سازی مهاجرت کامل از فایل‌های تستی و تکرارپذیری بدون خطای مایگریشن.
     * آزمون پروب‌های سلامت و وضعیت دیتابیس.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه ۶۵ تست پروژه با موفقیت ۱۰۰٪ همراه بود (`65 passed in 13.75s`).
  * کلیه قابلیت‌های قبلی بدون هیچ‌گونه شکست یا پس‌رفتی به کار خود ادامه می‌دهند.

---

### گام ۲.۲ — موتور پردازش مرکزی جاب‌ها، استخر ورکرها و زمان‌بند کرون (Step 2.2 Central Job Engine, Worker Pool & Cron Scheduler - F-15, F-17)
* **هدف:** پیاده‌سازی قلب تپنده پلتفرم اتوماسیون شامل موتور صف‌بندی ناهمگام وظایف در پایگاه داده، استخر نخ‌های کارگری (`MAX_SSH_WORKERS`)، انحصار قفل دستگاه‌ها (`device_locks`)، صف‌بندی عادلانه (Fair Scheduling)، توکن لغو آنی جاب‌ها، گذرگاه رویدادها جهت استریم زنده SSE، ریکاوری خودکار هنگام استارت‌آپ سرور، و موتور زمان‌بندی وظایف دوره‌ای (Cron Scheduler) با استفاده از `pycron`.
* **اقدامات انجام‌شده:**
  1. ساخت پکیج جامع [backend/app/jobs/](file:///d:/Playground/Web-Dash/backend/app/jobs/):
     * [backend/app/jobs/locks.py](file:///d:/Playground/Web-Dash/backend/app/jobs/locks.py):
       * پیاده‌سازی قفل انحصاری روترها بر روی جدول `device_locks` با مکانیزم Heartbeat.
       * جلوگیری قطعی از اجرای همزمان دو دستور یا تسک کانفیگ روی یک روتر واحد.
       * بازیابی خودکار قفل‌های مرده (Stale Locks با عمر بیش از ۱۰ دقیقه بدون ضربان).
     * [backend/app/jobs/events.py](file:///d:/Playground/Web-Dash/backend/app/jobs/events.py):
       * پیاده‌سازی کلاس `JobEventBroadcaster` به عنوان باس رویدادها.
       * ذخیره پایدار رویدادها در جدول `job_events` همراه با شناسه افزایشی (`BigInt`) و بازپخش آنی روی صف‌های مشترکین (SSE Replay Source).
     * [backend/app/jobs/cancel.py](file:///d:/Playground/Web-Dash/backend/app/jobs/cancel.py):
       * پیاده‌سازی متد `request_job_cancellation`.
       * تغییر وضعیت جاب به `cancelling`، لغو بلادرنگ کلیه وظایف در صف (`queued` -> `cancelled`)، و توقف ایمن تسک‌های در حال اجرا در نخستین بازرسی توکن (`ctx.cancelled()`).
     * [backend/app/jobs/queue.py](file:///d:/Playground/Web-Dash/backend/app/jobs/queue.py):
       * پیاده‌سازی صف کارهای مبتنی بر DB با زمان‌بندی عادلانه نوبتی (Round-Robin Fair Scheduling) بین جاب‌های فعال.
       * ادعای اتمیک وظایف با دستور `UPDATE job_tasks SET status='running' WHERE id=:id AND status='queued'`.
       * پشتیبانی از فیلد `not_before` جهت تأخیر مجدد تسک‌هایی که روتر آنها در حال حاضر قفل است (Backoff 5s).
     * [backend/app/jobs/worker.py](file:///d:/Playground/Web-Dash/backend/app/jobs/worker.py):
       * تزریق شئ کانتکست اجرایی `TaskContext` شامل متدهای ثبت لاگ زنده (`ctx.log`)، بررسی لغو (`ctx.cancelled`)، ضربان قلب (`ctx.heartbeat`)، و مشخصات دستگاه.
       * آزادسازی تضمین‌شده قفل دستگاه در بلوک `finally`.
       * مکانیزم محاسبه و خلاصه وضعیت جاب والد (Status Roll-up):
         * همه تسک‌ها موفق -> `succeeded`.
         * ترکیب موفق و ناموفق/لغو -> `partial`.
         * همه ناموفق/لغو -> `failed` / `cancelled`.
     * [backend/app/jobs/engine.py](file:///d:/Playground/Web-Dash/backend/app/jobs/engine.py):
       * مدیریت چرخه حیات استخر ورکرها (`ThreadPoolExecutor`) با ظرفیت `MAX_SSH_WORKERS`.
       * ثبت هندلرهای تسک‌ها با `register_handler(job_type, fn)`.
       * ثبت جاب‌های جدید و تولید خودکار تسک‌ها به ازای روترهای هدف (`submit`).
       * ریکاوری خودکار در شروع برنامه (`recover_on_startup`): تغییر وضعیت تسک‌های رهاشده در وضعیت `running` به `failed` با پیام `interrupted by restart` و پاکسازی قفل‌های یتیم.
       * پاکسازی دوره‌ای لاگ رویدادهای قدیمی (`purge_old_events`).
     * [backend/app/jobs/scheduler.py](file:///d:/Playground/Web-Dash/backend/app/jobs/scheduler.py):
       * موتور پس‌زمینه زمان‌بندی وظایف با پشتیبانی از فرمت استاندارد کرون (پکیج `pycron`).
       * امکان ثبت وظایف دوره‌ای (نظیر به‌روزرسانی خودکار ARP/MAC، ریفرش دیتابیس زبیکس، بررسی انقضای لایسنس).
       * ارائه متد `trigger_now` جهت اجرای درجا و بدون وقفه (On-Demand Run Now).
       * کلید فعال‌سازی/غیرفعال‌سازی بدون نیاز به حذف کانفیگ (`toggle_schedule`).
  2. نگارش آزمون‌های جامع در [tests/test_step_2_2_job_engine_and_scheduler.py](file:///d:/Playground/Web-Dash/tests/test_step_2_2_job_engine_and_scheduler.py):
     * آزمون انحصار قفل دستگاه‌ها و تصاحب قفل‌های مرده.
     * آزمون ثبت جاب و دریافت استریم رویدادهای زنده.
     * آزمون لغو ایمن جاب‌ها و تسک‌های صف‌بندی‌شده.
     * آزمون ریکاوری بازراه‌اندازی سرور (Crash Recovery).
     * آزمون کامل چرخه حیات زمان‌بند کرون (ثبت، اجرا، کلید Run Now، و غیرفعال‌سازی).
     * **تست استرس سنگین (Stress Test):** اجرای هماهنگ ۲۰۰ تسک بر روی ۲۰ روتر هدف توسط ۱۰ ورکر موازی؛ بررسی عدم وجود هرگونه تداخل قفل، عدم ایجاد Deadlock، و رول‌آپ صحیح ۱۰۰٪ نتایج.
* **تأییدیه (Verify):**
  * اجرای سراسری Pytest روی تمامی تست‌های پروژه: **۷۱ تست با موفقیت ۱۰۰٪ پاس شدند (`71 passed in 26.71s`).**
  * هیچ‌گونه رگرسیونی در قابلیت‌های فاز ۱ و گام‌های پیشین مشاهده نشد.

---

### گام ۲.۳ — استریمینگ رویدادهای زنده SSE با قابلیت Replay و API جاب‌ها (Step 2.3 Realtime Events SSE with Replay - F-42)
* **هدف:** پیاده‌سازی اندپوینت‌های استاندارد `GET /api/v1/jobs/{id}/events` با پروتکل Server-Sent Events (SSE) برای ارسال بلادرنگ لاگ‌ها و رویدادهای روترها به کلاینت، پشتیبانی از هدر `Last-Event-ID` و کوئری `?since=` جهت بازپخش رویدادهای ازدست‌رفته هنگام قطع یا ریفرش صفحه، ارسال پینگ‌های ضربان قلب ۱۵ ثانیه‌ای جهت باز نگه‌داشتن کانکشن از پشت Reverse Proxyها، و پیاده‌سازی متدهای ایجاد، مشاهده و لغو جاب‌ها مطابق با Target Architecture §4.
* **اقدامات انجام‌شده:**
  1. ساخت بلوپرینت API جاب‌ها در [backend/app/api/jobs.py](file:///d:/Playground/Web-Dash/backend/app/api/jobs.py) و ثبت در فکتوری اپلیکیشن [backend/app/__init__.py](file:///d:/Playground/Web-Dash/backend/app/__init__.py):
     * `GET /api/v1/jobs/<job_id>/events`:
       * تولید خروجی استریم با `mimetype="text/event-stream"`، هدرهای `Cache-Control: no-cache` و `X-Accel-Buffering: no`.
       * **فاز بازپخش (Historical Replay):** استخراج وقایع ثبت‌شده در پایگاه داده (`job_events`) که شناسه آنها بزرگتر از `Last-Event-ID` یا پارامتر `since` باشد؛ اطمینان از اینکه با ریفرش مرورگر وسط اجرای جاب، حتی یک خط لاگ از دست نمی‌رود.
       * **فاز استریم زنده (Live Stream):** اتصال به صف مشترک در گذرگاه `event_bus`؛ ارسال بدون وقفه لاگ‌های جدید هر روتر بدون ایجاد خطوط تکراری (Deduplication).
       * **ضربان قلب (Heartbeat):** در صورت عدم دریافت رویداد جدید به مدت ۱۵ ثانیه، کامنت `: ping\n\n` ارسال می‌شود تا از قطع شدن اتصال توسط پروکسی‌ها/فایروال‌ها جلوگیری کند.
       * **سیگنال خاتمه (`event: done`):** به محض ترمینال شدن وضعیت جاب در پایگاه داده (`succeeded`, `failed`, `partial`, `cancelled`) و تخلیه کامل صف، رویداد پایانی حاوی خلاصه نتایج ارسال شده و استریم به طور تمیز بسته می‌شود.
       * تضمین آزادسازی صف مشترکین در بلوک `finally` و عدم وقوع هرگونه نشت حافظه (Memory Leak).
     * `GET /api/v1/jobs`:
       * دریافت لیست جاب‌ها با صفحه‌بندی (`?page=&page_size=`) و فیلترهای نوع و وضعیت؛ فرمت خروجی یکپارچه `{"items": [...], "total": int}` مطابق Target Architecture §4.
     * `GET /api/v1/jobs/<job_id>`:
       * دریافت اطلاعات کامل جاب والد، تسک‌های هر روتر، خطاها و زمان اجرا.
     * `POST /api/v1/jobs`:
       * ثبت جاب جدید با اعتبارسنجی دقیق Content-Type (رد داده غیر JSON با خطای 415).
       * اعتبارسنجی فیلد اجباری `type` (خطای ساختاریافته 400 `VALIDATION_ERROR`).
       * بررسی کلید ایمنی فقط‌خواندنی (`READ_ONLY_MODE`): مسدودسازی درخواست‌های `mode="apply"` با خطای 403 `READ_ONLY`.
     * `POST /api/v1/jobs/<job_id>/cancel`:
       * لغو بلادرنگ جاب و وظایف صف‌بندی‌شده.
  2. نگارش آزمون‌های اختصاصی در [tests/test_step_2_3_sse_realtime_events.py](file:///d:/Playground/Web-Dash/tests/test_step_2_3_sse_realtime_events.py):
     * آزمون ثبت جاب، دریافت جزییات و بررسی ساختار تسک‌ها.
     * آزمون رد پی‌لود غیر JSON (415) و بررسی اعتبارسنجی نوع جاب (400).
     * آزمون حفاظت فقط‌خواندنی (403) در زمان ارسال دستورات Apply.
     * آزمون بازپخش دقیق وقایع تاریخی (Replay) با استفاده از `Last-Event-ID` و عدم دریافت وقایع قبل از پوینتر.
     * آزمون دریافت سیگنال پایانی `event: done` روی جاب‌های خاتمه‌یافته.
     * آزمون لغو جاب از طریق اندپوینت Cancel.
     * آزمون پشتیبانی همزمان چند تب/کلاینت از یک جاب بدون تداخل رویدادها.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه تست‌های مخزن: **۷۷ تست با موفقیت ۱۰۰٪ پاس شدند (`77 passed in 24.76s`).**
  * سازگاری کامل با استانداردهای استریمینگ و عدم وجود رگرسیون در سایر بخش‌ها.

---

### گام ۲.۴ — کنترل دسترسی، تفکیک مالکیت جاب‌ها و دانلود قطعی CSV (Step 2.4 Job Ownership, RBAC & Deterministic CSV Export - F-05, F-30)
* **هدف:** اعمال کنترل دسترسی مبتنی بر نقش (RBAC) و تفکیک حریم کاربران بر روی جاب‌ها؛ اپراتورها فقط جاب‌های خود را ببینند در حالی که ادمین‌ها و مدیر کل (God) به تمامی جاب‌ها دسترسی دارند، پیشگیری از شمارش شناسه‌ها (Anti-Enumeration) با بازگرداندن خطای **404 Not Found** (به جای 403) در صورت تلاش برای دسترسی به جاب کاربری دیگر، و تولید قطعی و بدون جهش فایل دانلود CSV نتایج مستقیماً از روی ردیف‌های پایگاه داده.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی لایه تشخیص هویت و احراز مالکیت در [backend/app/api/jobs.py](file:///d:/Playground/Web-Dash/backend/app/api/jobs.py):
     * متد `_get_current_user_info()`: استخراج کاربر و نقش از نشست جاری فلاسک (`session["user"]` یا `session["username"]`).
     * متد `_can_access_job(job, username, role)`: اعمال قانون مالکیت؛ کاربران با نقش `admin` و `god` به تمامی جاب‌ها دسترسی دارند؛ کاربران با نقش `operator` و `viewer` منحصراً به جاب‌هایی که فیلد `created_by` آن‌ها با نام‌کاربری خودشان برابر باشد دسترسی خواهند داشت.
  2. محافظت ضد افشای شناسه (Anti-IDOR / Anti-Enumeration - F-05):
     * در کلیه اندپوینت‌های جزییات (`GET /<id>`)، استریم زنده (`GET /<id>/events`)، دانلود گزارش (`GET /<id>/download`) و لغو (`POST /<id>/cancel`)، اگر کاربر به جاب دسترسی نداشته باشد یا جاب وجود نداشته باشد، پاسخ **404 NOT FOUND** با ساختار خطای استاندارد Target Architecture §4 بازگردانده می‌شود تا مهاجم یا کاربر متخاصم نتواند وجود شناسه جاب‌های دیگران را تست کند.
  3. فیلترینگ خودکار لیست جاب‌ها (`GET /api/v1/jobs`):
     * برای کاربران اپراتور، کوئری به طور خودکار به `Job.created_by == username` محدود می‌شود.
     * برای ادمین‌ها، تمامی جاب‌ها به همراه امکان فیلتر اختیاری بر روی سازنده جاب (`?user=username`) نمایش داده می‌شود.
  4. پیاده‌سازی دانلود خروجی نتایج به صورت CSV قطعی (F-30):
     * اندپوینت `GET /api/v1/jobs/<job_id>/download`.
     * تولید جریان داده CSV از ردیف‌های جدول `job_tasks` پایگاه داده به صورت کاملاً قطعی (Deterministic Sorting) مرتب‌شده بر اساس `ORDER BY device_name ASC, id ASC`.
     * عدم تغییر، دستکاری یا جهش داده‌های ثبت‌شده در دیتابیس (Zero Mutation).
     * دانلودهای متوالی دقیقا بایت‌به‌بایت یکسان تولید می‌شوند.
     * تنظیم هدر الصاق با نام یکتای فایل: `Content-Disposition: attachment; filename="job_<type>_<id>.csv"`.
  5. پشتیبانی از پیشوند ریشه `/jobs`:
     * ثبت بلوپرینت با دو پیشوند `/api/v1/jobs` و `/jobs` در [backend/app/__init__.py](file:///d:/Playground/Web-Dash/backend/app/__init__.py).
  6. نگارش آزمون‌های اختصاصی در [tests/test_step_2_4_job_ownership_and_access_control.py](file:///d:/Playground/Web-Dash/tests/test_step_2_4_job_ownership_and_access_control.py):
     * آزمون دریافت خطای 404 توسط اپراتور B هنگام درخواست جاب اپراتور A در تمام روت‌ها (جزییات، استریم، دانلود و کنسل).
     * آزمون فیلترینگ مستقل لیست جاب‌ها برای اپراتورهای مختلف و مشاهده همه جاب‌ها توسط ادمین.
     * آزمون دسترسی کامل کاربران Admin و God به جاب‌های همه اپراتورها.
     * آزمون تولید خروجی CSV مرتب‌شده الفبایی، تطابق بایت‌به‌بایت در دانلود‌های مکرر و عدم دستکاری دیتابیس.
     * آزمون درستی مسیر مستعار `/jobs`.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه ۸۲ تست پروژه: **۸۲ تست با موفقیت ۱۰۰٪ پاس شدند (`82 passed in 35.33s`).**
  * امنیت، ایزولاسیون دسترسی و تضمین کیفیت صادرات داده تأیید شد.

---

### گام ۲.۵ — تفکیک ماژولار روت‌ها به بلوپرینت‌ها و تبدیل app.py به Shim تمیز (Step 2.5 Blueprints & Entrypoint Shim - F-15, F-16, F-43)
* **هدف:** حذف ساختار یکپارچه و غول‌پیکر ۲۷۰۰ خطی فایل ریشه `app.py` (F-43)، تفکیک کامل قابلیت‌ها به بلوپرینت‌های ماژولار و مستقل در پکیج `backend/app/api/`، ثبت خودکار و منسجم در Application Factory (`create_app()`)، تبدیل `app.py` به یک بارگذار تمیز و سبک (Shim) جهت حفظ سازگاری کامل با کلاینت‌های WSGI و ایمپورت‌های موروثی، و افزودن اندپوینت‌های مدیریت زمان‌بندی کرون (`schedules`).
* **اقدامات انجام‌شده:**
  1. تفکیک روت‌های قدیمی به ۱۳ بلوپرینت مجزا در [backend/app/api/](file:///d:/Playground/Web-Dash/backend/app/api):
     * [main.py](file:///d:/Playground/Web-Dash/backend/app/api/main.py): روت اصلی نمایش رابط کاربری داشبورد (`GET /`).
     * [auth.py](file:///d:/Playground/Web-Dash/backend/app/api/auth.py): روت‌های نشست و اعتبارسنجی کاربر (`/login`, `/logout`, `/me`, `/change-password`).
     * [users.py](file:///d:/Playground/Web-Dash/backend/app/api/users.py): مدیریت حساب‌ها، پرمیشن‌ها و لاگ ادمین (`/admin/users`, `/admin/permissions`, `/admin/audit-log`).
     * [jobs.py](file:///d:/Playground/Web-Dash/backend/app/api/jobs.py): موتور مرکزی جاب‌ها، استریم SSE، لغو و خروجی قطعی CSV.
     * [alarm_clear.py](file:///d:/Playground/Web-Dash/backend/app/api/alarm_clear.py): رفع آلارم‌های دستی و گروهی، پردازش CSV نودها، استریم و گزارش (`/run-manual`, `/run-bulk`, `/parse-csv`, `/stream/<sid>`, `/download/<sid>`, `/session/<sid>`).
     * [reports.py](file:///d:/Playground/Web-Dash/backend/app/api/reports.py): گزارش لینک‌های دان و ترانک‌های شبکه (`/run-report`, `/run-full-report`, `/parse-csv-nodes`, `/stream-report/<sid>`, `/download-report/<sid>`, `/download-trunk-report/<sid>`, `/report-session/<sid>`, `/report-analytics/<sid>`).
     * [license.py](file:///d:/Playground/Web-Dash/backend/app/api/license.py): بررسی و پایش لایسنس‌ها، تطبیق خودکار فایل‌ها، فرآیند تمدید تعاملی با تأیید اپراتور و آرشیو فایل‌های قدیمی (`/run-license-check`, `/stream-license/<sid>`, `/license-session/<sid>`, `/download-license-summary/<sid>`, `/license-report/<sid>`, `/license-warnings/<sid>`, `/cancel-license-session/<sid>`, `/download-license-items/<sid>`, `/match-licenses`, `/start-renewal`, `/download-renewal-report/<path:sid>`, `/confirm-renewal/<sid>`, `/stream-lic-renewal/<sid>`, `/admin/renewal-reports`, `/admin/license-archive-files`, `/download-archived-license/<filename>`).
     * [routing.py](file:///d:/Playground/Web-Dash/backend/app/api/routing.py): بررسی روتینگ VRF و BGP هواوی و تحلیل اینترفیس مبدا (`/vrf-router-info`, `/parse-interface-config`, `/check-vrf-routing`, `/check-bgp-route`, `/show-originator-interfaces`).
     * [telemetry.py](file:///d:/Playground/Web-Dash/backend/app/api/telemetry.py): همگام‌سازی و جستجوی پایگاه داده زبیکس و اینترفیس‌ها (`/admin/zabbix-groups`, `/admin/refresh-zabbix-db`, `/admin/delete-zabbix-db`, `/refresh-zabbix-progress`, `/search-zabbix-interfaces`, `/search-zabbix-ip`).
     * [arp.py](file:///d:/Playground/Web-Dash/backend/app/api/arp.py): جستجوی بلادرنگ ARP/MAC، مدیریت کالکتور دسته‌جمعی و اندپوینت‌های آرشیو و تاریخچه اسکن‌ها درخواستی کاربر (`/search-site-arp-mac`, `/search-ip-arp-mac`, `/admin/parse-ne-csv`, `/admin/run-arp-mac-collector`, `/admin/arp-mac-collector-status`, `/admin/arp-mac-collector-stop`, `/admin/arp-mac/snapshots`, `/admin/arp-mac/snapshots/<id>/download`, `/admin/arp-mac/current/download`).
     * [sessions_export.py](file:///d:/Playground/Web-Dash/backend/app/api/sessions_export.py): استخراج سشن‌های SecureCRT/SSH و تولید پکیج ZIP دسته‌بندی‌شده بر اساس ساب‌نت‌ها (`/session-extractor/parse`, `/session-extractor/download`).
     * [ptp.py](file:///d:/Playground/Web-Dash/backend/app/api/ptp.py): عیب‌یابی هاپ‌به‌هاپ زنده PTP، ردگیری مسیر و استریم لاگ‌های تشخیصی (`/ptp/search-targets`, `/ptp/start-troubleshoot`, `/ptp/stream/<sid>`, `/ptp/session/<sid>`).
     * [schedules.py](file:///d:/Playground/Web-Dash/backend/app/api/schedules.py): مدیریت و اتوماسیون زمان‌بندی کرون در منوی ادمین مطابق درخواست کاربر با قابلیت اجرای آنی On-Demand (`GET/POST /api/v1/schedules`, `DELETE /<id>`, `POST /<id>/toggle`, `POST /<id>/run`).
  2. تجمیع توابع کمکی مشترک و لایه امنیتی در [backend/app/api/common.py](file:///d:/Playground/Web-Dash/backend/app/api/common.py):
     * متدهای `get_client_ip()`, `get_json_payload()`, `read_only_blocked()`, `parse_csv_to_routers()`.
  3. بازنویسی [app.py](file:///d:/Playground/Web-Dash/app.py) به صورت یک بارگذار تمیز (Shim) در ریشه پروژه:
     * حجم فایل از ۲۷۱۱ خط کد پیچیده به ۲۵ خط کد خوانا تقلیل یافت.
     * اتصال خودکار به `create_app()` و در دسترس بودن متغیر `app` جهت سازگاری با کلیه سرورهای وب و ابزارهای تست.
  4. نگارش آزمون‌های اختصاصی در [tests/test_step_2_5_blueprints_and_shim.py](file:///d:/Playground/Web-Dash/tests/test_step_2_5_blueprints_and_shim.py):
     * صحت ثبت تمامی ۱۳ بلوپرینت در هسته برنامه.
     * آزمون روت‌های اصلی و روتینگ VRF.
     * آزمون اندپوینت‌های اسنپ‌شات و دانلود آرشیو ARP/MAC.
     * آزمون کامل CRUD و اجرای دستی تسک‌های زمان‌بندی‌شده کرون در اندپوینت `/api/v1/schedules`.
     * آزمون سلامت ماژول‌های جستجوی PTP و استخراج سشن.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه ۸۸ تست سیستم: **۸۸ تست با موفقیت ۱۰۰٪ پاس شدند (`88 passed in 27.69s`).**
  * تأیید کارکرد بدون وقفه و صفر رگرسیون بر روی تمامی قابلیت‌های سیستم.

---

### گام ۲.۶ — لاگینگ ساختاریافته JSON، ثبت وقایع حسابرسی در پایگاه داده و اکسپورتر متریک‌های پرومتئوس (Step 2.6 Structured Logging, DB Audit Log & Prometheus Metrics - F-44)
* **هدف:** رفع نقص F-44 از طریق استقرار لاگینگ ساختاریافته تک‌خطی JSON روی خروجی استاندارد، جایگزینی لاگ متنی فایل با جدول رابطه‌ای `audit_logs` جهت ثبت پایدار رویدادهای امنیتی به همراه حفظ فایل متنی به عنوان Fallback، ردیابی کانتکست جاب‌ها و تسک‌ها و کاربران در لاگ‌ها، و افزودن اندپوینت استاندارد متریک‌های پرومتئوس (`/metrics`) جهت مانیتورینگ بلادرنگ وضعیت سیستم در استک‌های Zabbix و Grafana.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی فرمت‌دهنده لاگ‌های ساختاریافته در [backend/app/logging.py](file:///d:/Playground/Web-Dash/backend/app/logging.py):
     * کلاس `JsonFormatter`: تبدیل هر رکورد لاگ استاندارد پایتون به یک خط JSON معتبر شامل فیلدهای:
       `ts` (زمان UTC بر اساس ISO 8601), `level`, `logger`, `message`, `job_id`, `task_id`, `device`, `user`.
     * پشتیبانی از متغیرهای زمینه‌ای (`contextvars`): `job_id_var`, `task_id_var`, `device_var`, `user_var` جهت همبستگی (Correlation) خودکار بین تسک‌ها، لاگ‌ها و کاربر عامل حتی در محیط‌های ناهمگام و چندنخی.
     * توابع کمکی `set_log_context()` و `clear_log_context()`.
     * متد `setup_logging()` جهت پیکربندی لاگر ریشه و ادغام آن با شیء Flask `app`.
  2. به‌روزرسانی سیستم لاگ حسابرسی در [audit.py](file:///d:/Playground/Web-Dash/audit.py):
     * ارتقای `record_audit`: ذخیره‌سازی داده‌های ساختاریافته در جدول رابطه‌ای `audit_logs` (مدل [backend/app/models/audit.py](file:///d:/Playground/Web-Dash/backend/app/models/audit.py)) از طریق نشست دیتابیس `get_db_session()`.
     * استراتژی ثبت دوگانه تاب‌آور (Dual-Write Resilient Strategy): ثبت همزمان در دیتابیس و فایل `DATA_DIR/audit.log` به عنوان Fallback پشتیبان در صورت قطع ارتباط پایگاه داده.
     * ارتقای `get_audit_entries`: واکشی رکوردهای لاگ حسابرسی از دیتابیس با کوئری `order_by(AuditLog.id.desc())` با جایگزینی خودکار فایل در صورت بروز خطا.
     * اعمال ماسک امنیتی بر روی مقادیر کلمات عبور، توکن‌ها و سکرت‌ها (`[REDACTED]`).
  3. توسعه موتور جمع‌آوری و اکسپورت متریک‌های پرومتئوس در [backend/app/metrics.py](file:///d:/Playground/Web-Dash/backend/app/metrics.py):
     * تولید خروجی مبتنی بر فرمت متن پرومتئوس (Prometheus Exposition Format v0.0.4).
     * شمارنده جاب‌ها: `webdash_jobs_total{type, status}` برگرفته مستقیم از جداول دیتابیس با حفظ مقادیر پس از ری‌استارت.
     * شمارنده خطاهای ارتباطی SSH: `webdash_ssh_failures_total{reason}` با تفکیک دقیق کلاس خطاها (`auth_failed`, `timeout`, `connection_refused`, `unreachable`, `command_error`).
     * هیستوگرام زمان اجرای تسک‌ها: `webdash_task_duration_seconds` با باکت‌های زمانی استاندارد (`0.5s` تا `120s`).
     * شمارنده رخدادهای قفل دیوایس: `webdash_device_lock_waits_total`.
  4. ادغام متریک‌ها و کانتکست در لایه ورکر [backend/app/jobs/worker.py](file:///d:/Playground/Web-Dash/backend/app/jobs/worker.py):
     * تزریق خودکار متغیرهای کانتکست `set_log_context(job_id, task_id, device, user)` در متد `execute_task`.
     * سنجش دقیق مدت زمان اجرای تسک با `time.monotonic()` و ثبت در هیستوگرام.
     * دسته‌بندی و ثبت خطاهای SSH به تفکیک ریشه‌یابی خطا.
     * ثبت زمان‌های انتظار قفل دیوایس در متریک‌ها.
  5. راه‌اندازی اندپوینت `/metrics` و هماهنگی میدل‌ور:
     * اضافه شدن مسیر `GET /metrics` در Application Factory (`backend/app/__init__.py`).
     * معاف‌سازی اندپوینت `/metrics` از چک‌های امنیتی سشن و CSRF جهت امکان اسکرپ شدن توسط Prometheus و Zabbix HTTP Agent.
  6. نگارش آزمون‌های اختصاصی در [tests/test_step_2_6_logging_audit_and_metrics.py](file:///d:/Playground/Web-Dash/tests/test_step_2_6_logging_audit_and_metrics.py):
     * آزمون ساختار فیلدهای خروجی JSON لاگر و درستی مقداردهی ContextVars.
     * آزمون ثبت رکورد در جدول دیتابیس و فایل `audit.log` و تأیید ماسک بودن پسوردها.
     * آزمون فرمت استاندارد پرومتئوس و مقادیر باکت‌های هیستوگرام و شمارنده‌های `/metrics`.
     * آزمون عملکرد پروب‌های سلامت `/healthz` و آمادگی `/readyz`.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه ۹۲ تست سیستم: **۹۲ تست با موفقیت ۱۰۰٪ پاس شدند (`92 passed in 28.17s`).**
  * خروجی لاگ‌های جیسون و متریک‌های مانیتورینگ تأیید شدند.

---

### گام ۲.۷ — انتقال مدل کاربران به پایگاه داده، سلسله‌مراتب نقش‌ها و پشتیبان‌گیری فایل (Step 2.7 User DB Migration, RBAC Roles & JSON Backup - F-05, F-24)
* **هدف:** حذف وابستگی عملیاتی به فایل مسطح `users.json` از طریق انتقال هویت کاربران، رمزهای هش‌شده Argon2id و سطوح دسترسی به جداول رابطه‌ای پایگاه داده (`users` و `permissions`)، پیاده‌سازی نقش‌های سلسله‌مراتبی استاندارد (`god`, `admin`, `operator`, `viewer`) با اعمال محدودیت دسترسی کاملاً خواندنی برای نقش `viewer`، و حفظ خودکار فایل `users.json` به عنوان نسخه پشتیبان و همگام همیشگی.
* **اقدامات انجام‌شده:**
  1. ارتقای بارگذاری و احراز هویت کاربران در [auth.py](file:///d:/Playground/Web-Dash/auth.py):
     * متد `load_users()`: ابتدا کاربران را مستقیماً از جدول رابطه‌ای دیتابیس `User` واکشی می‌کند.
     * فرآیند مهاجرت خودکار بدون وقفه (On-the-fly ETL Sync): در صورت وجود فایل `users.json` و خالی بودن دیتابیس (یا اضافه شدن کاربر جدید در فایل)، اطلاعات کاربران و سطوح دسترسی به صورت خودکار به دیتابیس منتقل می‌شود.
     * همگام‌سازی دوطرفه فایل پشتیبان: در توابع `save_users()`، `add_user()`، `update_user()` و `delete_user()`، هرگونه تغییر ابتدا در جدول پایگاه داده اعمال شده و سپس همزمان فایل `users.json` به عنوان نسخه پشتیبان محلی با داده‌های به‌روز بازنویسی می‌شود.
  2. تثبیت نقش‌ها و سطوح دسترسی پیش‌فرض (Roles Matrix):
     * تعریف دقیق نقش‌های چهارگانه:
       - `god`: دسترسی کامل زیرساخت، سوپرادمین غیرقابل تنزل، مدیریت کاربران، زمان‌بندی و تنظیمات.
       - `admin`: دسترسی مدیریتی کامل به ماژول‌های سامانه، تنظیمات و مانیتورینگ.
       - `operator`: دسترسی عملیاتی جهت اجرای جاب‌ها، ترابل‌شوتینگ، پاکسازی آلارم‌ها و فرآیندهای لایسنس.
       - `viewer`: کاربر منحصراً فقط‌خواندنی. تمام دسترسی‌های ویرایشی، پاکسازی آلارم، تغییر لایسنس، کالکتور و مدیریت کاربران مسدود است و فقط به بخش‌های گزارش‌گیری، جستجوی زبیکس، بررسی روتینگ و ARP دسترسی دارد (`reporting`, `vrf_routing`, `zabbix_search`, `code_site_search`, `session_extractor`).
     * پشتیبانی از نقش سازگاری عقبرو `user`.
  3. به‌روزرسانی کنترلر کاربران در [backend/app/api/users.py](file:///d:/Playground/Web-Dash/backend/app/api/users.py):
     * مجاز شناختن نقش‌های جدید `god`, `admin`, `operator`, `viewer` در اعتبارسنجی هنگام ایجاد یا تغییر نقش کاربر.
  4. تثبیت سازوکار تقدم متغیرهای محیطی مسیر داده در [backend/app/config.py](file:///d:/Playground/Web-Dash/backend/app/config.py):
     * اولویت‌بندی `get_data_dir()`: ابتدا `WEBDASH_DATA_DIR`، سپس `DATA_DIR` و در نهایت مسیر پیش‌فرض داخلی جهت تضمین ایزولاسیون کامل محیط‌های تستی و عملیاتی.
  5. نگارش آزمون‌های خودکار جامع در [tests/test_step_2_7_user_db_migration_and_roles.py](file:///d:/Playground/Web-Dash/tests/test_step_2_7_user_db_migration_and_roles.py):
     * آزمون مهاجرت خودکار داده‌های `users.json` به جداول دیتابیس هنگام بوت.
     * آزمون همگام‌سازی پایدار تغییرات کاربر و رمز عبور از دیتابیس به فایل پشتیبان `users.json`.
     * آزمون اعمال دقیق محدودیت‌های دسترسی نقش `viewer` (ممانعت از پاکسازی آلارم، تغییرات دیوایس و اجرای کالکتور).
     * آزمون انتساب و اعتبارسنجی نقش‌ها در منوی مدیریت کاربران.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه ۹۶ تست سیستم: **۹۶ تست با موفقیت ۱۰۰٪ پاس شدند (`96 passed in 37.08s`).**
  * صحت عملیات همگام‌سازی دوطرفه دیتابیس و فایل `users.json` تأیید شد.

---

### گام ۲.۸ — گاوصندوق رمزنگاری‌شده اعتبارسنجی تجهیزات شبکه و ممنوعیت ارسال کلمات عبور متنی (Step 2.8 Credential Vault & Plaintext Password Prohibition - F-06)
* **هدف:** رفع قطعی آسیب‌پذیری بحرانی F-06 (انتقال کلمات عبور تجهیزات شبکه در بدنه درخواست‌ها و آرگومان‌های خام)، ایجاد گاوصندوق متمرکز اعتبارسنجی با رمزنگاری متقارن نظامی استاندارد Fernet با استفاده از کلید ۳۲ بایتی امنیتی `WEBDASH_VAULT_KEY`، ممانعت قطعی از ذخیره کلمات عبور متنی در دیتابیس و جاب‌ها، اعمال کنترل دسترسی RBAC، حل و فصل خودکار کلمات عبور توسط ورکرها از طریق شناسه `credential_id` یا پیوند به دیوایس، و پشتیبانی سازگار عقبرو از اندپوینت‌های قدیمی همراه با ثبت هشدارهای Deprecation.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی موتور رمزنگاری و مدیریت گاوصندوق در [backend/app/security/vault.py](file:///d:/Playground/Web-Dash/backend/app/security/vault.py):
     * توابع رمزنگاری متقارن `encrypt_secret` و `decrypt_secret` مبتنی بر کتابخانه `cryptography.fernet.Fernet`.
     * مدیریت کلید `get_vault_key`: خواندن از متغیر محیطی `WEBDASH_VAULT_KEY` یا مسیر فایل. در محیط عملیاتی (Production)، در صورت مفقود بودن کلید سامانه از بالا آمدن امتناع کرده و استثنای صریح `RuntimeError` بالا می‌آورد (Fail-Fast). در محیط توسعه و تست، کلید به صورت امن در فایل `.vault_key` نگهداری می‌شود.
     * کلاس `VaultService`: پیاده‌سازی متدهای ساخت (`create_credential`)، فهرست‌بندی ایمن بدون افشای سکرت (`list_credentials`)، استخراج سکرت رمزگشایی‌شده منحصراً برای ورکرها (`get_decrypted_secret`)، ویرایش/چرخش کلیدها (`update_credential`)، حذف و آزادسازی ارجاعات کلید خارجی دیوایس‌ها (`delete_credential`)، پیوند به دیوایس (`attach_to_device`)، حل و فصل خودکار اعتبارسنجی (`resolve_credentials`)، و بازرمزنگاری گروهی کلیدها (`rotate_all`).
  2. محافظت لایه مدل در [backend/app/models/device.py](file:///d:/Playground/Web-Dash/backend/app/models/device.py):
     * پیاده‌سازی متد `to_dict()` در مدل `Credential`: خروجی دیکشنری شامل `id`, `name`, `kind`, `username`, `meta`, `created_at` بوده و هرگز فیلد `secret_encrypted` یا سکرت متنی را فاش نمی‌کند.
     * کلید خارجی `devices.credential_id` با خاصیت `ondelete="SET NULL"`.
  3. توسعه بلوپرینت متمرکز [backend/app/api/credentials.py](file:///d:/Playground/Web-Dash/backend/app/api/credentials.py):
     * اندپوینت‌های استاندارد RESTful:
       - `GET /api/v1/credentials` و `/credentials`: دریافت لیست متادیتای مدارک اعتباری (بدون سکرت).
       - `POST /api/v1/credentials`: ایجاد مدرک اعتباری جدید و رمزنگاری بلادرنگ سکرت (نیاز به نقش `admin` یا `god`).
       - `GET /api/v1/credentials/<id>`: دریافت اطلاعات تکمیلی یک مدرک اعتباری.
       - `PUT /api/v1/credentials/<id>`: ویرایش مشخصات یا چرخش (Rotate) کلمه عبور با رمزنگاری مجدد.
       - `DELETE /api/v1/credentials/<id>`: حذف مدرک اعتباری و خروج از دیوایس‌های منتسب.
       - `POST /api/v1/credentials/<id>/attach`: پیوند یک مدرک اعتباری به تجهیزات شبکه (`device_name`).
     * کنترل دسترسی RBAC: مسدودسازی کامل دسترسی نقش `viewer` (خطای 403)، دسترسی فقط‌خواندنی نقش `operator` و حقوق مدیریتی کامل برای `admin` و `god`.
  4. اعمال ممانعت قطعی از ارسال رمز عبور متنی در جاب‌ها (F-06 Hardening) در [backend/app/api/jobs.py](file:///d:/Playground/Web-Dash/backend/app/api/jobs.py):
     * تابع `_has_plaintext_creds`: بررسی بازگشتی ساختار پارامترهای ارسالی در درخواست `POST /api/v1/jobs`.
     * در صورت وجود فیلدهای کلمه عبور متنی (`password`, `secret`, `ssh_password`, `plaintext_password`)، درخواست بلافاصله با خطای استاندارد 400 و کد `FORBIDDEN_PARAM` رد می‌شود:
       `"Plaintext passwords in job params are forbidden (F-06). Store credentials in vault and reference via credential_id."`
  5. حل و فصل خودکار در موتور جاب‌ها در [backend/app/jobs/engine.py](file:///d:/Playground/Web-Dash/backend/app/jobs/engine.py):
     * در تابع `_worker_execute`، قبل از اجرای تسک توسط ورکرها، مدارک اعتباری به صورت خودکار از طریق `job.params["credential_id"]` یا از فیلد `device.credential_id` مربوط به نام روتر، توسط `VaultService.resolve_credentials` استخراج و به شکل رمزگشایی‌شده در کانتکست ایزوله `TaskContext.creds` به ورکر تزریق می‌شود.
  6. پشتیبانی سازگار و ثبت رویداد Deprecation در اندپوینت‌های قدیمی:
     * طراحی تابع کمکی `resolve_request_credentials` در [backend/app/api/common.py](file:///d:/Playground/Web-Dash/backend/app/api/common.py):
       - در صورت ارسال `credential_id`، مقادیر کاربری و رمز از گاوصندوق دیتابیس استخراج می‌شود.
       - در صورت ارسال سنتی `username`/`password` متنی، ضمن حفظ سازگاری جهت عدم شکست کلاینت‌های قدیمی، هشدار لاگ ساختاریافته `DEPRECATION [F-06]: Endpoint ... received plaintext password in request body. Migrate to vault credential_id.` ثبت می‌شود.
     * ادغام این تابع در اندپوینت‌های `/run-manual`، `/run-bulk`، `/run-report`، `/run-full-report`، `/run-license-check`، `/start-renewal`، `/check-vrf-routing`، `/check-bgp-route`، `/show-originator-interfaces`، `/admin/run-arp-mac-collector` و `/ptp/start-troubleshoot`.
  7. راه‌اندازی و اعتبارسنجی بوت در Application Factory ([backend/app/__init__.py](file:///d:/Playground/Web-Dash/backend/app/__init__.py)):
     * ثبت بلوپرینت `credentials_bp` در مسیرهای `/api/v1/credentials` و `/credentials`.
     * اعتبارسنجی اولیه کلید گاوصندوق هنگام شروع به کار سرور.
  8. نگارش آزمون‌های خودکار جامع در [tests/test_step_2_8_credential_vault.py](file:///d:/Playground/Web-Dash/tests/test_step_2_8_credential_vault.py):
     * آزمون صحت رمزنگاری متقارن Fernet و تأیید قطعی عدم وجود رمز عبور متنی در دیتابیس با بازرسی مستقیم SQL.
     * آزمون چرخش کلیدها (Secret / Key Rotation).
     * آزمون امتناع از بوت در صورت نبود کلید در محیط Production.
     * آزمون کلیه اندپوینت‌های CRUD، متادیتای ایمن و ماتریکس دسترسی نقش‌های RBAC.
     * آزمون ممانعت از ارسال رمز متنی در اندپوینت جاب‌ها و تأیید تخلیه پارامترها در دیتابیس.
     * آزمون انتساب مدارک به دیوایس و حل و فصل خودکار در تسک‌ها.
     * آزمون سازگاری اندپوینت‌های قدیمی با `credential_id` و ثبت لاگ Deprecation برای کلمات عبور متنی.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه ۱۰۳ تست سیستم: **۱۰۳ تست با موفقیت ۱۰۰٪ پاس شدند (`103 passed, 20 warnings in 38.20s`).**
  * عدم وجود هرگونه رمز عبور متنی در پایگاه داده و برقراری کامل ایزولاسیون امنیتی تأیید شد.

---

### گام ۲.۹ — آزمون‌های جامع رگرسیون فاز ۲ و تثبیت پلتفرم (Step 2.9 Phase 2 Regression Pass & Verification)
* **هدف:** اعتبارسنجی یکپارچه و جامع تمامی قابلیت‌ها، جداول پایگاه داده، موتور جاب‌ها، استریم بلادرنگ، بلوپرینت‌های ماژولار، لاگ‌های ساختاریافته، اکسپورتر پرومتئوس، نقش‌های RBAC، و گاوصندوق رمزنگاری‌شده در قالب آزمون‌های جامع سراسری و اطمینان از صفر رگرسیون پیش از ادغام نهایی شاخه `phase2` در شاخه اصلی `main`.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی آزمون یکپارچه چرخه حیات فاز ۲ در [tests/test_step_2_9_phase2_regression.py](file:///d:/Playground/Web-Dash/tests/test_step_2_9_phase2_regression.py):
     * سنجش اولیه پروب‌های سلامت و آمادگی `/healthz` و `/readyz` و اکسپورتر متریک‌های پرومتئوس `/metrics`.
     * ایجاد مدرک اعتباری در گاوصندوق رمزنگاری‌شده با Fernet و پیوند خودکار آن به روتر هدف هواوی (`Device`).
     * ثبت جاب جدید با `credential_id` و اطمینان از مسدودسازی قطعی رمزهای متنی (F-06).
     * استخراج و حل و فصل خودکار کلمات عبور توسط لایه ورکر `JobEngine` بدون فاش شدن سکرت در پارامترها یا لاگ‌ها.
     * اعتبارسنجی استریم بلادرنگ رویدادهای جاب با مکانیزم Replay رویدادها از طریق `?since=`.
     * اعتبارسنجی ایزولاسیون امنیتی RBAC: ممانعت از مشاهده جاب‌های دیگران توسط اپراتورها (پاسخ 404 ضد شمارش)، و مسدودسازی تغییرات توسط نقش `viewer` (خطای 403).
     * اعتبارسنجی صحت خروجی شمارنده‌ها و هیستوگرام‌های `/metrics` پس از اجرای تسک‌ها.
     * اعتبارسنجی ایجاد و اجرای دستی جاب‌های زمان‌بندی‌شده کرون در اندپوینت `/api/v1/schedules`.
  2. بهینه‌سازی و تثبیت نشست‌های پایگاه داده در [backend/app/db/session.py](file:///d:/Playground/Web-Dash/backend/app/db/session.py):
     * استفاده از استراتژی `NullPool` برای اتصالات SQLite به منظور آزادسازی بلادرنگ قفل فایل‌های دیتابیس در سیستم‌عامل ویندوز بلافاصله پس از اتمام تراکنش‌ها.
     * پاکسازی و نوسازی خودکار موتور در متد `close_db()` و `get_engine()` در صورت تغییر مسیر دیتابیس در تست‌های ایزوله.
     * مقداردهی خودکار اسکیما و جداول برای موتورهای SQLite جدید در شروع به کار.
  3. انعطاف‌پذیری پارامترهای زمان‌بندی در [backend/app/api/schedules.py](file:///d:/Playground/Web-Dash/backend/app/api/schedules.py):
     * پذیرش نام‌های مستعار `cron_expr`، `cron_expression` و `cron` جهت سهولت ادغام و یکپارچگی کلاینت‌ها.
  4. اجرای سراسری سوئیت آزمون‌های فاز ۱ و فاز ۲ بر روی کل مخزن کد:
     * اجرای مجموع ۱۰۴ تست خودکار در ۱۸ ماژول آزمون.
* **تأییدیه (Verify):**
  * اجرای Pytest روی کلیه ۱۰۴ تست سیستم: **۱۰۴ تست با موفقیت ۱۰۰٪ پاس شدند (`104 passed, 101 warnings in 65.67s`).**
  * تایید یکپارچگی کامل معماری ماژولار فاز ۲ و آمادگی کامل برای ادغام در شاخه `main`.

---

## فاز ۳ — لایه ارتباط با تجهیزات و تله‌متری (Phase 3: Device Layer SSH & Telemetry)

### گام ۳.۱ و ۳.۲ — تجرید درایور تجهیزات هواوی، چرخه حیات نشست، همزمانی و مدارشکن (Steps 3.1 & 3.2 Device Session, VRP Drivers & Circuit Breaker)
* **هدف:** ایجاد یک لایه مطمئن، ایزوله و آزمون‌پذیر برای تعامل با روترهای هواوی VRP5 و VRP8، رفع آسیب‌پذیری‌های F-28 (نشت سوکت SSH) و F-32 (عدم تمایز رفتاری VRP8/VRP5) و اعمال قفل‌های ایمنی جهت ممانعت از اعمال کانفیگ مجدد در نشست‌های قطع‌شده.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی پکیج متمرکز [backend/app/devices/](file:///d:/Playground/Web-Dash/backend/app/devices/):
     * سلسله‌مراتب خطاهای تایپ‌شده در `errors.py`:
       - `DeviceError`, `ConnectTimeout`, `AuthFailed`, `CommandTimeout`, `ViewError`, `ParseError`, `DeviceLocked`, `ConfigRejected`.
       - تابع نگاشت خطاهای Netmiko و سوکت به استثناهای تایپ‌شده `map_netmiko_exception`.
       - تابع بازرسی بنرهای خطای بومی هواوی `check_vrp_banner_errors` (`Error:`, `Unrecognized command`, `Wrong parameter`, `Ambiguous command`).
     * رجیستری متمرکز دستورات CLI روترها در `registry.py`:
       - تعریف مدل داده `DeviceCommand` شامل نام منطقی دستور، نگاشت دستور برای هر خانواده سیستم‌عامل (`vrp5`, `vrp8`)، زمان انقضا، پرچم `read_only` و وضعیت راستی‌آزمایی سخت‌افزاری (`verified`).
       - ثبت دستورات استاندارد هواوی (`display version`, `display alarm active`, `display interface`, `commit`, `rollback`, ...).
     * درایورهای اختصاصی هواوی در زیرپوشه `drivers/`:
       - کلاس پایه `BaseVRPDriver` با توابع غیرفعال‌سازی صفحه‌بندی (`screen-length 0 temporary` و `undo terminal monitor`) و مدیریت ورود/خروج به `system-view`.
       - درایور `VRP5Driver` با مدل اعمال بلادرنگ (بدون `commit`).
       - درایور `VRP8Driver` با مدل Candidate Configuration و الزام دستور `commit`.
     * کانتکست منیجر مستحکم `DeviceSession` در `session.py`:
       - انضباط دقیق تلاش مجدد: حداکثر ۲ تلاش مجدد با فاصله زمانی (Backoff) فقط برای خطاهای اتصال/احراز هویت.
       - **قفل ایمنی قطعی:** بلافاصله پس از ارسال اولین دستور تغییر کانفیگ (`_config_executed = True`)، هرگونه تلاش مجدد برای اتصال مجدد غیرفعال می‌شود تا کانفیگ ناقص یا مضاعف اعمال نگردد.
       - **جلوگیری قطعی از نشت سوکت (F-28):** متد `disconnect()` در بلوک‌های `finally` و حتی بین دفعات تلاش مجدد فراخوانی می‌شود.
       - قابلیت سانسور و ماسک‌کردن خودکار کلمات عبور و سکرت‌ها در رونوشت‌های متنی CLI (`redact_sensitive_cli`).
     * کنترل همزمانی و مدارشکن در `pool.py`:
       - مدارشکن `DeviceCircuitBreaker`: ثبت ۳ خطای متوالی اتصال در بازه ۱۰ دقیقه، وضعیت دستگاه را به مدت ۵ دقیقه به `SKIPPED_UNREACHABLE` تغییر می‌دهد.
       - کنترل نرخ همزمانی سایت `SiteRateLimiter` با سقف پیش‌فرض ۵ اتصال همزمان به ازای هر سایت.
       - اعمال تاخیر تصادفی ورود (Jitter 0-500ms) جهت پیشگیری از هجوم ورود همزمان به روترها (Login Storm).
  2. نگارش آزمون‌های جامع در [tests/test_step_3_1_device_session_and_drivers.py](file:///d:/Playground/Web-Dash/tests/test_step_3_1_device_session_and_drivers.py).
* **تأییدیه (Verify):**
  * اجرای ۱۱ آزمون تخصصی لایه درایور و نشست با موفقیت ۱۰۰٪ (`11 passed`).

---

### گام ۳.۳ — پارسرهای ساختاریافته خروجی CLI و اعتبارسنجی گرامر اینترفیس‌ها (Step 3.3 Parsers & Interface Grammar)
* **هدف:** جایگزینی کامل عبارات باقاعده ناپایدار قدیمی با پارسرهای مستحکم و ایمن، رفع نقص F-25 (خطای پارس به جای لیست خالی)، رفع F-20 (عدم تلقی پاسخ خالی به عنوان پورت بدون کانفیگ)، رفع F-29 (جلوگیری از ضرب دکارتی در لایسنس) و رفع F-21 (اعتبارسنجی و نرمال‌سازی نام پورت‌ها).
* **اقدامات انجام‌شده:**
  1. توسعه پکیج تخصصی [backend/app/devices/parsers/](file:///d:/Playground/Web-Dash/backend/app/devices/parsers/):
     * موتور استخراج و نرمال‌سازی نام پورت‌ها در `interface_ref.py` (رفع F-21):
       - نرمال‌سازی پیشوندهای هواوی (`GE` -> `GigabitEthernet`, `10GE`/`XGE` -> `XGigabitEthernet`, `Eth-Trunk`, `Vlanif`, `LoopBack`, `Serial`, `Pos`, `Cpos`).
       - پشتیبانی کامل از ساب‌اینترفیس‌ها (`.NNN`) و استخراج اینترفیس والد (`parent`).
       - پاکسازی علائم نگارشی پایانی (پرانتز، ویرگول، نقطه، دونقطه).
       - کشف قطعی ابهام: در صورتی که در یک آلارم بیش از یک اینترفیس والد متفاوت ذکر شده باشد، خروجی `None` بازمی‌گردد تا از تغییر اشتباه پورت‌ها جلوگیری شود.
     * پارسر آلارم‌های فعال در `alarms.py` (رفع F-25):
       - پشتیبانی از فرمت‌های زمانی با آفست (`+HH:MM`)، منطقه زمانی `Z` و بدون تایم‌زون.
       - پشتیبانی از ادغام سطرهای چندخطی توضیحات آلارم (Wrapped descriptions).
       - بررسی ایمنی F-25: در صورتی که خروجی روتر بیش از ۳ سطر غیربنر داشته باشد اما هیچ آلارمی پارس نشود، استثنای صریح `ParseError` صادر می‌شود (عدم بازگرداندن خاموش لیست خالی).
     * پارسرهای وضعیت و کانفیگ اینترفیس در `interface.py` (رفع F-20):
       - بررسی وضعیت فیزیکی (`UP`, `DOWN`, `Administratively DOWN`) و وضعیت پروتکل.
       - ارزیابی کانفیگ جاری پورت: پاسخ خالی روتر به عنوان خطای `error='EMPTY_OUTPUT'` ثبت می‌شود (هرگز به عنوان "بدون کانفیگ" تلقی نمی‌شود).
       - شناسایی بنرهای خطای روتر (`Error:`, `Unrecognized command`).
       - تشخیص کانفیگ‌های بی‌اثر (Trivial) شامل صرفاً `dcn` یا `shutdown`.
     * پارسرهای لایسنس در `license.py` (رفع F-29):
       - بازنویسی به صورت ماشین حالت تمیز (State Machine).
       - انتساب انحصاری اقلام لایسنس به فیچر مربوطه و حذف قطعی ضرب دکارتی (F-29).
     * پارسرهای جدول مسیریابی و BGP VPNv4 در `routing.py`.
     * پارسرهای جداول ARP و MAC Address در `arp_mac.py`.
     * پارسر وضعیت همگام‌سازی پروتکل IEEE 1588 PTP در `ptp.py`.
  2. نگارش آزمون‌های جامع در [tests/test_step_3_3_parsers.py](file:///d:/Playground/Web-Dash/tests/test_step_3_3_parsers.py):
     * آزمون کورپوس گرامر اینترفیس روی بیش از ۴۰ نمونه واقعی آلارم‌های شبکه.
* **تأییدیه (Verify):**
  * اجرای ۳۵ آزمون تخصصی پارسرها با موفقیت کامل ۱۰۰٪ (`35 passed`).

---

### گام ۳.۴ و ۳.۵ و ۳.۶ — زیرسیستم تله‌متری Zabbix و Grafana بدون SNMP مستقیم (Steps 3.4, 3.5 & 3.6 Telemetry & NETCONF Hook)
* **هدف:** تجرید کامل مانیتورینگ تله‌متری از طریق APIهای Zabbix و Grafana، حذف کامل وابستگی به SNMP مستقیم و آماده‌سازی هوک NETCONF.
* **اقدامات انجام‌شده:**
  1. توسعه پکیج [backend/app/telemetry/](file:///d:/Playground/Web-Dash/backend/app/telemetry/):
     * مدل‌های تایپ‌شده تله‌متری در `models.py` (`TelemetryHost`, `TelemetryProblem`, `TelemetryItemValue`, `TelemetrySeries`, `TelemetryInterface`).
     * اینترفیس پایه `TelemetryProvider` در `base.py` با پیاده‌سازی `DisabledProvider` و `NullProvider`.
     * کش درون‌حافظه‌ای `TelemetryCache` در `cache.py` با قابلیت سرو داده‌های قدیمی در صورت قطعی مانیتورینگ (Stale-while-error).
     * کلاینت JSON-RPC 2.0 زبیکس در `zabbix.py`:
       - تشخیص خودکار نسخه زبیکس از طریق `apiinfo.version` و انتخاب احراز هویت `Bearer` در نسخه‌های جدید و `auth` در نسخه‌های قدیمی.
       - عدم تلاش مجدد برای خطاهای بیزینس JSON-RPC (رفع F-27).
       - مدارشکن ZabbixCircuitBreaker: در صورت ۵ خطای متوالی شبکه، مدار به مدت ۶۰ ثانیه باز می‌شود.
       - حل و فصل صحیح نوع داده هیستوری از طریق `item.value_type` و انتخاب خودکار بین `history.get` (برای بازه‌های کمتر از ۲۴ ساعت) و `trend.get` (برای بازه‌های بیش از ۲۴ ساعت).
       - ایزولاسیون کامل عملیات تغییر دهنده: تنها متد مجاز `ack_problem` بوده که نیازمند توکن دارای دسترسی نوشتن است.
     * کلاینت گرافانا در `grafana.py`:
       - تولید لینک‌های مستقیم و آدرس‌های امن تعبیه‌شده در iframe (`d-solo`) با تم و متغیرهای داینامیک بدون فاش کردن توکن برای مرورگر کاربر.
     * ماژول همگام‌سازی تجهیزات در `mapping.py`:
       - تطبیق روترهای دیتابیس با هاست‌های زبیکس بر اساس نام هاست، نام نمایشی و آی‌پی مدیریتی.
       - محافظت در برابر ابهام: در صورت وجود چند هاست مشابه در زبیکس، دستگاه به عنوان `ambiguous` علامت‌گذاری شده و هرگز به صورت خودکار منتسب نمی‌شود.
  2. تدوین سند مرجع رسمی تفکیک منابع داده در [docs/TELEMETRY_GUIDE.md](file:///d:/Playground/Web-Dash/docs/TELEMETRY_GUIDE.md) (گام ۳.۵).
  3. استاب هوک رابط NETCONF در [backend/app/devices/netconf.py](file:///d:/Playground/Web-Dash/backend/app/devices/netconf.py) به همراه فلگ `enable_netconf=False` در تنظیمات (گام ۳.۶).
  4. نگارش آزمون‌های خودکار در [tests/test_step_3_4_telemetry.py](file:///d:/Playground/Web-Dash/tests/test_step_3_4_telemetry.py).
* **تأییدیه (Verify):**
  * اجرای ۸ آزمون لایه تله‌متری با موفقیت ۱۰۰٪ (`8 passed`).
  * تایید عدم وجود هرگونه سوکت مستقیم SNMP یا پکیج `pysnmp` در کل مخزن کد.
  * اجرای سراسری کل ۱۵۸ تست خودکار پروژه: **۱۵۸ تست با موفقیت ۱۰۰٪ پاس شدند (`158 passed in 71.86s`).**

---

## فاز ۴: پایپ‌لاین تغییرات امن، پشتیبان‌گیری و تطبیق انطباق (Phase 4: Safe Change Pipeline)

### گام ۴.۱ — موتور پایپ‌لاین تغییرات و ماشین حالت (Step 4.1 Change Pipeline Engine & State Machine)
* **هدف:** پیاده‌سازی چرخه حیات و ترنزیشن‌های استاندارد تغییرات شبکه بر اساس الگوی قطعی **Plan → Pre-check → Approve → Apply → Verify → (Rollback)** و برچیدن رویکرد ارسال مستقیم و ناامن دستورات تغییر کانفیگ به روترها.
* **اقدامات انجام‌شده:**
  1. ارتقای مدل‌های پایگاه‌داده در [backend/app/models/config_change.py](file:///d:/Playground/Web-Dash/backend/app/models/config_change.py):
     * تعریف فیلدهای تخصصی برای `ChangeRequest` شامل `risk_level`, `creator_id`, `precheck_results`, `verification_results`, `snapshot_id` و متد استاندارد `to_dict()`.
  2. توسعه موتور پایپ‌لاین در [backend/app/jobs/change.py](file:///d:/Playground/Web-Dash/backend/app/jobs/change.py):
     * تعریف ماشین حالت قطعی `ChangeState`:
       - `PLANNED` -> `PRECHECKED` -> `AWAITING_APPROVAL` -> `APPLYING` -> `VERIFYING` -> `VERIFIED`.
       - انشعاب‌های امنیتی: `REJECTED`, `ROLLED_BACK`, `FAILED_NEEDS_ATTENTION`.
       - پشتیبانی از Rollback پس از تایید (`VERIFIED` -> `ROLLED_BACK`).
     * مدل ارزیابی ریسک (Risk Model):
       - سطح `low`: عملیات فقط خواندنی یا پاکسازی آلارم روی پورت‌های از قبل خاموش (قابلیت Auto-approve در صورت فعال بودن).
       - سطح `medium`: خاموش‌سازی اینترفیس‌های noconf تایید شده (نیازمند تایید نقش `admin` یا `god`).
       - سطح `high`: تغییرات گسترده مسیریابی، VRF، BGP، ترانک یا عبور از سقف شعاع انفجار (نیازمند تایید انحصاری `god`).
     * کنترل تفکیک وظایف (Separation of Duties): ممانعت از خود-تاییدی (`requester != approver`) برای تغییرات با ریسک بالاتر از low.
     * پشتیبانی از اجرای دسته‌ای (Batch Execution) با سقف خطای مجاز ۲۰٪ و بازگرداندن قطعی روتر به نمای کاربری با اجرای `return` در بلوک‌های `finally`.
  3. توسعه لایه REST API در [backend/app/api/changes.py](file:///d:/Playground/Web-Dash/backend/app/api/changes.py):
     * مسیرهای ثبت برنامه `POST /api/v1/changes/plan`، استعلام وضعیت `GET /api/v1/changes/{id}`، تصمیم‌گیری `POST /api/v1/changes/{id}/approve` و `reject`، اعمال `POST /api/v1/changes/{id}/apply`، و بازگردانی `POST /api/v1/changes/{id}/rollback`.
  4. نگارش آزمون‌های واحد و یکپارچگی در [tests/test_step_4_1_change_pipeline_skeleton.py](file:///d:/Playground/Web-Dash/tests/test_step_4_1_change_pipeline_skeleton.py).
* **تأییدیه (Verify):**
  * اجرای ۵ آزمون با موفقیت ۱۰۰٪، شامل اعتبارسنجی ممانعت از ترنزیشن‌های غیرمجاز، جلوگیری از اعمال مضاعف (Idempotency)، و اجرای قوانین تاییدیه.

---

### گام ۴.۲ — بازپیاده‌سازی ماژول پرچمدار پاکسازی آلارم و شات‌داون پورت‌های بدون کانفیگ (Step 4.2 Alarm Clear + Noconf Shutdown)
* **هدف:** جایگزینی کامل اسکریپت قدیمی `auto_clear_noconf.py` با یک هندلر امن در پایپ‌لاین تغییرات بر اساس جدول تصمیم‌گیری قطعی و رفع نواقص F-20, F-21, F-23, F-24.
* **اقدامات انجام‌شده:**
  1. توسعه هندلر `AlarmClearHandler` در [backend/app/jobs/handlers/alarm_clear.py](file:///d:/Playground/Web-Dash/backend/app/jobs/handlers/alarm_clear.py):
     * پیاده‌سازی جدول تصمیم‌گیری بدون ابهام:
       - در صورتی که اینترفیس `Administratively DOWN` باشد: صرفاً آلارم‌ها پاکسازی می‌شوند (ریسک `low`).
       - در صورتی که خروجی روتر خطا داشته باشد یا `EMPTY_OUTPUT` برگردد: توقف فوری و ثبت وضعیت `SKIP` با دلیل `CONFIG_UNREADABLE` (رفع قطعی نقص فاجعه‌بار F-20: جلوگیری از شات‌داون اشتباه اینترفیس‌های فعال به دلیل عدم پاسخگویی روتر).
       - در صورتی که اینترفیس دارای کانفیگ فراتر از کانفیگ‌های ناچیز، دارای توضیحات (Description)، عضو ترانک، والد ساب‌اینترفیس یا دارای آپ‌تایم خاموشی کمتر از ۶۰ دقیقه باشد: توقف با دلیل `HAS_CONFIG_OR_UP`.
       - در صورت احراز تمامی شرایط امنیتی noconf: برنامه‌ریزی `shutdown` با سطح ریسک `medium` و تعویق پاکسازی آلارم تا پس از موفقیت مرحله وریفای.
     * رفع نقص F-21: جداسازی آلارم‌های ساب‌اینترفیس‌ها؛ عملیات صرفاً بر روی همان ساب‌اینترفیس متمرکز شده و هرگز بر روی اینترفیس والد اعمال نمی‌شود.
     * رفع نقص F-23: تاییدیه پاکسازی آلارم منحصراً با تطابق الگوهای خروجی موفقیت هواوی؛ در صورت عدم وجود آلارم وضعیت `NOT_PRESENT` ثبت شده و هرگز به عنوان پاکسازی موفق شمرده نمی‌شود.
     * رفع نقص F-24: بررسی دسترسی به نمای آلارم (`alarm view`)؛ در صورت قفل بودن یا عدم دسترسی، جاب با وضعیت `ALARM_VIEW_UNAVAILABLE` متوقف شده و از ارسال دستورات اجتناب می‌شود.
     * تولید خروجی گزارش CSV با ساختار غنی و ردیابی کامل شناسه کار و تاییدکننده.
  2. نگارش آزمون‌های سناریوهای طلایی در [tests/test_step_4_2_alarm_clear_pipeline.py](file:///d:/Playground/Web-Dash/tests/test_step_4_2_alarm_clear_pipeline.py).
* **تأییدیه (Verify):**
  * اجرای ۵ آزمون تخصصی شامل خروجی خالی، ساب‌اینترفیس، پورت‌های ادمین داون، و سناریوی شکست وریفای و رول‌بک خودکار با موفقیت ۱۰۰٪.

---

### گام ۴.۳ — سرویس پشتیبان‌گیری، مقایسه تفاوت‌ها (Diff) و رمزنگاری کانفیگ (Step 4.3 Config Backup & Diff Service)
* **هدف:** ثبت خودکار و زمان‌بندی‌شده آخرین وضعیت کانفیگ روترها، کشف هوشمند تغییرات، رمزنگاری در حالت استراحت و مصورسازی تفاوت‌ها.
* **اقدامات انجام‌شده:**
  1. توسعه سرویس [backend/app/services/config_backup.py](file:///d:/Playground/Web-Dash/backend/app/services/config_backup.py):
     * نرمال‌سازی اختصاصی کانفیگ هواوی VRP: حذف تایم‌استمپ‌های متغیر سیستم، بنرهای صفحه‌بندی `---- More ----` و علائم پایانی.
     * جلوگیری از افزونگی رکوردهای مشابه (Deduplication): تولید هش SHA-256 و در صورت عدم تغییر، به‌روزرسانی فیلد `last_checked_at` بدون درج رکورد اضافی در دیتابیس.
     * رمزنگاری محتوا در حالت استراحت (Encryption at Rest) با استفاده از رمزنگاری متقارن Fernet بر پایه کلید والت محیط (`WEBDASH_VAULT_KEY`) جهت محافظت از کلمات عبور و رشته‌های SNMP در دیتابیس.
     * موتور مقایسه تفاوت‌ها (Diff Engine): تولید Unified Diff متنی استاندارد و آرایه‌ای از تکه‌های ساختاریافته (Structured Hunks) شامل متادیتا و شماره خطوط قبل و بعد.
     * سیاست ماندگاری و پاکسازی (Retention Policy): حفظ ۳۰ اسنپ‌شات آخر بعلاوه ۱ نسخه به ازای هر ماه در ۱۲ ماه گذشته (`prune_device_snapshots`).
  2. توسعه هندلر جاب `ConfigBackupHandler` در [backend/app/jobs/handlers/config_backup.py](file:///d:/Playground/Web-Dash/backend/app/jobs/handlers/config_backup.py).
  3. توسعه کنترلرهای REST در [backend/app/api/configs.py](file:///d:/Playground/Web-Dash/backend/app/api/configs.py) شامل دریافت لیست اسنپ‌شات‌ها، متن رمزگشایی‌شده، مقایسه دو نسخه و تریگر بکاپ فوری.
  4. نگارش آزمون‌های جامع در [tests/test_step_4_3_config_backup_and_diff.py](file:///d:/Playground/Web-Dash/tests/test_step_4_3_config_backup_and_diff.py).
* **تأییدیه (Verify):**
  * اجرای ۶ آزمون با موفقیت ۱۰۰٪ شامل نرمال‌سازی، حذف افزونگی هش، رمزنگاری/رمزگشایی، تولید دیف و پاکسازی اسنپ‌شات‌های قدیمی.

---

### گام ۴.۴ و ۴.۵ — تمدید لایسنس بر بستر پایپ‌لاین و موتور تطبیق قوانین انطباق (Step 4.4 License & Step 4.5 Compliance)
* **هدف:** مهاجرت تایید لایسنس به پایپ‌لاین امن، و راه‌اندازی موتور سنجش انطباق کانفیگ با سیاست‌های شبکه بر مبنای الگوی Policy as Data.
* **اقدامات انجام‌شده:**
  1. توسعه هندلر تمدید لایسنس در [backend/app/jobs/handlers/license_renewal.py](file:///d:/Playground/Web-Dash/backend/app/jobs/handlers/license_renewal.py):
     * تفکیک حالت پیش‌نمایش (Dry-run / Plan) جهت استخراج اطلاعات فایل لایسنس بدون تغییر روتر.
     * الزام تاییدیه مرحله‌ای قبل از بارگذاری فایل لایسنس به حافظه دائمی روتر.
     * اعتبارسنجی خودکار انقضای لایسنس بعد از فعال‌سازی با اجرای `display license` و مقایسه تاریخ انقضای جدید.
  2. پیاده‌سازی موتور تطبیق قوانین انطباق در [backend/app/services/compliance.py](file:///d:/Playground/Web-Dash/backend/app/services/compliance.py):
     * بارگذاری قوانین از فایل‌های پیکربندی YAML در دایرکتوری داده به همراه قواعد پیش‌فرض تعبیه‌شده:
       - `SEC-001`: غیرفعال بودن Telnet و الزام فعال بودن پروتکل امن SSH (`stelnet server enable`).
       - `OPS-001`: بررسی پیکربندی سرورهای ساعت شبکه (NTP unicast-server).
       - `SEC-002`: غیرفعال بودن SNMPv1/v2c و انطباق با نسخه امن SNMPv3 در کانفیگ روترها.
       - `OPS-002`: الزام به تعریف Description معنادار برای تمامی پورت‌های فیزیکی در وضعیت UP.
     * ارزیابی اسنپ‌شات‌های اخیر دستگاه‌ها، محاسبه امتیاز انطباق (Compliance Score)، صدور هشدار و ارائه راهنمای رفع نقص (Remediation Hint).
  3. نگارش آزمون‌های اعتبارسنجی در [tests/test_step_4_4_license_and_compliance.py](file:///d:/Playground/Web-Dash/tests/test_step_4_4_license_and_compliance.py).
* **تأییدیه (Verify):**
  * اجرای ۹ آزمون تخصصی لایسنس و قوانین انطباق با موفقیت ۱۰۰٪.

---

### گام ۴.۶ — گارد شعاع انفجار و تاییدیه ریسک بحرانی (Step 4.6 Blast-Radius Guard)
* **هدف:** جلوگیری از بروز خطای انسانی در تغییرات توده‌ای شبکه و الزام به تاییدیه دومنظوره سطح بالا برای تغییرات گسترده.
* **اقدامات انجام‌شده:**
  1. ارتقای متد `evaluate_risk` در [backend/app/jobs/change.py](file:///d:/Playground/Web-Dash/backend/app/jobs/change.py):
     * ارزیابی خودکار گستره تغییرات: در صورتی که تعداد روترهای هدف بیشتر از ۵۰ دستگاه (`MAX_DEVICES_PER_CHANGE`) یا تعداد اینترفیس‌های هدف روی یک دستگاه بیشتر از ۲۰ پورت (`MAX_INTERFACES_PER_DEVICE`) باشد:
       - سطح ریسک تغییرات به صورت اجباری به `high` تغییر می‌یابد.
       - پرچم `blast_radius_exceeded = True` ثبت می‌گردد.
  2. تقویت گیت تاییدیه در `approve_change`:
     * تایید تغییراتی که از شعاع انفجار عبور کرده‌اند منحصراً به کاربران با نقش `god` محدود می‌شود.
     * الزام ارسال رشته تاییدیه تایپ‌شده: `confirmation_token="I_CONFIRM_BLAST_RADIUS"`؛ در صورت عدم ارسال توکن یا ارسال توکن نادرست، درخواست تایید رد می‌شود (`BLAST_RADIUS_TOKEN_REQUIRED`).
  3. نگارش آزمون‌های ایمنی شعاع انفجار در [tests/test_step_4_6_blast_radius_and_regression.py](file:///d:/Playground/Web-Dash/tests/test_step_4_6_blast_radius_and_regression.py).
* **تأییدیه (Verify):**
  * اجرای ۹ آزمون تخصصی شامل ممانعت از تایید کاربران ادمین عادی، صحت‌سنجی توکن، ارزیابی سقف پورت‌ها و روترها با موفقیت ۱۰۰٪.
  * **اجرای رگرسیون سراسری کل پروژه:** اجرای تمامی ۱۹۵ آزمون خودکار در فازهای ۱ تا ۴: **۱۹۵ تست با موفقیت ۱۰۰٪ و بدون رگرسیون پاس شدند (`195 passed in 85.59s`).**

---

## فاز ۵ — کاتالوگ اتوماسیون و موتور گردش‌کار (Phase 5: Automation Catalog & Workflow Engine)

### گام ۵.۱ — کشف و شناسایی موجودی شبکه، مجموعه‌های هدف و بج‌های سلامت (Step 5.1 Inventory & Discovery)
* **هدف:** تبدیل Web-Dash به هاب اتوماسیون تخصصی تجهیزات هواوی VRP، مدیریت موجودی، گروه‌بندی و بج‌های سلامت.
* **اقدامات انجام‌شده:**
  1. توسعه متدهای درون‌ریزی CSV نام‌گذاری روترها بر پایه مشخصات `parse_csv_to_routers` با تفکیک تغییرات (Diff) در [backend/app/services/inventory.py](file:///d:/Playground/Web-Dash/backend/app/services/inventory.py).
  2. استخراج خودکار استان (`province`) و سایت (`site`) بر اساس الگوهای نام‌گذاری تجهیزات VRP هواوی (`_XXX`).
  3. پیاده‌سازی مدیریت گروه‌ها، برچسب‌ها و مجموعه‌های هدف ذخیره‌شده (`TargetSet`).
  4. محاسبه وضعیت سلامت روترها (`DeviceHealthBadge`) در حالت‌های `monitored_ok`, `ssh_ok`, `unreachable`, `auth_failed`, `not_in_zabbix`.
  5. ثبت قابلیت در کاتالوگ فیچرها (`InventoryDiscoveryFeature`) در [backend/app/features/inventory/](file:///d:/Playground/Web-Dash/backend/app/features/inventory/).
  6. نگارش آزمون‌های جامع در [tests/test_step_5_1_inventory_and_discovery.py](file:///d:/Playground/Web-Dash/tests/test_step_5_1_inventory_and_discovery.py).
* **تأییدیه (Verify):** پاس شدن ۹ تست از ۹ تست (`9 passed`).

---

### گام ۵.۲ — مرکز هشدارهای یکپارچه و آمار نویز (Step 5.2 Alarm Center)
* **هدف:** گردآوری هشدارهای فعال روترها، فیلترهای پیشرفته و آماده‌سازی درخواست‌های تغییر.
* **اقدامات انجام‌شده:**
  1. پارس هشدارهای فعال VRP از خروجی `display alarm active` و فیلتر بر اساس استان، سطح هشدار، اینترفیس و مدت زمان در [backend/app/services/alarm_center.py](file:///d:/Playground/Web-Dash/backend/app/services/alarm_center.py).
  2. ثبت فیلترهای ذخیره‌شده کاربر در جدول `alarm_filters`.
  3. تحلیل آماری نویز: محاسبه پرنویزترین روترها، هیستوگرام سنی هشدارها و توزیع سطوح خطر.
  4. برنامه‌ریزی درخواست‌های تغییر جهت پاکسازی یا خاموش‌سازی لینک‌های بدون کانفیگ از طریق پایپ‌لاین امن.
  5. نگارش آزمون‌ها در [tests/test_step_5_2_alarm_center.py](file:///d:/Playground/Web-Dash/tests/test_step_5_2_alarm_center.py).
* **تأییدیه (Verify):** پاس شدن ۷ تست از ۷ تست (`7 passed`).

---

### گام ۵.۳ — گزارش خطوط قطع، کشف تلاطم و مقایسه روزبه‌روز (Step 5.3 Down-Links Report & Analytics)
* **هدف:** پایش جامع لینک‌های قطع‌شده، تفکیک سرویس و بدون‌کانفیگ، کشف انفجار قطعی‌ها و خروجی چندزبانه Excel/CSV.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی مدل پایش در [backend/app/services/reporting.py](file:///d:/Playground/Web-Dash/backend/app/services/reporting.py) با حفظ فیلدهای استاندارد `FIELD_NAMES` و `TRUNK_FIELD_NAMES`.
  2. کشف پنجره‌های زمانی ۵ دقیقه‌ای تلاطم پورت‌ها (Burst Detection).
  3. مقایسه گزارش‌های روز جاری با روز قبل (Day-over-Day Diff) جهت کشف لینک‌های تازه قطع‌شده یا بهبودیافته.
  4. تولید فایل چندتب اکسل با استایل کامل (`openpyxl`) و فایل‌های CSV با انکودینگ UTF-8-SIG.
  5. نگارش آزمون‌ها در [tests/test_step_5_3_down_links_report.py](file:///d:/Playground/Web-Dash/tests/test_step_5_3_down_links_report.py).
* **تأییدیه (Verify):** پاس شدن ۸ تست از ۸ تست (`8 passed`).

---

### گام ۵.۴ — مدیریت لایسنس و مانیتورینگ روزهای باقی‌مانده (Step 5.4 License Management)
* **هدف:** ثبت وضعیت ناوگان لایسنس‌های هواوی، روزهای باقی‌مانده تا انقضا و هشدارهای چندسطحی.
* **اقدامات انجام‌شده:**
  1. ذخیره‌سازی داده‌های لایسنس در مدل `LicenseRecord` در [backend/app/models/license.py](file:///d:/Playground/Web-Dash/backend/app/models/license.py).
  2. دسته‌بندی هشدارهای انقضا بر اساس بازه‌های ۹۰، ۶۰، ۳۰ و ۷ روز مانده تا انقضا و لایسنس‌های منقضی‌شده.
  3. ارائه آمار استفاده از آیتم‌ها و فیچرهای هر تجهیز.
  4. نگارش آزمون‌ها در [tests/test_step_5_4_license_management.py](file:///d:/Playground/Web-Dash/tests/test_step_5_4_license_management.py).
* **تأییدیه (Verify):** پاس شدن ۹ تست از ۹ تست (`9 passed`).

---

### گام ۵.۵ — بررسی مسیریابی VRF و ترسیم گراف مسیر (Step 5.5 VRF / Routing Check)
* **هدف:** ردگیری مسیر هوپ‌به‌هوپ ترافیک درون VRF از مبدأ تا مقصد به همراه ساختار توپولوژی گراف مسیر.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی سرویس در [backend/app/services/routing.py](file:///d:/Playground/Web-Dash/backend/app/services/routing.py) بر پایه اعتبارسنجی دقیق نام VRF و آدرس IP.
  2. اجرای متد `transform_originator_ip` جهت اصلاح آدرس‌های Loopback و انطباق با جدول مسیریابی BGP.
  3. تولید ساختار گره‌ها (Nodes) و یال‌ها (Edges) برای نمایش بصری گراف مسیر در فرانت‌اند.
  4. نگارش آزمون‌ها در [tests/test_step_5_5_vrf_routing.py](file:///d:/Playground/Web-Dash/tests/test_step_5_5_vrf_routing.py).
* **تأییدیه (Verify):** پاس شدن ۸ تست از ۸ تست (`8 passed`).

---

### گام ۵.۶ — عیب‌یابی همگام‌سازی PTP و گراف توپولوژی ساعت (Step 5.6 PTP / Sync Troubleshoot)
* **هدف:** ردگیری گام‌به‌گام زنجیره ساعت پروتکل Precision Time Protocol (IEEE 1588v2) و تشخیص افت ساعت مرجع.
* **اقدامات انجام‌شده:**
  1. پارس خروجی‌های `display ptp all` و `display ptp trace` در [backend/app/services/ptp.py](file:///d:/Playground/Web-Dash/backend/app/services/ptp.py).
  2. تحلیل وضعیت Master/Slave/Passive پورت‌های PTP و تولید حکم تشخیصی (Verdict) درباره نقطه قطع شدن ساعت.
  3. نگارش آزمون‌ها در [tests/test_step_5_6_ptp_troubleshoot.py](file:///d:/Playground/Web-Dash/tests/test_step_5_6_ptp_troubleshoot.py).
* **تأییدیه (Verify):** پاس شدن ۶ تست از ۶ تست (`6 passed`).

---

### گام ۵.۷ — جستجوی ARP و MAC و جاب‌های پس‌زمینه (Step 5.7 ARP / MAC Lookup)
* **هدف:** جستجوی فوق‌سریع آدرس‌های فیزیکی و مک‌ادرس بر مبنای کد سایت، جاب‌های جمع‌آوری پس‌زمینه و کش TTL.
* **اقدامات انجام‌شده:**
  1. پارس و نرمال‌سازی فرمت مک‌ادرس‌ها به استاندارد استاندارد چهاربخشی هواوی (`xxxx-xxxx-xxxx`).
  2. ایجاد جاب‌های پس‌زمینه جمع‌آوری اطلاعات با امکان لغو آنی بدون قفل شدن سشن‌های شبکه.
  3. کش هوشمند نتایج با برچسب تازگی داده‌ها (Data Freshness).
  4. نگارش آزمون‌ها در [tests/test_step_5_7_arp_mac_lookup.py](file:///d:/Playground/Web-Dash/tests/test_step_5_7_arp_mac_lookup.py).
* **تأییدیه (Verify):** پاس شدن ۸ تست از ۸ تست (`8 passed`).

---

### گام ۵.۸ — استخراج نشست‌های SecureCRT بدون ذخیره سکرت‌ها (Step 5.8 Session Extractor)
* **هدف:** تولید پکیج فایل‌های کانفیگ SecureCRT با رعایت الزامات امنیتی سفت‌وسخت عدم افشای کلمات عبور.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی متدهای ساختار پوشه‌بندی و پاکسازی نام فایل‌ها در [backend/app/services/session_extractor.py](file:///d:/Playground/Web-Dash/backend/app/services/session_extractor.py).
  2. ممیزی امنیتی خروجی‌ها و حذف کامل فیلد پسورد از فایل‌های `.ini` (به‌کارگیری شیوه Prompt on Connect یا SSH Key).
  3. ایجاد فشرده‌سازی ZIP با انکودینگ UTF-8 استاندارد.
  4. نگارش آزمون‌ها در [tests/test_step_5_8_session_extractor.py](file:///d:/Playground/Web-Dash/tests/test_step_5_8_session_extractor.py).
* **تأییدیه (Verify):** پاس شدن ۸ تست از ۸ تست (`8 passed`).

---

### گام ۵.۹ — هاب مانیتورینگ: زبیکس، سلامت ناوگان و گرافانا (Step 5.9 Monitoring Hub)
* **هدف:** یکپارچگی شفاف با Zabbix و Grafana، داشبورد سلامت ناوگان و ادغام رویدادهای زبیکس با هشدارهای SSH.
* **اقدامات انجام‌شده:**
  1. اتصال به ارائه‌دهنده تله‌متری زبیکس بدون نیاز به نشست‌های سنگین SSH در [backend/app/services/monitoring.py](file:///d:/Playground/Web-Dash/backend/app/services/monitoring.py).
  2. تولید لینک‌های عمیق (Deep Links) داشبوردهای گرافانا به ازای هر اینترفیس.
  3. دریافت وبهوک‌های سامانه مانیتورینگ و تجمیع هشدارهای زبیکس با آلارم‌های فعال روترها.
  4. نگارش آزمون‌ها در [tests/test_step_5_9_monitoring_hub.py](file:///d:/Playground/Web-Dash/tests/test_step_5_9_monitoring_hub.py).
* **تأییدیه (Verify):** پاس شدن ۸ تست از ۸ تست (`8 passed`).

---

### گام ۵.۱۰ — پشتیبان‌گیری، دیف و داشبورد انطباق ناوگان (Step 5.10 Config Backup, Diff & Compliance)
* **هدف:** مشاهده تایم‌لاین تغییرات کانفیگ روترها، همبستگی با جاب‌های انجام‌شده و محاسبه درصد انطباق ناوگان.
* **اقدامات انجام‌شده:**
  1. یکپارچه‌سازی متدهای مقایسه تفاوت‌های کانفیگ با سابقه جاب‌ها و درخواست‌های تغییر در [backend/app/api/configs.py](file:///d:/Playground/Web-Dash/backend/app/api/configs.py).
  2. داشبورد انطباق ناوگان بر اساس قوانین تعریف‌شده در [backend/app/services/compliance.py](file:///d:/Playground/Web-Dash/backend/app/services/compliance.py).
  3. ارائه آمار انطباق به تفکیک استان و قوانین فعال.
  4. نگارش آزمون‌ها در [tests/test_step_5_10_config_compliance.py](file:///d:/Playground/Web-Dash/tests/test_step_5_10_config_compliance.py).
* **تأییدیه (Verify):** پاس شدن ۱۱ تست از ۱۱ تست (`11 passed`).

---

### گام ۵.۱۱ — اجرای دسته‌ای دستورات با اعتبارسنجی Read-Only (Step 5.11 Command Runner)
* **هدف:** اجرای همزمان دستورات نمایشی مجاز بر روی چند روتر، فیلتر خروجی با Regex و تولید گزارش خروجی.
* **اقدامات انجام‌شده:**
  1. تعریف لیست سفید دستورات مجاز (`read_only: True`) و انسداد هرگونه دستور تغییردهنده در [backend/app/services/command_runner.py](file:///d:/Playground/Web-Dash/backend/app/services/command_runner.py).
  2. پشتیبانی از قالب‌های Jinja2 جهت پارامتریک‌سازی ایمن دستورات.
  3. جستجوی پیشرفته متن و عبارات باقاعده در خروجی تجهیزات و ذخیره سابقه در جدول جاب‌ها.
  4. نگارش آزمون‌ها در [tests/test_step_5_11_command_runner.py](file:///d:/Playground/Web-Dash/tests/test_step_5_11_command_runner.py).
* **تأییدیه (Verify):** پاس شدن ۸ تست از ۸ تست (`8 passed`).

---

### گام ۵.۱۲ — زمان‌بندی با لیدری لیس دیتابیس و اعلان‌های چندکاناله (Step 5.12 Scheduler & Notifications)
* **هدف:** زمان‌بندی دقیق جاب‌های دوره‌ای با کرون استاندارد، انتخاب یک رهبر واحد (Single-Leader Lease) در دیتابیس و ارسال اعلان‌ها.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی مدل `SchedulerLease` و مکانیزم انتخاب رهبر با انقضای لیس زمانی در [backend/app/jobs/scheduler.py](file:///d:/Playground/Web-Dash/backend/app/jobs/scheduler.py).
  2. اعتبارسنجی دقیق بازه‌های ۵ فیلد کرون در متد `validate_cron_expression`.
  3. جلوگیری از اجرای تکراری در یک دقیقه و تضمین اجرای وظایف فقط توسط نود لیدر.
  4. توسعه سرویس اعلان‌های چندکاناله [backend/app/services/notifications.py](file:///d:/Playground/Web-Dash/backend/app/services/notifications.py) با پشتیبانی از Webhook، ایمیل SMTP و Syslog برای رخدادهای شکست جاب، تاییدیه تغییر، انقضای لایسنس، تلاطم پورت و افت انطباق.
  5. نگارش آزمون‌ها در [tests/test_step_5_12_scheduler_notifications.py](file:///d:/Playground/Web-Dash/tests/test_step_5_12_scheduler_notifications.py).
* **تأییدیه (Verify):** پاس شدن ۸ تست از ۸ تست (`8 passed`).

---

### گام ۵.۱۳ — سیستم گزارش‌دهی یکپارچه، استریمینگ و دایجست روزانه NOC (Step 5.13 Reporting & Exports)
* **هدف:** توسعه سرویس صادرات داده‌ها با استریمینگ داده‌های بزرگ، قالب‌بندی چندزبانه و گزارش دایجست روزانه عملیات شبکه.
* **اقدامات انجام‌شده:**
  1. توسعه سرویس صادرات داده [backend/app/services/export_service.py](file:///d:/Playground/Web-Dash/backend/app/services/export_service.py):
     * پشتیبانی از فرمت‌های CSV (همراه با انکودینگ UTF-8-SIG و کاراکتر BOM جهت خوانایی فارسی در اکسل).
     * استریمینگ خط‌به‌خط بدون مصرف بی‌رویه حافظه رم برای فایل‌های بزرگ (`stream_csv`).
     * ایجاد کتاب‌های چندبرگی اکسل با استایل حرفه‌ای هدرها و تنظیم خودکار عرض ستون‌ها (`export_xlsx`).
     * سریال‌سازی پیشرفته JSON برای انواع داده‌های تاریخ، زمان، UUID و Decimal.
  2. توسعه سرویس دایجست روزانه [backend/app/services/noc_digest.py](file:///d:/Playground/Web-Dash/backend/app/services/noc_digest.py):
     * تجمیع سلامت شبکه از رویدادها، خطوط قطع، لایسنس‌ها، جاب‌های ناموفق و درصد انطباق ناوگان.
     * صدور وضعیت نهایی سلامت ناوگان (`HEALTHY`, `ATTENTION_NEEDED`, `CRITICAL`).
  3. ایجاد فیچر کاتالوگ `reporting_digest` و کنترلرهای REST در [backend/app/api/reports.py](file:///d:/Playground/Web-Dash/backend/app/api/reports.py).
  4. نگارش آزمون‌ها در [tests/test_step_5_13_reporting_exports.py](file:///d:/Playground/Web-Dash/tests/test_step_5_13_reporting_exports.py).
* **تأییدیه (Verify):** پاس شدن ۸ تست از ۸ تست (`8 passed`).

---

### گام ۵.۱۴ — توکن‌های امن API، سند OpenAPI 3.0 و کلاینت CLI (Step 5.14 Public API & CLI)
* **هدف:** ارائه API عمومی سازمانی، مدیریت توکن‌های هش‌شده و تاریخ‌دار، مستندسازی تعاملی و ابزار خط فرمان `webdash-cli`.
* **اقدامات انجام‌شده:**
  1. ایجاد مدل `ApiToken` در [backend/app/models/api_token.py](file:///d:/Playground/Web-Dash/backend/app/models/api_token.py) با ذخیره هش SHA-256 و نگهداری پیشوند ایمن.
  2. توسعه سرویس [backend/app/services/tokens.py](file:///d:/Playground/Web-Dash/backend/app/services/tokens.py) شامل تولید توکن‌های `wbd_...`، اعتبارسنجی اسکوپ، ردیابی `last_used_at` و باطل‌سازی.
  3. ارتقای میدلور امنیتی در [backend/app/security/middleware.py](file:///d:/Playground/Web-Dash/backend/app/security/middleware.py) جهت پشتیبانی از هدر `Authorization: Bearer wbd_...` بدون نیاز به کوکی مرورگر یا توکن CSRF.
  4. تدوین استاندارد OpenAPI 3.0.3 در [backend/app/api/openapi_spec.py](file:///d:/Playground/Web-Dash/backend/app/api/openapi_spec.py) و ارائه اندپوینت‌های `/api/v1/openapi.json` و رابط گرافیکی Swagger UI در `/api/v1/docs`.
  5. توسعه ابزار خط فرمان مستقل و فاقد وابستگی خارجی در [scripts/webdash_cli.py](file:///d:/Playground/Web-Dash/scripts/webdash_cli.py) برای لیست روترها، اجرای جاب‌ها، انتظار تا اتمام و دریافت دایجست.
  6. نگارش آزمون‌ها در [tests/test_step_5_14_public_api_cli.py](file:///d:/Playground/Web-Dash/tests/test_step_5_14_public_api_cli.py).
* **تأییدیه (Verify):**
  * اجرای ۸ تست تخصصی با موفقیت ۱۰۰٪ (`8 passed`).
  * **اجرای رگرسیون کامل فاز ۵ (گام‌های ۵.۱ تا ۵.۱۴):** **۱۱۴ تست با موفقیت ۱۰۰٪ و بدون رگرسیون پاس شدند (`114 passed in 89.25s`).**

---

## فاز ۶ — سیستم طراحی و زیرساخت فرانت‌اند (Phase 6: Frontend Foundation & Design System)

### گام ۶.۱ — ساختار اولیه و اسکلت فرانت‌اند مدرن (Step 6.1 Scaffold)
* **هدف:** راه‌اندازی پروژه فرانت‌اند مدرن با React 18، TypeScript Strict، Vite، Tailwind CSS و قراردادهای سیستم طراحی NOC مناسب برای استقرار در محیط‌های ایزوله و آفلاین (Air-Gapped).
* **اقدامات انجام‌شده:**
  1. راه‌اندازی پروژه مستقل در پوشه [frontend/package.json](file:///d:/Playground/Web-Dash/frontend/package.json) شامل اسکریپت‌های استاندارد `dev`, `build`, `typecheck`, `lint`, `test`.
  2. اعمال پیکربندی تایپ‌اسکریپت سخت‌گیرانه (`strict: true`) و الیاس مسیر (`@/*`) در [frontend/tsconfig.json](file:///d:/Playground/Web-Dash/frontend/tsconfig.json).
  3. پیکربندی پروکسی توسعه Vite برای هدایت درخواست‌های `/api` به سرور محلی فلسک (`http://localhost:5000`) و تفکیک چانک‌های خروجی در [frontend/vite.config.ts](file:///d:/Playground/Web-Dash/frontend/vite.config.ts).
  4. پیاده‌سازی سیستم توکن‌های طراحی (تم‌های Paper / Night) و متغیرهای چگالی (Compact / Comfortable) در [frontend/src/styles/tokens.css](file:///d:/Playground/Web-Dash/frontend/src/styles/tokens.css) و اتصال آن به [frontend/tailwind.config.js](file:///d:/Playground/Web-Dash/frontend/tailwind.config.js).
  5. فراهم‌سازی قابلیت استقرار در سرورهای ایزوله (Air-Gapped): پوشه کامپایل‌شده `frontend/dist/` به صورت یک بسته مستقل از اینترنت آماده شده و در گیت ترک می‌شود تا در سرور نیازی به نصب Node.js یا اجرای npm نباشد.
  6. نگارش آزمون‌های خودکار در [tests/test_step_6_1_scaffold.py](file:///d:/Playground/Web-Dash/tests/test_step_6_1_scaffold.py).
* **تأییدیه (Verify):**
  * اجرای موفق `npm run typecheck` و `npm run lint` با صفر خطا و هشدار.
  * اجرای آزمون واحد کامپوننت با Vitest با ۱ پاس (`1 passed`).
  * اجرای `npm run build` و تولید باندل با حجم اولیه ۴۸ کیلوبایت (بسیار کمتر از سقف بودجه ۲۵۰ کیلوبایت).
  * اجرای آزمون‌های پایتون: ۵ تست از ۵ تست پاس شدند (`5 passed in 0.14s`).

---

### گام ۶.۲ — کلاینت API، نگاشت خطاها، پوسته احراز هویت و گاردهای دسترسی (Step 6.2 API Client & Auth Shell)
* **هدف:** پیاده‌سازی کلاینت HTTP استاندارد و تایپ‌شده برای ارتباط فرانت‌اند با APIهای سامانه، تزریق خودکار هدر امنیتی `X-CSRF-Token`، نگاشت دقیق خطاهای بک‌اند بر اساس مشخصات معماری به کلاس خطای `ApiError`، مدیریت انقضای سشن (401) و تغییر اجباری رمز (403 PASSWORD_CHANGE_REQUIRED)، پیکربندی تنظیمات بهینه TanStack Query برای اتاق مانیتورینگ NOC، ایجاد مخزن وضعیت احراز هویت با Zustand، ساخت صفحات ورود و تغییر رمز با استایل صنعتی، و پیاده‌سازی گاردهای مسیر و پوسته اصلی نرم‌افزار.
* **اقدامات انجام‌شده:**
  1. پیاده‌سازی کلاینت HTTP در [frontend/src/api/client.ts](file:///d:/Playground/Web-Dash/frontend/src/api/client.ts) و تعاریف تایپ در [frontend/src/api/types.ts](file:///d:/Playground/Web-Dash/frontend/src/api/types.ts):
     - تابع `request<T>` و متدهای کمکی `apiClient.get/post/put/patch/delete` با الزام بر ارتباط JSON و ارسال کوکی سشن (`credentials: 'same-origin'`).
     - تزریق خودکار هدر امنیتی `X-CSRF-Token` در کلیه متدهای تغییردهنده داده (`POST`, `PUT`, `DELETE`, `PATCH`).
     - تبدیل انواع خطاهای سرور (RFC 7807، خطاهای اعتبارسنجی فیلد، و پیام‌های استاتیک) به نمونه کلاس `ApiError` شامل کد خطا، پیام، و لیست فیلدهای نامعتبر.
     - مدیریت خطای 401 و ارسال رویداد `webdash:auth:unauthorized` جهت هدایت به صفحه ورود با حفظ مسیر بازگشت (`returnUrl`).
     - مدیریت خطای 403 با کد `PASSWORD_CHANGE_REQUIRED` و ارسال رویداد `webdash:auth:password-change-required`.
     - پیکربندی کلاینت سراسری TanStack Query: زمان کش اولیه ۱۵ ثانیه (`staleTime: 15_000`)، ممانعت قطعی از تلاش مجدد روی کدهای خطای کلاینت 4xx، و تلاش مجدد ۱ باره فقط برای خطاهای 5xx یا شبکه.
  2. ایجاد مخزن وضعیت نشست و کاربران با Zustand در [frontend/src/store/auth.ts](file:///d:/Playground/Web-Dash/frontend/src/store/auth.ts):
     - متدهای `checkAuth` (استعلام وضعیت از `/api/v1/me`)، `login`، `logout`، و `changePassword`.
     - گوش دادن خودکار به رویدادهای سراسری کلاینت برای پاکسازی نشست و نمایش بنر انقضای نشست پس از ۳۰ دقیقه عدم فعالیت (`idleTimeoutNotice`).
  3. ساخت کامپوننت‌های امنیتی و پوسته کنسول:
     - گارد محافظت از مسیرها [frontend/src/components/auth/ProtectedRoute.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/auth/ProtectedRoute.tsx): بررسی احراز هویت و هدایت به `/login` یا الزام تغییر رمز موقت به `/change-password`.
     - گارد دسترسی [frontend/src/components/auth/PermissionGate.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/auth/PermissionGate.tsx): کنترل دسترسی بر اساس سطح نقش کاربر (`god`, `admin`, `operator`, `viewer`) و پرچم فیچرهای فعال.
     - مودال اطلاع‌رسانی انقضای نشست [frontend/src/components/auth/IdleTimeoutNotice.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/auth/IdleTimeoutNotice.tsx) مبتنی بر Radix Dialog.
     - پوسته کنسول NOC در [frontend/src/components/layout/Shell.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/layout/Shell.tsx): نوار بالایی با نشانگر سلامت سیستم، تگ فقط‌خواندنی، مشخصات کاربر، دکمه خروج و پنل محتوایی بدون اسکرول سراسری بدنه.
  4. پیاده‌سازی صفحات کاربری:
     - صفحه ورود [frontend/src/pages/Login.tsx](file:///d:/Playground/Web-Dash/frontend/src/pages/Login.tsx): طراحی دقیق ابزارگونه مطابق توکن‌های طراحی، فرم لاگین با پشتیبانی از نمایش قفل شدن حساب در اثر ارسال زیاد رمز اشتباه (HTTP 429).
     - صفحه تغییر رمز [frontend/src/pages/ChangePassword.tsx](file:///d:/Playground/Web-Dash/frontend/src/pages/ChangePassword.tsx): فرم به‌روزرسانی رمز با چک‌لیست شرایط سیاست رمز عبور.
     - داشبورد عملیات [frontend/src/pages/Dashboard.tsx](file:///d:/Playground/Web-Dash/frontend/src/pages/Dashboard.tsx): نمایش کارت‌های خلاصه وضعیت و تست عملکرد PermissionGate.
  5. هماهنگی اندپوینت‌های احراز هویت بک‌اند:
     - ثبت الیاس پیشوند `/api/v1` برای `auth_bp` در [backend/app/__init__.py](file:///d:/Playground/Web-Dash/backend/app/__init__.py).
     - معافیت اندپوینت لاگین از بررسی CSRF و درج مسیرهای `/api/v1/...` در لیست معافیت‌های تغییر رمز در [backend/app/security/middleware.py](file:///d:/Playground/Web-Dash/backend/app/security/middleware.py).
  6. کامپایل نهایی و آزمون‌های خودکار:
     - نگارش تست‌های Vitest در [frontend/src/api/client.test.ts](file:///d:/Playground/Web-Dash/frontend/src/api/client.test.ts) و [frontend/src/store/auth.test.ts](file:///d:/Playground/Web-Dash/frontend/src/store/auth.test.ts) (مجموعاً ۱۸ تست).
     - نگارش تست‌های یکپارچگی در [tests/test_step_6_2_api_client_auth.py](file:///d:/Playground/Web-Dash/tests/test_step_6_2_api_client_auth.py).
     - بازسازی خروجی پروداکشن `frontend/dist/` و ترک آن در گیت برای سرورهای ایزوله (Air-Gapped).
* **تأییدیه (Verify):**
  * اجرای `npm run typecheck` و `npm run lint` با ۰ خطا و ۰ اخطار.
  * پاس شدن ۱۰۰٪ آزمون‌های Vitest با ۱۸ تست پاس‌شده (`18 passed in 3.56s`).
  * اجرای آزمون‌های پایتون: ۵ تست از ۵ تست پاس شدند (`5 passed in 16.01s`).
  * حجم باندل اولیه: ~۸۱ کیلوبایت Gzip (کمتر از یک‌سوم بودجه مجاز ۲۵۰ کیلوبایت).

---

### گام ۶.۳ — سیستم توکن‌ها، تم‌بندی، چگالی، و دوزبانه بودن با فونت‌های آفلاین (Step 6.3 Tokens, Theming, Density & Bilingual i18n)
* **هدف:** پیاده‌سازی سیستم کامل تم‌های بصری (Paper / Night / System)، حالت‌های چگالی نمایش (Compact / Comfortable)، دوزبانه بودن جامع فارسی و انگلیسی با چرخش بلادرنگ جهت صفحه (RTL/LTR)، بارگذاری فونت‌های سازمانی آفلاین (Vazirmatn، IBM Plex Sans، JetBrains Mono) با فرمت استاندارد WOFF2 بدون نیاز به اینترنت، و ذخیره‌سازی ترجیحات کاربر در `localStorage` تحت کلید `wd.prefs`.
* **اقدامات انجام‌شده:**
  1. تولید و بارگذاری فونت‌های محلی استاندارد:
     - استقرار فایل‌های فونت معتبر WOFF2 در [frontend/public/fonts/](file:///d:/Playground/Web-Dash/frontend/public/fonts) شامل `vazirmatn.woff2`، `ibm-plex-sans.woff2` و `jetbrains-mono.woff2`.
     - تعریف قوانین `@font-face` همراه با `font-display: swap` در [frontend/src/styles/tokens.css](file:///d:/Playground/Web-Dash/frontend/src/styles/tokens.css) و تضمین صفر ریکوئست خارجی به اینترنت (کاملاً سازگار با شبکه ایزوله Air-Gapped).
  2. مدیریت ترجیحات کاربری در [frontend/src/store/prefs.ts](file:///d:/Playground/Web-Dash/frontend/src/store/prefs.ts):
     - نگهداری کلید `wd.prefs` در `localStorage`.
     - انتخاب و سوئیچ تم: تیره (Night)، روشن (Paper) یا خودکار (System) با اعمال ویژگی `data-theme` و کلاس `dark` روی المان ریشه `<html>`.
     - انتخاب و سوئیچ چگالی: فشرده (Compact با ارتفاع سطر ۲۸ پیکسل) و معمولی (Comfortable با ارتفاع ۳۶ پیکسل) با متغیرهای اختصاصی CSS.
     - انتخاب زبان و جهت نوشتار: انگلیسی (LTR) و فارسی (RTL) با اعمال ویژگی‌های `lang` و `dir` روی المان `<html>`.
  3. بومی‌سازی و چندزبانه بودن با `react-i18next`:
     - پیکربندی هسته ترجمه در [frontend/src/i18n/config.ts](file:///d:/Playground/Web-Dash/frontend/src/i18n/config.ts).
     - فایل‌های دیکشنری جامع [frontend/src/i18n/locales/en.json](file:///d:/Playground/Web-Dash/frontend/src/i18n/locales/en.json) و [frontend/src/i18n/locales/fa.json](file:///d:/Playground/Web-Dash/frontend/src/i18n/locales/fa.json) با تطابق ۱۰۰٪ کلیدها در بخش‌های `common`, `prefs`, `auth`, `dashboard`.
     - به‌کارگیری تابع `useTranslation()` در تمامی کامپوننت‌ها و صفحات (`Shell`, `Login`, `ChangePassword`, `Dashboard`, `IdleTimeoutNotice`, `ProtectedRoute`).
     - قرارگیری اعداد، IPها، نام اینترفیس‌ها، دستورات CLI و خروجی لاگ‌ها در حالت ایزوله LTR (`dir-ltr`, `unicode-bidi: isolate`).
  4. کنترل‌های بالای صفحه (Top Bar Controls) در [frontend/src/components/layout/Shell.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/layout/Shell.tsx):
     - دکمه تغییر تم (Paper ☀️ / Night 🌙).
     - دکمه تغییر چگالی (Compact ↕️ / Comfortable).
     - دکمه تغییر زبان (FA / EN) همراه با چرخش بلادرنگ چیدمان به RTL.
  5. نگارش آزمون‌های خودکار و کامپایل:
     - آزمون‌های واحد فرانت‌اند در [frontend/src/store/prefs.test.ts](file:///d:/Playground/Web-Dash/frontend/src/store/prefs.test.ts) و [frontend/src/i18n/config.test.ts](file:///d:/Playground/Web-Dash/frontend/src/i18n/config.test.ts) (مجموعاً ۲۷ تست پاس‌شده).
     - نگارش آزمون‌های اختصاصی پایتون در [tests/test_step_6_3_tokens_theming_i18n.py](file:///d:/Playground/Web-Dash/tests/test_step_6_3_tokens_theming_i18n.py) (۵ تست).
     - بیلد نهایی در `frontend/dist/` با کپی خودکار فونت‌ها به `dist/fonts/` و حجم باندل اولیه ۱۰۱ کیلوبایت Gzip.
---

### گام ۶.۴ — کامپوننت‌های هسته NOC، ابزارهای نمایش داده و روت آزمایشگاهی Kitchen Sink (Step 6.4 Core NOC Components & Kitchen Sink Route)
* **هدف:** پیاده‌سازی کلیه کامپوننت‌های استاندارد و ابزارگونه کنسول عملیات شبکه (NOC) مطابق قرارداد طراحی `plan/08_PHASE6_UI_DESIGN_SYSTEM.md` §5.4، شامل جدول مجازی‌سازی‌شده داده‌ها، استریم و مشاهده‌گر لاگ‌ها، تایم‌لاین بصری اجرای جاب‌ها (Run Timeline)، مقایسه‌گر کانفیگ (Diff Viewer)، گراف توپولوژی شبکه، نمودار سری‌های زمانی uPlot، پنل گرافانا با کارت فال‌بک، و ساخت روت کارگاهی زنده `/_ui` (Kitchen Sink) جهت بررسی تعاملی و آزمون‌های خودکار.
* **اقدامات انجام‌شده:**
  1. **جدول داده‌های پرتراکم مجازی‌سازی‌شده ([frontend/src/components/datatable/DataTable.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/datatable/DataTable.tsx)):**
     - بهره‌گیری از ترکیب `@tanstack/react-table` و `@tanstack/react-virtual` با ارتفاع سطر مبتنی بر چگالی (۲۸ پیکسل در حالت Compact و ۳۶ پیکسل در Comfortable) و قابلیت رندر بیش از ۱۰,۰۰۰ سطر با نرخ فریم ۶۰ fps.
     - پشتیبانی از فیلتر سراسری، مرتب‌سازی چندستونه، پاپ‌اور انتخاب و پنهان‌سازی ستون‌ها، انتخاب سطرها و خروجی اکسپورت CSV از نمای فیلترشده جاری.
  2. **مشاهده‌گر و استریم لاگ‌های عملیاتی ([frontend/src/components/logviewer/LogViewer.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/logviewer/LogViewer.tsx)):**
     - پشتیبانی از رندر تا ۲۰۰,۰۰۰ خط لاگ با مجازی‌سازی دقیق، نمایش ایزوله LTR، برچسب‌های مونو برای نام تجهیزات و رنگ‌بندی سمانتیک سطوح لاگ (INFO، WARN، ERROR، DEBUG).
     - کلید فعال‌سازی تعقیب خودکار انتهای لاگ (Follow Tail)، جستجوی بلادرنگ در پیام‌ها و تجهیزات، فیلتر سطحی و دکمه‌های کپی و دانلود فایل لاگ.
  3. **هوک ارتباطی Server-Sent Events ([frontend/src/components/logviewer/useJobEvents.ts](file:///d:/Playground/Web-Dash/frontend/src/components/logviewer/useJobEvents.ts)):**
     - ارتباط مقاوم با سرور از طریق هدر `Last-Event-ID` برای بازپخش رویدادهای از دست رفته در زمان قطعی موقت.
     - الگوریتم اتصال مجدد نمایی (Exponential Backoff) و حذف رویدادهای تکراری (Deduplication) بر اساس شناسه رویداد.
  4. **شناور اجرای جاب‌ها — عنصر برجسته بصری سامانه ([frontend/src/components/timeline/RunTimeline.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/timeline/RunTimeline.tsx)):**
     - ردیف‌های نمایانگر هر روتر و ستون‌های نمایانگر مراحل پایپ‌لاین (اتصال → پیش‌بررسی → پلن دیف → اعمال کانفیگ → اعتبارسنجی).
     - نمادهای بصری پیشرفت (Queued، Running با اسپینر ظریف، Succeeded، Failed و Skipped) همراه با جزئیات خطا و مدت زمان اجرا در تولتیپ.
     - چیدمان اولویت‌دار "نیاز به توجه فوری" (Attention First: شکست‌خورده‌ها و موارد در حال اجرا بالاتر از موفق‌ها) با قابلیت سوییچ به الفبایی، فیلتر سریع و مجازی‌سازی برای ۱,۰۰۰ روتر.
  5. **مشاهده‌گر تغییرات کانفیگ روتر ([frontend/src/components/diff/DiffViewer.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/diff/DiffViewer.tsx)):**
     - محاسبه و تفکیک تغییرات با کتابخانه `diff` و رندرر بومی اختصاصی با پشتیبانی از دو حالت نمایشی یکپارچه (Unified) و ستونی (Split / Side-by-Side).
     - شماره‌گذاری سطور، هایلایت تفکیکی کلمات تغییریافته، آمار تعداد سطور افزوده و حذف‌شده، و دکمه کپی پچ کانفیگ.
  6. **اتم‌های رابط کاربری و تعاملات هسته NOC ([frontend/src/components/ui/](file:///d:/Playground/Web-Dash/frontend/src/components/ui/)):**
     - `StatusBadge` و `HealthDot`: نمایش سمانتیک وضعیت با برچسب و آیکون و شمارنده (عدم تکیه به رنگ تنها).
     - `Timestamp`: نمایش زمان نسبی خودکار (مانند "2m ago") همراه با ساعت دقیق ۲۴ ساعته UTC در هاور.
     - `Mono` و `MonoChip` و `CliOutput`: تراشه‌های کپی‌شونده برای IP، پورت و شماره AS در جهت LTR ایزوله.
     - `ConfirmDialog`: دیالوگ تأیید عملیات‌های حساس با الزام به تایپ دقیق مقدار (مانند تایپ تعداد روترها "12").
     - `Drawer`، `Tabs`، `TimeRangePicker` (بازه ۱۵ دقیقه تا ۷ روز) و `Toast` (سیستم اعلان با اعلامیه صوتی `aria-live`).
     - `CommandPalette`: پالت جستجو و اجرای سریع دستورات با کلید میانبر سراسری `Ctrl+K` مبتنی بر `cmdk`.
  7. **گراف‌ها و تلکتری ([frontend/src/components/charts/](file:///d:/Playground/Web-Dash/frontend/src/components/charts/)):**
     - `TimeSeriesChart`: بسته‌بندی سبک و پرسرعت کتابخانه `uPlot` با پشتیبانی از چندسری داده، خطوط خطی و پله‌ای، کراس‌هیر متقاطع و ایجاد گپ بصری روی دیتای ناموجود/گمشده.
     - `TopologyGraph`: نقشه تعاملی شبکه مبتنی بر `@xyflow/react` با چیدمان لایه‌ای خودکار (Core → Aggregation → Edge)، وضعیت سلامت روترها و برچسب اینترفیس‌های لینک.
     - `GrafanaPanel`: تعبیه فریم تلکتری با قابلیت تشخیص تایم‌اوت و نمایش خودکار کارت فال‌بک NOC همراه با دکمه "Open in Grafana".
  8. **روت کارگاهی و آزمایشگاهی Kitchen Sink ([frontend/src/pages/KitchenSink.tsx](file:///d:/Playground/Web-Dash/frontend/src/pages/KitchenSink.tsx)):**
     - ثبت مسیر `/_ui` در [frontend/src/App.tsx](file:///d:/Playground/Web-Dash/frontend/src/App.tsx) جهت بررسی زنده و تست بصری تمام کامپوننت‌ها با ۱۰۰۰ روتر نمونه، استریم زنده لاگ و سناریوهای تغییر کانفیگ.
  9. **تست و صحه‌گذاری خودکار:**
     - نگارش ۱۳ تست واحد در [frontend/src/components/CoreComponents.test.tsx](file:///d:/Playground/Web-Dash/frontend/src/components/CoreComponents.test.tsx).
     - نگارش تست‌های اعتبارسنجی پایتون در [tests/test_step_6_4_core_components.py](file:///d:/Playground/Web-Dash/tests/test_step_6_4_core_components.py).
     - به‌روزرسانی خروجی پروداکشن در `frontend/dist/` بدون نیاز به نصب هیچ ابزاری در مقصد.
* **تأییدیه (Verify):**
  - اجرای موفق `npm run typecheck` با ۰ خطا.
  - اجرای موفق `npm run lint` با ۰ خطا و ۰ اخطار.
  - پاس شدن ۱۰۰٪ آزمون‌های Vitest (مجموعاً **۴۰ تست از ۴۰ تست** در ۶ فایل تست: `40 passed in 5.71s`).
  - پاس شدن کلیه آزمون‌های پایتون گام ۶.۴ (**۶ تست از ۶ تست با موفقیت پاس شدند**).
  - موفقیت کامل بیلد پروداکشن `npm run build` با حجم بهینه و قرارگیری در `dist/`.





