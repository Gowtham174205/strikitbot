#!/bin/bash
# ============================================================================
#  STRIKIT Bot — Production Deployment Script
#  Target: AWS EC2 · Ubuntu 24.04 LTS · Python 3.11+ / FastAPI / Gunicorn
# ============================================================================
set -euo pipefail

# ── Colors & Helpers ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
success() { echo -e "${GREEN}[✔]${NC}      $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
error()   { echo -e "${RED}[✘ ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${CYAN}${BOLD}── $* ──${NC}"; }

# ── Configuration ───────────────────────────────────────────────────────────
APP_NAME="strikit-bot"
APP_USER="strikit"
APP_DIR="/opt/strikit-bot"
PYTHON_DIR="${APP_DIR}/strikit-python"
VENV_DIR="${PYTHON_DIR}/venv"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
REPO_URL="${REPO_URL:-https://github.com/your-org/strikitbot.git}"  # Override via env
DOMAIN="${DOMAIN:-your-domain.com}"                                  # Override via env
APP_PORT=5000

# ── Pre-flight checks ──────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  error "This script must be run as root (use sudo)."
fi

step "1/8  Updating system packages"
apt-get update -y && apt-get upgrade -y
success "System packages updated"

# ── Install dependencies ────────────────────────────────────────────────────
step "2/8  Installing Python 3.11+, Nginx, Certbot & tools"

apt-get install -y \
  software-properties-common \
  python3 \
  python3-pip \
  python3-venv \
  python3-dev \
  build-essential \
  nginx \
  certbot \
  python3-certbot-nginx \
  git \
  curl \
  ufw

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || { [[ "$PYTHON_MAJOR" -eq 3 ]] && [[ "$PYTHON_MINOR" -lt 11 ]]; }; then
  warn "Python ${PYTHON_VERSION} detected — 3.11+ recommended."
  info "Adding deadsnakes PPA for Python 3.11…"
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update -y
  apt-get install -y python3.11 python3.11-venv python3.11-dev
  PYTHON_BIN="python3.11"
else
  PYTHON_BIN="python3"
  success "Python ${PYTHON_VERSION} meets requirement (≥ 3.11)"
fi

# ── Create system user ──────────────────────────────────────────────────────
step "3/8  Creating system user '${APP_USER}'"

if id "${APP_USER}" &>/dev/null; then
  warn "User '${APP_USER}' already exists — skipping"
else
  useradd --system --shell /usr/sbin/nologin --home-dir "${APP_DIR}" "${APP_USER}"
  success "System user '${APP_USER}' created"
fi

# ── Clone / pull repository ────────────────────────────────────────────────
step "4/8  Setting up application at ${APP_DIR}"

if [[ -d "${APP_DIR}/.git" ]]; then
  info "Repository exists — pulling latest changes…"
  cd "${APP_DIR}"
  git fetch --all
  git reset --hard origin/main
  success "Repository updated"
else
  info "Cloning repository…"
  git clone "${REPO_URL}" "${APP_DIR}"
  success "Repository cloned to ${APP_DIR}"
fi

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

# ── Python virtual environment & dependencies ──────────────────────────────
step "5/8  Setting up Python venv & installing dependencies"

if [[ ! -d "${VENV_DIR}" ]]; then
  info "Creating virtual environment…"
  ${PYTHON_BIN} -m venv "${VENV_DIR}"
  success "Virtual environment created at ${VENV_DIR}"
else
  info "Virtual environment already exists — reusing"
fi

info "Upgrading pip…"
"${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel

info "Installing application dependencies…"
if [[ -f "${PYTHON_DIR}/requirements.txt" ]]; then
  "${VENV_DIR}/bin/pip" install -r "${PYTHON_DIR}/requirements.txt"
  success "Application dependencies installed"
else
  error "requirements.txt not found at ${PYTHON_DIR}/requirements.txt"
fi

info "Installing gunicorn…"
"${VENV_DIR}/bin/pip" install gunicorn uvicorn[standard]
success "Gunicorn + Uvicorn installed"

# Create logs directory
mkdir -p "${PYTHON_DIR}/logs"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

# ── Systemd service ────────────────────────────────────────────────────────
step "6/8  Creating systemd service"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=STRIKIT Bot — FastAPI Application
Documentation=https://github.com/your-org/strikitbot
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=notify
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${PYTHON_DIR}
EnvironmentFile=${PYTHON_DIR}/.env
ExecStart=${VENV_DIR}/bin/gunicorn app.main:app -c gunicorn.conf.py
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStartSec=30
TimeoutStopSec=30

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${PYTHON_DIR}/logs

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${APP_NAME}"
success "Systemd service created and enabled"

# ── Nginx reverse proxy ────────────────────────────────────────────────────
step "7/8  Configuring Nginx reverse proxy"

cat > "/etc/nginx/sites-available/${APP_NAME}" <<EOF
# ── STRIKIT Bot Nginx Configuration ─────────────────────────────────────
# Upstream: Gunicorn on port ${APP_PORT}
# Features: WebSocket support, long-polling, security headers

upstream strikit_backend {
    server 127.0.0.1:${APP_PORT} fail_timeout=0;
}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    # ── Security headers ────────────────────────────────────────────────
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # ── Client limits ───────────────────────────────────────────────────
    client_max_body_size 20M;
    client_body_timeout 60s;
    client_header_timeout 60s;

    # ── Logging ─────────────────────────────────────────────────────────
    access_log /var/log/nginx/${APP_NAME}_access.log;
    error_log  /var/log/nginx/${APP_NAME}_error.log;

    # ── Static files (if any) ───────────────────────────────────────────
    location /static/ {
        alias ${PYTHON_DIR}/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # ── API / Application ───────────────────────────────────────────────
    location / {
        proxy_pass http://strikit_backend;

        # Standard proxy headers
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Request-ID      \$request_id;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade           \$http_upgrade;
        proxy_set_header Connection        "upgrade";

        # Long-polling / streaming support
        proxy_read_timeout    300s;
        proxy_send_timeout    300s;
        proxy_connect_timeout 75s;
        proxy_buffering       off;

        # Retry on upstream errors
        proxy_next_upstream error timeout http_502 http_503;
        proxy_next_upstream_tries 2;
    }

    # ── Health check endpoint ───────────────────────────────────────────
    location /health {
        proxy_pass http://strikit_backend/health;
        access_log off;
    }
}
EOF

# Enable site & disable default
ln -sf "/etc/nginx/sites-available/${APP_NAME}" "/etc/nginx/sites-enabled/${APP_NAME}"
rm -f /etc/nginx/sites-enabled/default

nginx -t || error "Nginx configuration test failed!"
systemctl reload nginx
success "Nginx configured and reloaded"

# ── Firewall ────────────────────────────────────────────────────────────────
step "8/8  Configuring firewall & starting service"

ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
success "Firewall configured (SSH + Nginx)"

# ── Start the application ──────────────────────────────────────────────────
info "Starting ${APP_NAME} service…"
systemctl start "${APP_NAME}"

if systemctl is-active --quiet "${APP_NAME}"; then
  success "${APP_NAME} is running!"
else
  error "Service failed to start. Check logs with: journalctl -u ${APP_NAME} -n 50"
fi

# ── SSL Setup Instructions ──────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}${BOLD}  🔒  SSL Certificate Setup (run after DNS is configured)${NC}"
echo -e "${CYAN}${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${YELLOW}sudo certbot --nginx -d ${DOMAIN}${NC}"
echo ""
echo -e "  Certbot will automatically:"
echo -e "    • Obtain a free Let's Encrypt certificate"
echo -e "    • Configure Nginx for HTTPS"
echo -e "    • Set up auto-renewal via systemd timer"
echo ""
echo -e "  To test auto-renewal:"
echo -e "    ${YELLOW}sudo certbot renew --dry-run${NC}"
echo ""

# ── Quick Reference ─────────────────────────────────────────────────────────
echo -e "${CYAN}${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}${BOLD}  📋  Service Management Quick Reference${NC}"
echo -e "${CYAN}${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Service Control:${NC}"
echo -e "    ${GREEN}sudo systemctl start ${APP_NAME}${NC}      # Start"
echo -e "    ${GREEN}sudo systemctl stop ${APP_NAME}${NC}       # Stop"
echo -e "    ${GREEN}sudo systemctl restart ${APP_NAME}${NC}    # Restart"
echo -e "    ${GREEN}sudo systemctl status ${APP_NAME}${NC}     # Status"
echo ""
echo -e "  ${BOLD}Log Viewing (like PM2):${NC}"
echo -e "    ${GREEN}journalctl -u ${APP_NAME} -f${NC}              # Live tail (like pm2 logs)"
echo -e "    ${GREEN}journalctl -u ${APP_NAME} -n 100${NC}          # Last 100 lines"
echo -e "    ${GREEN}journalctl -u ${APP_NAME} --since today${NC}   # Today's logs"
echo -e "    ${GREEN}journalctl -u ${APP_NAME} --since '1 hour ago'${NC}"
echo -e "    ${GREEN}journalctl -u ${APP_NAME} -p err${NC}          # Errors only"
echo ""
echo -e "  ${BOLD}Application Logs:${NC}"
echo -e "    ${GREEN}tail -f ${PYTHON_DIR}/logs/access.log${NC}  # Gunicorn access"
echo -e "    ${GREEN}tail -f ${PYTHON_DIR}/logs/error.log${NC}   # Gunicorn errors"
echo ""
echo -e "  ${BOLD}Deployment (re-deploy):${NC}"
echo -e "    ${GREEN}cd ${APP_DIR} && git pull${NC}"
echo -e "    ${GREEN}${VENV_DIR}/bin/pip install -r ${PYTHON_DIR}/requirements.txt${NC}"
echo -e "    ${GREEN}sudo systemctl restart ${APP_NAME}${NC}"
echo ""
echo -e "${GREEN}${BOLD}  ✅  Deployment complete!${NC}"
echo ""
