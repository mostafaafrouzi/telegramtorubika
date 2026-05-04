# نقشه راه پیاده‌سازی v2 (وضعیت اجرا)

این سند **پیوند مستقیم** با فازهای پلن Greenfield دارد و هر بار که بخشی از پلن در کد یا معماری تحقق پیدا می‌کند، اینجا به‌روز می‌شود: **وضعیت، فایل‌های درگیر، و یادداشت فنی.**

آخرین به‌روزرسانی سند: **2026-05-04**

---

## فهرست فازهای پلن (مرجع)

| فاز | عنوان کوتاه |
|-----|----------------|
| Phase 0 | Product spec freeze |
| Phase 1 | Core rebuild + UX foundation |
| Phase 2 | Billing, packages, admin operations |
| Phase 3 | Transfer stack |
| Phase 4 | Toolkit stack |
| Phase 5 | Borrowed product modules (patterns) |
| Phase 6 | Reliability, growth, scale |

---

## Phase 0 — Product spec freeze

### انجام‌شده

- **PRD و طراحی هسته، منو، billing، transfer، toolkit، KPI** در پوشه `docs/v2/` ثبت شده است.
  - **فایل‌ها:** `01-prd-v2.md` … `08-kpi-sla-growth-anti-fraud.md`
  - **یادداشت فنی:** قراردادهای سطح بالا (plugin boundaries، کیف پول معنایی، KPI) بدون قفل کردن استک اجرایی؛ امکان پیاده‌سازی تدریجی در کنار `telebot.py` فعلی.

### در انتظار / بعدی

- نهایی‌سازی **قرارداد رویداد bot↔plugin** به صورت یک فایل JSON Schema یا ماژول Python مشترک (برای فاز ۱ formal).

---

## Phase 1 — Core rebuild + UX foundation

### انجام‌شده

#### 1) بازطراحی Reply Keyboard مطابق `03-menu-spec.md`

- **هدف پلن:** در منوی اصلی فقط **ورودی** «پلن / خرید / محدودیت»؛ دکمه‌های `/plan`، `/usage`، `/queue`، `/purchase` فقط در زیرمنوی پلن.
- **وضعیت:** انجام شد.
- **فایل:** [`telebot.py`](../../telebot.py) — توابع `build_main_menu`, `build_files_menu`, `build_admin_menu` و متن‌های `menu_intro` (فا/ان).
- **یادداشت فنی:**
  - دستورهای اسلش همچنان به‌صورت سراسری در Bot API معتبرند؛ تفکیک فقط در **نمایش دکمه‌های ReplyKeyboard** است تا UX شبیه منوی دسته‌ای (مثل نمونه‌های مرجع) شود.
  - منوی ادمین برای جلوگیری از تکرار، ردیف اول را به دکمهٔ بخش پلن و ردیف دوم را به `پنل ادمین` + `/admin` + `/version` منتقل کرد.

#### 2) اسکلت پکیج `v2` (ماژولارسازی تدریجی)

- **هدف پلن:** شروع هستهٔ ماژولار بدون شکستن اجرای فعلی.
- **وضعیت:** انجام شد (نسخه اولیه).
- **فایل‌ها:**
  - [`v2/__init__.py`](../../v2/__init__.py)
  - [`v2/core/menu_sections.py`](../../v2/core/menu_sections.py) — `MenuSection` (enum)
  - [`v2/core/plugins.py`](../../v2/core/plugins.py) — `PluginRegistry` stub
- **یادداشت فنی:** هنوز handlerهای Pyrogram به‌طور کامل به registry منتقل نشده‌اند؛ این مرحله **زیرساخت نام‌گذاری و مرز ماژول** است.

#### 3) پایش بخش منو در state کاربر (`menu_section`)

- **هدف پلن:** آماده‌سازی برای Menu Engine داده‌محور، آنالیتیکس، و مسیریابی آینده بدون اتکا به متن دکمه.
- **وضعیت:** انجام شد (نسخه اولیه، persistence در همان JSON موجود).
- **فایل:** [`telebot.py`](../../telebot.py)
- **جزئیات فنی:**
  - کلید ثابت: `menu_section` داخل [`queue/user_states.json`](../../queue/user_states.json) (کلید کاربر همان الگوی موجود `get_user_key`).
  - مقادیر هم‌تراز با [`MenuSection`](../../v2/core/menu_sections.py): `main`, `plan`, `files`, `rubika`, `settings`, `admin`.
  - توابع کمکی: `merge_user_state`, `set_menu_section`, **`set_state_preserving_menu`** — هنگام رفتن به مراحل wizard (روبیکا، تأیید ارسال، نام ZIP، …) مقدار `menu_section` در صورت وجود **حذف نمی‌شود** تا پس از خروج از ویزارد، زمینهٔ منو قابل استنتاج بماند.
  - نقاط به‌روزرسانی: `/start`, `/menu`, دکمهٔ بخش پلن، `/plan` `/usage` `/purchase` `/queue`, مسیرهای «منوی اتصال/فایل/تنظیمات/ادمین», `/admin`, `/newbatch`, فراخوانی اتصال روبیکا، و پس از تغییر زبان (callback).

#### 4) استخراج Menu Engine از `telebot.py` به `v2/core`

