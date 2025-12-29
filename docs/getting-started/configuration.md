# Configuration

Alima can be configured through environment variables in the `.env` file.

## Required Settings

These settings must be configured before running Alima:

### SECRET_KEY

Random secret key used for session encryption and security.

```bash
# Generate with: openssl rand -hex 32
SECRET_KEY=your-random-secret-key-here
```

!!! warning "Security"
    Never commit your secret key to version control! Keep it secret.

### DOMAIN

The full URL where Alima is accessible. Used for generating invite links and RSS feed URLs.

```bash
# Local development
DOMAIN=http://localhost:8000

# Production
DOMAIN=https://alima.yourdomain.com
```

## Optional Settings

### Database

```bash
# SQLite (default)
DATABASE_URL=sqlite:///data/db/alima.db

# PostgreSQL (for production)
DATABASE_URL=postgresql://user:password@localhost/alima
```

### File Paths

Customize where Alima stores files:

```bash
AUDIOBOOKS_PATH=/path/to/audiobooks
COVERS_PATH=/path/to/covers
AUDIBLE_AUTH_PATH=/path/to/audible_auth
TEMP_PATH=/path/to/temp
```

!!! tip "Docker Volumes"
    These paths are especially useful when running in Docker to map volumes.

### Email (SMTP)

Email settings for sending invitation emails. Can also be configured via the web UI at `/admin/settings`.

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@yourdomain.com
```

!!! info "Gmail Users"
    For Gmail, you'll need to create an [App Password](https://support.google.com/accounts/answer/185833).

### Sync Settings

```bash
# How often to sync with Audible (in hours)
SYNC_INTERVAL_HOURS=6

# Download quality: Extreme, High, or Normal
DOWNLOAD_QUALITY=Extreme
```

### Session Settings

```bash
# How long sessions last (in hours)
SESSION_EXPIRE_HOURS=168  # 7 days

# How long invite links are valid (in days)
INVITE_EXPIRE_DAYS=7
```

### Advanced Settings

```bash
# Application name
APP_NAME=Alima

# Environment: development, production, testing
ENVIRONMENT=development
```

## Web-Based Configuration

Many settings (especially email settings) can also be configured through the web UI:

1. Log in as an admin user
2. Navigate to **Admin → Server Settings**
3. Configure SMTP and other settings
4. Click **Save All Settings**

!!! success "No Restart Required"
    Settings changed via the web UI take effect immediately - no need to restart the server!

## Environment File Example

A complete `.env.example` file is provided in the repository. Copy it to `.env` and customize:

```bash
cp .env.example .env
nano .env
```

## Next Steps

- [Complete first run setup](first-run.md)
- [Configure email settings via web UI](../user-guide/server-settings.md)
