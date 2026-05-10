#!/bin/bash

# NovaBot Automated SSL & Nginx Configuration Script
# This script installs Nginx, configures a reverse proxy to Uvicorn (Port 8000), 
# and provisions a free Let's Encrypt SSL certificate.

if [ "$EUID" -ne 0 ]; then 
    echo "❌ Please run as root (use sudo bash setup_ssl.sh <your_domain>)"
    exit 1
fi

if [ -z "$1" ]; then
    echo "❌ You must provide your domain name!"
    echo "Usage: sudo bash setup_ssl.sh yourdomain.com"
    exit 1
fi

DOMAIN=$1
EMAIL="admin@$DOMAIN" # Certbot requires an email

echo "🚀 Starting Nginx & SSL setup for $DOMAIN..."

# 1. Install dependencies
echo "📦 Installing Nginx and Certbot..."
apt update
apt install -y nginx certbot python3-certbot-nginx

# 2. Create Nginx Configuration
echo "⚙️ Configuring Nginx reverse proxy for FastAPI (Port 8000)..."
cat > /etc/nginx/sites-available/novabot <<EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # WebSocket support for NovaBot Terminal
    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }
}
EOF

# 3. Enable the site
echo "🔗 Enabling Nginx site..."
# Remove default site if it exists
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/novabot /etc/nginx/sites-enabled/novabot

# 4. Restart Nginx
systemctl restart nginx

# 5. Run Certbot for SSL
echo "🔒 Requesting SSL Certificate from Let's Encrypt..."
certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos -m $EMAIL --redirect

if [ $? -eq 0 ]; then
    echo "✅ SUCCESS! NovaBot is now securely hosted at https://$DOMAIN"
    echo "WebAuthn Passkeys will now work perfectly across all browsers!"
else
    echo "❌ Certbot failed. Please ensure your domain's DNS A Record points to this server's IP (80.225.216.191) and has propagated."
fi
