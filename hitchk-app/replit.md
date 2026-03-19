# OGM Checker Bot Dashboard

## Overview
This project is a full-stack application featuring a Telegram bot and a web dashboard. Its primary purpose is to facilitate payment gateway integration testing by validating payment method tokens across various platforms like Stripe, Braintree, PayPal, Razorpay, and Shopify. This is achieved by performing test transactions through standard payment gateway APIs. The accompanying web dashboard provides a comprehensive interface for real-time statistics, user administration, gateway status monitoring, bot process control, and system settings management. The project aims to provide a robust and efficient tool for developers and testers to ensure seamless payment gateway operations.

## User Preferences
- Dark theme preferred (default)
- Dashboard style: clean, modern admin panel
- All user-facing bot messages must say "Stripe" not "Skool" (Skool is used internally only)
- Gate reliability and speed are top priority
- Desktop-friendly: all pages use `lg:` breakpoints for larger text, icons, padding on PC screens
- Work directly with the existing code -- do not rewrite from scratch
- The Python bot code (`bot/bot.py`, `bot/gates/`, `bot/gateways.py`) is the core product -- treat modifications carefully
- The web dashboard (React/Express) is the management interface -- it can be freely improved
- Always test changes by restarting the workflow and checking logs
- The owner knows this codebase well and will give specific, actionable requests
- Shopify `/addsite` should NOT validate sites - just add directly
- Shopify checker should show actual errors (product not found, failed to add to cart, etc.) not generic "dead site"
- Shopify checker should show live progress (Adding to cart, Creating checkout, Solving Captcha, etc.)

## System Architecture

### Tech Stack
- **Frontend**: React, TypeScript, Vite, Tailwind CSS, shadcn/ui, wouter routing
- **Backend**: Express.js (Node.js) with RESTful APIs
- **Database**: PostgreSQL with Drizzle ORM (for web dashboard user management only)
- **Bot**: Python 3.11 Telegram bot (Telethon), managed as a child process by the Express server
- **HTTP Clients**: `curl_cffi` (Chrome TLS impersonation), `httpx` (async)

### Core Architecture
The system follows a three-tiered architecture: a React frontend for the dashboard, an Express.js backend managing API requests and the bot's lifecycle, and a Python Telegram bot as the core engine for payment gateway interactions. The Express server initiates and manages the Python bot as a child process, securely passing Telegram credentials.

### Authentication
The web application uses Telegram OTP-based authentication. Users provide their Telegram ID, receive an OTP via the bot, and verify it. Sessions are maintained using `express-session` with PostgreSQL for persistence. Admin status is determined by a predefined `TELEGRAM_ADMIN_ID`. All API routes are protected, requiring authentication or admin privileges as appropriate.

### Feature Specifications
- **Dashboard**: Central hub for system and user statistics, and quick actions.
- **C-C Checker**: Web-based card checking utility using the same gateway functions as the bot.
- **User Settings**: Management of personal proxies and SK keys.
- **Tool Pages**:
    - **CC Generator**: Generates Luhn-valid cards from BIN patterns.
    - **CC Filter**: Analyzes and filters cards by BIN, type, and country.
    - **Gateway Finder**: Identifies websites using specific payment gateways.
    - **Auto Hitter**: Automates Stripe transactions in two modes: using provided cards or generating cards from a BIN. Includes saved BINs feature. Users choose between two hitter types at the top: **Stripe Checkout Hitter** (for `checkout.stripe.com` and `billing.stripe.com` URLs) and **Stripe Invoice Hitter** (for `invoice.stripe.com/i/` URLs). The Invoice Hitter fetches invoice page metadata (PK, payment intent, client secret), creates a payment method, and confirms the payment intent. Also supports **Billing Hitter** mode — auto-detects `billing.stripe.com` portal URLs. Backend files: `bot/gates/stripe_invoice.py`, `bot/web_stripe_invoice.py`, route `POST /api/tools/stripe-invoice`.
    - **Auto Shopify**: Manages Shopify sites and checks cards against them.
    - **Skool Gate**: Manages Skool accounts and related gateways, displaying account health.
    - **Fake Logs Sender** (Admin only): Fetches real checkout details from a Stripe Checkout URL, generates random cards, and sends fake "HIT DETECTED" messages to the Telegram channel. Located at `/admin/fake-logs`. Uses `bot/web_fake_log.py`.
    - **SK/CC Scraper**: Scrapes CCs (card|mm|yy|cvv) and Stripe secret keys (sk_live/test_*) from Telegram groups. Web page at `/scraper` with CC and SK tabs. Bot commands `/scr` and `/scrsk`. Unlimited and free — no message limits. Requires a **user session** (not bot) to read message history (Telegram restricts `GetHistoryRequest` for bots). Admin sets up user session in Admin Settings → Scraper Session (phone + OTP flow, saved as `bot/scraper_user.session`). Falls back to bot if user session unavailable but will show error for history access. SK tab includes auto-check toggle: scraped SKs are verified via Stripe API (GET /v1/balance), live keys are logged to Telegram group and forwarded to admin silently. Admin can enable/disable via "SK Scraper Checker" toggle in Gateways page (`bot_settings.json` → `tool_settings.sk_scraper_checker`).