- **هدف پلن:** حرکت واقعی به سمت معماری ماژولار و کم‌کردن چسبندگی منوی ReplyKeyboard به فایل monolith.
- **وضعیت:** انجام شد (مرحله اول extraction).
- **فایل‌ها:**
  - [`v2/core/menu_engine.py`](../../v2/core/menu_engine.py)
  - [`v2/core/__init__.py`](../../v2/core/__init__.py)
  - [`telebot.py`](../../telebot.py)
- **جزئیات فنی:**
  - تمام سازنده‌های منو (`build_main_menu`, `build_plan_menu`, `build_rubika_menu`, `build_files_menu`, `build_settings_menu`, `build_admin_menu`) در `telebot.py` به **wrapper** تبدیل شدند و rendering واقعی به `v2.core.menu_engine` منتقل شد.
  - `menu_engine` به‌جای وابستگی به i18n داخلی، `tr` را به‌صورت callback دریافت می‌کند؛ بنابراین مستقل از storage/translation backend باقی می‌ماند.
  - نتیجه: منطق چیدمان منو در یک ماژول جدا متمرکز شد و تغییرات UX بعدی روی منو بدون دست‌زدن به handlerهای صف/انتقال قابل انجام است.
  - **جدول نگاشت متن دکمهٔ Reply به مسیر داخلی** (`resolve_reply_button_route`) نیز از `text_handler` به [`v2/core/menu_engine.py`](../../v2/core/menu_engine.py) منتقل شد تا افزودن برچسب جدید یا زبان جدید بدون نگه‌داشتن دیکشنری بزرگ در monolith انجام شود؛ مسیر مصرف‌کننده همچنان `telebot.py` است.

#### 5) استخراج dispatch مسیرهای Reply Keyboard به `v2/handlers`

- **هدف پلن:** کاهش حجم `text_handler` و جدا کردن منطق «دکمه چه کاری کند» از بقیهٔ state machine (ویزارد روبیکا، ZIP، …).
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/reply_routes.py`](../../v2/handlers/reply_routes.py) — `ReplyRouteDeps`، `dispatch_reply_keyboard_route`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py)
  - [`telebot.py`](../../telebot.py) — نمونهٔ `REPLY_ROUTE_DEPS` و فراخوانی dispatch.
- **جزئیات فنی:**
  - الگوی **dependency injection**: ارجاع به handlerهای Pyrogram در یک `dataclass` immutable (`frozen=True`) یک‌بار بعد از تعریف توابع legacy ساخته می‌شود؛ از circular import جلوگیری می‌کند.
  - رفتار زنجیرهٔ قبلی `if mapped == ...` بدون تغییر معنایی منتقل شده است.
  - گام بعدی منطقی: استخراج ویزاردها با همان الگوی deps.

#### 6) استخراج ویزارد اتصال روبیکا (`await_phone` / `await_pass_key` / `await_code`)

- **هدف پلن:** نازک‌کردن `text_handler` و جداسازی state machine احراز روبیکا برای تست و تغییر امن‌تر.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/rubika_wizard.py`](../../v2/handlers/rubika_wizard.py) — `RubikaWizardDeps`، `dispatch_rubika_connect_wizard`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export
  - [`telebot.py`](../../telebot.py) — `RUBIKA_WIZARD_DEPS` و فراخوانی dispatch بعد از `await_quick_message`
- **جزئیات فنی:**
  - ارسال کد، pass key، و sign-in همانند قبل از legacy فراخوانی می‌شود؛ `log_event` و به‌روزرسانی `users.json` داخل همان جریان باقی ماند.
  - توابع کمکی `_deep_find_phone_hash` / `_deep_find_status` به‌صورت callback در `RubikaWizardDeps` تزریق شد تا `v2` وابسته به implementation داخلی فایل monolith نباشد.

#### 7) استخراج ویزارد ZIP batch (`await_zip_name` / `await_part_mb`)

- **هدف پلن:** جدا کردن جریان «نام آرشیو → اندازه قطعه → ساخت ZIP محلی → صف/تأیید» از بدنهٔ اصلی `text_handler`.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/zip_batch_wizard.py`](../../v2/handlers/zip_batch_wizard.py) — `ZipBatchWizardDeps`، `dispatch_zip_batch_wizard`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py)
  - [`telebot.py`](../../telebot.py) — `ZIP_BATCH_WIZARD_DEPS` و فراخوانی dispatch بعد از ویزارد روبیکا
- **جزئیات فنی:**
  - همان توابع legacy (`make_bundle_zip_local`, `gate_quota`, `queue_or_confirm`, `edit_wizard`, …) به‌صورت تزریق وابستگی پاس داده می‌شوند؛ رفتار صف و سهمیه تغییر نکرده است.
  - مسیر خطا (فایل خیلی بزرگ، رد quota، نبود فایل روی دیسک) همان پاک‌سازی state/batch قبلی را انجام می‌دهد.

#### 8) مسیرهای متن انتهایی: رمز ZIP سراسری، direct mode، راهنمای لینک

- **هدف پلن:** خالی‌کردن انتهای `text_handler` از منطق جانبی تا pipeline متن خواناتر شود.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/zip_password_prompt.py`](../../v2/handlers/zip_password_prompt.py) — `ZipPasswordPromptDeps`، `handle_zip_password_text`
  - [`v2/handlers/direct_mode_text.py`](../../v2/handlers/direct_mode_text.py) — `DirectModeTextDeps`، `handle_direct_mode_plain_text`
  - [`v2/handlers/direct_url_hint.py`](../../v2/handlers/direct_url_hint.py) — `DirectUrlHintDeps`، `handle_direct_url_sendlink_hint`
  - [`telebot.py`](../../telebot.py) — `_zip_password_waiting` / `_set_zip_password_waiting`، شیءهای `ZIP_PASSWORD_DEPS`، `DIRECT_MODE_TEXT_DEPS`، `DIRECT_URL_HINT_DEPS`
