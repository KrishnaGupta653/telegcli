FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create non-root user
RUN useradd -m -u 1000 bot && chown -R bot:bot /app

USER bot

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    BOT_MODE=polling \
    LOG_LEVEL=INFO \
    TELEGCLI_CONFIG_DIR=/home/bot/.config/telegcli

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import telegcli.bot.manager; m=telegcli.bot.manager.get_bot_manager(); s=m.service(); exit(0 if s and s.running else 1)" || exit 1

# Run bot
CMD ["python", "-m", "telegcli.main", "--bot", "--profile", "${BOT_PROFILE:-default}"]