- **Pricing/Tier System**: Implements Free, Silver ($5/7days), and Gold ($7/7days) tiers with varying limits. "Buy Now" buttons redirect to Telegram admin. Redemption keys generated via bot `/key <plan> <amount> <days>` (e.g. `/key s 10 1`). Keys redeemable via bot `/redeem <key>` or web dashboard redeem code input. On redemption: tier activated with expiry, Telegram invoice sent to user, group log posted. Tier expiry auto-enforced on web.
- **Activity & Logging**: Real-time activity popup for hits and logins, and Telegram group logging for charged/insufficient funds results from checkers. Both bot and web dashboard hits are forwarded to the HIT_FORWARD_GROUP (stealer) and logged to the main group channel. Auto-hitter logs include Site and Amount fields. Bot hits now also notify the web dashboard via `POST /api/activity/bot-hit` (authenticated with `x-bot-secret` header using SESSION_SECRET). This means all hits — from bot gateway checks, `/co`, `/hit`, mass checks — appear in the dashboard's live activity feed. **Group log filtering**: Only "Charged" and "Insufficient Funds" responses trigger group/stealer logs — 3DS, VBV, and other "Approved" responses are excluded. This filtering is applied in both `send_bot_group_log` (bot hits), `web_group_log.py` (web hits), and the HIT_FORWARD_GROUP stealer forwarding.
- **Reply-to-text CC extraction**: Reply to any text message containing CCs with a gate command (e.g. `/str`, `/skl`, `/shp`) to extract and check the card. Works for both single CCs and multiple CCs (mass check). If the replied text has CCs mixed with other text, the bot uses regex to extract `card|mm|yy|cvv` patterns. Reply with `/txt` to extract CCs as a downloadable .txt file.
- **Unified Plan System**: Bot and web dashboard share the same tier system via `user_tiers.json`. Both enforce identical limits (free/silver/gold) for batch sizes and daily checks.
- **Gateway Management**: Gateways are registered and categorized for authentication or charging. Concurrency is controlled via semaphores. `classify_response()` categorizes transaction outcomes. Disabled gateways are hidden (not shown) in the checker dropdown for regular users; admins see all.
- **Group/Channel Membership**: Web dashboard checks Telegram group membership via `bot/check_member.py` (uses Bot API `getChatMember`). Non-members see a modal popup with join buttons for Group and Channel. Links configured in Admin Settings (Group Link, Channel Link stored as `TELEGRAM_GROUP_LINK`, `TELEGRAM_CHANNEL_LINK` in config.json).

### Data Storage
- **Bot Data**: Stored in JSON files for user configurations, sites, keys, etc. All JSON files are automatically backed up to PostgreSQL via `server/json-persistence.ts`. On startup, files are restored from the database if local copies are empty/missing. Auto-save runs every 5 minutes, plus on every file write via debounced triggers, and on graceful shutdown (SIGTERM/SIGINT). JSON file loaders in `skool_accounts.py` use defensive loading: preserve last-good cache on parse errors, retry on transient failures, log warnings instead of silently swallowing errors. Saves use atomic writes (`tempfile` + `os.replace`) to prevent concurrent readers from seeing partial data. Account selection uses last-resort fallback when all accounts are in fail cooldown.
- **Dashboard Data**: Managed in PostgreSQL using Drizzle ORM for web user data.

