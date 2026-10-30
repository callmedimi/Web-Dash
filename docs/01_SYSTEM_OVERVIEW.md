# 01 — نمای کلی سامانه و معماری فنی (System Architecture)

سامانه **Web-Dash** یک وب‌اپلیکیشن اختصاصی برای تیم‌های عملیات شبکه (NOC) است که به منظور اجرای اتوماسیون‌های پیکربندی، گزارش‌گیری، پایش و عیب‌یابی بر روی روترها و سوئیچ‌های هواوی مبتنی بر سیستم‌عامل **Huawei VRP** (شامل خانواده‌های NE، CX، ATN و CE) طراحی شده است.

---

## ۱. پشته فناوری (Technology Stack)

* **زبان و فریم‌ورک بک‌اند:** Python 3.11 + Flask (نسخه >= 2.3.0) + Werkzeug
* **ارتباط با تجهیزات شبکه:** Netmiko (نسخه >= 4.2.0) و Paramiko (نسخه >= 3.0.0) از طریق پروتکل SSH (بدون پشتیبانی از SNMP مستقیم)
* **پایش و تلمتری:** Zabbix JSON-RPC API v2.0+ (جهت استعلام اینترفیس‌ها، وضعیت پورت‌ها و لایسنس)
* **فرانت‌اند:** ساختار Single Page Application (SPA) یکپارچه در [templates/index.html](file:///d:/Playground/Web-Dash/templates/index.html) با استفاده از HTML5، Vanilla JavaScript، Bootstrap 5 (لوکال) و استایل‌های سفارشی [netmate.css](file:///d:/Playground/Web-Dash/static/css/netmate.css) و [tokens.css](file:///d:/Playground/Web-Dash/static/css/tokens.css).
* **مدیریت نشست و همزمانی:** `threading.Thread` برای پردازش‌های پس‌زمینه و دائم، به همراه `threading.Lock` و Server-Sent Events (SSE) برای ارسال لاگ‌های زنده.
* **کانتینرسازی:** Docker (ایمیج سبک `python:3.11-slim`) و Docker Compose (پورت نگاشت‌شده `7676:5000`).

---

## ۲. ساختار پروژه و دایرکتوری‌ها

```text
Web-Dash/
├── app.py                         # هسته اصلی وب‌سرور، روت‌ها و هندلرهای API (~۲۳۴۰ خط)
├── auth.py                        # منطق احراز هویت، هش رمز، RBAC و مدیریت کاربران
├── auto_clear_noconf.py           # اتوماسیون پاکسازی آلارم و خاموش‌سازی پورت‌های noconf
├── reporting_logic.py             # ماژول تولید گزارش‌های لینک‌های قطع (Down-links) و ترانک
├── license_check.py               # استعلام وضعیت لایسنس و منابع روترها
├── license_renewal_logic.py       # اتوماسیون تمدید و فعال‌سازی لایسنس با آپلود فایل
├── check_vrf_routing.py           # ردیابی و بررسی جدول روتینگ VRF در روترها
├── ptp_troubleshoot_service.py    # عیب‌یابی زنجیره‌ای سینک کلاک مخابراتی (PTP / SyncE)
├── site_arp_service.py            # تطبیق کدهای سایت، جداول ARP و MAC پورت‌ها
├── session_extractor_service.py   # تولید ساختار درختی نشست‌های SecureCRT از روی CSV
├── services/
│   ├── zabbix_service.py          # کلاینت ارتباط با Zabbix JSON-RPC API
│   ├── refresh_zabbix_db.py       # اسکریپت رفرش کش دیتابیس روترهای زبیکس
│   └── license_db.py              # ارتباط با پایگاه داده لایسنس‌ها
├── templates/
│   └── index.html                 # رابط کاربری وب تک‌صفحه‌ای (۲۷۴ کیلوبایت)
├── static/
│   ├── css/                       # استایل‌های Bootstrap، netmate و دیزاین‌توکن‌ها
│   └── js/                        # اسکریپت باندل‌شده Bootstrap
├── plan/                          # اسناد نقشه‌راه، معماری هدف و فازهای بازطراحی
├── docs/                          # مستندات سیستم و گزارش مراحل پیاده‌سازی
├── Dockerfile                     # فایل بیلد کانتینر
├── docker-compose.yml             # تنظیمات اجرای کانتینر در سرور
└── requirements.txt               # وابستگی‌های پایتون
```

---

## ۳. مدیریت وضعیت و نشست‌ها (State Management)

در نسخه فعلی، داده‌ها و تسک‌های در حال اجرا درون دیکشنری‌های سراسری در رم سرور نگهداری می‌شوند:

* `SESSIONS`: ذخیره نشست‌های اتوماسیون آلارم (شناسه `sid`، وضعیت، درصد پیشرفت، روترهای پردازش‌شده، لاگ‌ها، قفل `result_lock`).
* `REPORT_SESSIONS`: ذخیره وضعیت تسک‌های تولید گزارش داون‌لینک و داده‌های ترانک.
* `LICENSE_SESSIONS`: ذخیره وضعیت اسکن وضعیت لایسنس تجهیزات.
* `RENEWAL_SESSIONS`: ذخیره وضعیت آپلود و اعمال لایسنس جدید بر روی روترها.
* `ROUTING_SESSIONS`: ذخیره پردازش‌های بررسی جدول روتینگ VRF.
* `PTP_SESSIONS`: ذخیره سشن‌های عیب‌یابی پروتکل‌های همگام‌سازی زمان PTP.
* `COLLECTOR_JOBS`: ذخیره تسک‌های کالکتور پس‌زمینه ARP و MAC به همراه وضعیت `running`/`stopped`.

---

## ۴. کاتالوگ اندپوینت‌های API (API Endpoints Catalog)

### ۴.۱ احراز هویت و مدیریت کاربران
| متد | مسیر | دسترسی | شرح |
|-----|------|--------|-----|
| `POST` | `/login` | عمومی | ورود به سامانه با username و password و ساخت کوکی سشن |
| `POST` | `/logout` | احرازشده | خروج از سیستم و پاکسازی سشن |
| `GET` | `/me` | احرازشده | دریافت اطلاعات کاربر جاری، نقش و سطوح دسترسی |
| `GET` | `/users` | ادمین | دریافت لیست تمام کاربران سیستم |
| `POST` | `/users` | ادمین | تعریف کاربر جدید و تخصیص نقش و پرمیشن‌ها |
| `PUT` | `/users/<id>` | ادمین | ویرایش اطلاعات، نقش، وضعیت فعال بودن یا رمز کاربر |
| `DELETE` | `/users/<id>` | ادمین | حذف کاربر از سیستم |

### ۴.۲ اتوماسیون پاکسازی آلارم (Alarm Clear)
| متد | مسیر | دسترسی | شرح |
|-----|------|--------|-----|
| `POST` | `/parse-csv` | لاگین | پارس فایل CSV روترها و استخراج لیست نودها |
| `POST` | `/run-manual` | مجوز `alarm_clear_manual` | اجرای تک‌دستگاه پاکسازی آلارم |
| `POST` | `/run-bulk` | مجوز `alarm_clear_bulk` | اجرای دسته‌ای پاکسازی آلارم و خاموش‌سازی noconf |
| `GET` | `/status/<sid>` | لاگین | دریافت وضعیت پیشرفت، شمارنده‌ها و لاگ‌های یک سشن |
| `POST` | `/stop/<sid>` | لاگین | ارسال سیگنال لغو و توقف تسک |
| `GET` | `/events/<sid>` | لاگین | استریم لاگ‌های زنده به فرانت‌اند از طریق SSE |
| `GET` | `/download/<sid>` | لاگین | دانلود فایل گزارش نهایی تغییرات در قالب CSV |

### ۴.۳ گزارش لینک‌های قطع (Down-Links Reporting)
| متد | مسیر | دسترسی | شرح |
|-----|------|--------|-----|
| `POST` | `/parse-csv-nodes` | لاگین | پارس CSV و استخراج لیست استان‌ها از نام روترها |
| `POST` | `/run-report` | مجوز `reporting` | استارت گزارش‌گیری لینک‌های قطع بر اساس استان و فیلتر سنی |
| `GET` | `/report-status/<sid>` | لاگین | دریافت وضعیت و نتایج گزارش داون‌لینک |
| `GET` | `/download-report/<sid>` | لاگین | دانلود فایل CSV گزارش پورت‌های قطع |
| `GET` | `/download-trunk-report/<sid>` | لاگین | دانلود فایل CSV وضعیت پورت‌های ترانک |

### ۴.۴ مدیریت لایسنس (License Management)
| متد | مسیر | دسترسی | شرح |
|-----|------|--------|-----|
| `POST` | `/license/run` | مجوز `license_check` | استعلام وضعیت و منابع لایسنس تجهیزات |
| `GET` | `/license/status/<sid>` | لاگین | وضعیت تسک بررسی لایسنس |
| `POST` | `/match-licenses` | مجوز `license_check` | تطبیق فایل‌های لایسنس آپلودشده با ESN روترها |
| `POST` | `/renew-licenses` | مجوز `license_renewal` | فعال‌سازی و اکتیو کردن فایل لایسنس روی روترها |
| `GET` | `/renew-status/<sid>` | لاگین | وضعیت پردازش تمدید لایسنس |
| `GET` | `/download-license-report/<sid>` | لاگین | دانلود گزارش جامع لایسنس در قالب CSV |

### ۴.۵ روتینگ، عیب‌یابی PTP، ARP و استخراج نشست‌ها
| متد | مسیر | دسترسی | شرح |
|-----|------|--------|-----|
| `POST` | `/routing/check` | مجوز `check_vrf_routing` | استعلام روت VRF از روترهای مبدأ، RR و PE |
| `POST` | `/ptp/check` | مجوز `ptp_troubleshoot` | اجرای عیب‌یابی گام‌به‌گام و هاپ‌به‌هاپ PTP |
| `GET` | `/ptp/status/<sid>` | لاگین | وضعیت لاگ‌ها و توپولوژی PTP |
| `POST` | `/site-arp/search` | مجوز `site_arp` | جستجوی اطلاعات سایت، IP و مک‌پورت |
| `POST` | `/site-arp/collector/start` | مجوز `site_arp` | راه‌اندازی کالکتور دوره‌ای ARP/MAC |
| `POST` | `/session-extractor/generate` | مجوز `session_extractor` | ساخت پکیج ZIP سشن‌های SecureCRT بر اساس CSV |
| `POST` | `/zabbix/interfaces` | مجوز `zabbix_lookup` | استعلام زنده‌ی پورت‌ها و گراف‌ها از Zabbix API |