- **جزئیات فنی:**
  - پرچم سراسری `waiting_for_zip_password` همچنان در `telebot.py` مانده است (`safemode on/off` همان global را می‌زند)؛ فقط خواندن/نوشتن از طریق callback به handler جدید تزریق شد تا در آینده بتوان آن را به state پایدار (DB یا state کاربر) منتقل کرد.
  - صف متن در حالت مستقیم همان `queue.push_task` و `log_event` قبلی را صدا می‌زند.
  - تشخیص URL برای پیام «از `/sendlink` استفاده کن» بدون تغییر منطق `extract_first_url` / `is_direct_url` باقی مانده است.

#### 9) جدا کردن bootstrap از انتهای `telebot.py` (factory + entrypoint)

- **هدف پلن:** آماده‌سازی برای «نقطهٔ ورود سبک»؛ اجرای `start`/`idle`/تسک‌های پس‌زمینه خارج از بدنهٔ monolith.
- **وضعیت:** انجام شد (مرحله اول؛ ثبت handlerها اکنون از طریق `register_handlers` انجام می‌شود؛ نقطهٔ ورود همچنان lazy import است).
- **فایل‌ها:**
  - [`v2/bot/client_factory.py`](../../v2/bot/client_factory.py) — `build_bot_client` (شامل `set_parse_mode`)
  - [`v2/bot/startup.py`](../../v2/bot/startup.py) — `run_bot()` با **lazy import** ماژول `telebot` تا بعد از بارگذاری کامل handlerها اجرا شود
  - [`v2/bot/__init__.py`](../../v2/bot/__init__.py)
  - [`telebot.py`](../../telebot.py) — `app = build_bot_client(...)` و `if __name__ == "__main__": run_bot()`
- **جزئیات فنی:**
  - `main.py` همچنان `python telebot.py` را اجرا می‌کند؛ رفتار runtime عوض نشده است.
  - مرحله بعدی برای تکمیل این محور: باریک‌تر کردن `telebot.py` با انتقال تدریجی callback/body handlerها به ماژول‌های `v2/handlers` (قرارداد ثبت همین `register_handlers` می‌ماند).

#### 10) اولین persistence v2 در SQLite (`v2_user_prefs`)

- **هدف پلن:** شروع مهاجرت تدریجی state از JSON به DB مشترک با همان فایل `queue.sqlite3`.
- **وضعیت:** انجام شد (مرحله dual-write برای `menu_section` + پاک‌سازی همراه `clear_state`).
- **فایل‌ها:**
  - [`queue_db.py`](../../queue_db.py) — جدول `v2_user_prefs`، متدهای `upsert_menu_section`، `get_menu_section`، `delete_v2_user_prefs`
  - [`telebot.py`](../../telebot.py) — `set_menu_section` پس از JSON، SQLite را به‌روز می‌کند؛ **`clear_state`** فقط ورودی `user_states.json` را حذف می‌کند و **دیگر** ردیف `v2_user_prefs` را پاک نمی‌کند تا mirrorها با خروج از ویزارد از بین نروند.
- **جزئیات فنی:**
  - خواندن اصلی state از `user_states.json` است؛ اگر کلید `menu_section` در JSON نباشد، **`get_state`** مقدار را از SQLite با **`queue.get_menu_section`** پر می‌کند (بدون نوشتن خودکار به JSON تا mergeهای بعدی رفتار قبلی را حفظ کنند).
  - جدول SQLite علاوه بر mirror برای تحلیل، اکنون در مسیر runtime برای بخش منو نیز استفاده می‌شود.
  - ستون **`lang`** به `v2_user_prefs` اضافه شد (`ALTER` برای دیتابیس‌های قدیمی)؛ **`set_lang`** / **`get_lang`** در `telebot.py` همان dual-write و fallback را برای زبان انجام می‌دهند (منبع اصلی هنوز `users.json` است).
  - ستون **`direct_mode`** (صفر/یک) به `v2_user_prefs` اضافه شد؛ **`set_direct_mode`** پس از JSON mirror می‌کند؛ **`is_direct_mode`** اگر کلید در `users.json` نباشد از SQLite با **`queue.get_direct_mode`** می‌خواند.
  - ستون **`rubika_session`** (نام سشن لینک‌شده) به `v2_user_prefs` اضافه شد؛ پس از موفقیت ویزارد در [`v2/handlers/rubika_wizard.py`](../../v2/handlers/rubika_wizard.py) با callback **`persist_rubika_session`** mirror می‌شود؛ **`get_user_session`** اگر در `users.json` وصل نباشد از **`queue.get_rubika_session`** fallback می‌گیرد.
  - **`clear_state` دیگر `delete_v2_user_prefs` را صدا نمی‌زند**؛ متد `delete_v2_user_prefs` در [`queue_db.py`](../../queue_db.py) برای سناریوهای آینده (مثلاً حذف کامل کاربر) باقی مانده است.
  - دستور ادمین **`/admin_clear_prefs <telegram_user_id>`** برای پاک‌سازی عمدی ردیف `v2_user_prefs` یک کاربر (پشتیبانی / اصلاح mirror) در [`telebot.py`](../../telebot.py) و [`register_handlers`](../../v2/bot/register_handlers.py) ثبت شد.
  - خطای DB در مسیر UI با `log_event` ثبت می‌شود تا bot در صورت خرابی DB از کار نیفتد.

