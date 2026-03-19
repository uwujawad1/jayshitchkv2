# OGM Checker Bot Dashboard

## Overview

Full-stack application featuring a Telegram bot and a web dashboard. Primary purpose: payment gateway integration testing by validating payment method tokens across Stripe, Braintree, PayPal, Razorpay, and Shopify. The web dashboard provides real-time statistics, user admin, gateway status monitoring, bot process control, and system settings management.

## Project Location

The main project lives in `hitchk-app/`. All development should happen there.

## Tech Stack

- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, wouter routing
- **Backend**: Express.js (Node.js), RESTful APIs
- **Database**: PostgreSQL with Drizzle ORM (session + user management)
- **Bot**: Python 3.11 Telegram bot (Telethon), managed as child process by Express
- **HTTP Clients**: `curl_cffi` (Chrome TLS impersonation), `httpx` (async)

## Running the App

The workflow runs: `cd hitchk-app && npm run dev`

Server listens on port 5000.

## Structure

```
hitchk-app/
├── client/src/          # React frontend
│   ├── pages/           # All page components
│   └── components/      # UI components
├── server/              # Express backend
│   ├── index.ts         # Entry point (port 5000)
│   ├── routes.ts        # API routes
│   ├── db.ts            # Drizzle DB connection
│   ├── botManager.ts    # Python bot lifecycle manager
│   └── storage.ts       # Data access layer
├── shared/
│   └── schema.ts        # Drizzle schema + Zod types
├── bot/                 # Python Telegram bot
│   ├── bot.py           # Main bot entry
│   └── gates/           # Gateway implementations
├── package.json         # Node.js dependencies
├── vite.config.ts       # Vite config
└── drizzle.config.ts    # DB config
```

## Key Bot Commands

- `/st` (Stripe Auth), `/charge` (Stripe Charge), `/shp` (Shopify Native)
- `/scr [limit]` (Scrape CCs), `/scrsk [limit]` (Scrape SKs)
- `/addpk` (Set Stripe keys), `/addsite` (Add Shopify site), `/authorize` (Authorize user)

## Authentication

Telegram OTP-based auth. Users provide Telegram ID, get OTP via bot, verify it. Sessions use `express-session` with PostgreSQL. Admin determined by `TELEGRAM_ADMIN_ID`.