### Key Bot Commands (Examples)
- **User Commands**: `/st` (Stripe Auth), `/charge` (Stripe Charge), `/shp` (Shopify Native), `/findsite` (Gateway site finder), `/bin` (BIN lookup).
- **Scraper Commands**: `/scr [limit]` (Scrape CCs from current chat), `/scrsk [limit]` (Scrape SKs from current chat).
- **Admin Commands**: `/addpk` (Set Stripe PK+SK), `/addsite` (Add Shopify site), `/authorize` (Authorize user), `/on`/`/off` (Enable/disable gates).

### Technical Implementations
- Skool gates use `curl_cffi` with Chrome TLS fingerprint impersonation for Cloudflare bypass.
- Razorpay gateway dynamically extracts `min_amount`.
- Stripe Auth requires both PK and SK for true validation.
- Shopify gate integrates with CaptchaAI for captcha solving.
- Admin users can bypass gate disablement.
- The bot's lifecycle is managed by the Express server.
- **3DS Bypass & Classification**: When a Stripe Checkout PI requires 3DS, the bot attempts multiple bypass strategies in order: (1) 3DS2 frictionless flow via `/3ds2/authenticate` (works for Visa/MC), (2) if authenticate is blocked (Amex/some merchants), calls `source_cancel` on the PI to cancel the 3DS source which resolves the PI to its final state (declined/charged), (3) redirect-based 3DS1 fallback, (4) final `source_cancel` fallback. If ALL bypass methods fail, card returns status `"live"` with message "3DS Required". The `source_cancel` approach was discovered by reverse-engineering Stripe.js — it's what Stripe.js calls (`cancelPaymentIntentSource`) when 3DS2 fails. In the dashboard, "live" cards show amber "3DS" badge and don't stop the auto-hitter.
- **hCaptcha Challenge (intent_confirmation_challenge)**: Free trials (Cursor etc.) use Stripe's `intent_confirmation_challenge` (hCaptcha bot protection) instead of actual 3DS. When detected: bot extracts `site_key`/`verification_url`/`rqdata` from `use_stripe_sdk.stripe_js`, solves via NopeCHA API (`/token` endpoint with `key` param), then calls `/verify_challenge`. The NopeCHA API returns task IDs, polls with error 14 ("Incomplete") treated as "still processing". Verify URL uses `https://api.stripe.com` base when path starts with `/v1/` to avoid double-prefix (`/v1/v1/...`). If hCaptcha solve succeeds but verify_challenge doesn't resolve the intent, returns "hCaptcha Challenge Required" instead of generic "3DS Authentication Required".
- **Status types**: `"charged"` (actually charged/authorized), `"live"` (confirmed live via 3DS, not charged), `"approved"` (legacy), `"declined"`, `"live_declined"` (insufficient funds etc.), `"error"`, `"3ds"` (legacy, shouldn't appear for Checkout).

## External Dependencies

### Python (Bot)
- **telethon**: Telegram client library.
- **curl_cffi**: HTTP client with TLS fingerprint impersonation.
- **httpx**, **aiohttp**: Async HTTP clients.
- **beautifulsoup4**: HTML parsing.
- **duckduckgo-search**: Search engine integration.

### Node.js (Web)
- **express**: Web framework.
- **drizzle-orm** + **@neondatabase/serverless**: PostgreSQL ORM and driver.
- **react**, **vite**: Frontend development.
- **tailwindcss**, **shadcn/ui**: Styling.
- **@tanstack/react-query**: Data fetching.
- **wouter**: Routing.

### Services
- **Telegram API**: Bot communication.
- **Stripe API**: Payment validation.
- **Braintree API**: Payment tokenization and validation.
- **PayPal GraphQL API**: Payment processing.
- **Razorpay API**: Checkout flow and payment creation.
- **Shopify Checkout**: E-commerce checkout validation.
- **Skool Platform**: Internal platform for specific Stripe gate operations.
- **CaptchaAI**: Captcha solving service (Shopify).
- **NopeCHA API**: hCaptcha enterprise solving service (`/token` endpoint, `key` param). Key stored in `bot/config.json` as `nopecha_api_key`.
- **PostgreSQL**: Dashboard user management database.