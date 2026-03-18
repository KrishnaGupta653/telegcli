# Railway Deployment Template for telegcli Bot

# Deploy to Railway with: railway up

# === railway.json Configuration ===

# Place this in your project root as railway.json

{
"name": "telegcli-bot",
"description": "Telegram bot service using telegcli",
"builder": "dockerfile",
"deploy": {
"startCommand": "python -m telegcli.main --bot --profile $BOT_PROFILE"
}
}

# === Environment Variables ===

# Set these in Railway Dashboard:

# BOT_PROFILE=my_bot # Name of bot profile to run

# BOT_TOKEN=<your_token> # Telegram bot token (stored securely)

# TELEGCLI_CONFIG_DIR=/app/.config/telegcli # Config directory

# WEBHOOK_URL=https://your-app.railway.app/telegram # Optional webhook URL

# === Webhook Setup (optional) ===

# For webhook mode instead of polling:

# BOT_WEBHOOK_URL=https://your-app.railway.app/telegram

# BOT_WEBHOOK_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# BOT_MODE=webhook

# === Monitoring ===

# Monitor bot via Railway dashboard:

# - Logs: Railway > Bot Service > Deployment Logs

# - Health: Check status with `bot doctor <profile>`

# - Restarts: Railway tracks auto-restarts on crash