#### 11) ثبت متمرکز handlerهای Pyrogram (`register_handlers`)

- **هدف پلن:** یک نقطهٔ ثبت وابسته به `app.add_handler` به‌جای پراکندگی `@app.on_message` / `@app.on_callback_query` در monolith.
- **وضعیت:** انجام شد (مرحله اول؛ بدون تغییر معنایی فیلترها).
- **فایل‌ها:**
  - [`v2/bot/register_handlers.py`](../../v2/bot/register_handlers.py) — `register_handlers(app)` با `MessageHandler` / `CallbackQueryHandler` و ترتیب هم‌ارز دکوریتورهای قبلی
  - [`telebot.py`](../../telebot.py) — توابع handler بدون decorator؛ انتهای ماژول `register_handlers(app)`
  - [`v2/bot/__init__.py`](../../v2/bot/__init__.py) — export نماد `register_handlers`
- **یادداشت فنی:**
  - `import telebot as tb` فقط **داخل** تابع ثبت انجام می‌شود تا از import حلقوی در زمان بارگذاری ماژول جلوگیری شود.
  - فهرست دستورهای مستثنی از `text_handler` در همان فایل به‌صورت ثابت `_TEXT_EXCLUDED_COMMANDS` نگه داشته شده است؛ افزودن `/command` جدید باید همزمان handler اختصاصی و این فهرست را به‌روز کند.

#### 12) استخراج دستورهای پایهٔ بدون وابستگی روبیکا (`/start` … `/version`)

- **هدف پلن:** نازک‌کردن monolith با انتقال بدنهٔ handlerهای ساده به `v2/handlers` بدون تغییر قرارداد `register_handlers`.
- **وضعیت:** انجام شد (مرحله اول: شش دستور).
- **فایل‌ها:**
  - [`v2/handlers/basic_commands.py`](../../v2/handlers/basic_commands.py) — `BasicCommandDeps`، `handle_start` / `handle_menu` / `handle_lang` / `handle_help` / `handle_log_help` / `handle_version`
  - [`telebot.py`](../../telebot.py) — نمونهٔ `BASIC_COMMAND_DEPS` و wrapperهای نازک با همان نام تابع قبلی (ثبت در `register_handlers` عوض نشده است)
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export نمادها
- **یادداشت فنی:** `APP_VERSION` به‌صورت رشته در deps تزریق می‌شود تا ماژول `v2` به متغیر سراسری monolith وابسته نباشد.

#### 13) استخراج روبیکا / direct mode / وضعیت شبکه (`rubika_*`, `directmode`, `netstatus`)

- **هدف پلن:** همان الگوی deps برای handlerهای وابسته به سشن و تنظیمات کاربر بدون جابه‌جایی `register_handlers`.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/session_settings_commands.py`](../../v2/handlers/session_settings_commands.py) — `SessionSettingsCommandDeps` و `handle_rubika_status` / `handle_rubika_connect` / `handle_direct_mode` / `handle_netstatus`
  - [`telebot.py`](../../telebot.py) — `SESSION_SETTINGS_COMMAND_DEPS` (شامل `functools.partial` برای خواندن `network.json` بدون وابستگی مستقیم به `Path` در v2)
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export

#### 14) استخراج پلن و ادمین (`/usage` `/plan` `/purchase`، پنل ادمین و دستورات مرتبط)

- **هدف پلن:** جدا کردن بدنهٔ دستورهای پلن و خوشهٔ ادمین از monolith با deps قابل تست.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/plan_commands.py`](../../v2/handlers/plan_commands.py) — `PlanCommandDeps`، `handle_usage` / `handle_plan` / `handle_purchase`
  - [`v2/handlers/admin_commands.py`](../../v2/handlers/admin_commands.py) — `AdminCommandDeps`، `handle_admin_panel` / `handle_admin_tier` / `handle_admin_bonus` / `handle_cleanup_downloads`
  - [`telebot.py`](../../telebot.py) — `PLAN_COMMAND_DEPS`؛ `ADMIN_COMMAND_DEPS` **بعد از** `failed_count()` تا ارجاع به تابع معتبر باشد؛ `_run_admin_cleanup_downloads()` برای encapsulate کردن حلقهٔ `DOWNLOAD_DIR` بدون وابستگی Path در v2
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export
- **یادداشت فنی:** `load_network_snapshot` برای پنل ادمین همان callback ذخیره‌شده در `SESSION_SETTINGS_COMMAND_DEPS` است تا خواندن `network.json` تکراری نشود.

