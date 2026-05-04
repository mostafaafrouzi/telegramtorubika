# Menu Behavior Specification (v2)

## 1) Objective
Make menus category-first and context-aware so that plan actions are shown only inside plan submenu.

## 2) Main Menu Taxonomy
- Main categories:
  - `📁 انتقال فایل`
  - `🧰 ابزارها`
  - `🌐 شبکه و امنیت`
  - `💰 بازارها`
  - `🌍 جهان`
  - `📋 پلن / خرید / محدودیت`
  - `⚙️ تنظیمات`
  - `👤 پروفایل من`
  - `🛠 پنل ادمین` (role-based visibility)

## 3) Plan Submenu Rules
- On main menu, only one plan entry appears:
  - `📋 پلن / خرید / محدودیت`
- Hidden from main menu:
  - `/plan`
  - `/purchase`
  - `/usage`
  - `/queue`
- These four items appear only after user opens plan section.
- Plan submenu includes:
  - `/plan`
  - `/purchase`
  - `/usage`
  - `/queue`
  - `🔙 بازگشت به منوی اصلی`

## 4) Rendering Contracts
- `build_main_menu(user_ctx)`:
  - never render plan command buttons directly.
  - render category entry only.
- `build_plan_menu(user_ctx)`:
  - render plan actions and localized descriptions.
- `menu_state.current_section` persists current submenu.
- `back` action resets `current_section = main`.

## 5) Input Handling
- Command input remains globally valid:
  - typing `/plan` manually always works.
- Button visibility follows section context:
  - global command availability != global button visibility.
- If user is in nested submenu and sends unsupported button text:
  - show short hint and keep current submenu.

## 6) Localization Rules
- All button labels resolved by i18n keys.
- Logic must not depend on literal Persian/English text.
- Mapping example:
  - `menu.section.plan`
  - `menu.plan.action.usage`
  - `menu.plan.action.purchase`

## 7) Access Rules
- `🛠 پنل ادمین` only visible to admin roles.
- If non-admin triggers admin command manually:
  - deny with localized `not_authorized`.

## 8) UX Constraints
- Max 3 rows visible per section when possible.
- Keep high-frequency actions in first two rows.
- Show premium markers only near premium actions, not categories.

## 9) Acceptance Tests
1. `/start` shows main categories and does not show `/plan` button.
2. Tapping `📋 پلن / خرید / محدودیت` opens plan submenu with four actions.
3. Tapping `🔙 بازگشت` returns to main menu and hides plan action buttons.
4. Typing `/plan` in any menu state still returns plan summary.
5. Switching language updates labels without breaking action routing.
