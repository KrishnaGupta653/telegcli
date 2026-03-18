# systemd Service Template for telegcli Bot

# Deploy on VPS with systemd (Ubuntu/Debian/RHEL)

# === Installation Steps ===

# 1. SSH into your VPS

# 2. Create ~/.telegcli/bot_profile.json with your bot configuration

# 3. Copy Dockerfile and docker-compose.yml (or install telegcli directly)

# 4. Follow setup steps below

# === systemd Service File ===

# Save as: /etc/systemd/system/telegcli-bot.service

[Unit]
Description=telegcli Telegram Bot Service
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=3

[Service]
Type=notify
User=telegcli
Group=telegcli
WorkingDirectory=/home/telegcli

# Bot environment variables

Environment="BOT_PROFILE=my_bot"
Environment="BOT_MODE=polling"
Environment="LOG_LEVEL=INFO"
Environment="TELEGCLI_CONFIG_DIR=/home/telegcli/.config/telegcli"

# Start command

ExecStart=/usr/bin/python3 -m telegcli.main --bot --profile $BOT_PROFILE

# Auto-restart on failure

Restart=always
RestartSec=10
MaxStartups=3

# Resource limits

MemoryLimit=512M
CPUQuota=50%

# Logging

StandardOutput=journal
StandardError=journal
SyslogIdentifier=telegcli-bot

[Install]
WantedBy=multi-user.target

# === socket Activation (Optional, for webhook mode) ===

# Save as: /etc/systemd/system/telegcli-bot.socket

[Unit]
Description=telegcli Bot Webhook Socket
Before=telegcli-bot.service

[Socket]
ListenStream=5000
Accept=yes

[Install]
WantedBy=sockets.target

# === Setup Commands ===

# 1. Create telegcli user:

sudo useradd -m -s /bin/bash telegcli

# 2. Install telegcli:

sudo pip install telegcli

# 3. Configure bot profile as telegcli user:

sudo -u telegcli telegcli login # Set up credentials
sudo -u telegcli bot add my_bot <YOUR_BOT_TOKEN>

# 4. Copy service files:

sudo cp telegcli-bot.service /etc/systemd/system/
sudo cp telegcli-bot.socket /etc/systemd/system/ # Optional

# 5. Enable and start service:

sudo systemctl daemon-reload
sudo systemctl enable telegcli-bot.service
sudo systemctl start telegcli-bot.service

# 6. Check status:

sudo systemctl status telegcli-bot.service
sudo journalctl -u telegcli-bot -f # Follow logs

# === Webhook Mode Setup ===

# For webhook instead of polling on port 5000:

# A. Create /etc/systemd/system/telegcli-bot-webhook.service:

# [Service]

# ExecStart=/usr/bin/python3 -m telegcli.main --bot-webhook --profile $BOT_PROFILE

# Environment="BOT_MODE=webhook"

# Environment="WEBHOOK_URL=https://yourdomain.com:5000/telegram"

# B. Set up reverse proxy (nginx):

sudo apt install nginx

# Configure /etc/nginx/sites-available/telegcli-bot to proxy to localhost:5000

sudo systemctl start nginx

# === Monitoring ===

# Check service logs:

sudo journalctl -u telegcli-bot -n 50

# Watch logs in real-time:

sudo journalctl -u telegcli-bot -f

# Check service health:

telegcli bot status
telegcli bot doctor my_bot

# Restart service:

sudo systemctl restart telegcli-bot.service

# Stop service:

sudo systemctl stop telegcli-bot.service

# Automatic restart on reboot:

sudo systemctl enable telegcli-bot.service

# === VPS Network Setup ===

# For webhook mode, configure firewall:

# ufw (Ubuntu):

sudo ufw allow 5000/tcp
sudo ufw allow 80/tcp # HTTP (for nginx redirect)
sudo ufw allow 443/tcp # HTTPS (recommended)

# Let's Encrypt SSL (strongswan/certbot with nginx):

sudo apt install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d yourdomain.com

# === Logging & Metrics ===

# View logs with timestamps:

sudo journalctl -u telegcli-bot --since "1 hour ago" --until now

# Count restarts:

sudo systemctl show telegcli-bot | grep NRestarts

# Disk usage:

du -sh ~/.config/telegcli

# === Troubleshooting ===

# Service won't start:

sudo systemctl start telegcli-bot.service
sudo journalctl -u telegcli-bot -n 100

# Module not found:

pip list | grep telegcli
pip install --upgrade telegcli

# Permission denied:

sudo chown telegcli:telegcli /home/telegcli/.config/telegcli -R

# Port already in use:

sudo lsof -i :5000