#### 15) استخراج خوشهٔ صف و ارسال سریع (`/sendtext` `/sendlink` `/queue` `/delall`)

- **هدف پلن:** جدا کردن مسیرهای پرمصرف صف از monolith با deps تزریق‌پذیر، بدون تغییر contract هندلرها و callbackهای موجود.
- **وضعیت:** انجام شد (مرحله اول؛ `/del` و callback مرکزی هنوز legacy هستند).
- **فایل‌ها:**
  - [`v2/handlers/queue_commands.py`](../../v2/handlers/queue_commands.py) — `QueueCommandDeps`، `handle_send_text` / `handle_send_link` / `handle_queue_manage` / `handle_clear_queue`
  - [`telebot.py`](../../telebot.py) — `QUEUE_COMMAND_DEPS` و wrapper برای `send_text_handler`، `send_link_handler`، `queue_manage_handler`، `clear_queue_handler`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export
- **یادداشت فنی:** برای جلوگیری از وابستگی ترتیبی هنگام بارگذاری ماژول، ارجاع `enqueue_rubika_text_message` در deps به‌صورت lazy (lambda) تنظیم شد تا تعریف تابع در بخش پایین‌تر فایل مشکلی ایجاد نکند.

#### 16) استخراج `safemode` به handler مستقل

- **هدف پلن:** جدا کردن منطق safe-mode از monolith و هم‌تراز کردن آن با الگوی deps در `v2/handlers`.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/safemode_command.py`](../../v2/handlers/safemode_command.py) — `SafeModeCommandDeps` و `handle_safemode`
  - [`telebot.py`](../../telebot.py) — wrapper برای `safemode_handler` و شیء `SAFEMODE_COMMAND_DEPS`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export

#### 17) استخراج `/del` به handler مستقل

- **هدف پلن:** جدا کردن مسیر حذف/لغو تک‌تسک از monolith و هم‌راستاسازی با خوشهٔ queue commands.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/delete_command.py`](../../v2/handlers/delete_command.py) — `DeleteCommandDeps` و `handle_delete_one`
  - [`telebot.py`](../../telebot.py) — wrapper در `delete_one_handler` + شیء `DELETE_COMMAND_DEPS`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export

#### 18) شکستن `callback_handler` به dispatcher ماژولار

- **هدف پلن:** خارج کردن مسیرهای callback پرتراکم از monolith با حفظ رفتار فعلی (lang/queue/confirm/cancel).
- **وضعیت:** انجام شد (مرحله اول؛ fallback نهایی همچنان در wrapper legacy).
- **فایل‌ها:**
  - [`v2/handlers/callback_routes.py`](../../v2/handlers/callback_routes.py) — `CallbackRouteDeps` و `dispatch_callback_route`
  - [`telebot.py`](../../telebot.py) — `callback_handler` به wrapper تبدیل شد (`handled` + fallback) و `CALLBACK_ROUTE_DEPS` اضافه شد
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export
- **یادداشت فنی:** مسیر `set_menu_section(main)` در deps به‌صورت callback مجزا تزریق شد تا coupling مستقیم enum/منطق منو از داخل dispatcher کم بماند.

#### 19) استخراج `newbatch/done` به ماژول batch commands

- **هدف پلن:** سبک‌سازی مسیر فایل‌ها و آماده‌سازی برای انتقال کامل flow batch به زیرماژول مستقل.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/batch_commands.py`](../../v2/handlers/batch_commands.py) — `BatchCommandDeps`، `handle_new_batch`، `handle_done_batch`
  - [`telebot.py`](../../telebot.py) — wrapper در `new_batch_handler` و `done_batch_handler` + شیء `BATCH_COMMAND_DEPS`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export

#### 20) استخراج orchestration پیام متنی (`text_handler`) به ماژول مستقل

- **هدف پلن:** سبک‌سازی مسیر متن ورودی و متمرکز کردن ترتیب dispatch (plan button → reply route → quick message → wizard tails) در یک ماژول تست‌پذیر.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/text_entry.py`](../../v2/handlers/text_entry.py) — `TextEntryDeps` و `handle_text_entry`
  - [`telebot.py`](../../telebot.py) — `TEXT_ENTRY_DEPS` و wrapper برای `text_handler`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export

#### 21) استخراج pipeline مدیا (`media_handler`) به ماژول مستقل

