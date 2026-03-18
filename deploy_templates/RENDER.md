# Render Deployment Template for telegcli Bot

# Deploy to Render: https://render.com/

# === render.yaml (Infrastructure as Code) ===

# Place this file in your repo as render.yaml

services:

- type: web
  name: telegcli-bot
  env: python
  plan: free # or starter/standard
  buildCommand: pip install -r requirements.txt
  startCommand: python -m telegcli.main --bot --profile $BOT_PROFILE

  envVars:
  - key: BOT_PROFILE
    value: my_bot # Change to your bot profile name
  - key: BOT_MODE
    value: polling # or "webhook" for webhook mode
  - key: TELEGCLI_CONFIG_DIR
    value: /var/lib/telegcli/config
    # Note: Data persists across redeployments with Render Disks
  - key: LOG_LEVEL
    value: INFO

  # For webhook mode, also set:
  - key: WEBHOOK_PORT
    value: 10000

  # Connect Render Disk for config persistence

  disk:
  name: telegcli-data
  mountPath: /var/lib/telegcli
  sizeGB: 1

# === Setup Instructions ===

# 1. Create Render account at https://render.com

# 2. Connect GitHub repository

# 3. Create web service from render.yaml

# 4. Set these environment variables:

# - BOT_TOKEN: Your Telegram bot token

# - Any other sensitive config as env vars

# 5. Deploy!

# === Webhook Mode ===

# For webhook instead of polling (more efficient):

# 1. Set BOT_MODE=webhook

# 2. Set WEBHOOK_URL=https://<your-service>.onrender.com/telegram

# 3. Set WEBHOOK_SECRET=<secure-random-token>

# 4. Configure firewall to allow POST /telegram

# === Monitoring ===

# - Logs: Render Dashboard > Logs tab

# - Health: Monitor bot using `bot doctor` command

# - Restarts: Render auto-restarts on failure (default 3 attempts)

# - Resources: Check CPU/memory usage in Render Dashboard

# === Cost Considerations ===

# - Free tier: 750 hrs/month (one service can run continuously)

# - Spinning down: Service goes to sleep after 15 mins of inactivity

# - For 24/7 uptime, upgrade to Starter or higher

# === Persistent Storage ===

# Config and logs stored in /var/lib/telegcli/config on Render Disk

# Survives redeployments and restarts
