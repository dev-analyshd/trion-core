# TRION Protocol — Production Deployment Guide

## Overview

TRION Protocol is a multi-component behavioral oracle system. This guide covers
production deployment using systemd, Docker, or manual startup.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Nginx Reverse Proxy                      │
│                  (SSL termination, rate limiting)            │
└──────────────┬──────────────────────────┬───────────────────┘
               │                          │
    ┌──────────▼──────────┐    ┌──────────▼──────────┐
    │  Frontend Dashboard │    │   Oracle API (5000)  │
    │    (Next.js 3000)   │    │   (Flask/Gunicorn)   │
    └─────────────────────┘    └──────────┬──────────┘
                                         │
                        ┌────────────────┼────────────────┐
                        │                │                │
              ┌─────────▼──────┐ ┌──────▼────────┐ ┌─────▼──────────┐
              │ FAISS Engine   │ │ Validator P2P │ │  BTCP Router   │
              │  (port 8000)   │ │ (port 6000)   │ │ (ZK + VMs)     │
              └────────────────┘ └───────────────┘ └────────────────┘
```

## Quick Start (Docker Compose)

```bash
# Build and start all services
cd deploy/docker
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api faiss
```

## Production Deployment (systemd)

### 1. Install Dependencies

```bash
# System packages
sudo apt-get update && sudo apt-get install -y \
    python3 python3-pip python3-venv \
    nginx certbot python3-certbot-nginx \
    nodejs npm

# Create service user
sudo useradd -r -s /bin/false trion
sudo mkdir -p /opt/trion /opt/trion/data /opt/trion/logs
sudo chown -R trion:trion /opt/trion
```

### 2. Install Application

```bash
# Clone repository
sudo -u trion git clone https://github.com/dev-analyshd/trion-core.git /opt/trion

# Python dependencies
cd /opt/trion
sudo -u trion python3 -m venv venv
sudo -u trion venv/bin/pip install -r requirements.txt gunicorn

