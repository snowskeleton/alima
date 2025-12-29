# Docker Deployment Guide

This guide covers deploying Alima using Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose V2

## Quick Start

1. **Copy the environment template:**
   ```bash
   cp .env.docker .env
   ```

2. **Edit `.env` and set required values:**
   - `SECRET_KEY` - Generate with: `openssl rand -hex 32`
   - `DOMAIN` - Your domain (e.g., `https://alima.yourdomain.com`)
   - Configure SMTP settings if you want email notifications

3. **Ensure data directories exist:**
   ```bash
   mkdir -p data/{audiobooks/unassigned,covers,audible_auth,temp,db}
   ```

4. **Build and start the container:**
   ```bash
   docker compose up -d
   ```

5. **Check the logs:**
   ```bash
   docker compose logs -f
   ```

6. **Access the application:**
   - Navigate to `http://localhost:8000` (or your configured domain)
   - First-time setup will prompt you to create an admin account

## Volume Mappings

All data is stored in filesystem directories (not hidden Docker volumes):

```
./data/audiobooks      → /app/data/audiobooks      (Audiobook files)
./data/covers          → /app/data/covers          (Cover images)
./data/audible_auth    → /app/data/audible_auth    (Audible credentials)
./data/temp            → /app/data/temp            (Temporary files)
./data/db              → /app/data/db              (SQLite database)
```

## Common Commands

### Start the service
```bash
docker compose up -d
```

### Stop the service
```bash
docker compose down
```

### View logs
```bash
docker compose logs -f
```

### Restart the service
```bash
docker compose restart
```

### Rebuild after code changes
```bash
docker compose up -d --build
```

### Run CLI commands
```bash
docker compose exec alima python cli.py --help
```

## Backup

### Database backup
```bash
cp data/db/alima.db data/db/alima.db.backup
```

### Full data backup
```bash
tar -czf alima-backup-$(date +%Y%m%d).tar.gz data/
```

## Using with Reverse Proxy (Caddy/Nginx)

### Caddy Example

Create a `Caddyfile`:
```
alima.yourdomain.com {
    reverse_proxy localhost:8000
}
```

Run Caddy:
```bash
caddy run
```

### Nginx Example

```nginx
server {
    listen 80;
    server_name alima.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Updating

1. Pull latest code:
   ```bash
   git pull
   ```

2. Rebuild and restart:
   ```bash
   docker compose up -d --build
   ```

## Troubleshooting

### Container won't start
- Check logs: `docker compose logs`
- Verify `.env` file has `SECRET_KEY` set
- Ensure data directories exist and have proper permissions

### Permission errors
```bash
sudo chown -R 1000:1000 data/
```

### Database errors
- Ensure `data/db/` directory exists
- Check database file permissions
- Try running: `docker compose exec alima python cli.py init-db`

### Port 8000 already in use
Edit `docker-compose.yml` and change the port mapping:
```yaml
ports:
  - "8080:8000"  # Use port 8080 instead
```

## Production Recommendations

1. **Set strong `SECRET_KEY`**: Generate with `openssl rand -hex 32`
2. **Use HTTPS**: Set `DOMAIN=https://your-domain.com` and use a reverse proxy
3. **Enable SMTP**: Configure email settings for user invites
4. **Regular backups**: Automate database and data backups
5. **Monitor logs**: Set up log aggregation and monitoring
6. **Resource limits**: Add resource constraints to `docker-compose.yml`

Example resource limits:
```yaml
services:
  alima:
    # ... other config ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

## Environment Variables Reference

See `.env.docker` for all available configuration options.

### Required Variables
- `SECRET_KEY` - Application secret key (generate with `openssl rand -hex 32`)
- `DOMAIN` - Your domain URL

### Optional Variables
- `SMTP_*` - Email configuration
- `SYNC_INTERVAL_HOURS` - How often to sync with Audible (default: 6)
- `DOWNLOAD_QUALITY` - Audio quality: High or Normal (default: High)
- `REPLICATION_MODE` - standalone/master/slave for multi-instance setups

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/alima2.0/issues
- Documentation: See `docs/` directory
