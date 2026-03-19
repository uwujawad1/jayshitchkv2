# HitChecker cPanel Deployment Guide

## Prerequisites
- cPanel hosting with **Node.js** and **Python 3** support
- SSH access (or cPanel Terminal)
- PostgreSQL database created

## Database Setup

1. Go to **cPanel > PostgreSQL Databases**
2. Create a database (e.g., `ogmtoolc_hitchecker`)
3. Create a user and assign it to the database with all privileges
4. Your DATABASE_URL will be:
   ```
   postgresql://USERNAME:PASSWORD@localhost:5432/DATABASE_NAME
   ```
   URL-encode any special characters in the password.

## File Upload

1. Download `hitchecker-cpanel.tar.gz` from Replit
2. Go to **cPanel > File Manager**
3. Navigate to your home directory (`/home/yourusername/`)
4. Create a folder called `hitchecker` (or your preferred name)
5. Upload `hitchecker-cpanel.tar.gz` into that folder
6. Right-click the file and select **Extract**

After extraction, your folder should contain:
```
hitchecker/
  app.js
  package.json
  requirements.txt
  dist/
  bot/
```

## Python Dependencies

Open **cPanel > Terminal** (or SSH) and run:

```bash
cd ~/hitchecker
/usr/bin/python3 -m pip install --user -r requirements.txt
```

## Node.js App Setup

1. Go to **cPanel > Setup Node.js App**
2. Click **Create Application**
3. Configure:
   - **Node.js version**: 18 or 20 (whichever is available)
   - **Application mode**: Production
   - **Application root**: `hitchecker` (your folder name)
   - **Application URL**: your domain or subdomain
   - **Application startup file**: `app.js`
4. Click **Create**
5. Note the virtual environment activation command shown at the top

## Install Node Dependencies

In the Terminal or SSH:

```bash
cd ~/hitchecker
```

Use the activation command from Step 5 above (looks like `source /home/user/nodevenv/hitchecker/18/bin/activate`), then:

```bash
npm install --production
```

## Environment Variables

In the Node.js App settings, add these environment variables:

| Variable | Value |
|----------|-------|
| `NODE_ENV` | `production` |
| `DATABASE_URL` | `postgresql://USER:PASS@localhost:5432/DB_NAME` |
| `SESSION_SECRET` | Any random long string (e.g., generate with `openssl rand -hex 32`) |
| `PYTHON_PATH` | `/usr/bin/python3` |
| `PORT` | The port assigned by cPanel (usually auto-configured) |

## Bot Configuration

The bot settings are in `bot/config.json`. These should already be configured from Replit. Key fields:

```json
{
  "TELEGRAM_BOT_TOKEN": "your-bot-token",
  "TELEGRAM_ADMIN_ID": "your-admin-telegram-id",
  "TELEGRAM_API_ID": "your-api-id",
  "TELEGRAM_API_HASH": "your-api-hash",
  "TELEGRAM_GROUP_ID": "-100xxxxxxxxxx",
  "TELEGRAM_CHANNEL_ID": "@YourChannel",
  "TELEGRAM_GROUP_LINK": "https://t.me/+invitelink",
  "TELEGRAM_CHANNEL_LINK": "https://t.me/YourChannel"
}
```

## Start the App

1. Go back to **cPanel > Setup Node.js App**
2. Find your application and click **Restart**
3. Visit your domain to verify the app is running

## Troubleshooting

### "pip3: command not found"
Use `/usr/bin/python3 -m pip install --user -r requirements.txt` instead.

### Python script errors
Make sure Python dependencies are installed. Check that `/usr/bin/python3` is the correct path:
```bash
which python3
```

### App won't start
- Check the Node.js app logs in cPanel
- Verify `DATABASE_URL` is correct and the database exists
- Ensure `app.js` is set as the startup file
- Make sure `dist/` folder exists with `index.cjs` inside

### Session issues
- Make sure `SESSION_SECRET` is set (without it, sessions won't persist across restarts)
- The database needs the `user_sessions` table (auto-created on first run)

## Updating

When you get a new `hitchecker-cpanel.tar.gz`:

1. Upload and extract it to the same folder (overwrite existing files)
2. Re-run `/usr/bin/python3 -m pip install --user -r requirements.txt` (if requirements changed)
3. Re-run `npm install --production` (if packages changed)
4. Restart the Node.js app in cPanel
