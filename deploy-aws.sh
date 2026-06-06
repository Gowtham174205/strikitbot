#!/bin/bash
# =========================================================================
# STRIKIT BOT - AWS EC2 AUTOMATED DEPLOYMENT SCRIPT (Ubuntu 24.04 LTS)
# =========================================================================

# Exit immediately if a command exits with a non-zero status
set -e

echo "🚀 Starting STRIKIT Bot Deployment Setup..."

# Update package lists
sudo apt-get update -y
sudo apt-get upgrade -y

# Install Essential Utilities
sudo apt-get install -y curl git nginx certbot python3-certbot-nginx build-essential

# 1. Install Node.js (v20.x LTS)
echo "📦 Installing Node.js v20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify Node and NPM installation
node -v
npm -v

# 2. Install PM2 (Process Manager) Globally
echo "📦 Installing PM2 globally..."
sudo npm install -y pm2 -g

# 3. Pull Project Repo
# Note: User should replace this with their repository URL
echo "📥 Git repo configuration..."
# git clone <your-git-repo-url> strikit-bot
# cd strikit-bot

# 4. Install NPM Dependencies
# npm install
# npx prisma generate

# 5. Setup PM2 Startup
echo "⚙️ Configuring PM2 boot startup..."
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u ubuntu --hp /home/ubuntu

# 6. Configure Nginx Reverse Proxy
echo "🌐 Configuring Nginx reverse proxy..."
cat << 'EOF' | sudo tee /etc/nginx/sites-available/strikit-bot
server {
    listen 80;
    server_name YOUR_DOMAIN; # Replace with your domain (e.g., bot.strikit.in)

    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

# Enable the Nginx site config
sudo ln -sf /etc/nginx/sites-available/strikit-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx syntax and restart Nginx
sudo nginx -t
sudo systemctl restart nginx

echo "========================================================================="
echo "✅ System packages, Node.js, PM2, and Nginx reverse proxy are ready!"
echo "========================================================================="
echo "Next Steps to complete setup manually:"
echo "1. Run: cd strikit-bot"
echo "2. Edit '.env' file: nano .env"
echo "3. Start app: pm2 start src/server.js --name strikit-bot"
echo "4. Save process list: pm2 save"
echo "5. Get Free SSL (replace with your domain and email):"
echo "   sudo certbot --nginx -d YOUR_DOMAIN --non-interactive --agree-tos -m YOUR_EMAIL"
echo "========================================================================="
