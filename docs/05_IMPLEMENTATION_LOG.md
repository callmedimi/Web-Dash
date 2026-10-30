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
