#!/bin/bash
# STRIKIT Bot Deployment Script
# Automatically pulls the latest code, sets correct permissions, and restarts the service.

set -e # Exit immediately if a command exits with a non-zero status

echo "🚀 Starting STRIKIT Bot Deployment..."

# 1. Fetch and reset
echo "📥 Pulling latest code from main branch..."
sudo git fetch --all
sudo git reset --hard origin/main

# 2. Fix permissions (Critical to prevent 502/Crash)
echo "🔒 Fixing file permissions..."
sudo chown -R strikit:strikit /opt/strikit-bot

# 3. Restart the systemd service
echo "🔄 Restarting STRIKIT Bot service..."
sudo systemctl restart strikit-bot

# 4. Check status
echo "✅ Deployment complete. Service status:"
sudo systemctl status strikit-bot --no-pager | head -n 10
