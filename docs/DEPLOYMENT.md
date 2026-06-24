# Production Deployment Guide

## Overview

The recommended production stack:

```
Internet → Nginx (443 SSL) → Dashboard (8000) → PostgreSQL
                             Bot ──────────────↗
```

A single VPS with 2GB RAM is sufficient for up to ~50 active guilds.

---

## Server Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 1 GB | 2 GB |
| Disk | 10 GB | 20 GB |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |

---

## Step 1 — Server Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Certbot for SSL
sudo apt install certbot -y
```

---

## Step 2 — Clone and Configure

```bash
git clone https://github.com/yourrepo/prefix-hub.git
cd prefix-hub
cp .env.example .env
nano .env    # Fill in all production values
```

Key production `.env` changes:
```env
ENVIRONMENT=production
LOG_LEVEL=WARNING
DISCORD_REDIRECT_URI=https://yourdomain.com/auth/callback
ALLOWED_ORIGINS=["https://yourdomain.com"]
DATABASE_URL=postgresql+asyncpg://prefixhub:STRONG_PASSWORD@db:5432/prefixhub
DASHBOARD_SECRET_KEY=<64-char secret>
```

---

## Step 3 — SSL Certificate

```bash
# Replace yourdomain.com with your actual domain
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com
```

Update `docker/nginx.conf` — replace `YOUR_DOMAIN` with your domain.

---

## Step 4 — Build and Deploy

```bash
# Build production images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Run migrations
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# Start all services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Step 5 — Verify

```bash
# Check all services are running
docker compose ps

# Check bot logs
docker compose logs bot --tail=50

# Check dashboard health
curl https://yourdomain.com/api/health
```

---

## Auto-restart on reboot

```bash
# Create a systemd service
sudo tee /etc/systemd/system/prefix-hub.service << 'EOF'
[Unit]
Description=Prefix Hub
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=/home/ubuntu/prefix-hub
ExecStart=docker compose -f docker-compose.yml -f docker-compose.prod.yml up
ExecStop=docker compose -f docker-compose.yml -f docker-compose.prod.yml down
Restart=always
User=ubuntu

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable prefix-hub
sudo systemctl start prefix-hub
```

---

## SSL Certificate Renewal

Certbot auto-renews, but you need to reload Nginx after renewal:

```bash
# Add to /etc/cron.d/certbot-renew
0 3 * * 1 certbot renew --quiet && docker compose -f /home/ubuntu/prefix-hub/docker-compose.yml -f /home/ubuntu/prefix-hub/docker-compose.prod.yml exec nginx nginx -s reload
```

---

## Updating

```bash
cd prefix-hub
git pull

# Rebuild images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Run any new migrations
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# Rolling restart (zero-downtime dashboard)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps bot
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps dashboard
```

---

## Monitoring

```bash
# Live resource usage
docker stats

# Bot health
docker compose logs bot -f --tail=100

# Database size
docker compose exec db psql -U prefixhub -c "SELECT pg_size_pretty(pg_database_size('prefixhub'));"

# Active connections
docker compose exec db psql -U prefixhub -c "SELECT count(*) FROM pg_stat_activity;"
```

---

## Backup

```bash
# Daily database backup (add to cron)
docker compose exec db pg_dump -U prefixhub prefixhub | gzip > /backups/prefixhub_$(date +%Y%m%d).sql.gz

# Keep last 30 days
find /backups -name "prefixhub_*.sql.gz" -mtime +30 -delete
```
