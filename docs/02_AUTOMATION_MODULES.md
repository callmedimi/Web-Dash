# 02 — ماژول‌های اتوماسیون شبکه (Automation Modules)

سامانه **Web-Dash** شامل ۸ ماژول اصلی اتوماسیون شبکه است که هر کدام وظیفه مشخصی را در فرآیندهای عملیاتی تیم NOC بر عهده دارند. این سند منطق، دستورات، ورودی و خروجی هر ماژول را به تفصیل شرح می‌دهد.

---

## ۱. پاکسازی آلارم و خاموش‌سازی پورت‌های بدون کانفیگ ([auto_clear_noconf.py](file:///d:/Playground/Web-Dash/auto_clear_noconf.py))

* **هدف:** حذف آلارم‌های غیرضروری روی پورت‌هایی که کانفیگ ندارند (`noconf`) و خاموش کردن اینترفیس‌های مربوطه جهت جلوگیری از تولید مجدد آلارم.
* **فرایند اجرا:**
  1. اتصال SSH با درایور `huawei` در Netmiko به روتر هدف.
  2. اجرای دستور `display alarm active` برای دریافت لیست آلارم‌های فعال.
  3. فیلتر کردن آلارم‌های پورت‌ها و بررسی وضعیت کانفیگ اینترفیس با `display current-configuration interface <intf>`.
  4. در صورتی که اینترفیس کانفیگ نداشته باشد (یا تنها شامل تنظیمات پیش‌فرض باشد):
     - اجرای دستور پاکسازی آلارم: `clear alarm active sequence <seq>`
     - ورود به حالت پیکربندی: `system-view`
     - رفتن به اینترفیس: `interface <name>`
     - اجرای دستور خاموش‌سازی: `shutdown`
     - خروج و اعمال تغییرات: `return` یا `commit` (بسته به نسخه VRP5/VRP8).
* **خروجی:** لاگ‌های زنده در فرانت‌اند و در نهایت فایل گزارش CSV شامل ستون‌های:
  `ne_name`, `interface`, `sequence`, `alarm_description`, `decision`, `action`, `status`, `timestamp`.

---

## ۲. گزارش‌گیری لینک‌های قطع ([reporting_logic.py](file:///d:/Playground/Web-Dash/reporting_logic.py))

* **هدف:** شناسایی تمام اینترفیس‌های Down در روترهای یک استان یا کل کشور، بررسی علت قطعی، بررسی ترانک‌ها و مدت زمان قطعی.
* **دستورات VRP مورد استفاده:**
  * `display interface brief` جهت دریافت وضعیت فیزیکی و پروتکلی تمام پورت‌ها.
  * `display interface description` جهت استخراج نام لینک، مقصد یا توضیحات خط.
  * `display trunkmembership eth-trunk <id>` برای شناسایی اعضای ترانک و وضعیت فعال/غیرفعال آن‌ها.
  * `display transceiver interface <intf> verbose` در پورت‌های نوری جهت خواندن توان نوری دریافتی (Rx Power) و ارزیابی قطعی فیبر.
* **فیلترها و تحلیل‌ها:**
  * فیلتر سنی (`age_value` و `age_unit` مثل ۲ روز): تفکیک لینک‌های تازه قطع‌شده از لینک‌های قدیمی.
  * تابع `compute_analytics`: تجمیع آمار پورت‌های قطع بر اساس نوع پورت، سرعت، علت قطعی و نام ترانک‌ها.
* **خروجی:** دو فایل گزارش CSV جداگانه برای «تمام لینک‌های داون» و «پورت‌های ترانک داون».

---

## ۳. بررسی و تمدید لایسنس ([license_check.py](file:///d:/Playground/Web-Dash/license_check.py) و [license_renewal_logic.py](file:///d:/Playground/Web-Dash/license_renewal_logic.py))

* **بررسی لایسنس (`license_check`):**
  * اجرای دستورات `display license state` و `display license resource usage` روی روتر.
  * استخراج شماره سریال سخت‌افزاری (ESN)، پکیج‌های فعال، تاریخ انقضا و تعداد روزهای باقی‌مانده.
* **تطبیق و تمدید لایسنس (`license_renewal`):**
  * دریافت فایل‌های لایسنس از کاربر (`.dat` یا `.xml`) به همراه فایل لیست روترها.
  * تطبیق ESN داخل هر فایل لایسنس با ESN روترهای شبکه.
  * آپلود فایل لایسنس مربوطه به حافظه فلش دستگاه از طریق پروتکل SFTP یا FTP.
  * اجرای دستور فعال‌سازی لایسنس: `license active <filename>` در روتر و بررسی نتیجه تاییدیه.