- **هدف پلن:** جدا کردن یکی از بزرگ‌ترین بدنه‌های monolith (دانلود مدیا، سقف حجم، batch zip، queue/confirm) در قالب deps قابل تست.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/handlers/media_handler.py`](../../v2/handlers/media_handler.py) — `MediaHandlerDeps` و `handle_media_message`
  - [`telebot.py`](../../telebot.py) — `MEDIA_HANDLER_DEPS` و wrapper برای `media_handler`
  - [`v2/handlers/__init__.py`](../../v2/handlers/__init__.py) — export

#### 22) Mirror کامل `user_states` / `batch_sessions` در SQLite

- **هدف پلن:** قدم بعدی مهاجرت طبق `02-core-technical-design.md` — همان `queue.sqlite3`، بدون قطع منبع اصلی JSON.
- **وضعیت:** انجام شد (dual-write + fallback خواندن).
- **فایل‌ها:**
  - [`queue_db.py`](../../queue_db.py) — جداول `v2_user_state_mirror`، `v2_batch_session_mirror` و متدهای `get/upsert/delete_*_mirror`
  - [`telebot.py`](../../telebot.py) — `set_state` / `clear_state` و `set_batch` / `clear_batch` mirror را به‌روز می‌کنند؛ اگر کلید کاربر **در فایل JSON نباشد**، `get_state` / `get_batch` از SQLite می‌خوانند.
- **یادداشت فنی:**
  - منبع حقیقت در runtime همچنان JSON است تا رفتار موجود عوض نشود؛ ردیف mirror با هر `set_state` / `set_batch` هم‌تراز می‌شود و با `clear_state` / `clear_batch` حذف می‌شود.
  - همگام‌سازی اولیه: تابع **`sync_v2_ephemeral_mirrors_from_json`** در [`telebot.py`](../../telebot.py) همهٔ ورودی‌های معتبر JSON را به mirror کپی می‌کند و از [`v2/bot/startup.py`](../../v2/bot/startup.py) در **`run_bot()`** قبل از `app.start` فراخوانی می‌شود تا بعد از ری‌استارت نیز DB با فایل روی دیسک هم‌خوان بماند.
  - **اولویت خواندن:** با **`V2_EPHEMERAL_READ_PRIMARY_SQLITE=1`** (یا `true` / `yes` / `on` / `sqlite`) در محیط، **`get_state`** و **`get_batch`** ابتدا mirror SQLite را می‌خوانند و در صورت خالی بودن به JSON برمی‌گردند؛ نوشتن همچنان **دوطرفه** است. نمونهٔ متغیر در [`.env.example`](../../.env.example). در استارت، اگر این حالت فعال باشد، `log_event("v2_ephemeral_read_mode", primary="sqlite")` ثبت می‌شود.
  - **ادمین:** **`/admin_clear_state_mirrors <telegram_user_id>`** در [`telebot.py`](../../telebot.py) و [`register_handlers`](../../v2/bot/register_handlers.py) — فقط ردیف‌های `v2_user_state_mirror` و `v2_batch_session_mirror` را حذف می‌کند (فایل‌های JSON عوض نمی‌شوند؛ راهنما در پنل ادمین با کلید i18n `admin_clear_state_mirrors_hint`).

### در انتظار / بعدی (همچنان Phase 1)

- **باقیمانده (اختیاری):** حذف تدریجی وابستگی به فایل JSON پس از اثبات پایداری حالت sqlite-first در production.
- پولیش: تست دستی مسیرهای ویزارد/صف؛ برای کاربر نهایی پاک‌سازی mirror همچنان با `clear_state` / `clear_batch` است.

---

## Phase 2 — Billing, packages, admin operations

**وضعیت فاز (MVP):** برای scope تعریف‌شده در این repo، **فاز ۲ بسته است** — ledger، مسیر تست end-to-end، اعمال پلن پس از `paid`، reconcile، و ابزار ادمین/HTTP بدون اتصال به PSP تجاری. اتصال به **درگاه بانکی واقعی** و امضای webhook اختصاصی پروایدر در **بک‌لاگ post-MVP** مانده است.

### انجام‌شده

- تداوم استفاده از [`user_entitlements.py`](../../user_entitlements.py) + دستورات `/usage`, `/plan`, `/purchase` و ادمین `/admin_tier`, `/admin_bonus` (پیش‌تر در محصول موجود بوده است).
- **زیرساخت billing v2** در `queue.sqlite3` و پکیج [`v2/billing/`](../../v2/billing/) (قرارداد درگاه، stub، webhook، اعمال پلن، reconcile).

#### 23) Ledger پرداخت در SQLite (`v2_payments`) + ماژول `v2/billing`

- **هدف پلن:** شروع پیاده‌سازی Phase 2 مطابق `04-billing-pricing-gateway.md` بدون تغییر رفتار فعلی `/purchase` (هنوز فقط متن راهنما).
- **وضعیت:** انجام شد (اسکیما + API نازک).
- **فایل‌ها:**
  - [`queue_db.py`](../../queue_db.py) — جدول **`v2_payments`** (ایندکس روی `telegram_user_id`, `status`, `authority`)، متدهای **`insert_v2_payment`**, **`update_v2_payment_status`**, **`get_v2_payment_by_id`**, **`get_v2_payment_by_idempotency_key`**, **`list_v2_payments_for_user`**
  - [`v2/billing/status.py`](../../v2/billing/status.py) — ثابت‌های وضعیت چرخهٔ عمر
  - [`v2/billing/ledger.py`](../../v2/billing/ledger.py) — **`record_initiated_payment`**
  - [`v2/billing/__init__.py`](../../v2/billing/__init__.py) — export عمومی
- **یادداشت فنی:** `telegram_user_id` به‌جای `user_id` داخلی تا بدون جدولٔ `users` v2 قابل استفاده باشد؛ درگاه و webhook بعداً به این ردیف‌ها وصل می‌شوند.

#### 24) قرارداد درگاه + Stub + دستور ادمین `/admin_payment_lookup`

- **هدف پلن:** پیاده‌سازی minimal مطابق `04-billing-pricing-gateway.md` §4، بدون اتصال واقعی به PSP.
- **وضعیت:** انجام شد (نسخهٔ اول).
- **فایل‌ها:**
  - [`v2/billing/gateway.py`](../../v2/billing/gateway.py) — **`PaymentGateway`** (Protocol)، **`PaymentIntentResult`**، **`StubPaymentGateway`** (`create_payment_intent` یک ردیف ledger با `authority` مصنوعی می‌سازد)
  - [`v2/handlers/admin_commands.py`](../../v2/handlers/admin_commands.py) — **`handle_admin_payment_lookup`**، فیلد **`list_v2_payments_for_user`** در deps
  - [`telebot.py`](../../telebot.py) — **`admin_payment_lookup_handler`**، i18n، **`ADMIN_COMMAND_DEPS`**
  - [`v2/bot/register_handlers.py`](../../v2/bot/register_handlers.py) — ثبت **`/admin_payment_lookup`**
- **یادداشت فنی:** `/purchase` همچنان فقط متن راهنما است؛ برای تست ledger می‌توان از کد یا REPL **`StubPaymentGateway(queue)`** را صدا زد.

#### 25) Webhook داخلی + ادمین وضعیت پرداخت

- **هدف پلن:** مسیر **verify + apply** مطابق `04-billing-pricing-gateway.md` §5–6 و اتصال به stub HTTP موجود.
- **وضعیت:** انجام شد (بدون PSP واقعی).
- **فایل‌ها:**
  - [`v2/billing/status.py`](../../v2/billing/status.py) — **`ALL_STATUSES`**
  - [`v2/billing/webhook.py`](../../v2/billing/webhook.py) — **`VerifiedPaymentEvent`**, **`verify_bearer_authorization`**, **`parse_verified_event_from_dict`**, **`apply_verified_payment_event`**
  - [`tools/payment_webhook_stub.py`](../../tools/payment_webhook_stub.py) — مسیر **`POST /v2_payment_event`** (همان Bearer که `/grant`)
  - [`v2/handlers/admin_commands.py`](../../v2/handlers/admin_commands.py) — **`/admin_payment_status`**
  - [`telebot.py`](../../telebot.py), [`register_handlers`](../../v2/bot/register_handlers.py)
- **یادداشت فنی (قدیمی):** اکنون reconcile پس‌زمینه و `/admin_reconcile_billing` اضافه شده‌اند (بند ۲۷).

#### 27) بستن MVP فاز ۲: checkout استاب، entitlement، reconcile

- **هدف:** یک بارِ End-to-end قابل اجرا بدون PSP خارجی: ثبت پرداخت → `paid` → اعمال پلن؛ به‌علاوه انقضای ردیف‌های گیرکرده.
- **وضعیت:** انجام شد.
- **رفتار:**
  - **`BILLING_STUB_CHECKOUT=1`:** `/purchase` یک ردیف **`v2_payments`** با **`StubPaymentGateway`** می‌سازد (metadata: `grant_tier=pro`, `grant_days=30`).
  - **`paid`:** [`v2/billing/paid_entitlements.py`](../../v2/billing/paid_entitlements.py) — **`maybe_grant_plan_after_paid`** بعد از webhook [`apply_verified_payment_event`](../../v2/billing/webhook.py) یا **`/admin_payment_status … paid`** یک‌بار **`set_user_tier`** را صدا می‌زند (`entitlement_applied_at` برای جلوگیری از دوباره‌کاری).
  - **Reconcile:** [`v2/billing/reconcile.py`](../../v2/billing/reconcile.py) — **`run_reconcile`** ردیف‌های **`pending` / `initiated`** قدیمی را **`expired`** می‌کند؛ با **`BILLING_RECONCILE_ENABLE=1`** از [`v2/bot/startup.py`](../../v2/bot/startup.py) دوره‌ای اجرا می‌شود؛ **`/admin_reconcile_billing`** همان منطق را یک‌بار اجرا می‌کند.
  - [**`.env.example`**](../../.env.example): متغیرهای **`BILLING_*`**.
- **بک‌لاگ (خارج از MVP فاز ۲):** آداپتر درگاه ایرانی (Zarinpal / …)، verify امضای PSP، polling وضعیت تراکنش، پنل billing خارج از تلگرام.

---

## Phase 3 — Transfer stack

**وضعیت فاز (MVP):** برای scope همین ریپو، **فاز ۳ بسته است** — قرارداد آداپتر، مدل تسک، آداپتر Rubika + HTTP stub، و یک نقطهٔ یکپارچه‌سازی واقعی در worker (**`TRANSFER_V2_VALIDATE`**). جایگزینی کامل حلقهٔ **`download`/`upload`** با آداپتر و ارائهٔ Bale/Drive/unzip امن در **بک‌لاگ post-MVP** است.

### انجام‌شده

- مسیر فعلی Telegram → Rubika + صف SQLite + worker در [`rub.py`](../../rub.py).

#### 28) قرارداد `TransferAdapter` (Protocol)

- **هدف پلن:** قفل کردن نام متدها برای پیاده‌سازی تدریجی طبق `05-transfer-adapters-spec.md` §3.
- **وضعیت:** انجام شد.
- **فایل‌ها:** [`v2/transfer/protocol.py`](../../v2/transfer/protocol.py)، [`v2/transfer/__init__.py`](../../v2/transfer/__init__.py)

#### 29) آداپتر Rubika (تزریق‌پذیر)

- **فایل:** [`v2/transfer/rubika_adapter.py`](../../v2/transfer/rubika_adapter.py) — **`RubikaTransferAdapter`**.

#### 30) مدل تسک + آداپتر لینک (stub)

- **فایل‌ها:**
  - [`v2/transfer/task_model.py`](../../v2/transfer/task_model.py) — ثابت‌ها و `TypedDict` مطابق §2 سند transfer (همسو با payloadهای صف فعلی).
  - [`v2/transfer/link_adapter.py`](../../v2/transfer/link_adapter.py) — **`HttpLinkTransferAdapter`** (`download`/`upload` هنوز «legacy_worker_path» تا [`rub.py`](../../rub.py) مرجع بماند).

#### 31) یکپارچه‌سازی worker: اعتبار نشست قبل از پردازش

- **هدف:** اولین استفادهٔ runtime از لایهٔ v2 بدون بازنویسی حلقهٔ آپلود.
- **وضعیت:** انجام شد.
- **فایل‌ها:**
  - [`v2/transfer/integration.py`](../../v2/transfer/integration.py) — **`validate_transfer_task_v2`**
  - [`rub.py`](../../rub.py) — در **`process_task`**، اگر **`TRANSFER_V2_VALIDATE=1`** باشد، قبل از مراحل شبکه/فایل فراخوانی می‌شود؛ **`fallback_session`** همان env **`RUBIKA_SESSION`** worker است.
  - [**`.env.example`**](../../.env.example) — **`TRANSFER_V2_VALIDATE`**

### بک‌لاگ (بعد از MVP فاز ۳)

- هدایت واقعی `download`/`upload` به آداپترها؛ Bale، Drive، لینک امن سخت‌گیرانه، unzip سخت‌گیرانه.

---

## Phase 4 — Toolkit stack

**وضعیت فاز (MVP):** اولین ابزار wave-1 (شبکهٔ سبک) با پرچم env اضافه شد؛ ادامهٔ پازل‌ها و رجیستری مرکزی پلاگین در بک‌لاگ است.

### انجام‌شده

- اولویت‌بندی موج‌ها در [`06-toolkit-release-priority.md`](../06-toolkit-release-priority.md) (سند).
- **دستورهای toolkit شبکه (`TOOLKIT_NETWORK_LIGHT=1`):** `/dns`، `/myip`، `/ping` (TCP).
- **دستورهای toolkit متنی (`TOOLKIT_UTILITY_LIGHT=1`):** `/md5`، `/sha256`، `/b64e`، `/b64d` (ورودی تا ~۱۲۰۰۰ نویسه).
- **فایل‌ها:**
  - [`v2/toolkit/dns_light.py`](../../v2/toolkit/dns_light.py) — **`resolve_hostname`**, **`normalized_toolkit_host`**
  - [`v2/toolkit/myip_light.py`](../../v2/toolkit/myip_light.py) — **`get_public_ip`**
  - [`v2/toolkit/ping_light.py`](../../v2/toolkit/ping_light.py) — **`tcp_ping`**
  - [`v2/toolkit/text_utils_light.py`](../../v2/toolkit/text_utils_light.py) — هش و Base64
  - [`v2/handlers/toolkit_commands.py`](../../v2/handlers/toolkit_commands.py) — همهٔ handlerهای toolkit + **`toolkit_quota_try`** / **`toolkit_quota_commit`** (مصرف سهمیه فقط پس از موفقیت)
  - [`telebot.py`](../../telebot.py) — **`TOOLKIT_NETWORK_LIGHT`**, سهمیهٔ روزانه UTC در `v2_toolkit_daily` (**`effective_toolkit_daily_limit`** در [`user_entitlements.py`](../../user_entitlements.py) + اختیاری **`TOOLKIT_DAILY_LIMIT_PER_USER`**)، **`dns_lookup_handler`**, i18n
  - [`v2/bot/register_handlers.py`](../../v2/bot/register_handlers.py)
  - [**`.env.example`**](../../.env.example)

### بک‌لاگ

- ابزارهای بعدی wave-1 (whois، …)، رجیستری مرکزی روی [`PluginRegistry`](../../v2/core/plugins.py).

---

## Phase 5 — Borrowed product modules

### انجام‌شده

- تحلیل patternها و ریسک در `07-reference-mapping-risk.md`.

### در انتظار

- پیاده‌سازی پلاگین‌های جدا با feature flag (Flare/Google/GitHub-style).

---

## Phase 6 — Reliability, growth, scale

### انجام‌شده

- چارچوب KPI/SLA در `08-kpi-sla-growth-anti-fraud.md`.

### در انتظار

- داشورد متریک واقعی، صف اولویت‌دار بر پایه tier، رفرال ضدتقلب.

---

## راهنمای نگهداری این سند

1. با هر merge معنادار به `main`/`master` که بخشی از پلن را می‌بندد، **یک بخش «انجام‌شده»** در همان فاز اضافه یا به‌روز کنید.
2. حتماً **مسیر فایل** و **تصمیم فنی کوتاه** را بنویسید تا در بازنویسی Greenfield گم نشود.