# Frontend dependencies
cd /opt/trion/frontend
sudo -u trion npm ci
sudo -u trion npm run build
```

### 3. Install Systemd Services

```bash
# Copy service files
sudo cp deploy/systemd/*.service /etc/systemd/system/

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable trion-faiss trion-api trion-validator trion-frontend
sudo systemctl start trion-faiss
sleep 5
sudo systemctl start trion-api
sleep 3
sudo systemctl start trion-validator trion-frontend

# Check status
sudo systemctl status trion-faiss trion-api trion-validator trion-frontend
```

### 4. Configure Nginx

```bash
# Copy nginx config
sudo cp deploy/nginx/trion.conf /etc/nginx/conf.d/

# Test and reload
sudo nginx -t
sudo systemctl reload nginx

# Obtain SSL certificate
sudo certbot --nginx -d trion.example.com
```

## Configuration

### Environment Variables

Create `/opt/trion/config/deployment.env`:

```env
# Service Ports
FAISS_PORT=8000
API_PORT=5000
VALIDATOR_PORT=6000
FRONTEND_PORT=3000

# Chain Configuration
CHAIN_ID=421614
NETWORK=arbitrum-sepolia
ORACLE_ADDRESS=0x1d129D34279d1246aB08a41dfE610EaF8D794237

# External Service URLs
FAISS_SERVICE_URL=http://127.0.0.1:8000
FLASK_URL=http://127.0.0.1:5000

# Bootstrap Configuration
SIGMA_BOOTSTRAP=0.25
K_BOOTSTRAP=0.10
THETA_MIN=0.55
THETA_MAX=0.92

# Security
GK_EVOLUTION_INTERVAL=100
CRISPR_LIBRARY_SIZE=4
```

## Monitoring

### Prometheus + Grafana

```bash
# Start monitoring stack
cd deploy/docker
docker-compose up -d prometheus grafana

# Access Grafana at http://localhost:3001
# Default credentials: admin / admin (change immediately!)
```

### Key Metrics to Monitor

| Metric | Threshold | Alert Severity |
|--------|-----------|----------------|
| API uptime | < 99.9% | Critical |
| FAISS uptime | < 99.9% | Critical |
| API p95 latency | > 2s | Warning |
| 5xx error rate | > 5% | Warning |
| Memory usage | > 85% | Warning |
| CPU usage | > 90% | Warning |
| Disk space | < 15% free | Warning |
| Validator count | < 7 | Warning |
| Coherence score | < 0.3 (15m) | Info |

## BTCP Cross-Chain Deployment

### Supported VMs and Chains

| VM Type | Chains | Status |
|---------|--------|--------|
| EVM | Ethereum, Arbitrum, Optimism, Polygon, BSC, Base, Avalanche | ✅ Production |
| SVM | Solana | ✅ Beta |
| Cosmos | Cosmos Hub, Osmosis, Celestia | ✅ Beta |
| Move | Aptos, Sui | 🔬 Alpha |
| CosmWasm | Juno, Terra | 🔬 Alpha |
| OOA | Fuel | 🔬 Research |

### Privacy Levels

| Level | ZK Proofs | Use Case |
|-------|-----------|----------|
| PUBLIC | None | Public transfers, low value |
| BASIC | Intent Commitment | Standard swaps |
| STANDARD | + Complementarity | High-value transfers |
| COMPLIANT | + Travel Rule | Regulated entities |
| FULL | + Behavioral Credential | Institutional, maximum privacy |

## Security Hardening

### Systemd Sandboxing

All services include:
- `NoNewPrivileges=true` — Prevent privilege escalation
- `ProtectSystem=strict` — Read-only filesystem
- `ProtectHome=true` — No home directory access
- `PrivateTmp=true` — Private /tmp
- `PrivateDevices=true` — No device access
- `MemoryDenyWriteExecute=true` — Prevent W^X violations

### Network Security

- Nginx rate limiting: 100 req/s API, 10 req/s signal endpoint
- Connection limits: 50 concurrent per IP
- TLS 1.2+ only with strong cipher suites
- HSTS enabled (1 year)
- All internal services on private Docker network

### API Security

- Input validation on all endpoints
- Entity ID format validation
- CORS configuration
- No debug mode in production
- Request size limits (10MB)

## Backup and Recovery

### Data Backup

```bash
# FAISS index backup
tar czf faiss-backup-$(date +%Y%m%d).tar.gz /opt/trion/data/faiss.index

# Configuration backup
tar czf config-backup-$(date +%Y%m%d).tar.gz /opt/trion/config/

# Offsite backup (example with S3)
aws s3 cp faiss-backup-*.tar.gz s3://trion-backups/
```

### Recovery Procedure

```bash
# Stop services
sudo systemctl stop trion-frontend trion-validator trion-api trion-faiss

# Restore FAISS index
tar xzf faiss-backup-YYYYMMDD.tar.gz -C /

# Restore configuration
tar xzf config-backup-YYYYMMDD.tar.gz -C /

# Restart services
sudo systemctl start trion-faiss
sleep 5
sudo systemctl start trion-api trion-validator trion-frontend
```

## Troubleshooting

### Common Issues

**FAISS won't start:**
- Check Python dependencies: `pip install -r requirements.txt`
- Verify index file exists: `ls -la /opt/trion/data/`
- Check logs: `journalctl -u trion-faiss -f`

**API returns 503:**
- FAISS not running: `systemctl status trion-faiss`
- Check connection: `curl http://127.0.0.1:8000/healthz`
- Restart API: `systemctl restart trion-api`

**Frontend shows no data:**
- API not reachable: check nginx and API service
- CORS misconfiguration: verify nginx headers
- Check browser console for errors

**Low coherence scores:**
- Normal for new entities (bootstrap phase)
- Check FAISS index population
- Verify chain RPC connections

### Log Locations

| Service | Log Location |
|---------|-------------|
| FAISS | `/opt/trion/logs/faiss.log` |
| API | `/opt/trion/logs/api.log` |
| Validator | `/opt/trion/logs/validator.log` |
| Frontend | `/opt/trion/logs/frontend.log` |
| Nginx | `/var/log/nginx/trion.*.log` |
| Systemd | `journalctl -u trion-*` |

## Performance Tuning

### Gunicorn Workers

Set workers to `2 × CPU cores + 1`:

```ini
# /etc/systemd/system/trion-api.service
ExecStart=/usr/bin/gunicorn --workers 9 --bind 127.0.0.1:5000 api.app:app
```

### FAISS Performance

- Use GPU build for large indices (>1M vectors)
- Tune `nprobe` parameter for search speed/accuracy tradeoff
- Enable prefetch for SSD storage

### Database Optimization

- Use PostgreSQL for production (replace SQLite)
- Set appropriate connection pool size
- Index frequently queried columns

## Scaling

### Horizontal Scaling

```yaml
# docker-compose override for API scaling
services:
  api:
    deploy:
      replicas: 4
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

### FAISS Sharding

For very large indices (>10M vectors):
1. Split entities across multiple FAISS instances
2. Use consistent hashing for entity→shard mapping
3. Aggregate results from all shards

## Support

- Repository: https://github.com/dev-analyshd/trion-core
- Documentation: See `docs/` directory
- Issues: GitHub Issues

---

*Last updated: 2026-08-15*
*TRION Protocol v2.0.0*