---

## ۴. بررسی روتینگ و جدول VRF ([check_vrf_routing.py](file:///d:/Playground/Web-Dash/check_vrf_routing.py))

* **هدف:** عیب‌یابی مسیرهای BGP/MPLS VPN در سطح روترهای مبدأ (Originator)، روترهای Route Reflector (RR) و روترهای لبه (PE).
* **فرایند اجرا:**
  1. دریافت نام VRF و آدرس IP / Subnet از کاربر.
  2. اتصال به روتر مبدأ و اجرای: `display ip routing-table vpn-instance <vrf> <prefix>`
  3. استخراج Next-Hop و BGP Community.
  4. اتصال به RR جهت بررسی وجود مسیر در جدول روتینگ سراسری.
  5. اتصال به PEهای مقصد و ارزیابی صحت انتشار مسیر و عدم وجود بلک‌هول (Blackhole).

---

## ۵. عیب‌یابی سینک کلاک مخابراتی ([ptp_troubleshoot_service.py](file:///d:/Playground/Web-Dash/ptp_troubleshoot_service.py))

* **هدف:** ردیابی و عیب‌یابی پروتکل‌های سنکرونیزاسیون شبکه مخابراتی (IEEE 1588v2 / PTP و SyncE).
* **دستورات VRP:**
  * `display ptp all`
  * `display ptp interface <interface>`
  * `display clock source`
* **منطق اجرا:**
  * بررسی وضعیت کلاک (Master, Slave, Passive).
  * استخراج مقادیر Clock Class, Clock Accuracy, Offset from Master, و Steps Removed.
  * ردگیری زنجیره‌ای هاپ‌به‌هاپ (Traceback) از روتر مقصد به سمت گرندمستر (Grandmaster) برای تشخیص این که سیگنال کلاک در کدام روتر یا اینترفیس دچار خطا یا انحراف فاز/فرکانس شده است.

---

## ۶. ردیابی کد سایت، ARP و مک‌پورت‌ها ([site_arp_service.py](file:///d:/Playground/Web-Dash/site_arp_service.py))

* **هدف:** اتصال متقابل کد سایت مخابراتی، آدرس IP و مک‌آدرس سوئیچ/روتر.
* **فرایند:**
  1. تطبیق کد سایت در `unified_sites.csv` جهت به‌دست آوردن IP و مدل دستگاه.
  2. بررسی جدول ARP برای یافتن مک‌آدرس متناظر با IP.
  3. کالکتور زنده (Collector): در صورت نیاز به اطلاعات زنده، اسکریپت با SSH دستورات `display arp` و `display mac-address` را جمع‌آوری کرده و پایگاه‌داده محلی را رفرش می‌کند.

---

## ۷. استخراج سشن‌های SecureCRT ([session_extractor_service.py](file:///d:/Playground/Web-Dash/session_extractor_service.py))

* **هدف:** ساخت خودکار فایل‌های کانفیگ SecureCRT (`.ini`) برای تک‌تک روترهای شبکه.
* **فرایند:**
  * دریافت فایل CSV استاندارد شامل ستون‌های `NE Name`، `NE IP Address` و `Subnet Path`.
  * پاکسازی نام‌ها و ایجاد ساختار پوشه‌بندی درختی متناظر با Subnet Path (مثلاً `IPBH/Hormozgan/Router1.ini`).
  * تنظیم پیش‌فرض‌های اتصال SSH (پورت ۲۲، پروتکل SSH2) و بسته‌بندی در قالب یک فایل ZIP آماده دانلود.

---

## ۸. یکپارچگی با Zabbix ([services/zabbix_service.py](file:///d:/Playground/Web-Dash/services/zabbix_service.py))

* **هدف:** پایش اینترفیس‌ها و سلامت تجهیزات بدون ارسال ترافیک سنگین SNMP به روترها.
* **ویژگی‌ها:**
  * اتصال از طریق JSON-RPC API به سرور زبیکس با توکن یا یوزرنیم/پسورد.
  * استعلام متادیتا و هاست‌های زبیکس با کش‌گذاری محلی (`zabbix_router_db.json`).
  * استعلام اینترفیس‌ها، ترافیک ورودی/خروجی، وضعیت خطاها (Errors/Discards) و ترسیم نمودار در فرانت‌اند.
